

class Component extends DCLogic {
  constructor(props) {
    super(props);
    this.timers = [];
    this.lastSender = {};
    this.D = this.makeData();
    this.state = this.initialState();
  }

  /* ================= backend (live mode) =================
     On load we call /health. If the backend and model are up, every screen uses the API and the scripted chats
     stream through the real model. Otherwise the original mock data runs ("Demo mode"). */
  componentDidMount() { this.connect(); }

  async connect() {
    this.setState({ conn: Object.assign({}, this.state.conn, { status: 'checking' }) });
    try {
      const h = await SSApi.get('/health', { timeout: 5000 });
      if (!h.model || !h.model.ready) throw new Error((h.model && h.model.error) || 'behaviour model not loaded');
      this.stopTimers();
      this.lastSender = {};
      this.setState({
        live: true, people: {}, sel: null, feed: [], alerts: [], idx: 0, running: false, unread: 0, packs: 0,
        panicPid: null, linkSugg: [], evLive: {}, details: {},
        ev: Object.assign({}, this.state.ev, { pid: null, generated: false, hashes: {}, fp: '', verify: '' }),
        imp: Object.assign({}, this.state.imp, { link: 'new' }),
        conn: { status: 'online', model: h.model.version || '', deepfake: (h.deepfake && h.deepfake.mode) || 'stub', base: SSApi.base(), error: '' }
      });
      await this.refreshPeople();
      this.loadLiveMetrics();
    } catch (e) {
      this.setState({ live: false, conn: { status: 'offline', base: SSApi.base(), error: String((e && e.message) || e) } });
    }
  }

  liveFail(e, what) {
    const msg = (e && e.message) || String(e);
    if (e && e.name === 'TypeError') {   // network error: backend went away
      this.setState({ live: false, conn: Object.assign({}, this.state.conn, { status: 'offline', error: msg }) });
      this.showToast('Lost the connection to the backend. Switched to demo mode.', { label: 'Retry', action: () => this.connect() });
    } else {
      this.showToast((what ? what + ': ' : '') + msg);
    }
  }

  LABELS() {
    return { safe_mutual: 'Mutual', banter: 'Banter', normal_frequent: 'Normal contact', unreciprocated: 'Unreciprocated',
      stalking: 'Stalking', harassment_after_no: 'Ignored "no"', group_bullying: 'Bullying', sextortion: 'Sextortion' };
  }
  appCode(a) { return { wa: 'WA', ig: 'IG', tg: 'TG', sms: 'SMS', snap: 'SNAP', fb: 'SMS' }[a] || 'SMS'; }
  localIso(d) { const p = (n) => String(n).padStart(2, '0'); return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate()) + 'T' + p(d.getHours()) + ':' + p(d.getMinutes()) + ':' + p(d.getSeconds()); }
  fmtTime(iso) { if (!iso) return ''; const d = new Date(iso); return d.toLocaleDateString([], { day: 'numeric', month: 'short' }) + ', ' + d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }); }
  fmtDate(iso) { return iso ? new Date(iso).toLocaleDateString([], { day: 'numeric', month: 'short' }) : ''; }
  pSev(p) { return (p && p.level) || this.sevOf(p ? p.risk : 0); }
  emptyPerson() {
    return { id: '', name: 'No one yet', initials: '–', rel: 'Stranger', risk: 0, level: 'info', tags: [], tagline: '', accounts: [],
      timeline: [{ phase: 'Neutral', w: 100, date: '', tip: 'No messages yet' }], reasons: [], features: [],
      activity: new Array(14).fill(0), night: new Array(14).fill(0), history: [] };
  }

  /* backend person view (+ optional detail and messages) -> the shape the template expects */
  mapPerson(v, old, d, msgs) {
    const L = this.LABELS();
    const PH = { mutual: 'Mutual', unreciprocated: 'Unreciprocated', rejected: 'Rejected', violation: 'Violation', neutral: 'Neutral' };
    const name = v.display_name || 'Unknown';
    const words = name.replace(/[^A-Za-z0-9 ]/g, ' ').trim().split(/\s+/).filter(Boolean);
    const initials = (words.length > 1 ? words[0][0] + words[1][0] : (words[0] || '?').slice(0, 2)).toUpperCase();
    const level = v.level || 'info';
    const base = old || this.emptyPerson();
    const p = Object.assign({}, base, {
      id: v.id, name, initials, live: true, level,
      rel: (v.relationship || 'stranger').replace(/^./, (c) => c.toUpperCase()),
      risk: Math.round((v.risk || 0) * 100), safe: !!v.trusted, nMsgs: v.n_messages || 0, label: v.label,
      early: !!v.early,
      tags: (v.early ? ['Early: watching'] : [L[v.label] || 'New']).concat((v.accounts || []).length > 1 ? ['Multiple accounts'] : []).concat(v.trusted ? ['Marked safe'] : []),
      tagline: v.early ? 'Too few messages to judge a pattern yet' + ((v.reasons || [])[0] ? ': ' + v.reasons[0].toLowerCase() : '') : ((v.reasons || [])[0] || (L[v.label] ? L[v.label] + ' pattern' : 'Not enough messages yet')),
      accounts: (v.accounts || []).map((a, i) => ({ app: this.appCode(a.app), handle: a.handle, label: i === 0 ? 'Primary' : 'Linked by you',
        reason: 'First seen ' + this.fmtTime(a.first_seen) + ' · last ' + this.fmtTime(a.last_seen), status: i === 0 ? 'primary' : 'confirmed', accountId: a.id }))
    });
    const reasons = level === 'info' ? ((d && d.reasons_down) || []) : (v.reasons || []);
    if (d || level !== 'info') p.reasons = reasons.map((r) => ({ pre: r, bold: '', post: '' }));
    if (d) {
      const f = d.facts || {};
      const num = (x, k) => (x === null || x === undefined) ? null : k(x);
      p.features = [
        ['Messages per day', num(f.msgs_per_day, (x) => x.toFixed(1))],
        ['Your reply ratio', num(f.reply_ratio, (x) => x.toFixed(2))],
        ['Messages after "no"', num(f.msgs_after_reject, (x) => String(Math.round(x)))],
        ['Longest run without a reply', num(f.unanswered_streak_max, (x) => String(Math.round(x)))],
        ['Night-time share (12–5 am)', num(f.night_ratio, (x) => Math.round(x * 100) + '%')],
        ['Accounts used', num(f.accounts_count, (x) => String(Math.round(x)))],
        ['Readable messages', num(d.text_available_ratio, (x) => Math.round(x * 100) + '%')]
      ].filter((x) => x[1] !== null).map((x) => ({ k: x[0], v: x[1] }));
      const tl = d.consent_timeline || [];
      if (tl.length) {
        const t0 = new Date(tl[0].start).getTime();
        const tEnd = msgs && msgs.length ? new Date(msgs[msgs.length - 1].timestamp).getTime() : Date.now();
        p.timeline = tl.map((ph, i) => {
          const s = new Date(ph.start).getTime(), e = i + 1 < tl.length ? new Date(tl[i + 1].start).getTime() : tEnd;
          const extra = ph.messages_after_no ? ' · ' + ph.messages_after_no + ' messages after you said no' : '';
          return { phase: PH[ph.phase] || 'Neutral', w: Math.max(8, Math.round(((e - s) / Math.max(1, tEnd - t0)) * 100)), date: this.fmtDate(ph.start), tip: this.fmtTime(ph.start) + ': ' + (PH[ph.phase] || ph.phase) + extra };
        });
      }
    }
    if (msgs) {
      const day = 86400000, end = new Date(); end.setHours(23, 59, 59, 999);
      const act = new Array(14).fill(0), night = new Array(14).fill(0);
      msgs.forEach((m) => {
        if (m.is_user || m.event !== 'message') return;
        const t = new Date(m.timestamp), k = 13 - Math.floor((end - t) / day);
        if (k >= 0 && k < 14) { act[k]++; if (t.getHours() < 5) night[k]++; }
      });
      p.activity = act; p.night = night;
      p.history = msgs.slice(-12).map((m) => ({
        app: m.is_user ? 'YOU' : this.appCode(m.app), mine: m.is_user, flag: !!m.flagged, time: this.fmtTime(m.timestamp),
        text: m.event === 'block' ? '[You blocked this account]' : (m.text || '[Preview hidden: scored from timing only]')
      }));
    }
    return p;
  }

  async refreshPeople(detailId) {
    try {
      const [list, sugg] = await Promise.all([SSApi.get('/people'), SSApi.get('/links/suggestions')]);
      const people = {};
      list.forEach((v) => { people[v.id] = this.mapPerson(v, this.state.people[v.id]); });
      const sel = people[this.state.sel] ? this.state.sel : (list[0] ? list[0].id : null);
      this.setState({ people, linkSugg: sugg || [], sel }, () => { const id = detailId || this.state.sel; if (id && people[id]) this.loadPersonDetail(id); });
    } catch (e) { this.liveFail(e, 'Could not load people'); }
  }

  async loadPersonDetail(id) {
    try {
      const [d, msgs] = await Promise.all([SSApi.get('/people/' + id), SSApi.get('/people/' + id + '/messages?limit=500')]);
      const np = Object.assign({}, this.state.people);
      np[id] = this.mapPerson(d, np[id], d, msgs);
      this.setState({ people: np, details: Object.assign({}, this.state.details, { [id]: d }) });
      return d;
    } catch (e) { if (e && e.status !== 404) this.liveFail(e, 'Could not load this person'); return null; }
  }

  selectPerson(id) { this.setState({ sel: id }); if (this.state.live && id) this.loadPersonDetail(id); }

  /* account-link suggestions for one person, shown as "pending" accounts */
  pendingLinks(pid) {
    return (this.state.linkSugg || []).filter((s) => s.person_id === pid || s.other_person_id === pid).map((s) => {
      const other = s.person_id === pid ? s.other_person_id : s.person_id;
      const op = this.state.people[other];
      const acc = op && op.accounts[0];
      return acc ? { app: acc.app, handle: acc.handle, label: 'Linked ' + Math.round(s.score * 100) + '%', reason: (s.reasons || []).join('. ') || 'Similar to this person', status: 'pending', otherId: other } : null;
    }).filter(Boolean);
  }

  makeData() {
    const SEV = {
      info: { label: 'Info', cls: 'sev-info', fill: 'fill-info', border: 'bl-info' },
      warn: { label: 'Warn', cls: 'sev-warn', fill: 'fill-warn', border: 'bl-warn' },
      high: { label: 'High', cls: 'sev-high', fill: 'fill-high', border: 'bl-high' },
      critical: { label: 'Critical', cls: 'sev-critical', fill: 'fill-critical', border: 'bl-critical' }
    };
    const PHASE = { Neutral: '#93A4B7', Mutual: '#2f9e6e', Unreciprocated: '#c98a00', Rejected: '#e2622b', Violation: '#d6264f' };
    const APPN = { WA: 'WhatsApp', IG: 'Instagram', TG: 'Telegram', SMS: 'SMS', SNAP: 'Snapchat', YOU: 'You' };
    const people = {
      tg: { id: 'tg', name: 'Unknown (Telegram)', initials: '?', rel: 'Stranger', risk: 96, tags: ['Sextortion', 'Deepfake'], tagline: 'Money demand with an intimate image',
        accounts: [{ app: 'TG', handle: '@night.owl_77', label: 'Primary', reason: 'First contact 14 Oct, 11:02 pm. No mutual contacts. Account is 3 days old.', status: 'primary' }],
        timeline: [{ phase: 'Neutral', w: 8, date: '14 Oct', tip: '14 Oct 11:02 pm: first message' }, { phase: 'Violation', w: 92, date: '14 Oct', tip: '14 Oct 11:04 pm: "Pay ₹20,000 by tonight…"' }],
        reasons: [{ pre: 'Sent an image that is ', bold: 'likely manipulated (88%)', post: ' and matches your face.' }, { pre: 'Demanded ', bold: '₹20,000', post: ' with a deadline.' }, { pre: 'Threatened to send it to ', bold: 'your family and college group', post: '.' }, { pre: 'Stranger account, ', bold: '3 days old', post: ', no mutual contacts.' }],
        features: [{ k: 'Messages in first hour', v: '6' }, { k: 'Your replies', v: '0' }, { k: 'Money mentioned', v: 'Yes · ₹20,000' }, { k: 'Media sent', v: '1 image' }, { k: 'Active hours', v: '11 pm – 1 am' }],
        activity: [0,0,0,0,0,0,0,0,0,0,0,0,0,6], night: [0,0,0,0,0,0,0,0,0,0,0,0,0,1],
        history: [{ app: 'TG', text: 'I have your private photos. Open this.', time: '14 Oct, 11:02 pm', flag: true }, { app: 'TG', text: '[Photo, blurred]', time: '14 Oct, 11:02 pm', flag: true }, { app: 'TG', text: 'Pay ₹20,000 by tonight or this goes to your family and your college group.', time: '14 Oct, 11:04 pm', flag: true }]
      },
      rahul: { id: 'rahul', name: 'Rahul K', initials: 'RK', rel: 'Acquaintance', risk: 84, tags: ['Stalking', 'Unreciprocated'], tagline: 'Back on a new Instagram account',
        accounts: [
          { app: 'WA', handle: '+91 98xxx x4421', label: 'Primary', reason: 'Saved contact since 3 Aug.', status: 'primary' },
          { app: 'IG', handle: '@rahul.k_22', label: 'Linked 91%', reason: 'Same profile photo and the same three phrases he uses on WhatsApp.', status: 'confirmed' },
          { app: 'IG', handle: '@r_k.backup', label: 'Linked 78%', reason: 'Created 2 days after you blocked @rahul.k_22. Messages at the same late-night hours.', status: 'pending' }
        ],
        timeline: [{ phase: 'Neutral', w: 14, date: '3 Aug', tip: '3 Aug: first message' }, { phase: 'Mutual', w: 26, date: '10 Aug', tip: '10 Aug: both of you chatting daily' }, { phase: 'Unreciprocated', w: 26, date: '28 Sep', tip: '28 Sep: you stopped replying' }, { phase: 'Rejected', w: 14, date: '12 Oct', tip: '12 Oct: you said "please stop messaging me"' }, { phase: 'Violation', w: 20, date: '13 Oct', tip: '13 Oct: 41 messages after you said no' }],
        reasons: [{ pre: 'Sent ', bold: '41 messages after you said "please stop"', post: ' on 12 Oct.' }, { pre: 'Mentioned ', bold: 'where you were and what you wore', post: ' today.' }, { pre: 'Came back on ', bold: 'a new Instagram account', post: ' 2 days after you blocked him.' }, { pre: 'Most messages sent ', bold: 'after 11 pm', post: '.' }],
        features: [{ k: 'Messages per day (last 7 days)', v: '23' }, { k: 'Your reply ratio', v: '0.04' }, { k: 'Messages after "no"', v: '41' }, { k: 'Night-time share', v: '68%' }, { k: 'Accounts used', v: '3' }],
        activity: [2,3,1,4,2,0,1,3,6,9,14,22,31,27], night: [0,0,0,1,0,0,0,1,2,4,8,15,22,19],
        history: [{ app: 'WA', text: 'good morning :)', time: '10 Aug, 8:12 am', flag: false }, { app: 'YOU', text: 'please stop messaging me', time: '12 Oct, 9:52 pm', flag: false, mine: true }, { app: 'WA', text: 'Saw you at the café near your college today. Blue kurta suits you.', time: '14 Oct, 6:05 pm', flag: true }, { app: 'IG', text: "you can block me but you can't get rid of me", time: '14 Oct, 11:31 pm', flag: true }]
      },
      arjun: { id: 'arjun', name: 'Arjun M', initials: 'AM', rel: 'Classmate', risk: 48, tags: ['Bullying', 'Slang'], tagline: 'Insults in the class group',
        accounts: [{ app: 'WA', handle: 'Class 12-B group (48 members)', label: 'Primary', reason: 'Group member since June.', status: 'primary' }],
        timeline: [{ phase: 'Neutral', w: 70, date: 'Jun', tip: 'June: joined the class group' }, { phase: 'Unreciprocated', w: 30, date: '11 Oct', tip: '11 Oct: started posting about you' }],
        reasons: [{ pre: 'Used ', bold: '"ch@pri"', post: ' (normalised to a slang insult) about you.' }, { pre: 'Posted in a ', bold: '48-member group', post: ', not privately.' }, { pre: '', bold: '3 posts in 4 days', post: ' target you.' }],
        features: [{ k: 'Posts about you (4 days)', v: '3' }, { k: 'Audience size', v: '48' }, { k: 'Slang terms matched', v: '2' }],
        activity: [0,0,0,0,0,0,0,0,0,0,1,0,1,1], night: [0,0,0,0,0,0,0,0,0,0,0,0,0,0],
        history: [{ app: 'WA', text: 'lol look at her pic, total ch@pri', time: '14 Oct, 4:40 pm', flag: true }]
      },
      vikram: { id: 'vikram', name: 'Vikram S', initials: 'VS', rel: 'Classmate', risk: 30, tags: ['Ignored "no"', 'Stalking', 'Threat'], tagline: 'Kept messaging after you said no 3 times',
        accounts: [
          { app: 'IG', handle: '@vikram.s_07', label: 'Primary', reason: 'Same college. Follows 3 of your friends.', status: 'primary' },
          { app: 'WA', handle: '+91 99xxx x7310', label: 'Linked 84%', reason: 'Started messaging 10 minutes after you blocked @vikram.s_07. Uses the same phrases ("tum meri ho").', status: 'pending' }
        ],
        timeline: [{ phase: 'Neutral', w: 12, date: '9:02 pm', tip: '9:02 pm: first message' }, { phase: 'Unreciprocated', w: 14, date: '9:20 pm', tip: '9:20 pm: 3 messages, no reply from you' }, { phase: 'Rejected', w: 10, date: '9:24 pm', tip: '9:24 pm: you said "please stop messaging me"' }, { phase: 'Violation', w: 18, date: '9:31 pm', tip: '9:31 pm: kept messaging after your no' }, { phase: 'Rejected', w: 8, date: '9:44 pm', tip: '9:44 pm: you said "mat karo please"' }, { phase: 'Violation', w: 14, date: '9:56 pm', tip: '9:56 pm: new WhatsApp number' }, { phase: 'Rejected', w: 8, date: '9:58 pm', tip: '9:58 pm: you said "bhaiya please, bas karo"' }, { phase: 'Violation', w: 16, date: '10:03 pm', tip: '10:03 pm: threatened to share your photos' }],
        reasons: [{ pre: 'You said no ', bold: '3 times, in English and Hindi', post: ': "please stop", "mat karo", "bhaiya please".' }, { pre: 'He sent ', bold: '4 messages after your first no', post: ' and never backed off.' }, { pre: 'Said he would ', bold: 'wait outside your hostel', post: '.' }, { pre: 'Switched to ', bold: 'a new WhatsApp number', post: ' after you blocked him.' }, { pre: 'Threatened to ', bold: 'send your photos to everyone', post: '.' }],
        features: [{ k: 'Your refusals', v: '3 (EN + HI)' }, { k: 'Messages after "no"', v: '4' }, { k: 'Your reply ratio (non-refusal)', v: '0' }, { k: 'Accounts used', v: '2' }, { k: 'Threat phrases', v: '"wait karunga", "photos bhej dunga"' }],
        activity: [0,0,0,0,0,1,0,0,2,0,1,0,3,9], night: [0,0,0,0,0,0,0,0,1,0,0,0,2,8],
        history: [{ app: 'IG', text: "why don't you reply? I'm just being friendly yaar", time: '9:20 pm', flag: false }, { app: 'YOU', text: 'please stop messaging me', time: '9:24 pm', flag: false, mine: true }, { app: 'IG', text: 'kal 8 baje tumhare hostel ke bahar wait karunga', time: '9:40 pm', flag: true }, { app: 'YOU', text: 'mat karo please. mujhe baat nahi karni', time: '9:44 pm', flag: false, mine: true }, { app: 'YOU', text: 'bhaiya please, bas karo', time: '9:58 pm', flag: false, mine: true }, { app: 'WA', text: 'bhaiya mat bolo. tum meri ho. nahi maani toh tumhari photos sabko bhej dunga', time: '10:03 pm', flag: true }]
      },
      priya: { id: 'priya', name: 'Priya S', initials: 'PS', rel: 'Friend', risk: 12, tags: ['Mutual banter'], tagline: 'Friendly teasing, both sides',
        accounts: [{ app: 'IG', handle: '@priya.s', label: 'Primary', reason: 'Mutual follow since 2024.', status: 'primary' }, { app: 'WA', handle: '+91 97xxx x1180', label: 'Linked 97%', reason: 'Same name and photo, saved contact.', status: 'confirmed' }],
        timeline: [{ phase: 'Mutual', w: 100, date: 'Since 2024', tip: 'You reply within minutes; both sides joke' }],
        reasons: [{ pre: 'You reply within ', bold: '4 minutes on average', post: '.' }, { pre: 'Teasing words are ', bold: 'returned by you', post: ', so this is banter.' }],
        features: [{ k: 'Messages per day', v: '18' }, { k: 'Your reply ratio', v: '0.96' }, { k: 'Messages after "no"', v: '0' }],
        activity: [12,15,9,20,18,11,14,16,22,13,19,17,15,18], night: [1,2,0,3,1,0,1,2,2,1,1,2,1,2],
        history: [{ app: 'IG', text: "haha that reel was SO you. coffee tomorrow? you're buying", time: '14 Oct, 5:10 pm', flag: false }]
      }
    };
    const script = [
      { app: 'IG', from: 'Vikram S', pid: 'vikram', text: 'hey you looked really nice in class today', sev: 'info', phase: 'Neutral', risk: 30, scen: ['refusal'] },
      { app: 'IG', from: 'Vikram S', pid: 'vikram', text: "why don't you reply? I'm just being friendly yaar", sev: 'warn', cat: 'Unreciprocated', phase: 'Unreciprocated', risk: 42, why: 'Third message in 20 minutes with no reply from you.', scen: ['refusal'] },
      { app: 'IG', from: 'You', pid: 'vikram', mine: true, text: 'please stop messaging me', sev: 'info', phase: 'Rejected', rejectNote: 'A direct refusal in English.', scen: ['refusal'] },
      { app: 'IG', from: 'Vikram S', pid: 'vikram', text: 'come on, ek coffee. itna attitude kyun?', sev: 'high', cat: 'Ignored refusal', phase: 'Violation', risk: 66, why: 'Sent right after you said "please stop". He is pressuring you ("itna attitude kyun") instead of backing off.', scen: ['refusal'] },
      { app: 'IG', from: 'Vikram S', pid: 'vikram', text: 'kal 8 baje tumhare hostel ke bahar wait karunga', sev: 'high', cat: 'Stalking', phase: 'Violation', risk: 78, why: 'Plans to wait outside where you live ("I will wait outside your hostel at 8 tomorrow").', scen: ['refusal'] },
      { app: 'IG', from: 'You', pid: 'vikram', mine: true, text: 'mat karo please. mujhe baat nahi karni', sev: 'info', phase: 'Rejected', rejectNote: 'A direct refusal in Hindi: "mat karo" (don\'t do this) and "mujhe baat nahi karni" (I don\'t want to talk).', scen: ['refusal'] },
      { app: 'WA', from: 'Unknown number', pid: 'vikram', text: 'number mil gaya tumhara :) ab kaise block karogi?', sev: 'high', cat: 'Stalking', phase: 'Violation', risk: 86, why: 'New WhatsApp number, 84% likely to be Vikram S. It started 10 minutes after you blocked him on Instagram ("got your number, how will you block me now?").', scen: ['refusal'] },
      { app: 'WA', from: 'You', pid: 'vikram', mine: true, text: 'bhaiya please, bas karo', sev: 'info', phase: 'Rejected', rejectNote: 'Calling someone "bhaiya" (brother) is a common way to say you are not romantically interested. With "bas karo" (stop it), this is a clear no.', scen: ['refusal'] },
      { app: 'WA', from: 'Vikram S (WhatsApp)', pid: 'vikram', text: 'bhaiya mat bolo. tum meri ho. nahi maani toh tumhari photos sabko bhej dunga', sev: 'critical', cat: 'Threat', phase: 'Violation', risk: 97, why: 'After 3 clear refusals, he rejected "bhaiya", claimed ownership ("tum meri ho") and threatened to send your photos to everyone.', scen: ['refusal'] },
      { app: 'WA', from: 'Mom', pid: null, text: 'Did you eat lunch? Call me when you are free.', sev: 'info', scen: ['full', 'flirt'] },
      { app: 'IG', from: 'Priya S', pid: 'priya', text: "haha that reel was SO you. coffee tomorrow? you're buying", sev: 'info', cat: 'Mutual banter', why: 'Teasing, but you both joke and reply within minutes.', scen: ['full', 'flirt'] },
      { app: 'WA', from: 'Rahul K', pid: 'rahul', text: 'why are you ignoring me. 14 messages and not one reply?', sev: 'warn', cat: 'Unreciprocated', why: '14 messages in 3 hours with no reply from you.', scen: ['full', 'stalker'] },
      { app: 'WA', from: 'Rahul K', pid: 'rahul', text: 'Saw you at the café near your college today. Blue kurta suits you.', sev: 'high', cat: 'Stalking', why: 'Mentions where you were and what you wore, 2 days after you said "please stop".', scen: ['full', 'stalker'] },
      { app: 'SMS', from: 'BlueDart', pid: null, text: 'Your parcel is out for delivery today.', sev: 'info', scen: ['full', 'stalker', 'bullying'] },
      { app: 'IG', from: '@r_k.backup', pid: 'rahul', text: "you can block me but you can't get rid of me", sev: 'high', cat: 'Stalking', why: 'New account, 78% likely to be Rahul K. Created 2 days after you blocked his old one.', scen: ['full', 'stalker'] },
      { app: 'WA', from: 'Arjun M · Class 12-B', pid: 'arjun', text: 'lol look at her pic, total ch@pri', sev: 'warn', cat: 'Bullying', why: '"ch@pri" matches a slang insult. Posted to a 48-member group.', scen: ['full', 'bullying'] },
      { app: 'SNAP', from: 'Snapchat', pid: null, hidden: true, text: '', sev: 'warn', cat: 'Low confidence', why: 'Unknown sender, 2:14 am, 4th message in 10 minutes.', scen: ['full', 'bullying'] },
      { app: 'TG', from: '@night.owl_77', pid: 'tg', text: 'I have your private photos. Open this.', media: true, sev: 'high', cat: 'Sextortion', why: 'Stranger sent an image with a threatening message.', scen: ['full', 'sextortion'] },
      { app: 'TG', from: '@night.owl_77', pid: 'tg', text: 'Pay ₹20,000 by tonight or this goes to your family and your college group.', sev: 'critical', cat: 'Sextortion', why: 'Money demand plus a threat to share an intimate image (likely manipulated, 88%).', scen: ['full', 'sextortion'] },
      { app: 'WA', from: 'Priya S', pid: 'priya', text: 'also send the chem notes pls', sev: 'info', scen: ['full', 'flirt'] },
      { app: 'IG', from: 'Priya S', pid: 'priya', text: "you're such an idiot lol. ok fine I'll buy the coffee", sev: 'info', cat: 'Mutual banter', why: '"idiot" is inside friendly banter you both take part in.', scen: ['flirt'] }
    ];
    const evidence = {
      tg: [
        { time: '14 Oct, 23:02', app: 'TG', acct: '@night.owl_77', text: 'I have your private photos. Open this.', cat: 'Sextortion' },
        { time: '14 Oct, 23:02', app: 'TG', acct: '@night.owl_77', text: 'IMG_0031.jpg · likely manipulated (88%)', cat: 'Deepfake media', media: true },
        { time: '14 Oct, 23:04', app: 'TG', acct: '@night.owl_77', text: 'Pay ₹20,000 by tonight or this goes to your family and your college group.', cat: 'Sextortion' },
        { time: '14 Oct, 23:15', app: 'TG', acct: '@night.owl_77', text: 'Tick tock. 3 hours left.', cat: 'Threat', deleted: true }
      ],
      rahul: [
        { time: '12 Oct, 21:40', app: 'WA', acct: '+91 98xxx x4421', text: "Why won't you talk to me", cat: 'Unreciprocated' },
        { time: '12 Oct, 21:52', app: 'YOU', acct: 'Your reply', text: 'please stop messaging me', cat: 'Rejection (yours)' },
        { time: '13 Oct, 23:10', app: 'WA', acct: '+91 98xxx x4421', text: "I know where you live. Don't make me come there.", cat: 'Threat', deleted: true },
        { time: '14 Oct, 18:05', app: 'WA', acct: '+91 98xxx x4421', text: 'Saw you at the café near your college today. Blue kurta suits you.', cat: 'Stalking' },
        { time: '14 Oct, 23:31', app: 'IG', acct: '@r_k.backup', text: "you can block me but you can't get rid of me", cat: 'Stalking' }
      ],
      arjun: [
        { time: '11 Oct, 13:20', app: 'WA', acct: 'Class 12-B group', text: 'who invited her anyway', cat: 'Bullying' },
        { time: '14 Oct, 16:40', app: 'WA', acct: 'Class 12-B group', text: 'lol look at her pic, total ch@pri', cat: 'Bullying' }
      ],
      vikram: [
        { time: '28 Oct, 21:20', app: 'IG', acct: '@vikram.s_07', text: "why don't you reply? I'm just being friendly yaar", cat: 'Unreciprocated' },
        { time: '28 Oct, 21:24', app: 'YOU', acct: 'Your reply', text: 'please stop messaging me', cat: 'Refusal (yours)' },
        { time: '28 Oct, 21:31', app: 'IG', acct: '@vikram.s_07', text: 'come on, ek coffee. itna attitude kyun?', cat: 'Ignored refusal' },
        { time: '28 Oct, 21:40', app: 'IG', acct: '@vikram.s_07', text: 'kal 8 baje tumhare hostel ke bahar wait karunga', cat: 'Stalking' },
        { time: '28 Oct, 21:44', app: 'YOU', acct: 'Your reply', text: 'mat karo please. mujhe baat nahi karni', cat: 'Refusal (yours)' },
        { time: '28 Oct, 21:56', app: 'WA', acct: '+91 99xxx x7310', text: 'number mil gaya tumhara :) ab kaise block karogi?', cat: 'Stalking' },
        { time: '28 Oct, 21:58', app: 'YOU', acct: 'Your reply', text: 'bhaiya please, bas karo', cat: 'Refusal (yours)' },
        { time: '28 Oct, 22:03', app: 'WA', acct: '+91 99xxx x7310', text: 'bhaiya mat bolo. tum meri ho. nahi maani toh tumhari photos sabko bhej dunga', cat: 'Threat' },
        { time: '28 Oct, 22:05', app: 'WA', acct: '+91 99xxx x7310', text: 'dekh lena kya hota hai', cat: 'Threat', deleted: true }
      ],
      priya: []
    };
    const laws = {
      vikram: [{ s: 'BNS s. 78 · Stalking', d: 'Repeatedly contacting a woman despite clear disinterest. Your three refusals show that disinterest.' }, { s: 'BNS s. 351 · Criminal intimidation', d: 'Threatening to share your photos to scare or force you.' }, { s: 'IT Act s. 66E / 67 · Privacy and explicit content', d: 'Apply if he actually shares private or explicit images of you.' }],
      tg: [{ s: 'BNS s. 308 · Extortion', d: 'Making someone pay by putting them in fear of harm, including harm to reputation.' }, { s: 'IT Act s. 66E · Violation of privacy', d: 'Capturing or sharing private images of a person without consent.' }, { s: 'IT Act s. 67A · Sexually explicit material', d: 'Publishing or sending sexually explicit material electronically.' }, { s: 'BNS s. 351 · Criminal intimidation', d: 'Threatening someone to cause alarm or force them to act.' }],
      rahul: [{ s: 'BNS s. 78 · Stalking', d: 'Following or repeatedly contacting a woman despite clear disinterest, including online.' }, { s: 'BNS s. 351 · Criminal intimidation', d: 'Threatening someone to cause alarm or force them to act.' }],
      arjun: [{ s: 'BNS s. 79 · Insulting the modesty of a woman', d: 'Words or gestures meant to insult a woman.' }, { s: 'School anti-bullying policy', d: 'Your school or college must act on bullying between students.' }],
      priya: []
    };
    const CH = {
      cyber: { name: 'cybercrime.gov.in', desc: 'National Cyber Crime Reporting Portal. File online and track your complaint. Choose "Women/Children related crime".', link: 'https://cybercrime.gov.in' },
      h1930: { name: '1930 Cyber Helpline', desc: 'Call quickly for any crime involving money. They can freeze payments in time.', tel: 'tel:1930', telLabel: 'Call 1930' },
      ncii: { name: 'StopNCII', desc: 'Creates a fingerprint of intimate images on your device so platforms can block them. The image is never uploaded.', link: 'https://stopncii.org' },
      ncw: { name: 'NCW / Women Helpline 181', desc: 'National Commission for Women complaint, or call 181 for help and counselling.', link: 'https://ncw.gov.in', tel: 'tel:181', telLabel: 'Call 181' },
      gro: { name: 'Platform Grievance Officer', desc: 'Every major app must have a Grievance Officer in India who acts on complaints within set timelines.', guide: true },
      e112: { name: '112 Emergency', desc: 'If you are in danger right now.', tel: 'tel:112', telLabel: 'Call 112' }
    };
    const chOrder = { vikram: ['cyber', 'e112', 'ncw', 'ncii', 'gro', 'h1930'], tg: ['h1930', 'ncii', 'cyber', 'ncw', 'gro', 'e112'], rahul: ['cyber', 'e112', 'ncw', 'gro', 'h1930', 'ncii'], arjun: ['gro', 'ncw', 'cyber', 'h1930', 'ncii', 'e112'], priya: ['cyber', 'h1930', 'ncii', 'ncw', 'gro', 'e112'] };
    const firsts = { vikram: ['cyber', 'e112'], tg: ['h1930', 'ncii'], rahul: ['cyber'], arjun: ['gro'] };
    const suggest = { vikram: 'He ignored 3 clear refusals and threatened you: file on cybercrime.gov.in and tell your hostel warden. If he turns up outside, call 112.', tg: 'Sextortion: call 1930 and hash the image on StopNCII first. Then file on cybercrime.gov.in.', rahul: 'Stalking with a threat: file on cybercrime.gov.in. If you feel unsafe right now, call 112.', arjun: 'Bullying in a group: report to the platform and your school first.' };
    const T = {
      en: { home: 'Home', feed: 'Live Feed', people: 'People', media: 'Media Check', import: 'Import Chat', evidence: 'Evidence & Report', metrics: 'Metrics', slang: 'Slang List', settings: 'Settings', help: 'Get Help Now', exit: 'Quick Exit', ondevice: 'Processed on device' },
      hi: { home: 'होम', feed: 'लाइव फ़ीड', people: 'लोग', media: 'मीडिया जाँच', import: 'चैट आयात', evidence: 'सबूत और रिपोर्ट', metrics: 'मेट्रिक्स', slang: 'स्लैंग सूची', settings: 'सेटिंग्स', help: 'अभी मदद पाएँ', exit: 'तुरंत बाहर', ondevice: 'डिवाइस पर प्रोसेस' }
    };
    const terms = [
      { term: 'please stop', cat: 'Refusal signal', sev: 'info', variants: 'pls stop, stop it, leave me alone', src: 'Seed', date: '1 Oct' },
      { term: 'mat karo', cat: 'Refusal signal', sev: 'info', variants: 'mat kar, mt karo, bas karo, rehne do', src: 'Seed', date: '1 Oct' },
      { term: 'bhaiya', cat: 'Refusal signal', sev: 'info', variants: 'bhaiyya, bhaiyaa, bhaiya ji', src: 'Seed', date: '1 Oct' },
      { term: 'baat nahi karni', cat: 'Refusal signal', sev: 'info', variants: 'baat nhi karni, nahi chahiye, mujhse door raho', src: 'User', date: '20 Oct' },
      { term: 'ch@pri', cat: 'Bullying', sev: 'warn', variants: 'chapri, chhapri, ch4pri', src: 'Seed', date: '1 Oct' },
      { term: 'viral kar dunga', cat: 'Sextortion', sev: 'critical', variants: 'viral kr dunga, viral krdunga', src: 'Seed', date: '1 Oct' },
      { term: 'paise bhej', cat: 'Extortion', sev: 'high', variants: 'paisa bhej, pese bhej', src: 'Seed', date: '1 Oct' },
      { term: 'kys', cat: 'Self-harm incitement', sev: 'critical', variants: 'k y s, kill urself', src: 'Seed', date: '1 Oct' },
      { term: 'maal', cat: 'Sexual harassment', sev: 'high', variants: 'm@al, maaal', src: 'Seed', date: '1 Oct' },
      { term: 'where r u now', cat: 'Stalking', sev: 'warn', variants: 'kahan ho abhi, wru', src: 'User', date: '9 Oct' },
      { term: 'n00dz', cat: 'Sextortion', sev: 'high', variants: 'nudes, nudez', src: 'AI', date: '12 Oct' },
      { term: 'ghar aa jaunga', cat: 'Threat', sev: 'high', variants: 'ghar pe aaunga, ghr aa jaunga', src: 'User', date: '13 Oct' }
    ];
    const pending = [
      { term: 'chhapri', cat: 'Bullying', sev: 'warn', src: 'AI', note: 'Spelling variant of "ch@pri", seen 6 times this week.' },
      { term: 'v1ral kr dunga', cat: 'Sextortion', sev: 'critical', src: 'AI', note: 'Leetspeak variant of "viral kar dunga".' },
      { term: 'snitch', cat: 'Bullying', sev: 'warn', src: 'User', note: 'Flagged by you from a missed message.' }
    ];
    return { SEV, PHASE, APPN, people, script, evidence, laws, CH, chOrder, firsts, suggest, T, terms, pending };
  }

  initialState() {
    const D = this.D;
    const people = JSON.parse(JSON.stringify(D.people));
    return {
      live: false, conn: { status: 'checking', base: '', model: '', deepfake: '', error: '' },
      linkSugg: [], evLive: {}, details: {}, busy: false,
      screen: 'feed', theme: 'light', lang: 'en', exit: false, bell: false, protection: true,
      running: false, idx: 0, feed: [], alerts: [], unread: 0, speed: 1, scenario: 'refusal',
      fFlag: false, fApp: '', fLevel: '', fq: '',
      people, sel: 'vikram', pFilter: 'all', pq: '',
      toast: null, dlg: null, panic: false, panicPid: 'tg', checks: { ev: true, ncii: false, call: false, report: false, tell: false },
      media: { file: null, revealed: false, context: '', steps: this.freshSteps(), verdict: null, server: 'up', error: '', addTo: '', running: false },
      imp: { stage: 'pick', src: null, fileName: '', count: 0, participants: [], who: '', link: 'rahul', progress: 0, error: '', range: '' },
      ev: { pid: 'tg', inc: {}, hashes: {}, fp: '', generated: false, jsonUrl: '', editing: false, complaints: {}, verify: '' },
      packs: 0, feedback: 0,
      met: { loaded: false, file: '', running: false, cm: 'Stalking', data: null },
      slang: { q: '', cat: '', adding: false, form: { term: '', cat: 'Bullying', sev: 'warn', variants: '' }, terms: D.terms.slice(), pending: D.pending.slice(), test: 'u r such a ch4pri, paisa bhej warna v1ral kr dunga', log: [{ t: 'Added "n00dz" (AI suggestion)', when: '16 days ago' }, { t: 'Added "ghar aa jaunga" (from your feedback)', when: '15 days ago' }] },
      set: { monitoring: true, apps: { WA: true, IG: true, TG: true, SNAP: true, MSG: false, SMS: true }, sensitivity: 'Balanced', quickExit: true, disguise: false, hidePreviews: true, uploadFlagged: true, trusted: 'Meera (sister) · +91 9xxxx x2210' }
    };
  }

  freshSteps() {
    return [
      { name: 'Nudity check', status: 'waiting', result: 'Runs on this device' },
      { name: 'Face match', status: 'waiting', result: 'Compares with your enrolled face, on device' },
      { name: 'Deepfake model', status: 'waiting', result: 'Looks for signs of editing or generation' },
      { name: 'Context', status: 'waiting', result: 'Reads the message sent with it' }
    ];
  }

  componentWillUnmount() { this.stopTimers(); }
  stopTimers() { this.timers.forEach((t) => { clearTimeout(t); clearInterval(t); }); this.timers = []; if (this.feedTimer) { clearInterval(this.feedTimer); this.feedTimer = null; } }
  later(fn, ms) { const t = setTimeout(fn, ms); this.timers.push(t); return t; }

  sevOf(risk) { return risk >= 85 ? 'critical' : risk >= 65 ? 'high' : risk >= 35 ? 'warn' : 'info'; }
  nowTime() { const d = new Date(); return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }); }

  showToast(text, opts) {
    opts = opts || {};
    if (this.toastT) clearTimeout(this.toastT);
    this.setState({ toast: { text, actionLabel: opts.label || '', action: opts.action || null, sev: opts.sev || '' } });
    this.toastT = setTimeout(() => this.setState({ toast: null }), opts.ms || 4500);
  }

  go(screen, extra) {
    const s = Object.assign({ screen, bell: false }, extra || {});
    if (screen === 'feed') s.unread = 0;
    if (this.state.live) {
      if (s.sel && screen === 'people') this.loadPersonDetail(s.sel);
      if (screen === 'people' && !s.sel) this.refreshPeople();
      if (screen === 'evidence') {
        const ids = Object.keys(this.state.people);
        const pid = (s.ev && this.state.people[s.ev.pid]) ? s.ev.pid : (this.state.people[this.state.ev.pid] ? this.state.ev.pid : (this.state.sel || ids[0]));
        s.ev = Object.assign({}, this.state.ev, s.ev || {}, { pid, generated: false, verify: '' });
        if (pid) this.loadPack(pid);
      }
    }
    this.setState(s);
  }

  /* ---------- feed simulation ---------- */
  scriptFor() { return this.D.script.filter((m) => m.scen.indexOf(this.state.scenario) >= 0); }
  startFeed() {
    if (this.feedTimer) clearInterval(this.feedTimer);
    this.setState({ running: true });
    this.feedTimer = setInterval(() => this.tick(), 1700 / this.state.speed);
  }
  pauseFeed() { if (this.feedTimer) clearInterval(this.feedTimer); this.feedTimer = null; this.setState({ running: false }); }
  tick() {
    if (!this.state.protection) return;
    const list = this.scriptFor();
    const i = this.state.idx;
    if (i >= list.length) { this.pauseFeed(); this.showToast('Demo script finished. Press Reset to play again.'); return; }
    const src = list[i];
    if (this.state.live) { this.tickLive(src, i); return; }
    const m = Object.assign({}, src, { id: 'm' + Date.now() + i, time: this.nowTime(), safe: false });
    const prior = this.state.feed;
    if (!m.mine && m.pid) {
      const refusals = prior.filter((x) => x.mine && x.pid === m.pid).length;
      if (refusals) { m.afterNo = prior.filter((x) => !x.mine && x.pid === m.pid && x.afterNo).length + 1; m.refusals = refusals; }
    }
    const st = { idx: i + 1, feed: [m].concat(prior) };
    if (m.risk && m.pid && this.state.people[m.pid]) { const np = Object.assign({}, this.state.people); np[m.pid] = Object.assign({}, np[m.pid], { risk: m.risk }); st.people = np; }
    const isAlert = !m.mine && (m.sev === 'high' || m.sev === 'critical');
    if (isAlert) {
      st.alerts = [m].concat(this.state.alerts);
      if (this.state.screen !== 'feed') st.unread = this.state.unread + 1;
    }
    this.setState(st);
    if (m.sev === 'critical') {
      this.showToast('Critical: ' + (m.cat === 'Threat' ? 'threat' : 'possible sextortion') + ' from ' + m.from + '. Don\'t reply.', { label: 'Get help', action: () => this.openPanic(m.pid), sev: 'critical', ms: 8000 });
      this.later(() => this.openPanic(m.pid), 900);
    }
  }
  /* scripted message -> notification the Android listener would produce */
  toNotification(src) {
    const APPL = { WA: 'wa', IG: 'ig', TG: 'tg', SMS: 'sms', SNAP: 'snap' };
    const REL = { Stranger: 'stranger', Acquaintance: 'acquaintance', Friend: 'friend', Partner: 'partner', Family: 'family', Classmate: 'acquaintance' };
    const key = (src.pid || src.from) + ':' + src.app;
    let sender = src.from, handle = src.handle || src.from;
    if (src.mine) {
      const last = this.lastSender[key] || Object.keys(this.lastSender).filter((k) => k.indexOf((src.pid || '') + ':') === 0).map((k) => this.lastSender[k]).pop();
      if (last) { sender = last.sender; handle = last.handle; }
    } else {
      this.lastSender[key] = { sender, handle };
    }
    const mp = src.pid && this.D.people[src.pid];
    const rel = mp ? REL[mp.rel] : (src.from === 'Mom' ? 'family' : undefined);
    return {
      app: APPL[src.app] || 'sms', sender, sender_handle: handle, is_user: !!src.mine,
      text: src.hidden ? null : (src.text || (src.media ? '📷 Photo' : null)),
      media_type: src.media ? 'image' : null, timestamp: this.localIso(this.nextSimTime()),
      relationship: rel, is_group: /group|·/i.test(src.from || '')
    };
  }

  /* Scenario clock: the scripts happen in the evening (sextortion late at night), a few minutes apart,
     instead of at the real time of the demo. Time of day is a real model signal, so this matters. */
  nextSimTime() {
    if (!this.simTime || this.state.idx === 0) {
      const start = { sextortion: [22, 55], refusal: [21, 0], stalker: [18, 0], bullying: [16, 0], flirt: [17, 30], full: [17, 0] }[this.state.scenario] || [20, 0];
      const d = new Date(); d.setHours(start[0], start[1], 0, 0);
      if (d > new Date()) d.setDate(d.getDate() - 1);
      this.simTime = d;
    } else {
      this.simTime = new Date(this.simTime.getTime() + (3 + Math.floor(Math.random() * 6)) * 60000);
    }
    return this.simTime;
  }

  async tickLive(src, i) {
    if (this.state.busy) return;
    this.setState({ busy: true });
    const L = this.LABELS();
    try {
      const r = await SSApi.post('/ingest/notification', this.toNotification(src));
      const pv = r.people[0];
      const lab = (r.labels || [])[0] || {};
      const d = await SSApi.get('/people/' + pv.id).catch(() => null);
      const PH = { mutual: 'Mutual', unreciprocated: 'Unreciprocated', rejected: 'Rejected', violation: 'Violation' };
      const tl = (d && d.consent_timeline) || [];
      const m = Object.assign({}, src, {
        id: 'm' + Date.now() + i, time: this.simTime.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }), safe: false, pid: pv.id, why: '', cat: '', risk: Math.round((pv.risk || 0) * 100),
        phase: tl.length ? PH[tl[tl.length - 1].phase] : undefined
      });
      if (src.mine) {
        m.sev = 'info';
        m.refusal = lab.label === 'reject';
        m.rejectNote = m.refusal ? (src.rejectNote || '') : 'The model read this as a ' + (lab.label || 'neutral') + ' reply, not a refusal.';
        if (!m.refusal) m.phase = undefined;
      } else {
        m.sev = pv.level;
        m.cat = pv.level === 'info' ? '' : (pv.early ? 'Early signal' : (L[pv.label] || ''));
        m.why = (pv.reasons || [])[0] || '';
        const after = d && d.facts && d.facts.msgs_after_reject;
        if (after && m.phase === 'Violation') { m.afterNo = Math.round(after); }
      }
      const np = Object.assign({}, this.state.people);
      np[pv.id] = this.mapPerson(pv, np[pv.id], d || undefined);
      const st = { idx: i + 1, feed: [m].concat(this.state.feed), people: np, busy: false, sel: this.state.sel || pv.id };
      const newAlerts = (r.new_alerts || []).map((a) => Object.assign({}, m, { id: 'a' + a.id, alertId: a.id, sev: a.level, cat: L[a.label] || a.label, why: (a.reasons || [])[0] || a.summary, pid: a.person_id }));
      if (newAlerts.length) {
        st.alerts = newAlerts.concat(this.state.alerts);
        if (this.state.screen !== 'feed') st.unread = this.state.unread + newAlerts.length;
      }
      this.setState(st);
      const crit = newAlerts.find((a) => a.sev === 'critical');
      if (crit) {
        this.showToast('Critical: ' + crit.cat.toLowerCase() + ' from ' + crit.from + '. Don\'t reply.', { label: 'Get help', action: () => this.openPanic(crit.pid), sev: 'critical', ms: 8000 });
        this.later(() => this.openPanic(crit.pid), 900);
      }
      if (i % 3 === 2) SSApi.get('/links/suggestions').then((s) => this.setState({ linkSugg: s || [] }), () => {});
    } catch (e) {
      this.setState({ busy: false });
      this.pauseFeed();
      this.liveFail(e, 'Scoring failed');
    }
  }

  async liveFeedback(pid, trusted) {
    try {
      const v = trusted ? await SSApi.post('/feedback', { person_id: pid, kind: 'not_harassment' }) : await SSApi.patch('/people/' + pid, { trusted: false });
      const np = Object.assign({}, this.state.people);
      np[pid] = this.mapPerson(v, np[pid], v);
      this.setState({ people: np, feedback: this.state.feedback + (trusted ? 1 : 0) });
      this.loadPersonDetail(pid);
    } catch (e) { this.liveFail(e, 'Feedback failed'); }
  }

  openPanic(pid) { this.setState({ panic: true, panicPid: pid || (this.state.live ? this.state.sel : 'tg'), toast: null, bell: false }); }

  notHarass(m) {
    if (this.state.live) {
      const feed = this.state.feed.map((x) => x.pid === m.pid ? Object.assign({}, x, { safe: true }) : x);
      this.setState({ feed, alerts: this.state.alerts.filter((x) => x.pid !== m.pid) });
      if (m.pid) this.liveFeedback(m.pid, true);
      const name = m.pid && this.state.people[m.pid] ? this.state.people[m.pid].name : m.from;
      this.showToast('Thanks. Marked ' + name + ' as not harassment.', { label: 'Undo', action: () => { if (m.pid) this.liveFeedback(m.pid, false); this.setState({ toast: null }); } });
      return;
    }
    const p = m.pid ? this.state.people[m.pid] : null;
    const people = Object.assign({}, this.state.people);
    let before = null;
    if (p) { before = p.risk; people[p.id] = Object.assign({}, p, { risk: Math.max(5, p.risk - 35), safe: true }); }
    const feed = this.state.feed.map((x) => x.id === m.id ? Object.assign({}, x, { safe: true }) : x);
    const alerts = this.state.alerts.filter((x) => x.id !== m.id);
    const prev = { feed: this.state.feed, alerts: this.state.alerts, people: this.state.people };
    this.setState({ feed, alerts, people, feedback: this.state.feedback + 1 });
    this.showToast('Thanks. Marked as not harassment' + (p ? ' and lowered ' + p.name + "'s risk." : '.'), { label: 'Undo', action: () => { this.setState(prev); this.setState({ toast: null }); } });
  }

  /* ---------- media ---------- */
  setMedia(patch) { this.setState({ media: Object.assign({}, this.state.media, patch) }); }
  loadFile(f) {
    if (!f) return;
    const ok = /^(image|video|audio)\//.test(f.type);
    if (!ok) { this.setMedia({ error: 'This file type isn\'t supported. Use an image, video or voice note.', file: null }); return; }
    if (f.size > 50 * 1024 * 1024) { this.setMedia({ error: 'This file is larger than 50 MB. Try a shorter clip or a screenshot.', file: null }); return; }
    let url = '';
    try { url = URL.createObjectURL(f); } catch (e) {}
    const kind = f.type.split('/')[0];
    this.mediaBlob = f;
    this.setMedia({ file: { name: f.name, size: (f.size / 1048576).toFixed(1) + ' MB', kind, url, sample: false }, error: '', revealed: false, verdict: null, steps: this.freshSteps() });
  }

  /* placeholder bytes for the "use sample" button, so the real pipeline can run without a real photo */
  sampleBlob() {
    const b64 = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=';
    const bin = atob(b64), arr = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
    return new Blob([arr], { type: 'image/png' });
  }

  async analyseLive() {
    const md = this.state.media;
    const fd = new FormData();
    const blob = md.file.sample || !this.mediaBlob ? this.sampleBlob() : this.mediaBlob;
    fd.append('file', blob, md.file.sample ? 'IMG_0031.png' : md.file.name);
    if (md.context) fd.append('context_text', md.context);
    if (md.addTo) fd.append('person_id', md.addTo);
    this.setMedia({ running: true, error: '', verdict: null, steps: this.freshSteps() });
    let r;
    try { r = await SSApi.post('/media/check', fd); } catch (e) {
      this.setMedia({ running: false, error: (e && e.status === 502 ? 'The deepfake service returned an error: ' : "Couldn't analyse this file: ") + ((e && e.message) || e) + '. Retry?' });
      return;
    }
    const by = {}; (r.steps || []).forEach((s) => { by[s.step] = s; });
    const fmt = (v) => (v === null || v === undefined) ? null : (Math.round(v * 100) / 100).toFixed(2);
    const n = by.nudity_check || {}, fm = by.face_match || {}, dfs = by.deepfake_model || {}, cx = by.context || {};
    const results = [
      { status: n.flagged ? 'flagged' : 'pass', result: fmt(n.value) === null ? 'Not provided by the model' : (n.flagged ? 'Likely intimate image · ' : 'No nudity detected · ') + fmt(n.value) },
      { status: fm.flagged ? 'flagged' : 'pass', result: fmt(fm.value) === null ? 'Not provided by the model' : (fm.flagged ? 'Matches your enrolled face · ' : 'Does not match your face · ') + fmt(fm.value) },
      { status: dfs.flagged ? 'flagged' : 'pass', result: dfs.wording || '' },
      { status: cx.flagged ? 'flagged' : 'pass', result: cx.flagged ? 'Threat or demand: ' + (cx.value || []).join(', ') : (md.context && md.context.trim() ? 'No threat or demand found in the message' : 'No message given') }
    ];
    const verdict = { sev: r.level, text: r.headline + (r.is_stub ? ' · demo values: the deepfake model is not connected yet' : ''), todo: r.actions || [] };
    this.mediaCheckId = r.id;
    results.forEach((res, i) => {
      this.later(() => { const steps = this.state.media.steps.map((s, j) => j === i ? Object.assign({}, s, { status: 'running', result: 'Checking…' }) : s); this.setMedia({ steps }); }, i * 700 + 100);
      this.later(() => {
        const steps = this.state.media.steps.map((s, j) => j === i ? Object.assign({}, s, res) : s);
        this.setMedia(i === results.length - 1 ? { steps, running: false, verdict } : { steps });
      }, i * 700 + 600);
    });
  }
  useSample(ctx) {
    this.setMedia({ file: { name: 'IMG_0031.jpg', size: '1.8 MB', kind: 'image', url: '', sample: true }, context: ctx || 'Pay ₹20,000 by tonight or this goes to your family and your college group.', error: '', revealed: false, verdict: null, steps: this.freshSteps() });
  }
  analyse() {
    const md = this.state.media;
    if (!md.file || md.running) return;
    if (md.server === 'down') {
      const steps = this.freshSteps(); steps[0].status = 'pass'; steps[0].result = 'No nudity detected · 0.06'; steps[1].status = 'flagged'; steps[1].result = 'Matches your enrolled face · 0.87';
      this.setMedia({ steps, error: "Couldn't reach the analysis server. On-device checks still ran. Retry?", verdict: null });
      return;
    }
    if (this.state.live) { this.analyseLive(); return; }
    const ctx = (md.context || '').toLowerCase();
    const money = /(₹|rs|pay|paise|money|send|transfer|upi)/.test(ctx);
    const threat = /(family|college|viral|share|leak|send this|everyone)/.test(ctx);
    const results = [
      { status: 'flagged', result: 'Likely intimate image · 0.94' },
      { status: 'flagged', result: 'Matches your enrolled face · 0.87' },
      { status: 'flagged', result: 'Likely manipulated (88%) · face edges and lighting don\'t match' },
      ctx.trim() ? (money || threat ? { status: 'flagged', result: (money ? 'Money demand' : '') + (money && threat ? ' + ' : '') + (threat ? 'threat to share' : '') } : { status: 'pass', result: 'No threat or demand found in the message' }) : { status: 'pass', result: 'No message given' }
    ];
    this.setMedia({ running: true, error: '', verdict: null, steps: this.freshSteps() });
    results.forEach((r, i) => {
      this.later(() => { const steps = this.state.media.steps.map((s, j) => j === i ? Object.assign({}, s, { status: 'running', result: 'Checking…' }) : s); this.setMedia({ steps }); }, i * 1000 + 100);
      this.later(() => {
        const steps = this.state.media.steps.map((s, j) => j === i ? Object.assign({}, s, r) : s);
        const patch = { steps };
        if (i === results.length - 1) {
          const crit = results[3].status === 'flagged';
          patch.running = false;
          patch.verdict = crit
            ? { sev: 'critical', text: 'Likely manipulated intimate image (88%) used for sextortion', todo: ["Don't pay and don't reply.", 'Hash the image on StopNCII so platforms can block it.', 'Call 1930 and save the evidence pack.'] }
            : { sev: 'high', text: 'Likely manipulated image of you (88%)', todo: ['Keep the original message. Don\'t delete it.', 'Hash the image on StopNCII so platforms can block it.', 'Add it to the sender\'s case.'] };
        }
        this.setMedia(patch);
      }, i * 1000 + 900);
    });
  }

  /* ---------- import ---------- */
  setImp(patch) { this.setState({ imp: Object.assign({}, this.state.imp, patch) }); }

  /* small realistic export files for the "sample" buttons, so the real parser and model run */
  sampleExport(src) {
    if (src === 'WA') {
      const L = ['03/08/26, 7:10 pm - Rahul K: hi, Rahul from the bus stop', '03/08/26, 7:30 pm - You: oh hi', '10/08/26, 8:12 am - Rahul K: good morning :)',
        '10/08/26, 8:40 am - You: gm', '28/09/26, 11:40 pm - Rahul K: reply na', '28/09/26, 11:41 pm - Rahul K: why are you online but not replying',
        '29/09/26, 1:05 am - Rahul K: hello??', '29/09/26, 1:06 am - Rahul K: kab tak ignore karogi', '12/10/26, 9:40 pm - Rahul K: Why won\'t you talk to me',
        '12/10/26, 9:52 pm - You: please stop messaging me', '12/10/26, 10:10 pm - Rahul K: itna attitude kyu', '13/10/26, 12:30 am - Rahul K: ek baar baat kar lo',
        '13/10/26, 1:15 am - Rahul K: reply na please', '13/10/26, 11:10 pm - Rahul K: I know where you live. Don\'t make me come there.',
        '14/10/26, 6:05 pm - Rahul K: Saw you at the café near your college today. Blue kurta suits you.', '14/10/26, 6:06 pm - Rahul K: who were you with',
        '14/10/26, 11:31 pm - Rahul K: you can block me but you can\'t get rid of me'];
      return new File([L.join('\n')], 'WhatsApp Chat with Rahul K.txt', { type: 'text/plain' });
    }
    if (src === 'IG') {
      const t = (d) => new Date(d).getTime();
      const msgs = [['rahul.k_22', '2026-10-15T00:10:00', 'block kyu kiya'], ['rahul.k_22', '2026-10-15T00:11:00', 'reply na'], ['You', '2026-10-15T09:00:00', 'leave me alone'],
        ['rahul.k_22', '2026-10-15T23:30:00', 'tum kiske saath thi'], ['rahul.k_22', '2026-10-16T01:20:00', 'where are you right now']];
      return new File([JSON.stringify({ participants: [{ name: 'rahul.k_22' }, { name: 'You' }], messages: msgs.map((m) => ({ sender_name: m[0], timestamp_ms: t(m[1]), content: m[2] })) })], 'message_1.json', { type: 'application/json' });
    }
    const msgs = [['night.owl_77', '2026-10-14T23:02:00', 'I have your private photos. Open this.'], ['night.owl_77', '2026-10-14T23:03:00', 'your morphed photo is ready'],
      ['You', '2026-10-14T23:03:30', 'who is this'], ['night.owl_77', '2026-10-14T23:04:00', 'Pay ₹20,000 by tonight or this goes to your family and your college group.'],
      ['night.owl_77', '2026-10-14T23:15:00', 'paise bhej nahi toh viral kar dunga']];
    return new File([JSON.stringify({ name: 'night.owl_77', messages: msgs.map((m, i) => ({ id: i, type: 'message', date: m[1], from: m[0], text: m[2] })) })], 'result.json', { type: 'application/json' });
  }

  async importFileLive(src, f) {
    const SRC = { WA: 'whatsapp', IG: 'instagram', TG: 'telegram' };
    if (!SRC[src]) { this.setImp({ stage: 'pick', error: 'Screenshot OCR is not connected to the backend yet. Use a WhatsApp, Instagram or Telegram export.', errorSample: '' }); return; }
    const fd = new FormData(); fd.append('file', f, f.name); fd.append('source', SRC[src]);
    try {
      const r = await SSApi.post('/import/preview', fd);
      this.impFile = f;
      const counts = r.message_counts || {};
      this.setImp({ stage: 'preview', src, fileName: f.name, count: r.total, participants: r.participants,
        range: this.fmtDate(r.first) + ' – ' + this.fmtDate(r.last), who: r.participants.indexOf('You') >= 0 ? 'You' : '', error: '', errorSample: '',
        link: 'new', counts });
    } catch (e) {
      const sample = src === 'WA' ? '14/10/26, 6:05 pm - Rahul K: Saw you at the café…' : '{"messages":[{"sender_name":"rahul.k_22","content":"…"}]}';
      this.setImp({ stage: 'pick', error: "We couldn't read this file (" + ((e && e.message) || e) + '). It should look like this:', errorSample: sample });
    }
  }

  async runImportLive() {
    const I = this.state.imp, SRC = { WA: 'whatsapp', IG: 'instagram', TG: 'telegram' };
    const fd = new FormData();
    fd.append('file', this.impFile, this.impFile.name); fd.append('source', SRC[I.src]); fd.append('user_name', I.who);
    if (I.link && I.link !== 'new') fd.append('person_id', I.link);
    this.setImp({ stage: 'running', progress: 15, stageText: 'Parsing messages and scoring behaviour…' });
    this.later(() => { if (this.state.imp.stage === 'running') this.setImp({ progress: 55, stageText: 'Scoring consent over time…' }); }, 500);
    try {
      const r = await SSApi.post('/import', fd);
      const p = r.people[0], L = this.LABELS(), SEV = this.D.SEV;
      const head = r.imported + ' messages imported · ' + SEV[p.level].label + ': ' + (L[p.label] || 'not enough data');
      const sub = (p.level === 'info' ? (p.reasons_down || [])[0] : (p.reasons || [])[0]) || '';
      this.setImp({ stage: 'done', progress: 100, result: head, resultSub: sub, donePid: p.id });
      this.refreshPeople(p.id);
    } catch (e) {
      this.setImp({ stage: 'preview', error: 'Import failed: ' + ((e && e.message) || e) });
    }
  }

  importSample(src) {
    if (this.state.live && src !== 'OCR') { this.importFileLive(src, this.sampleExport(src)); return; }
    const map = {
      WA: { fileName: 'WhatsApp Chat with Rahul K.txt', count: 1240, participants: ['You', 'Rahul K'], range: '3 Aug – 14 Oct', link: 'rahul' },
      IG: { fileName: 'message_1.json', count: 386, participants: ['You', 'rahul.k_22'], range: '20 Aug – 10 Oct', link: 'rahul' },
      TG: { fileName: 'result.json', count: 9, participants: ['You', 'night.owl_77'], range: '14 Oct', link: 'tg' },
      OCR: { fileName: '3 screenshots', count: 27, participants: ['You', 'Arjun M'], range: '11 Oct – 14 Oct', link: 'arjun' }
    };
    this.setImp(Object.assign({ stage: 'preview', src, who: '', error: '' }, map[src]));
  }
  importFile(src, f) {
    if (!f) return;
    if (this.state.live) { this.importFileLive(src, f); return; }
    if (src === 'OCR') { this.setImp({ stage: 'preview', src, fileName: f.name, count: 27, participants: ['You', 'Other person'], range: 'dates from screenshot', who: '', error: '', link: 'arjun' }); return; }
    const rd = new FileReader();
    rd.onload = () => {
      const text = String(rd.result || '');
      if (!text.trim()) { this.setImp({ error: 'This file is empty.', errorSample: '', stage: 'pick' }); return; }
      let names = [], count = 0;
      if (src === 'WA') {
        const re = /^\[?\d{1,2}[\/.]\d{1,2}[\/.]\d{2,4},?\s[^\]\-]*[\]\-]\s*-?\s*([^:]{1,40}):/gm;
        let mm; while ((mm = re.exec(text))) { count++; if (names.indexOf(mm[1].trim()) < 0) names.push(mm[1].trim()); }
      } else {
        try { const j = JSON.parse(text); const msgs = j.messages || []; count = msgs.length; msgs.forEach((x) => { const n = x.sender_name || x.from; if (n && names.indexOf(n) < 0) names.push(n); }); (j.participants || []).forEach((p) => { if (p.name && names.indexOf(p.name) < 0) names.push(p.name); }); } catch (e) { count = 0; }
      }
      if (!count) {
        const sample = src === 'WA' ? '14/10/26, 6:05 pm - Rahul K: Saw you at the café…' : '{"messages":[{"sender_name":"rahul.k_22","content":"…"}]}';
        this.setImp({ stage: 'pick', error: "We couldn't read this format. It should look like this:", errorSample: sample });
        return;
      }
      this.setImp({ stage: 'preview', src, fileName: f.name, count, participants: names.slice(0, 8), range: 'from your file', who: '', error: '', link: 'rahul' });
    };
    rd.readAsText(f);
  }
  runImport() {
    if (this.state.live) { this.runImportLive(); return; }
    const stages = ['Parsing messages…', 'Separating your replies…', 'Normalising slang…', 'Scoring consent over time…', 'Linking accounts…'];
    this.setImp({ stage: 'running', progress: 0 });
    for (let k = 1; k <= 20; k++) {
      this.later(() => this.setImp({ progress: k * 5, stageText: stages[Math.min(stages.length - 1, Math.floor(k / 4))] }), k * 110);
    }
    this.later(() => {
      const im = this.state.imp;
      const pid = im.link === 'new' ? 'rahul' : im.link;
      const res = { rahul: ['23 flagged messages · consent violated on 12 Oct', 'Rahul K kept messaging after you said "please stop". His risk went up to 88.'], tg: ['4 flagged messages · sextortion', 'A money demand and a threat to share an image.'], arjun: ['3 flagged messages · bullying', 'Insults in a 48-member group.'], priya: ['0 flagged messages', 'This looks like mutual banter. Nothing to worry about.'] }[pid];
      const people = Object.assign({}, this.state.people);
      if (pid === 'rahul') people.rahul = Object.assign({}, people.rahul, { risk: Math.max(people.rahul.risk, 88) });
      this.setState({ people, imp: Object.assign({}, this.state.imp, { stage: 'done', result: res[0], resultSub: res[1], donePid: pid }) });
    }, 2400);
  }

  /* ---------- evidence ---------- */
  async sha(str) {
    try {
      const b = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(str));
      return Array.from(new Uint8Array(b)).map((x) => x.toString(16).padStart(2, '0')).join('');
    } catch (e) {
      let out = ''; let h = 2166136261;
      for (let r = 0; r < 8; r++) { for (let i = 0; i < str.length; i++) { h ^= str.charCodeAt(i) + r; h = Math.imul(h, 16777619) >>> 0; } out += h.toString(16).padStart(8, '0'); }
      return out;
    }
  }
  evItems(pid) {
    if (!this.state.live) return this.D.evidence[pid] || [];
    const pack = this.state.evLive[pid];
    if (!pack) return [];
    const CAT = { user_said_no: 'Refusal (yours)', sexual: 'Sexual', insult: 'Insult', threat: 'Threat', sextortion: 'Sextortion',
      surveillance: 'Stalking', clingy: 'Pressure', flirt: 'Unwanted flirting', media: 'Media' };
    return pack.items.map((it) => ({
      time: this.fmtTime(it.time_utc), app: it.from_user ? 'YOU' : this.appCode((it.app || (it.account || '').split(':')[0])),
      acct: it.from_user ? 'Your reply' : (it.account || it.filename || '').replace(/^[a-z]+:/, ''),
      text: it.text || it.verdict || (it.filename ? it.filename : '[Preview hidden]'),
      cat: (it.category || '').indexOf('media_') === 0 ? 'Media check' : (CAT[it.category] || it.category),
      media: (it.category || '').indexOf('media') === 0, deleted: false, raw: it
    }));
  }

  async loadPack(pid, reveal) {
    if (!pid) return;
    try {
      const pack = await SSApi.post('/report/' + pid);
      const hashes = {};
      pack.items.forEach((it, i) => { hashes[pid + ':' + i] = it.sha256; });
      const prevC = this.state.evLive[pid] && this.state.evLive[pid].conclusion;
      const evLive = Object.assign({}, this.state.evLive, { [pid]: Object.assign(pack, { conclusion: prevC }) });
      const ev = Object.assign({}, this.state.ev, reveal ? { hashes: Object.assign({}, this.state.ev.hashes, hashes) } : {});
      this.setState({ evLive, ev });
      SSApi.post('/conclusion/' + pid).then((c) => {
        const cur = this.state.evLive[pid];
        if (cur) this.setState({ evLive: Object.assign({}, this.state.evLive, { [pid]: Object.assign({}, cur, { conclusion: c }) }) });
      }, () => {});
      return pack;
    } catch (e) { this.liveFail(e, 'Could not build the evidence pack'); return null; }
  }

  async generateLive() {
    const pid = this.state.ev.pid;
    const pack = await this.loadPack(pid, true);
    if (!pack) return;
    const inc = pack.items.filter((_, i) => this.isInc(pid, i));
    const all = inc.length === pack.items.length;
    const fp = all ? pack.pack_sha256 : await this.sha(inc.map((x) => x.sha256).join(''));
    let jsonUrl = '';
    try {
      const out = Object.assign({}, pack, { items: inc, pack_sha256: fp },
        all ? {} : { note: 'Subset chosen by the user: pack_sha256 = SHA-256 of the included items\' sha256 values joined in order.' });
      jsonUrl = URL.createObjectURL(new Blob([JSON.stringify(out, null, 2)], { type: 'application/json' }));
    } catch (e) {}
    const hashes = Object.assign({}, this.state.ev.hashes);
    pack.items.forEach((it, i) => { hashes[pid + ':' + i] = it.sha256; });   // same update, so a stale state can't drop them
    this.setState((s) => ({ ev: Object.assign({}, s.ev, { hashes, fp, generated: true, jsonUrl, verify: '' }), packs: s.packs + (s.ev.generated ? 0 : 1) }));
    this.showToast('Evidence pack generated · ' + inc.length + ' items fingerprinted by the backend.');
  }

  async verifyLive() {
    const pack = this.state.evLive[this.state.ev.pid];
    if (!pack) return;
    let ok = true;
    for (const it of pack.items) {
      const copy = Object.assign({}, it); delete copy.sha256;
      if ((await this.sha(SSApi.pyJson(copy))) !== it.sha256) ok = false;
    }
    this.setState({ ev: Object.assign({}, this.state.ev, { verify: ok ? 'Verified in your browser: every item matches the SHA-256 the backend recorded. Nothing has changed.' : 'Warning: some items do not match their recorded SHA-256.' }) });
  }

  async pdfLive() {
    const pid = this.state.ev.pid;
    try {
      const r = await SSApi.raw('GET', '/report/' + pid + '.pdf');
      const url = URL.createObjectURL(await r.blob());
      const a = document.createElement('a'); a.href = url; a.download = 'safesphere_evidence_' + pid + '.pdf'; document.body.appendChild(a); a.click(); a.remove();
      this.showToast('PDF downloaded.');
    } catch (e) { this.liveFail(e, 'PDF failed'); }
  }
  isInc(pid, i) { const v = this.state.ev.inc[pid + ':' + i]; return v === undefined ? true : v; }
  async generate() {
    if (this.state.live) return this.generateLive();
    const pid = this.state.ev.pid;
    const items = this.evItems(pid);
    const hashes = Object.assign({}, this.state.ev.hashes);
    const inc = [];
    for (let i = 0; i < items.length; i++) {
      const it = items[i];
      const h = await this.sha([it.time, it.app, it.acct, it.text, it.cat].join('|'));
      hashes[pid + ':' + i] = h;
      if (this.isInc(pid, i)) inc.push(Object.assign({}, it, { sha256: h }));
    }
    const fp = await this.sha(inc.map((x) => x.sha256).join(''));
    let jsonUrl = '';
    try {
      const pack = { app: 'SafeSphere', person: this.state.people[pid].name, created: new Date().toISOString(), items: inc, pack_sha256: fp, note: 'Hashes are SHA-256 over time|app|account|text|category.' };
      jsonUrl = URL.createObjectURL(new Blob([JSON.stringify(pack, null, 2)], { type: 'application/json' }));
    } catch (e) {}
    this.setState({ ev: Object.assign({}, this.state.ev, { hashes, fp, generated: true, jsonUrl, verify: '' }), packs: this.state.packs + (this.state.ev.generated ? 0 : 1) });
    this.showToast('Evidence pack generated · ' + inc.length + ' items hashed.');
  }
  async verify() {
    if (this.state.live) return this.verifyLive();
    const pid = this.state.ev.pid;
    const items = this.evItems(pid);
    let ok = true;
    for (let i = 0; i < items.length; i++) {
      const it = items[i];
      const h = await this.sha([it.time, it.app, it.acct, it.text, it.cat].join('|'));
      if (h !== this.state.ev.hashes[pid + ':' + i]) ok = false;
    }
    this.setState({ ev: Object.assign({}, this.state.ev, { verify: ok ? 'Verified: every item matches its hash. Nothing has changed.' : 'Warning: some items do not match their hashes.' }) });
  }
  complaintFor(pid) {
    if (this.state.live) {
      const pack = this.state.evLive[pid];
      if (!pack) return 'Pick a person, then press Generate pack.';
      return pack.complaint_text + '\nEvidence pack SHA-256: ' + (this.state.ev.generated ? this.state.ev.fp : '[GENERATE THE PACK FIRST]') + '\n\n[YOUR NAME]\n[YOUR PHONE]\n[DATE]';
    }
    const p = this.state.people[pid];
    const items = this.evItems(pid).filter((_, i) => this.isInc(pid, i));
    const accts = p.accounts.map((a) => this.D.APPN[a.app] + ' ' + a.handle).join(', ');
    const lines = items.map((it, i) => (i + 1) + '. ' + it.time + ' (' + it.acct + '): "' + it.text + '"').join('\n');
    const what = { vikram: 'kept contacting me after I clearly refused three times ("please stop messaging me", "mat karo please", "bhaiya please, bas karo"), said he would wait outside my hostel, and threatened to share my photos with everyone', tg: 'is threatening to share a manipulated intimate image of me unless I pay ₹20,000', rahul: 'has been following and repeatedly messaging me after I clearly told him to stop on 12 Oct', arjun: 'has been insulting me in our class WhatsApp group', priya: 'has contacted me' }[pid];
    return 'To the Cyber Crime Cell,\n\nI, [YOUR NAME], wish to report that the person using the account(s) ' + accts + ' ' + what + '.\n\nFlagged messages:\n' + lines + '\n\nI have attached a SafeSphere evidence pack. Its SHA-256 fingerprint is ' + (this.state.ev.generated ? this.state.ev.fp : '[GENERATE THE PACK FIRST]') + '. I have not deleted any messages.\n\nI request you to take action under the applicable sections of the BNS and IT Act.\n\n[YOUR NAME]\n[YOUR PHONE]\n[DATE]';
  }
  copyText(text, msg) {
    const done = () => this.showToast(msg);
    try { navigator.clipboard.writeText(text).then(done, () => this.showToast('Copy is blocked here. Select the text and copy it.')); } catch (e) { this.showToast('Copy is blocked here. Select the text and copy it.'); }
  }

  /* ---------- metrics ---------- */
  metData() {
    if (this.state.met.data) return this.state.met.data;
    return {
      overall: { keyword: { precision: 0.58, recall: 0.47, f1: 0.52, detection_rate: 0.61 }, safesphere: { precision: 0.89, recall: 0.86, f1: 0.87, detection_rate: 0.93 } },
      categories: [{ name: 'Stalking', precision: 0.88, recall: 0.84, f1: 0.86 }, { name: 'Sextortion', precision: 0.93, recall: 0.91, f1: 0.92 }, { name: 'Bullying', precision: 0.84, recall: 0.8, f1: 0.82 }, { name: 'Sexual harassment', precision: 0.87, recall: 0.85, f1: 0.86 }, { name: 'Threats', precision: 0.9, recall: 0.83, f1: 0.86 }],
      banter_false_alarm: { keyword: 0.31, safesphere: 0.06 },
      linking_accuracy: 0.88,
      deepfake: [{ type: 'Image', detection_rate: 0.91, false_alarm: 0.07 }, { type: 'Video', detection_rate: 0.84, false_alarm: 0.11 }, { type: 'Voice note', detection_rate: 0.79, false_alarm: 0.13 }],
      dataset: { size: '[N] messages · [M] media files', sources: 'Sources: [ADD YOUR DATASETS] · includes synthetic chats written by the team' }
    };
  }
  /* backend metrics.json (evaluate.py output) -> the Metrics screen's shape */
  async loadLiveMetrics(toast) {
    try {
      const m = await SSApi.get('/metrics');
      const t = m.synthetic_text_model || m.synthetic;
      const L = this.LABELS();
      const order = ['stalking', 'harassment_after_no', 'sextortion', 'group_bullying', 'unreciprocated', 'safe_mutual', 'banter', 'normal_frequent'];
      const pc = t.per_class || {};
      const data = {
        overall: { keyword: t.comparison.keyword, safesphere: t.comparison.lightgbm },
        categories: order.filter((k) => pc[k]).map((k) => ({ name: L[k], precision: pc[k].precision, recall: pc[k]['recall'], f1: pc[k]['f1-score'] })),
        banter_false_alarm: { keyword: t.hard_negative_far.keyword || 0, safesphere: t.hard_negative_far.lightgbm || 0 },
        linking_accuracy: null,
        deepfake: [{ type: 'Your deepfake models', detection_rate: null, false_alarm: null }],
        dataset: { size: t.n_persons + ' test people · ' + (m.cross_generator ? m.cross_generator.n_persons + ' more from a second generator' : ''),
          sources: 'Synthetic data: team dataset + SafeSphere simulator. Labels predicted by the text model, as in real use.' + (m.cross_generator ? ' Second generator F1: ' + m.cross_generator.comparison.lightgbm.f1.toFixed(2) + '.' : '') }
      };
      this.setState({ met: Object.assign({}, this.state.met, { loaded: true, file: 'backend metrics.json · model ' + (m.model_version || ''), data, running: false }) });
      if (toast) this.showToast('Loaded the latest metrics from the backend.');
    } catch (e) {
      this.setState({ met: Object.assign({}, this.state.met, { running: false }) });
      if (toast) this.liveFail(e, 'Metrics not available');
    }
  }

  loadMetrics(f) {
    if (!f) return;
    const rd = new FileReader();
    rd.onload = () => {
      try {
        const j = JSON.parse(String(rd.result));
        if (!j.overall || !j.categories) throw new Error('shape');
        const base = this.metData();
        this.setState({ met: Object.assign({}, this.state.met, { loaded: true, file: f.name, data: Object.assign({}, base, j) }) });
        this.showToast('Loaded ' + f.name);
      } catch (e) { this.showToast("That file doesn't match the expected format. See the example under Deepfake detection."); }
    };
    rd.readAsText(f);
  }

  /* ---------- slang ---------- */
  norm(w) { return w.toLowerCase().replace(/@/g, 'a').replace(/4/g, 'a').replace(/0/g, 'o').replace(/1/g, 'i').replace(/3/g, 'e').replace(/\$/g, 's').replace(/[^a-zऀ-ॿ ]/g, ''); }
  setSlang(patch) { this.setState({ slang: Object.assign({}, this.state.slang, patch) }); }

  renderVals() {
    const S = this.state, D = this.D, SEV = D.SEV;
    const T = D.T[S.lang];
    const sevBits = (sev) => ({ sevClass: SEV[sev].cls, sevLabel: SEV[sev].label, border: SEV[sev].border, fill: SEV[sev].fill });
    const people = S.people;
    const LV = { info: 0, warn: 1, high: 2, critical: 3 };
    const plist = Object.keys(people).map((k) => people[k]).sort((a, b) => (LV[this.pSev(b)] - LV[this.pSev(a)]) || (b.risk - a.risk));
    const peopleOpts = plist.map((p) => ({ id: p.id, name: p.name }));
    const isHigh = (p) => LV[this.pSev(p)] >= 2;
    const EMPTY = this.emptyPerson();

    /* nav */
    const screens = ['home', 'feed', 'people', 'media', 'import', 'evidence', 'metrics', 'slang', 'settings'];
    const nav = {}; const is = {};
    const highPeople = plist.filter((p) => !p.safe && isHigh(p)).length;
    screens.forEach((s) => {
      is[s] = S.screen === s;
      nav[s] = { cls: S.screen === s ? 'active' : '', current: S.screen === s ? 'page' : undefined, go: () => this.go(s), hasBadge: false, badge: 0 };
    });
    nav.feed.hasBadge = S.unread > 0; nav.feed.badge = S.unread;
    nav.people.hasBadge = highPeople > 0; nav.people.badge = highPeople;
    nav.evidence.hasBadge = S.packs > 0; nav.evidence.badge = S.packs;
    nav.slang.hasBadge = S.slang.pending.length > 0; nav.slang.badge = S.slang.pending.length;

    /* KPIs */
    const flagged = S.feed.filter((m) => m.sev !== 'info').length;
    const crit = S.feed.filter((m) => m.sev === 'critical').length;
    const tracked = Object.keys(S.feed.reduce((a, m) => { if (m.pid) a[m.pid] = 1; return a; }, {})).length;
    const kpis = [{ label: 'Messages scanned', value: S.feed.length }, { label: 'People tracked', value: is.home ? plist.length : tracked }, { label: 'Flagged', value: flagged }, { label: 'Critical', value: crit }];

    /* alerts mapping */
    const alertView = (a) => Object.assign({}, sevBits(a.sev), {
      from: a.from, cat: a.cat || '', time: a.time, why: a.why || '', app: a.app, isCrit: a.sev === 'critical',
      view: () => this.go('people', { sel: a.pid || S.sel }),
      evidence: () => this.go('evidence', { ev: Object.assign({}, S.ev, { pid: a.pid || 'tg', generated: false, verify: '' }) }),
      notHarass: () => this.notHarass(a),
      dismiss: () => { this.setState({ alerts: S.alerts.filter((x) => x.id !== a.id) }); this.showToast('Alert hidden. It is still logged.'); },
      open: () => a.sev === 'critical' ? this.openPanic(a.pid) : this.go('people', { sel: a.pid || S.sel })
    });

    /* home */
    const worst = plist.filter((p) => !p.safe)[0];
    const worstSev = worst ? this.pSev(worst) : 'info';
    const attn = plist.filter((p) => !p.safe && isHigh(p));
    const home = {
      headline: attn.length ? "You're protected. " + attn.length + (attn.length === 1 ? ' person needs' : ' people need') + ' attention.' : "You're protected. Nothing needs your attention.",
      sub: !S.protection ? 'Protection is paused. Turn it back on from the top bar.'
        : S.live ? 'Connected to the SafeSphere model. Watching WhatsApp, Instagram, Telegram, Snapchat and SMS.' + (plist.length ? '' : ' Start the Live Feed or import a chat to begin.')
        : 'Watching WhatsApp, Instagram, Telegram, Snapchat and SMS. Clean messages never leave this device.',
      worstClass: SEV[worstSev].cls, worstLabel: SEV[worstSev].label, statusBorder: SEV[worstSev].border,
      attention: plist.filter((p) => !p.safe).slice(0, 3).map((p) => Object.assign({ name: p.name, initials: p.initials, tagline: p.tagline, view: () => this.go('people', { sel: p.id }) }, sevBits(this.pSev(p)))),
      noAlerts: S.alerts.length === 0,
      recent: S.alerts.slice(0, 5).map(alertView)
    };

    /* feed */
    let consent = null;
    const phased = S.feed.filter((x) => x.phase);
    if (phased.length) {
      const cpid = phased[0].pid;
      const seq = S.feed.filter((x) => x.pid === cpid && x.phase).slice().reverse();
      const segs = [];
      seq.forEach((x) => { const last = segs[segs.length - 1]; if (last && last.phase === x.phase) last.n++; else segs.push({ phase: x.phase, n: 1, tip: x.time + ': ' + (x.mine ? 'you said "' + x.text + '"' : x.phase) }); });
      const cur = segs[segs.length - 1].phase;
      const curSev = { Neutral: 'info', Mutual: 'info', Unreciprocated: 'warn', Rejected: 'high', Violation: 'critical' }[cur];
      const refs = seq.filter((x) => x.mine);
      const after = seq.filter((x) => x.afterNo).length;
      const cp = people[cpid];
      consent = {
        name: cp ? cp.name : 'this person', phase: cur, sevClass: SEV[curSev].cls, border: SEV[curSev].border,
        counts: refs.length + (refs.length === 1 ? ' refusal' : ' refusals') + ' · ' + after + ' messages after no',
        segs: segs.map((g) => ({ tip: g.tip, style: 'flex: ' + g.n + ' 1 0; background: ' + D.PHASE[g.phase] })),
        summary: segs.map((g) => g.phase + (g.n > 1 ? ' ×' + g.n : '')).join(' → '),
        refusals: refs.map((x) => ({ time: x.time, text: x.text }))
      };
    }
    const fl = S.feed.filter((m) => (!S.fFlag || m.sev !== 'info') && (!S.fApp || m.app === S.fApp) && (!S.fLevel || m.sev === S.fLevel) && (!S.fq || (m.from + ' ' + m.text).toLowerCase().indexOf(S.fq.toLowerCase()) >= 0));
    const feed = {
      scenario: S.scenario,
      setScenario: (e) => { this.pauseFeed(); this.setState({ scenario: e.target.value, idx: 0, feed: [], alerts: [], unread: 0 }); },
      sp1: S.speed === 1 ? 'on' : '', sp2: S.speed === 2 ? 'on' : '', sp1on: S.speed === 1, sp2on: S.speed === 2,
      speed1: () => { this.setState({ speed: 1 }, () => { if (S.running) this.startFeed(); }); },
      speed2: () => { this.setState({ speed: 2 }, () => { if (S.running) this.startFeed(); }); },
      runLabel: S.running ? 'Pause' : (S.idx > 0 ? 'Resume' : 'Start simulation'),
      toggleRun: () => (S.running ? this.pauseFeed() : this.startFeed()),
      reset: () => {
        this.pauseFeed();
        if (S.live) {
          this.lastSender = {};
          SSApi.del('/data').then(() => { this.setState({ idx: 0, feed: [], alerts: [], unread: 0, people: {}, sel: null, linkSugg: [], evLive: {}, details: {} }); this.showToast('Demo reset. The backend memory was cleared.'); }, (e) => this.liveFail(e, 'Reset failed'));
          return;
        }
        this.setState({ idx: 0, feed: [], alerts: [], unread: 0, people: JSON.parse(JSON.stringify(D.people)) });
      },
      paused: !S.protection,
      fAll: S.fFlag ? '' : 'on', fFlag: S.fFlag ? 'on' : '',
      showAll: () => this.setState({ fFlag: false }), showFlagged: () => this.setState({ fFlag: true }),
      app: S.fApp, setApp: (e) => this.setState({ fApp: e.target.value }),
      level: S.fLevel, setLevel: (e) => this.setState({ fLevel: e.target.value }),
      q: S.fq, setQ: (e) => this.setState({ fq: e.target.value }),
      empty: fl.length === 0,
      emptyText: S.feed.length ? 'No messages match these filters.' : 'Press Start simulation to stream a scripted demo chat.',
      hasConsent: !!consent, consent: consent || {},
      items: fl.map((m) => Object.assign({}, sevBits(m.sev), {
        mine: !!m.mine, incoming: !m.mine, rejectNote: m.rejectNote || '',
        isRefusal: !!m.mine && (S.live ? !!m.refusal : true), notRefusal: !!m.mine && S.live && !m.refusal,
        hasAfterNo: !!m.afterNo && !m.safe,
        afterNoLabel: m.afterNo ? 'Message ' + m.afterNo + ' after you said no' + (m.refusals > 1 ? ' (you refused ' + m.refusals + ' times)' : '') : '',
        app: m.app, appName: D.APPN[m.app], from: m.from, time: m.time, text: m.text,
        border: m.safe ? 'bl-info' : SEV[m.sev].border,
        flagged: m.sev !== 'info' && !m.safe, hasCat: !!m.cat, cat: m.cat,
        hidden: !!m.hidden, shown: !m.hidden, media: !!m.media,
        hasWhy: !!m.why && m.sev !== 'info' && !m.safe, why: m.why,
        clean: m.sev === 'info' && !m.safe, canNotHarass: m.sev !== 'info' && !m.safe, markedSafe: !!m.safe,
        notHarass: () => this.notHarass(m),
        missed: () => { const sl = S.slang; this.setState({ slang: Object.assign({}, sl, { pending: sl.pending.concat([{ term: m.text.split(' ').slice(0, 3).join(' '), cat: 'Bullying', sev: 'warn', src: 'User', note: 'From a message you flagged as missed.' }]) }), feedback: S.feedback + 1 }); this.showToast('Logged as missed. Sent words to the Slang List for review.', { label: 'Open', action: () => this.go('slang') }); },
        checkMedia: () => { this.useSample('Pay ₹20,000 by tonight or this goes to your family and your college group.'); this.go('media'); }
      })),
      noAlerts: S.alerts.length === 0,
      alerts: S.alerts.map(alertView)
    };

    /* people */
    const pf = [['all', 'All'], ['high', 'High+'], ['known', 'Known contacts'], ['strangers', 'Strangers']];
    const pfiltered = plist.filter((p) => {
      if (S.pFilter === 'high' && !isHigh(p)) return false;
      if (S.pFilter === 'known' && p.rel === 'Stranger') return false;
      if (S.pFilter === 'strangers' && p.rel !== 'Stranger') return false;
      if (S.pq) { const hay = (p.name + ' ' + p.accounts.map((a) => a.handle).join(' ')).toLowerCase(); if (hay.indexOf(S.pq.toLowerCase()) < 0) return false; }
      return true;
    });
    const peopleV = {
      filters: pf.map((f) => ({ label: f[1], cls: S.pFilter === f[0] ? 'on' : '', pick: () => this.setState({ pFilter: f[0] }) })),
      q: S.pq, setQ: (e) => this.setState({ pq: e.target.value }),
      noMatch: pfiltered.length === 0,
      openMerge: () => { if (plist.length < 2) { this.showToast('You need at least two people to merge.'); return; } this.setState({ dlg: { kind: 'merge', a: plist[0].id, b: plist[1].id } }); },
      list: pfiltered.map((p) => Object.assign({}, sevBits(this.pSev(p)), {
        name: p.name, initials: p.initials, nAcc: p.accounts.length + (p.accounts.length === 1 ? ' account' : ' accounts'), tags: p.tags, risk: p.risk,
        riskW: 'height: 100%; width: ' + p.risk + '%', selected: S.sel === p.id,
        rowCls: S.sel === p.id ? '' : '', select: () => this.selectPerson(p.id)
      }))
    };
    const P = people[S.sel] || plist[0] || EMPTY;
    const setP = (patch) => { if (!P.id) return; const np = Object.assign({}, S.people); np[P.id] = Object.assign({}, P, patch); this.setState({ people: np }); };
    const pSev = this.pSev(P);
    const liveCall = (promise, okMsg) => promise.then(() => { if (okMsg) this.showToast(okMsg); this.refreshPeople(P.id); }, (e) => this.liveFail(e));
    const RELB = { Stranger: 'stranger', Acquaintance: 'acquaintance', Friend: 'friend', Partner: 'partner', Family: 'family', Classmate: 'acquaintance' };
    const pAccounts = S.live ? P.accounts.concat(this.pendingLinks(P.id)) : P.accounts;
    const maxAct = Math.max.apply(null, P.activity.concat([1]));
    const pd = Object.assign({}, sevBits(pSev), {
      name: P.name, initials: P.initials, rel: P.rel, risk: P.risk, nAcc: P.accounts.length + (P.accounts.length === 1 ? ' account' : ' accounts'), safe: !!P.safe,
      undoSafe: () => { if (S.live) { this.liveFeedback(P.id, false); return; } setP({ safe: false, risk: Math.min(100, P.risk + 35) }); },
      evidence: () => this.go('evidence', { ev: Object.assign({}, S.ev, { pid: P.id, generated: false, verify: '' }) }),
      alertTrusted: () => this.setState({ dlg: { kind: 'trusted', pid: P.id } }),
      notHarass: () => {
        if (P.safe || !P.id) return;
        if (S.live) { this.liveFeedback(P.id, true); this.showToast('Marked ' + P.name + ' as not harassment. The model will treat them as trusted.', { label: 'Undo', action: () => { this.liveFeedback(P.id, false); this.setState({ toast: null }); } }); return; }
        setP({ safe: true, risk: Math.max(5, P.risk - 35) }); this.setState({ feedback: S.feedback + 1 }); this.showToast('Marked ' + P.name + ' as not harassment. Alerts lowered.', { label: 'Undo', action: () => { setP({ safe: false }); this.setState({ toast: null }); } });
      },
      mute: P.mute || '', setMute: (e) => { const v = e.target.value; setP({ mute: v }); if (v) this.showToast('Alerts from ' + P.name + ' muted ' + (v === 'always' ? 'until you turn them back on' : 'for ' + v) + '. They are still logged.'); },
      howBlock: () => this.setState({ dlg: { kind: 'block', pid: P.id } }),
      accounts: pAccounts.map((a, i) => ({
        app: a.app, handle: a.handle, label: a.label, reason: a.reason, pending: a.status === 'pending', confirmed: a.status === 'confirmed',
        confirm: () => {
          if (S.live) { liveCall(SSApi.post('/people/' + P.id + '/link', { other_person_id: a.otherId }), 'Link confirmed. ' + a.handle + ' is now part of ' + P.name + '. Risk re-scored.'); return; }
          const acc = P.accounts.slice(); acc[i] = Object.assign({}, a, { status: 'confirmed' }); setP({ accounts: acc, risk: Math.min(100, P.risk + 4) }); this.showToast('Link confirmed. ' + a.handle + ' is now part of ' + P.name + '.');
        },
        split: () => {
          if (S.live) {
            if (a.status === 'pending') { this.setState({ linkSugg: (S.linkSugg || []).filter((s) => !((s.person_id === P.id && s.other_person_id === a.otherId) || (s.other_person_id === P.id && s.person_id === a.otherId))) }); this.showToast('OK, ' + a.handle + ' stays a separate person.'); return; }
            liveCall(SSApi.post('/people/' + P.id + '/unlink', { account_id: a.accountId }), 'Split out ' + a.handle + '. It is a separate person again.'); return;
          }
          const acc = P.accounts.filter((_, j) => j !== i); setP({ accounts: acc, risk: Math.max(5, P.risk - 6) }); this.showToast('Split out ' + a.handle + '. The linker will learn from this.');
        }
      })),
      timeline: P.timeline.map((t) => ({ phase: t.phase, date: t.date, tip: t.tip, style: 'flex: ' + t.w + ' 1 0; background: ' + D.PHASE[t.phase], labelStyle: 'flex: ' + t.w + ' 1 0; min-width: 0; overflow: hidden' })),
      timelineAria: 'Consent timeline: ' + P.timeline.map((t) => t.phase + ' from ' + t.date).join(', '),
      reasons: P.reasons, features: P.features,
      activity: P.activity.map((v, i) => ({ style: 'flex: 1; border-radius: 3px 3px 0 0; min-height: 2px; height: ' + Math.round((v / maxAct) * 100) + '%; background: ' + (P.night[i] / Math.max(v, 1) > 0.5 ? '#A84900' : '#FDDBB8'), tip: v + ' messages' })),
      activityAria: 'Messages per day over 14 days: ' + P.activity.join(', '),
      setRel: (e) => { const v = e.target.value; setP({ rel: v }); if (S.live && P.id) liveCall(SSApi.patch('/people/' + P.id, { relationship: RELB[v] || 'stranger' }), 'Relationship saved. Risk re-scored.'); },
      history: P.history.map((h) => ({ app: h.app, text: h.text, time: h.time, cls: '', style: 'display: flex; gap: 10px; align-items: flex-start; padding: 8px 10px; border-radius: 10px; ' + (h.flag ? 'background: var(--high-bg)' : h.mine ? 'background: var(--brandSoft)' : 'background: var(--surface2)') }))
    });

    /* media */
    const M = S.media;
    const steps = M.steps.map((s, i) => ({ n: i + 1, name: s.name, result: s.result, isWaiting: s.status === 'waiting', isRunning: s.status === 'running', isPass: s.status === 'pass', isFlag: s.status === 'flagged', statusLabel: { waiting: 'Waiting', running: 'Running', pass: 'Pass', flagged: 'Flagged' }[s.status] }));
    const media = {
      server: M.server, setServer: (e) => this.setMedia({ server: e.target.value }),
      noFile: !M.file, hasFile: !!M.file,
      isImg: !!(M.file && M.file.url && M.file.kind === 'image'), isPlaceholder: !!(M.file && !(M.file.url && M.file.kind === 'image')),
      url: M.file ? M.file.url : '',
      imgStyle: 'width: 100%; max-height: 320px; object-fit: contain; ' + (M.revealed ? '' : 'filter: blur(28px)'),
      phStyle: 'width: 100%; height: 240px; background: radial-gradient(circle at 40% 40%, #f5c6d4, #93A4B7 55%, #D05B00); ' + (M.revealed ? '' : 'filter: blur(18px)'),
      blurred: !!M.file && !M.revealed, revealed: !!M.file && M.revealed,
      askReveal: () => this.setState({ dlg: { kind: 'reveal' } }), hide: () => this.setMedia({ revealed: false }),
      name: M.file ? M.file.name : '', size: M.file ? M.file.size : '', kind: M.file ? (M.file.sample ? 'Sample from the demo chat' : M.file.kind) : '',
      dragOver: (e) => e.preventDefault(), drop: (e) => { e.preventDefault(); this.loadFile(e.dataTransfer.files[0]); },
      pick: (e) => this.loadFile(e.target.files[0]), useSample: () => this.useSample(),
      resetAll: () => this.setMedia({ file: null, revealed: false, verdict: null, steps: this.freshSteps(), error: '', context: '', running: false }),
      hasError: !!M.error, error: M.error, canRetry: !!M.file,
      context: M.context, setContext: (e) => this.setMedia({ context: e.target.value }),
      analyse: () => this.analyse(), cantAnalyse: !M.file || M.running, analyseLabel: M.running ? 'Analysing…' : 'Analyse',
      steps,
      hasVerdict: !!M.verdict,
      vClass: M.verdict ? SEV[M.verdict.sev].cls : '', vLabel: M.verdict ? SEV[M.verdict.sev].label : '', vBorder: M.verdict ? SEV[M.verdict.sev].border : '',
      verdict: M.verdict ? M.verdict.text : '', todo: M.verdict ? M.verdict.todo : [],
      toEvidence: () => this.go('evidence', { ev: Object.assign({}, S.ev, { pid: M.addTo || (S.live ? S.sel : 'tg'), generated: false, verify: '' }) }),
      addTo: M.addTo, setAddTo: (e) => {
        const v = e.target.value; this.setMedia({ addTo: v });
        if (!v) return;
        if (S.live && this.mediaCheckId) { SSApi.patch('/media/' + this.mediaCheckId, { person_id: v }).then(() => this.showToast('Added ' + (M.file ? M.file.name : 'media') + ' to ' + people[v].name + "'s evidence."), (err) => this.liveFail(err)); return; }
        this.showToast(S.live ? 'This file will be added to ' + people[v].name + "'s case when you press Analyse." : 'Added ' + (M.file ? M.file.name : 'media') + " to " + people[v].name + "'s case.");
      }
    };

    /* import */
    const I = S.imp;
    const imp = {
      isPick: I.stage === 'pick', isPreview: I.stage === 'preview', isRunning: I.stage === 'running', isDone: I.stage === 'done',
      hasError: !!I.error, error: I.error, errorSample: I.errorSample || '',
      sources: [
        { badge: 'WA', name: 'WhatsApp', how: 'Open the chat → ⋮ → More → Export chat → Without media. You get a .txt file.', btn: 'Upload .txt', accept: '.txt,text/plain', src: 'WA' },
        { badge: 'IG', name: 'Instagram', how: 'Settings → Your activity → Download your information → Messages (JSON).', btn: 'Upload .json', accept: '.json,application/json', src: 'IG' },
        { badge: 'TG', name: 'Telegram', how: 'Telegram Desktop → open the chat → ⋮ → Export chat history → JSON.', btn: 'Upload .json', accept: '.json,application/json', src: 'TG' },
        { badge: 'SMS', name: 'Screenshots (OCR)', how: 'Works for any app, including on iPhone. We read the text from the images on this device.', btn: 'Upload images', accept: 'image/*', src: 'OCR' }
      ].map((s) => Object.assign({}, s, { pick: (e) => this.importFile(s.src, e.target.files[0]), sample: () => this.importSample(s.src) })),
      badge: I.src === 'OCR' ? 'SMS' : (I.src || 'WA'), isOcr: I.src === 'OCR',
      fileName: I.fileName, count: I.count,
      summary: 'Found ' + I.count.toLocaleString() + ' messages between ' + (I.participants || []).join(' and ') + ', ' + I.range + '.',
      participants: I.participants || [], who: I.who, setWho: (e) => this.setImp({ who: e.target.value }),
      link: I.link, setLink: (e) => this.setImp({ link: e.target.value }),
      cantRun: !I.who, run: () => this.runImport(), cancel: () => this.setImp({ stage: 'pick', error: '' }),
      progress: I.progress, progressStyle: 'height: 100%; width: ' + I.progress + '%', stage: I.stageText || 'Starting…',
      result: I.result || '', resultSub: I.resultSub || '', viewPerson: () => this.go('people', { sel: I.donePid || 'rahul' })
    };

    /* evidence */
    const E = S.ev; const ep = people[E.pid] || plist[0] || EMPTY;
    const eItems = this.evItems(ep.id);
    const incCount = eItems.filter((_, i) => this.isInc(ep.id, i)).length;
    const livePack = S.live ? S.evLive[ep.id] : null;
    const CHID = { cybercrime: 'cyber', '1930': 'h1930', stopncii: 'ncii', ncw: 'ncw', platform: 'gro', '112': 'e112' };
    const order = livePack ? livePack.channels.map((c) => CHID[c.id]).filter(Boolean) : (D.chOrder[ep.id] || D.chOrder.priya);
    const firsts = livePack ? order.slice(0, 1) : (D.firsts[ep.id] || []);
    const SUGGEST = { sextortion: 'Sextortion: call 1930 and hash the image on StopNCII first. Then file on cybercrime.gov.in.',
      stalking: 'Stalking: file on cybercrime.gov.in. If you feel unsafe right now, call 112.',
      harassment_after_no: 'They kept going after you said no: file on cybercrime.gov.in and keep every message.',
      group_bullying: 'Bullying in a group: report to the platform and your school or college first.' };
    const concl = livePack && livePack.conclusion;
    const suggestText = concl
      ? concl.summary + (concl.next_steps && concl.next_steps.length ? '\n\nNext steps: ' + concl.next_steps.map((s, i) => (i + 1) + '. ' + s).join('  ') : '')
        + '\n\n' + (concl.source === 'gemini' ? 'Conclusion written by Gemini from the model\'s findings. No message text was shared. ' : '') + (concl.caution || '')
      : livePack ? (ep.level === 'info' ? '' : (SUGGEST[ep.label] || '')) : (D.suggest[ep.id] || '');
    const ev = {
      pid: ep.id, name: ep.name, setPerson: (e) => { const v = e.target.value; this.setState({ ev: Object.assign({}, E, { pid: v, generated: false, verify: '', editing: false }) }); if (S.live) this.loadPack(v); },
      empty: eItems.length === 0, hasItems: eItems.length > 0,
      includedLabel: incCount + ' of ' + eItems.length + ' items included',
      items: eItems.map((it, i) => ({
        time: it.time, app: it.app, acct: it.acct, text: it.text, cat: it.cat, isMedia: !!it.media, isText: !it.media, deleted: !!it.deleted,
        inc: this.isInc(ep.id, i), toggle: () => { const inc = Object.assign({}, E.inc); inc[ep.id + ':' + i] = !this.isInc(ep.id, i); this.setState({ ev: Object.assign({}, E, { inc, generated: false, verify: '' }) }); },
        hash: E.hashes[ep.id + ':' + i] ? E.hashes[ep.id + ':' + i].slice(0, 16) + '…' : 'Not hashed yet'
      })),
      generate: () => this.generate(), genLabel: E.generated ? 'Regenerate pack' : 'Generate pack',
      generated: E.generated, fingerprint: E.fp, jsonUrl: E.jsonUrl || '#', jsonName: 'safesphere-evidence-' + ep.id + '.json',
      pdf: () => { if (S.live) { this.pdfLive(); return; } try { window.print(); } catch (e) {} this.showToast('Opening the print dialog. Choose "Save as PDF".'); },
      verify: () => this.verify(), hasVerify: !!E.verify, verifyMsg: E.verify,
      copyHash: () => this.copyText(E.fp, 'Fingerprint copied.'),
      timeline: ep.timeline.map((t) => ({ tip: t.tip, style: 'flex: ' + t.w + ' 1 0; background: ' + D.PHASE[t.phase] })),
      timelineText: ep.timeline.map((t) => t.phase + ' (' + t.date + ')').join(' → '),
      laws: concl && concl.acts.length ? concl.acts.map((a) => ({ s: a.section, d: a.why }))
        : livePack ? livePack.legal.map((l) => ({ s: l.section, d: l.description })) : (D.laws[ep.id] || []),
      editLabel: E.editing ? 'Done editing' : 'Edit',
      toggleEdit: () => this.setState({ ev: Object.assign({}, E, { editing: !E.editing }) }),
      readOnly: !E.editing,
      complaint: E.complaints[ep.id] !== undefined ? E.complaints[ep.id] : this.complaintFor(ep.id),
      setComplaint: (e) => { const c = Object.assign({}, E.complaints); c[ep.id] = e.target.value; this.setState({ ev: Object.assign({}, E, { complaints: c }) }); },
      copyComplaint: () => this.copyText(E.complaints[ep.id] !== undefined ? E.complaints[ep.id] : this.complaintFor(ep.id), 'Complaint copied. Paste it into the portal.'),
      hasSuggest: !!suggestText, suggest: suggestText,
      channels: order.map((k) => { const c = D.CH[k]; const first = firsts.indexOf(k) >= 0; return { name: c.name, desc: c.desc, first, hasLink: !!c.link, link: c.link || '', hasTel: !!c.tel, tel: c.tel || '', telLabel: c.telLabel || '', hasGuide: !!c.guide, guide: () => this.setState({ dlg: { kind: 'grievance', pid: ep.id } }), style: 'padding: 16px; display: flex; flex-direction: column; gap: 10px; ' + (first ? 'border: 2px solid var(--brand)' : '') }; })
    };

    /* metrics */
    const md = this.metData();
    const pct = (v) => Math.round(v * 100) + '%';
    const dec = (v) => (Math.round(v * 100) / 100).toFixed(2);
    const mk = [['Precision', 'precision'], ['Recall', 'recall'], ['F1', 'f1'], ['Detection rate', 'detection_rate']];
    const cmCat = md.categories.find((c) => c.name === S.met.cm) || md.categories[0] || { name: '', precision: 1, recall: 0, f1: 0 };
    const pos = 100, tp = Math.round(pos * cmCat.recall), fn = pos - tp, fp = Math.round(tp / (cmCat.precision || 1) - tp), tn = 300 - fp;
    const cell = (v, max, good) => 'padding: 14px 6px; text-align: center; border-radius: 8px; font-weight: 800; color: ' + (v / max > 0.45 ? '#fff' : 'var(--ink)') + '; background: ' + (good ? 'rgba(208,91,0,' : 'rgba(226,98,43,') + (0.12 + 0.75 * (v / max)).toFixed(2) + ')';
    const met = {
      sample: !S.met.loaded, loaded: S.met.loaded, file: S.met.file,
      sampleText: S.live ? 'Loading metrics from the backend…' : 'Sample values (demo mode: backend offline). Start the backend to load the real evaluation.',
      load: (e) => this.loadMetrics(e.target.files[0]),
      running: S.met.running, runLabel: S.met.running ? 'Loading…' : (S.live ? 'Reload from backend' : 'Run evaluation'),
      run: () => {
        this.setState({ met: Object.assign({}, S.met, { running: true }) });
        if (S.live) { this.loadLiveMetrics(true); return; }
        this.later(() => { this.setState({ met: Object.assign({}, this.state.met, { running: false }) }); this.showToast('The backend is not connected. Showing sample values.'); }, 1200);
      },
      farSS: pct(md.banter_false_alarm.safesphere), farKW: pct(md.banter_false_alarm.keyword),
      link: md.linking_accuracy == null ? (S.live ? 'Not measured yet' : pct(0.88)) : pct(md.linking_accuracy),
      dataset: (md.dataset || {}).size || '[N] messages', sources: (md.dataset || {}).sources || '',
      bars: mk.map((m) => { const kw = md.overall.keyword[m[1]] || 0, ss = md.overall.safesphere[m[1]] || 0; return { label: m[0], kw: dec(kw), ss: dec(ss), kwStyle: 'width: 100%; border-radius: 6px 6px 0 0; background: #93A4B7; height: ' + Math.round(kw * 180) + 'px', ssStyle: 'width: 100%; border-radius: 6px 6px 0 0; background: var(--brand); height: ' + Math.round(ss * 180) + 'px' }; }),
      chartAria: mk.map((m) => m[0] + ': keyword ' + dec(md.overall.keyword[m[1]] || 0) + ', SafeSphere ' + dec(md.overall.safesphere[m[1]] || 0)).join('; '),
      cats: md.categories.map((c) => ({ name: c.name, p: dec(c.precision), r: dec(c.recall), f: dec(c.f1) })),
      cmCat: cmCat.name, setCm: (e) => this.setState({ met: Object.assign({}, S.met, { cm: e.target.value }) }),
      cm: { tp, fn, fp, tn, tpStyle: cell(tp, tn, true), fnStyle: cell(fn, tn, false), fpStyle: cell(fp, tn, false), tnStyle: cell(tn, tn, true) },
      deep: (md.deepfake || []).map((d) => ({ t: d.type, dr: d.detection_rate == null ? 'Add after connecting' : pct(d.detection_rate), fa: d.false_alarm == null ? '–' : pct(d.false_alarm) }))
    };

    /* slang */
    const SL = S.slang;
    const allTerms = SL.terms;
    const catOpts = ['Refusal signal', 'Bullying', 'Sextortion', 'Extortion', 'Stalking', 'Threat', 'Sexual harassment', 'Self-harm incitement'];
    const dict = [];
    allTerms.forEach((t) => { [t.term].concat(t.variants.split(',')).forEach((v) => { const n = this.norm(v.trim()); if (n) dict.push({ n, t }); }); });
    const normText = this.norm(SL.test || '');
    const words = normText.split(/\s+/).filter(Boolean);
    const hit = new Array(words.length).fill(null);
    dict.forEach((d) => { const dw = d.n.split(' '); for (let i = 0; i + dw.length <= words.length; i++) { if (dw.every((w, j) => words[i + j] === w)) { for (let j = 0; j < dw.length; j++) hit[i + j] = d.t; } } });
    const matched = []; hit.forEach((h) => { if (h && matched.indexOf(h) < 0) matched.push(h); });
    const sevBg = { info: 'var(--brandSoft)', warn: 'var(--warn-bg)', high: 'var(--high-bg)', critical: 'var(--crit-bg)' };
    const slang = {
      q: SL.q, setQ: (e) => this.setSlang({ q: e.target.value }), cat: SL.cat, setCat: (e) => this.setSlang({ cat: e.target.value }), catOpts,
      adding: SL.adding, toggleAdd: () => this.setSlang({ adding: !SL.adding }), form: SL.form,
      setTerm: (e) => this.setSlang({ form: Object.assign({}, SL.form, { term: e.target.value }) }),
      setFCat: (e) => this.setSlang({ form: Object.assign({}, SL.form, { cat: e.target.value }) }),
      setFSev: (e) => this.setSlang({ form: Object.assign({}, SL.form, { sev: e.target.value }) }),
      setVar: (e) => this.setSlang({ form: Object.assign({}, SL.form, { variants: e.target.value }) }),
      suggest: () => { const t = SL.form.term.trim(); if (!t) { this.showToast('Type a term first.'); return; } const v = [t.replace(/a/g, '@'), t.replace(/o/g, '0').replace(/i/g, '1'), t.replace(/(.)/, '$1$1'), t.replace(/ /g, '')].filter((x, i, a) => x !== t && a.indexOf(x) === i); this.setSlang({ form: Object.assign({}, SL.form, { variants: v.join(', ') }) }); this.showToast('Suggested ' + v.length + ' variants. Edit them before saving.'); },
      save: () => { const f = SL.form; if (!f.term.trim()) { this.showToast('Type a term first.'); return; } this.setSlang({ terms: [{ term: f.term.trim(), cat: f.cat, sev: f.sev, variants: f.variants || '-', src: 'User', date: 'Today' }].concat(SL.terms), adding: false, form: { term: '', cat: 'Bullying', sev: 'warn', variants: '' }, log: [{ t: 'Added "' + f.term.trim() + '"', when: 'just now' }].concat(SL.log) }); this.showToast('Added "' + f.term.trim() + '" to the Slang List.'); },
      terms: allTerms.filter((t) => (!SL.cat || t.cat === SL.cat) && (!SL.q || (t.term + ' ' + t.variants).toLowerCase().indexOf(SL.q.toLowerCase()) >= 0)).map((t) => ({ term: t.term, cat: t.cat, sevClass: SEV[t.sev].cls, sevLabel: SEV[t.sev].label, variants: t.variants, src: t.src, date: t.date })),
      noPending: SL.pending.length === 0,
      pending: SL.pending.map((p, i) => ({ term: p.term, src: p.src, note: p.note,
        approve: () => this.setSlang({ terms: [{ term: p.term, cat: p.cat, sev: p.sev, variants: '-', src: p.src, date: 'Today' }].concat(SL.terms), pending: SL.pending.filter((_, j) => j !== i), log: [{ t: 'Approved "' + p.term + '"', when: 'just now' }].concat(SL.log) }),
        reject: () => this.setSlang({ pending: SL.pending.filter((_, j) => j !== i), log: [{ t: 'Rejected "' + p.term + '"', when: 'just now' }].concat(SL.log) }),
        edit: () => this.setSlang({ adding: true, form: { term: p.term, cat: p.cat, sev: p.sev, variants: '' }, pending: SL.pending.filter((_, j) => j !== i) })
      })),
      test: SL.test, setTest: (e) => this.setSlang({ test: e.target.value }),
      tokens: words.map((w, i) => ({ w, style: hit[i] ? 'background: ' + sevBg[hit[i].sev] + '; border-radius: 4px; padding: 1px 3px; font-weight: 800' : '' })),
      matchText: matched.length ? 'Matched: ' + matched.map((m) => m.term + ' (' + m.cat + ', ' + SEV[m.sev].label + ')').join(' · ') : 'No terms matched.',
      log: SL.log.slice(0, 5)
    };

    /* settings */
    const ST = S.set;
    const setSet = (patch) => this.setState({ set: Object.assign({}, ST, patch) });
    const sw = (label, on, toggle, hint) => ({ label, hint: hint || '', hasHint: !!hint, isSwitch: true, on, onCls: on ? 'on' : '', toggle });
    const segRow = (label, value, opts, pick, hint) => ({ label, hint: hint || '', hasHint: !!hint, isSeg: true, opts: opts.map((o) => ({ label: o, cls: o === value ? 'on' : '', pick: () => pick(o) })) });
    const btnRow = (label, btn, click, danger, hint) => ({ label, hint: hint || '', hasHint: !!hint, isBtn: true, btn, click, btnCls: danger ? 'btn btn-sm btn-danger' : 'btn btn-sm' });
    const txt = (label, value) => ({ label, isText: true, value, hasHint: false });
    const appNames = { WA: 'WhatsApp', IG: 'Instagram', TG: 'Telegram', SNAP: 'Snapchat', MSG: 'Messenger', SMS: 'SMS' };
    const C0 = S.conn;
    const backendRows = [
      txt('Status', C0.status === 'online' ? 'Connected (live model)' : C0.status === 'checking' ? 'Connecting…' : 'Offline: demo mode with sample data'),
      txt('Backend address', C0.base || SSApi.base())
    ].concat(C0.status === 'online' ? [txt('Behaviour model', C0.model || 'loaded'), txt('Deepfake connector', C0.deepfake === 'stub' ? 'Stub: placeholder results until your model is connected' : C0.deepfake)] : [])
      .concat(C0.error ? [txt('Last error', C0.error)] : [])
      .concat([btnRow('Reconnect', 'Reconnect', () => this.connect(), false, 'Open the page with ?api=<url> to use another backend, and ?key=<key> if it needs an API key.')]);
    const set = { groups: [
      { title: 'Backend', rows: backendRows },
      { title: 'Protection', rows: [sw('Monitoring', S.protection, () => this.setState({ protection: !S.protection }))].concat(Object.keys(ST.apps).map((k) => sw('Watch ' + appNames[k], ST.apps[k], () => setSet({ apps: Object.assign({}, ST.apps, { [k]: !ST.apps[k] }) })))).concat([segRow('Alert sensitivity', ST.sensitivity, ['Low', 'Balanced', 'High'], (o) => setSet({ sensitivity: o }), 'High catches more but may alert on banter.')]) },
      { title: 'People', rows: [txt('Trusted contact', ST.trusted), btnRow('Add a trusted contact', '+ Add', () => this.showToast('Add contact: name and phone number (prototype).')), btnRow('Known and safe contacts', 'Manage', () => this.go('people', { pFilter: 'known' }))] },
      { title: 'Face', rows: [btnRow('Face enrolment', 'Re-enrol face', () => this.showToast('Face re-enrolled. Your face data stays on this device.'), false, 'Used only to tell you if a fake image shows your face.'), btnRow('Face data', 'Delete face data', () => this.setState({ dlg: { kind: 'delface' } }), true)] },
      { title: 'Discretion', rows: [sw('Quick Exit button', ST.quickExit, () => setSet({ quickExit: !ST.quickExit })), sw('Disguised app name and icon', ST.disguise, () => setSet({ disguise: !ST.disguise }), 'Shows as "Notes" on your home screen.'), sw('Hide notification previews', ST.hidePreviews, () => setSet({ hidePreviews: !ST.hidePreviews }), 'Never show message text on the lock screen.')] },
      { title: 'Privacy', rows: [sw('Upload flagged items only', ST.uploadFlagged, () => setSet({ uploadFlagged: !ST.uploadFlagged }), 'Clean messages never leave this device.'), btnRow('Export my data', 'Export', () => this.showToast('Your data export is ready (prototype).')), btnRow('Delete all data', 'Delete all data', () => this.setState({ dlg: { kind: 'delall' } }), true, 'This cannot be undone.')] },
      { title: 'Language and theme', rows: [segRow('Language', S.lang === 'en' ? 'English' : 'हिंदी', ['English', 'हिंदी'], (o) => this.setState({ lang: o === 'English' ? 'en' : 'hi' })), segRow('Theme', S.theme === 'dark' ? 'Dark' : 'Light', ['Light', 'Dark'], (o) => this.setState({ theme: o.toLowerCase() }))] },
      { title: 'About', rows: [txt('Model versions', 'Text v0.3 · Linker v0.2 · Deepfake v0.1'), txt('Feedback given', S.feedback + ' items'), txt('Helplines', '1930 · 181 · 112 · Tele-MANAS 14416')] }
    ] };

    /* dialog */
    const G = S.dlg;
    const close = () => this.setState({ dlg: null });
    let dlg = { show: false, title: '', body: '', hasOk: false, ok: close, okLabel: 'OK', okCls: 'btn btn-primary', cancel: close, cancelLabel: 'Cancel', isMerge: false, a: '', b: '', setA: () => {}, setB: () => {} };
    if (G) {
      dlg.show = true;
      if (G.kind === 'reveal') Object.assign(dlg, { title: 'Show this media?', body: 'It may contain explicit or upsetting content. You can hide it again at any time.', hasOk: true, okLabel: 'Reveal', ok: () => { this.setMedia({ revealed: true }); close(); } });
      if (G.kind === 'trusted') { const p = people[G.pid] || people[S.panicPid]; Object.assign(dlg, { title: 'Alert ' + ST.trusted.split(' ·')[0] + '?', body: 'We will send this text message:\n\n"Hi, I\'m getting threatening messages from ' + p.name + '. SafeSphere has saved the evidence. Can you call me when you see this?"', hasOk: true, okLabel: 'Send message', ok: () => { close(); this.showToast('Message sent to ' + ST.trusted.split(' ·')[0] + '.'); } }); }
      if (G.kind === 'block') { const p = people[G.pid]; const steps = { WA: 'WhatsApp: open the chat → tap the name → Block. Keep the chat; don\'t delete it.', IG: 'Instagram: open the profile → ⋯ → Block. Choose "Block this and new accounts they create".', TG: 'Telegram: open the chat → ⋮ → Block user. Report it as "Other: threats".', SMS: 'SMS: open the conversation → Details → Block number.', SNAP: 'Snapchat: press and hold the name → Manage friendship → Block.' }; const apps = []; p.accounts.forEach((a) => { if (apps.indexOf(a.app) < 0) apps.push(a.app); }); Object.assign(dlg, { title: 'How to block ' + p.name, body: apps.map((a) => steps[a] || '').join('\n\n') + '\n\nSave the evidence pack before blocking. Blocking can hide their earlier messages.', cancelLabel: 'Close' }); }
      if (G.kind === 'grievance') Object.assign(dlg, { title: 'Reach the Grievance Officer', body: 'In the app, go to Settings → Help → Report a problem, or search "[app name] grievance officer India" for the official contact form.\n\nAttach your evidence pack fingerprint. Platforms must acknowledge complaints quickly under the IT Rules, 2021.', cancelLabel: 'Close' });
      if (G.kind === 'delface') Object.assign(dlg, { title: 'Delete face data?', body: 'We will no longer be able to tell you if a fake image shows your face.', hasOk: true, okLabel: 'Delete', okCls: 'btn btn-danger', ok: () => { close(); this.showToast('Face data deleted.'); } });
      if (G.kind === 'delall') Object.assign(dlg, { title: 'Delete all data?', body: 'This removes every message, person, evidence pack and setting from this device. It cannot be undone.', hasOk: true, okLabel: 'Delete everything', okCls: 'btn btn-danger', ok: () => {
        this.stopTimers();
        if (S.live) {
          close();
          SSApi.del('/data').then(() => { this.lastSender = {}; this.setState(Object.assign(this.initialState(), { live: true, conn: S.conn, people: {}, sel: null, screen: 'home', met: S.met })); this.showToast('All data deleted from the backend and this page.'); }, (e) => this.liveFail(e, 'Delete failed'));
          return;
        }
        this.setState(Object.assign(this.initialState(), { dlg: null, screen: 'home', conn: S.conn })); this.showToast('All data deleted.');
      } });
      if (G.kind === 'merge') Object.assign(dlg, { title: 'Merge two people', body: 'Use this when you know two entries are the same person.', isMerge: true, a: G.a, b: G.b, setA: (e) => this.setState({ dlg: Object.assign({}, G, { a: e.target.value }) }), setB: (e) => this.setState({ dlg: Object.assign({}, G, { b: e.target.value }) }), hasOk: true, okLabel: 'Merge', ok: () => { if (G.a === G.b) { this.showToast('Choose two different people.'); return; }
        if (S.live) { this.setState({ dlg: null }); SSApi.post('/people/' + G.a + '/link', { other_person_id: G.b }).then(() => { this.showToast('Merged ' + people[G.b].name + ' into ' + people[G.a].name + '. Risk re-scored.'); this.setState({ sel: G.a }); this.refreshPeople(G.a); }, (e) => this.liveFail(e, 'Merge failed')); return; }
        const np = Object.assign({}, people); const A = np[G.a], B = np[G.b]; np[G.a] = Object.assign({}, A, { accounts: A.accounts.concat(B.accounts.map((x) => Object.assign({}, x, { label: 'Merged by you', status: 'confirmed' }))), risk: Math.max(A.risk, B.risk), tags: A.tags.concat(B.tags.filter((t) => A.tags.indexOf(t) < 0)) }); delete np[G.b]; this.setState({ people: np, dlg: null, sel: G.a }); this.showToast('Merged ' + B.name + ' into ' + A.name + '.'); } });
    }

    /* panic */
    const PP = people[S.panicPid] || plist[0] || EMPTY;
    const LIVEWHAT = { sextortion: PP.name + ' is threatening you or demanding money. Don\'t pay and don\'t reply.',
      harassment_after_no: PP.name + ' kept messaging you after you said no. You did the right thing by saying no.',
      stalking: PP.name + ' is contacting you obsessively and may be tracking where you are.',
      group_bullying: 'You are being targeted in a group chat.' };
    const what = (S.live ? (LIVEWHAT[PP.label] || (PP.reasons[0] ? PP.reasons[0].pre : '')) : { vikram: 'Vikram S ignored your "no" three times and is threatening to share your photos. You did the right thing by saying no.', tg: 'Someone sent a manipulated intimate image of you with a money demand.', rahul: 'Rahul K is following you and has threatened to come to your home.', arjun: 'You are being insulted in a group chat.' }[PP.id]) || 'Here is what to do right now.';
    const C = S.checks;
    const cks = [['ev', 'Evidence saved (done automatically)'], ['ncii', 'Hash the image on StopNCII'], ['call', 'Call 1930'], ['report', 'Report on cybercrime.gov.in'], ['tell', 'Tell someone you trust']];
    const panic = {
      open: S.panic, what,
      steps: cks.map((c) => ({ label: c[1], done: !!C[c[0]], style: C[c[0]] ? 'text-decoration: line-through; color: var(--muted)' : 'font-weight: 600', toggle: () => this.setState({ checks: Object.assign({}, C, { [c[0]]: !C[c[0]] }) }) })),
      doneCount: cks.filter((c) => C[c[0]]).length,
      trusted: () => this.setState({ dlg: { kind: 'trusted', pid: PP.id } }),
      evidence: () => this.go('evidence', { panic: false, ev: Object.assign({}, S.ev, { pid: PP.id, generated: false, verify: '' }) }),
      close: () => this.setState({ panic: false })
    };

    /* bell */
    const bell = { open: S.bell, hasCount: S.alerts.length > 0, count: S.alerts.length, empty: S.alerts.length === 0, items: S.alerts.slice(0, 5).map(alertView) };

    const T2 = S.toast;
    return {
      conn: S.conn.status === 'online'
        ? { label: '● Live model', title: 'Connected to ' + S.conn.base + (S.conn.deepfake === 'stub' ? ' · deepfake connector: stub' : ''), style: 'background: var(--brandSoft); color: var(--brand); border: 0; cursor: pointer', click: () => this.go('settings') }
        : S.conn.status === 'checking'
          ? { label: 'Connecting…', title: 'Looking for the backend at ' + SSApi.base(), style: 'background: var(--surface2); color: var(--muted); border: 0', click: () => {} }
          : { label: 'Demo mode · backend offline', title: 'Showing sample data. ' + (S.conn.error || '') + ' Click to retry.', style: 'background: var(--warn-bg); color: var(--warn-ink); border: 0; cursor: pointer', click: () => this.connect() },
      themeClass: S.theme === 'dark' ? 'dark' : '', t: T, exitMode: S.exit, appMode: !S.exit,
      forecast: [{ d: 'Thu', s: 'Light rain', t: '28° / 24°' }, { d: 'Fri', s: 'Cloudy', t: '29° / 24°' }, { d: 'Sat', s: 'Sunny', t: '31° / 25°' }, { d: 'Sun', s: 'Sunny', t: '31° / 25°' }, { d: 'Mon', s: 'Partly cloudy', t: '30° / 24°' }],
      quickExit: () => { this.pauseFeed(); this.setState({ exit: true, panic: false, dlg: null, toast: null, bell: false }); },
      leaveExit: () => this.setState({ exit: false }),
      protection: { label: S.protection ? 'Protection active' : 'Protection paused', aria: S.protection ? 'Protection active. Click to pause.' : 'Protection paused. Click to resume.', dot: 'width: 9px; height: 9px; border-radius: 50%; background: ' + (S.protection ? '#2f9e6e' : '#c98a00'), toggle: () => { this.setState({ protection: !S.protection }); this.showToast(S.protection ? 'Protection paused. Messages are not being scanned.' : 'Protection resumed.'); } },
      toggleBell: () => this.setState({ bell: !S.bell }), bell,
      toggleLang: () => this.setState({ lang: S.lang === 'en' ? 'hi' : 'en' }), langLabel: S.lang === 'en' ? 'हिं' : 'EN',
      toggleTheme: () => this.setState({ theme: S.theme === 'dark' ? 'light' : 'dark' }), themeLabel: S.theme === 'dark' ? 'Light' : 'Dark',
      openHelp: () => this.openPanic(S.panicPid),
      startFromHome: () => { this.go('feed'); this.startFeed(); },
      nav, is, kpis, home, feed, people: peopleV, pd, media, imp, ev, met, slang, set, dlg, panic, peopleOpts,
      toast: { show: !!T2, text: T2 ? T2.text : '', hasAction: !!(T2 && T2.action), actionLabel: T2 ? T2.actionLabel : '', action: () => { if (T2 && T2.action) T2.action(); }, close: () => this.setState({ toast: null }), border: T2 && T2.sev ? SEV[T2.sev].border : 'bl-none' }
    };
  }
}

DCMount(document.getElementById('tpl').textContent, Component);
