from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestProjectPortal(HttpCase):
    def _task(self):
        project = self.env["project.project"].create({
            "name": "Private Portal workspace", "facodi_managed": True,
            "privacy_visibility": "followers",
        })
        result = self.env["project.task"].facodi_ensure_task(
            project.id, "Private portal execution", "portal-secret-key",
        )
        task = self.env["project.task"].browse(result["id"])
        task.facodi_bind_receipt("portal-secret-receipt")
        return task

    def test_native_share_token_does_not_expose_technical_fields(self):
        task = self._task()
        token = task._portal_ensure_token()
        response = self.url_open("/my/tasks/%s?access_token=%s" % (task.id, token))
        self.assertEqual(response.status_code, 200)
        self.assertIn(task.name, response.text)
        for secret in (task.facodi_ref, task.facodi_idempotency_key, task.facodi_external_ref):
            self.assertNotIn(secret, response.text)

    def test_anonymous_user_without_token_cannot_read_private_task(self):
        task = self._task()
        response = self.url_open("/my/tasks/%s" % task.id)
        self.assertNotIn(task.name, response.text)
        self.assertNotIn(task.facodi_ref, response.text)