/* SafeSphere Guard core: pure logic shared by the content script (as self.SSGCore) and Node tests.
   No DOM, no chrome.* here. All harm judgement comes from the backend; this file only decides what to send,
   how to word guidance, and when to blur. */
(function (root) {
  const LEVELS = ['info', 'warn', 'high', 'critical'];
  const MEDIA_TEXT = { image: '📷 Photo', video: '🎥 Video', audio: '🎤 Voice message' };
  const esc = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const mentionRe = (name, flags) => new RegExp('@' + esc(name) + '(?![\\w])', flags);

  function mentions(text, selfName) {
    return !!text && !!selfName && mentionRe(selfName, 'i').test(text);
  }

  /* Only messages aimed at the user feed the engine: everyday room chatter between others would cause false alarms. */
  function isTargeting(rec, selfName, selfId) {
    return !!rec.isSelf || (!!selfId && rec.replyTo === selfId) || mentions(rec.text, selfName);
  }

  /* rec -> body for POST /ingest/notification, or null when it should not be sent.
     ctx = {room, selfName, selfId, members: {id: name}, lastTargeter: {id, name} | null}; ctx is updated. */
  function toNotification(rec, ctx) {
    if (!rec.isSelf && rec.senderId) ctx.members[rec.senderId] = rec.senderName || rec.senderId;
    if (!isTargeting(rec, ctx.selfName, ctx.selfId)) return null;
    let text = rec.text || '';
    if (!rec.isSelf) text = text.replace(new RegExp(mentionRe(ctx.selfName, '').source + '[,:]?\\s*', 'gi'), '').trim() || text;
    if (!text && rec.media) text = MEDIA_TEXT[rec.media] || '';
    const base = { app: 'web', text: text || null, timestamp: rec.time, room: rec.room || ctx.room,
      relationship: 'acquaintance', media_type: rec.media || null };
    if (rec.isSelf) {
      // the user's own message belongs to the chat with the member they answer, else the last one who targeted them
      let target = null;
      if (rec.replyTo && rec.replyTo !== ctx.selfId && ctx.members[rec.replyTo]) target = { id: rec.replyTo, name: ctx.members[rec.replyTo] };
      else if (ctx.lastTargeter) target = ctx.lastTargeter;
      if (!target) return null;
      return Object.assign({ sender: target.name, sender_handle: target.id }, base, { is_user: true });
    }
    ctx.lastTargeter = { id: rec.senderId, name: rec.senderName || rec.senderId };
    return Object.assign({ sender: ctx.lastTargeter.name, sender_handle: rec.senderId }, base, { is_user: false });
  }

  /* From an ingest response's people[]: this sender's own level and the room's level. */
  function levelsFor(people, senderId, room) {
    const member = (people || []).find((p) => !p.is_room && (p.accounts || []).some((a) => a.handle === senderId));
    const rm = (people || []).find((p) => p.is_room && p.display_name === room);
    return { member: member ? member.level : null, roomLevel: rm ? rm.level : null,
      memberPid: member ? member.id : null, roomPid: rm ? rm.id : null };
  }

  const atLeastHigh = (lv) => LEVELS.indexOf(lv) >= 2;

  /* Blur only when words AND behaviour agree: friends' banter uses the same words. */
  function shouldBlur(flagged, memberLevel, roomLevel) {
    return !!flagged && (atLeastHigh(memberLevel) || atLeastHigh(roomLevel));
  }

  /* An alert is raised when a person first reaches high/critical; later messages can sharpen the behaviour type
     (e.g. a short chat that turns into a money demand). Cards follow the person's current view while it stays
     high/critical. */
  function currentAlert(alert, person) {
    if (!person || !atLeastHigh(person.level)) return alert;
    return Object.assign({}, alert, { level: person.level, label: person.label, reasons: person.reasons || alert.reasons });
  }

  const HIGH_STEPS = ["Don't reply or argue: it usually makes them escalate.",
    'Mute them or leave the room for now.',
    'Save evidence: generate the evidence pack below (each message gets a SHA-256 fingerprint).',
    'Report the accounts to the platform, and on cybercrime.gov.in if it continues.'];
  const ROOM_STEPS = ["Don't reply to the group: a pile-on feeds on reactions.",
    'Leave or mute the room, and tell someone you trust (a friend, teacher or parent).',
    'Save evidence: generate the evidence pack below (each message gets a SHA-256 fingerprint).',
    "Report the room to the platform; for school or college groups, also the institution's committee."];
  const SEXTORTION_STEPS = ["Don't pay, don't delete, don't reply.",
    'Call 1930 (cyber crime helpline) right away if money was demanded.',
    'Hash the image on StopNCII.org so it is blocked from being re-uploaded.',
    'File a complaint on cybercrime.gov.in (Women/Child section) with the evidence pack.'];

  /* alert: one of new_alerts; people: the ingest response's people[] */
  function guidance(alert, people) {
    const p = (people || []).find((x) => x.id === alert.person_id) || {};
    const name = p.display_name || 'Someone';
    const critical = alert.level === 'critical';
    let title, steps;
    if (p.is_room) {
      title = (p.accounts || []).length + ' members of ' + name + ' are targeting you';
      steps = ROOM_STEPS;
    } else if (alert.label === 'sextortion') {
      title = name + ' is threatening you or demanding money';
      steps = SEXTORTION_STEPS;
    } else if (alert.label === 'harassment_after_no') {
      title = name + ' keeps contacting you after you said no';
      steps = HIGH_STEPS;
    } else if (alert.label === 'stalking') {
      title = name + ' is persistently targeting you';
      steps = HIGH_STEPS;
    } else {
      title = name + ' is sending you harmful messages';
      steps = HIGH_STEPS;
    }
    if (critical && p.is_room !== true && alert.label !== 'sextortion') steps = ['If you feel unsafe right now, call 112.'].concat(steps);
    return { title, body: (alert.reasons || []).slice(0, 4), steps: steps.slice(), critical };
  }

  function describeError(err) {
    if (err && (err.name === 'TypeError' || /fetch|network/i.test(err.message || ''))) {
      return 'SafeSphere backend not reachable. Start it (run.bat) and check the address in the extension popup.';
    }
    return 'SafeSphere backend error' + (err && err.status ? ' ' + err.status : '') + ': ' + ((err && err.message) || err);
  }

  const api = { LEVELS, mentions, isTargeting, toNotification, levelsFor, shouldBlur, currentAlert, guidance, describeError };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.SSGCore = api;
})(typeof self !== 'undefined' ? self : this);
