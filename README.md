# FACODI API

This repository contains the Odoo addon that exposes the FACODI service boundary for external providers such as Supabase and Stripe. It keeps Odoo domain code decoupled from third-party transports and provides a small registry for auditable outbound calls.

## Structure

- `facodi_api/` — installable Odoo addon
- `tests/` — provider and contract tests

## Local validation

Run the addon contract tests with:

```bash
python3 -m unittest discover -s tests -v
```
