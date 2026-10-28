# SafeSphere: Architecture

## 1. Flow
```
 Inputs (chat export JSON/TXT, images, voice notes)
        │
        ▼
 ┌──────────── FastAPI backend (poc/app.py) ────────────┐
 │ text_detector   → toxicity + Hinglish/code-word lexicon│
 │ image_detector  → NSFW model (+ manipulation hints)    │
 │ audio_detector  → Whisper → text_detector              │
 │ behavior_engine → per-sender features → stalking risk  │
 │ lexicon (JSON)  ← user feedback / optional LLM suggest │
 │ report          → SHA-256 evidence pack + legal map    │
 └───────────────────────────────────────────────────────┘
        │
        ▼
 Dashboard (poc/static/index.html): risk cards, timeline, report button
```

## 2. Behavioral model (deliverable 1)
Features computed for each sender over a sliding window:

| Feature | Why |
|---|---|
| msgs_per_day | frequency |
| active_days / span_days | persistence |
| night_ratio (00:00–05:00) | intrusive timing |
| unanswered_streak (max consecutive messages without a reply) | ignoring the victim's silence |
| mean_toxicity, toxicity_slope | tone and escalation |
| surveillance_hits ("saw you", "where are you", location) | monitoring |
| alias_flag (same pattern from a new handle after a block) | evasion |

The risk score is a logistic regression trained on synthetic labelled conversations, with weighted rules as a fallback. Each flag lists the features that drove it (explainability).

## 3. Multimodal (deliverable 2)
- **Text**: `unitary/multilingual-toxic-xlm-roberta` (optional, through `transformers`) combined with the lexicon. The final score is the max of the two.
- **Image**: `Falconsai/nsfw_image_detection` (optional). For deepfakes, an EXIF/editing-software check plus a hook for a deepfake detector. With no model installed, the image is marked "needs review".
- **Audio**: `openai-whisper` tiny (optional), then the text pipeline.
- Every heavy model is **optional**, so the demo runs on any laptop.

## 4. Slang adaptation (deliverable 3)
- `lexicon.json` stores terms with a category, severity and variants. Leetspeak/obfuscation is normalised before matching (`b1tch`, `b!tch`, spaced letters, repeated characters).
- `POST /feedback` adds a missed term that the user flagged.
- `POST /lexicon/suggest` (optional `ANTHROPIC_API_KEY`) asks Claude to propose new slang variants for review. Nothing is applied automatically, so a human approves each entry.

## 5. Reporting (deliverable 4)
`POST /report` returns an evidence pack containing: the flagged items, UTC timestamps, a SHA-256 hash for each item plus a pack hash, suggested legal sections, and reporting channels (cybercrime.gov.in, 1930, NCW, StopNCII, platform grievance officer with the 2h/3h IT Rules 2026 timelines).

## 6. Deliverable mapping
| PS deliverable | Where |
|---|---|
| 1 Behavioral AI | `poc/behavior.py` |
| 2 Multimodal | `poc/detectors.py` |
| 3 Slang adaptation | `poc/lexicon.json`, `/feedback`, `/lexicon/suggest` |
| 4 PoC detect + report | `poc/app.py`, dashboard, `/report` |
| 5 Metrics | `poc/eval.py` |

## 7. Privacy
Everything is processed locally. Nothing leaves the device except an optional LLM call, which receives only slang terms and never chat content.
