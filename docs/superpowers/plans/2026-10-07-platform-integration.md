# FACODI platform integration implementation plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan inline, task by task.

**Goal:** Integrate the API processing mechanism with existing Learning consumers without duplicate execution or lost editorial history.
**Architecture:** One authorized API facade and scheduler. Learning adapts accepted input and completed outputs into its native source/job/result/review/curriculum models. Legacy provider selection stays the default until canary acceptance.
**Tech Stack:** Odoo 19 Community, PostgreSQL 16, Python dataclasses/requests, existing Docker/GitHub runtime gates.
**Spec:** ../specs/2026-10-07-platform-integration-design.md plus the linked full next-agent prompt.

## Global Constraints

- Isolated worktrees, exact submodule gitlinks, no production volume mutations.
- API pure core imports no Odoo/Learning/AI; dependency direction Learning → API.
- Native course/content/progress remain authoritative; no inferred rights or academic credits.
- Default gate false; real network acceptance cannot be substituted by manual input.
- Every delivered behavior requires pure or real ORM/HTTP tests; external transport alone may be controlled in deterministic E2E.

## Review Focus

- Stale/repeated commands must not lose history or create duplicate input revisions.
- A job accepted before a configuration change must retain its provider and scheduler.
- A modified canonical slide/attachment must not reuse a stale processing or publication receipt.
- Client defaults/context must never inject generated fields or bypass native review.
- Private/error/provenance data must not leak through public tracking or provider logs.

### Task 1: lifecycle and common submission

Files: core/contracts/lifecycle.py; models/pipeline_run.py; controllers/api_v2.py; tests/test_lifecycle.py; native test_pipeline_security.py.
Interfaces: command_transition(status,command,revision,expected_revision) → next status; submit(values) → (record,created); action_retry/action_cancel(expected_revision); action_supply_transcript(raw_content,idempotency_key,expected_revision) → new record.
- [ ] Write tests for waiting_input decisions, strict expected revisions, cancel publication refusal, retry state bounds and stale commands. Run and observe missing behavior.
- [ ] Implement policy, locked native actions, immutable child evidence and common idempotent facade; HTTP exposes commands/status revision.
- [ ] Add native tests for RPC/default protection, manual-input replay, history and authorization. Run pure suite, commit, run native runtime gate.

### Task 2: resumable processing and bounded ingestion/providers

Files: core/pipeline/runner.py, core/ingestion/document.py + child transport, core/enrichment providers, models/pipeline_run.py, tests/test_pipeline.py/ingestion/provider tests.
Interfaces: verified checkpoints retain document/chunks/enrichment; accepted attachment digest and server-owned provider configuration are immutable.
- [ ] Write failure/restart tests proving completed ingestion is reused and changed configuration conflicts; file/type/size/deadline and invalid provider/evidence tests.
- [ ] Implement checkpoint reuse, bounded attachment parsing and independent provider boundary; preserve explicit baseline mode and errors.
- [ ] Run full pure suite and native attachment/state tests; document exact external configuration requirements, commit.

### Task 3: Learning bridge and scheduler isolation

Files in learning: models/analysis_job.py, pipeline_adapter.py, slide_slide.py, learning_source.py, res_config_settings.py, manifests/security/views/tests; API extension is owned here.
Interfaces: enqueue one run per new odoo_python job; API completion → validated immutable result/attempt; private existing-slide handoff → native review receipt.
- [ ] Write real ORM tests for enqueue without processing, scheduler mutual exclusion, provider freezing, stale source, baseline output, failed/waiting_input results absence and replay.
- [ ] Implement adapters, persisted origin/provider, source queue selection and safe tracking; retain legacy registry/history and exclude local jobs from legacy cron.
- [ ] Add backend actions/translations and source/submission acceptance cases. Run full runtime gate and commit.

### Task 4: remaining consumers and simplification

Files in learning: snapshot adapter, curriculum/mapping consumers, submission projection, UI; AI optional learning module only where new-flow calls are excluded; docs consumer matrix.
Interfaces: authorized versioned catalog snapshots and reviewed proposals point to existing IDs; API-origin jobs have no AI/legacy execution path.
- [ ] Inventory every consumer and add its regression/E2E test before replacing duplicated processing.
- [ ] Route eligible consumers through API adapters, preserve review/actions, remove duplicated new-flow execution only after parities pass; retain historical models and unrelated AI/payment integrations.
- [ ] Validate native installation/upgrade, Portal visibility and desktop/mobile/language projections; commit.

### Task 5: deploy, review and operational evidence

Files in deploy: docker/migrate.py, canonical Compose only supported environment passthrough, runtime harness and docs/pins.
Interfaces: persisted local provider survives repeated migrate regardless of legacy Supabase pair; exact reviewed gitlinks feed final CI.
- [ ] Add executable migration tests for local selector persistence and malformed legacy configuration; add composed native consumer/scheduler/review tests.
- [ ] Update pins, run repository contracts and both actual runtime gates; get independent final review and fix blockers with regressions.
- [ ] Publish PRs/evidence/issues. Merge only green eligible changes, verify installed code/health and scoped MCP. Keep affected cutover off on external YouTube/credential/production-backup blockers; restore temporary settings and permissions.

No task is marked complete from static assertions or a report alone. Progress and rulings belong in the execution ledger.
