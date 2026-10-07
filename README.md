# FACODI API

This repository owns FACODI technical processing: ingestion, normalization, enrichment, jobs, checkpoints and proposed matching. Its Python core is independent of Odoo and Learning. The Odoo facade and HTTP transport share authorized commands; Learning owns editorial results, courses, content, review and publication. Supabase and Stripe bridges remain separate integrations.

## Structure

- `facodi_api/` — installable Odoo addon
- `tests/` — provider and contract tests

## Local validation

Run the addon contract tests with:

```bash
python3 -m unittest discover -s facodi_api/tests -v
```

## Isolated Python content pipeline v2

A complete development proposal for a Python pipeline inside this addon, with capability endpoints and standard Odoo Project tasks, is available in [docs/facodi-api](docs/facodi-api/README.md). The addon implements gated asynchronous intake, review and canonical publication. The existing provider bridge and legacy platform consumers remain active. See [current review and operational evidence](docs/facodi-api/review-integration-2026-10-07.md) before enabling v2.

- Engineering epic: https://github.com/marcelo-m7/facodi-api/issues/1
- Deployment integration epic: https://github.com/marcelo-m7/facodi-deploy/issues/255
- [Implementation plan](docs/superpowers/plans/2026-10-06-facodi-api.md)

Pure pipeline and provider tests run with `python -m pytest tests facodi_api/tests -q`; the ORM module is skipped only outside Odoo and must execute in the native gate. ORM tests run in the real Odoo registry through the isolated deploy CI. Provider contract tests also support:

```bash
python3 -m unittest discover -s facodi_api/tests -v
```

## Executable HTTP contract

| Route | Method | Authentication and behavior |
| --- | --- | --- |
| `/facodi/api/v1/health` | GET | Public; loaded addon version, not deployment SHA or readiness of external services |
| `/facodi/api/v1/supabase/webhook` | POST | `X-Facodi-Signature`, HMAC-SHA256 over exact body; server `FACODI_SUPABASE_WEBHOOK_SECRET` required |
| `/facodi/api/v1/stripe/webhook` | POST | Standard `Stripe-Signature`; official Stripe SDK and 300-second tolerance; server `FACODI_STRIPE_WEBHOOK_SECRET` required |
| `/facodi/api/v2/pipeline/runs` | POST | Native Odoo bearer API key, Pipeline Operator and enabled gate; 202 new receipt, 200 identical replay, 409 divergent input |
| `/facodi/api/v2/pipeline/runs/<run_id>` | GET | Same operator/gate and record scope; status, revision, attempt count and persisted enrichment/mapping |
| `/facodi/api/v2/pipeline/runs/<run_id>/retry` | POST | JSON `expected_revision`; retries failed runs without replacing accepted input |
| `/facodi/api/v2/pipeline/runs/<run_id>/cancel` | POST | JSON `expected_revision`; versioned cancellation at transaction boundaries, not interruption of active external I/O |
| `/facodi/api/v2/pipeline/runs/<run_id>/input` | POST | JSON `expected_revision`, `raw_content`, `idempotency_key`; creates explicit YouTube transcript child revision |
| `/facodi/api/v2/pipeline/runs/<run_id>/approve` | POST | Reviewer; Learning additionally requires native editorial evidence/review before publication |

Webhooks fail closed: absent server secret returns 503, absent/invalid signature
returns 401, invalid JSON returns 400 and bodies above 262144 bytes return 413.
Configure the dedicated webhook signing secrets before adopting signed callers;
Supabase API keys are not webhook signing secrets. Signature validation does not
yet provide v1 event replay deduplication. Never log signing secrets or signatures.

V2 submission fields are `source_type`, `url`, `title`, `raw_content`, `language`,
`channel_id`, `attachment_id`, `existing_slide_id`, `is_manual_transcript` and
`idempotency_key` (or `Idempotency-Key` header). Synchronous execution and unknown
fields are rejected. Supported sources are manual text, Markdown, authorized
documents and YouTube; arbitrary web crawling, playlists and books are not
implemented adapters. There is no deployed capabilities/OpenAPI route yet.

Accepted source, actor, provider and catalog are frozen. Core stages are ingest,
normalize, enrich and map. Matching source/catalog/provider fingerprints permit
valid completed checkpoints to survive later failures; changed inputs conflict.
Manual transcripts are explicit evidence, not proof of external acquisition.
Core success becomes Odoo `waiting_review`, never automatic publication.

## Continuing development

- Do not duplicate analysis in Learning/controllers/crons or call the instance over HTTP from its own models.
- Preserve canonical `slide.channel`/`slide.slide`, native progress and human review.
- Technical jobs are API entities; Project tasks should track actionable human work. The current per-run technical Project mirror is legacy behavior to migrate additively, not a pattern to extend.
- Preserve accepted inputs and reuse verified checkpoints; contract changes need pure, native and HTTP regressions.
- Migrate each legacy consumer with parity evidence before removing its engine or historical records.
- Keep provider selection opt-in until external acquisition, operational backup/identity and a bounded canary are proven.
