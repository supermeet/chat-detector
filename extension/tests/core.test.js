// Run from the repo root:  node --test extension/tests/
const test = require('node:test');
const assert = require('node:assert/strict');
const C = require('../lib/core.js');

const ctx = () => ({ room: 'Class 12-B', selfName: 'Priya', selfId: 'priya', members: {}, lastTargeter: null });
const rec = (o) => Object.assign({ room: 'Class 12-B', senderId: 'rohan', senderName: 'Rohan K', isSelf: false,
  text: 'hi', time: '2026-10-28T19:00:00', replyTo: null, media: null }, o);

test('mentions: case-insensitive, whole name only', () => {
  assert.equal(C.mentions('@priya full chapri hai tu', 'Priya'), true);
  assert.equal(C.mentions('hey @PRIYA!', 'Priya'), true);
  assert.equal(C.mentions('@Priyanka hi', 'Priya'), false);
  assert.equal(C.mentions('priya hi', 'Priya'), false);
  assert.equal(C.mentions(null, 'Priya'), false);
});

test('isTargeting: self, reply to self, mention', () => {
  assert.equal(C.isTargeting(rec({ isSelf: true }), 'Priya', 'priya'), true);
  assert.equal(C.isTargeting(rec({ replyTo: 'priya', text: 'loser' }), 'Priya', 'priya'), true);
  assert.equal(C.isTargeting(rec({ text: '@Priya loser' }), 'Priya', 'priya'), true);
  assert.equal(C.isTargeting(rec({ text: 'kal ka test?' }), 'Priya', 'priya'), false);
  assert.equal(C.isTargeting(rec({ replyTo: 'kunal', text: 'notes' }), 'Priya', 'priya'), false);
});

test('toNotification: member message aimed at the user', () => {
  const c = ctx();
  const n = C.toNotification(rec({ text: '@Priya full chapri hai tu' }), c);
  assert.deepEqual(n, { app: 'web', sender: 'Rohan K', sender_handle: 'rohan', text: 'full chapri hai tu',
    timestamp: '2026-10-28T19:00:00', is_user: false, room: 'Class 12-B', relationship: 'acquaintance', media_type: null });
  assert.deepEqual(c.lastTargeter, { id: 'rohan', name: 'Rohan K' });
  assert.equal(c.members.rohan, 'Rohan K');
});

test('toNotification: bystander chatter dropped, but member name remembered', () => {
  const c = ctx();
  assert.equal(C.toNotification(rec({ senderId: 'kunal', senderName: 'Kunal', text: 'kal ka test?' }), c), null);
  assert.equal(c.lastTargeter, null);
  assert.equal(c.members.kunal, 'Kunal');
});

test('toNotification: self reply goes to the member replied to', () => {
  const c = ctx();
  C.toNotification(rec({ senderId: 'kabir', senderName: 'Kabir', text: 'x' }), c);   // seen, not targeting
  C.toNotification(rec({ text: '@Priya loser' }), c);
  const n = C.toNotification(rec({ isSelf: true, senderId: 'priya', senderName: 'Priya', text: 'stop', replyTo: 'kabir' }), c);
  assert.equal(n.sender_handle, 'kabir');
  assert.equal(n.sender, 'Kabir');
  assert.equal(n.is_user, true);
});

test('toNotification: self message without reply goes to last targeter', () => {
  const c = ctx();
  C.toNotification(rec({ text: '@Priya loser' }), c);
  const n = C.toNotification(rec({ isSelf: true, senderId: 'priya', senderName: 'Priya', text: 'please stop' }), c);
  assert.equal(n.sender_handle, 'rohan');
});

test('toNotification: self message with no target is dropped', () => {
  assert.equal(C.toNotification(rec({ isSelf: true, senderId: 'priya', text: 'hello all' }), ctx()), null);
});

test('toNotification: media without text uses the notification label', () => {
  const n = C.toNotification(rec({ text: '', media: 'image', replyTo: 'priya' }), ctx());
  assert.equal(n.text, '📷 Photo');
  assert.equal(n.media_type, 'image');
});

test('toNotification: bare mention keeps its text', () => {
  assert.equal(C.toNotification(rec({ text: '@Priya' }), ctx()).text, '@Priya');
});

const people = [
  { id: 'p1', display_name: 'Rohan K', is_room: false, level: 'warn', accounts: [{ handle: 'rohan' }] },
  { id: 'p2', display_name: 'Class 12-B', is_room: true, level: 'critical', accounts: [{ handle: 'Class 12-B/rohan' }, { handle: 'Class 12-B/sneha' }] },
];

test('levelsFor: member and room levels', () => {
  assert.deepEqual(C.levelsFor(people, 'rohan', 'Class 12-B'), { member: 'warn', roomLevel: 'critical', memberPid: 'p1', roomPid: 'p2' });
  assert.deepEqual(C.levelsFor(people, 'nobody', 'Other'), { member: null, roomLevel: null, memberPid: null, roomPid: null });
});

test('shouldBlur: flagged words alone are not enough', () => {
  assert.equal(C.shouldBlur(true, 'warn', 'info'), false);
  assert.equal(C.shouldBlur(true, 'high', null), true);
  assert.equal(C.shouldBlur(true, 'warn', 'critical'), true);
  assert.equal(C.shouldBlur(false, 'critical', 'critical'), false);
});

test('guidance: room pile-on', () => {
  const g = C.guidance({ person_id: 'p2', level: 'critical', label: 'group_bullying', reasons: ['r1'] }, people);
  assert.equal(g.title, '2 members of Class 12-B are targeting you');
  assert.equal(g.critical, true);
  assert.ok(g.steps.some((s) => /evidence/i.test(s)));
});

test('guidance: after a no / stalking', () => {
  const g = C.guidance({ person_id: 'p1', level: 'high', label: 'harassment_after_no', reasons: [] }, people);
  assert.equal(g.title, 'Rohan K keeps contacting you after you said no');
  assert.equal(g.critical, false);
  assert.equal(C.guidance({ person_id: 'p1', level: 'high', label: 'stalking', reasons: [] }, people).title,
    'Rohan K is persistently targeting you');
});

test('guidance: sextortion starts with the panic rule', () => {
  const g = C.guidance({ person_id: 'p1', level: 'critical', label: 'sextortion', reasons: [] }, people);
  assert.equal(g.steps[0], "Don't pay, don't delete, don't reply.");
  assert.ok(g.steps.join(' ').includes('1930'));
  assert.ok(g.steps.join(' ').includes('StopNCII.org'));
  assert.ok(g.steps.join(' ').includes('cybercrime.gov.in'));
});

test('describeError: network vs http', () => {
  assert.match(C.describeError(new TypeError('Failed to fetch')), /not reachable/);
  assert.match(C.describeError({ status: 503, message: 'model missing' }), /503/);
});

test('currentAlert: card follows the person as the pattern becomes clearer', () => {
  const alert = { id: 1, person_id: 'p1', level: 'critical', label: 'unreciprocated', reasons: ['old'] };
  const now = { id: 'p1', level: 'critical', label: 'sextortion', reasons: ['new'] };
  assert.deepEqual(C.currentAlert(alert, now), { id: 1, person_id: 'p1', level: 'critical', label: 'sextortion', reasons: ['new'] });
  assert.deepEqual(C.currentAlert(alert, undefined), alert);
  // a person marked safe (info) keeps the alert's own level so the card is not silently downgraded
  assert.equal(C.currentAlert(alert, { id: 'p1', level: 'info', label: 'stalking', reasons: [] }).level, 'critical');
});
