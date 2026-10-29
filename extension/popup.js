const $ = (id) => document.getElementById(id);
const DEFAULT_API = 'http://localhost:8000';

async function cfg() {
  const c = await chrome.storage.local.get({ api: DEFAULT_API, key: '', enabled: true });
  c.api = (c.api || DEFAULT_API).replace(/\/$/, '');
  return c;
}

async function call(method, path) {
  const c = await cfg();
  const r = await fetch(c.api + path, { method, headers: c.key ? { 'X-API-Key': c.key } : {} });
  if (!r.ok) throw new Error(r.status + ' ' + r.statusText);
  return r.json();
}

async function refresh() {
  const c = await cfg();
  $('enabled').checked = c.enabled;
  $('api').value = c.api;
  $('dash').href = c.api + '/';
  try {
    const h = await call('GET', '/health');
    $('conn').textContent = h.model.ready ? 'Connected · model ' + h.model.version : 'Connected, but the model is not loaded';
  } catch (e) {
    $('conn').textContent = 'Backend not reachable at ' + c.api;
    return;
  }
  const alerts = await call('GET', '/alerts');
  const ul = $('alerts');
  ul.textContent = '';
  if (!alerts.length) { const li = document.createElement('li'); li.className = 'muted'; li.textContent = 'None yet'; ul.appendChild(li); }
  alerts.slice(0, 5).forEach((a) => {
    const li = document.createElement('li');
    const lv = document.createElement('span');
    lv.className = 'lv ' + a.level;
    lv.textContent = a.level.toUpperCase();
    li.append(lv, document.createTextNode(a.summary));
    ul.appendChild(li);
  });
}

$('enabled').addEventListener('change', (e) => chrome.storage.local.set({ enabled: e.target.checked }));
$('save').addEventListener('click', async () => { await chrome.storage.local.set({ api: $('api').value.trim() || DEFAULT_API }); refresh(); });
$('clear').addEventListener('click', async () => {
  try { await call('DELETE', '/data'); } catch (e) { $('conn').textContent = 'Could not clear: ' + e.message; return; }
  refresh();
});
refresh();
