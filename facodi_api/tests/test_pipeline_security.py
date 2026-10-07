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

    def test_common_submission_is_async_and_idempotent(self):
        first = self.Run.submit(self.values('facade'))
        again = self.Run.submit(self.values('facade'))
        self.assertTrue(first['created'])
        self.assertFalse(again['created'])
        self.assertEqual(first['id'], again['id'])
        run = self.Run.browse(first['id'])
        self.assertEqual(run.status, 'received')
        self.assertFalse(run.metadata_json)
        self.assertEqual(run.attempt_count, 0)
        from odoo.addons.facodi_api.models.pipeline_run import SubmissionConflict
        with self.assertRaises(SubmissionConflict):
            self.Run.submit(dict(self.values('facade'), raw_content='Different source.'))

    def test_cancel_command_replays_without_new_state_or_history(self):
        run = self.Run.create(self.values('cancel-replay'))
        run.action_cancel(expected_revision=0)
        self.assertEqual(run.status, 'cancelled')
        self.assertEqual(run.revision, 1)
        history = run.history_json
        run.action_cancel(expected_revision=0)
        self.assertEqual(run.history_json, history)
        from odoo.addons.facodi_api.core.contracts.lifecycle import RevisionConflict
        with self.assertRaises(RevisionConflict):
            run.action_retry(expected_revision=0)

    def test_blocked_video_input_creates_separate_immutable_revision(self):
        from odoo.addons.facodi_api.core.ingestion.youtube_transport import YouTubeAcquisitionError
        run = self.Run.create(dict(self.values('blocked-input'), source_type='youtube',
                                  source_url='https://www.youtube.com/watch?v=4GVbqYFmGBw', raw_content=''))
        with patch('odoo.addons.facodi_api.core.ingestion.youtube.acquire_transcript',
                   side_effect=YouTubeAcquisitionError('YOUTUBE_IP_BLOCKED')):
            self.assertFalse(run.action_execute_pipeline())
        self.assertEqual(run.status, 'waiting_input')
        self.assertEqual(run.error_message, 'YOUTUBE_IP_BLOCKED')
        revision = run.revision
        child = run.action_supply_transcript('Original explicit manual test evidence.', 'input-child', revision)
        self.assertEqual(child.input_parent_id, run)
        self.assertTrue(child.is_manual_transcript)
        self.assertEqual(child.status, 'received')
        self.assertEqual(run.status, 'cancelled')
        self.assertFalse(run.raw_content)
        self.assertFalse(run.is_manual_transcript)
        again = run.action_supply_transcript('Original explicit manual test evidence.', 'input-child', revision)
        self.assertEqual(child, again)
        from odoo.addons.facodi_api.models.pipeline_run import SubmissionConflict
        with self.assertRaises(SubmissionConflict):
            run.action_supply_transcript('Altered evidence.', 'input-child', revision)

    def test_generated_command_history_is_not_rpc_writable(self):
        run = self.Run.with_context(default_revision=99, default_history_json='[{"forged":true}]',
                                    default_input_parent_id=123456).create(self.values('history-guards'))
        self.assertEqual(run.revision, 0)
        self.assertFalse(run.history_json)
        self.assertFalse(run.input_parent_id)
        for values in ({'revision': 999}, {'history_json': '[]'}, {'input_parent_id': run.id}):
            with self.assertRaises(AccessError):
                run.write(values)

    def test_retry_keeps_accepted_input_and_records_attempt(self):
        run = self.Run.create(self.values('retry-audit'))
        run._set_execution_values({'status': 'failed', 'error_message': 'PIPELINE_FAILED'})
        revision = run.revision
        accepted = (run.request_hash, run.raw_content, run.owner_id.id, run.company_id.id)
        run.action_retry(revision)
        run.action_retry(revision)
        self.assertEqual(run.status, 'received')
        self.assertEqual((run.request_hash, run.raw_content, run.owner_id.id, run.company_id.id), accepted)
        self.assertTrue(run.action_execute_pipeline())
        self.assertEqual(run.attempt_count, 1)
        self.assertEqual(run.status, 'waiting_review')

    def test_authorized_attachment_is_snapshotted_and_converted(self):
        import base64
        attachment = self.env['ir.attachment'].with_user(self.operator).create({
            'name': 'original.txt', 'datas': base64.b64encode(b'Original attachment learning evidence.'),
        })
        run = self.Run.create(dict(self.values('attachment'), source_type='document', raw_content='', attachment_id=attachment.id))
        self.assertTrue(run.attachment_digest)
        self.assertEqual(run.attachment_name_snapshot, 'original.txt')
        self.assertTrue(run.action_execute_pipeline())
        self.assertEqual(run.status, 'waiting_review')
        self.assertEqual(run.chunks_count, 1)

    def test_attachment_change_is_detected_before_processing(self):
        import base64
        attachment = self.env['ir.attachment'].with_user(self.operator).create({
            'name': 'original.txt', 'datas': base64.b64encode(b'Original evidence.'),
        })
        run = self.Run.create(dict(self.values('changed-attachment'), source_type='document', raw_content='', attachment_id=attachment.id))
        attachment.write({'datas': base64.b64encode(b'Replaced evidence.')})
        self.assertFalse(run.action_execute_pipeline())
        self.assertEqual(run.status, 'waiting_input')
        self.assertEqual(run.error_message, 'ATTACHMENT_CHANGED')
        self.assertFalse(run.metadata_json)

    def test_attachment_rename_is_detected_before_processing(self):
        import base64
        attachment = self.env['ir.attachment'].with_user(self.operator).create({
            'name': 'original.txt', 'datas': base64.b64encode(b'Original evidence.'),
        })
        run = self.Run.create(dict(self.values('renamed-attachment'), source_type='document', raw_content='', attachment_id=attachment.id))
        attachment.name = 'renamed.pdf'
        self.assertFalse(run.action_execute_pipeline())
        self.assertEqual(run.status, 'waiting_input')
        self.assertEqual(run.error_message, 'ATTACHMENT_CHANGED')

    def test_foreign_unlinked_attachment_cannot_be_submitted(self):
        import base64
        attachment = self.env['ir.attachment'].create({'name': 'private.txt', 'datas': base64.b64encode(b'Private.')})
        with self.assertRaises(AccessError):
            self.Run.create(dict(self.values('foreign-attachment'), source_type='document', raw_content='', attachment_id=attachment.id))

    def test_existing_source_change_invalidates_processing_snapshot(self):
        self.operator.write({'group_ids': [Command.link(self.env.ref('website_slides.group_website_slides_officer').id)]})
        slide = self.env['slide.slide'].with_user(self.operator).create({
            'name': 'Existing original', 'channel_id': self.channel.id,
            'slide_category': 'article', 'html_content': '<p>Original evidence.</p>',
        })
        run = self.Run.create(dict(self.values('existing-snapshot'), existing_slide_id=slide.id,
                                   raw_content='Original evidence.'))
        slide.write({'html_content': '<p>Changed evidence.</p>'})
        self.assertFalse(run.action_execute_pipeline())
        self.assertEqual(run.error_message, 'CANONICAL_INPUT_CHANGED')
        self.assertEqual(run.status, 'waiting_input')

    def test_existing_slide_rejects_unrelated_caller_content(self):
        self.operator.write({'group_ids': [Command.link(self.env.ref('website_slides.group_website_slides_officer').id)]})
        slide = self.env['slide.slide'].with_user(self.operator).create({
            'name': 'Existing original', 'channel_id': self.channel.id,
            'slide_category': 'article', 'html_content': '<p>Canonical evidence.</p>',
        })
        with self.assertRaises(ValidationError):
            self.Run.create(dict(self.values('existing-mismatch'), existing_slide_id=slide.id,
                                 raw_content='Unrelated caller content.'))

    def test_publication_replay_rejects_changed_canonical_slide(self):
        self.operator.write({'group_ids': [Command.link(self.env.ref('facodi_api.group_pipeline_reviewer').id)]})
        slide = self.env['slide.slide'].with_user(self.operator).create({
            'name': 'Replay original', 'channel_id': self.channel.id,
            'slide_category': 'article', 'html_content': '<p>Original replay evidence.</p>',
        })
        run = self.Run.create(dict(
            self.values('published-replay-change'),
            existing_slide_id=slide.id,
            raw_content='Original replay evidence.',
        ))
        self.assertTrue(run.action_execute_pipeline())
        self.assertTrue(run.action_approve_and_publish())
        slide.write({'html_content': '<p>Changed after publication.</p>'})
        with self.assertRaises(UserError):
            run.action_approve_and_publish()

    def test_run_scoped_attachment_can_be_published_by_reviewer(self):
        import base64
        reviewer = self.env['res.users'].create({
            'name': 'Different pipeline reviewer', 'login': 'different-pipeline-reviewer',
            'group_ids': [Command.set([
                self.env.ref('facodi_api.group_pipeline_reviewer').id,
                self.env.ref('website_slides.group_website_slides_manager').id,
            ])],
        })
        attachment = self.env['ir.attachment'].with_user(self.operator).create({
            'name': 'operator-source.txt', 'datas': base64.b64encode(b'Accepted operator evidence.'),
        })
        run = self.Run.create(dict(self.values('cross-reviewer-attachment'), source_type='document',
                                   raw_content='', attachment_id=attachment.id))
        self.assertTrue(run.action_execute_pipeline())
        self.assertTrue(run.with_user(reviewer).action_approve_and_publish())
        self.assertTrue(run.published_slide_id.is_published)

    def test_document_failure_preserves_safe_acquisition_code(self):
        import base64
        attachment = self.env['ir.attachment'].with_user(self.operator).create({
            'name': 'invalid.pdf', 'datas': base64.b64encode(b'This is not a PDF.'),
        })
        run = self.Run.create(dict(self.values('invalid-pdf'), source_type='document', raw_content='', attachment_id=attachment.id))
        self.assertFalse(run.action_execute_pipeline())
        self.assertEqual(run.error_message, 'DOCUMENT_INVALID_FORMAT')
        self.assertFalse(run.metadata_json)

    def test_enrichment_configuration_is_server_owned_and_frozen(self):
        import json
        params = self.env['ir.config_parameter'].sudo()
        params.set_param('facodi_api.enrichment_provider', 'baseline')
        run = self.Run.with_context(default_provider_config_json='{"provider":"gemini"}').create(self.values('provider-freeze'))
        self.assertEqual(json.loads(run.provider_config_json)['provider'], 'baseline')
        params.set_param('facodi_api.enrichment_provider', 'unsupported-provider')
        self.assertTrue(run.action_execute_pipeline())
        self.assertEqual(json.loads(run.metadata_json)['enriched_data']['provider_name'], 'baseline-deterministic')
        with self.assertRaises(AccessError):
            run.write({'provider_config_json': '{}'})

    def test_catalog_snapshot_has_no_silent_fifty_course_limit(self):
        import json
        courses = self.env['slide.channel'].create([{
            'name': 'Authorized snapshot course %s' % index,
            'user_id': self.operator.id, 'website_id': self.channel.website_id.id,
            'website_published': True,
        } for index in range(51)])
        run = self.Run.create(self.values('catalog-full'))
        snapshot = json.loads(run.catalog_snapshot_json)
        self.assertTrue({'channel_%s' % course.id for course in courses}.issubset({target['id'] for target in snapshot['targets']}))
        accepted = run.catalog_snapshot_json
        courses[0].name = 'Renamed after acceptance'
        self.assertTrue(run.action_execute_pipeline())
        self.assertEqual(run.catalog_snapshot_json, accepted)

    def test_backend_command_captures_revision_and_rejects_stale_confirmation(self):
        from odoo.addons.facodi_api.core.contracts.lifecycle import RevisionConflict
        run = self.Run.create(self.values('backend-cancel'))
        action = run.action_open_cancel()
        wizard = self.env[action['res_model']].with_user(self.operator).browse(action['res_id'])
        self.assertEqual(wizard.expected_revision, run.revision)
        run._set_execution_values({'status': 'waiting_review'})
        with self.assertRaises(RevisionConflict):
            wizard.action_apply()
        self.assertEqual(run.status, 'waiting_review')

    def test_backend_command_cannot_forge_scope_or_revision(self):
        run = self.Run.create(self.values('backend-guard'))
        self.assertIn('facodi.pipeline.command', self.env)
        CommandWizard = self.env['facodi.pipeline.command'].with_user(self.operator)
        with self.assertRaises(AccessError):
            CommandWizard.create({'run_id': run.id, 'command': 'cancel', 'expected_revision': 999})
        with self.assertRaises(AccessError):
            CommandWizard.with_context(
                default_run_id=run.id,
                default_command='retry',
                default_expected_revision=999,
            ).create({})
        action = run.with_context(
            default_run_id=123456,
            default_command='retry',
            default_expected_revision=999,
        ).action_open_cancel()
        wizard = CommandWizard.browse(action['res_id'])
        self.assertEqual(wizard.run_id, run)
        self.assertEqual(wizard.command, 'cancel')
        self.assertEqual(wizard.expected_revision, 0)
        wizard.action_apply()
        wizard.action_apply()
        self.assertEqual(run.status, 'cancelled')
        self.assertEqual(run.revision, 1)
