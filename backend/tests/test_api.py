"""End-to-end API tests with the real behaviour model and the stub deepfake connector.

Run from backend/:  SAFESPHERE_MODEL_DIR=<dir with behavior_model.pkl> pytest -q
"""
import io

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.store import store

client = TestClient(app)

WHATSAPP_EXPORT = """12/10/24, 9:41 pm - Messages and calls are end-to-end encrypted.
12/10/24, 9:41 pm - Vikram: hi
12/10/24, 9:42 pm - Vikram: kaisi ho
12/10/24, 9:50 pm - Priya: hmm
13/10/24, 1:10 am - Vikram: reply na
13/10/24, 1:11 am - Vikram: why are you online but not replying
13/10/24, 1:12 am - Vikram: hello??
13/10/24, 9:00 am - Priya: please stop messaging me
13/10/24, 9:05 am - Vikram: itna attitude kyu
13/10/24, 11:40 pm - Vikram: send pics na bas ek baar
14/10/24, 12:30 am - Vikram: <Media omitted>
14/10/24, 12:31 am - Vikram: saw you outside college today
14/10/24, 2:15 am - Vikram: reply na
it's me
14/10/24, 2:16 am - Vikram: This message was deleted
"""


@pytest.fixture(autouse=True)
def clean():
    store.reset()
    yield


def load(name):
    r = client.post(f"/demo/load/{name}")
    assert r.status_code == 200, r.text
    return r.json()


def test_health():
    r = client.get("/health").json()
    assert r["model"]["ready"], r["model"]
    assert r["deepfake"]["mode"] == "stub"


def test_demo_scenarios_listed():
    names = {s["name"] for s in client.get("/demo/scenarios").json()}
    assert {"silent_stalker", "mutual_flirt", "friend_banter", "sextortion"} <= names
    ev = client.get("/demo/scenarios/silent_stalker").json()["events"]
    assert ev[0]["timestamp"] < ev[-1]["timestamp"]


def test_single_notification_scored():
    r = client.post("/ingest/notification", json={"app": "wa", "sender": "X", "text": "hi"}).json()
    assert r["people"][0]["level"] in ("info", "warn", "high", "critical")


def test_evidence_gate_on_first_messages():
    """One or two harmless-looking messages must not reach high: too little history to judge."""
    r = client.post("/ingest/notification", json=[
        {"app": "ig", "sender": "New Person", "text": "hey you looked really nice in class today", "timestamp": "2026-10-28T23:50:00"},
        {"app": "ig", "sender": "New Person", "text": "why don't you reply?", "timestamp": "2026-10-28T23:55:00"}]).json()
    p = r["people"][0]
    assert p["level"] in ("info", "warn"), p
    assert p["early"] is True


def test_sextortion_is_critical():
    r = load("sextortion")
    p = r["people"][0]
    assert p["level"] == "critical", p
    assert r["new_alerts"]


def test_mutual_flirt_and_banter_stay_safe():
    for name in ("mutual_flirt", "friend_banter"):
        store.reset()
        p = load(name)["people"][0]
        assert p["level"] in ("info", "warn"), (name, p["level"], p["risk"], p["reasons"])
        d = client.get(f"/people/{p['id']}").json()
        assert "violation" not in [ph["phase"] for ph in d["consent_timeline"]], (name, d["consent_timeline"])


def test_stalker_linking_and_risk():
    load("silent_stalker")
    people = client.get("/people").json()
    assert len(people) == 3                      # 3 accounts, not yet linked
    sugg = client.get("/links/suggestions").json()
    assert sugg, "expected link suggestions between the stalker's accounts"
    main = next(p for p in people if p["accounts"][0]["app"] == "wa")
    for s in sugg:
        other = s["other_person_id"] if s["person_id"] == main["id"] else s["person_id"]
        if other in store.persons and other != main["id"]:
            client.post(f"/people/{main['id']}/link", json={"other_person_id": other})
    merged = client.get(f"/people/{main['id']}").json()
    assert len(merged["accounts"]) == 3, merged["accounts"]
    assert merged["level"] in ("high", "critical"), merged
    assert merged["reasons"]
    phases = [ph["phase"] for ph in merged["consent_timeline"]]
    assert "rejected" in phases


def test_unlink():
    load("silent_stalker")
    pid = client.get("/people").json()[0]["id"]
    others = [p["id"] for p in client.get("/people").json() if p["id"] != pid]
    client.post(f"/people/{pid}/link", json={"other_person_id": others[0]})
    acc = client.get(f"/people/{pid}").json()["accounts"][-1]["id"]
    r = client.post(f"/people/{pid}/unlink", json={"account_id": acc})
    assert r.status_code == 200, r.text
    assert r.json()["split_off"]["accounts"][0]["id"] == acc


def test_whatsapp_import():
    f = {"file": ("chat.txt", io.BytesIO(WHATSAPP_EXPORT.encode()), "text/plain")}
    prev = client.post("/import/preview", files=f, data={"source": "whatsapp"}).json()
    assert set(prev["participants"]) == {"Vikram", "Priya"}
    f = {"file": ("chat.txt", io.BytesIO(WHATSAPP_EXPORT.encode()), "text/plain")}
    r = client.post("/import", files=f, data={"source": "whatsapp", "user_name": "Priya"})
    assert r.status_code == 200, r.text
    p = r.json()["people"][0]
    assert p["display_name"] == "Vikram"
    msgs = client.get(f"/people/{p['id']}/messages").json()
    assert any(m["media_type"] == "image" for m in msgs)
    assert any(m["text"] and "it's me" in m["text"] for m in msgs)   # multi-line message kept


def test_media_check_stub_and_report():
    r = load("sextortion")
    pid = r["people"][0]["id"]
    img = {"file": ("photo.jpg", io.BytesIO(b"\xff\xd8fake-jpeg-bytes"), "image/jpeg")}
    m = client.post("/media/check", files=img,
                    data={"person_id": pid, "context_text": "10k bhej warna ye photo sabko bhej dunga"})
    assert m.status_code == 200, m.text
    m = m.json()
    assert m["is_stub"] is True and m["deepfake"]["model"] == "stub"
    assert m["verdict"] in ("ai_sextortion", "deepfake_intimate_image", "intimate_image_leak", "cyber_flashing")
    pack = client.post(f"/report/{pid}").json()
    assert pack["items"] and all(len(i["sha256"]) == 64 for i in pack["items"])
    assert len(pack["pack_sha256"]) == 64
    assert pack["channels"][0]["id"] == "1930"
    pdf = client.get(f"/report/{pid}.pdf")
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"


def test_unsupported_media_rejected():
    r = client.post("/media/check", files={"file": ("a.exe", io.BytesIO(b"x"), "application/octet-stream")})
    assert r.status_code == 415


def test_feedback_not_harassment_downgrades():
    pid = load("silent_stalker")["people"][0]["id"]
    before = client.get(f"/people/{pid}").json()["level"]
    after = client.post("/feedback", json={"person_id": pid, "kind": "not_harassment"}).json()
    assert after["trusted"] is True
    assert after["level"] in ("info", "critical"), (before, after["level"])


def test_ui_served_and_message_labels():
    r = client.get("/")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]
    out = client.post("/ingest/notification", json=[
        {"app": "wa", "sender": "Z", "text": "send nudes"},
        {"app": "wa", "sender": "Z", "text": "please stop messaging me", "is_user": True}]).json()
    kinds = [x["kind"] for x in out["labels"]]
    assert kinds == ["message", "reply"], out["labels"]
    msgs = client.get(f"/people/{out['people'][0]['id']}/messages").json()
    assert all("flagged" in m and "label" in m for m in msgs)


def test_media_attach_after_check():
    pid = load("sextortion")["people"][0]["id"]
    m = client.post("/media/check", files={"file": ("a.png", io.BytesIO(b"\x89PNG"), "image/png")}).json()
    r = client.patch(f"/media/{m['id']}", json={"person_id": pid})
    assert r.status_code == 200 and r.json()["person_id"] == pid
    assert any(i["category"].startswith("media_") for i in client.post(f"/report/{pid}").json()["items"])


def test_conclusion_rules_and_privacy(monkeypatch):
    from app import conclusion
    from app.config import settings
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "")
    pid = load("sextortion")["people"][0]["id"]
    out = client.post(f"/conclusion/{pid}").json()
    assert out["source"] == "rules" and out["summary"] and out["acts"]
    assert all(a["section"] in conclusion.LEGAL_OPTIONS for a in out["acts"])
    facts, _ = conclusion.case_facts(pid)
    blob = str(facts).lower()
    assert "10k bhej" not in blob and "priv_x_771" not in blob, "message text or handles must never be sent to the LLM"


def test_delete_all():
    load("mutual_flirt")
    assert client.delete("/data").json()["deleted"]
    assert client.get("/people").json() == []
