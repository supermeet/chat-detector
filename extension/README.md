# SafeSphere Guard: live chatroom extension (PoC)

A Chrome extension that watches a live group chat while you use it, sends the messages **aimed at you** to the
local SafeSphere engine, and alerts, blurs and guides you when a harmful pattern appears.

## Try it
1. Start the backend (`run.bat`, or `uvicorn app.main:app --port 8000` in `backend/`).
2. Chrome → `chrome://extensions` → turn on **Developer mode** → **Load unpacked** → pick this `extension/` folder.
3. Open **http://localhost:8000/chatroom/**, pick a scenario, press **Start**.
   - **Scripted** plays everything. **Live typing** pauses at each of your lines with the reply pre-filled, so the
     presenter can type "please stop" on stage (or anything else).
   - Before switching scenarios, use the extension popup's **Clear SafeSphere data** for a clean run.

| Scenario | Room | What you should see |
|---|---|---|
| Pile-on | Class 12-B | "4 members of Class 12-B are targeting you" (critical, `group_bullying`), insults blurred |
| Friends roasting | Cricket Gang | Nothing: same swear words, but you banter back, so no alert and no blur |
| Singled out | Physics Lab B2 | "Vikram is persistently targeting you" after you say no (critical, `stalking`) |
| Stranger + photo + demand | College Fest 2026 | "Don't pay, don't delete, don't reply", then 1930 / StopNCII / cybercrime.gov.in |

## How it decides (all judgement is the backend's)
- **What is sent:** only your messages and messages that @mention you or reply to you (`lib/core.js` `isTargeting`).
  Chatter between other people is never sent. Your own message is attributed to the member you reply to, or to the
  last member who targeted you.
- **Two views per message:** the backend scores each member on their own **and** the room as one group
  (`room` field on `/ingest/notification`), so a pile-on by four people who each send only a few messages is still
  caught as `group_bullying`.
- **Room members are acquaintances**, not strangers (you share the room). Spike, 29 Oct: as strangers, friends'
  banter scored *high*; as acquaintances *info*, while the pile-on stayed *critical*.
- **Alerts** only at high/critical. Warn shows only in the popup.
- **Blur** only when the text model flags the words **and** the sender or room is high/critical: banter uses the
  same words. Tap a blurred message to view it.

## Files
| File | Role |
|---|---|
| `lib/core.js` | Pure logic: targeting, mapping to the API, blur rule, guidance wording. Unit-tested in Node. |
| `content.js` | Site adapter (DOM contract of `chatroom/`), MutationObserver, panel (shadow DOM), blur |
| `background.js` | The only part that calls the backend; notifications and icon badge |
| `popup.html/js` | Connection status, on/off, recent alerts, backend address, clear data |

## Tests
```
node --test "extension/tests/*.test.js"                                   # core logic
backend/.venv/Scripts/python -m pytest -q extension/tests/test_e2e.py      # real Chromium + extension + backend
```
The end-to-end test needs `pip install playwright && python -m playwright install chromium` once (branded Chrome no
longer loads unpacked extensions from the command line). It saves screenshots to `docs/results/extension_*.png`.

## Privacy
Runs only on the chatroom pages listed in `manifest.json`; talks only to the backend address in the popup
(default `http://localhost:8000`). Messages not aimed at you never leave the page.

## Limits (say them before the judges do)
- One site adapter (the simulated chatroom). Real platforms need their own adapter; the seam is `ADAPTER` in `content.js`.
- Pile-on messages must @mention or reply to you to be counted; untagged "talking about you" is not caught yet.
- Scores come from the same synthetic-data model as the rest of SafeSphere.
