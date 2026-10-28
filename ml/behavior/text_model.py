"""Lightweight text models that feed the behaviour model.

- msg model:   sender message text -> msg_label (greeting/flirt/sexual/insult/threat/...)
- reply model: user reply text      -> reply_label (accept/playful/neutral/deflect/reject)

TF-IDF over character n-grams copes with Hinglish spelling variants and leetspeak, trains in
seconds, and is the stand-in until the fine-tuned MuRIL model is ready. Extra labelled messages
from external datasets (HASOC, TRAC, ...) can be added through `extra_msgs`.
"""
import joblib
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline

# generic keyword list for the BASELINE only (what a naive filter would use)
BASELINE_KEYWORDS = [
    "nude", "nudes", "sexy", "sex", "body", "naked", "nangi", "bitch", "slut", "whore", "fuck", "bc", "mc",
    "chutiya", "randi", "kutti", "kamini", "ugly", "loser", "kill", "maar", "acid", "rape", "leak", "viral",
    "dekh lena", "chhodunga", "paise bhej", "pay or", "photo sabko",
]


# labels that fire hard rules (critical level) must be predicted confidently
SEVERE = {"threat", "sextortion"}
SEVERE_MIN_PROB = 0.8


def keyword_flag(text):
    t = str(text).lower()
    return any(k in t for k in BASELINE_KEYWORDS)


def _clf():
    return make_pipeline(
        TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), min_df=2, sublinear_tf=True),
        LogisticRegression(max_iter=2000, class_weight="balanced", C=4.0),
    )


class TextModels:
    def __init__(self):
        self.msg = _clf()
        self.reply = _clf()

    def fit(self, df, extra_msgs=None, max_rows=60000):
        s = df[(~df["is_user"]) & df["text"].notna() & (df["msg_label"] != "block")]
        s = s[["text", "msg_label"]]
        if extra_msgs is not None and len(extra_msgs):
            s = pd.concat([s, extra_msgs[["text", "msg_label"]]], ignore_index=True)
        s = s.drop_duplicates()
        if len(s) > max_rows:
            s = s.sample(max_rows, random_state=42)
        self.msg.fit(s["text"].astype(str), s["msg_label"])
        u = df[df["is_user"] & df["text"].notna() & df["reply_label"].notna() & (df["reply_label"] != "block")]
        u = u[["text", "reply_label"]].drop_duplicates()
        if len(u) > max_rows:
            u = u.sample(max_rows, random_state=42)
        self.reply.fit(u["text"].astype(str), u["reply_label"])
        return self

    def label_messages(self, texts, severe_min_prob=SEVERE_MIN_PROB):
        """Severe labels trigger hard rules downstream, so they need a confident prediction;
        otherwise fall back to the most likely non-severe label."""
        if not len(texts):
            return []
        proba = self.msg.predict_proba(texts)
        classes = np.array(self.msg.classes_)
        severe = np.isin(classes, list(SEVERE))
        best = proba.argmax(1)
        out = classes[best].astype(object)
        weak = severe[best] & (proba.max(1) < severe_min_prob)
        if weak.any():
            fallback = np.where(severe, -1, proba[weak]).argmax(1)
            out[weak] = classes[fallback]
        return list(out)

    def label_replies(self, texts):
        return list(self.reply.predict(texts)) if len(texts) else []

    def relabel(self, df):
        """Replace ground-truth labels with model predictions (realistic end-to-end evaluation)."""
        df = df.copy()
        u = df["is_user"] & df["text"].notna() & (df["text"].astype(str).str.len() > 0)
        if u.any():
            df.loc[u, "reply_label"] = self.label_replies(df.loc[u, "text"].astype(str).tolist())
        return df

    def save(self, path):
        joblib.dump(self, path)

    @staticmethod
    def load(path):
        return joblib.load(path)
