"""Person-level behaviour features. Shared by training and the FastAPI backend.

Input: message rows for ONE person (all linked accounts merged) in the common schema.
Labels come from `obs_label` (what the text model saw); a hidden preview has obs_label='unknown'.
"""
import numpy as np
import pandas as pd

HARMFUL_MSG = {"sexual", "insult", "threat", "sextortion"}
EXPLICIT = {"flirt": 0.5, "sexual": 1.0}
REPLY_KINDS = ["accept", "playful", "neutral", "deflect", "reject", "block"]
RELATIONSHIPS = ["stranger", "acquaintance", "friend", "partner", "family"]
MSG_LABELS = ["greeting", "other", "flirt", "sexual", "insult", "threat", "sextortion",
              "surveillance", "clingy", "apology", "media"]

FEATURES = [
    # volume / timing
    "msgs_per_day", "active_days_ratio", "span_days", "burst_count", "night_ratio", "weekend_ratio",
    # reciprocity
    "reply_ratio", "initiation_ratio", "reply_length_ratio", "unanswered_streak_max",
    "msgs_while_ignored", "user_latency_trend",
    # consent
    "rejected_flag", "msgs_after_reject", "sexual_after_reject", "insult_after_reject",
    "apologised_after_reject", "reply_ratio_after_reject",
    # tone
    "flirt_ratio", "sexual_ratio", "insult_ratio", "clingy_ratio", "threat_count", "sextortion_count",
    "surveillance_count", "media_count", "toxicity_slope", "escalation_gap",
    # user side
    *[f"reply_{k}_share" for k in REPLY_KINDS],
    # evasion
    "accounts_count", "platforms_count", "new_account_after_block", "block_count",
    # context
    *[f"rel_{r}" for r in RELATIONSHIPS], "relationship_age_days", "known_contact", "is_group",
    "text_available_ratio", "user_side_available", "minor_involved",
]

# +1: feature can only increase harm risk; -1: can only decrease it (for the binary head)
MONOTONE = {
    "msgs_after_reject": 1, "sexual_after_reject": 1, "insult_after_reject": 1, "threat_count": 1,
    "sextortion_count": 1, "unanswered_streak_max": 1, "new_account_after_block": 1,
    "surveillance_count": 1, "reply_ratio": -1, "reply_accept_share": -1, "reply_playful_share": -1,
}

# features that need message text (for the metadata-only ablation)
TEXT_FEATURES = ["reply_length_ratio", "sexual_after_reject", "insult_after_reject", "apologised_after_reject",
                 "flirt_ratio", "sexual_ratio", "insult_ratio", "clingy_ratio", "threat_count",
                 "sextortion_count", "surveillance_count", "toxicity_slope", "escalation_gap"]
CONSENT_FEATURES = ["rejected_flag", "msgs_after_reject", "sexual_after_reject", "insult_after_reject",
                    "apologised_after_reject", "reply_ratio_after_reject"]


def add_observed_labels(df, text_labeler=None):
    """obs_label = what the system can see. Hidden previews -> 'unknown'.
    text_labeler(list[str]) -> list[str] replaces ground-truth msg_label with model predictions."""
    df = df.copy()
    if "msg_label" not in df:
        df["msg_label"] = "other"
    if "reply_label" not in df:
        df["reply_label"] = None
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True).dt.tz_convert(None)
    has_text = df["text"].notna() & (df["text"].astype(str).str.len() > 0)
    if text_labeler is not None:
        obs = pd.Series("unknown", index=df.index, dtype=object)
        if has_text.any():
            obs[has_text] = text_labeler(df.loc[has_text, "text"].astype(str).tolist())
    else:
        obs = df["msg_label"].where(has_text, "unknown")
    obs[(df["msg_label"] == "block") | (df["is_user"] & (df["reply_label"] == "block"))] = "block"
    df["obs_label"] = obs
    return df


def apply_label_noise(df, rate, rng):
    """Simulate text-model / reply-classifier errors so the behaviour model is robust to them."""
    df = df.copy()
    known = (df["obs_label"] != "unknown") & (df["obs_label"] != "block") & (~df["is_user"])
    idx = df.index[known & (rng.random(len(df)) < rate)]
    df.loc[idx, "obs_label"] = rng.choice(MSG_LABELS, size=len(idx))
    uidx = df.index[df["is_user"] & df["reply_label"].notna() & (rng.random(len(df)) < rate)]
    df.loc[uidx, "reply_label"] = rng.choice(REPLY_KINDS[:5], size=len(uidx))
    return df


def _slope(y):
    y = np.asarray(y, dtype=float)
    if len(y) < 3 or np.all(y == y[0]):
        return 0.0 if len(y) >= 3 else np.nan
    return float(np.polyfit(np.arange(len(y)), y, 1)[0])


def person_features(g):
    g = g.sort_values("timestamp")
    ts = pd.to_datetime(g["timestamp"])
    user_side = bool(g["user_side_available"].iloc[0]) if "user_side_available" in g else True
    is_block = g["obs_label"] == "block"
    s = g[~g["is_user"]]
    u = g[g["is_user"] & ~is_block] if user_side else g.iloc[0:0]
    f = dict.fromkeys(FEATURES, np.nan)
    ns = len(s)
    if ns == 0:
        return f

    s_ts = pd.to_datetime(s["timestamp"])
    span = max(1.0, (ts.max() - ts.min()).total_seconds() / 86400)
    f["span_days"] = span
    f["msgs_per_day"] = ns / span
    f["active_days_ratio"] = s_ts.dt.normalize().nunique() / np.ceil(span)
    f["night_ratio"] = float((s_ts.dt.hour < 5).mean())
    f["weekend_ratio"] = float((s_ts.dt.dayofweek >= 5).mean())
    secs = (s_ts - s_ts.min()).dt.total_seconds().to_numpy()
    f["burst_count"] = float(np.sum(secs[9:] - secs[:-9] <= 1800)) if ns >= 10 else 0.0

    known = s[s["obs_label"] != "unknown"]
    lab = known["obs_label"]
    nk = max(1, len(known))
    f["text_available_ratio"] = len(known) / ns
    for name, key in [("flirt_ratio", "flirt"), ("sexual_ratio", "sexual"), ("insult_ratio", "insult"),
                      ("clingy_ratio", "clingy")]:
        f[name] = float((lab == key).sum() / nk) if len(known) else np.nan
    for name, key in [("threat_count", "threat"), ("sextortion_count", "sextortion"),
                      ("surveillance_count", "surveillance"), ("media_count", "media")]:
        f[name] = float((s["obs_label"] == key).sum())
    if len(known):
        daily = known.assign(d=pd.to_datetime(known["timestamp"]).dt.normalize(),
                             h=known["obs_label"].isin(HARMFUL_MSG)).groupby("d")["h"].mean()
        f["toxicity_slope"] = _slope(daily.values)

    f["accounts_count"] = float(s["account_id"].nunique())
    f["platforms_count"] = float(s["app"].nunique())
    f["block_count"] = float(is_block.sum())
    if is_block.any():
        t_block = ts[is_block].min()
        first_seen = s.groupby("account_id")["timestamp"].min()
        f["new_account_after_block"] = float((pd.to_datetime(first_seen) > t_block).sum())
    else:
        f["new_account_after_block"] = 0.0

    rel = str(g["relationship"].iloc[0]) if "relationship" in g else "stranger"
    for r in RELATIONSHIPS:
        f[f"rel_{r}"] = float(rel == r)
    f["relationship_age_days"] = float(g["relationship_age_days"].iloc[0]) if "relationship_age_days" in g else np.nan
    f["known_contact"] = float(rel != "stranger")
    f["is_group"] = float(bool(g["is_group"].iloc[0])) if "is_group" in g else 0.0
    f["user_side_available"] = float(user_side)
    f["minor_involved"] = float(bool(g["minor_involved"].any())) if "minor_involved" in g else 0.0
    if not user_side:
        return f   # reciprocity / consent / reply-share stay NaN: the model learns to cope

    # reciprocity on the merged timeline (block events excluded)
    tl = g[~is_block]
    users = tl["is_user"].to_numpy()
    f["reply_ratio"] = len(u) / ns
    runs, cur = [], 0
    for is_u in users:
        if is_u:
            if cur:
                runs.append(cur)
            cur = 0
        else:
            cur += 1
    if cur:
        runs.append(cur)
    f["unanswered_streak_max"] = float(max(runs)) if runs else 0.0
    f["msgs_while_ignored"] = float(sum(r - 1 for r in runs))
    tl_ts = pd.to_datetime(tl["timestamp"]).to_numpy()
    starts = np.r_[True, np.diff(tl_ts).astype("timedelta64[s]").astype(float) > 3 * 3600]
    f["initiation_ratio"] = float((~users[starts]).mean())
    if len(u) and s["text"].notna().any() and u["text"].notna().any():
        f["reply_length_ratio"] = float(u["text"].dropna().str.len().mean() / max(1, s["text"].dropna().str.len().mean()))
    # user reply latency trend (hours, per reply index)
    lat, last_s = [], None
    for is_u, t in zip(users, tl_ts):
        if not is_u:
            last_s = t
        elif last_s is not None:
            lat.append((t - last_s) / np.timedelta64(1, "h"))
            last_s = None
    f["user_latency_trend"] = _slope(lat)

    rl = u["reply_label"].fillna("neutral")
    for k in REPLY_KINDS:
        f[f"reply_{k}_share"] = float((rl == k).mean()) if len(u) else 0.0
    f["reply_block_share"] = float(is_block.sum() / max(1, len(u) + is_block.sum()))

    u_expl = u["obs_label"].map(EXPLICIT).fillna(0).mean() if len(u) else 0.0
    s_expl = known["obs_label"].map(EXPLICIT).fillna(0).mean() if len(known) else np.nan
    f["escalation_gap"] = float(s_expl - u_expl) if len(known) else np.nan

    rej = u[u["reply_label"] == "reject"]
    f["rejected_flag"] = float(len(rej) > 0)
    if len(rej):
        tr = pd.to_datetime(rej["timestamp"]).min()
        after = s[s_ts > tr]
        f["msgs_after_reject"] = float(len(after))
        f["sexual_after_reject"] = float((after["obs_label"] == "sexual").sum())
        f["insult_after_reject"] = float((after["obs_label"] == "insult").sum())
        f["apologised_after_reject"] = float((after["obs_label"] == "apology").any())
        u_after = u[pd.to_datetime(u["timestamp"]) > tr]
        f["reply_ratio_after_reject"] = len(u_after) / max(1, len(after))
    else:
        for k in ["msgs_after_reject", "sexual_after_reject", "insult_after_reject", "apologised_after_reject"]:
            f[k] = 0.0
    return f


def build_feature_table(df, noise=0.0, seed=42, text_labeler=None):
    """Messages -> one row per person. Returns (X, meta) where meta has labels and flags."""
    df = add_observed_labels(df, text_labeler)
    if noise:
        df = apply_label_noise(df, noise, np.random.default_rng(seed))
    rows, meta = [], []
    for pid, g in df.groupby("person_id", sort=False):
        rows.append(person_features(g))
        first = g.iloc[0]
        meta.append(dict(person_id=pid, person_label=first.get("person_label"), variant=first.get("variant", "base"),
                         hard_case=bool(first.get("hard_case", False)), source=first.get("source", "unknown")))
    X = pd.DataFrame(rows, columns=FEATURES)
    return X, pd.DataFrame(meta)
