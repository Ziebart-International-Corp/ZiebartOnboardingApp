# Ziebart Onboarding – Next.js (full-stack)

Full-stack Next.js app with **Neon** (serverless PostgreSQL). No Flask backend.

## Stack

- **Next.js 14** (App Router), TypeScript, Tailwind
- **Neon** (serverless PostgreSQL) via Prisma ORM
- **NextAuth.js** (credentials: email + password)

## Setup

1. **Environment**

   Copy env example and set your Neon URL and NextAuth secret:

   ```bash
   cp .env.local.example .env.local
   ```

   Edit `.env.local` (or `.env`):

   - `DATABASE_URL` – Neon connection string from [Neon Console](https://console.neon.tech) → your project → Connection details (e.g. `postgresql://user:password@ep-xxx.region.aws.neon.tech/neondb?sslmode=require`)
   - `NEXTAUTH_SECRET` – random string (e.g. `openssl rand -base64 32`)
   - `NEXTAUTH_URL` – app URL (e.g. `http://localhost:3000` in dev)

2. **Database (Neon)**

   Push the Prisma schema to Neon and seed an admin user:

   ```bash
   npm install
   npm run db:push
   SEED_ADMIN_EMAIL=admin@ziebart.com SEED_ADMIN_PASSWORD=YourPassword npm run db:seed
   ```

3. **Run**

   ```bash
   npm run dev
   ```

   Open [http://localhost:3000](http://localhost:3000), sign in with the seeded admin email/password.

## Scripts

| Command        | Description                    |
|----------------|--------------------------------|
| `npm run dev`  | Start dev server (port 3000)   |
| `npm run build`| Build for production           |
| `npm run start`| Run production server          |
| `npm run db:push` | Push Prisma schema to DB   |
| `npm run db:studio` | Open Prisma Studio        |
| `npm run db:seed`   | Create admin user (set `SEED_ADMIN_EMAIL`, `SEED_ADMIN_PASSWORD`) |

## Vercel

- Set **Root Directory** to `next-app` (if the repo root is the monorepo).
- Add env vars: `DATABASE_URL` (Neon connection string), `NEXTAUTH_SECRET`, `NEXTAUTH_URL` (e.g. `https://your-app.vercel.app`).
