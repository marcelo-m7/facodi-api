try:
    from . import controllers
    from . import models
except ModuleNotFoundError as e:
    # Allow importing standalone core / CLI when odoo is not in python environment
    if e.name != "odoo" and not (e.name and e.name.startswith("odoo.")):
        raise
    controllers = None
    models = None
