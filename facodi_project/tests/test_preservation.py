import json


TASK_FIELDS = [
    "id", "name", "description", "project_id", "stage_id", "state", "active",
    "user_ids", "message_partner_ids", "message_ids", "write_date",
]
PROJECT_FIELDS = [
    "id", "name", "active", "company_id", "privacy_visibility", "user_id",
    "message_partner_ids", "message_ids", "write_date",
]


def capture_history(env):
    if not env.cr.dbname.startswith("facodi_project_"):
        raise RuntimeError("History fixtures require a disposable Project database.")
    project = env["project.project"].create({
        "name": "Historical unmanaged workspace", "privacy_visibility": "followers",
    })
    task = env["project.task"].create({
        "name": "Historical human work", "project_id": project.id,
        "description": "Historical description", "user_ids": [(6, 0, [env.uid])],
    })
    task.message_post(body="Historical chatter remains unchanged")
    env.flush_all()
    snapshot = {
        "tasks": env["project.task"].with_context(active_test=False).search([]).read(TASK_FIELDS),
        "projects": env["project.project"].with_context(active_test=False).search([]).read(PROJECT_FIELDS),
    }
    env["ir.config_parameter"].set_param(
        "facodi_project.test.history", json.dumps(snapshot, default=str),
    )
    env.cr.commit()
    print("PASS pre-install unmanaged history captured")


def verify_history(env):
    if not env.cr.dbname.startswith("facodi_project_"):
        raise RuntimeError("History verification requires a disposable Project database.")
    snapshot = json.loads(env["ir.config_parameter"].get_param("facodi_project.test.history"))
    for key, model, selected_fields in (
        ("tasks", "project.task", TASK_FIELDS), ("projects", "project.project", PROJECT_FIELDS),
    ):
        records = env[model].with_context(active_test=False).browse([
            record["id"] for record in snapshot[key]
        ])
        current = json.loads(json.dumps(records.read(selected_fields), default=str))
        assert current == snapshot[key], "Historical %s changed" % key
        assert not any(records.mapped("facodi_ref")), "Historical references were backfilled"
    print("PASS pre-install history preserved through installation and repeated upgrades")