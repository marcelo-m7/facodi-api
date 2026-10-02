from odoo import fields, models


class FacodiApiEvent(models.Model):
    _name = "facodi.api.event"
    _description = "FACODI API Event"
    _order = "id desc"

    name = fields.Char(required=True)
    provider = fields.Selection(
        [("supabase", "Supabase"), ("stripe", "Stripe"), ("manual", "Manual")],
        default="manual",
        required=True,
    )
    event_type = fields.Char(string="Event Type")
    request_id = fields.Char(string="Request ID")
    status = fields.Selection(
        [
            ("queued", "Queued"),
            ("accepted", "Accepted"),
            ("processed", "Processed"),
            ("failed", "Failed"),
        ],
        default="queued",
        required=True,
    )
    payload = fields.Json(default={})
    metadata = fields.Json(default={})
