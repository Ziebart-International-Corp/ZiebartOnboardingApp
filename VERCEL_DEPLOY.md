# Deploying the Flask app on Vercel

- **Root Directory:** In Vercel → Project Settings → General, set **Root Directory** to `.` (or leave empty). Do **not** set it to `next-app`, or Vercel will deploy the Next.js app instead of this Flask app and the site may spin on "Loading...".
- **Environment variables:** Set **DATABASE_URL** (Neon Postgres) and **SECRET_KEY** in Vercel → Project Settings → Environment Variables.
- **Health check:** After deploy, open `https://your-app.vercel.app/health`. If you get `{"status":"ok"}`, the Flask app is running. If the home page still spins, check Vercel → Deployments → your deployment → **Functions** / **Logs** for errors (e.g. DB timeout, import errors).
