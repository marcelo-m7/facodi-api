# FACODI API

This repository owns FACODI technical processing: ingestion, normalization, enrichment, jobs, checkpoints and proposed matching. Its Python core is independent of Odoo and Learning. The Odoo facade and HTTP transport share authorized commands; Learning owns editorial results, courses, content, review and publication. Supabase and Stripe bridges remain separate integrations.

## INC-P2 Bounded Text Candidate

Version `19.0.3.4.0` introduces the first disabled-by-default cutover slice,
not a complete Supabase executor. The independent `facodi_project` addon remains
Project-only; API now consumes it. Future technical execution belongs to Supabase,
while the existing Python engine remains the frozen compatibility route.

Only administrators may configure `facodi_api.canonical_intake_enabled` and
`facodi_api.canonical_workspace.<website_id>` using an explicitly managed Project
ID in the Website company. Intake freezes `execution_plane` and creates/reuses
one canonical task atomically. Replay after route changes preserves the accepted
executor and human work; the legacy worker cannot process canonical jobs.
Old runs are not adopted or backfilled. Missing or inaccessible workspaces fail
closed, without per-run fallback Projects or mandatory technical subtasks.

The candidate now freezes a minimal dispatch payload and polls authenticated,
identity-scoped monotonic receipts. `facodi_api.canonical_dispatch_enabled`
defaults to false. Its scheduler uses a separate transaction: uncommitted intake
never reaches the network. Lost acceptance responses replay the native task key
and bind the same external job UUID. Unchanged polls cannot starve later jobs;
terminal projection has only one local revision. Human task fields are untouched.
Terminal failures create one native review activity for the course responsible
user (or accepted owner), without technical payload; identical replay creates
neither another activity nor another editorial revision.

The first cohort supports explicit manual/Markdown text, explicit YouTube
transcripts and automatic YouTube acquisition up to 12000 UTF-8 bytes. Automatic
requests accept empty text and freeze the server-owned acquisition provider and
version. Unsupported sources fail before intake; no content is silently truncated.
The frozen baseline/Gemini provider
is preserved, never replaced by the semantically different v3 metadata fallback.
The server-only target is the approved FACODI Supabase project and modern secret.
Legacy providers, binary documents and old accepted runs retain their old route
when canonical intake is disabled.

Automatic acquisition runs in the durable Supabase worker through the pinned
`youtube-transcript-plus` parser, with a shared 30-second deadline and a 2 MiB
HTTP response bound. It permits only the accepted video's YouTube watch, player
and timed-text endpoints, without redirects or transport credentials. The
immutable metadata checkpoint retains the exact acquired text, language, source
URL and extraction provider/version; recovery reuses it without acquiring again.
Receipt projection requires matching provenance and never replaces the accepted
empty input. Known input failures return the native input-required lifecycle
before enrichment; manual input revisions remain available without publication.

The accepted dispatch includes the complete authorized frozen course catalog,
within the 60000-byte ASCII JSON transport budget; oversized snapshots fail
before acceptance rather than being truncated. Review receipts must carry the
accepted snapshot identity/hash and an associated enriched document. Proposed
targets must belong to that snapshot. Old immutable jobs without a catalog and
old ASCII-encoded receipts retain compatible replay.

Canonical cancellation accepts a versioned local intent without network I/O.
It immediately blocks publication; the committed dispatcher recovers any lost
job binding and delivers the same scoped command UUID until its exact
acknowledgement is recorded. Technical receipt revisions do not change the
command version. Supabase archives the queue message and fences the old claim
atomically, preserving the prior receipt in an append-only service-only audit.
Already active external I/O is not interrupted; its worker cannot checkpoint or
finish after cancellation. Legacy command policy and accepted inputs are unchanged.

Canonical retry uses the same versioned post-commit outbox for failed jobs only.
It retains the native task, external job, accepted request/provider and committed
checkpoints; a saved analysis is reused without another paid call. The durable
command atomically requeues one message, preserves the previous failed receipt
and grants at most two additional claims, capped at twenty lifetime attempts.
Pending commands cannot be replaced, and acknowledgements must advance both the
command version and technical receipt. Retry cannot revive cancelled jobs or
reset an exhausted lifetime budget.

Canonical input-required receipts reuse the native lifecycle error policy. An
explicit transcript command creates a new immutable execution in the accepted
workspace, preserving the provider/catalog even after intake routing changes.
The previous accepted input, task, remote job and attempt history remain intact.
One scoped cancellation intent marks that parent superseded; child creation and
the parent transition roll back together. Replay returns the same child, never
another Project or mandatory technical subtask. Learning may link exactly one
new editorial request through the API extension point; it does not reroute the
child through current provider configuration or execute it locally.

The preceding local pure suite passed 105 contracts. The 2026-10-09 isolated
API E2E passed all 56 native API security tests with zero failures or errors;
the deployment harness also proves one unpublished native Learning
result/attempt and idempotent replay.
Do not enable this candidate in production: worker scheduling, all-source and
large-catalog parity, final integrated acceptance
and productive target/image/canary proof remain required. Source test success is
not runtime image identity. Owner CI retains native Project/API gates, real
Project concurrency and repeated upgrades.

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
