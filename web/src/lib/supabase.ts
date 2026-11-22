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
  // Retry briefly on server errors and statement timeouts (code 57014), which come
  // from momentary load (e.g. many pages building at once), not from a bad query.
  for (let attempt = 0; ; attempt++) {
    const res = await fetch(`${url}/rest/v1/${path}`, { headers: headers(key) });
    if (res.ok) return res.json();
    const body = await res.text();
    if (res.status >= 500 && attempt < RETRIES) {
      await new Promise((r) => setTimeout(r, 500 * 2 ** attempt));
      continue;
    }
    throw new Error(`Supabase ${res.status} on ${path.split("?")[0]}: ${body}`);
  }
}

const RETRIES = 3; // waits 0.5 s, 1 s, 2 s

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
