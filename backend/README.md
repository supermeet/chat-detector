# SafeSphere backend

FastAPI service that ties everything together: live notifications and chat imports → behaviour model →
people, alerts and link suggestions → media check (deepfake connector) → evidence pack (JSON/PDF) → metrics.

**Already done here:** scoring, person/account linking, consent timeline, WhatsApp/Instagram/Telegram import,
alerts, feedback, evidence pack with SHA-256 fingerprints + PDF, demo scenarios, privacy wipe, tests.
**Left to connect:** your deepfake models (one `.env` change) and the UI (calls in `docs/API_CONTRACT.md`).

## Run
Python **3.11–3.13** (3.14 lacks wheels for some packages).
```
cd backend
python -m venv .venv && .venv\Scripts\activate        # Windows
pip install -r requirements.txt
copy .env.example .env                                 # then edit
# put behavior_model.pkl, text_models.pkl, metrics.json into backend/models/
uvicorn app.main:app --reload --port 8000
```
Open http://localhost:8000/docs to try every endpoint.

> **Model files:** produced by the Colab run (`safesphere_trained_models.zip` → `backend/models/`).
> They must be loaded with scikit-learn 1.6.1 and LightGBM 4.6.0 (pinned in requirements.txt).

## Connect the deepfake models
Edit `.env`, no code changes:
```
DEEPFAKE_MODE=http
DEEPFAKE_URL=https://<your-service>
DEEPFAKE_API_KEY=<key>
```
or `DEEPFAKE_MODE=python` + `DEEPFAKE_PYTHON=package.module:function`. The request/response format is in
`docs/API_CONTRACT.md` §2. Until then `DEEPFAKE_MODE=stub` returns placeholder scores marked `is_stub: true`.

## Connect the UI
Set `SAFESPHERE_API_KEY` and `SAFESPHERE_ALLOWED_ORIGINS` (the UI's dev URL) in `.env`; the UI sends
`X-API-Key`. Screen-by-screen calls: `docs/API_CONTRACT.md` §1.

## Test
```
python -m pytest -q
```
Tests use the real model files and the stub deepfake connector. In Colab, `colab_run_all.sh` retrains the
model and runs these tests in one go.

## Privacy
Everything is held **in memory only**. Restarting the server or calling `DELETE /data` erases it. Uploaded
media is analysed and dropped; only its SHA-256 and the result are kept. Request bodies are never logged.

## Layout
| File | Role |
|---|---|
| `app/main.py` | All routes |
| `app/scoring.py` | Store ↔ behaviour model (`ml/behavior/predict.py`), alerts, consent timeline |
| `app/store.py` | In-memory messages, accounts, persons, alerts, media checks |
| `app/importers.py` | WhatsApp `.txt`, Instagram JSON, Telegram JSON parsers |
| `app/linking.py` | "Same person?" suggestions: handle similarity, writing style, new account after a block |
| `app/deepfake.py` | Deepfake connector (stub / http / python) + response normalisation |
| `app/media.py` | Combines deepfake scores and message context into a verdict |
| `app/report.py` | Evidence pack, legal map, complaint text, PDF |
| `demo/scenarios.json` | Scripted demo chats for the Live Feed |
