"""Exercise ORM boundaries in the real Odoo registry (not source-text assertions)."""
import importlib.util
import unittest
from unittest.mock import patch

if importlib.util.find_spec("odoo") is None:
    raise unittest.SkipTest("Requires the real Odoo registry; executed by isolated runtime CI")

from odoo.fields import Command
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestPipelineSecurity(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['ir.config_parameter'].sudo().set_param('facodi_api.pipeline_enabled', 'true')
        cls.operator = cls.env['res.users'].create({
            'name': 'Pipeline security operator', 'login': 'pipeline-security-operator',
            'group_ids': [Command.set([cls.env.ref('facodi_api.group_pipeline_operator').id])],
        })
        cls.channel = cls.env['slide.channel'].create({
            'name': 'Security course', 'user_id': cls.operator.id, 'website_published': True,
            'website_id': cls.env['website'].search([('company_id', '=', cls.env.company.id)], limit=1).id,
        })
        cls.Run = cls.env['facodi.pipeline.run'].with_user(cls.operator)

    def values(self, key='security'):
        return {'source_type': 'manual', 'raw_content': 'A real reviewable paragraph.',
                'idempotency_key': key, 'target_channel_id': self.channel.id}

    def test_creation_rejects_forged_provenance(self):
        for field, value in [('status', 'published'), ('owner_id', self.env.user.id),
                             ('metadata_json', '{}'), ('reviewed_by_id', self.operator.id)]:
            with self.assertRaises(AccessError):
                self.Run.create(dict(self.values(field), **{field: value}))

    def test_context_defaults_cannot_forge_generated_fields(self):
        run = self.Run.with_context(
            default_status='published', default_metadata_json='{"forged": true}',
            default_reviewed_by_id=self.operator.id, default_reviewed_at='2026-10-07 10:00:00',
            default_legacy_quarantined=True, default_published_slide_id=123456,
            default_project_id=123456, default_task_id=123456,
        ).create(self.values())
        self.assertEqual(run.status, 'received')
        self.assertFalse(run.metadata_json)
        self.assertFalse(run.reviewed_by_id)
        self.assertFalse(run.reviewed_at)
        self.assertFalse(run.published_slide_id)
        self.assertFalse(run.legacy_quarantined)
        self.assertNotEqual(run.task_id.id, 123456)
        self.assertNotEqual(run.project_id.id, 123456)

    def test_write_rejects_generated_and_accepted_fields(self):
        run = self.Run.create(self.values())
        for field, value in [('status', 'published'), ('metadata_json', '{}'),
                             ('target_channel_id', self.channel.id), ('raw_content', 'replaced'),
                             ('reviewed_by_id', self.operator.id), ('company_id', self.env.company.id), ('create_uid', self.env.user.id)]:
            with self.assertRaises(AccessError):
                run.with_context(facodi_pipeline_internal=True).write({field: value})
        self.assertEqual(run.status, 'received')
        self.assertFalse(run.reviewed_by_id)
        self.assertFalse(run.published_slide_id)

    def test_non_admin_cannot_lock_the_global_cron_queue(self):
        with self.assertRaises(AccessError):
            self.Run.cron_process_received_runs()

    def test_empty_source_rejected_without_run_or_task(self):
        with self.assertRaises(ValidationError):
            self.Run.create(dict(self.values(), raw_content=' \n '))

    def test_company_website_boundary_even_for_reviewer(self):
        reviewer = self.operator
        reviewer.group_ids = [Command.link(self.env.ref('facodi_api.group_pipeline_reviewer').id)]
        company = self.env['res.company'].create({'name': 'Other pipeline company'})
        website = self.env['website'].create({'name': 'Other pipeline website', 'company_id': company.id})
        channel = self.env['slide.channel'].create({'name': 'Other website course', 'website_id': website.id})
        with self.assertRaises(AccessError):
            self.Run.create(dict(self.values(), target_channel_id=channel.id))

    def test_model_failure_logging_never_exposes_provider_exception(self):
        run = self.Run.create(self.values())
        with patch('odoo.addons.facodi_api.models.pipeline_run.PipelineRunner.run_pipeline',
                   side_effect=RuntimeError('secret-provider-body-abc123')), \
             patch('odoo.addons.facodi_api.models.pipeline_run._logger') as logger:
            self.assertFalse(run.action_execute_pipeline())
            self.assertEqual(run.status, 'failed')
            self.assertEqual(run.error_message, 'PIPELINE_FAILED')
            self.assertNotIn('secret-provider-body-abc123', str(logger.mock_calls))
            logger.exception.assert_not_called()

    def test_execution_cannot_replay_failed_or_reviewed_run(self):
        run = self.Run.create(self.values())
        run._set_execution_values({'status': 'waiting_review'})
        with self.assertRaises(UserError):
            run.action_execute_pipeline()

    def test_archived_course_does_not_starve_the_next_queue_run(self):
        first = self.Run.create(self.values('archived'))
        other_channel = self.env['slide.channel'].create({
            'name': 'Next valid course', 'user_id': self.operator.id,
            'website_id': self.channel.website_id.id, 'website_published': True,
        })
        second = self.Run.create(dict(self.values('next-valid'), target_channel_id=other_channel.id))
        self.channel.active = False
        self.env['facodi.pipeline.run'].cron_process_received_runs()
        first.invalidate_recordset()
        self.assertEqual(first.status, 'failed')
        self.env['facodi.pipeline.run'].cron_process_received_runs()
        second.invalidate_recordset()
        self.assertEqual(second.status, 'waiting_review')
