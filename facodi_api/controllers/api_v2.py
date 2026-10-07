"""API v2 Endpoints for Content Pipeline execution and inspection."""

from __future__ import annotations

import json
import logging
import hashlib
import os
import uuid

from odoo import http
from odoo.http import request
from werkzeug.exceptions import BadRequest, Forbidden, NotFound, ServiceUnavailable, NotImplemented, RequestEntityTooLarge, UnsupportedMediaType
from werkzeug.wrappers import Response

from ..core.contracts.http_input import read_json_object, PayloadTooLarge, InvalidPayload

_logger = logging.getLogger(__name__)


class FacodiApiV2Controller(http.Controller):
    """v2 Endpoints for the FACODI Content Processing Pipeline."""

    def _check_auth(self):
        """Validate Bearer API Token if configured."""
        # Native Odoo bearer authentication resolves the API key to a user.
        if not request.httprequest.headers.get("Authorization", "").startswith("Bearer "):
            raise Forbidden("An explicit bearer API key is required.")
        enabled = request.env["ir.config_parameter"].sudo().get_param("facodi_api.pipeline_enabled", "false")
        if enabled.lower() not in ("true", "1"):
            raise ServiceUnavailable("The isolated pipeline is disabled.")
        if not request.env.user.has_group("base.group_system"):
            raise Forbidden("Pipeline access requires an administrator during the isolation phase.")
        return True

    @http.route("/facodi/api/v2/pipeline/runs", type="http", auth="bearer", methods=["POST"], csrf=False)
    def create_pipeline_run(self, **kwargs):
        """Submit a content item for ingestion and processing. Responds 202 Accepted asynchronously."""
        self._check_auth()
        if not request.httprequest.is_json:
            raise UnsupportedMediaType("Content-Type must be application/json")
        if request.httprequest.content_length and request.httprequest.content_length > 262144:
            raise RequestEntityTooLarge("Payload too large")
        try:
            data = read_json_object(request.httprequest.stream)
        except PayloadTooLarge:
            raise RequestEntityTooLarge("Payload too large") from None
        except InvalidPayload:
            raise BadRequest("Invalid JSON body") from None
        if data.get("sync"):
            raise BadRequest("Synchronous execution is disabled")
        idempotency_key = (
            request.httprequest.headers.get("Idempotency-Key")
            or data.get("idempotency_key")
        )

        if not isinstance(idempotency_key, str) or not 1 <= len(idempotency_key) <= 128:
            raise BadRequest("Idempotency-Key is required (1–128 characters)")
        fingerprint = hashlib.sha256(json.dumps(data, sort_keys=True, allow_nan=False).encode()).hexdigest()

        source_type = data.get("source_type", "document")
        url = data.get("url")
        title = data.get("title")
        raw_content = data.get("raw_content")
        language = data.get("language", "pt")
        execute_sync = data.get("sync", False)

        # Check existing if idempotency_key is present
        RunModel = request.env["facodi.pipeline.run"]
        if idempotency_key:
            existing = RunModel.search([("idempotency_key", "=", idempotency_key)], limit=1)
            if existing:
                if existing.request_hash != fingerprint:
                    return Response(json.dumps({"error": "idempotency_conflict"}), status=409, mimetype="application/json")
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
            "request_hash": fingerprint,
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

    @http.route("/facodi/api/v2/pipeline/runs/<string:run_id>", type="http", auth="bearer", methods=["GET"], csrf=False)
    def get_pipeline_run(self, run_id, **kwargs):
        """Retrieve status, artifacts and curriculum mapping recommendations for a run."""
        self._check_auth()
        RunModel = request.env["facodi.pipeline.run"]
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

    @http.route("/facodi/api/v2/pipeline/runs/<string:run_id>/approve", type="http", auth="bearer", methods=["POST"], csrf=False)
    def approve_pipeline_run(self, run_id, **kwargs):
        """Manager approval to publish content and complete pedagogical workflow."""
        self._check_auth()
        raise NotImplemented("Publication adapter and transactional approval are not implemented.")
