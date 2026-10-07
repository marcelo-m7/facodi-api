from . import test_provider_contract
import importlib.util
if importlib.util.find_spec("odoo") is not None:
    from . import test_pipeline_security
