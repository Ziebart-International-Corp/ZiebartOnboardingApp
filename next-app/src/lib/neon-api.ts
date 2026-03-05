/**
 * Neon Data API (REST) client. Uses NEON_API_URL and NEON_API_KEY.
 * No direct DB connection — all access via HTTP to the Neon REST endpoint.
 */

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
  const qs = searchParams
    ? "?" + new URLSearchParams(searchParams).toString()
    : "";
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
  if (res.status === 204 || res.headers.get("content-length") === "0")
    return undefined as T;
  return res.json() as Promise<T>;
}

/** Get total count via GET + Prefer: count=exact, parse Content-Range (e.g. "0-9/42" => 42) */
async function fetchCount(path: string, searchParams: Record<string, string> = {}): Promise<number> {
  const base = getBase();
  const key = getKey();
  const qs = new URLSearchParams({ ...searchParams, select: "id", limit: "1" }).toString();
  const res = await fetch(`${base}${path}?${qs}`, {
    method: "GET",
    headers: {
      Accept: "application/json",
      apikey: key,
      Authorization: `Bearer ${key}`,
      Prefer: "count=exact",
    },
  });
  const range = res.headers.get("content-range");
  if (range) {
    const m = range.match(/\/(\d+)$/);
    if (m) return parseInt(m[1], 10);
  }
  return 0;
}

// --- Users (table: users) ---
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
  const encoded = encodeURIComponent(email.trim().toLowerCase());
  const rows = await fetchApi<DbUser[]>(
    "/users",
    { searchParams: { email: `eq.${encoded}`, access_revoked_at: "is.null", select: "id,username,email,password_hash,full_name,role" } }
  );
  return Array.isArray(rows) && rows.length > 0 ? rows[0] : null;
}

export async function createUser(data: {
  username: string;
  email: string;
  password_hash: string;
  full_name?: string;
  role?: string;
}): Promise<DbUser> {
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

// --- New hires (table: new_hires) ---
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
  const params: Record<string, string> = {
    select: "id,username,first_name,last_name,email,department,position,status,start_date,created_at",
    order: "last_name.asc,first_name.asc",
  };
  if (whereNotRemoved) params.status = "neq.removed";
  const rows = await fetchApi<DbNewHire[]>("/new_hires", { searchParams: params });
  return Array.isArray(rows) ? rows : [];
}

export async function getNewHiresCount(): Promise<number> {
  return fetchCount("/new_hires", { status: "neq.removed" });
}

// --- Documents (table: documents) ---
export interface DbDocument {
  id: number;
  filename: string;
  original_filename: string;
  display_name: string | null;
  is_visible: boolean;
  created_at: string;
}

export async function getDocuments(): Promise<DbDocument[]> {
  const rows = await fetchApi<DbDocument[]>("/documents", {
    searchParams: {
      select: "id,filename,original_filename,display_name,is_visible,created_at",
      order: "created_at.desc",
    },
  });
  return Array.isArray(rows) ? rows : [];
}

export async function getDocumentsCount(): Promise<number> {
  return fetchCount("/documents");
}
