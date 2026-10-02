import os
import re

try:
    import requests
except ImportError:  # pragma: no cover
    class _MissingRequests:
        post = None

    requests = _MissingRequests()

from .base import ProviderAdapter

_FUNCTION_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_DEFAULT_FUNCTIONS = {
    "resource.analyze": "v3_analyze_learning_resource",
    "resource.metadata": "v3_discover_resource_metadata",
    "video.ingest": "v2_ingest_youtube_video",
    "video_ingest": "v2_ingest_youtube_video",
    "analysis": "v3_analyze_learning_resource",
    "metadata": "v3_discover_resource_metadata",
}


class SupabaseProvider(ProviderAdapter):
    name = "supabase"

    def _resolved_function_name(self, function_name):
        normalized = (function_name or "").strip()
        if not normalized:
            raise RuntimeError("Supabase function name is required")
        normalized = _DEFAULT_FUNCTIONS.get(normalized, normalized)
        if not _FUNCTION_RE.fullmatch(normalized):
            raise RuntimeError("Supabase function name is invalid")
        return normalized

    def _resolved_url(self):
        url = self.config.get("url") or os.getenv("SUPABASE_URL") or ""
        if not url:
            raise RuntimeError("Supabase configuration is missing")
        return url.rstrip("/")

    def _resolved_secret(self):
        secret = self.config.get("secret") or os.getenv("SUPABASE_SECRET_KEY") or ""
        if not secret:
            raise RuntimeError("Supabase configuration is missing")
        return secret

    def dispatch(self, function_name, payload):
        if requests.post is None:
            raise RuntimeError("requests package is not installed")

        secret = self._resolved_secret()
        url = self._resolved_url()
        function_name = self._resolved_function_name(function_name)
        endpoint = f"{url}/functions/v1/{function_name}"

        headers = {
            "apikey": secret,
            "Content-Type": "application/json",
            "user-agent": "FACODI-Odoo/19 SupabaseProvider",
        }

        gemini_key = self.config.get("gemini_key") or os.getenv("GEMINI_API_KEY") or ""
        if gemini_key:
            headers["x-facodi-gemini-key"] = gemini_key

        response = requests.post(
            endpoint,
            json=payload or {},
            headers=headers,
            timeout=30,
        )
        response.raise_for_status()
        try:
            return response.json()
        except ValueError:
            text = getattr(response, "text", "")
            return {"status": "ok", "raw": text}
