# Migrate old database data to Neon

This guide covers two things: **test user** and **full data migration** from your old DB (e.g. MSSQL) to Neon.

---

## 1. Test user (asymons@ziebart.com / password)

The app’s Data API may require Neon Auth (JWT), so the script that creates the test user might not work from your machine. Use the SQL below in the **Neon SQL Editor** instead.

1. In Neon Console go to your branch → **SQL Editor**.
2. Paste and run the contents of **`prisma/seed-test-user.sql`**.

You can then log in with **asymons@ziebart.com** / **password**.

---

## 2. Migrate all old tables and data to Neon

You need:

- **Source:** Old database (e.g. MSSQL) with existing data.
- **Target:** Neon (Postgres). Tables must already exist (e.g. you ran `neon-create-tables.sql`).

### Option A: Run the Node migration script (MSSQL → Neon)

1. **Install deps** (from `next-app`):
   ```bash
   npm install mssql pg --save-dev
   ```
2. **Set env** (in `.env` or in the shell):
   - `OLD_MSSQL_CONNECTION_STRING` – connection string for the **old** MSSQL database.
   - `NEON_MIGRATION_URL` – **direct** Postgres connection string for Neon (from Neon Console → Connect → connection string). Use this only for the one-time migration; the app keeps using the Data API.
3. **Run** (from `next-app`):
   ```bash
   npx tsx scripts/migrate-mssql-to-neon.ts
   ```

The script copies tables in dependency order and maps PascalCase columns to snake_case where needed.

### Option B: Export from old DB and import into Neon yourself

1. **Export** from your old DB (e.g. MSSQL): use SSMS “Export Data” or `bcp` / scripts to get CSV or SQL inserts.
2. **Import** into Neon: use Neon’s **SQL Editor** to run `INSERT` statements, or a CSV import tool, in an order that respects foreign keys (e.g. `stores` → `roles` → `users` → …).

---

## After migration

- Ensure the test user exists (run `prisma/seed-test-user.sql` in Neon if you haven’t).
- In the app, log in with **asymons@ziebart.com** / **password** and confirm data looks correct.
