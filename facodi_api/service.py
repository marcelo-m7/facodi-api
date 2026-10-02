from .provider.registry import get_provider, register_provider
from .provider.stripe import StripeProvider
from .provider.supabase import SupabaseProvider

register_provider("supabase", SupabaseProvider)
register_provider("stripe", StripeProvider)


class FacodiApiService:
    @staticmethod
    def dispatch(provider_name, function_name, payload=None, config=None):
        provider_cls = get_provider(provider_name)
        if provider_cls is None:
            raise KeyError(f"Unknown provider: {provider_name}")
        provider = provider_cls(config=config or {})
        return provider.dispatch(function_name, payload or {})
