# Environment Variables Reference

Variables are read in **`config.py`** (and a few services) from the project `.env` file and/or the process environment. On **IIS + wfastcgi**, keep secrets in `.env` next to `app.py` (IIS blocks HTTP access to `.env`).

---

## Required

| Variable | Description |
|----------|-------------|
| `SECRET_KEY` | Flask session signing key. Must be unique — the app **refuses** the insecure default unless `ALLOW_INSECURE_SECRET_KEY=1`. |
| `DB_SERVER` | SQL Server hostname |
| `DB_PORT` | SQL Server port (default `42278`) |
| `DB_NAME` | Database name (e.g. `NewHireApp`) |
| `DB_USER` | SQL login |
| `DB_PASSWORD` | SQL password |

Optional DB:

| Variable | Description |
|----------|-------------|
| `DB_MAX_POOL_SIZE` | SQLAlchemy pool size (default `300`) |
| `DB_TRUST_SERVER_CERTIFICATE` | `yes` (default) or `no` for `TrustServerCertificate` |

---

## Auth / HTTPS

| Variable | Description |
|----------|-------------|
| `AUTH_METHOD` | `windows` or `ldap` (email/password login is primary for new hires) |
| `ADMIN_USERS` | Comma-separated admin usernames |
| `ADMIN_GROUP` | AD group name if using LDAP |
| `DOMAIN_NAME` / `DOMAIN_CONTROLLER` / `LDAP_BASE_DN` | Windows/LDAP options |
| `FORCE_HTTPS` | Default on; set `false` to disable Flask HTTPS redirect |
| `PROXY_FIX` | Default `True` — trust `X-Forwarded-*` behind IIS |
| `PREFERRED_URL_SCHEME` | `http` or `https` |
| `SESSION_COOKIE_SECURE` | Optional static default; also set dynamically when HTTPS detected |

---

## Email (SMTP / SocketLabs)

| Variable | Description |
|----------|-------------|
| `MAIL_SERVER` / `MAIL_PORT` / `MAIL_USE_TLS` / `MAIL_USE_SSL` | SMTP |
| `MAIL_USERNAME` / `MAIL_PASSWORD` / `MAIL_DEFAULT_SENDER` | Credentials |
| `SOCKETLABS_USERNAME` / `SOCKETLABS_PASSWORD` | Alternate relay |
| `EMAIL_DOMAIN` | Default domain for new-hire emails |

---

## Asana feedback

| Variable | Description |
|----------|-------------|
| `ASANA_ACCESS_TOKEN` | Personal / service token (preferred) |
| `ASANA_FEEDBACK_PROJECT_GID` | Target project |
| `ASANA_SECTION_GID_COMMENT` / `_ISSUE` / `_SUGGESTION` | Section GIDs |
| `ASANA_FEEDBACK_ASSIGNEE_GID` | Assignee for new tasks |
| `ASANA_CLIENT_ID` / `ASANA_CLIENT_SECRET` / `ASANA_REFRESH_TOKEN` | Optional OAuth |
| `ASANA_REDIRECT_URI` | Optional; defaults to `/admin/asana/callback` |

---

## Feature flags / limits

| Variable | Description |
|----------|-------------|
| `ENABLE_TEST_FORM_WIZARD` | `true` to show admin Test Form Wizard (default off) |
| `MAX_DOCUMENT_UPLOAD_MB` | Max size for library document uploads (default `40`; videos still use 500MB ceiling) |
| `ALLOW_INSECURE_SECRET_KEY` | Local only — allow default `SECRET_KEY` |
| `FLASK_DEBUG` | `1` to enable `app.run(debug=True)` locally |
| `OPENAI_API_KEY` | Optional AI for Test Form Wizard scanned PDFs |

---

## Optional data API (`data_api/`)

Separate FastAPI process — **not** required for the main IIS app.

| Variable | Description |
|----------|-------------|
| `DATA_API_KEY` | **Required** if you run `data_api`. Without it, API routes return 503. |

---

## Where defined

- `config.py` — core settings
- `.env` / `.env.example` — local and IIS secrets
- `web.config` — IIS FastCGI paths and headers (not secrets)
