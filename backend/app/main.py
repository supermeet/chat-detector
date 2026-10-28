"""SafeSphere API. Run:  uvicorn app.main:app --reload --port 8000   (from backend/)

Interactive docs at http://localhost:8000/docs. Contract for the UI team: docs/API_CONTRACT.md.
"""
import hashlib
import json
import logging
from datetime import timedelta
from typing import Optional, Union

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response

from . import conclusion, deepfake, importers, linking, media, report
from .config import BACKEND_DIR, settings
from .schemas import Feedback, LinkRequest, MediaPatch, Notification, PersonPatch, UnlinkRequest
from .scoring import (FLAG_MSG_LABELS, LEVELS, ModelNotReady, label_replies, label_texts, model_status, person_view,
                      score_person)
from .store import MediaCheck, Message, store, utcnow

# never log request bodies: they contain private messages
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

app = FastAPI(title="SafeSphere API", version="0.1.0",
              description="Behaviour-based harassment detection, media checks and evidence packs.")
app.add_middleware(CORSMiddleware, allow_origins=settings.ALLOWED_ORIGINS, allow_methods=["*"],
                   allow_headers=["*"])


def require_key(x_api_key: Optional[str] = Header(None)):
    if settings.API_KEY and x_api_key != settings.API_KEY:
        raise HTTPException(401, "missing or wrong X-API-Key")


@app.exception_handler(ModelNotReady)
async def _model_not_ready(_: Request, exc: ModelNotReady):
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.exception_handler(deepfake.DeepfakeError)
async def _deepfake_error(_: Request, exc: deepfake.DeepfakeError):
    return JSONResponse(status_code=502, content={"detail": str(exc)})


def _person(pid):
    p = store.persons.get(pid)
    if p is None:
        raise HTTPException(404, f"person {pid} not found")
    return p


# ---------------------------------------------------------------- UI
@app.get("/", include_in_schema=False)
def ui():
    if settings.FRONTEND_PATH.exists():
        return FileResponse(settings.FRONTEND_PATH, media_type="text/html")
    return HTMLResponse("<h1>SafeSphere API</h1><p>UI not built: run <code>python frontend/build.py</code>. "
                        "API docs at <a href='/docs'>/docs</a>.</p>")


# ---------------------------------------------------------------- health
@app.get("/health")
def health():
    return dict(status="ok", model=model_status(), deepfake=deepfake.status(), conclusion=conclusion.status(),
                counts=dict(people=len(store.persons), messages=len(store.messages), alerts=len(store.alerts)))


# ---------------------------------------------------------------- ingest (live notifications)
def _add_message(n: Notification, source="notification"):
    ts = (n.timestamp.replace(tzinfo=None) if n.timestamp else utcnow())
    handle = n.sender_handle or n.sender
    # the user's own reply/block belongs to the chat with `sender`
    acc = store.get_or_create_account(n.app, handle, n.sender, ts)
    mid = next(store._msg_ids)
    store.messages[mid] = Message(mid, acc.id, n.app, ts, n.is_user, n.text, n.event, n.media_type,
                                  n.chat, n.is_group, source)
    person = store.persons[acc.person_id]
    if n.is_group:
        person.is_group = True
    if n.relationship and person.relationship == "stranger":
        person.relationship = n.relationship
    return mid, acc


@app.post("/ingest/notification", dependencies=[Depends(require_key)])
def ingest(body: Union[Notification, list[Notification]]):
    items = body if isinstance(body, list) else [body]
    with store.lock:
        touched, ids = {}, []
        for n in items:
            mid, acc = _add_message(n)
            ids.append(mid)
            touched[acc.person_id] = acc.id
        alerts_before = set(store.alerts)
        people = []
        for pid in touched:
            score_person(pid)
            people.append(person_view(store.persons[pid]))
        new_alerts = [_alert_view(store.alerts[a]) for a in store.alerts if a not in alerts_before]
        labels = _message_labels([store.messages[i] for i in ids])
    return dict(message_ids=ids, people=people, new_alerts=new_alerts, labels=labels)


def _message_labels(msgs):
    """What the text models read in each message: label for incoming, reply_label for the user's own."""
    out = {m.id: dict(message_id=m.id, kind="block" if m.event == "block" else ("reply" if m.is_user else "message"),
                      label=None, flagged=False) for m in msgs}
    readable = [m for m in msgs if m.event == "message" and m.text]
    incoming = [m for m in readable if not m.is_user]
    replies = [m for m in readable if m.is_user]
    for m, lab in zip(incoming, label_texts([m.text for m in incoming])):
        out[m.id].update(label=lab, flagged=lab in FLAG_MSG_LABELS - {"flirt"})
    for m, lab in zip(replies, label_replies([m.text for m in replies])):
        out[m.id].update(label=lab)
    return [out[m.id] for m in msgs]


# ---------------------------------------------------------------- chat-export import
def _read_upload(f: UploadFile):
    data = f.file.read()
    if len(data) > settings.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(413, f"file larger than {settings.MAX_UPLOAD_MB} MB")
    return data


@app.post("/import/preview", dependencies=[Depends(require_key)])
def import_preview(file: UploadFile = File(...), source: str = Form("whatsapp")):
    if source not in importers.PARSERS:
        raise HTTPException(400, f"source must be one of {list(importers.PARSERS)}")
    try:
        participants, msgs = importers.parse(source, _read_upload(file))
    except (ValueError, KeyError) as e:
        raise HTTPException(422, f"could not parse {source} export: {e}") from e
    if not msgs:
        raise HTTPException(422, "no messages found; check the export format")
    counts = {p: sum(1 for m in msgs if m["sender"] == p) for p in participants}
    return dict(source=source, participants=participants, message_counts=counts, total=len(msgs),
                first=msgs[0]["timestamp"].isoformat(), last=msgs[-1]["timestamp"].isoformat())


@app.post("/import", dependencies=[Depends(require_key)])
def import_chat(file: UploadFile = File(...), source: str = Form("whatsapp"), user_name: str = Form(...),
                relationship: str = Form("stranger"), person_id: Optional[str] = Form(None)):
    """user_name = which participant is the app user. person_id = merge into an existing person."""
    if source not in importers.PARSERS:
        raise HTTPException(400, f"source must be one of {list(importers.PARSERS)}")
    participants, msgs = importers.parse(source, _read_upload(file))
    if user_name not in participants:
        raise HTTPException(400, f"user_name must be one of {participants}")
    others = [p for p in participants if p != user_name]
    is_group = len(others) > 1
    app_code = importers.APP_CODE[source]
    with store.lock:
        touched = set()
        group_name = file.filename or "imported group"
        for m in msgs:
            is_user = m["sender"] == user_name
            if is_group:
                sender = group_name if is_user else m["sender"]
            else:
                sender = others[0] if others else "unknown"
            n = Notification(app=app_code, sender=sender, text=m["text"], timestamp=m["timestamp"], is_user=is_user,
                             media_type=m["media_type"], is_group=is_group, chat=group_name if is_group else None)
            mid, acc = _add_message(n, source="import")
            touched.add(acc.person_id)
        if is_group:   # a group pile-on is one "person" (the group) with each member as an account
            keep = sorted(touched)[0]
            for pid in sorted(touched)[1:]:
                if pid in store.persons:
                    store.link(keep, store.persons[pid].account_ids[0])
            touched = {keep}
            store.persons[keep].display_name = group_name
            store.persons[keep].is_group = True
        if person_id:
            _person(person_id)
            for pid in list(touched):
                for aid in list(store.persons[pid].account_ids):
                    store.link(person_id, aid)
            touched = {person_id}
        for pid in touched:
            p = store.persons[pid]
            if p.relationship == "stranger":
                p.relationship = relationship
            score_person(pid)
        return dict(imported=len(msgs), people=[person_view(store.persons[p], detail=True) for p in touched])


# ---------------------------------------------------------------- people
@app.get("/people", dependencies=[Depends(require_key)])
def list_people(min_level: str = "info"):
    lv = LEVELS.index(min_level) if min_level in LEVELS else 0
    views = [person_view(p) for p in store.persons.values()]
    views = [v for v in views if LEVELS.index(v["level"]) >= lv]
    return sorted(views, key=lambda v: -(v["risk"] or 0))


@app.get("/people/{pid}", dependencies=[Depends(require_key)])
def get_person(pid: str):
    return person_view(_person(pid), detail=True)


@app.patch("/people/{pid}", dependencies=[Depends(require_key)])
def patch_person(pid: str, body: PersonPatch):
    p = _person(pid)
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(p, k, v)
    score_person(pid)
    return person_view(p, detail=True)


@app.get("/people/{pid}/messages", dependencies=[Depends(require_key)])
def person_messages(pid: str, limit: int = 500):
    _person(pid)
    msgs = store.person_messages(pid)[-limit:]
    labels = {x["message_id"]: x for x in _message_labels(msgs)}
    return [dict(id=m.id, account_id=m.account_id, app=m.app, timestamp=m.timestamp.isoformat(), is_user=m.is_user,
                 text=m.text, event=m.event, media_type=m.media_type, source=m.source,
                 label=labels[m.id]["label"], flagged=labels[m.id]["flagged"]) for m in msgs]


@app.post("/people/{pid}/link", dependencies=[Depends(require_key)])
def link(pid: str, body: LinkRequest):
    _person(pid)
    with store.lock:
        if body.other_person_id:
            for aid in list(_person(body.other_person_id).account_ids):
                store.link(pid, aid)
        elif body.account_id and body.account_id in store.accounts:
            store.link(pid, body.account_id)
        else:
            raise HTTPException(400, "give account_id or other_person_id")
        score_person(pid)
        return person_view(store.persons[pid], detail=True)


@app.post("/people/{pid}/unlink", dependencies=[Depends(require_key)])
def unlink(pid: str, body: UnlinkRequest):
    _person(pid)
    with store.lock:
        p, newp = store.unlink(pid, body.account_id)
        if newp is None:
            raise HTTPException(400, "account not in this person, or it is their only account")
        score_person(p.id)
        score_person(newp.id)
        return dict(person=person_view(p, detail=True), split_off=person_view(newp, detail=True))


@app.get("/links/suggestions", dependencies=[Depends(require_key)])
def link_suggestions():
    return linking.suggestions()


# ---------------------------------------------------------------- alerts & feedback
def _alert_view(a):
    return dict(id=a.id, person_id=a.person_id, level=a.level, label=a.label, summary=a.summary,
                reasons=a.reasons, created_at=a.created_at.isoformat(), dismissed=a.dismissed)


@app.get("/alerts", dependencies=[Depends(require_key)])
def list_alerts(include_dismissed: bool = False):
    out = [_alert_view(a) for a in store.alerts.values() if include_dismissed or not a.dismissed]
    return sorted(out, key=lambda a: a["created_at"], reverse=True)


@app.post("/alerts/{aid}/dismiss", dependencies=[Depends(require_key)])
def dismiss_alert(aid: int):
    a = store.alerts.get(aid)
    if a is None:
        raise HTTPException(404, "alert not found")
    a.dismissed = True
    return _alert_view(a)


@app.post("/feedback", dependencies=[Depends(require_key)])
def feedback(body: Feedback):
    p = _person(body.person_id)
    store.feedback.append(dict(**body.model_dump(), at=utcnow().isoformat(),
                               level_before=(p.result or {}).get("level")))
    if body.kind == "not_harassment":
        p.trusted = True
        for a in store.alerts.values():
            if a.person_id == p.id:
                a.dismissed = True
    score_person(p.id)
    return person_view(p, detail=True)


# ---------------------------------------------------------------- media check (deepfake connector)
def _kind(f: UploadFile):
    ct = (f.content_type or "").lower()
    for k in ("image", "video", "audio"):
        if ct.startswith(k):
            return k
    ext = (f.filename or "").rsplit(".", 1)[-1].lower()
    return {"jpg": "image", "jpeg": "image", "png": "image", "webp": "image", "mp4": "video", "mov": "video",
            "webm": "video", "mp3": "audio", "wav": "audio", "ogg": "audio", "opus": "audio", "m4a": "audio"}.get(ext)


@app.post("/media/check", dependencies=[Depends(require_key)])
def media_check(file: UploadFile = File(...), person_id: Optional[str] = Form(None),
                context_text: Optional[str] = Form(None)):
    kind = _kind(file)
    if kind is None:
        raise HTTPException(415, "unsupported file type; send an image, video or audio file")
    if person_id:
        _person(person_id)
    data = _read_upload(file)
    df = deepfake.analyse(kind, data, file.filename or f"upload.{kind}", context_text)
    v = media.verdict(df, context_text)
    v["deepfake"] = df
    mc_id = next(store._media_ids)
    store.media[mc_id] = MediaCheck(mc_id, kind, file.filename or "", hashlib.sha256(data).hexdigest(), len(data),
                                    person_id, context_text, v, utcnow())
    del data   # the file itself is never kept; only its fingerprint and the result
    return dict(id=mc_id, kind=kind, file_sha256=store.media[mc_id].sha256, **v)


@app.patch("/media/{mid}", dependencies=[Depends(require_key)])
def media_patch(mid: int, body: MediaPatch):
    """Attach an analysed file to a person's case after the fact."""
    mc = store.media.get(mid)
    if mc is None:
        raise HTTPException(404, "media check not found")
    _person(body.person_id)
    mc.person_id = body.person_id
    return dict(id=mc.id, person_id=mc.person_id)


@app.get("/media/{mid}", dependencies=[Depends(require_key)])
def media_get(mid: int):
    mc = store.media.get(mid)
    if mc is None:
        raise HTTPException(404, "media check not found")
    return dict(id=mc.id, kind=mc.kind, filename=mc.filename, file_sha256=mc.sha256, person_id=mc.person_id,
                created_at=mc.created_at.isoformat(), **mc.result)


# ---------------------------------------------------------------- evidence pack
@app.post("/report/{pid}", dependencies=[Depends(require_key)])
def make_report(pid: str):
    _person(pid)
    return report.build_pack(pid)


@app.get("/report/{pid}.pdf", dependencies=[Depends(require_key)])
def make_report_pdf(pid: str):
    _person(pid)
    try:
        pdf = report.pack_pdf(report.build_pack(pid))
    except RuntimeError as e:
        raise HTTPException(501, str(e)) from e
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="safesphere_evidence_{pid}.pdf"'})


@app.post("/conclusion/{pid}", dependencies=[Depends(require_key)])
def case_conclusion(pid: str):
    """Plain-language conclusion + applicable Acts. Gemini sees only extracted facts, never message text."""
    _person(pid)
    return conclusion.conclude(pid)


# ---------------------------------------------------------------- metrics
@app.get("/metrics")
def metrics():
    if not settings.METRICS_PATH.exists():
        raise HTTPException(404, f"metrics.json not found at {settings.METRICS_PATH}")
    return json.loads(settings.METRICS_PATH.read_text(encoding="utf-8"))


# ---------------------------------------------------------------- demo scenarios (for the Live Feed)
DEMO_FILE = BACKEND_DIR / "demo" / "scenarios.json"


def _scenarios():
    return json.loads(DEMO_FILE.read_text(encoding="utf-8"))


@app.get("/demo/scenarios")
def demo_list():
    return [dict(name=k, title=v["title"], events=len(v["events"])) for k, v in _scenarios().items()]


@app.get("/demo/scenarios/{name}")
def demo_get(name: str):
    """Events with real timestamps (ending now), ready to POST one by one to /ingest/notification."""
    sc = _scenarios().get(name)
    if sc is None:
        raise HTTPException(404, "scenario not found")
    # each event has "t": "<days offset> HH:MM", wall-clock time so night/day patterns are what the script says
    today = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    stamped = []
    for e in sc["events"]:
        day, hm = e["t"].split()
        h, m = (int(x) for x in hm.split(":"))
        stamped.append((today + timedelta(days=int(day), hours=h, minutes=m), e))
    shift = timedelta(days=1) if max(ts for ts, _ in stamped) > utcnow() else timedelta(0)
    out = []
    for ts, e in sorted(stamped, key=lambda x: x[0]):
        ev = {k: v for k, v in e.items() if k != "t"}
        ev["timestamp"] = (ts - shift).isoformat()
        if sc.get("relationship"):
            ev.setdefault("relationship", sc["relationship"])
        out.append(ev)
    return dict(name=name, title=sc["title"], relationship=sc.get("relationship"), events=out)


@app.post("/demo/load/{name}", dependencies=[Depends(require_key)])
def demo_load(name: str):
    events = demo_get(name)["events"]
    return ingest([Notification(**e) for e in events])


# ---------------------------------------------------------------- privacy
@app.delete("/data", dependencies=[Depends(require_key)])
def delete_all():
    store.reset()
    return dict(deleted=True)
