"""Evidence pack: flagged items with SHA-256 fingerprints, pattern summary, legal map, complaint text."""
import hashlib
import io
import json

from .scoring import FLAG_MSG_LABELS, label_texts, person_view, scorer
from .store import store, utcnow

LEGAL = {
    "stalking": ("BNS 78", "Stalking, including repeated contact despite clear disinterest"),
    "sexual": ("BNS 75", "Sexual harassment, including sexually coloured remarks"),
    "insult": ("BNS 79", "Words or gestures intended to insult the modesty of a woman"),
    "threat": ("BNS 351", "Criminal intimidation"),
    "sextortion": ("BNS 308", "Extortion"),
    "intimate_image": ("IT Act 66E / 67 / 67A", "Privacy violation; publishing obscene or sexually explicit material"),
    "impersonation": ("IT Act 66C / 66D", "Identity theft / cheating by personation (fake accounts)"),
    "minor": ("IT Act 67B + POCSO", "Sexual content involving a child"),
}
CHANNELS = [
    dict(id="cybercrime", name="cybercrime.gov.in", detail="Women/Child related crime section, anonymous reporting allowed",
         url="https://cybercrime.gov.in"),
    dict(id="1930", name="1930 helpline", detail="Cyber financial fraud: call right away if money was demanded", url="tel:1930"),
    dict(id="stopncii", name="StopNCII.org", detail="Fingerprints intimate images on your device and blocks re-uploads",
         url="https://stopncii.org"),
    dict(id="ncw", name="NCW / 181", detail="National Commission for Women complaint, women's helpline", url="https://ncwapps.nic.in"),
    dict(id="platform", name="Platform grievance officer",
         detail="IT Rules 2026: remove intimate images within 2 hours, other unlawful content within 3 hours", url=None),
    dict(id="112", name="112", detail="Immediate danger", url="tel:112"),
]


def _sha(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def build_pack(person_id):
    person = store.persons[person_id]
    msgs = [m for m in store.person_messages(person_id) if m.event == "message"]
    texts = [m.text or "" for m in msgs]
    labels = label_texts(texts) if texts else []
    replies = scorer().tm.label_replies([m.text or "" for m in msgs if m.is_user]) if scorer().tm else []
    reply_iter = iter(replies)

    items, cats = [], set()
    for m, lab in zip(msgs, labels):
        rlab = next(reply_iter) if m.is_user else None
        lab = lab if m.text else None     # hidden previews have no readable label
        keep = (not m.is_user and (lab in FLAG_MSG_LABELS or m.media_type)) or (m.is_user and rlab == "reject")
        if not keep:
            continue
        item = dict(time_utc=m.timestamp.isoformat(), app=m.app, account=m.account_id,
                    from_user=m.is_user, text=m.text,
                    category="user_said_no" if m.is_user else (m.media_type and "media") or lab)
        item["sha256"] = _sha(item)
        items.append(item)
        if lab in ("sexual", "insult", "threat", "sextortion"):
            cats.add(lab)
    for mc in store.media.values():
        if mc.person_id == person_id:
            item = dict(time_utc=mc.created_at.isoformat(), category=f"media_{mc.result['verdict']}",
                        filename=mc.filename, file_sha256=mc.sha256, verdict=mc.result["headline"],
                        deepfake_score=mc.result["deepfake"]["deepfake_score"], is_stub=mc.result["is_stub"])
            item["sha256"] = _sha(item)
            items.append(item)
            if mc.result["verdict"] in ("ai_sextortion", "intimate_image_leak", "deepfake_intimate_image"):
                cats.add("intimate_image")
            if mc.result["verdict"] == "ai_sextortion":
                cats.add("sextortion")

    view = person_view(person, detail=True)
    if view["label"] in ("stalking", "harassment_after_no"):
        cats.add("stalking")
    if len(person.account_ids) > 1 and not person.is_group:   # a group's accounts are different members
        cats.add("impersonation")
    if person.minor_involved:
        cats.add("minor")

    generated = utcnow().isoformat()
    pack = dict(
        generated_at_utc=generated, person=dict(id=person.id, name=person.display_name, accounts=view["accounts"]),
        assessment=dict(level=view["level"], label=view["label"], risk=view["risk"], reasons=view["reasons"],
                        consent_timeline=view["consent_timeline"]),
        items=items,
        legal=[dict(section=LEGAL[c][0], description=LEGAL[c][1]) for c in sorted(cats) if c in LEGAL],
        channels=_channels(cats),
        complaint_text=_complaint(person, view, items),
        disclaimer="Automated analysis to support a complaint. Not legal advice; sections are suggestions to verify.",
    )
    pack["pack_sha256"] = _sha(dict(person=person.id, generated=generated, items=[i["sha256"] for i in items]))
    return pack


def _channels(cats):
    order = ["cybercrime", "platform", "ncw", "112"]
    if "sextortion" in cats:
        order = ["1930", "stopncii", "cybercrime", "platform", "112"]
    elif "intimate_image" in cats:
        order = ["stopncii", "cybercrime", "platform", "ncw", "112"]
    by_id = {c["id"]: c for c in CHANNELS}
    return [by_id[i] for i in order]


def _complaint(person, view, items):
    handles = ", ".join(f"{a['handle']} ({a['app']})" for a in view["accounts"])
    reasons = "\n".join(f"- {r}" for r in view["reasons"]) or "- See attached items"
    first = items[0]["time_utc"][:10] if items else "unknown date"
    return (f"To: Grievance Officer / Cyber Cell\n\n"
            f"I am being harassed by {person.display_name}, using the account(s): {handles}, since {first}.\n\n"
            f"Pattern observed:\n{reasons}\n\n"
            f"The attached evidence pack contains {len(items)} items, each with a SHA-256 fingerprint so that "
            f"any alteration can be detected. Under the IT Rules 2026, non-consensual intimate imagery must be "
            f"removed within 2 hours and other unlawful content within 3 hours of a complaint. I request "
            f"immediate removal of this content, preservation of the account data, and appropriate action.\n")


def pack_pdf(pack):
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table
    except ImportError as e:
        raise RuntimeError("PDF export needs reportlab: pip install reportlab") from e

    def esc(s):
        return (str(s) if s is not None else "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    buf = io.BytesIO()
    st = getSampleStyleSheet()
    small = st["BodyText"].clone("small", fontSize=7, leading=9)
    a = pack["assessment"]
    story = [Paragraph("SafeSphere evidence pack", st["Title"]),
             Paragraph(f"Person: {esc(pack['person']['name'])} · Level: {esc(a['level'])} · "
                       f"Pattern: {esc(a['label'])} · Risk: {esc(a['risk'])}", st["Normal"]),
             Paragraph(f"Generated (UTC): {esc(pack['generated_at_utc'])}", st["Normal"]),
             Paragraph(f"Pack fingerprint (SHA-256): {esc(pack['pack_sha256'])}", small), Spacer(1, 8),
             Paragraph("Why this was flagged", st["Heading3"])]
    story += [Paragraph(f"• {esc(r)}", st["Normal"]) for r in a["reasons"]]
    story += [Spacer(1, 8), Paragraph("Evidence items", st["Heading3"])]
    rows = [["Time (UTC)", "Account", "Content", "Category", "SHA-256"]]
    for i in pack["items"]:
        rows.append([Paragraph(esc(i["time_utc"][:16]), small), Paragraph(esc(i.get("account", i.get("filename", ""))), small),
                     Paragraph(esc(i.get("text") or i.get("verdict") or ""), small), Paragraph(esc(i["category"]), small),
                     Paragraph(esc(i["sha256"][:16] + "…"), small)])
    story.append(Table(rows, colWidths=[70, 90, 200, 70, 80], repeatRows=1))
    story += [Spacer(1, 8), Paragraph("Possible legal provisions (verify with a lawyer)", st["Heading3"])]
    story += [Paragraph(f"• {esc(l['section'])}: {esc(l['description'])}", st["Normal"]) for l in pack["legal"]]
    story += [Spacer(1, 8), Paragraph("Complaint", st["Heading3"]),
              Paragraph(esc(pack["complaint_text"]).replace("\n", "<br/>"), st["Normal"]), Spacer(1, 8),
              Paragraph(esc(pack["disclaimer"]), small)]
    SimpleDocTemplate(buf, pagesize=A4, title="SafeSphere evidence pack").build(story)
    return buf.getvalue()
