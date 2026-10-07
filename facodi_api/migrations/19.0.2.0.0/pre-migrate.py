"""Quarantine pre-v2 runs; preserve historical payloads without claiming ownership/publication."""

def migrate(cr, version):
    cr.execute("SELECT to_regclass('public.facodi_pipeline_run')")
    if not cr.fetchone()[0]:
        return
    cr.execute("SELECT column_name FROM information_schema.columns WHERE table_name='facodi_pipeline_run'")
    columns = {row[0] for row in cr.fetchall()}
    if 'legacy_quarantined' not in columns:
        cr.execute("ALTER TABLE facodi_pipeline_run ADD COLUMN legacy_quarantined boolean DEFAULT false")
        cr.execute("ALTER TABLE facodi_pipeline_run ADD COLUMN IF NOT EXISTS legacy_status varchar")
        cr.execute("UPDATE facodi_pipeline_run SET legacy_status=status")
        cr.execute("ALTER TABLE facodi_pipeline_run ADD COLUMN IF NOT EXISTS owner_id integer")
        cr.execute("ALTER TABLE facodi_pipeline_run ADD COLUMN IF NOT EXISTS company_id integer")
        cr.execute("UPDATE facodi_pipeline_run r SET owner_id=coalesce(r.create_uid, 1), company_id=u.company_id FROM res_users u WHERE u.id=coalesce(r.create_uid, 1)")
        # Do not reinterpret old workflow states as canonical publication.
        cr.execute("UPDATE facodi_pipeline_run SET legacy_quarantined=true, status='cancelled', error_message='LEGACY_QUARANTINED: historical state retained in migration audit; resubmit with verified ownership'")
        cr.execute("INSERT INTO ir_config_parameter (key, value, create_uid, write_uid, create_date, write_date) VALUES ('facodi_api.pipeline_enabled', 'false', 1, 1, now(), now()) ON CONFLICT (key) DO UPDATE SET value='false'")
    # Remove the historical global key constraint if the old runtime created it.
    cr.execute("ALTER TABLE facodi_pipeline_run DROP CONSTRAINT IF EXISTS facodi_pipeline_run_idempotency_key_uniq")
