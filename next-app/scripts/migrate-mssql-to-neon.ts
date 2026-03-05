/**
 * One-time migration: copy all data from old MSSQL DB to Neon (Postgres).
 * Requires: OLD_MSSQL_CONNECTION_STRING, NEON_MIGRATION_URL (direct Postgres).
 * Run from next-app: npx tsx scripts/migrate-mssql-to-neon.ts
 */
import { readFileSync, existsSync } from "fs";
import { resolve } from "path";
const envPath = resolve(process.cwd(), ".env");
if (existsSync(envPath)) {
  for (const line of readFileSync(envPath, "utf8").split("\n")) {
    const m = line.match(/^([^#=]+)=(.*)$/);
    if (m) process.env[m[1].trim()] = m[2].trim().replace(/^["']|["']$/g, "");
  }
}

import sql from "mssql";
import pg from "pg";

const NEON_URL = process.env.NEON_MIGRATION_URL;
const MSSQL_URL = process.env.OLD_MSSQL_CONNECTION_STRING;

if (!NEON_URL) throw new Error("Set NEON_MIGRATION_URL (direct Postgres connection string from Neon)");
if (!MSSQL_URL) throw new Error("Set OLD_MSSQL_CONNECTION_STRING (your old MSSQL connection string)");

/** Convert PascalCase to snake_case */
function toSnakeCase(str: string): string {
  return str.replace(/[A-Z]/g, (c) => `_${c.toLowerCase()}`).replace(/^_/, "");
}

/** Tables in FK-safe order (parents before children) */
const TABLE_ORDER = [
  "stores",
  "roles",
  "users",
  "manager_permissions",
  "new_hires",
  "documents",
  "document_stores",
  "role_documents",
  "checklist_items",
  "new_hire_checklists",
  "admin_settings",
  "training_videos",
  "user_tasks",
  "document_assignments",
  "external_links",
  "quiz_questions",
  "quiz_answers",
  "user_training_progress",
  "user_quiz_responses",
  "document_signature_fields",
  "document_signatures",
  "document_typed_fields",
  "document_typed_field_values",
  "user_notifications",
  "new_hire_required_training",
];

function mapRow(row: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(row)) {
    const key = toSnakeCase(k);
    if (v instanceof Date) out[key] = v.toISOString();
    else out[key] = v;
  }
  return out;
}

async function main() {
  const pool = new pg.Pool({ connectionString: NEON_URL });
  let mssqlPool: sql.ConnectionPool | null = null;

  try {
    mssqlPool = await sql.connect(MSSQL_URL);
  } catch (e) {
    console.error("Failed to connect to MSSQL. Check OLD_MSSQL_CONNECTION_STRING.");
    throw e;
  }

  for (const table of TABLE_ORDER) {
    try {
      const result = await mssqlPool.request().query(`SELECT * FROM [${table}]`);
      const rows = (result.recordset as Record<string, unknown>[]) || [];
      if (rows.length === 0) {
        console.log(table, ": 0 rows (skipped)");
        continue;
      }
      const mapped = rows.map(mapRow);
      const columns = Object.keys(mapped[0]);
      const quotedCols = columns.map((c) => `"${c}"`).join(", ");
      const hasId = columns.includes("id") && table !== "admin_settings";
      let inserted = 0;
      for (const row of mapped) {
        const values = columns.map((c) => row[c]);
        const placeholders = values.map((_, i) => `$${i + 1}`).join(", ");
        const conflictClause = hasId ? " ON CONFLICT (id) DO NOTHING" : "";
        try {
          const res = await pool.query(
            `INSERT INTO "${table}" (${quotedCols}) VALUES (${placeholders})${conflictClause}`,
            values
          );
          if (res.rowCount) inserted++;
        } catch (err) {
          console.warn(table, "row err:", (err as Error).message, String(row.id ?? ""), (err as Error).message);
        }
      }
      if (hasId && inserted > 0) {
        const seq = await pool.query(`SELECT pg_get_serial_sequence('"${table}"', 'id') as seq`).then((r) => r.rows[0]?.seq);
        if (seq) {
          await pool.query(`SELECT setval($1, (SELECT COALESCE(MAX(id), 1) FROM "${table}"))`, [seq]);
        }
      }
      console.log(table, ":", inserted, "rows");
    } catch (e) {
      console.error(table, ":", (e as Error).message);
    }
  }

  await pool.end();
  if (mssqlPool) await mssqlPool.close();
  console.log("Done.");
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
