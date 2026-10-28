"""Adaptive slang list (FINAL_IDEA §4.4): catches new slang, code words and obfuscated spellings without retraining.

- Normalisation (`skeleton`): leetspeak, symbols inside words, spaced-out letters, stretched letters.
- Combined with the text model as "final = max(model, word list)", ranked by harm (`upgrade`). Terms are
  human-approved, so a threat/sextortion match counts as confident for the hard rules.
- "Refusal signal" terms teach the reply classifier what a "no" looks like (`reply_override`), unless the model
  already reads the reply as warm or playful ("hehe stop it 😂" is not a no).
- The seed file reloads when it changes on disk; terms added or approved in the app apply immediately.
"""
import itertools
import json
import re
import threading
import unicodedata
from datetime import datetime

from .config import settings

CATEGORIES = {   # UI category -> message label the behaviour model understands (None = reply-side signal)
    "Refusal signal": None, "Bullying": "insult", "Sextortion": "sextortion", "Extortion": "sextortion",
    "Stalking": "surveillance", "Threat": "threat", "Sexual harassment": "sexual",
    "Self-harm incitement": "threat",   # the model has no self-harm label; pushing self-harm is treated as a threat
}
SEVERITIES = ("info", "warn", "high", "critical")
HARM_RANK = {"surveillance": 1, "insult": 2, "sexual": 3, "threat": 4, "sextortion": 5}
LEET = str.maketrans({"@": "a", "4": "a", "3": "e", "1": "i", "0": "o", "$": "s", "5": "s", "7": "t"})
ZERO_WIDTH = re.compile("[​-‏⁠﻿]")


def skeleton(text):
    """Comparable form of a word or message: 'CH4PRI', 'c h a p r i', 'chaaapri' -> 'chapri'.
    Doubled letters collapse too ('chhapri', 'maaal'), so it is for matching, not for display."""
    return re.sub(r"(.)\1+", r"\1", readable(text))


def readable(text):
    """Normalised text to show the user: same tokens as skeleton(), only runs of 3+ letters squeezed."""
    s = ZERO_WIDTH.sub("", unicodedata.normalize("NFKC", str(text)).lower()).translate(LEET)
    s = re.sub(r"(?<=[^\W_])[.*_\-'’]+(?=[^\W_])", "", s)        # b.i.t.c.h, sl*t
    s = re.sub(r"[^\wऀ-ॿ]+|_", " ", s)
    tokens, out, run = s.split(), [], []
    for t in tokens + [""]:                                       # join 3+ spaced-out single letters: k y s
        if len(t) == 1:
            run.append(t)
            continue
        out.extend(["".join(run)] if len(run) >= 3 else run)
        run = []
        if t:
            out.append(t)
    return re.sub(r"(.)\1{2,}", r"\1", " ".join(out))


def _is_emoji_only(term):
    return not skeleton(term)


def _today():
    return datetime.now().strftime("%d %b").lstrip("0")


class Lexicon:
    def __init__(self, path):
        self.path = path
        self.lock = threading.RLock()
        self.reset()

    def reset(self):
        with self.lock:
            self.added, self.pending, self.log = [], [], []
            self._ids = itertools.count(1)
            self._mtime, self._seed, self._index = None, [], None
            self.version = 0
            self._reload_if_changed()

    # --- storage ---------------------------------------------------------------------------
    def _reload_if_changed(self):
        try:
            mtime = self.path.stat().st_mtime
        except OSError:
            mtime = None
        if mtime == self._mtime and self._index is not None:
            return
        self._mtime = mtime
        raw = json.loads(self.path.read_text(encoding="utf-8")).get("terms", []) if mtime else []
        self._seed = [dict(id=f"s{i}", term=t["term"], cat=t["cat"], sev=t.get("sev", "warn"),
                           variants=list(t.get("variants", [])), src=t.get("src", "Seed"), date=t.get("date", ""))
                      for i, t in enumerate(raw) if t.get("cat") in CATEGORIES]
        self._rebuild()

    def _rebuild(self):
        index = []
        for t in self._seed + self.added:
            for form in [t["term"]] + t["variants"]:
                if _is_emoji_only(form):
                    index.append((None, form.strip(), t))
                elif skeleton(form):
                    index.append((skeleton(form).split(), None, t))
        self._index = index
        self.version += 1

    def terms(self):
        with self.lock:
            self._reload_if_changed()
            return self._seed + self.added

    def add_term(self, term, cat, sev, variants=(), src="User", log_as=None):
        with self.lock:
            t = dict(id=f"u{next(self._ids)}", term=term.strip(), cat=cat, sev=sev,
                     variants=[v.strip() for v in variants if v and v.strip()], src=src, date=_today())
            self.added.insert(0, t)
            self._rebuild()
            self.log.insert(0, dict(t=log_as or f'Added "{t["term"]}"', when=_today()))
            return t

    def add_pending(self, term, cat="Bullying", sev="warn", src="User", note=""):
        with self.lock:
            p = dict(id=f"q{next(self._ids)}", term=term.strip(), cat=cat, sev=sev, src=src, note=note)
            self.pending.append(p)
            return p

    def resolve_pending(self, pid, approve, edits=None):
        with self.lock:
            p = next((x for x in self.pending if x["id"] == pid), None)
            if p is None:
                return None
            self.pending.remove(p)
            if not approve:
                self.log.insert(0, dict(t=f'Rejected "{p["term"]}"', when=_today()))
                return p
            e = edits or {}
            return self.add_term(e.get("term") or p["term"], e.get("cat") or p["cat"], e.get("sev") or p["sev"],
                                 e.get("variants") or [], src=p["src"], log_as=f'Approved "{e.get("term") or p["term"]}"')

    # --- matching --------------------------------------------------------------------------
    def analyse(self, text):
        """-> (normalised text, tokens, matches). Matches are whole-token sequences, one per term."""
        with self.lock:
            self._reload_if_changed()
            norm = readable(text or "")
            shown = norm.split()
            tokens = [skeleton(w) for w in shown]
            hits, matches, seen = [False] * len(tokens), [], set()
            for toks, emoji, t in self._index:
                found = False
                if emoji is not None:
                    found = emoji in unicodedata.normalize("NFKC", str(text or ""))
                else:
                    n = len(toks)
                    for i in range(len(tokens) - n + 1):
                        if tokens[i:i + n] == toks:
                            found = True
                            for j in range(i, i + n):
                                hits[j] = True
                if found and t["id"] not in seen:
                    seen.add(t["id"])
                    matches.append(dict(term=t["term"], cat=t["cat"], sev=t["sev"], label=CATEGORIES[t["cat"]]))
            return norm, [dict(w=w, hit=h) for w, h in zip(shown, hits)], matches

    def match(self, text):
        return self.analyse(text)[2]

    def label_for(self, text):
        """Most harmful message label among matched terms, or None."""
        labels = [m["label"] for m in self.match(text) if m["label"]]
        return max(labels, key=lambda lab: HARM_RANK[lab]) if labels else None

    def upgrade(self, text, model_label):
        """final = max(model, word list), by harm."""
        lex = self.label_for(text)
        return lex if lex and HARM_RANK[lex] > HARM_RANK.get(model_label, 0) else model_label

    def reply_override(self, text, model_label):
        if model_label in ("accept", "playful", "reject", "block"):
            return model_label
        return "reject" if any(m["cat"] == "Refusal signal" for m in self.match(text)) else model_label


LEET_OUT = {"a": "@", "i": "1", "o": "0", "e": "3", "s": "$"}


def suggest_rules(term):
    """Spellings people use to dodge filters, without any AI."""
    t = term.strip().lower()
    out = [t.replace(c, r) for c, r in LEET_OUT.items() if c in t]
    out.append("".join(LEET_OUT.get(c, c) for c in t))
    if " " in t:
        out.append(t.replace(" ", ""))
    else:
        out.append(" ".join(t))
    m = re.search(r"[aeiou]", t)
    if m:
        out.append(t[:m.end()] + t[m.start()] * 2 + t[m.end():])
    out.append(re.sub(r"(?<=\w)[aeiou](?=\w)", "", t))
    seen, res = {t}, []
    for v in out:
        if v and v not in seen:
            seen.add(v)
            res.append(v)
    return res[:8]


lex = Lexicon(settings.LEXICON_PATH)
