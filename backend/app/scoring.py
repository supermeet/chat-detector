"""Bridge between the store and the trained behaviour model in ml/behavior."""
import sys

import pandas as pd

from .config import settings
from .store import Alert, store, utcnow

LEVELS = ["info", "warn", "high", "critical"]
HARMFUL_LABELS = {"stalking", "harassment_after_no", "group_bullying", "sextortion"}
FLAG_MSG_LABELS = {"sexual", "insult", "threat", "sextortion", "surveillance", "clingy", "flirt"}


class ModelNotReady(RuntimeError):
    pass


_scorer = None


def scorer():
    global _scorer
    if _scorer is None:
        if str(settings.ML_DIR) not in sys.path:
            sys.path.insert(0, str(settings.ML_DIR))
        model = settings.MODEL_DIR / "behavior_model.pkl"
        if not model.exists():
            raise ModelNotReady(f"behaviour model not found at {model}. Copy behavior_model.pkl and "
                                f"text_models.pkl from the Colab run into {settings.MODEL_DIR}.")
        from predict import Scorer  # noqa: E402  (ml/behavior)
        _scorer = Scorer(str(settings.MODEL_DIR))
    return _scorer


def model_status():
    try:
        s = scorer()
        return dict(ready=True, version=s.b.get("version"), classes=s.b.get("classes"),
                    text_model=s.tm is not None)
    except ModelNotReady as e:
        return dict(ready=False, error=str(e))


def person_frame(person):
    msgs = store.person_messages(person.id)
    rows = []
    for m in msgs:
        is_block = m.event == "block"
        rows.append(dict(
            conversation_id=person.id, person_id=person.id, account_id=m.account_id, app=m.app,
            timestamp=m.timestamp, is_user=m.is_user or is_block, text=None if is_block else m.text,
            msg_label="block" if is_block else None, reply_label="block" if is_block else None,
            relationship=person.relationship, relationship_age_days=person.relationship_age_days,
            is_group=person.is_group or m.is_group, minor_involved=person.minor_involved))
    df = pd.DataFrame(rows)
    if len(df):
        df["user_side_available"] = bool((df["is_user"] & df["text"].notna()).any())
    return df


def label_texts(texts):
    s = scorer()
    if s.tm is None or not texts:
        return [None] * len(texts)
    return s.tm.label_messages(texts)


def label_replies(texts):
    s = scorer()
    if s.tm is None or not texts:
        return [None] * len(texts)
    return s.tm.label_replies(texts)


def score_person(person_id):
    """Re-score one person, store the result, raise an alert when the level goes up to high/critical."""
    person = store.persons[person_id]
    df = person_frame(person)
    if df.empty or not (~df["is_user"]).any():
        person.result = None
        return None
    if person.is_room and df.loc[~df["is_user"], "account_id"].nunique() < 2:
        person.result = None   # one member alone is already scored as their own person; no duplicate alert
        return None
    res = scorer().score_person(df)
    if person.trusted and res["level"] != "critical":
        res["level"] = "info"
        res["reasons_down"] = ["You marked this person as not harassment"] + res["reasons_down"]
    res["n_messages"] = int(len(df))
    res["scored_at"] = utcnow().isoformat()
    prev = person.result["level"] if person.result else "info"
    person.result = res
    if LEVELS.index(res["level"]) >= 2 and LEVELS.index(res["level"]) > LEVELS.index(prev):
        aid = next(store._alert_ids)
        store.alerts[aid] = Alert(aid, person_id, res["level"], res["label"], _summary(person, res),
                                  res["reasons"], utcnow())
    return res


def _summary(person, res):
    nice = res["label"].replace("_", " ")
    accs = len(person.account_ids)
    extra = f" across {accs} accounts" if accs > 1 else ""
    return f"{person.display_name}: likely {nice}{extra} (risk {res['risk']:.2f})"


def person_view(person, detail=False):
    res = person.result or {}
    accounts = [dict(id=a.id, app=a.app, handle=a.handle, display_name=a.display_name,
                     first_seen=a.first_seen.isoformat(), last_seen=a.last_seen.isoformat())
                for a in (store.accounts[i] for i in person.account_ids)]
    level = res.get("level", "info")
    # for safe people, "why risky" reasons are noise; the UI shows reasons_down instead
    reasons = res.get("reasons", []) if level != "info" else []
    out = dict(id=person.id, display_name=person.display_name, accounts=accounts,
               relationship=person.relationship, trusted=person.trusted, is_group=person.is_group,
               is_room=person.is_room,
               risk=res.get("risk"), level=level, label=res.get("label"), early=bool(res.get("early", False)),
               reasons=reasons, n_messages=res.get("n_messages", 0))
    if detail:
        out.update(reasons_down=res.get("reasons_down", []), minor_signals=res.get("reasons", []) if level == "info" else [],
                   label_probs=res.get("label_probs", {}),
                   facts=res.get("facts", {}), text_available_ratio=res.get("text_available_ratio"),
                   consent_timeline=consent_timeline(person))
    return out


def consent_timeline(person):
    """Phases for the UI's consent bar: neutral/mutual -> rejected -> violation, with dates."""
    msgs = [m for m in store.person_messages(person.id) if m.event == "message"]
    if not msgs:
        return []
    user_texts = [(m, m.text) for m in msgs if m.is_user and m.text]
    reject_at = None
    if user_texts and scorer().tm is not None:
        labels = scorer().tm.label_replies([t for _, t in user_texts])
        for i, ((m, _), lab) in enumerate(zip(user_texts, labels)):
            # a real "no" is not followed by warm/playful replies ("hehe stop it 😂" is not a no)
            if lab == "reject" and not any(x in ("accept", "playful") for x in labels[i + 1:i + 4]):
                reject_at = m.timestamp
                break
    replies = sum(1 for m in msgs if m.is_user)
    sent = sum(1 for m in msgs if not m.is_user)
    phases = [dict(phase="mutual" if replies >= 0.5 * sent else "unreciprocated",
                   start=msgs[0].timestamp.isoformat())]
    if reject_at:
        after = sum(1 for m in msgs if not m.is_user and m.timestamp > reject_at)
        phases.append(dict(phase="rejected", start=reject_at.isoformat()))
        if after:
            phases.append(dict(phase="violation", start=reject_at.isoformat(), messages_after_no=after))
    return phases
