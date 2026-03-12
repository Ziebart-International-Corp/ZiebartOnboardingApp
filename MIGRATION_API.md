# Migrating to API-only (no direct DB in main app)

## Current state

- **data_api/** – FastAPI service that connects to the DB and exposes REST (users, new_hires, documents, stores). Run it separately (e.g. `uvicorn data_api.main:app --port 8001`).
- **api_client.py** – HTTP client for the Data API.
- **data_layer.py** – Single data access layer: when `API_BASE_URL` is set it uses the API; otherwise it uses the DB. Use this everywhere instead of `Model.query` / `db.session` so the app can run with zero DB later.
- **Already using API when `API_BASE_URL` set:** auth (`load_user`, `get_user_role`), `get_current_user_store_id` (via `data_layer`).

The rest of the app still uses `models` / `db` directly (~570 usages in app.py). So the main app still opens a DB connection until the migration is finished.

## To get to “no direct DB” (API only)

1. **Deploy data_api** (e.g. second Vercel project or Railway/Render) and set **API_BASE_URL** in the main app (e.g. `https://your-data-api.vercel.app`). Set **DATA_API_KEY** if you use it.
2. **Add any missing endpoints** to data_api for operations the app needs (writes, complex queries). See `data_api/main.py` and `api_client.py` for the current set.
3. **Replace every DB use in app.py** with `data_layer` or `api_client`: no direct `Model.query`, no `db.session`, no data access from `models`. Use `data_layer.get_user`, `data_layer.get_new_hire`, `data_layer.list_documents`, etc. (add more helpers in `data_layer.py` as needed).
4. **Stop DB init when using API:** In `app.py`, wrap the DB config and `db.init_app(app)` in `if not config.USE_DATA_API:` so the main app never creates a DB connection when `API_BASE_URL` is set. After step 3, the app will run with no direct DB.
