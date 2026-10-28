# SafeSphere Guard (live chatroom extension) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Chrome extension that reads a live chatroom page, streams messages aimed at the user into the existing
SafeSphere engine, and alerts, blurs and guides; demonstrated on a simulated chatroom served by the backend.

**Architecture:** Backend gains a `room` field on notifications: each room message is stored for the member *and*
for a room-level group person (members = accounts), so pile-ons are scored as `group_bullying` while one harasser is
still scored alone. The extension is plain MV3 JS: a pure `core.js` (targeting, mapping, guidance, blur rule; unit
tested in Node), a content script (DOM adapter + MutationObserver + shadow-DOM panel), and a service worker (API
calls, notifications, badge).

**Tech Stack:** FastAPI/pytest (existing, Python 3.11 venv in `backend/.venv`), Chrome MV3, Node 24 `node --test`,
Python Playwright + bundled Chromium for the end-to-end test.

**Spec:** `docs/superpowers/specs/2026-10-29-chatroom-extension-design.md`

## Global Constraints
- Extension talks only to the configured backend (default `http://localhost:8000`); no other network.
- The chatroom never tells the extension what is harmful; all judgement comes from backend responses.
- Room members are sent with `relationship: "acquaintance"` (shared room membership). Grounded by spike, 29 Oct:
  as `stranger`, banter-as-room scored **high** (risk 0.63); as `acquaintance` it scored **info** (0.14) while the
  pile-on stayed **critical / group_bullying**. Simulator trains group_bullying with `rel="acquaintance"`.
- Panel alert cards only for levels `high`/`critical` (backend `new_alerts`). Warn is shown only in the popup.
- Blur a message only if the backend flagged it **and** its sender's person or the room person is `high`/`critical`.
- Room person is scored only when ≥ 2 distinct member accounts have sent it messages (no duplicate alert for a
  single harasser).
- Existing 16 backend tests must keep passing.

## Review Focus
1. Backend down or restarted mid-demo → content script shows "SafeSphere backend not reachable" in the panel, does
   not throw; test: core `describeError` + e2e not required (manual check).
2. Same DOM node seen twice (re-render / observer double-fire) → sent once; test: content script marks
   `data-ssg-seen`, e2e counts `/people` messages equal to targeting events.
3. User message with no reply target and no prior targeter → dropped (not attributed to a random member); test:
   core `toNotification` returns null.
4. Live-typed free message (not from the script) → still timestamped on the scenario clock; test: chatroom stamps
   last event time + 1 min (checked in e2e live-typing test).
5. Mention matching is case-insensitive and not a substring of another name (`@Priyanka` ≠ `@Priya`); test: core.

---

### Task 1: Backend room ingest + scoring

**Files:**
- Modify: `backend/app/schemas.py` (App += `"web"`; `Notification.room: Optional[str]`)
- Modify: `backend/app/store.py` (`Person.is_room: bool = False`; `Store.rooms: dict[str, str]` reset in `reset()`)
- Modify: `backend/app/main.py` (`_add_message` room copy; ingest touches room pid)
- Modify: `backend/app/scoring.py` (`score_person` room guard; `person_view` adds `is_room`)
- Test: `backend/tests/test_rooms.py`

**Interfaces:**
- Produces: `POST /ingest/notification` accepts `room`; response `people[]` items have `is_room: bool`; room person
  `display_name == room`, accounts `web:<room>/<handle>`; member person accounts `web:<handle>`.
  `message_ids`/`labels` stay 1:1 with submitted notifications (room copy not listed).

- [ ] Step 1: tests `test_room_pile_on_scored_as_group` (4 members, insults, room person level in high/critical, label
  `group_bullying`, `is_room` true, 4 accounts), `test_room_single_member_not_scored_as_room` (room person `risk is
  None`), `test_room_labels_one_per_notification` (len(labels) == len(batch)).
- [ ] Step 2: run, expect FAIL (`room` rejected / no room person).
- [ ] Step 3: implement. In `_add_message`, when `n.room`: `store.get_or_create_account(n.app, f"{n.room}/{handle}",
  n.sender, ts)`; if `n.room` not in `store.rooms`, that account's person becomes the room person (display_name =
  room, `is_group=True`, `is_room=True`, relationship `acquaintance`); else `store.link(room_pid, acc.id)`. Store a
  second `Message` on that account. Member person stays `is_group=False`. `score_person`: if `person.is_room` and
  fewer than 2 distinct account_ids among non-user messages → `person.result = None; return None`.
- [ ] Step 4: run `backend/.venv/Scripts/python -m pytest -q` → all pass (16 old + new).
- [ ] Step 5: commit `feat(backend): score live chatroom messages per member and per room`.

### Task 2: Room scenarios + chatroom page

**Files:**
- Create: `backend/demo/rooms.json`, `chatroom/index.html`, `chatroom/room.js`, `chatroom/room.css`
- Modify: `backend/app/main.py` (`_stamp(events)` helper shared with `demo_get`; `GET /demo/rooms`,
  `GET /demo/rooms/{name}`; mount `chatroom/` at `/chatroom` via `StaticFiles(html=True)`)
- Modify: `backend/app/config.py` (`CHATROOM_DIR = ROOT_DIR / "chatroom"`)
- Test: `backend/tests/test_rooms.py`

**Interfaces:**
- `rooms.json`: `{name: {title, room, self: {id, name}, members: {id: name}, events: [{t, from, text, reply_to?,
  media?}]}}`; `from` is a member id or `"self"`; `reply_to` is a member id or `"self"`; `t` uses the
  `"<day offset> HH:MM"` format of `scenarios.json`. Scenarios: `pile_on`, `banter`, `singled_out`, `sextortion`;
  room `Class 12-B`, self `Priya`. Bystander lines (no `@Priya`, no reply to self) are included in each.
- `GET /demo/rooms/{name}` → same object with each event's `timestamp` (ISO, scenario clock ending now).
- **Chatroom DOM contract** (the extension's adapter depends on exactly this):
  `main#room[data-room][data-self-name][data-state=idle|playing|done]` › `ol#messages` ›
  `li.msg[data-msg-id][data-sender-id][data-self?][data-reply-to?]` containing `.msg-sender`,
  `time[datetime]`, `.msg-text`, optional `.msg-media[data-kind]`. `data-reply-to` holds the replied-to sender id
  (`"priya"` for the user).
- Page controls: scenario select, mode `Scripted | Live typing`, speed, Start, Reset; query params
  `?scenario=&speed=fast&autostart=1&mode=` for tests. Live mode pauses at each `from:"self"` event with its text
  pre-filled; free-typed messages are stamped last event time + 1 min; clicking a message's ↩ sets reply target.

- [ ] Step 1: tests `test_room_scenarios_reach_intended_levels`, parametrized over the 4 rooms: fetch
  `/demo/rooms/{name}`, keep events where `from == "self"` or `"@priya"` in lowercase text (word boundary) or
  `reply_to == "self"`, map like core `toNotification` (Task 3), POST as one batch, assert: pile_on → room person
  high/critical + label group_bullying; banter → no person high/critical and `new_alerts == []`; singled_out → member
  high/critical and consent phases include `rejected` and `violation`; sextortion → member critical.
- [ ] Step 2: run → FAIL (404). Step 3: implement rooms.json + endpoints + page. Tune script lines (not the model)
  until Step 4 passes. Step 4: `pytest -q` all pass; open `/chatroom` and play each scenario by eye.
- [ ] Step 5: commit `feat: simulated chatroom with four room scenarios`.

### Task 3: Extension core (pure logic, Node-tested)

**Files:** Create `extension/lib/core.js`, `extension/tests/core.test.js`

**Interfaces (exported as `module.exports` in Node, `self.SSGCore` in the browser):**
- `isTargeting(rec, selfName, selfId) -> bool` — `rec.isSelf || rec.replyTo === selfId || mentions(rec.text, selfName)`;
  mention = `@name` case-insensitive with a non-word char or end after it.
- `toNotification(rec, ctx) -> Notification | null` — `ctx = {room, selfName, selfId, lastTargeter}` (mutated:
  sets `lastTargeter` to `{id, name}` on a targeting member message). Member message → `{app:"web", sender: name,
  sender_handle: id, text, timestamp, room, relationship:"acquaintance", media_type?}`. Self message → sender is
  the member in `rec.replyTo` (looked up in `ctx.members`) else `ctx.lastTargeter`, else `null`; `is_user: true`.
  Non-targeting → `null`. The `@selfName` mention is stripped from `text`.
- `levelsFor(people, senderId, room) -> {member, roomLevel, memberPid, roomPid}` from an ingest response.
- `shouldBlur(flagged, memberLevel, roomLevel) -> bool` (Global Constraints rule).
- `guidance(alert, people) -> {title, body, steps[], critical: bool}` — room alert title "N members of <room> are
  targeting you"; harassment_after_no/stalking "<name> keeps contacting you after you said no" / "<name> is
  persistently targeting you"; sextortion steps start with "Don't pay, don't delete, don't reply." then 1930,
  StopNCII.org, cybercrime.gov.in; high steps: don't reply, mute or leave, save evidence, report.
- `describeError(err) -> string`.

- [ ] Step 1: tests in `core.test.js` (node:test + assert) covering each export, including Review Focus 3 and 5.
- [ ] Step 2: `node --test extension/tests/` → FAIL. Step 3: implement. Step 4: → PASS.
- [ ] Step 5: commit `feat(extension): core targeting, mapping and guidance logic`.

### Task 4: Extension shell (manifest, content script, panel, blur, worker, popup)

**Files:** Create `extension/manifest.json`, `extension/content.js`, `extension/panel.css`,
`extension/background.js`, `extension/popup.html`, `extension/popup.js`, `extension/icons/icon128.png`,
`extension/README.md`

**Interfaces:**
- Manifest V3; permissions `storage`, `notifications`; host_permissions `http://localhost/*`, `http://127.0.0.1/*`;
  content script on `http://localhost/chatroom*`, `http://127.0.0.1/chatroom*` with `lib/core.js`, `content.js`.
- Worker messages: `{type:"ingest", items}` → POST `/ingest/notification` (serialized promise chain) → response;
  `{type:"feedback", pid}` → POST `/feedback` `not_harassment`; `{type:"report", pid}` → open
  `<api>/report/<pid>.pdf` tab; `{type:"health"}`. API base from `chrome.storage.local.api`, default
  `http://localhost:8000`; `X-API-Key` from `chrome.storage.local.key` when set. New alerts →
  `chrome.notifications.create` + per-tab badge count.
- Content script: adapter for the Task 2 DOM contract; MutationObserver on `ol#messages`; marks nodes
  `data-ssg-seen`; one `ingest` per observer callback batch; applies `shouldBlur` (class `ssg-blur`, click to
  reveal) including retro-blur of earlier flagged nodes when a level rises; panel host `div#safesphere-guard` with
  an **open** shadow root, cards from `guidance()`, buttons Evidence pack / Not harassment / Dismiss; status line
  shows backend errors via `describeError`.
- Popup: backend status from `/health`, monitoring toggle (`chrome.storage.local.enabled`, default true), recent
  alerts (`GET /alerts`), "Clear SafeSphere data" (`DELETE /data`), link to dashboard.

- [ ] Step 1: load unpacked in Chrome, run each scenario at `/chatroom`; expected: pile_on panel + blur, banter
  nothing, singled_out escalation after the "stop", sextortion critical card. (Automated in Task 5.)
- [ ] Step 2: commit `feat(extension): content script, panel, blur, worker and popup`.

### Task 5: End-to-end proof

**Files:** Create `extension/tests/test_e2e.py`; Modify `README.md` (extension section), `docs/API_CONTRACT.md`
(`room` field, `/demo/rooms`, `/chatroom`)

- [ ] Step 1: pytest e2e: start uvicorn on port 8765 (subprocess), Playwright `chromium.launch_persistent_context`
  with `--disable-extensions-except/--load-extension`, set `api` in storage via the service worker, then per
  scenario open `/chatroom?scenario=X&speed=fast&autostart=1`, wait for `data-state=done`, and assert:
  pile_on → panel text contains "members of Class 12-B" and ≥1 `.ssg-blur`; banter → no panel card, 0 `.ssg-blur`;
  singled_out → card for Vikram; sextortion → card containing "Don't pay". Save a screenshot per scenario to
  `docs/results/extension_<scenario>.png`. Live-typing test: `mode=live`, type the paused line, assert it renders
  with a scenario-clock time and the run continues.
- [ ] Step 2: run all: `node --test extension/tests/`, `backend/.venv/Scripts/python -m pytest -q backend/tests
  extension/tests` → all pass.
- [ ] Step 3: commit `test: end-to-end extension proof + docs`.
