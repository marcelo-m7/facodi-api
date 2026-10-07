"""Server-scoped backend commands for pipeline runs."""

from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError


class FacodiPipelineCommand(models.TransientModel):
    _name = "facodi.pipeline.command"
    _description = "FACODI Pipeline Command"

    run_id = fields.Many2one(
        "facodi.pipeline.run", required=True, readonly=True, ondelete="cascade"
    )
    command = fields.Selection(
        [("retry", "Retry"), ("cancel", "Cancel"), ("input", "Supply transcript")],
        required=True,
        readonly=True,
    )
    expected_revision = fields.Integer(required=True, readonly=True)
    raw_content = fields.Text(string="Transcript")
    idempotency_key = fields.Char(string="Idempotency Key")

    @api.model_create_multi
    def create(self, vals_list):
        raise AccessError("Pipeline command scope must be captured by a server action.")

    @api.model
    def _create_for_run(self, run, command):
        """Private server capability; underscore methods are not RPC-callable."""
        run.ensure_one()
        run.check_access("write")
        if command not in {"retry", "cancel", "input"}:
            raise ValidationError("Unsupported pipeline command.")
        clean_context = {
            key: value
            for key, value in self.env.context.items()
            if not key.startswith("default_")
        }
        model = self.with_context(clean_context)
        return super(FacodiPipelineCommand, model).create(
            {
                "run_id": run.id,
                "command": command,
                "expected_revision": run.revision,
            }
        )

    def write(self, vals):
        if set(vals) & {"run_id", "command", "expected_revision"}:
            raise AccessError("Pipeline command scope and revision are immutable.")
        return super().write(vals)

    def action_apply(self):
        self.ensure_one()
        run = self.run_id
        if self.command == "retry":
            run.action_retry(self.expected_revision)
        elif self.command == "cancel":
            run.action_cancel(self.expected_revision)
        else:
            run.action_supply_transcript(
                self.raw_content,
                self.idempotency_key,
                self.expected_revision,
            )
        return {"type": "ir.actions.act_window_close"}
