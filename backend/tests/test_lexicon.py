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
