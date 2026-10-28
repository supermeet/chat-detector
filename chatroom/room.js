/* Huddle: a simulated group chat that plays a room script from /demo/rooms/{name}.
   It renders messages only. Detection happens in the SafeSphere Guard extension, which reads this DOM.
   Query params (for tests): ?scenario=pile_on&mode=scripted|live&speed=fast&autostart=1 */
(function () {
  const $ = (id) => document.getElementById(id);
  const room = $('room'), list = $('messages'), input = $('input'), status = $('status');
  const qs = new URLSearchParams(location.search);
  const DELAY = { slow: 2600, normal: 1400, fast: 120 };
  const MEDIA = { image: '📷 Photo', video: '🎥 Video', audio: '🎤 Voice message' };
  const COLORS = ['#e2622b', '#2f9e6e', '#7b4ae2', '#c98a00', '#d6264f', '#1f7ae0', '#5b6475'];

  let sc = null, run = 0, lastTs = null, replyTo = null, waiting = null, nextId = 1;

  function color(id) { let h = 0; for (const c of id) h = (h * 31 + c.charCodeAt(0)) >>> 0; return COLORS[h % COLORS.length]; }
  function nameOf(id) { return id === sc.self.id ? sc.self.name : (sc.members[id] || id); }
  function fmt(iso) {
    const d = new Date(iso);
    return d.toLocaleDateString([], { weekday: 'short' }) + ' ' + d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
  }
  function plusMinute(iso) {   // scenario clock for messages typed outside the script (local wall-clock ISO)
    const d = new Date(new Date(iso).getTime() + 60000), p = (n) => String(n).padStart(2, '0');
    return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate()) + 'T' + p(d.getHours()) + ':' + p(d.getMinutes()) + ':00';
  }
  function setState(s) { room.dataset.state = s; }
  function el(tag, cls, text) { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; }

  function textWithMentions(text) {
    const frag = document.createDocumentFragment();
    String(text).split(/(@[\w.]+)/).forEach((part) => {
      frag.appendChild(part.startsWith('@') ? el('span', 'mention', part) : document.createTextNode(part));
    });
    return frag;
  }

  /* DOM contract read by the extension: li.msg[data-msg-id][data-sender-id][data-self?][data-reply-to?]
     > .msg-sender, time[datetime], .msg-text, .msg-media[data-kind] */
  function render(ev) {
    const from = ev.from === 'self' ? sc.self.id : ev.from;
    const li = el('li', 'msg');
    li.dataset.msgId = String(nextId++);
    li.dataset.senderId = from;
    if (ev.from === 'self') li.dataset.self = '';
    const rt = ev.reply_to === 'self' ? sc.self.id : ev.reply_to;
    if (rt) li.dataset.replyTo = rt;
    const av = el('div', 'avatar', nameOf(from).slice(0, 1).toUpperCase());
    av.style.background = color(from);
    const b = el('div', 'bubble');
    const meta = el('div', 'meta');
    meta.appendChild(el('span', 'msg-sender', nameOf(from)));
    const t = el('time', null, fmt(ev.timestamp));
    t.setAttribute('datetime', ev.timestamp);
    meta.appendChild(t);
    const rb = el('button', 'reply-btn', '↩ Reply');
    rb.type = 'button';
    rb.addEventListener('click', () => setReply(from === sc.self.id ? null : from));
    meta.appendChild(rb);
    b.appendChild(meta);
    if (rt) b.appendChild(el('div', 'quote', 'Replying to ' + nameOf(rt)));
    if (ev.text) { const p = el('div', 'msg-text'); p.appendChild(textWithMentions(ev.text)); b.appendChild(p); }
    if (ev.media) { const m = el('div', 'msg-media', MEDIA[ev.media] || ev.media); m.dataset.kind = ev.media; b.appendChild(m); }
    li.appendChild(av);
    li.appendChild(b);
    list.appendChild(li);
    list.scrollTop = list.scrollHeight;
    lastTs = ev.timestamp;
  }

  function setReply(id) {
    replyTo = id;
    $('replying').hidden = !id;
    $('replying').querySelector('span').textContent = id ? 'Replying to ' + nameOf(id) : '';
  }

  function renderMembers() {
    const ul = $('member-list');
    ul.textContent = '';
    [sc.self.id].concat(Object.keys(sc.members)).forEach((id) => {
      const li = el('li');
      const av = el('div', 'avatar', nameOf(id).slice(0, 1).toUpperCase());
      av.style.background = color(id);
      li.appendChild(av);
      li.appendChild(el('span', null, nameOf(id) + (id === sc.self.id ? ' (you)' : '')));
      ul.appendChild(li);
    });
  }

  async function load(name) {
    run++;
    const r = await fetch('/demo/rooms/' + encodeURIComponent(name));
    if (!r.ok) { status.textContent = 'Could not load scenario "' + name + '"'; return; }
    sc = await r.json();
    list.textContent = '';
    lastTs = null; waiting = null; nextId = 1;
    setReply(null);
    room.dataset.room = sc.room;
    room.dataset.selfName = sc.self.name;
    room.dataset.selfId = sc.self.id;
    $('room-name').textContent = sc.room;
    $('scenario-title').textContent = sc.title;
    renderMembers();
    input.classList.remove('waiting');
    input.value = '';
    status.textContent = 'Ready. Press Start.';
    setState('idle');
  }

  const sleep = (ms) => new Promise((res) => setTimeout(res, ms));

  async function play() {
    const my = ++run;
    const live = $('mode').value === 'live';
    const delay = DELAY[$('speed').value] || DELAY.normal;
    $('start').disabled = true;
    setState('playing');
    for (const ev of sc.events) {
      await sleep(delay);
      if (my !== run) return;
      if (ev.from === 'self' && live) {
        setState('waiting');
        status.textContent = 'Your turn: send the suggested reply (or type your own).';
        input.value = ev.text || '';
        input.classList.add('waiting');
        setReply(ev.reply_to || null);
        input.focus();
        const typed = await new Promise((res) => { waiting = res; });
        if (my !== run) return;
        input.classList.remove('waiting');
        setState('playing');
        render(Object.assign({}, ev, { text: typed }));
        continue;
      }
      render(ev);
      status.textContent = '';
    }
    $('start').disabled = false;
    status.textContent = 'Scenario finished. You can keep typing.';
    setState('done');
  }

  $('composer').addEventListener('submit', (e) => {
    e.preventDefault();
    const text = input.value.trim();
    if (!text || !sc) return;
    input.value = '';
    if (waiting) { const w = waiting; waiting = null; w(text); return; }
    render({ from: 'self', text, reply_to: replyTo || undefined, timestamp: lastTs ? plusMinute(lastTs) : sc.events[0].timestamp });
    setReply(null);
  });
  $('cancel-reply').addEventListener('click', () => setReply(null));
  $('start').addEventListener('click', () => { if (room.dataset.state !== 'idle') load($('scenario').value).then(play); else play(); });
  $('reset').addEventListener('click', () => { $('start').disabled = false; load($('scenario').value); });
  $('scenario').addEventListener('change', () => { $('start').disabled = false; load($('scenario').value); });

  (async function init() {
    const rooms = await (await fetch('/demo/rooms')).json();
    rooms.forEach((r) => { const o = el('option', null, r.title); o.value = r.name; $('scenario').appendChild(o); });
    if (qs.get('scenario')) $('scenario').value = qs.get('scenario');
    if (qs.get('mode')) $('mode').value = qs.get('mode');
    if (qs.get('speed')) $('speed').value = qs.get('speed');
    await load($('scenario').value);
    if (qs.get('autostart') === '1') play();
  })();
})();
