"""Evaluate the behaviour model -> reports/metrics.json + charts (feeds the UI Metrics page).

Reports keyword baseline vs logistic regression vs LightGBM: per-class P/R/F1, macro-F1,
binary harmful P/R/F1, detection rate, false-alarm rate on hard negatives, time-to-detect,
and ablations (metadata-only, no consent features).

Usage:  python evaluate.py --test data/synthetic/test.parquet [--handwritten data/external/handwritten.parquet]
"""
import argparse
import json
import os

import joblib
import lightgbm as lgb
import matplotlib
import numpy as np
import pandas as pd
from sklearn.metrics import (classification_report, confusion_matrix, f1_score, precision_recall_curve,
                             precision_score, recall_score)

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from features import CONSENT_FEATURES, FEATURES, MONOTONE, TEXT_FEATURES, build_feature_table  # noqa: E402
from predict import Scorer  # noqa: E402
from simulate import HARMFUL  # noqa: E402
from text_model import keyword_flag  # noqa: E402

SAFE = ["safe_mutual", "banter", "normal_frequent"]


def binary_block(y_true, flagged):
    return dict(precision=round(float(precision_score(y_true, flagged, zero_division=0)), 3),
                recall=round(float(recall_score(y_true, flagged, zero_division=0)), 3),
                f1=round(float(f1_score(y_true, flagged, zero_division=0)), 3),
                detection_rate=round(float(flagged[y_true == 1].mean()) if (y_true == 1).any() else 0.0, 3))


def far(meta, flagged, hard_only=True):
    m = meta["person_label"].isin(SAFE).to_numpy()
    if hard_only:
        m &= meta["hard_case"].to_numpy()
    return round(float(flagged[m].mean()), 3) if m.any() else None


def keyword_baseline(df):
    s = df[(~df["is_user"]) & df["text"].notna()]
    hit = s.assign(k=s["text"].map(keyword_flag)).groupby("person_id")["k"].any()
    return hit


def evaluate_set(name, df, scorer, use_text_model):
    b = scorer.b
    labeler = scorer.tm.label_messages if (use_text_model and scorer.tm) else None
    if use_text_model and scorer.tm:
        df = scorer.tm.relabel(df)
    X, meta = build_feature_table(df, text_labeler=labeler)
    y = meta["person_label"].astype(str).to_numpy()
    yb = np.isin(y, list(HARMFUL)).astype(int)
    res = scorer.score_features(X)
    flagged = np.array([r["level"] in ("high", "critical") for r in res]).astype(int)
    pred = np.array([r["label"] for r in res])

    kw = keyword_baseline(df).reindex(meta["person_id"]).astype("boolean").fillna(False).to_numpy().astype(int)
    lr_flag = (b["lr_bin"].predict_proba(X)[:, 1] >= 0.5).astype(int)
    lr_pred = b["lr_multi"].predict(X)

    out = dict(
        n_persons=int(len(y)),
        comparison=dict(keyword=binary_block(yb, kw), logreg=binary_block(yb, lr_flag),
                        lightgbm=binary_block(yb, flagged)),
        macro_f1=dict(logreg=round(float(f1_score(y, lr_pred, average="macro")), 3),
                      lightgbm=round(float(f1_score(y, pred, average="macro")), 3)),
        hard_negative_far=dict(keyword=far(meta, kw), logreg=far(meta, lr_flag), lightgbm=far(meta, flagged)),
        all_safe_far=dict(keyword=far(meta, kw, False), logreg=far(meta, lr_flag, False),
                          lightgbm=far(meta, flagged, False)),
        per_class=classification_report(y, pred, output_dict=True, zero_division=0),
        stalking_recall=dict(
            keyword=round(float(kw[y == "stalking"].mean()), 3) if (y == "stalking").any() else None,
            lightgbm=round(float(flagged[y == "stalking"].mean()), 3) if (y == "stalking").any() else None),
    )
    print(f"\n== {name} ({len(y)} persons, text model={'on' if labeler else 'off'}) ==")
    print(pd.DataFrame(out["comparison"]).T.to_string())
    print("macro-F1:", out["macro_f1"], "| hard-negative FAR:", out["hard_negative_far"])
    return out, X, meta, y, pred, res


def time_to_detect(df, scorer, n=60, step=5, seed=0):
    rng = np.random.default_rng(seed)
    pids = df[df["person_label"].isin(HARMFUL)]["person_id"].unique()
    pids = rng.choice(pids, size=min(n, len(pids)), replace=False)
    counts = []
    for pid in pids:
        g = df[df["person_id"] == pid].sort_values("timestamp")
        sender_idx = np.flatnonzero(~g["is_user"].to_numpy())
        hit = None
        for k in range(step, len(sender_idx) + step, step):
            cut = sender_idx[min(k, len(sender_idx)) - 1]
            X, _ = build_feature_table(g.iloc[: cut + 1])
            if scorer.score_features(X)[0]["level"] in ("high", "critical"):
                hit = min(k, len(sender_idx))
                break
        counts.append(hit)
    found = [c for c in counts if c is not None]
    return dict(median_sender_msgs=float(np.median(found)) if found else None,
                detected_share=round(len(found) / max(1, len(counts)), 3), sampled=len(counts))


def early_detection(df, scorer, ks=(3, 5, 10), n=150, seed=0):
    """Score only the first k messages from each person (what the live feed sees early on).
    false_alarm = safe people flagged high+ ; recall = harmful people flagged high+."""
    rng = np.random.default_rng(seed)
    df = scorer.tm.relabel(df) if scorer.tm else df
    labeler = scorer.tm.label_messages if scorer.tm else None
    out = {}
    for group, labels in [("safe", SAFE), ("harmful", sorted(HARMFUL))]:
        pids = df[df["person_label"].isin(labels)]["person_id"].unique()
        pids = rng.choice(pids, size=min(n, len(pids)), replace=False)
        for k in ks:
            prefixes = []
            for pid in pids:
                g = df[df["person_id"] == pid].sort_values("timestamp")
                s_idx = np.flatnonzero(~g["is_user"].to_numpy())
                if len(s_idx) >= k:
                    prefixes.append(g.iloc[: s_idx[k - 1] + 1])
            if not prefixes:
                continue
            X, _ = build_feature_table(pd.concat(prefixes), text_labeler=labeler)
            res = scorer.score_features(X)
            hi = scorer.b["thresholds"]["high"]
            flagged = np.mean([r["level"] in ("high", "critical") for r in res])
            no_gate = np.mean([r["level"] == "critical" or r["risk"] >= hi for r in res])
            key = "false_alarm" if group == "safe" else "recall"
            row = out.setdefault(f"after_{k}_msgs", {})
            row[key] = round(float(flagged), 3)
            row[key + "_without_gate"] = round(float(no_gate), 3)
    print("\nearly detection:", out)
    return out


def ablation(train_feats, X_test, meta_test, b):
    y_tr = train_feats["person_label"].isin(HARMFUL).astype(int)
    yb = meta_test["person_label"].isin(HARMFUL).astype(int).to_numpy()
    out = {}
    for name, drop in [("full", []), ("metadata_only", TEXT_FEATURES), ("no_consent", CONSENT_FEATURES)]:
        Xtr, Xte = train_feats[FEATURES].copy(), X_test[FEATURES].copy()
        if drop:
            Xtr[drop], Xte[drop] = np.nan, np.nan
        m = lgb.LGBMClassifier(objective="binary", class_weight="balanced", random_state=42, verbose=-1,
                               monotone_constraints=[MONOTONE.get(f, 0) for f in FEATURES], **b["params"])
        m.fit(Xtr, y_tr)
        flag = (m.predict_proba(Xte)[:, 1] >= 0.5).astype(int)
        out[name] = dict(**binary_block(yb, flag), hard_negative_far=far(meta_test, flag))
    print("\nablation:\n" + pd.DataFrame(out).T.to_string())
    return out


def charts(out_dir, synth, y, pred, classes, res, meta):
    os.makedirs(out_dir, exist_ok=True)
    cmp = synth["comparison"]
    metrics = ["precision", "recall", "f1", "detection_rate"]
    x = np.arange(len(metrics))
    plt.figure(figsize=(7, 4))
    for i, (k, c) in enumerate([("keyword", "#9aa1b5"), ("logreg", "#c9b8ff"), ("lightgbm", "#6d4aff")]):
        plt.bar(x + (i - 1) * 0.27, [cmp[k][m] for m in metrics], 0.27, label=k, color=c)
    plt.xticks(x, metrics); plt.ylim(0, 1.05); plt.legend(); plt.title("Harmful-behaviour detection")
    plt.tight_layout(); plt.savefig(f"{out_dir}/comparison.png", dpi=150); plt.close()

    cm = confusion_matrix(y, pred, labels=classes, normalize="true")
    plt.figure(figsize=(7, 6)); plt.imshow(cm, cmap="Purples", vmin=0, vmax=1)
    plt.xticks(range(len(classes)), classes, rotation=45, ha="right"); plt.yticks(range(len(classes)), classes)
    for i in range(len(classes)):
        for j in range(len(classes)):
            plt.text(j, i, f"{cm[i, j]:.2f}", ha="center", va="center", fontsize=8,
                     color="white" if cm[i, j] > 0.5 else "black")
    plt.title("Confusion matrix (row-normalised)"); plt.tight_layout()
    plt.savefig(f"{out_dir}/confusion_matrix.png", dpi=150); plt.close()

    yb = meta["person_label"].isin(HARMFUL).astype(int)
    p, r, _ = precision_recall_curve(yb, [x["risk"] for x in res])
    plt.figure(figsize=(5, 4)); plt.plot(r, p, color="#6d4aff"); plt.xlabel("recall"); plt.ylabel("precision")
    plt.title("PR curve: harmful head"); plt.tight_layout(); plt.savefig(f"{out_dir}/pr_curve.png", dpi=150); plt.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="models")
    ap.add_argument("--test", default="data/synthetic/test.parquet")
    ap.add_argument("--handwritten", default="data/external/handwritten.parquet")
    ap.add_argument("--external", default="data/external/conversations.parquet")
    ap.add_argument("--cross", default="data/synthetic/test.parquet",
                    help="test set from a DIFFERENT generator (robustness check)")
    ap.add_argument("--out", default="reports")
    ap.add_argument("--skip-ttd", action="store_true")
    args = ap.parse_args()
    scorer = Scorer(args.models)
    test = pd.read_parquet(args.test)

    report = dict(model_version=scorer.b["version"], synthetic_disclosure=True)
    synth, X, meta, y, pred, res = evaluate_set("synthetic test (oracle labels)", test, scorer, False)
    report["synthetic"] = synth
    report["synthetic_text_model"] = evaluate_set("synthetic test (text-model labels)", test, scorer, True)[0]
    for key, path in [("handwritten", args.handwritten), ("external", args.external),
                      ("cross_generator", args.cross)]:
        if os.path.exists(path):
            report[key] = evaluate_set(key, pd.read_parquet(path), scorer, True)[0]
    report["early_detection"] = early_detection(test, scorer)
    if not args.skip_ttd:
        report["time_to_detect"] = time_to_detect(test, scorer)
        print("\ntime to detect:", report["time_to_detect"])
    tf_path = f"{args.models}/features_train.parquet"
    if os.path.exists(tf_path):
        report["ablation"] = ablation(pd.read_parquet(tf_path), X, meta, scorer.b)
    hw = report.get("handwritten")
    if hw and synth["macro_f1"]["lightgbm"] > 0.97 and hw["macro_f1"]["lightgbm"] < 0.75:
        report["warning"] = "Simulator too easy: synthetic >> handwritten. Widen overlaps / add hard negatives."
        print("\n⚠", report["warning"])

    os.makedirs(args.out, exist_ok=True)
    charts(args.out, synth, y, pred, scorer.b["classes"], res, meta)
    with open(f"{args.out}/metrics.json", "w") as fh:
        json.dump(report, fh, indent=2, default=float)
    print(f"\nsaved {args.out}/metrics.json and charts")


if __name__ == "__main__":
    main()
