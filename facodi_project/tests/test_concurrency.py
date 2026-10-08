import json
import os
from pathlib import Path
import socket
import subprocess
import sys
from tempfile import TemporaryDirectory
from uuid import uuid4

from odoo.tools import config


WORKER = """
import json
import os
import socket
from odoo import api, SUPERUSER_ID
from odoo.orm.registry import Registry
from odoo.service.model import retrying
from odoo.tools import config

settings = json.loads(os.environ['FACODI_RACE_SETTINGS'])
config.parse_config(['--addons-path=' + settings['addons_path'], '--no-http'])
for name in ('db_host', 'db_port', 'db_user', 'db_password'):
    config[name] = settings[name]
registry = Registry(settings['database'])
with registry.cursor() as cursor:
    env = api.Environment(cursor, SUPERUSER_ID, {})
    cursor.execute('SELECT count(*) FROM project_task WHERE project_id=%s '
                   'AND facodi_idempotency_key=%s', [settings['project_id'], settings['key']])
    assert cursor.fetchone()[0] == settings['expected_count']
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as rendezvous:
        rendezvous.settimeout(40)
        rendezvous.connect(settings['socket'])
        rendezvous.sendall(b'ready')
        assert rendezvous.recv(2) == b'go'
    attempts = [0]
    def operation():
        attempts[0] += 1
        result = env['project.task'].facodi_ensure_task(
            settings['project_id'], 'Concurrent execution', settings['key'])
        task = env['project.task'].browse(result['id'])
        task.facodi_bind_receipt('stable-external-job')
        return dict(result, active=task.active)
    result = retrying(operation, env)
    result['attempts'] = attempts[0]
    print(json.dumps(result), flush=True)
"""


def run_concurrency(env):
    if not env.cr.dbname.startswith("facodi_project_"):
        raise RuntimeError("The standalone race requires a disposable Project test database.")
    project = env["project.project"].create({
        "name": "Standalone Project race fixture", "facodi_managed": True,
        "privacy_visibility": "followers",
    })
    key = "race-%s" % uuid4()
    project_count = env["project.project"].with_context(active_test=False).search_count([])
    env.cr.commit()
    settings = {name: config[name] for name in (
        "db_host", "db_port", "db_user", "db_password", "addons_path",
    )}
    if isinstance(settings["addons_path"], (list, tuple)):
        settings["addons_path"] = ",".join(settings["addons_path"])
    settings.update(database=env.cr.dbname, project_id=project.id, key=key)

    def compete(expected_count):
        processes = []
        connections = []
        with TemporaryDirectory(prefix="facodi-project-race-") as directory:
            settings.update(socket=str(Path(directory) / "barrier.sock"), expected_count=expected_count)
            worker_environment = dict(os.environ, FACODI_RACE_SETTINGS=json.dumps(settings))
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
                listener.settimeout(60)
                listener.bind(settings["socket"])
                listener.listen(2)
                try:
                    for worker_number in range(2):
                        processes.append(subprocess.Popen(
                            [sys.executable, "-c", WORKER], env=worker_environment,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                        ))
                    for worker_number in range(2):
                        connection, address = listener.accept()
                        connection.settimeout(40)
                        assert connection.recv(5) == b"ready"
                        connections.append(connection)
                    for connection in connections:
                        connection.sendall(b"go")
                    results = []
                    for process in processes:
                        output, errors = process.communicate(timeout=90)
                        if process.returncode:
                            raise AssertionError("Standalone worker failed: %s" % errors[-3000:])
                        results.append(json.loads(output.strip().splitlines()[-1]))
                    return results
                except TimeoutError as error:
                    for process in processes:
                        if process.poll() is not None:
                            output, errors = process.communicate()
                            raise AssertionError("Worker startup failed: %s" % errors[-3000:]) from error
                    raise
                finally:
                    for connection in connections:
                        connection.close()
                    for process in processes:
                        if process.poll() is None:
                            process.kill()
                        process.wait(timeout=10)

    initial = compete(0)
    assert initial[0]["id"] == initial[1]["id"]
    assert initial[0]["facodi_ref"] == initial[1]["facodi_ref"]
    assert max(result["attempts"] for result in initial) >= 2
    env.cr.rollback()
    env.invalidate_all()
    tasks = env["project.task"].with_context(active_test=False).search([
        ("project_id", "=", project.id), ("facodi_idempotency_key", "=", key),
    ])
    assert len(tasks) == 1 and not tasks.child_ids
    assert tasks.facodi_external_ref == "stable-external-job"
    env.cr.execute("SELECT conname FROM pg_constraint WHERE conrelid='project_task'::regclass "
                   "AND conname IN ('project_task_facodi_ref_unique', 'project_task_facodi_replay_unique')")
    assert len(env.cr.fetchall()) == 2
    tasks.write({"name": "Human archived execution", "active": False})
    env.cr.commit()
    replay = compete(1)
    assert all(result["id"] == initial[0]["id"] and not result["active"] for result in replay)
    env.cr.rollback()
    env.invalidate_all()
    assert tasks.name == "Human archived execution" and not tasks.active
    assert env["project.project"].with_context(active_test=False).search_count([]) == project_count
    assert env["project.task"].with_context(active_test=False).search_count([
        ("project_id", "=", project.id), ("facodi_idempotency_key", "=", key),
    ]) == 1
    print("PASS standalone two-process race, PostgreSQL uniqueness, transactional retry, receipt and archived replay")