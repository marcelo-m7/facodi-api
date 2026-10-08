# FACODI Project

Independent Odoo19 addon, version19.0.1.0.0, depending only on standard Project.
INC-P1 establishes opt-in permanent workspaces, globally stable namespaced refs,
canonical task replay within a workspace and immutable external job correlation.
No pipeline cutover, historical adoption/backfill, compulsory technical subtasks,
processing cron, publication policy or Learning/AI/Supabase dependency is added.

Project administrators configure managed workspaces; authorized Operations users
use `project.task.facodi_ensure_task` and `facodi_bind_receipt` within native
record/company permissions. `auto` is inert policy metadata in this increment.
Native forms/search/kanban remain standard, with technical fields unavailable
to Portal users. Copies get new identity; accepted executions are archived.

## Required Acceptance

The owner workflow `.github/workflows/standalone-tests.yml` runs:

1. Native Project initialization and pre-install history capture.
2. Clean `facodi_project` installation and its native ORM/HTTP Portal suite.
3. Mandatory `tests.test_concurrency.run_concurrency(env)` in `odoo shell`,
   outside module loading: separate processes and PostgreSQL snapshots, unique
   constraints, full transaction retry, one receipt and archived replay.
4. Two consecutive upgrades and exact history/ref preservation verification.

The standalone fixture refuses non-`facodi_project_*` databases. It never mocks
the helper/ORM/SQL or changes vendor locks. Technical subprocess credentials
remain in child environment only and are never printed.

The deployment repository additionally runs full API/Learning/runtime gates
against the exact clean owner commit. Production install and image identity are
separate from source acceptance. No network exactly-once guarantee is claimed.