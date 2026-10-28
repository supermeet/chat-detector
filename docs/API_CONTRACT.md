# SafeSphere API contract (for the UI and deepfake teams)

Backend: FastAPI in `backend/`. Base URL in dev: `http://localhost:8000`. Interactive docs: `/docs`.

**Auth:** if `SAFESPHERE_API_KEY` is set in `backend/.env`, every call except `/health`, `/metrics` and
`/demo/*` (GET) needs the header `X-API-Key: <key>`. CORS origins come from `SAFESPHERE_ALLOWED_ORIGINS`.

**Levels:** `info` < `warn` < `high` < `critical`. **Labels:** `safe_mutual`, `banter`, `normal_frequent`,
`unreciprocated`, `stalking`, `harassment_after_no`, `group_bullying`, `sextortion`.

---

## 1. For the UI team: screen → endpoint

| Screen / action | Call |
|---|---|
| Startup / status badge | `GET /health` |
| **Live Feed**: get a demo script | `GET /demo/scenarios` → `GET /demo/scenarios/{name}` (events with timestamps) |
| Live Feed: send each event | `POST /ingest/notification` (one object or an array) |
| Live Feed: load a whole scenario at once | `POST /demo/load/{name}` |
| Alerts panel | `GET /alerts` · dismiss: `POST /alerts/{id}/dismiss` |
| **People** list | `GET /people?min_level=info` |
| Person detail | `GET /people/{id}` · messages: `GET /people/{id}/messages` |
| Edit relationship / trusted | `PATCH /people/{id}` |
| Link suggestions | `GET /links/suggestions` |
| ✓ Confirm link | `POST /people/{id}/link` `{"other_person_id": "p3"}` or `{"account_id": "ig:rahul.k_02"}` |
| ✗ Not the same person | `POST /people/{id}/unlink` `{"account_id": "..."}` |
| Not harassment | `POST /feedback` `{"person_id": "p1", "kind": "not_harassment"}` |
| Missed this | `POST /feedback` `{"person_id": "p1", "kind": "missed_harassment", "note": "..."}` |
| **Import Chat**: step 1 | `POST /import/preview` (multipart: `file`, `source` = whatsapp \| instagram \| telegram) |
| Import Chat: step 2 ("who are you?") | `POST /import` (multipart: `file`, `source`, `user_name`, optional `relationship`, `person_id`) |
| **Media Check** | `POST /media/check` (multipart: `file`, optional `person_id`, `context_text`) |
| **Evidence**: JSON pack | `POST /report/{person_id}` |
| Evidence: PDF download | `GET /report/{person_id}.pdf` |
| Evidence: case conclusion + applicable Acts | `POST /conclusion/{person_id}` (Gemini if configured, else rules) |
| Media: attach to a person after analysis | `PATCH /media/{id}` `{"person_id": "p1"}` |
| **Metrics** page | `GET /metrics` (the evaluation output `metrics.json`) |
| The UI itself | `GET /` serves `frontend/index.html` |
| Settings → Delete all data | `DELETE /data` |

### `POST /ingest/notification`
```json
{ "app": "wa", "sender": "Rahul K", "sender_handle": "+919800004410",
  "text": "reply na", "timestamp": "2026-10-28T21:40:00", "is_user": false,
  "event": "message", "media_type": null, "chat": null, "is_group": false }
```
- `app`: `wa` `ig` `tg` `sms` `snap` `fb` · `text: null` = hidden preview · `event: "block"` + `is_user: true` = the user blocked them
- `media_type`: `image` | `video` | `audio` (send `text: "📷 Photo"` like the real notification)
- `room` (optional, live chatrooms; used by the extension with `app: "web"`): the message is stored for the member
  **and** for a room person (`is_room: true`, `display_name` = room, one account `web:<room>/<handle>` per member),
  so a pile-on is scored as one group. The room person is scored only once ≥ 2 members have messaged the user.
  `message_ids` and `labels` stay one per submitted notification. Every person view has `is_room`.

The ingest response also has `new_slang`: words the system just proposed for the word list (see below).

### Word list (adaptive slang)
| Call | Body / result |
|---|---|
| `GET /lexicon` | `{version, terms[{id, term, cat, sev, variants[], src, date}], pending[{id, term, cat, sev, src, note}], log[{t, when}]}` |
| `POST /lexicon/terms` | `{term, cat, sev, variants?}`: adds and re-scores everyone (variants auto-generated when empty) |
| `POST /lexicon/pending` | `{term, cat?, sev?, src: User\|AI\|Auto, note?}`: into the review queue |
| `POST /lexicon/pending/{id}/approve` | optional edits `{term?, cat?, sev?, variants?}` · `.../reject` (never proposed again) |
| `POST /lexicon/test` | `{text}` → `{normalised, tokens[{w, hit}], matches[], label}` (label = model + word list) |
| `POST /lexicon/suggest` | `{term}` → `{variants[], source: rules\|gemini+rules}` (Gemini sees only the term) |

`cat` is one of: Refusal signal, Bullying, Sextortion, Extortion, Stalking, Threat, Sexual harassment,
Self-harm incitement. `POST /feedback` with `kind: missed_harassment` and a `note` also adds the note to the queue.

### Simulated chatroom (extension demo)
`GET /demo/rooms` lists room scripts; `GET /demo/rooms/{name}` returns `{title, room, self, members, events[]}` with
scenario-clock `timestamp`s. `GET /chatroom/` serves the page that plays them. See `extension/README.md`.

Response:
```json
{ "message_ids": [12],
  "people": [ {"id": "p1", "display_name": "Rahul K", "level": "high", "risk": 0.91, "label": "stalking",
               "reasons": ["Sent 23 messages after you said no", "..."], "accounts": [...], "n_messages": 40} ],
  "new_alerts": [ {"id": 3, "person_id": "p1", "level": "high", "label": "stalking",
                   "summary": "Rahul K: likely stalking across 3 accounts (risk 0.91)", "reasons": [...]} ] }
```

The response also has `labels`: what the text models read in each message, e.g.
`[{"message_id": 12, "kind": "reply", "label": "reject", "flagged": false}]`. Use it to show "Refusal detected"
only when the reply really was read as a refusal.

Every person has `early: true` while there is too little history to judge (fewer than 5 messages from them, and no
messages after a "no"). The level is then capped at `warn`, unless a hard rule fires (confident threat or sextortion,
or a minor involved).

### `POST /conclusion/{id}`
```json
{ "source": "gemini", "model": "gemini-3.5-flash", "level": "critical", "behaviour_type": "harassment_after_no",
  "summary": "The analysis shows a consistent pattern of repeated contact after you clearly refused…",
  "acts": [{"section": "BNS 78", "why": "They kept messaging after you said no."}],
  "next_steps": ["Report on cybercrime.gov.in…", "…"], "caution": "Automated analysis, not legal advice.",
  "shared_with_ai": "facts only, no message text", "fallback_reason": null }
```
`source` is `rules` when no Gemini key is set, or when Gemini fails (`fallback_reason` says why). `acts` only ever
contains sections from the backend's vetted list.

### `GET /people/{id}` (detail)
Adds to the list view: `reasons_down` (why the risk is lower), `label_probs`, `facts` (all behaviour
features, e.g. `msgs_after_reject`, `night_ratio`, `reply_ratio`), `text_available_ratio`, and
`consent_timeline`:
```json
[{"phase": "unreciprocated", "start": "..."}, {"phase": "rejected", "start": "..."},
 {"phase": "violation", "start": "...", "messages_after_no": 23}]
```

### `POST /media/check` response
```json
{ "id": 1, "kind": "image", "file_sha256": "…",
  "verdict": "ai_sextortion", "level": "critical",
  "headline": "Likely AI sextortion: a manipulated intimate image of you, sent with a threat or demand",
  "actions": ["Don't pay, don't delete, don't reply.", "..."],
  "steps": [ {"step": "nudity_check", "value": 0.93, "flagged": true},
             {"step": "face_match", "value": 0.81, "flagged": true},
             {"step": "deepfake_model", "value": 0.88, "flagged": true, "wording": "Likely manipulated (88%)"},
             {"step": "context", "value": ["sextortion"], "flagged": true} ],
  "is_stub": false,
  "deepfake": { "deepfake_score": 0.88, "nsfw_score": 0.93, "face_match": 0.81, "heatmap": null, "model": "…" } }
```
**Show a "demo values" badge whenever `is_stub` is true.** The file itself is not stored; only its SHA-256.

### `POST /report/{id}` response
`generated_at_utc`, `person`, `assessment` (level, label, risk, reasons, consent_timeline),
`items[]` (each with `sha256`), `pack_sha256`, `legal[]` (`section`, `description`),
`channels[]` (`name`, `detail`, `url`; ordered by what fits the case), `complaint_text`, `disclaimer`.

### Errors
`401` wrong/missing key · `404` not found · `413` file too large · `415` unsupported media ·
`422` export could not be parsed · `502` deepfake service failed · `503` behaviour model files missing.
All errors return `{"detail": "..."}`.

---

## 2. For the deepfake team: how to connect

Set in `backend/.env` and restart. **No backend code changes needed.**

### Option A: your models run as an HTTP service (recommended)
```
DEEPFAKE_MODE=http
DEEPFAKE_URL=https://your-service.example.com      # we call {URL}/image, {URL}/video, {URL}/audio
DEEPFAKE_API_KEY=<your key>                        # sent as  Authorization: Bearer <key>
```
We send `POST {URL}/{kind}`, multipart form: `file` (the media bytes) and `context_text` (may be empty).

### Option B: your models are a Python package on the same machine
```
DEEPFAKE_MODE=python
DEEPFAKE_PYTHON=your_package.module:analyse        # def analyse(kind: str, data: bytes, filename: str) -> dict
```

### What to return (JSON object / dict)
| Field | Required | Meaning |
|---|---|---|
| `deepfake_score` (or `fake_score` / `score` / `probability`) | **yes** | 0–1 (or 0–100) probability the media is manipulated |
| `label` | no | e.g. `"fake"` / `"real"` |
| `nsfw_score` (or `nudity_score` / `explicit_score`) | no | 0–1, explicit content |
| `face_match` (or `face_match_score`) | no | 0–1, similarity to the user's enrolled face |
| `heatmap` (or `heatmap_url`) | no | base64 PNG or URL |
| `frames` | no | video: `[{"t": 1.0, "score": 0.9}, ...]` |
| `transcript` | no | audio: speech-to-text; we score it with our text model |
| `model` | no | model name/version, shown in the evidence pack |

If `nsfw_score` or `face_match` are missing, those pipeline steps show as not flagged. The verdict still
uses the deepfake score and the message context.

Verdict thresholds (in `backend/app/media.py`): explicit ≥ 0.7, face match ≥ 0.7, manipulated ≥ 0.5.
