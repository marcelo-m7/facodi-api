from odoo.tests import TransactionCase
from odoo.exceptions import AccessError, ValidationError


class TestProjectIdentity(TransactionCase):
    def test_standard_project_has_no_identity(self):
        project = self.env["project.project"].create({"name": "Native workspace"})
        self.assertFalse(project.facodi_managed)
        self.assertFalse(project.facodi_ref)

    def test_managed_project_identity_survives_rename(self):
        project = self.env["project.project"].create(
            {"name": "Managed workspace", "facodi_managed": True}
        )
        reference = project.facodi_ref
        self.assertTrue(reference.startswith("project:"))
        project.write({"name": "Human renamed workspace"})
        self.assertEqual(project.facodi_ref, reference)
        self.assertEqual(project.facodi_automation_mode, "auto")

    def _workspace(self):
        return self.env["project.project"].create({
            "name": "Private P1 workspace", "facodi_managed": True,
            "privacy_visibility": "followers",
        })

    def _execution(self, project, key="stable-execution"):
        result = self.env["project.task"].facodi_ensure_task(
            project.id, "Original title", idempotency_key=key,
        )
        return self.env["project.task"].browse(result["id"])

    def test_canonical_replay_preserves_human_work_and_creates_no_project_or_subtasks(self):
        project = self._workspace()
        count = self.env["project.project"].search_count([])
        task = self._execution(project)
        task.write({"name": "Human title", "description": "Human notes"})
        self.assertEqual(self._execution(project), task)
        self.assertEqual(task.name, "Human title")
        self.assertIn("Human notes", task.description)
        self.assertFalse(task.child_ids)
        self.assertEqual(self.env["project.project"].search_count([]), count)

    def test_receipt_bind_replay_and_conflict(self):
        task = self._execution(self._workspace())
        result = task.facodi_bind_receipt("external-job")
        self.assertEqual(task.facodi_bind_receipt("external-job"), result)
        with self.assertRaises(ValidationError):
            task.facodi_bind_receipt("different-job")

    def test_archived_replay_does_not_duplicate_or_unarchive(self):
        project = self._workspace()
        task = self._execution(project)
        task.active = False
        self.assertEqual(self._execution(project), task)
        self.assertFalse(task.active)

    def test_identity_metadata_is_immutable(self):
        project = self._workspace()
        task = self._execution(project)
        for values in ({"facodi_ref": False}, {"facodi_idempotency_key": "replacement"},
                       {"facodi_kind": "replacement"}, {"facodi_origin": "replacement"},
                       {"project_id": False}):
            with self.assertRaises(ValidationError):
                task.with_context(facodi_override=True).write(values)
        with self.assertRaises(ValidationError):
            project.write({"facodi_ref": False})

    def test_context_defaults_cannot_forge_identity(self):
        with self.assertRaises(AccessError):
            self.env["project.task"].with_context(
                default_facodi_idempotency_key="forged",
            ).create({"name": "Hostile default"})

    def test_copy_has_new_identity_without_execution_key_or_receipt(self):
        task = self._execution(self._workspace())
        task.facodi_bind_receipt("external-job")
        copied = task.copy()
        self.assertNotEqual(copied.facodi_ref, task.facodi_ref)
        self.assertTrue(copied.facodi_ref)
        self.assertFalse(copied.facodi_idempotency_key)
        self.assertFalse(copied.facodi_external_ref)

    def test_conflicting_replay_is_denied(self):
        project = self._workspace()
        self._execution(project)
        with self.assertRaises(ValidationError):
            self.env["project.task"].facodi_ensure_task(
                project.id, "Ignored title", "stable-execution", kind="different",
            )

    def test_accepted_execution_and_workspace_cannot_be_deleted(self):
        project = self._workspace()
        task = self._execution(project)
        with self.assertRaises(ValidationError):
            task.unlink()
        with self.assertRaises(ValidationError):
            project.unlink()

    def test_standard_task_has_no_identity(self):
        task = self.env["project.task"].create({"name": "Native personal task"})
        self.assertFalse(task.facodi_ref)

    def test_receipt_bound_human_task_cannot_move_workspace(self):
        project = self._workspace()
        task = self.env["project.task"].create({"name": "Human work", "project_id": project.id})
        task.facodi_bind_receipt("stable-job")
        with self.assertRaises(ValidationError):
            task.write({"project_id": self._workspace().id})

    def test_global_reference_cannot_be_replayed_in_another_workspace(self):
        task = self._execution(self._workspace())
        with self.assertRaises(ValidationError):
            self.env["project.task"].facodi_ensure_task(
                self._workspace().id, "Wrong workspace", facodi_ref=task.facodi_ref,
            )

    def test_failure_rolls_back_task_and_receipt_together(self):
        project = self._workspace()
        with self.assertRaises(ValidationError):
            with self.env.cr.savepoint():
                task = self._execution(project, "rollback-key")
                task.facodi_bind_receipt("first-job")
                task.facodi_bind_receipt("conflicting-job")
        self.assertFalse(self.env["project.task"].search([
            ("project_id", "=", project.id), ("facodi_idempotency_key", "=", "rollback-key"),
        ]))