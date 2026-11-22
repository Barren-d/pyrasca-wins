import "server-only";

/**
 * Minimal read-only client for Supabase's REST API (PostgREST).
 *
 * Uses the public anon key, so every read goes through row-level security
 * (public read on every table). Never put the service_role key here.
 */
function config() {
  const url = process.env.SUPABASE_URL;
  const key = process.env.SUPABASE_ANON_KEY;
  if (!url || !key) {
    throw new Error("SUPABASE_URL and SUPABASE_ANON_KEY must be set (see web/.env.example)");
  }
  return { url: url.replace(/\/$/, ""), key };
}

function headers(key: string, extra?: Record<string, string>) {
  return { apikey: key, Authorization: `Bearer ${key}`, ...extra };
}

/** GET /rest/v1/{path}, e.g. "game_overview?select=name&active=eq.true". */
export async function select<T>(path: string): Promise<T[]> {
  const { url, key } = config();
  const res = await fetch(`${url}/rest/v1/${path}`, { headers: headers(key) });
  if (!res.ok) throw new Error(`Supabase ${res.status} on ${path.split("?")[0]}: ${await res.text()}`);
  return res.json();
}

/** Exact row count of a table or view, with optional PostgREST filters. */
export async function count(table: string, filters = ""): Promise<number> {
  const { url, key } = config();
  const res = await fetch(`${url}/rest/v1/${table}?select=*&limit=1${filters ? `&${filters}` : ""}`, {
    method: "HEAD",
    headers: headers(key, { Prefer: "count=exact" }),
  });
  if (!res.ok) throw new Error(`Supabase ${res.status} counting ${table}`);
  const total = res.headers.get("content-range")?.split("/")[1];
  return total && total !== "*" ? Number(total) : 0;
}
