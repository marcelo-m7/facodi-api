"""Remove the historical broad ACL and keep the new worker disabled on upgrade."""
from odoo import api, SUPERUSER_ID

def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    for xmlid in ('facodi_api.access_facodi_pipeline_run', 'facodi_api.access_facodi_pipeline_run_manager'):
        old_acl = env.ref(xmlid, raise_if_not_found=False)
        if old_acl:
            old_acl.unlink()
    cron = env.ref('facodi_api.ir_cron_facodi_pipeline_process', raise_if_not_found=False)
    if cron:
        cron.active = False
