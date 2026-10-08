from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError

from .identity import TECHNICAL_GROUPS, reference, reject_identity_defaults


class ProjectProject(models.Model):
    _inherit = "project.project"

    facodi_managed = fields.Boolean(default=False, groups="project.group_project_user")
    facodi_ref = fields.Char(
        readonly=True, copy=False, index=True, groups=TECHNICAL_GROUPS
    )
    facodi_kind = fields.Char(groups="project.group_project_user")
    facodi_automation_mode = fields.Selection(
        [("auto", "Automatic"), ("exception", "Exceptions"), ("manual", "Manual")],
        groups="project.group_project_user",
    )

    _facodi_ref_unique = models.Constraint(
        "UNIQUE(facodi_ref)", "A FACODI project reference must be unique."
    )

    @api.model_create_multi
    def create(self, vals_list):
        reject_identity_defaults(self.env)
        prepared = []
        for values in vals_list:
            values = dict(values)
            if values.get("facodi_managed"):
                self._facodi_check_manager()
                values["company_id"] = values.get("company_id") or self.env.company.id
                if values["company_id"] not in self.env.companies.ids:
                    raise AccessError("The workspace company is not allowed.")
                values["facodi_ref"] = reference(values.get("facodi_ref"), "project")
                values.setdefault("facodi_automation_mode", "auto")
            elif values.get("facodi_ref"):
                raise ValidationError("Only an explicitly managed workspace has a FACODI reference.")
            prepared.append(values)
        return super().create(prepared)

    def _facodi_check_manager(self):
        if not self.env.su and not self.env.user.has_group("project.group_project_manager"):
            raise AccessError("Only a Project administrator configures FACODI workspaces.")

    def write(self, values):
        reject_identity_defaults(self.env)
        values = dict(values)
        if any(key.startswith("facodi_") for key in values):
            self._facodi_check_manager()
        for project in self:
            if "facodi_ref" in values and values["facodi_ref"] != project.sudo().facodi_ref:
                raise ValidationError("FACODI workspace references are immutable.")
            if project.sudo().facodi_ref and "company_id" in values and values["company_id"] != project.company_id.id:
                raise ValidationError("An identified workspace cannot change company.")
        if values.get("facodi_managed"):
            self.check_access("write")
            for project in self:
                project_values = dict(values)
                project_values.setdefault("facodi_automation_mode", project.facodi_automation_mode or "auto")
                if not project.facodi_ref:
                    project_values["facodi_ref"] = reference(False, "project")
                    project_values["company_id"] = project.company_id.id or self.env.company.id
                    super(ProjectProject, project).write(project_values)
                else:
                    super(ProjectProject, project).write(project_values)
            return True
        return super().write(values)

    def unlink(self):
        self.check_access("unlink")
        accepted = self.env["project.task"].sudo().with_context(active_test=False).search_count([
            ("project_id", "in", self.ids),
            "|", "|", ("facodi_idempotency_key", "!=", False),
            ("facodi_external_ref", "!=", False),
            "&", ("facodi_kind", "!=", False), ("facodi_origin", "!=", False),
        ], limit=1)
        if accepted:
            raise ValidationError("Archive workspaces with accepted FACODI executions instead of deleting them.")
        return super().unlink()