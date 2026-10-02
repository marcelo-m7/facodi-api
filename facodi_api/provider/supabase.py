import os

try:
    import requests
except ImportError:  # pragma: no cover
    class _MissingRequests:
        post = None

    requests = _MissingRequests()

from .base import ProviderAdapter


class SupabaseProvider(ProviderAdapter):
    name = "supabase"

    def dispatch(self, function_name, payload):
        if requests.post is None:
            raise RuntimeError("requests package is not installed")

        url = self.config.get("url") or os.getenv("SUPABASE_URL") or ""
        secret = self.config.get("secret") or os.getenv("SUPABASE_SECRET_KEY") or ""
        if not url or not secret:
            raise RuntimeError("Supabase configuration is missing")

        endpoint = f"{url.rstrip('/')}/functions/v1/{function_name}"
        response = requests.post(
            endpoint,
            json=payload,
            headers={
                "Authorization": f"Bearer {secret}",
                "Content-Type": "application/json",
            },
            timeout=30,
        )
        response.raise_for_status()
        return response.json()
