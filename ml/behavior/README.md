# SafeSphere: behavioural model

Tells **stalking / harassment** apart from **flirting / banter** using behaviour and consent signals
(reciprocity, replies, behaviour after a "no", timing, accounts), not keywords alone.

## Run it (Colab, CPU is enough)
Upload `SafeSphere_Behavior_Training.ipynb` to Colab, drop `safesphere_behavior_dataset.zip` into the Files pane,
then run the cells in order. Everything in the notebook is generated from the `.py` files here:
`python build_notebook.py` rebuilds it after any code change.

Locally (Python 3.11–3.13):
```
pip install pandas numpy scikit-learn lightgbm pyarrow matplotlib joblib
python prepare_provided.py --src data/provided/synthetic --out data/prepared   # team dataset
python simulate.py --n-train 300 --n-test 150                                  # our simulator
python train.py --train data/prepared/train.parquet --extra data/synthetic/train.parquet --trials 8
python evaluate.py --test data/prepared/test.parquet --cross data/synthetic/test.parquet
```
Outputs: `models/behavior_model.pkl`, `models/text_models.pkl`, `reports/metrics.json` + PNG charts.

## Files
| File | Role |
|---|---|
| `prepare_provided.py` | Maps the team dataset onto the schema (hard cases from `scenario`, block events, timezone) |
| `simulate.py`, `text_pools.py` | Our own conversation simulator (8 classes, hard negatives, hidden previews) |
| `features.py` | ~50 person-level features. **Shared with the backend.** |
| `text_model.py` | TF-IDF message/reply classifiers (stand-in for MuRIL) + keyword baseline |
| `train.py` | Logistic regression baseline, LightGBM multiclass, LightGBM binary (monotonic + isotonic calibration) |
| `predict.py` | `Scorer(model_dir).score_person(df)` → risk, level, label, reasons (SHAP via `pred_contrib`) |
| `evaluate.py` | Keyword vs logreg vs LightGBM, hard-negative false-alarm rate, time-to-detect, ablations |
| `external.py` | Converters for extra datasets (labelled messages, chat logs, hand-written test set) |

## Hard rules (applied after the model, never learned)
Sextortion message, threat message or `minor_involved` → **critical**, whatever the score.

## Results (Colab run, 28 Oct 2026, trained on team dataset + our simulator, 7,200 persons)
Binary "harmful" detection, using text-model labels (the realistic setting):

| Test set | Keyword F1 | LogReg F1 | **LightGBM F1** | LightGBM detection rate | Hard-negative false alarms (keyword → LightGBM) |
|---|---|---|---|---|---|
| Team test set (1,200 persons) | 0.718 | 0.893 | **0.985** | 0.995 | 25.6% → **0.6%** |
| Our simulator's test set (1,200) | 0.608 | 0.892 | **0.933** | 0.980 | 40% → 26.4% |

- Behaviour-type macro-F1: 0.967 (team test) / 0.858 (simulator test).
- Metadata only (no text at all): F1 0.992 vs 0.995 with text.
- Time to detect: harmful people are flagged by the first check (≤5 sender messages).
- Severe text labels (threat/sextortion) need probability ≥ 0.8. Before that gate, the hard rule
  caused 89% false alarms on the simulator's safe people; after it, 11%. The rest is mostly worried-parent
  chats misread as threats by the TF-IDF model.
- Hard rule: critical needs ≥ 2 confident threat/sextortion messages, or 1 plus behaviour risk ≥ warn
  (a minor involved is always critical). One misread swear in friendly banter no longer forces critical.

## Honest limitations
- All training data is synthetic. Report the **hand-written test set** numbers once the team has written it
  (`external.py handwritten data/handwritten`).
- Trained on one generator alone, the model reached F1 0.997 on that generator but only 0.65 on the other
  (hard-negative false alarms 91%). Training on both generators is the default for that reason.
- The text model is TF-IDF; swap in fine-tuned MuRIL for real Hinglish chats.
