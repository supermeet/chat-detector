"""Adaptive slang list (PS deliverable 3): normalisation, matching, hot updates without retraining, review queue.

Run from backend/:  .venv/Scripts/python -m pytest -q
"""
import json
import os
import time

import pytest
from fastapi.testclient import TestClient

from app import lexicon
from app.main import app
from app.store import store

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean():
    store.reset()
    lexicon.lex.reset()
    yield
    lexicon.lex.reset()


# ---------------------------------------------------------------- normalisation
@pytest.mark.parametrize("raw,expected", [
    ("ch4pri", "chapri"), ("CH@PRI", "chapri"), ("c h a p r i", "chapri"), ("chaaapri", "chapri"),
    ("b.i.t.c.h", "bitch"), ("V1RAL KR DUNGA!!", "viral kr dunga"), ("k y s", "kys"), ("p3$e bhej", "pese bhej"),
])
def test_skeleton(raw, expected):
    assert lexicon.skeleton(raw) == expected


def test_match_multiword_variant_and_whole_tokens_only():
    labels = {m["term"] for m in lexicon.lex.match("u r such a ch4pri, paisa bhej warna v1ral kr dunga")}
    assert {"ch@pri", "paise bhej", "viral kar dunga"} <= labels
    assert lexicon.lex.match("chaprasi aaya tha") == []      # "chapri" inside another word is not a match


def test_emoji_terms_match_raw_text():
    assert any(m["term"] == "🍆🍑" for m in lexicon.lex.match("send 🍆🍑 tonight"))


# ---------------------------------------------------------------- combined with the text model
def test_lexicon_upgrades_model_label():
    out = client.post("/lexicon/test", json={"text": "tu full ch4pri hai"}).json()
    assert out["label"] == "insult"
    assert out["normalised"] == "tu full chapri hai"
    assert [t["hit"] for t in out["tokens"]] == [False, False, True, False]


def test_new_term_takes_effect_without_retraining():
    r = client.post("/ingest/notification", json={"app": "wa", "sender": "X", "text": "you are such a zorkhead"}).json()
    pid = r["people"][0]["id"]
    assert r["labels"][0]["label"] != "insult"
    added = client.post("/lexicon/terms", json={"term": "zorkhead", "cat": "Bullying", "sev": "warn",
                                                "variants": ["z0rkhead"]})
    assert added.status_code == 200, added.text
    msgs = client.get(f"/people/{pid}/messages").json()
    assert msgs[0]["label"] == "insult" and msgs[0]["flagged"] is True
    r2 = client.post("/ingest/notification", json={"app": "wa", "sender": "X", "text": "z0rkhead"}).json()
    assert r2["labels"][0]["label"] == "insult"


def test_severe_lexicon_label_counts_as_confident():
    out = client.post("/lexicon/test", json={"text": "kys"}).json()
    assert out["label"] == "threat"


def test_refusal_signal_teaches_reply_classifier_but_not_over_playful():
    assert lexicon.lex.reply_override("bas karo yaar", "neutral") == "reject"
    assert lexicon.lex.reply_override("bas karo yaar", "deflect") == "reject"
    assert lexicon.lex.reply_override("hehe stop it 😂", "playful") == "playful"
    assert lexicon.lex.reply_override("ok see you", "neutral") == "neutral"


# ---------------------------------------------------------------- review queue + feedback
def test_pending_approve_and_reject():
    p = client.post("/lexicon/pending", json={"term": "lafanga", "cat": "Bullying", "sev": "warn", "src": "User",
                                             "note": "missed"}).json()
    assert any(x["id"] == p["id"] for x in client.get("/lexicon").json()["pending"])
    client.post(f"/lexicon/pending/{p['id']}/approve", json={})
    data = client.get("/lexicon").json()
    assert any(t["term"] == "lafanga" for t in data["terms"]) and not data["pending"]
    q = client.post("/lexicon/pending", json={"term": "nope", "cat": "Bullying", "sev": "warn"}).json()
    client.post(f"/lexicon/pending/{q['id']}/reject")
    data = client.get("/lexicon").json()
    assert not any(t["term"] == "nope" for t in data["terms"]) and not data["pending"]
    assert [entry["t"] for entry in data["log"][:2]] == ['Rejected "nope"', 'Approved "lafanga"']


def test_missed_feedback_goes_to_review_queue():
    pid = client.post("/ingest/notification", json={"app": "wa", "sender": "X", "text": "hi"}).json()["people"][0]["id"]
    client.post("/feedback", json={"person_id": pid, "kind": "missed_harassment", "note": "tharki"})
    assert any(p["term"] == "tharki" and p["src"] == "User" for p in client.get("/lexicon").json()["pending"])


def test_bad_category_rejected():
    r = client.post("/lexicon/terms", json={"term": "x", "cat": "Nonsense", "sev": "warn"})
    assert r.status_code == 422


# ---------------------------------------------------------------- variants + hot reload of the seed file
def test_suggest_variants_without_ai(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "")
    out = client.post("/lexicon/suggest", json={"term": "viral kar dunga"}).json()
    assert out["source"] == "rules"
    assert "v1ral kar dunga" in out["variants"] and "viralkardunga" in out["variants"]
    assert "viral kar dunga" not in out["variants"]


def test_seed_file_hot_reload(tmp_path, monkeypatch):
    seed = tmp_path / "seed.json"
    seed.write_text(json.dumps({"terms": [{"term": "alpha", "cat": "Bullying", "sev": "warn", "variants": []}]}),
                    encoding="utf-8")
    monkeypatch.setattr(lexicon.lex, "path", seed)
    lexicon.lex.reset()
    assert [m["term"] for m in lexicon.lex.match("alpha")] == ["alpha"]
    seed.write_text(json.dumps({"terms": [{"term": "betaword", "cat": "Bullying", "sev": "warn", "variants": []}]}),
                    encoding="utf-8")
    later = time.time() + 5
    os.utime(seed, (later, later))
    assert [m["term"] for m in lexicon.lex.match("betaword alpha")] == ["betaword"]


# ---------------------------------------------------------------- automatic discovery: behaviour teaches vocabulary
def _room(sender, text, minute, day=27, room="Class 12-B", user=False):
    return dict(app="web", sender=sender.title(), sender_handle=sender, text=text, is_user=user, room=room,
                relationship="acquaintance", timestamp=f"2026-10-{day}T19:{minute:02d}:00")


BULLIES = [
    _room("rohan", "full chapri hai tu", 0), _room("sneha", "behenji kahin ki", 1), _room("kabir", "nobody likes you", 2),
    _room("rohan", "loser behenji", 3), _room("rohan", "please stop", 5, user=True), _room("sneha", "moti kahin ki", 6),
    _room("kabir", "everyone laughs at you", 7), _room("ishaan", "go cry somewhere", 8),
    _room("rohan", "tu kisi kaam ki nahi", 9), _room("sneha", "kitni dumb hai tu", 0, day=28),
    _room("ishaan", "useless", 2, day=28), _room("kabir", "cheap lagti hai", 3, day=28),
    _room("kabir", "leave me alone", 5, day=28, user=True), _room("rohan", "kaali kalooti", 6, day=28),
]


def _pending_terms():
    return {p["term"]: p for p in client.get("/lexicon").json()["pending"]}


def test_discovery_suggests_new_word_from_flagged_chats():
    r = client.post("/ingest/notification", json=BULLIES).json()
    assert any(p["is_room"] and p["level"] in ("high", "critical") for p in r["people"])
    p = _pending_terms().get("behenji")
    assert p is not None, _pending_terms()
    assert p["src"] == "Auto" and "2 senders" in p["note"] and "0 safe" in p["note"]
    assert p["cat"] == "Bullying"


def test_discovery_privacy_only_the_term_is_kept():
    client.post("/ingest/notification", json=BULLIES)
    p = _pending_terms()["behenji"]
    assert "kahin" not in str(p) and "loser" not in str(p)


def test_discovery_skips_common_known_and_one_sender_words():
    client.post("/ingest/notification", json=BULLIES)
    terms = _pending_terms()
    assert "kahin" not in terms        # one sender only (sneha twice)
    assert "chapri" not in terms       # already on the list
    assert not any(len(t) < 4 for t in terms)


def test_discovery_ignores_words_also_used_in_safe_chats():
    safe = [dict(app="wa", sender="Didi", text=t, is_user=u, relationship="family",
                 timestamp=f"2026-10-2{d}T1{h}:00:00")
            for d, h, t, u in [(5, 0, "behenji style kurta mast hai", False), (5, 1, "haha thanks", True),
                               (6, 0, "behenji look aaj", False), (6, 1, "😂 love it", True)]]
    client.post("/ingest/notification", json=safe)
    client.post("/ingest/notification", json=BULLIES)
    assert "behenji" not in _pending_terms()


def test_discovery_does_not_resuggest_rejected():
    client.post("/ingest/notification", json=BULLIES)
    qid = _pending_terms()["behenji"]["id"]
    client.post(f"/lexicon/pending/{qid}/reject")
    client.post("/ingest/notification", json=[_room("ishaan", "behenji", 30, day=28)])
    assert "behenji" not in _pending_terms()


def test_approved_discovery_gets_variants_and_applies():
    client.post("/ingest/notification", json=BULLIES)
    t = client.post(f"/lexicon/pending/{_pending_terms()['behenji']['id']}/approve").json()
    assert "b3h3nji" in t["variants"] or "beh3nji" in t["variants"], t["variants"]
    assert client.post("/lexicon/test", json={"text": "b3henji"}).json()["label"] == "insult"
