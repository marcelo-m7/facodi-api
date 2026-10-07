"""Models for FACODI Content Pipeline runs, artifacts and Project mirroring."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import uuid
from html import escape

from odoo import api, fields, models
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

_logger = logging.getLogger(__name__)


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
        "idempotency_key", "target_channel_id", "is_manual_transcript",
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
        if vals["source_type"] == "youtube":
            from ..core.ingestion.youtube import YouTubeIngestionAdapter
            if not YouTubeIngestionAdapter.extract_video_id(vals["source_url"]):
                raise ValidationError("Invalid HTTPS YouTube URL.")
            if vals["raw_content"] and not manual:
                raise ValidationError("A supplied transcript must be marked explicitly.")
        if (vals["source_type"] != "youtube" or manual) and not vals["raw_content"].strip():
            raise ValidationError("Nonempty source content is required.")
        channel_id = vals.get("target_channel_id")
        if isinstance(channel_id, bool) or not isinstance(channel_id, int) or channel_id <= 0:
            raise ValidationError("An authorized publication course is required.")
        return vals

    @api.model
    def _submission_fingerprint(self, vals):
        payload = {key: vals[key] for key in sorted(self._submission_fields - {"name"})}
        return hashlib.sha256(json.dumps(payload, sort_keys=True, allow_nan=False).encode()).hexdigest()

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
        return super().write(vals)

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
        self._set_execution_values({"status": "running", "error_message": False})

        # Build ContentSource
        source = ContentSource(
            source_type=SourceType(self.source_type),
            url=self.source_url,
            title=self.title,
            raw_content=self.raw_content,
            language=self.language or "pt",
            metadata={"is_manual_transcript": self.is_manual_transcript},
        )

        # Build CatalogSnapshot from Odoo courses / subjects if available
        targets = []
        try:
            # Check if slide.channel exists (Odoo eLearning)
            if "slide.channel" in self.env:
                channels = self.env["slide.channel"].search([("active", "=", True), ("website_id", "=", self.website_id.id), ("website_id.company_id", "=", self.company_id.id)], limit=50)
                for c in channels:
                    targets.append(
                        TargetEntity(
                            id=f"channel_{c.id}",
                            type="course",
                            name=c.name,
                            tags=[t.name for t in getattr(c, "tag_ids", [])],
                            topics=[],
                        )
                    )
        except Exception:
            _logger.warning("Could not load slide.channel for catalog snapshot", exc_info=False)

        catalog = CatalogSnapshot(
            snapshot_id=f"snap-{self.id}",
            created_at=fields.Datetime.now().isoformat(),
            targets=targets,
        )

        runner = PipelineRunner(storage_dir=os.path.join(os.environ.get("FACODI_PIPELINE_STORAGE", "/tmp/facodi-pipeline-v2"), self.env.cr.dbname, str(self.id)))
        try:
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
            return True
        except Exception as exc:
            from ..core.ingestion.youtube import YouTubeAcquisitionError
            code = exc.code if isinstance(exc, YouTubeAcquisitionError) else "PIPELINE_FAILED"
            _logger.error("Pipeline execution failed run=%s code=%s", self.run_id, code, exc_info=False)
            self._set_execution_values({"status": "failed", "error_message": code})
            if self.task_id:
                self.task_id.message_post(body="Falha na execução do pipeline.")
            return False

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

    def action_approve_and_publish(self):
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
            return True
        if self.legacy_quarantined or self.status != "waiting_review":
            raise UserError("Only runs waiting for review can be published.")
        if not self.target_channel_id:
            raise UserError("The run has no authorized publication course.")

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
            "is_published": True,
            "website_published": True,
            "is_preview": False,
            "user_id": self.env.user.id,
        }
        if self.source_type == "youtube":
            slide_values.update({"slide_category": "video", "source_type": "external", "video_url": self.source_url})
        slide = self.env["slide.slide"].create(slide_values)
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
