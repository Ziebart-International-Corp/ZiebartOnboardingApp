# Deploying the Flask app on Vercel

- **Root Directory:** In Vercel → Project Settings → General, set **Root Directory** to `.` (or leave empty). Do **not** set it to `next-app`, or you'll get 404 or a spinning Next.js app.
- **Environment variables:** Set **DATABASE_URL** (Neon Postgres) and **SECRET_KEY** in Vercel → Project Settings → Environment Variables.
- **Entry point:** `pyproject.toml` declares the Flask app as `app:app` so Vercel detects and runs it.
- **Health check:** After deploy, open `https://your-app.vercel.app/health`. If you get `{"status":"ok"}`, the Flask app is running. Check **Functions** / **Logs** in the deployment for errors (e.g. DB timeout, import errors).
