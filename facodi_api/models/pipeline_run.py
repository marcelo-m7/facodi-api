"""Models for FACODI Content Pipeline runs, artifacts and Project mirroring."""

from __future__ import annotations

import hashlib
import base64
import json
import logging
import os
import uuid
from html import escape

from odoo import api, fields, models, tools
from odoo.exceptions import AccessError, UserError, ValidationError

from ..core.contracts.dtos import (
    CatalogSnapshot,
    ContentSource,
    PipelineRun,
    RunStatus,
    SourceType,
    TargetEntity,
)
from ..core.pipeline.runner import PipelineRunner
from ..core.enrichment.provider import BaselineDeterministicProvider, GeminiStructuredProvider, EnrichmentError
from ..core.ingestion.document import DocumentAcquisitionError
from ..core.submission_lock import SubmissionAdvisoryLock
from ..core.contracts.lifecycle import (
    InvalidTransition, RevisionConflict, command_transition, failure_status,
)

_logger = logging.getLogger(__name__)


class SubmissionConflict(ValueError):
    pass


class SubmissionBusy(ValueError):
    pass


class PipelineSourceError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


class FacodiPipelineRun(models.Model):
    """Execution record of content ingestion and enrichment pipeline."""

    _name = "facodi.pipeline.run"
    _description = "FACODI Pipeline Run"
    _inherit = ["mail.thread"]
    _order = "id desc"

    name = fields.Char(string="Run Reference", required=True, default=lambda self: str(uuid.uuid4())[:8], tracking=True)
    run_id = fields.Char(string="Run UUID", required=True, index=True, default=lambda self: str(uuid.uuid4()))
    idempotency_key = fields.Char(string="Idempotency Key", index=True)
    owner_id = fields.Many2one("res.users", required=True, readonly=True, index=True, default=lambda self: self.env.user)
    company_id = fields.Many2one("res.company", required=True, readonly=True, index=True, default=lambda self: self.env.company)
    request_hash = fields.Char(readonly=True)
    website_id = fields.Many2one("website", readonly=True, index=True, ondelete="restrict")
    legacy_status = fields.Char(readonly=True)
    legacy_quarantined = fields.Boolean(readonly=True, default=False, index=True)
    is_manual_transcript = fields.Boolean(default=False, help="Explicit caller-supplied transcript; no provider acquisition is claimed.")
    source_type = fields.Selection(
        [
            ("youtube", "YouTube Video"),
            ("document", "Document / PDF / DOCX"),
            ("manual", "Manual Text"),
            ("markdown", "Markdown Text"),
        ],
        string="Source Type",
        required=True,
        default="document",
        tracking=True,
    )
    source_url = fields.Char(string="Source URL")
    title = fields.Char(string="Content Title")
    raw_content = fields.Text(string="Raw Content")
    language = fields.Char(string="Language", default="pt")

    status = fields.Selection(
        [
            ("received", "Received"),
            ("running", "Running"),
            ("succeeded", "Succeeded"),
            ("waiting_review", "Waiting Manager Review"),
            ("published", "Published"),
            ("failed", "Failed"),
            ("waiting_input", "Waiting for Input"),
            ("cancelled", "Cancelled"),
        ],
        string="Status",
        default="received",
        required=True,
        tracking=True,
    )

    project_id = fields.Many2one("project.project", string="Project", ondelete="set null")
    task_id = fields.Many2one("project.task", string="Project Task", ondelete="set null")
    target_channel_id = fields.Many2one("slide.channel", string="Publication Course", index=True, ondelete="restrict")
    published_slide_id = fields.Many2one("slide.slide", string="Published Content", readonly=True, copy=False, ondelete="restrict")
    reviewed_by_id = fields.Many2one("res.users", string="Reviewed By", readonly=True, copy=False)
    reviewed_at = fields.Datetime(string="Reviewed At", readonly=True, copy=False)
    error_message = fields.Text(string="Error Message")
    artifacts_json = fields.Text(string="Artifacts JSON (Cache)")
    metadata_json = fields.Text(string="Metadata JSON")
    revision = fields.Integer(default=0, readonly=True)
    attempt_count = fields.Integer(default=0, readonly=True)
    history_json = fields.Text(readonly=True)
    input_parent_id = fields.Many2one("facodi.pipeline.run", readonly=True, ondelete="restrict")
    input_revision_ids = fields.One2many("facodi.pipeline.run", "input_parent_id", readonly=True)
    attachment_id = fields.Many2one("ir.attachment", readonly=True, ondelete="restrict")
    attachment_digest = fields.Char(readonly=True)
    attachment_name_snapshot = fields.Char(readonly=True)
    existing_slide_id = fields.Many2one("slide.slide", readonly=True, ondelete="restrict")
    existing_slide_hash = fields.Char(readonly=True)
    provider_config_json = fields.Text(readonly=True)
    catalog_snapshot_json = fields.Text(readonly=True)

    # Metrics
    execution_time = fields.Float(string="Total Execution Time (s)")
    concepts_count = fields.Integer(string="Concepts Count")
    chunks_count = fields.Integer(string="Chunks Count")

    _idempotency_scope_uniq = models.Constraint(
        "UNIQUE(owner_id, company_id, idempotency_key)",
        "Idempotency key must be unique per owner and company.",
    )

    _run_uuid_uniq = models.Constraint("UNIQUE(run_id)", "Run UUID must be unique.")

    _submission_fields = frozenset({
        "name", "source_type", "source_url", "title", "raw_content", "language",
        "idempotency_key", "target_channel_id", "is_manual_transcript", "attachment_id", "existing_slide_id",
    })
    _reserved_fields = frozenset({
        "run_id", "owner_id", "company_id", "website_id", "request_hash", "status",
        "source_type", "source_url", "title", "raw_content", "language",
        "idempotency_key", "target_channel_id", "is_manual_transcript",
        "legacy_quarantined", "legacy_status", "project_id", "task_id", "published_slide_id",
        "reviewed_by_id", "reviewed_at", "error_message", "artifacts_json",
        "metadata_json", "execution_time", "concepts_count", "chunks_count",
    })

    @api.model
    def _normalize_submission(self, values):
        if set(values) - self._submission_fields:
            raise AccessError("Generated identity, state and provenance cannot be supplied.")
        vals = dict(values)
        vals.setdefault("source_type", "document")
        vals.setdefault("language", "pt")
        for field, limit in (("source_type", 20), ("source_url", 2048), ("title", 256),
                             ("language", 20), ("raw_content", 262144), ("name", 256)):
            value = vals.get(field) or ""
            if not isinstance(value, str) or len(value.encode("utf-8")) > limit:
                raise ValidationError("Invalid or oversized source field: %s" % field)
            vals[field] = value
        if vals["source_type"] not in {"youtube", "manual", "markdown", "document"}:
            raise ValidationError("Unsupported source type.")
        key = vals.get("idempotency_key")
        if not isinstance(key, str) or not 1 <= len(key) <= 128 or any(ord(char) < 32 or ord(char) == 127 for char in key):
            raise ValidationError("Idempotency key is required (1–128 characters).")
        manual = vals.get("is_manual_transcript", False)
        if not isinstance(manual, bool):
            raise ValidationError("is_manual_transcript must be boolean.")
        vals["is_manual_transcript"] = manual
        for field in ('attachment_id', 'existing_slide_id'):
            value = vals.get(field, False)
            if value is not False and (type(value) is not int or value <= 0):
                raise ValidationError('Invalid source record identity.')
            vals[field] = value
        if vals['attachment_id'] and (vals['source_type'] != 'document' or vals['source_url'] or vals['raw_content']):
            raise ValidationError('Attachment input cannot include a URL or text payload.')
        if vals["source_type"] == "youtube":
            from ..core.ingestion.youtube import YouTubeIngestionAdapter
            if not YouTubeIngestionAdapter.extract_video_id(vals["source_url"]):
                raise ValidationError("Invalid HTTPS YouTube URL.")
            if vals["raw_content"] and not manual:
                raise ValidationError("A supplied transcript must be marked explicitly.")
        if (vals["source_type"] != "youtube" or manual) and not vals["raw_content"].strip() and not vals['attachment_id']:
            raise ValidationError("Nonempty source content is required.")
        channel_id = vals.get("target_channel_id")
        if isinstance(channel_id, bool) or not isinstance(channel_id, int) or channel_id <= 0:
            raise ValidationError("An authorized publication course is required.")
        return vals

    @api.model
    def _submission_fingerprint(self, vals):
        payload = {key: vals[key] for key in sorted(self._submission_fields - {"name"})}
        # Absent optional fields preserve v2 idempotency fingerprints.
        for field in ('attachment_id', 'existing_slide_id'):
            if not payload[field]:
                payload.pop(field)
        if vals['attachment_id']:
            payload['attachment_digest'] = self._attachment_details(vals['attachment_id'], vals['target_channel_id'])[1]
        if vals['existing_slide_id']:
            slide = self._authorize_existing_slide(vals['existing_slide_id'], vals['target_channel_id'])
            self._validate_existing_slide_source(slide, vals)
            payload['existing_slide_hash'] = self._canonical_source_hash(slide)
        return hashlib.sha256(json.dumps(payload, sort_keys=True, allow_nan=False).encode()).hexdigest()

    @api.model
    def _server_provider_configuration(self):
        params = self.env['ir.config_parameter'].sudo()
        provider = params.get_param('facodi_api.enrichment_provider', 'baseline')
        if provider == 'baseline':
            return {'provider': 'baseline', 'version': 'regex-frequency-v2-evidence'}
        if provider != 'gemini':
            raise ValidationError('Unsupported enrichment provider configuration.')
        model = params.get_param('facodi_api.enrichment_model', '')
        try:
            budget = int(params.get_param('facodi_api.enrichment_max_output_tokens', '4096'))
            instance = GeminiStructuredProvider(model=model, max_output_tokens=budget)
        except (TypeError, ValueError):
            raise ValidationError('Configure a supported enrichment model and bounded output budget.') from None
        return {'provider': 'gemini', **instance.cache_identity()}

    def _accepted_enrichment_provider(self):
        config = json.loads(self.provider_config_json or '{"provider":"baseline"}')
        if config.get('provider') == 'baseline':
            return BaselineDeterministicProvider()
        if config.get('provider') == 'gemini':
            return GeminiStructuredProvider(model=config['model'], max_output_tokens=config['max_output_tokens'])
        raise ValidationError('Accepted enrichment provider configuration is invalid.')

    @api.model
    def _build_catalog_snapshot(self, channel):
        domain = [('active', '=', True), ('website_id', '=', channel.website_id.id),
                  ('website_id.company_id', '=', self.env.company.id)]
        channels = self.env['slide.channel'].search(domain, limit=5001, order='id')
        if len(channels) > 5000:
            raise ValidationError('Catalog exceeds the explicit 5000-course snapshot budget; narrow the processing scope.')
        targets = [TargetEntity(id='channel_%s' % course.id, type='course', name=course.name,
                                description=tools.html2plaintext(course.description or '')[:8000],
                                tags=course.tag_ids.mapped('name'), topics=[],
                                metadata={'model': 'slide.channel', 'res_id': course.id,
                                          'website_id': course.website_id.id, 'company_id': self.env.company.id})
                   for course in channels]
        identity = hashlib.sha256(json.dumps([target.to_dict() for target in targets], sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        snapshot = CatalogSnapshot(snapshot_id='catalog-%s-%s' % (channel.website_id.id, identity[:20]),
                                   created_at=fields.Datetime.now().isoformat(), targets=targets,
                                   metadata={'company_id': self.env.company.id, 'website_id': channel.website_id.id,
                                             'ranking': 'lexical score; not calibrated probability'})
        if len(json.dumps(snapshot.to_dict()).encode()) > 4 * 1024 * 1024:
            raise ValidationError('Catalog exceeds the explicit four MiB snapshot budget.')
        return snapshot

    @api.model
    def _authorize_existing_slide(self, slide_id, channel_id):
        slide = self.env['slide.slide'].browse(slide_id).exists()
        if not slide or slide.channel_id.id != channel_id:
            raise AccessError('Source content must belong to the accepted course.')
        slide.check_access('read')
        slide.check_access('write')
        return slide

    @api.model
    def _canonical_source_hash(self, slide):
        digest = hashlib.sha256()
        for name in ('name', 'description', 'html_content', 'binary_content', 'video_url', 'slide_category', 'source_type', 'channel_id'):
            field = slide._fields[name]
            value = (field._get_stored_translations(slide) or {} if field.translate and field.store else slide[name])
            if field.type == 'many2one':
                value = value.id
            value = value if isinstance(value, bytes) else json.dumps(value or False, sort_keys=True, ensure_ascii=False).encode()
            digest.update(name.encode() + b'\0' + value + b'\0')
        return digest.hexdigest()

    @api.model
    def _validate_existing_slide_source(self, slide, vals):
        """Bind caller input to the selected canonical slide before processing."""
        if slide.slide_category == 'video':
            canonical_url = slide.video_url or slide.url or ''
            if vals['source_type'] != 'youtube' or vals['source_url'] != canonical_url:
                raise ValidationError('The submitted video must match the selected canonical content.')
            # Explicit manual transcripts are immutable input revisions; their
            # text is evidence supplied for the canonical video, not a URL swap.
            return
        if slide.slide_category == 'document':
            if vals['source_type'] != 'document' or not vals['attachment_id']:
                raise ValidationError('The submitted document must match the selected canonical content.')
            return
        canonical_text = tools.html2plaintext(slide.html_content or slide.description or '').strip()
        if not canonical_text:
            canonical_text = (getattr(slide, 'facodi_transcript', '') or '').strip()
        if vals['source_type'] not in {'manual', 'markdown'} or vals['raw_content'].strip() != canonical_text:
            raise ValidationError('The submitted text must match the selected canonical content.')

    @api.model
    def _attachment_details(self, attachment_id, channel_id, *, accepted_run=None):
        trusted = bool(accepted_run and accepted_run.exists()
                       and accepted_run.attachment_id.id == attachment_id
                       and accepted_run.target_channel_id.id == channel_id)
        Attachment = self.env['ir.attachment'].sudo() if trusted else self.env['ir.attachment']
        attachment = Attachment.browse(attachment_id).exists()
        if not attachment or attachment.type != 'binary':
            raise ValidationError('A binary attachment is required.')
        if not trusted:
            attachment.check_access('read')
        if attachment.res_model == 'slide.slide' and attachment.res_id:
            self._authorize_existing_slide(attachment.res_id, channel_id)
        elif attachment.res_model or attachment.res_id or (not trusted and attachment.create_uid != self.env.user):
            raise AccessError('Attachment is outside the accepted content scope.')
        if attachment.file_size > 2 * 1024 * 1024:
            raise ValidationError('Attachment exceeds two MiB.')
        extension = os.path.splitext(attachment.name or '')[1].lower()
        if extension not in {'.pdf', '.docx', '.txt', '.md'}:
            raise ValidationError('Attachment format is unsupported.')
        content = attachment.raw
        if not content or len(content) > 2 * 1024 * 1024:
            raise ValidationError('Attachment is empty or oversized.')
        accepted_digest = hashlib.sha256(content + b'\0' + (attachment.name or '').encode()).hexdigest()
        return content, accepted_digest, attachment.name

    def _prepare_content_source(self):
        if self.existing_slide_id:
            slide = self._authorize_existing_slide(self.existing_slide_id.id, self.target_channel_id.id)
            if self._canonical_source_hash(slide) != self.existing_slide_hash:
                raise PipelineSourceError('CANONICAL_INPUT_CHANGED')
            self._validate_existing_slide_source(slide, {
                'source_type': self.source_type, 'source_url': self.source_url or '',
                'raw_content': self.raw_content or '', 'attachment_id': self.attachment_id.id,
            })
        content, filename = None, None
        if self.attachment_id:
            content, digest, filename = self._attachment_details(
                self.attachment_id.id, self.target_channel_id.id, accepted_run=self,
            )
            if digest != self.attachment_digest or filename != self.attachment_name_snapshot:
                raise PipelineSourceError('ATTACHMENT_CHANGED')
        return ContentSource(
            source_type=SourceType(self.source_type), url=self.source_url,
            title=self.title, raw_content=self.raw_content, language=self.language or 'pt',
            raw_file_bytes=content, raw_file_name=filename,
            metadata={'is_manual_transcript': self.is_manual_transcript},
        )

    @api.model
    def submit(self, values):
        """Authorized async command used by HTTP and in-process adapters.

        The dedicated cursor observes committed intake even when the caller's
        REPEATABLE READ snapshot predates the competing transaction.
        """
        self._check_pipeline_enabled()
        self.check_access("create")
        values = self._normalize_submission(values)
        self._authorize_channel(self.env["slide.channel"].browse(values["target_channel_id"]), self.env.company)
        fingerprint = self._submission_fingerprint(values)
        scope = [("owner_id", "=", self.env.uid), ("company_id", "=", self.env.company.id),
                 ("idempotency_key", "=", values["idempotency_key"])]
        local = self.search(scope, limit=1)
        if local:
            if local.request_hash != fingerprint:
                raise SubmissionConflict("Idempotency key conflicts with the accepted payload.")
            return local._submission_receipt(False)
        lock_key = f"facodi-pipeline:{self.env.company.id}:{self.env.uid}:{values['idempotency_key']}"
        try:
            with self.env.cr.savepoint():
                self.env.cr.execute("SET LOCAL lock_timeout = '10s'")
                self.env.cr.execute(
                    "SELECT pg_advisory_lock(hashtextextended(%s, 0))",
                    [lock_key],
                )
                self.env.cr.execute("SET LOCAL lock_timeout = DEFAULT")
        except Exception:
            raise SubmissionBusy("Submission busy; retry with the same key.") from None

        lock = SubmissionAdvisoryLock(self.env.cr, lock_key)

        self.env.cr.postcommit.add(lock.release)
        self.env.cr.postrollback.add(lock.release)
        try:
            with self.env.registry.cursor() as committed_cursor:
                committed_cursor.execute(
                    """SELECT id, run_id, idempotency_key, request_hash, status, create_date, revision
                       FROM facodi_pipeline_run WHERE owner_id=%s AND company_id=%s AND idempotency_key=%s LIMIT 1""",
                    [self.env.uid, self.env.company.id, values["idempotency_key"]],
                )
                existing = committed_cursor.fetchone()
        except Exception:
            lock.release()
            raise
        if existing:
            record_id, run_id, key, accepted_hash, status, created_at, revision = existing
            lock.release()
            if accepted_hash != fingerprint:
                raise SubmissionConflict("Idempotency key conflicts with the accepted payload.")
            return {"id": record_id, "run_id": run_id, "idempotency_key": key,
                    "status": status, "revision": revision, "created": False,
                    "created_at": created_at.isoformat() if created_at else None}
        try:
            return self.create(values)._submission_receipt(True)
        except Exception:
            lock.release()
            raise

    def _submission_receipt(self, created):
        self.ensure_one()
        self.check_access("read")
        return {"id": self.id, "run_id": self.run_id, "idempotency_key": self.idempotency_key,
                "status": self.status, "revision": self.revision, "created": created,
                "created_at": self.create_date.isoformat() if self.create_date else None}

    @api.model
    def _authorize_channel(self, channel, company, website=None, *, publication=False):
        if not channel.exists():
            raise ValidationError("Course not found.")
        channel.check_access("read")
        if not channel.active or not channel.website_id or channel.website_id.company_id != company:
            raise AccessError("The course must belong to a website in the run company.")
        if website and channel.website_id != website:
            raise AccessError("The course website changed after intake.")
        if publication or self.env.user.has_group("facodi_api.group_pipeline_reviewer"):
            channel.check_access("write")
        elif channel.user_id != self.env.user:
            raise AccessError("Operators may submit only to courses they own.")

    @api.model_create_multi
    def create(self, vals_list):
        self._check_pipeline_enabled()
        self.check_access("create")
        prepared = []
        for values in vals_list:
            vals = self._normalize_submission(values)
            channel = self.env["slide.channel"].browse(vals["target_channel_id"])
            self._authorize_channel(channel, self.env.company)
            vals.update({
                "run_id": str(uuid.uuid4()), "owner_id": self.env.user.id,
                "company_id": self.env.company.id, "website_id": channel.website_id.id,
                "request_hash": self._submission_fingerprint(vals), "status": "received",
                "name": vals["name"] or vals["title"] or "Content intake",
            })
            if vals['attachment_id']:
                _content, digest, filename = self._attachment_details(vals['attachment_id'], channel.id)
                vals.update(attachment_digest=digest, attachment_name_snapshot=filename)
            if vals['existing_slide_id']:
                slide = self._authorize_existing_slide(vals['existing_slide_id'], channel.id)
                self._validate_existing_slide_source(slide, vals)
                vals['existing_slide_hash'] = self._canonical_source_hash(slide)
            vals['provider_config_json'] = json.dumps(self._server_provider_configuration(), sort_keys=True)
            vals['catalog_snapshot_json'] = json.dumps(self._build_catalog_snapshot(channel).to_dict(), ensure_ascii=False)
            prepared.append(vals)
        clean_context = {key: value for key, value in self.env.context.items() if not key.startswith("default_")}
        trusted_model = self.with_context(clean_context)
        runs = super(FacodiPipelineRun, trusted_model).create(prepared)
        for run in runs:
            run._ensure_project_task()
        return runs

    def write(self, vals):
        if set(vals) - {"name"}:
            raise AccessError("Accepted input and generated workflow fields are immutable through RPC.")
        return super().write(vals)

    def _set_execution_values(self, vals):
        """Private capability: never authorize trusted writes with caller context."""
        return self._record_transition(vals)

    def _record_transition(self, vals, *, command=None):
        self.ensure_one()
        vals = dict(vals)
        if "status" in vals and vals["status"] != self.status:
            history = json.loads(self.history_json or "[]")
            history.append({
                "from": self.status, "to": vals["status"],
                "from_revision": self.revision, "revision": self.revision + 1,
                "command": command, "actor_id": self.env.uid,
                "at": fields.Datetime.now().isoformat(),
                "reason": vals.get("error_message") or None,
            })
            vals.update(revision=self.revision + 1, history_json=json.dumps(history))
        return super().write(vals)

    def _lock_command(self):
        self.ensure_one()
        self._check_pipeline_enabled()
        self.check_access("write")
        self.env.cr.execute("SELECT id FROM facodi_pipeline_run WHERE id = %s FOR UPDATE SKIP LOCKED", [self.id])
        if not self.env.cr.fetchone():
            raise RevisionConflict("Run is busy; retry after reading its revision.")
        self.invalidate_recordset()
        if self.legacy_quarantined or self.env.company != self.company_id:
            raise AccessError("Commands require a verified run in its recorded company.")
        self._authorize_channel(self.target_channel_id, self.company_id, self.website_id)

    def _apply_command(self, command, expected_revision):
        self._lock_command()
        if type(expected_revision) is not int or expected_revision < 0:
            raise InvalidTransition("A nonnegative expected_revision is required.")
        # Replay identifies the exact already-applied command, never a fresh retry.
        if any(event.get("command") == command and event.get("from_revision") == expected_revision
               for event in json.loads(self.history_json or "[]")):
            return True
        state = command_transition(self.status, command, self.revision, expected_revision)
        if command == "retry" and self.attempt_count >= 20:
            raise InvalidTransition("Attempt budget exhausted; submit a reviewed new request.")
        self._record_transition({"status": state, "error_message": False}, command=command)
        return True

    def action_retry(self, expected_revision=None):
        return self._apply_command("retry", expected_revision)

    def action_cancel(self, expected_revision=None):
        return self._apply_command("cancel", expected_revision)

    def _action_open_command(self, command):
        self.ensure_one()
        wizard = self.env["facodi.pipeline.command"]._create_for_run(self, command)
        return {
            "type": "ir.actions.act_window",
            "name": dict(wizard._fields["command"].selection).get(command),
            "res_model": "facodi.pipeline.command",
            "res_id": wizard.id,
            "view_mode": "form",
            "target": "new",
        }

    def action_open_retry(self):
        return self._action_open_command("retry")

    def action_open_cancel(self):
        return self._action_open_command("cancel")

    def action_open_input(self):
        return self._action_open_command("input")

    def action_supply_transcript(self, raw_content, idempotency_key, expected_revision=None):
        """Create an explicit input revision; never replace the accepted source."""
        self._lock_command()
        if type(expected_revision) is not int or expected_revision < 0:
            raise InvalidTransition("A nonnegative expected_revision is required.")
        if self.source_type != "youtube":
            raise InvalidTransition("Transcript input is available only for YouTube sources.")
        values = {
            "source_type": "youtube", "source_url": self.source_url,
            "title": self.title, "language": self.language,
            "raw_content": raw_content, "is_manual_transcript": True,
            "target_channel_id": self.target_channel_id.id,
            "idempotency_key": idempotency_key,
            'existing_slide_id': self.existing_slide_id.id or False,
        }
        values = self._normalize_submission(values)
        child = self.input_revision_ids.filtered(lambda run: run.idempotency_key == idempotency_key)
        if child:
            child.check_access("read")
            if child.request_hash != self._submission_fingerprint(values):
                raise SubmissionConflict("Input revision payload conflicts with its key.")
            if not any(event.get('command') == 'input' and event.get('from_revision') == expected_revision
                       for event in json.loads(self.history_json or '[]')):
                raise RevisionConflict('Input command revision does not match the accepted child.')
            return child
        if self.revision != expected_revision:
            raise RevisionConflict("Run changed before new input was supplied.")
        if self.status != "waiting_input":
            raise InvalidTransition("Only a run waiting for input accepts a new transcript revision.")
        with self.env.cr.savepoint():
            receipt = self.submit(values)
            child = self.browse(receipt["id"])
            if not receipt["created"]:
                raise SubmissionConflict("Input revision key already belongs to another request.")
            child._set_execution_values({"input_parent_id": self.id})
            self._record_transition({"status": "cancelled", "error_message": "SUPERSEDED_BY_INPUT"}, command="input")
        return child

    def action_execute_pipeline(self):
        """Execute the pure Python pipeline runner and update record state."""
        self.ensure_one()
        self._check_pipeline_enabled()
        self.check_access("write")
        self.env.cr.execute("SELECT id FROM facodi_pipeline_run WHERE id = %s FOR UPDATE SKIP LOCKED", [self.id])
        if not self.env.cr.fetchone():
            return False
        self.invalidate_recordset()
        if self.legacy_quarantined or self.status != "received":
            raise UserError("Only newly received, non-quarantined runs can execute.")
        if self.env.company != self.company_id:
            raise AccessError("Execution must use the recorded company.")
        self._authorize_channel(self.target_channel_id, self.company_id, self.website_id)
        self._set_execution_values({"status": "running", "error_message": False, "attempt_count": self.attempt_count + 1})

        # New requests retain their authorized catalog. Pre-snapshot accepted
        # receipts bind it once under this same row lock, never on every retry.
        if not self.catalog_snapshot_json:
            self._set_execution_values({'catalog_snapshot_json': json.dumps(self._build_catalog_snapshot(self.target_channel_id).to_dict(), ensure_ascii=False)})
        catalog = CatalogSnapshot.from_dict(json.loads(self.catalog_snapshot_json))
        storage = os.environ.get('FACODI_PIPELINE_STORAGE') or os.path.join(tools.config['data_dir'], 'facodi-pipeline')
        runner = PipelineRunner(enrichment_provider=self._accepted_enrichment_provider(),
                                storage_dir=os.path.join(storage, self.env.cr.dbname, str(self.id)))
        try:
            source = self._prepare_content_source()
            res_run = runner.run_pipeline(
                source=source,
                catalog=catalog,
                idempotency_key=self.idempotency_key or self.run_id,
            )
            vals = {
                "status": "waiting_review",  # Ready for pedagogical / manager review
                "artifacts_json": json.dumps(res_run.artifacts, ensure_ascii=False),
                "metadata_json": json.dumps(res_run.metadata, ensure_ascii=False),
                "concepts_count": res_run.metadata.get("concepts_count", 0),
                "chunks_count": res_run.metadata.get("chunks_count", 0),
            }
            self._set_execution_values(vals)
            self._sync_to_project_task()
            self._on_processing_complete()
            return True
        except Exception as exc:
            from ..core.ingestion.youtube import YouTubeAcquisitionError
            code = exc.code if isinstance(exc, (YouTubeAcquisitionError, PipelineSourceError, DocumentAcquisitionError, EnrichmentError)) else "PIPELINE_FAILED"
            _logger.error("Pipeline execution failed run=%s code=%s", self.run_id, code, exc_info=False)
            self._set_execution_values({"status": failure_status(code), "error_message": code})
            if self.task_id:
                self.task_id.message_post(body="Falha na execução do pipeline.")
            self._on_processing_complete()
            return False

    def _on_processing_complete(self):
        """Editorial addon extension point; pure processing has no Learning dependency."""
        return True

    @api.model
    def _reconcile_processing_receipts(self):
        return True

    def _sync_to_project_task(self):
        """Create or update a mirrored task in project.project / project.task."""
        self.ensure_one()
        if "project.task" not in self.env:
            return

        self._ensure_project_task()
        project = self.project_id

        task_title = f"Conteúdo: {self.title or self.source_url or self.name}"
        meta = json.loads(self.metadata_json or "{}")
        enriched_data = meta.get("enriched_data", {})
        mapping_data = meta.get("mapping_data", {})

        description_parts = [
            f"<p><strong>Origem:</strong> {escape(self.source_type)} ({escape(self.source_url or 'Direto')})</p>",
            f"<p><strong>Sumário Gerado:</strong></p><p>{escape(enriched_data.get('summary', 'N/D'))}</p>",
            f"<p><strong>Conceitos Chave:</strong> {len(enriched_data.get('concepts', []))}</p>",
        ]
        candidates = mapping_data.get("candidates", [])
        if candidates:
            description_parts.append("<p><strong>Sugestões de Alinhamento Curricular:</strong></p><ul>")
            for cand in candidates:
                description_parts.append(f"<li>{escape(cand.get('target_name', ''))} (score: {escape(str(cand.get('score', '')) )})</li>")
            description_parts.append("</ul>")

        html_description = "".join(description_parts)

        self.task_id.write({"name": task_title, "description": html_description})

    def _ensure_project_task(self):
        """Create private review work as soon as a run is accepted."""
        self.ensure_one()
        if self.project_id and self.task_id:
            return

        owner = self.owner_id
        project = self.project_id or self.env["project.project"].sudo().create({
            "name": f"FACODI Pipeline {self.run_id}",
            "company_id": self.company_id.id,
            "user_id": owner.id,
            "privacy_visibility": "followers",
        })
        project.message_subscribe(partner_ids=[owner.partner_id.id])
        task = self.task_id or self.env["project.task"].sudo().create({
            "name": f"Conteúdo: {self.title or self.source_url or self.name}",
            "project_id": project.id,
            "user_ids": [(4, owner.id)],
        })
        task.message_subscribe(partner_ids=[owner.partner_id.id])
        # Ensure subtasks for execution stages
        stages = [("Ingestão & Validação", 1), ("Processamento & Enriquecimento", 2), ("Revisão & Aprovação", 3)]
        for stage_name, seq in stages:
            self.env["project.task"].sudo().create({
                "name": f"Etapa {seq}: {stage_name}",
                "project_id": project.id,
                "parent_id": task.id,
                "user_ids": [(4, owner.id)],
                "sequence": seq,
            })
        self._set_execution_values({"project_id": project.id, "task_id": task.id})

    def action_approve_and_publish(self, publication_evidence=None):
        """Atomically publish reviewed content as a canonical eLearning slide."""
        self.ensure_one()
        self._check_pipeline_enabled()
        if not self.env.user.has_group("facodi_api.group_pipeline_reviewer"):
            raise UserError("Only an eLearning manager can approve publication.")

        self.check_access("write")
        self.env.cr.execute(
            "SELECT id FROM facodi_pipeline_run WHERE id = %s FOR UPDATE",
            [self.id],
        )
        self.invalidate_recordset()
        self._authorize_channel(self.target_channel_id, self.company_id, self.website_id, publication=True)
        if self.published_slide_id:
            if (self.published_slide_id.channel_id != self.target_channel_id
                    or not self.published_slide_id.is_published
                    or not self.published_slide_id.website_published):
                raise UserError("Publication receipt requires reconciliation with the canonical course/content.")
            if (self.existing_slide_id
                    and self._canonical_source_hash(self.published_slide_id) != self.existing_slide_hash):
                raise UserError("Canonical content changed after intake and requires reconciliation.")
            if ("facodi.learning.content.review" in self.env
                    and self.published_slide_id._facodi_requires_review()
                    and not self.published_slide_id._facodi_has_approved_review()):
                raise UserError("Canonical publication requires a current approved content review.")
            return True
        if self.legacy_quarantined or self.status != "waiting_review":
            raise UserError("Only runs waiting for review can be published.")
        if not self.target_channel_id:
            raise UserError("The run has no authorized publication course.")

        native_review_values = None
        if "facodi.learning.content.review" in self.env:
            if not self.env.user.has_group("website_slides.group_website_slides_manager"):
                raise AccessError("An eLearning Manager must decide the native publication review.")
            evidence = publication_evidence
            required = {"author", "rights_mode", "usage_basis", "purpose"}
            if not isinstance(evidence, dict) or set(evidence) != required:
                raise UserError("Provide verified author, rights_mode, usage_basis and purpose for publication.")
            if any(not isinstance(evidence[key], str) or not evidence[key].strip()
                   or len(evidence[key]) > 16384 for key in required):
                raise UserError("Publication evidence must contain nonempty bounded text.")
            if evidence["rights_mode"] not in {"original", "licensed", "external"}:
                raise UserError("Invalid publication rights mode.")
            native_review_values = {
                **evidence, "origin": "manual", "responsible_id": self.env.user.id,
                "source_url": self.source_url or False,
            }

        channel = self.target_channel_id
        self._authorize_channel(channel, self.company_id, self.website_id, publication=True)

        metadata = json.loads(self.metadata_json or "{}")
        enriched = metadata.get("enriched_data") or {}
        summary = enriched.get("summary") or self.raw_content or ""
        if not isinstance(summary, str) or not summary.strip():
            raise UserError("Empty content cannot be published.")
        paragraphs = [part.strip() for part in summary.splitlines() if part.strip()]
        html_content = "".join(f"<p>{escape(paragraph)}</p>" for paragraph in paragraphs)
        slide_values = {
            "name": self.title or self.name,
            "channel_id": channel.id,
            "slide_category": "article",
            "source_type": "local_file",
            "html_content": html_content,
            "is_published": False,
            "website_published": False,
            "is_preview": False,
            "user_id": self.env.user.id,
        }
        if self.source_type == "youtube":
            slide_values.update({
                "slide_category": "video", "source_type": "external",
                "video_url": self.source_url, "html_content": False,
                "description": html_content,
            })
        publication_context = {
            key: value for key, value in self.env.context.items()
            if not key.startswith("default_")
        }
        if self.attachment_id:
            source = self._prepare_content_source()
            if (source.raw_file_name or '').lower().endswith('.pdf'):
                slide_values.update(slide_category='document', html_content=False,
                                    binary_content=base64.b64encode(source.raw_file_bytes))
            else:
                text = (metadata.get('document_data') or {}).get('text_content') or ''
                slide_values['html_content'] = ''.join('<p>%s</p>' % escape(line) for line in text.splitlines() if line.strip())
                slide_values['description'] = html_content
        with self.env.cr.savepoint():
            # This receipt is owned by v2. Suppress the legacy learning video
            # export hook for this creation only; this context grants no access.
            slide = self._create_or_reuse_publication_slide(slide_values, publication_context)
            if native_review_values is not None:
                self._ensure_native_publication_review(slide, native_review_values, publication_context)
            # Native Learning guards revalidate the immutable review hash here.
            slide.write({"is_published": True, "website_published": True})
            if not slide.exists() or slide.channel_id != channel or not slide.is_published:
                raise UserError("Canonical content was not persisted in the target course.")

            self._set_execution_values({
                "status": "published",
                "published_slide_id": slide.id,
                "reviewed_by_id": self.env.user.id,
                "reviewed_at": fields.Datetime.now(),
            })
            if self.task_id:
                self.task_id.message_post(body="Content reviewed and published to the authorized course.")
            return True

    def _create_or_reuse_publication_slide(self, values, context):
        self._prepare_content_source()
        if self.existing_slide_id:
            return self._authorize_existing_slide(self.existing_slide_id.id, self.target_channel_id.id)
        slide = self.env['slide.slide'].with_context(context, facodi_supabase_video_sync=True).create(values)
        if self.attachment_id and not (self.attachment_id.name or '').lower().endswith('.pdf'):
            content, _digest, filename = self._attachment_details(
                self.attachment_id.id, self.target_channel_id.id, accepted_run=self,
            )
            self.env['slide.slide.resource'].with_context(context).create({
                'slide_id': slide.id, 'name': filename, 'file_name': filename,
                'resource_type': 'file', 'data': base64.b64encode(content),
            })
        return slide

    def _ensure_native_publication_review(self, slide, values, context):
        if slide._facodi_has_approved_review():
            return True
        Review = self.env['facodi.learning.content.review'].with_context(context)
        review = Review.search([('slide_id', '=', slide.id), ('state', '=', 'pending')], order='id desc', limit=1)
        if review:
            review.write({key: value for key, value in values.items() if key != 'origin'})
        else:
            review = Review.create({**values, 'slide_id': slide.id})
        review.action_approve()
        return True

    def _check_pipeline_enabled(self):
        enabled = self.env["ir.config_parameter"].sudo().get_param("facodi_api.pipeline_enabled", "false")
        if enabled.lower() not in ("true", "1"):
            raise UserError("Pipeline isolado desativado.")
        if not self.env.user.has_group("facodi_api.group_pipeline_operator"):
            raise UserError("Pipeline operator access is required.")

    @api.model
    def cron_process_received_runs(self):
        """Cron job to process newly received background pipeline requests with exclusive row lock."""
        if not self.env.is_superuser() and not self.env.user.has_group("base.group_system"):
            raise AccessError("Only the scheduler administrator can process the queue.")
        enabled = self.env["ir.config_parameter"].sudo().get_param("facodi_api.pipeline_enabled", "false")
        if enabled.lower() not in ("true", "1"):
            return False
        self._reconcile_processing_receipts()
        self.env.cr.execute(
            """SELECT id FROM facodi_pipeline_run
               WHERE status = 'received'
               ORDER BY id
               LIMIT 1
               FOR UPDATE SKIP LOCKED"""
        )
        row_ids = [row[0] for row in self.env.cr.fetchall()]
        if not row_ids:
            return False
        runs = self.browse(row_ids)
        for run in runs:
            try:
                with self.env.cr.savepoint():
                    run.with_user(run.owner_id).with_context(allowed_company_ids=[run.company_id.id]).with_company(run.company_id).action_execute_pipeline()
            except Exception:
                run.invalidate_recordset()
                run.sudo()._set_execution_values({"status": "failed", "error_message": "PIPELINE_AUTHORIZATION_CHANGED"})
                _logger.error("Queue run failed run=%s code=PIPELINE_AUTHORIZATION_CHANGED", run.run_id, exc_info=False)

        return True
