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

## Proposed Python content pipeline

A complete development proposal for a Python pipeline inside this addon, with capability endpoints and standard Odoo Project tasks, is available in [docs/facodi-api](docs/facodi-api/README.md). This is planned behavior; the existing provider bridge is unchanged by the documentation delivery.

- Engineering epic: https://github.com/marcelo-m7/facodi-api/issues/1
- Deployment integration epic: https://github.com/marcelo-m7/facodi-deploy/issues/255
- [Implementation plan](docs/superpowers/plans/2026-10-06-facodi-api.md)

The current provider tests live in facodi_api/tests (the tests/ directory is proposed for future pure service tests). For the current checkout use:

```bash
python3 -m unittest discover -s facodi_api/tests -v
```
