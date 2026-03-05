/**
 * Database access: uses direct Postgres (DATABASE_URL) when set, otherwise Neon Data API.
 * Direct connection works on Vercel without JWT; Data API requires Neon Auth JWT.
 */

import { neon } from "@neondatabase/serverless";

const useDirect = () => !!process.env.DATABASE_URL;

function getSql() {
  const url = process.env.DATABASE_URL;
  if (!url) throw new Error("DATABASE_URL is required when using direct connection");
  return neon(url);
}

// --- Data API helpers (used only when DATABASE_URL is not set) ---
const getBase = () => {
  const url = process.env.NEON_API_URL?.replace(/\/$/, "");
  if (!url) throw new Error("NEON_API_URL is required");
  return url;
};
const getKey = () => {
  const key = process.env.NEON_API_KEY;
  if (!key) throw new Error("NEON_API_KEY is required");
  return key;
};

async function fetchApi<T>(
  path: string,
  opts: { method?: string; body?: object; searchParams?: Record<string, string>; prefer?: string } = {}
): Promise<T> {
  const base = getBase();
  const key = getKey();
  const { method = "GET", body, searchParams, prefer } = opts;
  const qs = searchParams ? "?" + new URLSearchParams(searchParams).toString() : "";
  const headers: Record<string, string> = {
    Accept: "application/json",
    "Content-Type": "application/json",
    apikey: key,
    Authorization: `Bearer ${key}`,
  };
  if (prefer) headers["Prefer"] = prefer;
  const res = await fetch(`${base}${path}${qs}`, {
    method,
    headers,
    ...(body !== undefined && { body: JSON.stringify(body) }),
  });
  if (!res.ok) {
    const t = await res.text();
    throw new Error(`Neon API ${res.status}: ${t}`);
  }
  if (res.status === 204 || res.headers.get("content-length") === "0") return undefined as T;
  return res.json() as Promise<T>;
}

async function fetchCount(path: string, searchParams: Record<string, string> = {}): Promise<number> {
  const base = getBase();
  const key = getKey();
  const qs = new URLSearchParams({ ...searchParams, select: "id", limit: "1" }).toString();
  const res = await fetch(`${base}${path}?${qs}`, {
    method: "GET",
    headers: { Accept: "application/json", apikey: key, Authorization: `Bearer ${key}`, Prefer: "count=exact" },
  });
  const range = res.headers.get("content-range");
  if (range) {
    const m = range.match(/\/(\d+)$/);
    if (m) return parseInt(m[1], 10);
  }
  return 0;
}

// --- Users ---
export interface DbUser {
  id: number;
  username: string;
  email: string | null;
  password_hash: string | null;
  full_name: string | null;
  role: string;
  access_revoked_at: string | null;
}

export async function getUserByEmail(email: string): Promise<DbUser | null> {
  const normalized = email.trim().toLowerCase();
  if (useDirect()) {
    const sql = getSql();
    const rows = await sql`
      SELECT id, username, email, password_hash, full_name, role
      FROM users WHERE lower(email) = ${normalized} AND access_revoked_at IS NULL LIMIT 1
    `;
    const user = (rows as DbUser[])[0] ?? null;
    return user;
  }
  const encoded = encodeURIComponent(normalized);
  const rows = await fetchApi<DbUser[]>("/users", {
    searchParams: { email: `eq.${encoded}`, access_revoked_at: "is.null", select: "id,username,email,password_hash,full_name,role" },
  });
  return Array.isArray(rows) && rows.length > 0 ? rows[0] : null;
}

export async function createUser(data: {
  username: string;
  email: string;
  password_hash: string;
  full_name?: string;
  role?: string;
}): Promise<DbUser> {
  if (useDirect()) {
    const sql = getSql();
    const rows = await sql`
      INSERT INTO users (username, email, password_hash, full_name, role)
      VALUES (${data.username}, ${data.email}, ${data.password_hash}, ${data.full_name ?? null}, ${data.role ?? "user"})
      RETURNING id, username, email, password_hash, full_name, role
    `;
    const row = (rows as DbUser[])[0];
    if (!row) throw new Error("Insert did not return user");
    return row;
  }
  const rows = await fetchApi<DbUser | DbUser[]>("/users", {
    method: "POST",
    body: {
      username: data.username,
      email: data.email,
      password_hash: data.password_hash,
      full_name: data.full_name ?? null,
      role: data.role ?? "user",
    },
    searchParams: { select: "id,username,email,password_hash,full_name,role" },
    prefer: "return=representation",
  });
  const row = Array.isArray(rows) ? rows[0] : (rows as DbUser);
  if (!row) throw new Error("Neon API did not return created user");
  return row;
}

export async function updateUserPasswordByEmail(email: string, password_hash: string): Promise<void> {
  const normalized = email.trim().toLowerCase();
  if (useDirect()) {
    const sql = getSql();
    await sql`UPDATE users SET password_hash = ${password_hash} WHERE lower(email) = ${normalized}`;
    return;
  }
  const encoded = encodeURIComponent(normalized);
  await fetchApi<unknown>("/users", {
    method: "PATCH",
    body: { password_hash },
    searchParams: { email: `eq.${encoded}` },
  });
}

// --- New hires ---
export interface DbNewHire {
  id: number;
  username: string;
  first_name: string;
  last_name: string;
  email: string;
  department: string | null;
  position: string | null;
  status: string;
  start_date: string | null;
  created_at: string;
}

export async function getNewHires(whereNotRemoved = true): Promise<DbNewHire[]> {
  if (useDirect()) {
    const sql = getSql();
    const rows = whereNotRemoved
      ? await sql`
          SELECT id, username, first_name, last_name, email, department, position, status, start_date, created_at
          FROM new_hires WHERE status <> 'removed'
          ORDER BY last_name ASC, first_name ASC
        `
      : await sql`
          SELECT id, username, first_name, last_name, email, department, position, status, start_date, created_at
          FROM new_hires ORDER BY last_name ASC, first_name ASC
        `;
    return rows as DbNewHire[];
  }
  const params: Record<string, string> = {
    select: "id,username,first_name,last_name,email,department,position,status,start_date,created_at",
    order: "last_name.asc,first_name.asc",
  };
  if (whereNotRemoved) params.status = "neq.removed";
  const rows = await fetchApi<DbNewHire[]>("/new_hires", { searchParams: params });
  return Array.isArray(rows) ? rows : [];
}

export async function getNewHiresCount(): Promise<number> {
  if (useDirect()) {
    const sql = getSql();
    const rows = await sql`SELECT count(*)::int AS c FROM new_hires WHERE status <> 'removed'`;
    return (rows as { c: number }[])[0]?.c ?? 0;
  }
  return fetchCount("/new_hires", { status: "neq.removed" });
}

// --- Documents ---
export interface DbDocument {
  id: number;
  filename: string;
  original_filename: string;
  display_name: string | null;
  is_visible: boolean;
  created_at: string;
}

export async function getDocuments(): Promise<DbDocument[]> {
  if (useDirect()) {
    const sql = getSql();
    const rows = await sql`
      SELECT id, filename, original_filename, display_name, is_visible, created_at
      FROM documents ORDER BY created_at DESC
    `;
    return rows as DbDocument[];
  }
  const rows = await fetchApi<DbDocument[]>("/documents", {
    searchParams: { select: "id,filename,original_filename,display_name,is_visible,created_at", order: "created_at.desc" },
  });
  return Array.isArray(rows) ? rows : [];
}

export async function getDocumentsCount(): Promise<number> {
  if (useDirect()) {
    const sql = getSql();
    const rows = await sql`SELECT count(*)::int AS c FROM documents`;
    return (rows as { c: number }[])[0]?.c ?? 0;
  }
  return fetchCount("/documents");
}

// --- External links (table: external_links) ---
export interface DbExternalLink {
  id: number;
  title: string;
  url: string;
  description: string | null;
  icon: string;
  image_filename: string | null;
  order: number;
  is_active: boolean;
}

export async function getExternalLinks(): Promise<DbExternalLink[]> {
  if (useDirect()) {
    const sql = getSql();
    const rows = await sql`
      SELECT id, title, url, description, icon, image_filename, "order", is_active
      FROM external_links WHERE is_active = true ORDER BY "order" ASC, created_at ASC
    `;
    return rows as DbExternalLink[];
  }
  const rows = await fetchApi<DbExternalLink[]>("/external_links", {
    searchParams: { is_active: "eq.true", order: "order.asc", select: "id,title,url,description,icon,image_filename,order,is_active" },
  });
  return Array.isArray(rows) ? rows : [];
}

// --- User tasks (table: user_tasks) ---
export interface DbUserTask {
  id: number;
  task_title: string;
  task_description: string | null;
  task_type: string;
  document_id: number | null;
  status: string;
  completed_at: string | null;
}

export async function getUserTasks(username: string): Promise<DbUserTask[]> {
  if (useDirect()) {
    const sql = getSql();
    const rows = await sql`
      SELECT id, task_title, task_description, task_type, document_id, status, completed_at
      FROM user_tasks WHERE username = ${username} ORDER BY assigned_at ASC
    `;
    return rows as DbUserTask[];
  }
  const enc = encodeURIComponent(username);
  const rows = await fetchApi<DbUserTask[]>("/user_tasks", {
    searchParams: { username: `eq.${enc}`, select: "id,task_title,task_description,task_type,document_id,status,completed_at", order: "assigned_at.asc" },
  });
  return Array.isArray(rows) ? rows : [];
}

// --- Document assignments (for "Sign Document" tasks) ---
export interface DbDocumentAssignmentWithDoc {
  id: number;
  document_id: number;
  document_display_name: string | null;
  is_completed: boolean;
  completed_at: string | null;
}

export async function getDocumentAssignmentsWithDoc(username: string): Promise<DbDocumentAssignmentWithDoc[]> {
  if (useDirect()) {
    const sql = getSql();
    const rows = await sql`
      SELECT da.id, da.document_id, d.display_name AS document_display_name, da.is_completed, da.completed_at
      FROM document_assignments da
      LEFT JOIN documents d ON d.id = da.document_id
      WHERE da.username = ${username}
      ORDER BY da.assigned_at ASC
    `;
    return rows as DbDocumentAssignmentWithDoc[];
  }
  return [];
}
