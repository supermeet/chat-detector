# SafeSphere Guard: live chatroom extension (design)

Status: draft for team approval · 29 Oct 2026

## 1. Why
At the mentoring round the mentor pointed out that SafeSphere covers phone notifications and chat exports, but most
cyberbullying happens in **live group chatrooms** (class groups, gaming and community rooms). This extension brings the
existing analysis engine into the browser: while the user is in a chatroom, it reads new messages as they appear, scores
them with the same behaviour model, and **alerts and guides** the user in the moment.

We can't stage real bullying on a real platform, so the PoC runs on a **simulated chatroom page** we build. The point
judges should take away: *the extension works on a live, changing chat page, the engine catches the pattern, and the
user is guided properly*.

## 2. Goals
1. A Chrome extension (Manifest V3) that watches a chatroom page and streams its messages into the existing backend.
2. Detects both demo moments (decided 29 Oct: show both):
   - **Pile-on:** several members gang up on the user in the group → `group_bullying`.
   - **Singled out:** one member keeps targeting the user, continues after "stop" → `harassment_after_no` /
     `stalking`, plus sextortion as a Critical case.
3. Stays quiet on friends' banter in the same room (the false-alarm story is as important as the catch).
4. Alerts in the page, guides with clear next steps, and produces the evidence pack from inside the extension.
5. Prevention, not just detection (PS title is "Detection *and Prevention*"): flagged messages are blurred with
   tap-to-reveal. *(Claude's call, flagged for the team to confirm.)*

## 3. Non-goals
- Adapters for real platforms (Discord, WhatsApp Web, Instagram web). The design keeps a per-site adapter seam so
  this is future work, but none ship in the PoC.
- Chrome Web Store publishing; the extension is loaded unpacked for the demo.
- OCR of images in the chat, the deepfake models, the slang list (tracked separately).
- Auto-reporting, auto-blocking or sending messages on the user's behalf. The user always decides.

## 4. Anti-goals (would make it a failure even if it "works")
- Alerting on banter or ordinary room chatter during the demo.
- Text leaving the machine: the extension talks only to the local backend.
- Feeling like spyware: it only runs on sites the user has switched on, and always shows that it is active.
- A fake PoC: the chatroom must not tell the extension what is harmful. The extension reads the page's DOM like any
  real site; all judgement comes from the backend.

## 5. Parts

### 5.1 Simulated chatroom (`chatroom/`, served by the backend at `/chatroom`)
- Generic group-chat look (room name, member list, message list, input box). No real brand's name or styling.
- Scripted members post on a timer from scenario scripts; the presenter can type replies as "You" (e.g. "please stop").
- Each message shows a **scenario-clock timestamp** in the DOM (the existing demo already learned that real-time
  minute-scale bursts score oddly; see MODEL_ANALYSIS §1.4b). The extension reads that displayed time.
- Messages support @mentions and "reply to" so targeting is visible in the DOM.
- Scenarios (one room each, or one room with selectable script):
  1. `pile_on`: 3–5 members insult/mock the user, a couple of bystanders chat normally.
  2. `singled_out`: one member flirts, user says stop, member continues, escalates, mentions where the user is.
  3. `banter`: friends swearing at each other and at the user, user banters back. Must stay safe.
  4. `sextortion`: a member DMs/mentions the user with a photo + money demand → Critical.
- Scenario controls (start, speed, reset) live on the chatroom page, not in the extension.

### 5.2 Extension (`extension/`, plain JS, no build step, matching the repo's style)
- **Content script + site adapter.** A MutationObserver on the message list turns each new message node into
  `{room, sender, sender_id, text, time, is_self, mentions_self, reply_to_self, media}`. All selectors live in one
  adapter object per site; the PoC ships one adapter (the simulated chatroom).
- **Background service worker.** Batches messages and POSTs them to `/ingest/notification`; keeps per-tab state;
  shows `chrome.notifications` and the icon badge count for new alerts.
- **In-page panel** (injected in a shadow DOM so the page's CSS can't break it):
  - Alert card: who, behaviour type, level, the model's top reasons.
  - Guidance by level, reusing SafeSphere's wording: Warn → "Is this bothering you?" (Not harassment / Mute);
    High → don't engage, mute/block, save evidence, report; Critical → "Don't pay, don't delete, don't reply", then
    1930 / StopNCII / cybercrime.gov.in.
  - **Generate evidence pack** → `/report/{pid}` (+ PDF download).
  - "Not harassment" → `/feedback`, which marks the person trusted.
- **Blur** messages the backend labels as flagged (`labels[].flagged` from the ingest response), with tap to reveal.
- **Popup:** backend connection status, monitoring on/off for the current site, people in this room with level.
- Permissions: the chatroom origin and `http://localhost:8000` only; other sites only via an explicit opt-in.

### 5.3 Backend changes (keep small)
- Add an app code for web chat (e.g. `web`) to `schemas.App`.
- Serve `chatroom/` at `/chatroom`.
- **Room vs person scoring.** Today each sender becomes their own person. That handles "singled out", but in a
  pile-on each bully sends only a few messages, so the 5-message evidence gate keeps each at Warn and the model
  never sees the gang. Need: score the **room's targeting messages as one group person** (members = accounts, like
  the chat-export import already does for groups) *in addition to* scoring each member individually. Exact mechanism
  is the builder's call.
- **Targeting filter.** Only messages aimed at the user (mention, reply-to, DM) plus the user's own messages feed the
  engine; general room chatter is dropped in the content script. Prevents false alarms from strangers arguing.

## 6. Demo flow (~3 min)
1. Open the chatroom with the extension on; popup shows "Connected · monitoring this room".
2. Banter scenario plays; nothing fires. Point this out.
3. Pile-on: messages blur as they arrive; after a few, the panel slides in: "You're being targeted by 4 members of
   this room", with reasons and steps. Generate the evidence pack.
4. Singled out: presenter types "please stop"; the member continues; alert escalates to High with
   "Sent N messages after you said no".
5. Sextortion: Critical panel with "Don't pay, don't delete, don't reply" and the 1930 / StopNCII steps.

## 7. Success criteria
- Each harmful scenario reaches its intended level (pile-on and singled-out ≥ High, sextortion Critical) within its
  script; banter never goes above Info/Warn. Verified by running every script through the backend before the demo
  (a test per scenario, like `backend/tests/test_api.py`).
- Works with only the backend running plus the unpacked extension; no network beyond localhost.
- If the backend is down, the extension says so plainly instead of failing silently.

## 8. Risks
- **Model fit for live rooms.** Trained on day-scale 1:1 conversations; live, room-scale bursts may score oddly.
  Mitigation: scenario clock + check scores per scenario early, tune scripts (not the model) if needed.
- **Pile-on detection** depends on the room-level scoring in §5.3; the simulator trained `group_bullying` as one
  group person with several accounts, so that shape should match.

## 9. Left to the builder
Folder layout details, message batching interval, panel visual design (follow the SafeSphere indigo UI), how
room-level persons are keyed, scenario script format (reuse `backend/demo/scenarios.json` style where possible).

## 10. Claude's calls (team to confirm)
- Both demo moments, plus banter and sextortion scenarios.
- Blur-with-reveal as the prevention feature.
- Chatroom served by the backend at `/chatroom`; extension in plain JS with no build step.
- Targeting filter (mentions / replies / DMs only).
