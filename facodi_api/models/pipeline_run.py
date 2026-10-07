"""Models for FACODI Content Pipeline runs, artifacts and Project mirroring."""

from __future__ import annotations

import json
import logging
import os
import uuid
from html import escape

from odoo import api, fields, models
from odoo.exceptions import UserError

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

    def action_execute_pipeline(self):
        """Execute the pure Python pipeline runner and update record state."""
        self.ensure_one()
        self._check_pipeline_enabled()
        if self.status in ["running", "published"]:
            return

        self.write({"status": "running", "error_message": False})

        # Build ContentSource
        source = ContentSource(
            source_type=SourceType(self.source_type),
            url=self.source_url,
            title=self.title,
            raw_content=self.raw_content,
            language=self.language or "pt",
        )

        # Build CatalogSnapshot from Odoo courses / subjects if available
        targets = []
        try:
            # Check if slide.channel exists (Odoo eLearning)
            if "slide.channel" in self.env:
                channels = self.env["slide.channel"].search([("active", "=", True)], limit=50)
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
            self.write(vals)
            self._sync_to_project_task()
            return True
        except Exception as e:
            _logger.exception("Pipeline execution failed for run %s", self.id)
            self.write({
                "status": "failed",
                "error_message": "Pipeline execution failed",
            })
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
        self.write({"project_id": project.id, "task_id": task.id})

    def action_approve_and_publish(self):
        """Atomically publish reviewed content as a canonical eLearning slide."""
        self.ensure_one()
        self._check_pipeline_enabled()
        if not self.env.user.has_group("facodi_api.group_pipeline_reviewer"):
            raise UserError("Only an eLearning manager can approve publication.")

        self.env.cr.execute(
            "SELECT id FROM facodi_pipeline_run WHERE id = %s FOR UPDATE",
            [self.id],
        )
        self.invalidate_recordset()
        if self.published_slide_id:
            if self.published_slide_id.channel_id != self.target_channel_id:
                raise UserError("Published content does not match the authorized course.")
            return True
        if self.status != "waiting_review":
            raise UserError("Only runs waiting for review can be published.")
        if not self.target_channel_id:
            raise UserError("The run has no authorized publication course.")

        channel = self.target_channel_id
        channel.check_access("write")
        if not channel.active:
            raise UserError("The target course is archived.")

        metadata = json.loads(self.metadata_json or "{}")
        enriched = metadata.get("enriched_data") or {}
        summary = enriched.get("summary") or self.raw_content or ""
        paragraphs = [part.strip() for part in summary.splitlines() if part.strip()]
        html_content = "".join(f"<p>{escape(paragraph)}</p>" for paragraph in paragraphs)
        slide = self.env["slide.slide"].create({
            "name": self.title or self.name,
            "channel_id": channel.id,
            "slide_category": "article",
            "source_type": "local_file",
            "html_content": html_content,
            "is_published": True,
            "website_published": True,
            "is_preview": False,
            "user_id": self.env.user.id,
        })
        if not slide.exists() or slide.channel_id != channel or not slide.is_published:
            raise UserError("Canonical content was not persisted in the target course.")

        self.write({
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
        """Cron job to process newly received background pipeline requests."""
        enabled = self.env["ir.config_parameter"].sudo().get_param("facodi_api.pipeline_enabled", "false")
        if enabled.lower() not in ("true", "1"):
            return
        runs = self.search([("status", "=", "received")], order="id", limit=10)
        for run in runs:
            try:
                run.with_user(run.owner_id).action_execute_pipeline()
            except Exception:
                _logger.error("Error processing run %s in cron", run.id, exc_info=False)
