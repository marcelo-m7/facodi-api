"""Freeze the current attachment filename for receipts accepted before 19.0.3.1."""
import hashlib

from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    runs = env['facodi.pipeline.run'].search([
        ('attachment_id', '!=', False),
        ('legacy_quarantined', '=', False),
        ('attachment_name_snapshot', '=', False),
    ])
    for run in runs:
        attachment = run.attachment_id
        content = attachment.raw or b''
        filename = attachment.name or ''
        digest = hashlib.sha256(content + b'\0' + filename.encode()).hexdigest()
        run._set_execution_values({
            'attachment_digest': digest,
            'attachment_name_snapshot': filename,
        })
