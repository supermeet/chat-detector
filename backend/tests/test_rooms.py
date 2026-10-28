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
