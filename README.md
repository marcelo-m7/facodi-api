# FACODI API

This repository contains the Odoo addon that exposes the FACODI service boundary for external providers such as Supabase and Stripe. It keeps Odoo domain code decoupled from third-party transports and provides a small registry for auditable outbound calls.

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

Pure pipeline tests run with `PYTHONPATH=. pytest -q`. ORM tests run in the real Odoo registry through the isolated deploy CI. Provider contract tests also support:

```bash
python3 -m unittest discover -s facodi_api/tests -v
```
