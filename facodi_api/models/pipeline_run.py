"""Models for FACODI Content Pipeline runs, artifacts and Project mirroring."""

from __future__ import annotations

import json
import logging
import os
import uuid

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
    error_message = fields.Text(string="Error Message")
    artifacts_json = fields.Text(string="Artifacts JSON (Cache)")
    metadata_json = fields.Text(string="Metadata JSON")

    # Metrics
    execution_time = fields.Float(string="Total Execution Time (s)")
    concepts_count = fields.Integer(string="Concepts Count")
    chunks_count = fields.Integer(string="Chunks Count")

    _sql_constraints = [
        ("idempotency_key_uniq", "unique(idempotency_key)", "Idempotency key must be unique per pipeline run!"),
    ]

    def action_execute_pipeline(self):
        """Execute the pure Python pipeline runner and update record state."""
        self.ensure_one()
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
            _logger.warning("Could not load slide.channel for catalog snapshot", exc_info=True)

        catalog = CatalogSnapshot(
            snapshot_id=f"snap-{self.id}",
            created_at=fields.Datetime.now().isoformat(),
            targets=targets,
        )

        runner = PipelineRunner()
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
                "error_message": str(e),
            })
            if self.task_id:
                self.task_id.message_post(body=f"Falha na execução do pipeline: {str(e)}")
            return False

    def _sync_to_project_task(self):
        """Create or update a mirrored task in project.project / project.task."""
        self.ensure_one()
        if "project.task" not in self.env:
            return

        # Find or create default Pipeline project
        project = self.project_id
        if not project:
            project = self.env["project.project"].search([("name", "=", "FACODI Ingestão & Conteúdos")], limit=1)
            if not project:
                project = self.env["project.project"].create({
                    "name": "FACODI Ingestão & Conteúdos",
                })
            self.project_id = project

        task_title = f"Conteúdo: {self.title or self.source_url or self.name}"
        meta = json.loads(self.metadata_json or "{}")
        doc_data = meta.get("document_data", {})
        enriched_data = meta.get("enriched_data", {})
        mapping_data = meta.get("mapping_data", {})

        description_parts = [
            f"<p><strong>Origem:</strong> {self.source_type} ({self.source_url or 'Direto'})</p>",
            f"<p><strong>Sumário Gerado:</strong></p><p>{enriched_data.get('summary', 'N/D')}</p>",
            f"<p><strong>Conceitos Chave:</strong> {len(enriched_data.get('concepts', []))}</p>",
        ]
        candidates = mapping_data.get("candidates", [])
        if candidates:
            description_parts.append("<p><strong>Sugestões de Alinhamento Curricular:</strong></p><ul>")
            for cand in candidates:
                description_parts.append(f"<li>{cand.get('target_name')} (score: {cand.get('score')})</li>")
            description_parts.append("</ul>")

        html_description = "".join(description_parts)

        if not self.task_id:
            task = self.env["project.task"].create({
                "name": task_title,
                "project_id": project.id,
                "description": html_description,
            })
            self.task_id = task
        else:
            self.task_id.write({
                "name": task_title,
                "description": html_description,
            })

    def action_approve_and_publish(self):
        """Manager review action to publish content into target catalog or course."""
        self.ensure_one()
        if self.status != "waiting_review":
            raise UserError("Apenas execuções em estado 'Aguardando Revisão' podem ser aprovadas.")

        self.write({"status": "published"})
        if self.task_id:
            self.task_id.message_post(body="Conteúdo aprovado e publicado pelo gestor.")
        return True

    @api.model
    def cron_process_received_runs(self):
        """Cron job to process newly received background pipeline requests."""
        runs = self.search([("status", "=", "received")], limit=10)
        for run in runs:
            try:
                run.action_execute_pipeline()
            except Exception:
                _logger.error("Error processing run %s in cron", run.id, exc_info=True)
