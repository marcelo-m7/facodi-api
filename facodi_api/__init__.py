"""Load Odoo integration only when Odoo is installed; expose real import errors."""
import importlib.util
if importlib.util.find_spec("odoo") is not None:
    from . import controllers, models
