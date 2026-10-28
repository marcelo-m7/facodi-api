"""Public OAuth consent frontend; Open2 is the sole authorization server."""

import json
import os
import re

from odoo import http
from odoo.http import request


OPEN2_SUPABASE_URL = "https://wvkjainfwsyiyfcmbtid.supabase.co"
AUTHORIZATION_ID = re.compile(r"\A[a-zA-Z0-9_-]{8,200}\Z")


def public_consent_configuration():
    """Publish no credentials except Open2's designated public browser API key."""
    key = os.environ.get("MONYNHA_OAUTH_SUPABASE_PUBLISHABLE_KEY", "").strip()
    raw_clients = os.environ.get("MONYNHA_OAUTH_ALLOWED_CLIENT_IDS", "[]")
    try:
        clients = json.loads(raw_clients)
    except (ValueError, TypeError):
        return None
    if (
        not key.startswith("sb_publishable_")
        or not isinstance(clients, list)
        or not clients
        or any(not isinstance(c, str) or not 1 <= len(c) <= 200 for c in clients)
    ):
        return None
    return {
        "supabase_url": OPEN2_SUPABASE_URL,
        "publishable_key": key,
        "allowed_clients": json.dumps(sorted(set(clients))),
    }


class MonynhaOAuthConsentController(http.Controller):
    @http.route(
        "/oauth/consent",
        type="http",
        auth="public",
        website=True,
        sitemap=False,
        methods=["GET"],
        csrf=False,
    )
    def oauth_consent(self, authorization_id=None, **_kwargs):
        config = public_consent_configuration()
        if config is None:
            return request.render(
                "facodi_mcp_oauth.consent_unavailable",
                {},
                status=503,
                headers=[("Cache-Control", "no-store")],
            )
        if not isinstance(authorization_id, str) or not AUTHORIZATION_ID.fullmatch(authorization_id):
            return request.render(
                "facodi_mcp_oauth.consent_invalid",
                {},
                status=400,
                headers=[("Cache-Control", "no-store")],
            )
        return request.render(
            "facodi_mcp_oauth.consent_page",
            {"authorization_id": authorization_id, **config},
            headers=[("Cache-Control", "no-store")],
        )
