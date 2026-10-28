"""Why are safe people flagged? Splits false alarms into 'model score' vs 'hard rule' causes.

    python diagnose.py --test data/synthetic/test.parquet
"""
import argparse

import pandas as pd

from evaluate import SAFE
from features import build_feature_table
from predict import Scorer

ap = argparse.ArgumentParser()
ap.add_argument("--models", default="models")
ap.add_argument("--test", default="data/synthetic/test.parquet")
a = ap.parse_args()
sc = Scorer(a.models)
df = sc.tm.relabel(pd.read_parquet(a.test))
X, meta = build_feature_table(df, text_labeler=sc.tm.label_messages)
res = pd.DataFrame(sc.score_features(X))
res = pd.concat([meta, res[["risk", "level", "label"]], X[["threat_count", "sextortion_count", "sexual_ratio"]]], axis=1)
safe = res[res.person_label.isin(SAFE)]
fa = safe[safe.level.isin(["high", "critical"])]
print(f"safe persons: {len(safe)}, flagged: {len(fa)} ({len(fa) / max(1, len(safe)):.1%})")
print(f"  flagged by model score (risk >= 0.55): {(fa.risk >= 0.55).sum()}")
print(f"  flagged ONLY by hard rule (risk < 0.55): {(fa.risk < 0.55).sum()}")
print("\nthreat/sextortion counts among rule-only false alarms:")
print(fa[fa.risk < 0.55][["threat_count", "sextortion_count"]].describe().round(2).to_string())
print("\nfalse alarms by class/variant:\n", fa.groupby(["person_label", "variant"]).size().to_string())
