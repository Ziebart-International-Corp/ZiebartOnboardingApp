# Migrating app.py into blueprints + services

## Status

`app.py` is ~400 lines. Feature routes live in `blueprints/`. Domain helpers live in `services/` and `db/`.

### Services (high level)

Mail, documents/PDF, wizard, stores, staff console, jobs (async signed PDF), theme, app_hooks, rate_limit, etc. See `services/`.

### Quality bar (A− track)

- Unit tests: `pytest tests -q` (install `requirements-dev.txt`)
- Smoke: `.\.venv\Scripts\python.exe tests\test_smoke.py`
- Background jobs: hardened claim/stuck recovery; admin UI at `/admin/jobs`
- Schema: `_run_users_migration_if_needed()` runs **once at app startup** and **fails loud** if migrations error. Prefer adding an explicit SQL script + one `_ensure_*` for new columns; full Alembic is a follow-up.
- PDF signatures: production uses visual overlay + `SignatureAuditLog`. Cryptographic PAdES (`sign_pdf_cryptographically`) needs HSM/KMS certs and is intentionally not enabled.

### Blueprints

`auth`, `feedback`, `manager`, `admin`, `documents`, `wizard`, `user`, `static_files`

Wizard imports critical helpers from `services.*` directly (not via `app` re-exports).
