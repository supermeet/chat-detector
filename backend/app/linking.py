"""Suggest when two accounts are probably the same person. Suggestions only: the user confirms every link.

Signals: similar handle/name, similar writing style (character n-grams), and a new account appearing
soon after the user blocked another one.
"""
import re
from datetime import timedelta
from difflib import SequenceMatcher

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from .store import store

SUGGEST_AT = 0.5
BLOCK_WINDOW = timedelta(hours=48)


def _norm(s):
    s = s.lower().replace("0", "o").replace("1", "i").replace("3", "e").replace("4", "a").replace("@", "a")
    return re.sub(r"[^a-z]", "", s)


def _name_sim(p, q):
    best = 0.0
    for a in p.account_ids:
        for b in q.account_ids:
            A, B = store.accounts[a], store.accounts[b]
            for x, y in [(A.handle, B.handle), (A.display_name, B.display_name)]:
                nx, ny = _norm(x), _norm(y)
                if nx and ny:
                    best = max(best, SequenceMatcher(None, nx, ny).ratio())
    return best


def _block_then_new(p, q):
    """q's first account appeared within 48 h after the user blocked one of p's accounts."""
    blocks = [m.timestamp for m in store.person_messages(p.id) if m.event == "block"]
    if not blocks:
        return False
    first_q = min(store.accounts[a].first_seen for a in q.account_ids)
    return any(timedelta(0) <= first_q - b <= BLOCK_WINDOW for b in blocks)


def suggestions(limit=20):
    persons = [p for p in store.persons.values() if not p.is_group]
    texts = {p.id: " ".join(m.text for m in store.person_messages(p.id) if not m.is_user and m.text)
             for p in persons}
    with_text = [p for p in persons if len(texts[p.id]) >= 20]
    style = {}
    if len(with_text) >= 2:
        vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), sublinear_tf=True)
        M = vec.fit_transform([texts[p.id] for p in with_text])
        sim = cosine_similarity(M)
        for i, p in enumerate(with_text):
            for j, q in enumerate(with_text):
                style[(p.id, q.id)] = float(sim[i, j])

    out = []
    for i, p in enumerate(persons):
        for q in persons[i + 1:]:
            if q.id in p.rejected_links:
                continue
            name = _name_sim(p, q)
            sty = style.get((p.id, q.id), 0.0)
            timing = _block_then_new(p, q) or _block_then_new(q, p)
            score = 0.45 * name + 0.35 * sty + (0.3 if timing else 0.0)
            if score < SUGGEST_AT:
                continue
            reasons = []
            if name >= 0.6:
                reasons.append(f"Similar handle or name ({name:.0%} match)")
            if sty >= 0.5:
                reasons.append(f"Similar writing style ({sty:.0%})")
            if timing:
                reasons.append("New account appeared within 48 h of a block")
            out.append(dict(person_id=p.id, other_person_id=q.id, score=round(min(score, 1.0), 3),
                            reasons=reasons, person=p.display_name, other=q.display_name))
    return sorted(out, key=lambda s: -s["score"])[:limit]
