from psycopg2.errors import UniqueViolation

from odoo import api, fields, models
from odoo.exceptions import AccessError, ConcurrencyError, ValidationError

from .identity import (
    TECHNICAL_GROUPS, check_operator, identifier, reference, reject_identity_defaults,
)


class ProjectTask(models.Model):
    _inherit = "project.task"

    facodi_ref = fields.Char(readonly=True, copy=False, index=True, groups=TECHNICAL_GROUPS)
    facodi_external_ref = fields.Char(readonly=True, copy=False, index=True, groups=TECHNICAL_GROUPS)
    facodi_idempotency_key = fields.Char(readonly=True, copy=False, index=True, groups=TECHNICAL_GROUPS)
    facodi_kind = fields.Char(copy=False, groups=TECHNICAL_GROUPS)
    facodi_origin = fields.Char(copy=False, groups=TECHNICAL_GROUPS)

    _facodi_ref_unique = models.Constraint(
        "UNIQUE(facodi_ref)", "A FACODI task reference must be unique."
    )
    _facodi_replay_unique = models.Constraint(
        "UNIQUE(project_id, facodi_idempotency_key)",
        "An execution key identifies only one task in its workspace.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        reject_identity_defaults(self.env)
        prepared = []
        references = []
        for values in vals_list:
            values = dict(values)
            metadata = {key for key in values if key.startswith("facodi_")}
            if metadata:
                check_operator(self.env)
                for key in metadata:
                    if key != "facodi_ref":
                        values[key] = identifier(values[key])
            supplied_ref = values.pop("facodi_ref", False)
            if values.get("facodi_external_ref"):
                raise ValidationError("Bind an external receipt only after creating its task.")
            if metadata:
                project_id = values.get("project_id") or self.env.context.get("default_project_id")
                project = self.env["project.project"].browse(project_id).exists()
                self._facodi_check_workspace(project)
            references.append(reference(supplied_ref, "task") if supplied_ref else False)
            prepared.append(values)
        tasks = super().create(prepared)
        for task, supplied_ref in zip(tasks, references):
            if task.project_id.sudo().facodi_managed:
                super(ProjectTask, task.sudo()).write({
                    "facodi_ref": supplied_ref or reference(False, "task"),
                })
        return tasks

    def _facodi_check_workspace(self, project):
        check_operator(self.env)
        if len(project) != 1:
            raise ValidationError("An existing permanent workspace is required.")
        project.check_access("read")
        if not project.active or not project.facodi_managed:
            raise ValidationError("An active, explicitly managed workspace is required.")
        if not project.company_id or project.company_id not in self.env.companies:
            raise AccessError("The workspace company is not allowed.")

    @api.model
    def facodi_ensure_task(self, project_id, name, idempotency_key=False,
                          facodi_ref=False, kind="execution", origin="api"):
        reject_identity_defaults(self.env)
        project = self.env["project.project"].browse(project_id).exists()
        self._facodi_check_workspace(project)
        key = identifier(idempotency_key)
        task_ref = reference(facodi_ref, "task") if facodi_ref else False
        kind = identifier(kind, 80)
        origin = identifier(origin, 80)
        if not (key or task_ref) or not kind or not origin:
            raise ValidationError("An execution identity, kind and origin are required.")
        if task_ref:
            identified = self.with_context(active_test=False).search([
                ("facodi_ref", "=", task_ref),
            ], limit=1)
            if identified and identified.project_id != project:
                raise ValidationError("The task reference belongs to a different workspace.")
        domain = [("project_id", "=", project.id)]
        selectors = []
        if key:
            selectors.append(("facodi_idempotency_key", "=", key))
        if task_ref:
            selectors.append(("facodi_ref", "=", task_ref))
        domain += (["|"] if len(selectors) == 2 else []) + selectors
        existing = self.with_context(active_test=False).search(domain, limit=2)
        if existing:
            existing.check_access("read")
            existing.check_access("write")
            if len(existing) != 1 or any([
                key and existing.facodi_idempotency_key != key,
                task_ref and existing.facodi_ref != task_ref,
                existing.facodi_kind != kind,
                existing.facodi_origin != origin,
            ]):
                raise ValidationError("The execution identity has conflicting metadata.")
            task = existing
        else:
            values = {
                "name": identifier(name, 512), "project_id": project.id,
                "facodi_idempotency_key": key, "facodi_kind": kind,
                "facodi_origin": origin,
            }
            if task_ref:
                values["facodi_ref"] = task_ref
            try:
                with self.env.cr.savepoint():
                    task = self.create(values)
            except UniqueViolation as error:
                if error.diag.constraint_name not in {
                    "project_task_facodi_ref_unique", "project_task_facodi_replay_unique",
                }:
                    raise
                raise ConcurrencyError("Retry the FACODI execution transaction.") from error
        return {"id": task.id, "facodi_ref": task.facodi_ref}

    def facodi_bind_receipt(self, external_ref):
        self.ensure_one()
        reject_identity_defaults(self.env)
        check_operator(self.env)
        self.check_access("read")
        self.check_access("write")
        receipt = identifier(external_ref)
        if not receipt or not self.facodi_ref:
            raise ValidationError("An identified task and nonempty external receipt are required.")
        with self.env.cr.savepoint():
            locked = self.try_lock_for_update()
            if not locked:
                raise ConcurrencyError("Retry the FACODI receipt transaction.")
            self.invalidate_recordset(["facodi_external_ref"])
            if self.facodi_external_ref and self.facodi_external_ref != receipt:
                raise ValidationError("The accepted external receipt cannot be replaced.")
            if not self.facodi_external_ref:
                self.write({"facodi_external_ref": receipt})
        return {"id": self.id, "facodi_external_ref": self.facodi_external_ref}

    def write(self, values):
        reject_identity_defaults(self.env)
        self.check_access("write")
        values = dict(values)
        if any(key.startswith("facodi_") for key in values):
            check_operator(self.env)
            for key in values.keys() & {
                "facodi_idempotency_key", "facodi_external_ref", "facodi_kind", "facodi_origin",
            }:
                values[key] = identifier(values[key])
        for task in self.sudo():
            accepted = task.facodi_idempotency_key or task.facodi_external_ref or (task.facodi_kind and task.facodi_origin)
            if values.get("facodi_external_ref") and not task.facodi_ref:
                raise ValidationError("Only an identified task accepts an external receipt.")
            for key in ("facodi_ref", "facodi_idempotency_key", "facodi_kind", "facodi_origin"):
                if key in values and values[key] != task[key]:
                    raise ValidationError("Accepted FACODI task identity is immutable.")
            if "facodi_external_ref" in values and task.facodi_external_ref and values["facodi_external_ref"] != task.facodi_external_ref:
                raise ValidationError("The accepted external receipt cannot be replaced.")
            if accepted and (
                ("project_id" in values and values["project_id"] != task.project_id.id)
                or ("company_id" in values and values["company_id"] != task.company_id.id)
            ):
                raise ValidationError("An accepted execution cannot change workspace or company.")
        return super().write(values)

    def unlink(self):
        self.check_access("unlink")
        if any(
            task.facodi_idempotency_key or task.facodi_external_ref
            or (task.facodi_kind and task.facodi_origin)
            for task in self.sudo()
        ):
            raise ValidationError("Archive accepted FACODI executions instead of deleting them.")
        return super().unlink()