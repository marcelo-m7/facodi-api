import hashlib
import hmac
import json
import os

from odoo import http
from odoo.http import request
from werkzeug.exceptions import BadRequest
from werkzeug.wrappers import Response


class FacodiApiController(http.Controller):
    @http.route("/facodi/api/v1/health", type="http", auth="public", methods=["GET"], csrf=False)
    def health(self, **kwargs):
        payload = {
            "status": "ok",
            "service": "facodi_api",
            "version": "19.0.1.0.0",
        }
        return Response(json.dumps(payload), status=200, mimetype="application/json")

    @http.route(
        "/facodi/api/v1/supabase/webhook",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def supabase_webhook(self, **kwargs):
        data = request.get_json_data(silent=True) or {}
        body = request.httprequest.get_data(cache=False)
        signature = request.httprequest.headers.get("X-Facodi-Signature")
        secret = os.getenv("FACODI_SUPABASE_WEBHOOK_SECRET") or ""
        if secret and signature:
            expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
            if not hmac.compare_digest(signature, expected):
                raise BadRequest("invalid signature")

        request.env["facodi.api.event"].sudo().create(
            {
                "name": "supabase_webhook",
                "provider": "supabase",
                "event_type": "webhook",
                "request_id": data.get("id") or "supabase-webhook",
                "status": "accepted",
                "payload": data,
                "metadata": {"source": "supabase"},
            }
        )
        return Response(json.dumps({"status": "accepted"}), status=202, mimetype="application/json")

    @http.route(
        "/facodi/api/v1/stripe/webhook",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def stripe_webhook(self, **kwargs):
        data = request.get_json_data(silent=True) or {}
        request.env["facodi.api.event"].sudo().create(
            {
                "name": "stripe_webhook",
                "provider": "stripe",
                "event_type": data.get("type") or "webhook",
                "request_id": data.get("id") or "stripe-webhook",
                "status": "accepted",
                "payload": data,
                "metadata": {"source": "stripe"},
            }
        )
        return Response(json.dumps({"status": "accepted"}), status=202, mimetype="application/json")
