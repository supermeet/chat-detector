"""Print how each demo scenario scores through the API (sanity check before a demo).

    python scripts/demo_report.py      (from backend/)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.store import store  # noqa: E402

c = TestClient(app)
for s in c.get("/demo/scenarios").json():
    store.reset()
    c.post(f"/demo/load/{s['name']}")
    if s["name"] == "silent_stalker":
        people = c.get("/people").json()
        main = next(p for p in people if p["accounts"][0]["app"] == "wa")
        sugg = c.get("/links/suggestions").json()
        print(f"\n[{s['name']}] link suggestions:")
        for g in sugg:
            print(f"   {g['person']} <-> {g['other']}  {g['score']}  {g['reasons']}")
        for p in people:
            if p["id"] != main["id"]:
                c.post(f"/people/{main['id']}/link", json={"other_person_id": p["id"]})
    for p in c.get("/people").json():
        d = c.get(f"/people/{p['id']}").json()
        print(f"\n[{s['name']}] {d['display_name']} ({len(d['accounts'])} accounts): level={d['level']} "
              f"risk={d['risk']} label={d['label']}")
        for r in d["reasons"]:
            print("   ↑", r)
        for r in d["reasons_down"]:
            print("   ↓", r)
        print("   consent:", [ph["phase"] for ph in d["consent_timeline"]])
