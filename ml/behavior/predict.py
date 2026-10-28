"""Score one person and explain why. This is what the FastAPI backend calls.

    from predict import Scorer
    scorer = Scorer("models")
    result = scorer.score_person(messages_df)
    # {"risk": 0.86, "level": "high", "label": "harassment_after_no", "reasons": [...], ...}

Explanations use LightGBM's exact SHAP contributions (pred_contrib) rendered through fixed
templates. No AI model is involved in the decision or the reasons.
"""
import joblib
import numpy as np
import pandas as pd

from features import FEATURES, add_observed_labels, person_features


def _pct(v):
    return f"{v * 100:.0f}%"


# feature -> (sentence when it pushes risk UP, sentence when it pushes risk DOWN)
TEMPLATES = {
    "msgs_after_reject": (lambda v: f"Sent {v:.0f} messages after you said no", None),
    "sexual_after_reject": (lambda v: f"Sent {v:.0f} sexual messages after you said no", None),
    "insult_after_reject": (lambda v: f"Sent {v:.0f} insults after you said no", None),
    "reply_ratio": (lambda v: f"You replied to only {_pct(v)} of their messages",
                    lambda v: f"You reply to {_pct(min(v, 1))} of their messages"),
    "unanswered_streak_max": (lambda v: f"Sent up to {v:.0f} messages in a row without a reply", None),
    "msgs_while_ignored": (lambda v: f"Kept messaging {v:.0f} times while you didn't respond", None),
    "night_ratio": (lambda v: f"{_pct(v)} of messages were sent between midnight and 5 AM", None),
    "msgs_per_day": (lambda v: f"About {v:.0f} messages per day", None),
    "burst_count": (lambda v: "Sent bursts of 10+ messages within 30 minutes", None),
    "accounts_count": (lambda v: f"Contacted you from {v:.0f} accounts", None),
    "platforms_count": (lambda v: f"Contacted you on {v:.0f} different apps", None),
    "new_account_after_block": (lambda v: f"Created {v:.0f} new account(s) after being blocked", None),
    "surveillance_count": (lambda v: f"{v:.0f} messages tracking where you are or who you're with", None),
    "threat_count": (lambda v: f"{v:.0f} threatening messages", None),
    "sextortion_count": (lambda v: f"{v:.0f} blackmail / sextortion messages", None),
    "sexual_ratio": (lambda v: f"{_pct(v)} of readable messages are sexual", None),
    "insult_ratio": (lambda v: f"{_pct(v)} of readable messages are insults", None),
    "clingy_ratio": (lambda v: f"{_pct(v)} of messages demand replies (\"reply na\", \"why ignoring\")", None),
    "toxicity_slope": (lambda v: "Messages are getting more hostile over time", None),
    "escalation_gap": (lambda v: "They are far more sexual or explicit than you are", None),
    "initiation_ratio": (lambda v: f"They start {_pct(v)} of conversations",
                         lambda v: f"You start {_pct(1 - v)} of conversations"),
    "reply_reject_share": (lambda v: "You have asked them to stop", None),
    "reply_deflect_share": (lambda v: f"{_pct(v)} of your replies avoid the conversation", None),
    "reply_accept_share": (None, lambda v: f"{_pct(v)} of your replies are warm or positive"),
    "reply_playful_share": (None, lambda v: f"{_pct(v)} of your replies are playful banter"),
    "known_contact": (None, lambda v: "This is a known contact"),
    "relationship_age_days": (None, lambda v: f"You have known them for about {v:.0f} days"),
    "apologised_after_reject": (None, lambda v: "They apologised after you said no"),
    "media_count": (lambda v: f"Sent {v:.0f} photo/video/voice files", None),
}


# an "up" reason only makes sense from this value on (e.g. "contacted you from 1 account" is not a reason)
MIN_VALUE = {"accounts_count": 2, "platforms_count": 2, "new_account_after_block": 1, "msgs_after_reject": 1,
             "sexual_after_reject": 1, "insult_after_reject": 1, "surveillance_count": 1, "threat_count": 1,
             "sextortion_count": 1, "media_count": 1, "burst_count": 1, "unanswered_streak_max": 3,
             "night_ratio": 0.2, "sexual_ratio": 0.05, "insult_ratio": 0.05, "clingy_ratio": 0.05,
             "reply_reject_share": 0.01, "reply_deflect_share": 0.1, "toxicity_slope": 0.001,
             "escalation_gap": 0.1, "msgs_while_ignored": 3}


MIN_EVIDENCE_MSGS = 5


def has_evidence(f):
    """Enough behaviour to judge a pattern: 5+ messages from them, or they kept going after a "no".
    The model learned from whole conversations; one or two messages are outside what it was trained on."""
    n_sender = round((f.get("msgs_per_day") or 0) * (f.get("span_days") or 0))
    return n_sender >= MIN_EVIDENCE_MSGS or (f.get("msgs_after_reject") or 0) >= 1


def consistent_label(classes, probs, f):
    """Most likely behaviour type, except "sextortion" needs evidence of it (a demand/threat message or media).
    Short conversations otherwise look like sextortion to the model, because sextortion chats are short."""
    order = np.argsort(-np.asarray(probs))
    evidence = (f.get("sextortion_count") or 0) + (f.get("threat_count") or 0) + (f.get("media_count") or 0)
    readable = (f.get("text_available_ratio") or 0) >= 0.7   # if previews were hidden, absence proves nothing
    for j in order:
        if classes[j] == "sextortion" and evidence == 0 and readable:
            continue
        return classes[j]
    return classes[int(order[0])]


def level_for(risk, f, thresholds):
    level = "info"
    for name in ("warn", "high", "critical"):
        if risk >= thresholds[name]:
            level = name
    # hard rules: never left to the model. One severe message alone does not override clearly mutual,
    # low-risk contact (e.g. friends' banter misread as a threat); two, or one plus some risk, does.
    severe = (f.get("sextortion_count") or 0) + (f.get("threat_count") or 0)
    if (f.get("minor_involved") or 0) >= 1 or severe >= 2 or (severe >= 1 and risk >= thresholds["warn"]):
        return "critical"
    # evidence gate: without enough history the model may only warn
    if level in ("high", "critical") and not has_evidence(f):
        level = "warn"
    return level


class Scorer:
    def __init__(self, model_dir="models", text_models=True):
        self.b = joblib.load(f"{model_dir}/behavior_model.pkl")
        self.tm = None
        if text_models:
            try:
                self.tm = joblib.load(f"{model_dir}/text_models.pkl")
            except FileNotFoundError:
                pass

    def score_features(self, X):
        """X: DataFrame of FEATURES rows -> list of result dicts."""
        b = self.b
        X = X[FEATURES]
        raw = b["binary"].predict_proba(X)[:, 1]
        risk = b["iso"].predict(raw)
        probs = b["multi"].predict_proba(X)
        contrib = b["binary"].booster_.predict(X, pred_contrib=True)[:, :-1]
        out = []
        for i in range(len(X)):
            f = X.iloc[i].to_dict()
            order = np.argsort(-contrib[i])
            up, down = [], []
            for j in order:
                name, c, v = FEATURES[j], contrib[i, j], f[FEATURES[j]]
                t = TEMPLATES.get(name)
                if t is None or v is None or (isinstance(v, float) and np.isnan(v)):
                    continue
                if name in MIN_VALUE and v < MIN_VALUE[name]:
                    continue
                if c > 0.05 and t[0] and len(up) < 5:
                    up.append(t[0](v))
            for j in order[::-1]:
                name, c, v = FEATURES[j], contrib[i, j], f[FEATURES[j]]
                t = TEMPLATES.get(name)
                if t is None or v is None or (isinstance(v, float) and np.isnan(v)):
                    continue
                if c < -0.05 and t[1] and len(down) < 3:
                    down.append(t[1](v))
            out.append(dict(
                risk=round(float(risk[i]), 3),
                level=level_for(float(risk[i]), f, b["thresholds"]),
                early=not has_evidence(f),
                label=consistent_label(b["classes"], probs[i], f),
                label_probs={c: round(float(p), 3) for c, p in zip(b["classes"], probs[i])},
                reasons=up, reasons_down=down,
                facts={k: (None if isinstance(v, float) and np.isnan(v) else round(float(v), 3)) for k, v in f.items()},
                text_available_ratio=f.get("text_available_ratio"),
            ))
        return out

    def score_person(self, msgs):
        """msgs: DataFrame in the common schema for ONE person."""
        if self.tm is not None:
            msgs = self.tm.relabel(msgs)
            df = add_observed_labels(msgs, self.tm.label_messages)
        else:
            df = add_observed_labels(msgs)
        X = pd.DataFrame([person_features(df)], columns=FEATURES)
        return self.score_features(X)[0]
