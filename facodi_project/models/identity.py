from uuid import UUID, uuid4

from odoo.exceptions import AccessError, ValidationError


TECHNICAL_GROUPS = "facodi_project.group_facodi_operations,project.group_project_manager"


def identifier(value, maximum=200):
    if value is False or value is None or value == "":
        return False
    if not isinstance(value, str) or len(value) > maximum or not value.strip():
        raise ValidationError("FACODI identifiers must be bounded nonempty strings.")
    return value.strip()


def reference(value, namespace):
    value = identifier(value)
    if not value:
        return "%s:%s" % (namespace, uuid4())
    try:
        prefix, encoded = value.split(":", 1)
        parsed = UUID(encoded)
    except (ValueError, AttributeError) as error:
        raise ValidationError("Invalid FACODI reference.") from error
    if prefix != namespace or str(parsed) != encoded:
        raise ValidationError("Invalid FACODI reference namespace or UUID.")
    return value


def check_operator(env):
    if not env.su and not (
        env.user.has_group("facodi_project.group_facodi_operations")
        or env.user.has_group("project.group_project_manager")
    ):
        raise AccessError("FACODI correlation requires an authorized Project operator.")


def reject_identity_defaults(env):
    if any(
        key.startswith("default_facodi_") and value
        for key, value in env.context.items()
    ):
        raise AccessError("FACODI metadata cannot be supplied through context defaults.")