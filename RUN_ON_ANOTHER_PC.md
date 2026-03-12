# Running This App on Another Computer

GitHub does not track everything. Here’s what to **copy over** or **set up** on the new machine after you clone the repo.

---

## 1. Clone the repo (on the new computer)

```bash
git clone https://github.com/Ziebart-International-Corp/ZiebartOnboardingApp.git
cd ZiebartOnboardingApp
```

---

## 2. Things to copy from the old computer (not in GitHub)

### Environment / secrets (if you use them)

- **`.env`** (if it exists in the project root)  
  - Holds secrets and overrides: `SECRET_KEY`, `DB_SERVER`, `DB_PASSWORD`, `MAIL_PASSWORD`, etc.  
  - Copy the whole file to the new PC in the same folder as `app.py`.  
  - If you don’t use `.env`, set the same variables in the system environment or in IIS/app config.

### Uploaded files (app data)

- **`uploads/`** folder  
  - PDFs, videos, dashboard assets (e.g. handbook, training videos, `dashboard_hero/`, `videos/`).  
  - Not in the repo. Copy the entire `uploads` folder from the old PC to the new one (same place next to `app.py`).

### Virtual environment (optional to copy)

- **`venv/`** or **`.venv/`**  
  - Ignored by Git. Don’t copy it; recreate it on the new PC (see below).

---

## 3. Set up on the new computer

### Python and virtual environment

1. Install Python 3 (same major version as on the old PC, e.g. 3.11).
2. In the project folder:
   ```bash
   python -m venv venv
   venv\Scripts\activate
   pip install -r requirements.txt
   ```

### Database

- The app uses **MSSQL** (connection in `config.py` or `.env`).  
- Either:
  - Point the new PC to the **same** SQL Server (set `DB_SERVER`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` in `.env` or environment), or  
  - Use a different server and run migrations / init scripts as you did on the first PC.

### ODBC driver (for SQL Server)

- Install **ODBC Driver for SQL Server** (e.g. “ODBC Driver 18 for SQL Server”) on the new PC so `pyodbc` can connect.

### Config / environment

- Ensure **SECRET_KEY**, **DB_***, and (if used) **MAIL_*** and **AUTH_*** are set (via `.env` or system/env vars).  
- Change **SECRET_KEY** and **DB_PASSWORD** if this is a different environment.

### Running the app

- From the project folder with the venv activated:
  ```bash
  python app.py
  ```
  Or run under IIS as on the old PC (same bindings and app pool).

---

## Quick checklist

| Item | In GitHub? | Action on new PC |
|------|------------|-------------------|
| Source code | Yes | `git clone` |
| `.env` | No (don’t commit secrets) | Copy from old PC or recreate |
| `uploads/` | No | Copy from old PC |
| `venv/` | No (ignored) | Create new venv, `pip install -r requirements.txt` |
| ODBC Driver 18 for SQL Server | N/A | Install on new PC |
| DB + config | N/A | Same MSSQL or new; set DB_* and SECRET_KEY |

If you use **Windows auth / IIS**, also replicate IIS app pool, bindings, and any proxy/HTTPS settings (e.g. `PREFERRED_URL_SCHEME`, `PROXY_FIX`) on the new machine.
