"""API v2 Endpoints for Content Pipeline execution and inspection."""

from __future__ import annotations

import io
import json
import logging

from odoo import http
from odoo.http import request
from werkzeug.exceptions import BadRequest, Forbidden, NotFound, ServiceUnavailable, RequestEntityTooLarge, Unauthorized, UnsupportedMediaType
from werkzeug.wrappers import Response

from ..core.contracts.http_input import read_request_object, PayloadTooLarge, InvalidPayload

_logger = logging.getLogger(__name__)


class FacodiApiV2Controller(http.Controller):
    """v2 Endpoints for the FACODI Content Processing Pipeline."""

    def _check_auth(self, *, reviewer=False):
        """Require native bearer authentication, feature gate, and explicit role."""
        if not request.httprequest.headers.get("Authorization", "").lower().startswith("bearer "):
            raise Unauthorized("An explicit bearer API key is required.")
        enabled = request.env["ir.config_parameter"].sudo().get_param("facodi_api.pipeline_enabled", "false")
        if enabled.lower() not in ("true", "1"):
            raise ServiceUnavailable("The isolated pipeline is disabled.")
        if not request.env.user.has_group("facodi_api.group_pipeline_operator"):
            raise Forbidden("Pipeline operator access is required.")
        if reviewer and not request.env.user.has_group("facodi_api.group_pipeline_reviewer"):
            raise Forbidden("Pipeline reviewer access is required.")
        return True

    @http.route("/facodi/api/v2/pipeline/runs", type="http", auth="bearer", methods=["POST"], csrf=False)
    def create_pipeline_run(self, **kwargs):
        """Submit a content item for ingestion and processing. Responds 202 Accepted asynchronously."""
        self._check_auth()
        if not request.httprequest.is_json:
            raise UnsupportedMediaType("Content-Type must be application/json")
        try:
            # Odoo 19 exposes get_data, but deliberately hides the WSGI stream.
            # Werkzeug enforces this limit for Content-Length and chunked bodies.
            request.httprequest.max_content_length = 262144
            body = request.httprequest.get_data(cache=False)
            data = read_request_object(io.BytesIO(body), len(body), terminated=True)
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
        from odoo.exceptions import AccessError, ValidationError
        RunModel = request.env["facodi.pipeline.run"]
        allowed = {"source_type", "url", "title", "raw_content", "language", "channel_id",
                   "idempotency_key", "is_manual_transcript", "sync"}
        if set(data) - allowed:
            raise BadRequest("Unsupported submission fields")
        if data.get("sync") not in (None, False):
            raise BadRequest("Synchronous execution is disabled")
        values = {key: data[key] for key in ("source_type", "title", "raw_content", "language", "is_manual_transcript") if key in data}
        values.update({"source_url": data.get("url"), "target_channel_id": data.get("channel_id"), "idempotency_key": idempotency_key})
        try:
            values = RunModel._normalize_submission(values)
            channel = request.env["slide.channel"].browse(values["target_channel_id"])
            RunModel._authorize_channel(channel, request.env.company)
        except ValidationError:
            raise BadRequest("Invalid content submission") from None
        except AccessError:
            raise Forbidden("Course is outside the authorized scope") from None
        fingerprint = RunModel._submission_fingerprint(values)
        scope = [
            ("idempotency_key", "=", idempotency_key),
            ("owner_id", "=", request.env.user.id),
            ("company_id", "=", request.env.company.id),
        ]
        lock_key = f"facodi-pipeline:{request.env.company.id}:{request.env.user.id}:{idempotency_key}"
        lock_cursor = request.env.registry.cursor()
        try:
            lock_cursor.execute("SET LOCAL lock_timeout = '10s'")
            lock_cursor.execute("SELECT pg_advisory_lock(hashtextextended(%s, 0))", [lock_key])
            lock_cursor.commit()
        except Exception:
            lock_cursor.close()
            raise ServiceUnavailable("Submission busy; retry with the same idempotency key.") from None

        def release_idempotency_lock():
            if lock_cursor.closed:
                return
            try:
                lock_cursor.execute("SELECT pg_advisory_unlock(hashtextextended(%s, 0))", [lock_key])
            finally:
                lock_cursor.close()

        request.env.cr.postcommit.add(release_idempotency_lock)
        request.env.cr.postrollback.add(release_idempotency_lock)
        lock_cursor.execute(
            """SELECT run_id, idempotency_key, request_hash, status, create_date
               FROM facodi_pipeline_run
               WHERE idempotency_key = %s AND owner_id = %s AND company_id = %s
               LIMIT 1""",
            [idempotency_key, request.env.user.id, request.env.company.id],
        )
        existing = lock_cursor.fetchone()
        if existing:
            existing_run_id, existing_key, existing_hash, existing_status, created_at = existing
            if existing_hash != fingerprint:
                return Response(json.dumps({"error": "idempotency_conflict"}), status=409, mimetype="application/json")
            resp = {
                "run_id": existing_run_id,
                "idempotency_key": existing_key,
                "status": existing_status,
                "created_at": created_at.isoformat() if created_at else None,
            }
            return Response(json.dumps(resp), status=200, mimetype="application/json")

        run_record = RunModel.create(values)

        resp = {
            "run_id": run_record.run_id,
            "idempotency_key": run_record.idempotency_key,
            "status": run_record.status,
            "links": {
                "self": f"/facodi/api/v2/pipeline/runs/{run_record.run_id}",
            },
        }
        return Response(json.dumps(resp), status=202, mimetype="application/json")

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
        self._check_auth(reviewer=True)
        RunModel = request.env["facodi.pipeline.run"]
        run = RunModel.search([("run_id", "=", run_id)], limit=1)
        if not run:
            raise NotFound("Run not found.")
        run.action_approve_and_publish()
        return Response(
            json.dumps({
                "status": run.status,
                "run_id": run.run_id,
                "slide_id": run.published_slide_id.id,
            }),
            status=200,
            mimetype="application/json",
        )
