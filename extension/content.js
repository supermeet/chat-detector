/* SafeSphere Guard content script: reads the chat page, sends messages aimed at the user to the engine
   (through background.js), blurs flagged messages once behaviour confirms harm, and shows guidance. */
(function () {
  const C = self.SSGCore;

  /* Site adapter for the simulated chatroom (chatroom/). A real site gets its own adapter with the same shape. */
  const ADAPTER = {
    root: () => document.querySelector('main#room'),
    list: () => document.querySelector('ol#messages'),
    isMessage: (n) => n.nodeType === 1 && n.matches('li.msg'),
    parse(node, root) {
      const text = node.querySelector('.msg-text');
      const media = node.querySelector('.msg-media');
      const time = node.querySelector('time[datetime]');
      return { room: root.dataset.room, senderId: node.dataset.senderId,
        senderName: (node.querySelector('.msg-sender') || {}).textContent || node.dataset.senderId,
        isSelf: node.hasAttribute('data-self'), text: text ? text.textContent : '',
        time: time ? time.getAttribute('datetime') : null, replyTo: node.dataset.replyTo || null,
        media: media ? media.dataset.kind : null };
    },
  };

  let ctx = null, people = {}, tracked = [], cards = {}, checked = 0;
  let host, shadow, statusEl, cardsEl;

  function newCtx(root) {
    return { room: root.dataset.room, selfName: root.dataset.selfName, selfId: root.dataset.selfId, members: {}, lastTargeter: null };
  }

  const send = (msg) => new Promise((res) => chrome.runtime.sendMessage(msg, res));

  /* ---------------- panel (shadow DOM so the page's CSS can't touch it) ---------------- */
  function el(tag, cls, text) { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; }

  function mountPanel() {
    host = document.createElement('div');
    host.id = 'safesphere-guard';
    shadow = host.attachShadow({ mode: 'open' });
    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = chrome.runtime.getURL('panel.css');
    shadow.appendChild(link);
    const box = el('section', 'panel');
    const head = el('header', 'head');
    head.appendChild(el('span', 'dot'));
    head.appendChild(el('strong', null, 'SafeSphere Guard'));
    statusEl = el('span', 'status', 'Monitoring this room');
    head.appendChild(statusEl);
    box.appendChild(head);
    cardsEl = el('div', 'cards');
    box.appendChild(cardsEl);
    shadow.appendChild(box);
    document.documentElement.appendChild(host);
  }

  function setStatus(text, isError) {
    statusEl.textContent = text;
    host.classList.toggle('error', !!isError);
    shadow.querySelector('.panel').classList.toggle('error', !!isError);
  }

  /* one card per person; it follows the person's current level and behaviour type */
  function showCard(alert) {
    const entry = cards[alert.person_id];
    if (entry) { entry.alert = alert; renderCard(entry); return; }
    const card = el('article', 'card');
    card.dataset.personId = alert.person_id;
    cards[alert.person_id] = { alert, card, resolved: false };
    renderCard(cards[alert.person_id]);
    cardsEl.prepend(card);
  }

  function refreshCards() {
    for (const entry of Object.values(cards)) if (!entry.resolved && people[entry.alert.person_id]) renderCard(entry);
  }

  function renderCard(entry) {
    if (entry.resolved) return;
    const alert = C.currentAlert(entry.alert, people[entry.alert.person_id]);
    const g = C.guidance(alert, Object.values(people));
    const card = entry.card;
    card.className = 'card ' + alert.level;
    card.style.order = (people[alert.person_id] || {}).is_room ? '-1' : '0';   // the room-wide pile-on leads
    card.dataset.alertId = String(alert.id);
    card.textContent = '';
    const top = el('div', 'top');
    top.appendChild(el('span', 'badge', alert.level.toUpperCase()));
    top.appendChild(el('h3', null, g.title));
    card.appendChild(top);
    if (g.body.length) {
      card.appendChild(el('p', 'why', 'Why we think so'));
      const ul = el('ul', 'reasons');
      g.body.forEach((r) => ul.appendChild(el('li', null, r)));
      card.appendChild(ul);
    }
    card.appendChild(el('p', 'why', 'What to do now'));
    const ol = el('ol', 'steps');
    g.steps.forEach((s) => ol.appendChild(el('li', null, s)));
    card.appendChild(ol);
    const actions = el('div', 'actions');
    const report = el('button', 'primary', 'Generate evidence pack');
    report.addEventListener('click', () => send({ type: 'report', pid: alert.person_id }));
    const safe = el('button', null, 'Not harassment');
    safe.addEventListener('click', async () => {
      const r = await send({ type: 'feedback', pid: alert.person_id });
      if (!r || !r.ok) { setStatus(C.describeError(r && r.error), true); return; }
      people[r.data.id] = r.data;
      entry.resolved = true;
      card.classList.add('resolved');
      card.querySelector('h3').textContent = 'Marked as not harassment: ' + r.data.display_name;
      actions.remove();
      applyBlur();
    });
    const dismiss = el('button', 'ghost', 'Dismiss');
    dismiss.addEventListener('click', () => { entry.resolved = true; card.remove(); });
    actions.append(report, safe, dismiss);
    card.appendChild(actions);
  }

  /* ---------------- blur ---------------- */
  function injectPageStyle() {
    const s = document.createElement('style');
    s.id = 'ssg-page-style';
    s.textContent = '.ssg-blur .msg-text,.ssg-blur .msg-media{filter:blur(7px);user-select:none}' +
      '.ssg-blur{cursor:pointer}.ssg-note{display:none;font-size:11px;color:#8a3a14;margin-top:2px}' +
      '.ssg-blur .ssg-note{display:block}';
    document.head.appendChild(s);
  }

  function applyBlur() {
    const list = Object.values(people);
    for (const t of tracked) {
      if (t.revealed || !t.node.isConnected) continue;
      const lv = C.levelsFor(list, t.senderId, ctx.room);
      const blur = C.shouldBlur(t.flagged, lv.member, lv.roomLevel);
      if (blur && !t.node.classList.contains('ssg-blur')) {
        t.node.classList.add('ssg-blur');
        if (!t.node.querySelector('.ssg-note')) {
          const note = el('div', 'ssg-note', 'Hidden by SafeSphere Guard · tap to view');
          (t.node.querySelector('.bubble') || t.node).appendChild(note);
        }
      } else if (!blur) {
        t.node.classList.remove('ssg-blur');
      }
    }
  }

  document.addEventListener('click', (e) => {
    const node = e.target.closest && e.target.closest('li.ssg-blur');
    if (!node) return;
    const t = tracked.find((x) => x.node === node);
    if (t) t.revealed = true;
    node.classList.remove('ssg-blur');
  }, true);

  /* ---------------- reading the page ---------------- */
  async function process(nodes) {
    const root = ADAPTER.root();
    if (!ctx || ctx.room !== root.dataset.room) ctx = newCtx(root);
    const items = [], owners = [];
    for (const node of nodes) {
      if (node.dataset.ssgSeen) continue;
      node.dataset.ssgSeen = '1';
      const rec = ADAPTER.parse(node, root);
      const n = C.toNotification(rec, ctx);
      if (!n) continue;
      items.push(n);
      owners.push({ node, senderId: rec.isSelf ? null : rec.senderId, flagged: false, revealed: false });
    }
    if (!items.length) return;
    const r = await send({ type: 'ingest', items });
    if (!r || !r.ok) { setStatus(C.describeError(r && r.error), true); return; }
    checked += items.length;
    setStatus('Monitoring ' + ctx.room + ' · ' + checked + ' messages aimed at you checked');
    r.data.labels.forEach((lab, i) => { owners[i].flagged = !!lab.flagged; });
    tracked.push(...owners.filter((o) => o.senderId));
    for (const p of r.data.people) people[p.id] = p;
    applyBlur();
    refreshCards();
    for (const a of r.data.new_alerts) showCard(a);
  }

  function resetForNewScenario() {
    ctx = null; people = {}; tracked = []; cards = {}; checked = 0;
    cardsEl.textContent = '';
    setStatus('Monitoring this room');
    send({ type: 'reset-tab' });
  }

  async function start() {
    const { enabled } = await chrome.storage.local.get({ enabled: true });
    const root = ADAPTER.root(), list = ADAPTER.list();
    if (!enabled || !root || !list) return;
    mountPanel();
    injectPageStyle();
    // the observer callback is the batch: messages added together are sent together, in page order
    let queue = Promise.resolve();
    new MutationObserver((muts) => {
      const added = [];
      let cleared = false;
      for (const m of muts) {
        m.addedNodes.forEach((n) => { if (ADAPTER.isMessage(n)) added.push(n); });
        if (m.removedNodes.length && !list.children.length) cleared = true;
      }
      if (cleared) queue = queue.then(resetForNewScenario);
      if (added.length) queue = queue.then(() => process(added));
    }).observe(list, { childList: true });
    const existing = Array.from(list.children).filter(ADAPTER.isMessage);
    if (existing.length) queue = queue.then(() => process(existing));
  }

  start();
})();
