# Data API

REST API over the app database. Run **separately** so only this process holds DB connections; the main Flask app uses `API_BASE_URL` and `api_client` instead of direct DB.

## Run

From project root, with venv active:

```bash
pip install -r data_api/requirements.txt
uvicorn data_api.main:app --reload --port 8001
```

Or from `data_api/`:

```bash
pip install -r requirements.txt
uvicorn main:app --reload --port 8001
```

Uses the same `.env` in project root (DATABASE_URL or DB_*).

## Endpoints (read-only for now)

- `GET /health`
- `GET /users`, `GET /users/by-username/{username}`
- `GET /new-hires`, `GET /new-hires/by-username/{username}`
- `GET /documents`, `GET /documents/{id}`
- `GET /stores`

Optional: set `DATA_API_KEY` in env and send `X-API-Key` header.

## Main app

Set in `.env`:

- `API_BASE_URL=http://localhost:8001` (or your data_api URL)
- `DATA_API_KEY=<same as data_api>` if you use API key

Auth (load_user, get_user_role) will use the API when `API_BASE_URL` is set. Full migration of the rest of the app to API-only is in progress (see MIGRATION_API.md).
