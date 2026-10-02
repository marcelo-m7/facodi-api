class ProviderAdapter:
    name = "base"

    def __init__(self, config=None):
        self.config = config or {}

    def dispatch(self, function_name, payload):
        raise NotImplementedError("ProviderAdapter.dispatch() must be implemented")
