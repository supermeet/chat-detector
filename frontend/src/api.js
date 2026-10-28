/* SafeSphere backend client.
   Base URL: ?api=<url> (remembered), else this page's origin when served over http(s), else http://localhost:8000.
   API key:  ?key=<key> (remembered on this device), sent as X-API-Key. */
window.SSApi = (function () {
  const mem = {};
  const store = {
    get(k) { try { return localStorage.getItem(k); } catch (e) { return mem[k] || null; } },
    set(k, v) { try { if (v == null) localStorage.removeItem(k); else localStorage.setItem(k, v); } catch (e) { mem[k] = v; } }
  };
  const qs = new URLSearchParams(location.search);
  if (qs.get('api')) store.set('ss_api', qs.get('api'));
  if (qs.get('key')) store.set('ss_key', qs.get('key'));

  class ApiError extends Error {
    constructor(status, msg) { super(typeof msg === 'string' ? msg : JSON.stringify(msg)); this.status = status; }
  }

  function base() {
    const b = store.get('ss_api') || (/^https?:$/.test(location.protocol) ? location.origin : 'http://localhost:8000');
    return b.replace(/\/$/, '');
  }

  async function req(method, path, body, opts) {
    opts = opts || {};
    const headers = {};
    const key = store.get('ss_key');
    if (key) headers['X-API-Key'] = key;
    let payload;
    if (body instanceof FormData) payload = body;
    else if (body !== undefined) { headers['Content-Type'] = 'application/json'; payload = JSON.stringify(body); }
    const ctl = new AbortController();
    const t = setTimeout(() => ctl.abort(), opts.timeout || 60000);
    try {
      const r = await fetch(base() + path, { method, headers, body: payload, signal: ctl.signal });
      if (opts.raw) { if (!r.ok) throw new ApiError(r.status, await r.text()); return r; }
      const txt = await r.text();
      let data = null;
      try { data = txt ? JSON.parse(txt) : null; } catch (e) { data = txt; }
      if (!r.ok) throw new ApiError(r.status, (data && data.detail) || txt || r.statusText);
      return data;
    } finally { clearTimeout(t); }
  }

  /* Same bytes as Python json.dumps(obj, sort_keys=True, ensure_ascii=False) for flat objects,
     so evidence items can be re-hashed in the browser and checked against the backend's SHA-256. */
  function pyJson(obj) {
    const val = (v) => (v === null || v === undefined) ? 'null' : JSON.stringify(v);
    return '{' + Object.keys(obj).sort().map((k) => JSON.stringify(k) + ': ' + val(obj[k])).join(', ') + '}';
  }

  return {
    base, ApiError, pyJson,
    get: (p, o) => req('GET', p, undefined, o),
    post: (p, b, o) => req('POST', p, b, o),
    patch: (p, b) => req('PATCH', p, b),
    del: (p) => req('DELETE', p),
    raw: (method, p) => req(method, p, undefined, { raw: true }),
    hasKey: () => !!store.get('ss_key')
  };
})();
