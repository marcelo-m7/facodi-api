"""API v2 Endpoints for Content Pipeline execution and inspection."""

from __future__ import annotations

import json
import logging
import os
import uuid

from odoo import http
from odoo.http import request
from werkzeug.exceptions import BadRequest, Forbidden, NotFound
from werkzeug.wrappers import Response

_logger = logging.getLogger(__name__)


class FacodiApiV2Controller(http.Controller):
    """v2 Endpoints for the FACODI Content Processing Pipeline."""

    def _check_auth(self):
        """Validate Bearer API Token if configured."""
        token = os.getenv("FACODI_API_BEARER_TOKEN")
        if not token:
            # If not configured, allow local/test access or request session
            return True

        auth_header = request.httprequest.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            raise Forbidden("Missing or invalid Authorization header.")
        provided = auth_header.split(" ", 1)[1].strip()
        if provided != token:
            raise Forbidden("Invalid bearer token.")
        return True

    @http.route("/facodi/api/v2/pipeline/runs", type="http", auth="public", methods=["POST"], csrf=False)
    def create_pipeline_run(self, **kwargs):
        """Submit a content item for ingestion and processing. Responds 202 Accepted asynchronously."""
        try:
            self._check_auth()
            data = None
            try:
                data = request.get_json_data()
            except Exception:
                try:
                    raw_body = request.httprequest.get_data(as_text=True)
                    if raw_body:
                        data = json.loads(raw_body)
                except Exception:
                    data = {}
            if not isinstance(data, dict):
                data = {}

            idempotency_key = (
                request.httprequest.headers.get("Idempotency-Key")
                or data.get("idempotency_key")
            )

            source_type = data.get("source_type", "document")
            url = data.get("url")
            title = data.get("title")
            raw_content = data.get("raw_content")
            language = data.get("language", "pt")
            execute_sync = data.get("sync", False)

            # Check existing if idempotency_key is present
            RunModel = request.env["facodi.pipeline.run"].sudo()
            if idempotency_key:
                existing = RunModel.search([("idempotency_key", "=", idempotency_key)], limit=1)
                if existing:
                    resp = {
                        "run_id": existing.run_id,
                        "idempotency_key": existing.idempotency_key,
                        "status": existing.status,
                        "created_at": existing.create_date.isoformat() if existing.create_date else None,
                    }
                    return Response(json.dumps(resp), status=200, mimetype="application/json")

            run_record = RunModel.create({
                "name": title or f"Run {idempotency_key or str(uuid.uuid4())[:8]}",
                "run_id": str(uuid.uuid4()),
                "idempotency_key": idempotency_key,
                "source_type": source_type,
                "source_url": url,
                "title": title,
                "raw_content": raw_content,
                "language": language,
                "status": "received",
            })

            if execute_sync:
                run_record.action_execute_pipeline()
                status_code = 200
            else:
                status_code = 202

            resp = {
                "run_id": run_record.run_id,
                "idempotency_key": run_record.idempotency_key,
                "status": run_record.status,
                "links": {
                    "self": f"/facodi/api/v2/pipeline/runs/{run_record.run_id}",
                },
            }
            return Response(json.dumps(resp), status=status_code, mimetype="application/json")
        except Forbidden as e:
            return Response(json.dumps({"error": str(e)}), status=403, mimetype="application/json")
        except Exception as e:
            _logger.exception("Error creating pipeline run: %s", e)
            return Response(json.dumps({"error": str(e), "type": type(e).__name__}), status=500, mimetype="application/json")

    @http.route("/facodi/api/v2/pipeline/runs/<string:run_id>", type="http", auth="public", methods=["GET"], csrf=False)
    def get_pipeline_run(self, run_id, **kwargs):
        """Retrieve status, artifacts and curriculum mapping recommendations for a run."""
        self._check_auth()
        RunModel = request.env["facodi.pipeline.run"].sudo()
        run = RunModel.search([("run_id", "=", run_id)], limit=1)
        if not run:
            raise NotFound(f"Run {run_id} not found.")

        meta = json.loads(run.metadata_json or "{}")
        resp = {
            "run_id": run.run_id,
            "idempotency_key": run.idempotency_key,
            "status": run.status,
            "title": run.title,
            "source_type": run.source_type,
            "source_url": run.source_url,
            "error_message": run.error_message,
            "metrics": {
                "concepts_count": run.concepts_count,
                "chunks_count": run.chunks_count,
            },
            "artifacts": {
                "enriched": meta.get("enriched_data"),
                "mapping": meta.get("mapping_data"),
            },
        }
        return Response(json.dumps(resp), status=200, mimetype="application/json")

    @http.route("/facodi/api/v2/pipeline/runs/<string:run_id>/approve", type="http", auth="public", methods=["POST"], csrf=False)
    def approve_pipeline_run(self, run_id, **kwargs):
        """Manager approval to publish content and complete pedagogical workflow."""
        self._check_auth()
        RunModel = request.env["facodi.pipeline.run"].sudo()
        run = RunModel.search([("run_id", "=", run_id)], limit=1)
        if not run:
            raise NotFound(f"Run {run_id} not found.")

        run.action_approve_and_publish()
        return Response(json.dumps({"status": "published", "run_id": run.run_id}), status=200, mimetype="application/json")
