"""Live chatroom support: each room message is scored for the member AND for the room as a group.

Run from backend/:  .venv/Scripts/python -m pytest -q
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.store import store

client = TestClient(app)
ROOM = "Class 12-B"


@pytest.fixture(autouse=True)
def clean():
    store.reset()
    yield


def msg(sender, text, ts, is_user=False):
    return dict(app="web", sender=sender.title(), sender_handle=sender, text=text, timestamp=ts, is_user=is_user,
                room=ROOM, relationship="acquaintance")


PILE_ON = [
    msg("rohan", "full chapri hai tu", "2026-10-27T19:00:00"), msg("sneha", "shakal dekhi hai apni", "2026-10-27T19:01:00"),
    msg("kabir", "nobody likes you", "2026-10-27T19:02:00"), msg("rohan", "loser", "2026-10-27T19:03:00"),
    msg("rohan", "please stop", "2026-10-27T19:05:00", is_user=True),
    msg("sneha", "moti kahin ki", "2026-10-27T19:06:00"), msg("kabir", "everyone laughs at you", "2026-10-27T19:07:00"),
    msg("ishaan", "go cry somewhere", "2026-10-27T19:08:00"), msg("rohan", "tu kisi kaam ki nahi", "2026-10-27T19:09:00"),
    msg("sneha", "kitni dumb hai tu", "2026-10-28T15:00:00"), msg("ishaan", "useless", "2026-10-28T15:02:00"),
    msg("kabir", "cheap lagti hai", "2026-10-28T15:03:00"),
    msg("kabir", "leave me alone", "2026-10-28T15:05:00", is_user=True),
    msg("rohan", "kaali kalooti", "2026-10-28T15:06:00"),
]


def test_room_pile_on_scored_as_group():
    r = client.post("/ingest/notification", json=PILE_ON).json()
    rooms = [p for p in r["people"] if p["is_room"]]
    assert len(rooms) == 1, r["people"]
    room = rooms[0]
    assert room["display_name"] == ROOM
    assert len(room["accounts"]) == 4
    assert room["level"] in ("high", "critical"), room
    assert room["label"] == "group_bullying", room
    members = [p for p in r["people"] if not p["is_room"]]
    assert {p["accounts"][0]["handle"] for p in members} == {"rohan", "sneha", "kabir", "ishaan"}
    assert not any(p["is_group"] for p in members)
    assert any(a["person_id"] == room["id"] for a in r["new_alerts"])


def test_room_single_member_not_scored_as_room():
    batch = [msg("vikram", t, f"2026-10-27T2{i}:00:00") for i, t in enumerate(["hi", "reply na", "hello??", "??"])]
    r = client.post("/ingest/notification", json=batch).json()
    room = next(p for p in r["people"] if p["is_room"])
    assert room["risk"] is None and room["level"] == "info"
    vikram = next(p for p in r["people"] if not p["is_room"])
    assert vikram["n_messages"] == 4


def test_room_labels_one_per_notification():
    r = client.post("/ingest/notification", json=PILE_ON).json()
    assert len(r["message_ids"]) == len(PILE_ON)
    assert [x["kind"] for x in r["labels"]] == ["reply" if m["is_user"] else "message" for m in PILE_ON]


def test_room_reset_clears_rooms():
    client.post("/ingest/notification", json=PILE_ON[:3])
    client.delete("/data")
    r = client.post("/ingest/notification", json=PILE_ON[:3]).json()
    room = next(p for p in r["people"] if p["is_room"])
    assert len(room["accounts"]) == 3


# ---------------------------------------------------------------- room scenarios (what the extension would send)
MENTION = r"@{name}(?!\w)"


def to_notifications(sc):
    """Python mirror of extension/lib/core.js toNotification: only messages aimed at the user, plus the user's own
    messages attributed to the member they answer (or the last member who targeted them)."""
    import re
    self_id, self_name, members = sc["self"]["id"], sc["self"]["name"], sc["members"]
    pat = re.compile(MENTION.format(name=re.escape(self_name)) + r"[,:]?\s*", re.I)
    last, out = None, []
    for e in sc["events"]:
        text = e.get("text")
        if e.get("media"):
            text = {"image": "📷 Photo", "video": "🎥 Video", "audio": "🎤 Voice message"}[e["media"]]
        base = dict(app="web", timestamp=e["timestamp"], room=sc["room"], relationship="acquaintance",
                    media_type=e.get("media"))
        if e["from"] == "self":
            target = e.get("reply_to") if e.get("reply_to") in members else last
            if target is None:
                continue
            out.append(dict(base, sender=members[target], sender_handle=target, text=text, is_user=True))
        elif (text and pat.search(text)) or e.get("reply_to") == "self":
            last = e["from"]
            out.append(dict(base, sender=members[e["from"]], sender_handle=e["from"],
                            text=(pat.sub("", text).strip() or text) if text else None))
    return out


def play(name):
    sc = client.get(f"/demo/rooms/{name}").json()
    batch = to_notifications(sc)
    assert batch, name
    return sc, client.post("/ingest/notification", json=batch).json()


def test_rooms_listed():
    names = {r["name"] for r in client.get("/demo/rooms").json()}
    assert names == {"pile_on", "banter", "singled_out", "sextortion"}


def test_room_scenario_has_bystanders_and_clock():
    sc = client.get("/demo/rooms/pile_on").json()
    ts = [e["timestamp"] for e in sc["events"]]
    assert ts == sorted(ts)
    assert len(to_notifications(sc)) < len(sc["events"]), "bystander chatter must be filtered out"


def test_room_pile_on_reaches_group_bullying():
    _, r = play("pile_on")
    room = next(p for p in r["people"] if p["is_room"])
    assert room["level"] in ("high", "critical") and room["label"] == "group_bullying", room


def test_room_banter_stays_quiet():
    _, r = play("banter")
    assert all(p["level"] in ("info", "warn") for p in r["people"]), [(p["display_name"], p["level"]) for p in r["people"]]
    assert r["new_alerts"] == []


def test_room_singled_out_after_no():
    _, r = play("singled_out")
    member = next(p for p in r["people"] if not p["is_room"])
    assert member["level"] in ("high", "critical"), member
    assert member["label"] in ("stalking", "harassment_after_no"), member
    phases = [ph["phase"] for ph in client.get(f"/people/{member['id']}").json()["consent_timeline"]]
    assert "rejected" in phases and "violation" in phases, phases


def test_room_sextortion_critical():
    _, r = play("sextortion")
    member = next(p for p in r["people"] if not p["is_room"])
    assert member["level"] == "critical", member


def test_chatroom_page_served():
    r = client.get("/chatroom/")
    assert r.status_code == 200 and 'id="room"' in r.text


def test_room_pack_does_not_claim_impersonation():
    """A room's accounts are different members, not one person's fake accounts: no IT Act 66C/66D."""
    r = client.post("/ingest/notification", json=PILE_ON).json()
    room = next(p for p in r["people"] if p["is_room"])
    sections = [l["section"] for l in client.post(f"/report/{room['id']}").json()["legal"]]
    assert "IT Act 66C / 66D" not in sections, sections


def test_room_wording_says_members_not_accounts():
    r = client.post("/ingest/notification", json=PILE_ON).json()
    alert = next(a for a in r["new_alerts"] if a["person_id"] == next(p["id"] for p in r["people"] if p["is_room"]))
    assert "4 members" in alert["summary"] and "accounts" not in alert["summary"], alert["summary"]
    assert not any("accounts" in x for x in alert["reasons"]), alert["reasons"]
    assert any("4 members of the room" in x for x in alert["reasons"]), alert["reasons"]


def test_pile_on_teaches_new_slang():
    from app import lexicon
    lexicon.lex.reset()
    play("pile_on")
    assert any(p["term"] == "behenji" and p["src"] == "Auto" for p in lexicon.lex.pending), lexicon.lex.pending
    lexicon.lex.reset()
