"""Train the SafeSphere behaviour model.

Models: logistic-regression baseline, LightGBM multiclass (which kind of behaviour) and a LightGBM
binary "harmful" head with monotonic constraints + isotonic calibration (how risky).

Usage:  python train.py --train data/synthetic/train.parquet [--extra data/external/conversations.parquet]
"""
import argparse
import json
import os
import time

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score
from sklearn.model_selection import StratifiedKFold, train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from features import FEATURES, MONOTONE, build_feature_table
from simulate import HARMFUL
from text_model import TextModels

THRESHOLDS = {"warn": 0.30, "high": 0.55, "critical": 0.80}
SEED = 42


def logreg():
    return make_pipeline(SimpleImputer(strategy="median", add_indicator=True), StandardScaler(),
                         LogisticRegression(max_iter=3000, class_weight="balanced"))


def tune_lgbm(X, y, n_trials=12):
    """Small random search on macro-F1 (3-fold). Kept small so it runs in minutes on a laptop."""
    rng = np.random.default_rng(SEED)
    skf = StratifiedKFold(3, shuffle=True, random_state=SEED)
    best, best_score = None, -1
    for i in range(n_trials):
        params = dict(num_leaves=int(rng.integers(15, 64)), learning_rate=float(rng.uniform(0.03, 0.1)),
                      min_child_samples=int(rng.integers(10, 51)), colsample_bytree=float(rng.uniform(0.7, 0.9)),
                      n_estimators=int(rng.integers(200, 501)), reg_lambda=float(rng.uniform(0, 2)))
        scores = []
        for tr, va in skf.split(X, y):
            m = lgb.LGBMClassifier(objective="multiclass", class_weight="balanced", random_state=SEED,
                                   verbose=-1, **params)
            m.fit(X.iloc[tr], y.iloc[tr])
            scores.append(f1_score(y.iloc[va], m.predict(X.iloc[va]), average="macro"))
        score = float(np.mean(scores))
        print(f"  trial {i + 1}/{n_trials}: macro-F1={score:.3f}")
        if score > best_score:
            best, best_score = params, score
    return best, best_score


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", default="data/synthetic/train.parquet")
    ap.add_argument("--extra", nargs="*", default=[], help="extra conversations in the common schema (parquet)")
    ap.add_argument("--extra-msgs", default=None, help="labelled messages parquet (text,msg_label) for the text model")
    ap.add_argument("--noise", type=float, default=0.15, help="simulated upstream label-error rate")
    ap.add_argument("--trials", type=int, default=12)
    ap.add_argument("--out", default="models")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    t0 = time.time()

    df = pd.concat([pd.read_parquet(p) for p in [args.train, *args.extra]], ignore_index=True)
    print(f"training data: {df.person_id.nunique()} persons, {len(df)} messages")

    extra_msgs = pd.read_parquet(args.extra_msgs) if args.extra_msgs else None
    tm = TextModels().fit(df, extra_msgs)
    tm.save(f"{args.out}/text_models.pkl")
    print("text models trained")

    X, meta = build_feature_table(df, noise=args.noise, seed=SEED)
    y = meta["person_label"].astype(str)
    yb = y.isin(HARMFUL).astype(int)
    X.assign(person_label=y.values).to_parquet(f"{args.out}/features_train.parquet", index=False)
    print(f"features built: {X.shape}")

    X_fit, X_cal, y_fit, y_cal, yb_fit, yb_cal = train_test_split(
        X, y, yb, test_size=0.2, stratify=y, random_state=SEED)

    print("tuning LightGBM multiclass ...")
    params, cv = tune_lgbm(X_fit, y_fit, args.trials)
    multi = lgb.LGBMClassifier(objective="multiclass", class_weight="balanced", random_state=SEED,
                               verbose=-1, **params).fit(X_fit, y_fit)

    mono = [MONOTONE.get(f, 0) for f in FEATURES]
    binary = lgb.LGBMClassifier(objective="binary", class_weight="balanced", random_state=SEED, verbose=-1,
                                monotone_constraints=mono, monotone_constraints_method="advanced",
                                **params).fit(X_fit, yb_fit)
    iso = IsotonicRegression(out_of_bounds="clip").fit(binary.predict_proba(X_cal)[:, 1], yb_cal)

    lr_multi = logreg().fit(X_fit, y_fit)
    lr_bin = logreg().fit(X_fit, yb_fit)

    bundle = dict(version=time.strftime("%Y%m%d-%H%M"), features=FEATURES, classes=list(multi.classes_),
                  multi=multi, binary=binary, iso=iso, lr_multi=lr_multi, lr_bin=lr_bin,
                  thresholds=THRESHOLDS, params=params, cv_macro_f1=cv, noise=args.noise)
    joblib.dump(bundle, f"{args.out}/behavior_model.pkl")
    val = f1_score(y_cal, multi.predict(X_cal), average="macro")
    json.dump(dict(params=params, cv_macro_f1=cv, holdout_macro_f1=float(val), seconds=round(time.time() - t0)),
              open(f"{args.out}/train_summary.json", "w"), indent=2)
    print(f"done in {time.time() - t0:.0f}s · CV macro-F1 {cv:.3f} · holdout macro-F1 {val:.3f}")
    print(f"saved {args.out}/behavior_model.pkl")


if __name__ == "__main__":
    main()
