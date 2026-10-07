try:
    from . import api
from . import api_v2
except Exception:  # pragma: no cover
    api = None
