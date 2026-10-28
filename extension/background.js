/* SafeSphere Guard service worker: the only part that talks to the backend.
   Config in chrome.storage.local: api (default http://localhost:8000), key (sent as X-API-Key when set). */
const DEFAULT_API = 'http://localhost:8000';
const BADGE = { high: '#e2622b', critical: '#d6264f' };
const alertCount = {};   // tabId -> number of alerts shown
let chain = Promise.resolve();   // ingests run one after another so timelines stay in order

async function config() {
  const c = await chrome.storage.local.get({ api: DEFAULT_API, key: '' });
  return { api: (c.api || DEFAULT_API).replace(/\/$/, ''), key: c.key };
}

async function call(method, path, body) {
  const { api, key } = await config();
  const headers = {};
  if (key) headers['X-API-Key'] = key;
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  const r = await fetch(api + path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  const txt = await r.text();
  let data = null;
  try { data = txt ? JSON.parse(txt) : null; } catch (e) { data = txt; }
  if (!r.ok) {
    const err = new Error((data && data.detail) || txt || r.statusText);
    err.status = r.status;
    throw err;
  }
  return data;
}

function notify(tabId, alerts) {
  for (const a of alerts) {
    chrome.notifications.create('ssg-' + a.id, {
      type: 'basic', iconUrl: 'icons/icon128.png', priority: 2,
      title: 'SafeSphere Guard · ' + a.level.toUpperCase(), message: a.summary,
    });
  }
  if (tabId == null || !alerts.length) return;
  alertCount[tabId] = (alertCount[tabId] || 0) + alerts.length;
  const worst = alerts.some((a) => a.level === 'critical') ? 'critical' : 'high';
  chrome.action.setBadgeText({ tabId, text: String(alertCount[tabId]) });
  chrome.action.setBadgeBackgroundColor({ tabId, color: BADGE[worst] });
}

const err = (e) => ({ ok: false, error: { name: e.name, message: e.message, status: e.status } });

chrome.runtime.onMessage.addListener((msg, sender, reply) => {
  const tabId = sender.tab ? sender.tab.id : null;
  if (msg.type === 'ingest') {
    chain = chain.then(() => call('POST', '/ingest/notification', msg.items))
      .then((data) => { notify(tabId, data.new_alerts || []); reply({ ok: true, data }); })
      .catch((e) => reply(err(e)));
  } else if (msg.type === 'feedback') {
    call('POST', '/feedback', { person_id: msg.pid, kind: 'not_harassment' })
      .then((data) => reply({ ok: true, data })).catch((e) => reply(err(e)));
  } else if (msg.type === 'report') {
    config().then(({ api }) => { chrome.tabs.create({ url: api + '/report/' + encodeURIComponent(msg.pid) + '.pdf' }); reply({ ok: true }); });
  } else if (msg.type === 'reset-tab') {
    if (tabId != null) { alertCount[tabId] = 0; chrome.action.setBadgeText({ tabId, text: '' }); }
    reply({ ok: true });
  } else {
    reply({ ok: false, error: { message: 'unknown message ' + msg.type } });
  }
  return true;   // reply is async
});
