from .provider.abacate import AbacatePayProvider
from .provider.registry import get_provider, register_provider
from .provider.stripe import StripeProvider
from .provider.supabase import SupabaseProvider

register_provider("supabase", SupabaseProvider)
register_provider("stripe", StripeProvider)
register_provider("abacate", AbacatePayProvider)


class FacodiApiService:
    @staticmethod
    def dispatch(provider_name, function_name, payload=None, config=None):
        provider_cls = get_provider(provider_name)
        if provider_cls is None:
            raise KeyError(f"Unknown provider: {provider_name}")
        provider = provider_cls(config=config or {})
        return provider.dispatch(function_name, payload or {})

    @staticmethod
    def ingest_video(payload=None, config=None):
        return FacodiApiService.dispatch(
            "supabase",
            "video.ingest",
            payload or {},
            config=config,
        )

    @staticmethod
    def analyze_resource(payload=None, config=None):
        return FacodiApiService.dispatch(
            "supabase",
            "resource.analyze",
            payload or {},
            config=config,
        )

    @staticmethod
    def discover_metadata(payload=None, config=None):
        return FacodiApiService.dispatch(
            "supabase",
            "resource.metadata",
            payload or {},
            config=config,
        )
