# Environment Variables Reference

All of these are read in **`config.py`** from `os.environ` (and optionally from a `.env` file via `python-dotenv`). Set them in Vercel under **Project → Settings → Environment Variables**.

---

## Required (app won’t work without these)

| Variable | Description | Example |
|----------|-------------|---------|
| `SECRET_KEY` | Flask session signing key. Use a long random string in production. | `your-random-secret-key-here` |
| `DATABASE_URL` | Full SQL Server connection string. **Or** set the pieces below and the app builds it. | `mssql+pyodbc://user:pass@host:port/db?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes` |

**If you don’t set `DATABASE_URL`**, the app builds it from:

| Variable | Description | Example |
|----------|-------------|---------|
| `DB_SERVER` | SQL Server hostname | `roadrunner` or `yourserver.database.windows.net` |
| `DB_PORT` | SQL Server port | `42278` or `1433` |
| `DB_NAME` | Database name | `NewHireApp` |
| `DB_USER` | SQL login | `Developer` |
| `DB_PASSWORD` | SQL password | (your password) |
| `DB_MAX_POOL_SIZE` | Connection pool size (optional) | `300` |

---

## Auth (how users log in)

| Variable | Description | Example |
|----------|-------------|---------|
| `AUTH_METHOD` | `windows` = IIS/Windows auth headers, `ldap` = LDAP | `windows` or `ldap` |
| `ADMIN_USERS` | Comma-separated admin usernames (no domain) | `admin,jdoe` |
| `ADMIN_GROUP` | AD group name for admins (if using LDAP) | `Domain Admins` |
| `DOMAIN_NAME` | Windows domain (e.g. for LDAP) | `CONTOSO` |
| `DOMAIN_CONTROLLER` | LDAP domain controller (optional) | `dc.contoso.com` |
| `LDAP_BASE_DN` | LDAP base DN (optional) | `DC=contoso,DC=com` |

Headers used when `AUTH_METHOD=windows` (set by your reverse proxy/IIS):

- `AUTH_USER_HEADER` → default `HTTP_X_FORWARDED_USER`
- `LOGON_USER_HEADER` → default `HTTP_X_REMOTE_USER`
- `AUTH_TYPE_HEADER` → default `HTTP_X_AUTH_TYPE`

---

## Email (SMTP)

| Variable | Description | Example |
|----------|-------------|---------|
| `MAIL_SERVER` | SMTP host | `smtp.office365.com` |
| `MAIL_PORT` | SMTP port | `587` |
| `MAIL_USE_TLS` | Use TLS | `True` |
| `MAIL_USE_SSL` | Use SSL | `False` |
| `MAIL_USERNAME` | SMTP login | `noreply@ziebart.com` |
| `MAIL_PASSWORD` | SMTP password | (your password) |
| `MAIL_DEFAULT_SENDER` | From address | `noreply@ziebart.com` |

---

## App behavior

| Variable | Description | Example |
|----------|-------------|---------|
| `EMAIL_DOMAIN` | Default domain for new hire emails when blank | `ziebart.com` |
| `SESSION_COOKIE_SECURE` | Only send cookie over HTTPS | `True` on Vercel |
| `PREFERRED_URL_SCHEME` | `http` or `https` | `https` on Vercel |
| `PROXY_FIX` | Trust X-Forwarded-* headers (use behind proxy) | `True` on Vercel |

---

## Where they’re defined in code

- **`config.py`** – every variable above is read with `os.environ.get('VAR_NAME', default)`.
- **`.env`** – optional; `python-dotenv` loads it and fills `os.environ` before config is used. On Vercel you don’t use a file; you set the same names in the dashboard.

---

## Vercel notes

1. **Flask on Vercel** – You run Flask as a serverless function (e.g. with `vercel build` and a serverless adapter). The app is built for a long‑running server (IIS, etc.), so you may need a Vercel serverless Flask setup (e.g. `vercel-python` or a custom `api` handler).
2. **SQL Server / pyodbc** – Vercel’s runtime may not include ODBC Driver for SQL Server. You might need a different driver or a **database proxy** (e.g. REST API in front of SQL) that runs elsewhere.
3. **Windows / LDAP auth** – If you rely on IIS Windows auth or on‑prem LDAP, that typically doesn’t run on Vercel; you’d need to replicate auth (e.g. email+password only) or put an auth proxy in front.
4. **File storage** – The app uses local `uploads/`. On Vercel the filesystem is read‑only and ephemeral. You’d need to switch uploads to a store (e.g. Vercel Blob, S3, or similar) and change the code that reads/writes files.

So: **all config is driven by the env vars above** (mainly in `config.py`). For “publishing the site with Vercel,” set those same variables in Vercel’s Environment Variables; getting the app itself to run on Vercel will also require adapting deployment (serverless Flask), database connectivity, auth, and file storage as above.
