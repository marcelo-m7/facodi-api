from odoo.exceptions import AccessError, ValidationError
from odoo.tests import TransactionCase, new_test_user


class TestProjectAccess(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.operator = new_test_user(
            cls.env, login="p1-operator", groups="facodi_project.group_facodi_operations",
        )
        cls.worker = new_test_user(
            cls.env, login="p1-worker", groups="project.group_project_user",
        )
        cls.portal = new_test_user(cls.env, login="p1-portal", groups="base.group_portal")
        cls.project = cls.env["project.project"].create({
            "name": "Private operator workspace", "facodi_managed": True,
            "privacy_visibility": "followers",
        })
        cls.project.message_subscribe([cls.operator.partner_id.id, cls.worker.partner_id.id])

    def test_operator_can_correlate_without_project_manager_role(self):
        self.assertFalse(self.operator.has_group("project.group_project_manager"))
        tasks = self.env["project.task"].with_user(self.operator)
        result = tasks.facodi_ensure_task(self.project.id, "Operator task", "operator-key")
        self.assertTrue(tasks.browse(result["id"]).facodi_bind_receipt("operator-job"))
        with self.assertRaises(AccessError):
            self.project.with_user(self.operator).write({"facodi_automation_mode": "manual"})

    def test_native_worker_can_create_and_rename_without_technical_field_access(self):
        task = self.env["project.task"].with_user(self.worker).create({
            "name": "Human work", "project_id": self.project.id,
        })
        task.write({"name": "Human renamed work"})
        self.assertEqual(task.name, "Human renamed work")
        self.assertTrue(task.sudo().facodi_ref)
        self.assertNotIn("facodi_ref", task.fields_get(["facodi_ref"]))
        with self.assertRaises(AccessError):
            task.read(["facodi_ref"])
        with self.assertRaises(AccessError):
            task.write({"facodi_external_ref": "forged-job"})

    def test_portal_cannot_use_helpers_or_read_or_write_technical_metadata(self):
        result = self.env["project.task"].facodi_ensure_task(self.project.id, "Task", "portal-key")
        task = self.env["project.task"].browse(result["id"])
        task.message_subscribe([self.portal.partner_id.id])
        portal_task = task.with_user(self.portal)
        self.assertNotIn("facodi_ref", portal_task.fields_get(["facodi_ref"]))
        with self.assertRaises(AccessError):
            portal_task.read(["facodi_idempotency_key"])
        with self.assertRaises(AccessError):
            portal_task.facodi_bind_receipt("forged-job")
        with self.assertRaises(AccessError):
            self.env["project.task"].with_user(self.portal).facodi_ensure_task(
                self.project.id, "Forbidden", "forged-key",
            )

    def test_operator_cannot_access_another_private_workspace(self):
        hidden = self.env["project.project"].create({
            "name": "Other private workspace", "facodi_managed": True,
            "privacy_visibility": "followers",
        })
        with self.assertRaises(AccessError):
            self.env["project.task"].with_user(self.operator).facodi_ensure_task(
                hidden.id, "Forbidden", "other-project-key",
            )

    def test_cross_company_is_denied(self):
        company = self.env["res.company"].create({"name": "P1 other company"})
        project = self.env["project.project"].with_company(company).create({
            "name": "Other company workspace", "facodi_managed": True,
            "company_id": company.id, "privacy_visibility": "employees",
        })
        with self.assertRaises(AccessError):
            self.env["project.task"].with_user(self.operator).facodi_ensure_task(
                project.id, "Forbidden", "other-company-key",
            )

    def test_standard_task_cannot_be_bound_to_an_external_execution(self):
        task = self.env["project.task"].create({"name": "Native task"})
        with self.assertRaises(ValidationError):
            task.write({"facodi_external_ref": "unbound-job"})

    def test_archived_accepted_task_still_blocks_workspace_deletion(self):
        result = self.env["project.task"].facodi_ensure_task(self.project.id, "Task", "archived-key")
        self.env["project.task"].browse(result["id"]).active = False
        with self.assertRaises(ValidationError):
            self.project.unlink()