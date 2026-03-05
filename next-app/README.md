# Ziebart Onboarding – Next.js frontend

This Next.js app is the **frontend** for the Ziebart Onboarding app. It uses the existing **Flask backend** as the API.

## How it works

- **Next.js** (this app): Login page and home. Runs on port 3000 by default.
- **Flask**: All other app features (dashboard, new hires, documents, etc.). Must run on the URL set in `NEXT_PUBLIC_API_URL` (default `http://127.0.0.1:5000`).

After you sign in on the Next.js login page, you are redirected to the Flask app for the rest of the session.

## Setup

1. Copy env example and set your Flask URL (if different from default):
   ```bash
   cp .env.local.example .env.local
   # Edit .env.local: NEXT_PUBLIC_API_URL=http://127.0.0.1:5000
   ```

2. Install and run:
   ```bash
   npm install
   npm run dev
   ```

3. Run the **Flask** backend from the project root (e.g. `python app.py` on port 5000).

4. Open [http://localhost:3000](http://localhost:3000), sign in, and you’ll be redirected to Flask.

## Scripts

- `npm run dev` – Start Next.js dev server (port 3000)
- `npm run build` – Production build
- `npm run start` – Run production server
