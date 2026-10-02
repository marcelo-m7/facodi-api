_PROVIDERS = {}


def register_provider(name, provider_cls):
    _PROVIDERS[name] = provider_cls
    return provider_cls


def get_provider(name):
    return _PROVIDERS.get(name)


def list_providers():
    return sorted(_PROVIDERS)
