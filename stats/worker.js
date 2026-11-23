// Job Hunter active-user counter (Cloudflare Worker + D1), served at https://stats.codeprojectsofficial.com
//
//   POST /ping   {"id": "<32 hex chars>", "version": "2.0.0"}   an install is in use today (the app sends it once a day)
//   GET  /stats  {"daily", "weekly", "monthly", "installs", "versions": {"2.0.0": 812, ...}, "updated"}
//
// Stores only the random install id, the day and the version. No IP address, name, email or anything else.
// Day rows older than 90 days are deleted every night; the first day each install was seen is kept for "installs".

const CORS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type',
};

const json = (data, status = 200, extra = {}) =>
  new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json', ...CORS, ...extra } });

const day = (offset = 0) => new Date(Date.now() - offset * 86400000).toISOString().slice(0, 10);

async function ping(request, env) {
  let body;
  try {
    body = await request.json();
  } catch {
    return json({ error: 'expected JSON' }, 400);
  }
  const id = String(body?.id ?? '');
  const version = String(body?.version ?? '').slice(0, 20);
  if (!/^[0-9a-f]{32}$/.test(id) || !/^[0-9A-Za-z.\-+]{1,20}$/.test(version)) return json({ error: 'bad ping' }, 400);
  const today = day();
  await env.DB.batch([
    env.DB.prepare(
      'INSERT INTO pings (id, day, version) VALUES (?1, ?2, ?3) ON CONFLICT (id, day) DO UPDATE SET version = excluded.version',
    ).bind(id, today, version),
    env.DB.prepare('INSERT OR IGNORE INTO installs (id, first_day) VALUES (?1, ?2)').bind(id, today),
  ]);
  return new Response(null, { status: 204, headers: CORS });
}

async function stats(request, env, ctx) {
  const cache = caches.default;
  const key = new Request(new URL('/stats', request.url).toString());
  const hit = await cache.match(key);
  if (hit) return hit;
  const count = (sql, ...args) => env.DB.prepare(sql).bind(...args).first('n');
  const since = (days) => count('SELECT COUNT(DISTINCT id) AS n FROM pings WHERE day >= ?1', day(days - 1));
  const [daily, weekly, monthly, installs, versions] = await Promise.all([
    since(1), since(7), since(30),
    count('SELECT COUNT(*) AS n FROM installs'),
    env.DB.prepare('SELECT version, COUNT(DISTINCT id) AS n FROM pings WHERE day >= ?1 GROUP BY version ORDER BY n DESC')
      .bind(day(6)).all(),
  ]);
  const res = json({
    daily, weekly, monthly, installs,
    versions: Object.fromEntries(versions.results.map((r) => [r.version, r.n])),
    updated: new Date().toISOString(),
  }, 200, { 'Cache-Control': 'public, max-age=600' });
  ctx.waitUntil(cache.put(key, res.clone()));
  return res;
}

export default {
  async fetch(request, env, ctx) {
    const { pathname } = new URL(request.url);
    if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers: CORS });
    if (pathname === '/ping' && request.method === 'POST') return ping(request, env);
    if (pathname === '/stats' && request.method === 'GET') return stats(request, env, ctx);
    return json({ error: 'not found' }, 404);
  },

  async scheduled(_event, env) {
    await env.DB.prepare('DELETE FROM pings WHERE day < ?1').bind(day(90)).run();
  },
};
