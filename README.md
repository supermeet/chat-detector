# SafeSphere: chat harassment detector

**Hacksploit 2026 · PS 5: Detection and Prevention of Personal & Social Harassment**

A victim-side safety app that detects **stalking, harassment, bullying and sextortion from behaviour**
(frequency, persistence, replies, what happens after a "no", new accounts after a block) rather than keywords
alone. It checks media with deepfake models and turns flagged chats into a **tamper-evident evidence pack**
mapped to Indian law.

## Run the demo
Requires Python **3.11–3.13** (3.14 is too new for the model libraries).
```
cd backend
python -m venv .venv
.venv\Scripts\python -m pip install --use-feature=truststore -r requirements.txt
```
Then double-click **`run.bat`** (or run `.venv\Scripts\python -m uvicorn app.main:app --port 8000` in `backend`).
`--use-feature=truststore` makes pip use the Windows certificate store, which is needed on networks that inspect HTTPS.
Open **http://localhost:8000**. The UI and API are served together. The header chip shows
**● Live model** when the backend is connected, or **Demo mode** (sample data) when it isn't.

The trained model files are already in `backend/models/`. To retrain, use `ml/behavior/SafeSphere_Behavior_Training.ipynb`
in Google Colab (CPU, about 10 minutes) with `data/safesphere_behavior_dataset.zip`.

## Repository layout
| Folder | What it is |
|---|---|
| `frontend/` | The UI. Edit `src/`, then `python frontend/build.py` → `index.html` (single file). `src/logic.js` holds the backend wiring. |
| `backend/` | FastAPI: scoring, people and account linking, chat import, media check, evidence pack (JSON/PDF), metrics. See `backend/README.md`. |
| `extension/` | SafeSphere Guard: Chrome extension for live chatrooms. See `extension/README.md`. |
| `chatroom/` | Simulated group chat (served at `/chatroom/`) the extension is demonstrated on |
| `backend/models/` | Trained behaviour model + text models + `metrics.json` |
| `ml/behavior/` | Training pipeline: simulator, features, LightGBM training, evaluation, Colab notebook |
| `data/` | Team synthetic dataset (4,800 train / 1,200 test conversations) |
| `docs/` | Idea, architecture, UI/UX spec, API contract, model analysis and privacy, pitch material |

## Results (synthetic data, labels from the text model)
| Test set | Keyword filter F1 | **SafeSphere F1** | False alarms on tricky safe chats |
|---|---|---|---|
| Team test set (1,200 people) | 0.72 | **0.985** | 25.6% → **0.6%** |
| Second, independent generator | 0.61 | **0.933** | 40% → 26.4% |

Details and limitations: `docs/MODEL_ANALYSIS_AND_PRIVACY.md`.

## Live chatrooms: SafeSphere Guard extension
Most bullying happens in live group chats, so `extension/` is a Chrome extension that reads a chat page as you use
it, scores the messages aimed at you with the same engine (per member **and** per room, so pile-ons are caught), and
alerts, blurs and guides you. Demo on the simulated chatroom at **http://localhost:8000/chatroom/**. Setup, scenarios
and tests: `extension/README.md`.

## Slang that keeps up (PS deliverable 3)
The word list (`backend/lexicon/seed.json` + the **Word list** screen) works next to the text model:
**final label = max(model, word list)**, ranked by harm, so a new insult or code word counts immediately, with no retraining.
- **Normalisation** catches obfuscated spellings: `ch4pri`, `c h a p r i`, `chaaapri`, `b.i.t.c.h` all match `chapri`/`bitch`.
- **It learns new slang by itself.** The behaviour model catches harassment from patterns even without known bad
  words. Words that keep appearing in those flagged chats, from 2+ different senders and never in safe chats, are
  proposed automatically (`Auto`). In the demo, the pile-on teaches it **"behenji"**.
- **Three more ways in:** "Missed this" on a message, "+ Add term", and editing the seed file, which reloads on save.
  Approved terms get their leetspeak/spacing variants added automatically (AI suggestions optional, term only).
- **A person approves every new term**, so harassers can't teach it to flag innocent words. "Refusal signal" terms
  ("bas karo", "bhaiya") also teach the reply classifier what a "no" looks like, unless the reply reads as playful.

## Connecting the deepfake models
Set `DEEPFAKE_MODE`, `DEEPFAKE_URL` and `DEEPFAKE_API_KEY` in `backend/.env` (see `.env.example`). No code changes are
needed. Until then a stub returns placeholder scores, clearly marked "demo values" in the UI. Contract: `docs/API_CONTRACT.md` §2.

## Case conclusion (Gemini)
Put `GEMINI_API_KEY` in `backend/.env` (never commit it). The Evidence screen then shows a plain-language conclusion,
the applicable Acts/sections and next steps, written by `gemini-3.5-flash`, with `gemini-flash-lite-latest` as fallback.
**Gemini only receives the model's extracted facts** (level, behaviour type, counts, ratios, template reasons), never
message text, names or handles, and it may only cite sections from the backend's vetted list. Without a key, or if the
call fails, a rule-based conclusion is shown instead.

## Privacy
Everything is held in memory only. Uploaded media is analysed and dropped; only its SHA-256 fingerprint is kept.
No AI model sees chat text: the detection model is our own, and Gemini only gets extracted facts.
`DELETE /data` (Settings → Delete all data) wipes everything.
