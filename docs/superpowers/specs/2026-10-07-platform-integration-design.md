# FACODI platform integration: execution design

This implements the architecture and acceptance contract in the reviewed [next-agent prompt](https://github.com/marcelo-m7/facodi-deploy/blob/main/docs/facodi-api/prompt-platform-integration.md), which Marcelo asked us to continue autonomously. The API owns processing; Learning owns canonical sources, submission context, immutable analysis evidence, curricular proposals and human decisions. Existing legacy consumers remain the default until parity and external acceptance pass.

## Processing and commands

Use one authorized ORM submission facade for HTTP and Learning. Bind owner/company/website, input hash, provider and catalog to the accepted request; deduplicate within that scope. Commands require a nonnegative expected revision and a row lock. Retry applies only to failed/waiting_input runs, cancel never undoes publication, and manual input creates a separately identified child run rather than editing the original. Acquisition errors that require intervention are waiting_input with distinct sanitized codes. Cache complete processing stages so restart can reuse verified checkpoints. Uncommitted ORM work rolls back after a worker crash; external reads before a checkpoint can be repeated and are not claimed exactly-once.

Input attachments require native authorization, matching course scope where linked, bounded size and immutable digest. Parse PDF/DOCX in a deadline/resource-limited child. Never fetch arbitrary document URLs. Provider selection is server-owned and frozen, baseline explicitly labeled. An independent structured provider may be configured without facodi_ai; source text cannot select credentials, model, prompt or tools. Provider output must reference real input chunks.

## Learning consumer boundary

Opt-in odoo_python jobs enqueue one run without executing it. Keep the existing job/result/attempt models as editorial history; only complete/schema-valid outputs create an immutable result. The API scheduler processes runs; the legacy Learning scheduler excludes delegated jobs. Reconcile finished runs separately, never dispatch processing twice. Existing slide content is the canonical record and must not be duplicated on review/publication. Snapshot content at intake and reject stale inputs. Add persistent origin/provider authority so edits of API-owned content cannot trigger legacy Supabase reanalysis. Legacy jobs, external correlation and non-learning AI functions remain intact.

Source ingestion, slide/backend requests, submission tracking, Explore canonical sources and curricular suggestion consumers use adapters to this boundary. Public projections contain safe states, never technical artifacts/task IDs. Native review actions still control publication and curriculum decisions. Learning may depend on the API; the reverse dependency is forbidden.

## Promotion

All new selection is off by default. Test clean install, upgrades, legacy fixtures, real ORM/HTTP/cron, concurrency, restart, review/replay, Website/Portal and DB+filestore restore before promotion. Real YouTube capture remains blocked until a supported server-side transport is available and tested. Production backup/image identity and external credentials are operational gates, never inferred from CI. Never alter production volumes or silently cut over consumers.
