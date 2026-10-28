"""Agent-based conversation simulator for the SafeSphere behaviour model.

Each conversation = one other person (possibly several accounts) messaging the user over days.
Scenario parameters are sampled from deliberately OVERLAPPING ranges so classes are not trivially
separable, and ~25% of every safe class are hard negatives (clingy partner, worried parent, ...).

Usage:  python simulate.py --n-train 600 --n-test 150 --out data/synthetic
"""
import argparse
import os
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from text_pools import sample_text, split_pools

CLASSES = ["safe_mutual", "banter", "normal_frequent", "unreciprocated",
           "stalking", "harassment_after_no", "group_bullying", "sextortion"]
HARMFUL = {"stalking", "harassment_after_no", "group_bullying", "sextortion"}

# intent pool -> message label the text model is expected to output
MSG_LABEL = {
    "greeting": "greeting", "small_talk": "other", "flirt": "flirt", "sexual": "sexual",
    "insult": "insult", "banter_swear": "insult", "threat": "threat", "sextortion": "sextortion",
    "surveillance": "surveillance", "clingy": "clingy", "apology": "apology", "media": "media",
    "warm_reply": "flirt", "playful_reply": "other", "neutral_reply": "other",
    "deflect_reply": "other", "rejection": "rejection",
}
REPLY_LABEL = {"warm_reply": "accept", "playful_reply": "playful", "neutral_reply": "neutral",
               "deflect_reply": "deflect", "rejection": "reject", "banter_swear": "playful"}
APPS = ["wa", "ig", "tg", "sms", "snap"]


def U(rng, a, b):
    return float(rng.uniform(a, b))


def scenario_params(scn, rng):
    """Sample one conversation's parameters. Returns (params, variant_name, is_hard)."""
    p = dict(days=int(rng.integers(5, 31)), rate=U(rng, 3, 20), reply=U(rng, 0.6, 0.9),
             night=U(rng, 0.05, 0.3), burst=0.0, user_init=0.0, latency=U(rng, 5, 60),
             latency_growth=0.0, stages=[(0, {"greeting": 2, "small_talk": 4})],
             reply_mix={"neutral_reply": 3, "warm_reply": 2}, reject_day=None, apology_stop=False,
             post=None, new_accounts=0, block=False, rel="acquaintance", rel_age=U(rng, 30, 900),
             group=0)
    variant, hard = "base", False
    r = rng.random()

    if scn == "safe_mutual":
        p.update(rate=U(rng, 3, 20), reply=U(rng, 0.65, 0.95), night=U(rng, 0.05, 0.35),
                 user_init=U(rng, 0.3, 0.8), rel=rng.choice(["partner", "friend", "acquaintance"]),
                 stages=[(0, {"greeting": 2, "small_talk": 4, "flirt": 3, "sexual": 0.15, "media": 0.1})],
                 reply_mix={"warm_reply": 5, "playful_reply": 2, "neutral_reply": 2, "deflect_reply": 0.3})
        if r < 0.15:
            variant, hard = "clingy_partner", True
            p.update(rel="partner", rate=U(rng, 15, 50), night=U(rng, 0.35, 0.65), reply=U(rng, 0.6, 0.9))
            p["stages"][0][1]["clingy"] = 1.5
        elif r < 0.27:
            variant, hard = "gappy_flirt", True
            p.update(reply=U(rng, 0.3, 0.55), latency=U(rng, 120, 600), user_init=U(rng, 0.2, 0.5))

    elif scn == "banter":
        p.update(rel="friend", rate=U(rng, 3, 25), reply=U(rng, 0.6, 0.95), night=U(rng, 0.05, 0.4),
                 user_init=U(rng, 0.5, 1.0),
                 stages=[(0, {"banter_swear": 3, "small_talk": 3, "greeting": 1, "insult": 0.5})],
                 reply_mix={"playful_reply": 4, "banter_swear": 2, "neutral_reply": 2, "warm_reply": 0.5})
        if r < 0.25:
            variant, hard = "heavy_swearer", True
            p["stages"] = [(0, {"banter_swear": 4, "insult": 2.5, "small_talk": 1})]

    elif scn == "normal_frequent":
        p.update(rel=rng.choice(["family", "friend"]), rate=U(rng, 10, 60), reply=U(rng, 0.5, 0.9),
                 night=U(rng, 0.0, 0.3), user_init=U(rng, 0.3, 0.7),
                 stages=[(0, {"greeting": 2, "small_talk": 6, "clingy": 0.3})],
                 reply_mix={"neutral_reply": 4, "warm_reply": 2, "playful_reply": 1})
        if r < 0.25:
            variant, hard = "worried_parent", True
            p.update(rel="family", night=U(rng, 0.3, 0.55), reply=U(rng, 0.4, 0.8), user_init=U(rng, 0.1, 0.3),
                     stages=[(0, {"small_talk": 3, "clingy": 1.5, "surveillance": 0.5, "greeting": 1})],
                     reply_mix={"neutral_reply": 5, "deflect_reply": 2})

    elif scn == "unreciprocated":
        p.update(rel=rng.choice(["stranger", "acquaintance"]), days=int(rng.integers(3, 21)),
                 rate=U(rng, 1, 10), reply=U(rng, 0.1, 0.4), night=U(rng, 0.05, 0.4), rel_age=U(rng, 0, 120),
                 stages=[(0, {"greeting": 3, "flirt": 2, "small_talk": 2, "clingy": 1})],
                 reply_mix={"neutral_reply": 3, "deflect_reply": 4})
        if r < 0.3:
            variant, hard = "apology_stop", True
            p.update(reject_day=int(rng.integers(1, max(2, p["days"] // 2))), apology_stop=True)

    elif scn == "stalking":
        p.update(rel=rng.choice(["stranger", "acquaintance", "partner"]), rate=U(rng, 8, 60),
                 reply=U(rng, 0.0, 0.2), night=U(rng, 0.3, 0.8), burst=U(rng, 0.1, 0.4),
                 latency=U(rng, 60, 400), latency_growth=U(rng, 0.05, 0.3), rel_age=U(rng, 0, 400),
                 stages=[(0, {"greeting": 3, "clingy": 3, "small_talk": 1, "flirt": 1}),
                         (0.4, {"clingy": 3, "surveillance": 2, "greeting": 1, "flirt": 1, "insult": 0.3})],
                 reply_mix={"neutral_reply": 2, "deflect_reply": 4, "rejection": 1},
                 new_accounts=int(rng.integers(0, 4)), block=rng.random() < 0.6)
        if r < 0.2:
            variant, hard = "polite_stalker", True
            p.update(rate=U(rng, 4, 15), night=U(rng, 0.2, 0.5),
                     stages=[(0, {"greeting": 5, "small_talk": 2, "clingy": 1})])
        elif r < 0.35:
            variant, hard = "fearful_replies", True
            p.update(reply=U(rng, 0.2, 0.4), reply_mix={"neutral_reply": 5, "deflect_reply": 3})

    elif scn == "harassment_after_no":
        p.update(days=int(rng.integers(6, 31)), rate=U(rng, 3, 15), reply=U(rng, 0.5, 0.85),
                 night=U(rng, 0.05, 0.4), user_init=U(rng, 0.1, 0.4),
                 rel=rng.choice(["acquaintance", "partner", "friend"]),
                 stages=[(0, {"greeting": 2, "small_talk": 3, "flirt": 2})],
                 reply_mix={"warm_reply": 2, "neutral_reply": 3, "playful_reply": 1})
        p["reject_day"] = int(p["days"] * U(rng, 0.2, 0.5))
        p["post"] = dict(rate_mult=U(rng, 1.0, 3.0), reply=U(rng, 0.0, 0.12), night=U(rng, 0.2, 0.6),
                         mix={"sexual": 2, "clingy": 3, "insult": 1.5, "flirt": 1.5, "threat": 0.2, "surveillance": 0.5},
                         reply_mix={"deflect_reply": 2, "rejection": 2, "neutral_reply": 1})
        p.update(block=rng.random() < 0.4, new_accounts=int(rng.integers(0, 2)))
        if r < 0.2:
            variant, hard = "polite_after_no", True   # keeps "asking nicely": no sexual/insult words
            p["post"]["mix"] = {"clingy": 3, "flirt": 2, "greeting": 2}

    elif scn == "group_bullying":
        p.update(group=int(rng.integers(3, 7)), days=int(rng.integers(2, 16)), rate=U(rng, 5, 30),
                 reply=U(rng, 0.0, 0.3), night=U(rng, 0.05, 0.4), rel="acquaintance",
                 stages=[(0, {"insult": 5, "banter_swear": 1, "small_talk": 1, "threat": 0.2})],
                 reply_mix={"deflect_reply": 3, "neutral_reply": 2, "rejection": 1})

    elif scn == "sextortion":
        p.update(rel="stranger", rel_age=0.0, days=int(rng.integers(1, 6)), rate=U(rng, 3, 20),
                 reply=U(rng, 0.1, 0.6), night=U(rng, 0.1, 0.5),
                 stages=[(0, {"greeting": 3, "flirt": 3}),
                         (0.3, {"sexual": 3, "flirt": 1, "media": 1}),
                         (0.6, {"sextortion": 4, "threat": 2, "media": 1, "clingy": 1})],
                 reply_mix={"neutral_reply": 2, "deflect_reply": 2, "rejection": 2})
    return p, variant, hard


def _pick(mix, rng):
    keys = list(mix)
    w = np.array([mix[k] for k in keys], dtype=float)
    return keys[rng.choice(len(keys), p=w / w.sum())]


def _stage_mix(stages, progress):
    mix = stages[0][1]
    for start, m in stages:
        if progress >= start:
            mix = m
    return mix


def _msg_time(day0, rng, night):
    hour = rng.uniform(0, 5) if rng.random() < night else rng.uniform(8, 24)
    return day0 + timedelta(hours=float(hour))


def gen_conversation(cid, scn, rng, pools, split, max_sender_msgs=400):
    p, variant, hard = scenario_params(scn, rng)
    start = datetime(2026, 1, 1) + timedelta(days=int(rng.integers(0, 250)))
    apps = list(rng.choice(APPS, size=3, replace=False))
    acc_i, app_i = 0, 0
    if p["group"]:
        accounts = [(f"{cid}_m{i}", apps[0]) for i in range(p["group"])]
    else:
        accounts = [(f"{cid}_a0", apps[0])]
    rows, n_sender = [], 0
    rejected, stopped, blocks_left = False, False, p["new_accounts"]
    block_days = sorted(rng.choice(range(1, max(2, p["days"])), size=min(blocks_left + 1, max(1, p["days"] - 1)),
                                   replace=False).tolist()) if p["block"] else []

    def add(ts, is_user, intent, account, app, reply_label=None, text=None):
        rows.append(dict(conversation_id=cid, person_id=cid, account_id=account, app=app, timestamp=ts,
                         is_user=is_user, text=text if text is not None else sample_text(pools, intent, rng),
                         msg_label=MSG_LABEL.get(intent, "other"), reply_label=reply_label))

    for day in range(p["days"]):
        if stopped or n_sender >= max_sender_msgs:
            break
        day0 = start + timedelta(days=day)
        post = rejected and p["post"] is not None
        rate = p["rate"] * (p["post"]["rate_mult"] if post else 1.0)
        reply_prob = p["post"]["reply"] if post else p["reply"]
        night = p["post"]["night"] if post else p["night"]
        mix = p["post"]["mix"] if post else _stage_mix(p["stages"], day / max(1, p["days"] - 1))
        rmix = p["post"]["reply_mix"] if post else p["reply_mix"]
        latency = p["latency"] * (1 + p["latency_growth"] * day)

        times = [_msg_time(day0, rng, night) for _ in range(rng.poisson(rate))]
        if p["burst"] and rng.random() < p["burst"]:
            b0 = _msg_time(day0, rng, night)
            times += [b0 + timedelta(minutes=float(rng.uniform(0, 30))) for _ in range(rng.integers(10, 16))]
        for t in sorted(times):
            account, app = accounts[rng.integers(len(accounts))] if p["group"] else accounts[-1]
            add(t, False, _pick(mix, rng), account, app)
            n_sender += 1
            if rng.random() < reply_prob:
                kind = _pick(rmix, rng)
                add(t + timedelta(minutes=float(rng.exponential(latency))), True, kind, account, app,
                    REPLY_LABEL.get(kind, "neutral"))
        # user-initiated messages (mutual relationships)
        for _ in range(rng.poisson(rate * p["user_init"] * 0.5)):
            kind = _pick(p["reply_mix"], rng)
            add(_msg_time(day0, rng, 0.1), True, kind, accounts[-1][0], accounts[-1][1], REPLY_LABEL.get(kind, "neutral"))

        if p["reject_day"] is not None and day == p["reject_day"] and not rejected:
            t = day0 + timedelta(hours=float(rng.uniform(18, 23.5)))
            add(t, True, "rejection", accounts[-1][0], accounts[-1][1], "reject")
            rejected = True
            if p["apology_stop"]:
                add(t + timedelta(minutes=float(rng.uniform(1, 120))), False, "apology", *accounts[-1])
                stopped = True
        if block_days and day == block_days[0]:
            block_days.pop(0)
            add(day0 + timedelta(hours=23.9), True, "neutral_reply", accounts[-1][0], accounts[-1][1], "block", text="")
            rows[-1].update(text=None, msg_label="block")
            if blocks_left > 0:
                blocks_left -= 1
                acc_i += 1
                app_i = (app_i + int(rng.random() < 0.5)) % len(apps)
                accounts.append((f"{cid}_a{acc_i}", apps[app_i]))
            else:
                stopped = True

    if scn == "sextortion" and not any(r["msg_label"] == "sextortion" for r in rows):
        last = rows[-1]["timestamp"] if rows else start
        add(last + timedelta(minutes=5), False, "sextortion", *accounts[-1])

    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df = df.sort_values("timestamp").reset_index(drop=True)
    df["msg_id"] = np.arange(len(df))
    # hidden notification previews: the text model cannot label these messages
    p_hide = 1.0 if rng.random() < 0.1 else U(rng, 0.1, 0.4)
    hide = (~df["is_user"]) & (rng.random(len(df)) < p_hide)
    df.loc[hide, "text"] = None
    df["user_side_available"] = bool(rng.random() > 0.1)   # live-notification-only conversations
    df["person_label"] = scn
    df["scenario"] = scn
    df["variant"] = variant
    df["hard_case"] = hard
    df["relationship"] = p["rel"]
    df["relationship_age_days"] = float(p["rel_age"])
    df["is_group"] = bool(p["group"])
    df["template_split"] = split
    df["source"] = "synthetic"
    return df


def generate(n_per_class, split, seed, pools):
    rng = np.random.default_rng(seed)
    frames = []
    for scn in CLASSES:
        for i in range(n_per_class):
            df = gen_conversation(f"{split}_{scn}_{i}", scn, rng, pools, split)
            if len(df):
                frames.append(df)
    return pd.concat(frames, ignore_index=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-train", type=int, default=600)
    ap.add_argument("--n-test", type=int, default=150)
    ap.add_argument("--out", default="data/synthetic")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    train_pools, test_pools = split_pools(seed=42)
    tr = generate(args.n_train, "train", 42, train_pools)
    te = generate(args.n_test, "test", 1337, test_pools)
    tr.to_parquet(f"{args.out}/train.parquet", index=False)
    te.to_parquet(f"{args.out}/test.parquet", index=False)
    for name, df in [("train", tr), ("test", te)]:
        print(f"{name}: {df.conversation_id.nunique()} conversations, {len(df)} messages")
        print(df.groupby("person_label").conversation_id.nunique().to_string())


if __name__ == "__main__":
    main()
