"""Parse chat exports into a common list of messages.

Each parser returns (participants, messages); messages are dicts:
    {"sender": str, "timestamp": datetime, "text": str | None, "media_type": str | None}
"""
import json
import re
from datetime import datetime

MEDIA_MARKERS = {
    "<media omitted>": "image", "image omitted": "image", "video omitted": "video",
    "audio omitted": "audio", "sticker omitted": "image", "gif omitted": "video",
}
MEDIA_TEXT = {"image": "📷 Photo", "video": "🎥 Video", "audio": "🎤 Voice message"}
DELETED = {"this message was deleted", "you deleted this message"}

# Android: "12/10/24, 9:41 pm - Rahul: hi"   iOS: "[12/10/24, 9:41:05 PM] Rahul: hi"
WA_LINE = re.compile(
    r"^\[?(?P<date>\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}),?\s+(?P<time>\d{1,2}:\d{2}(?::\d{2})?)\s*"
    r"(?P<ampm>[apAP]\.?\s?[mM]\.?)?\]?\s*(?:-|–)?\s*(?P<rest>.*)$")


def _parse_wa_datetime(date, time, ampm, dayfirst=True):
    sep = re.findall(r"[/.-]", date)[0]
    a, b, y = date.split(sep)
    d, mth = (a, b) if dayfirst else (b, a)
    y = int(y) + (2000 if len(y) == 2 else 0)
    parts = [int(x) for x in time.split(":")]
    h, mi, s = parts[0], parts[1], parts[2] if len(parts) > 2 else 0
    if ampm:
        pm = ampm.lower().startswith("p")
        h = (h % 12) + (12 if pm else 0)
    return datetime(y, int(mth), int(d), h, mi, s)


def _guess_dayfirst(lines):
    for line in lines:
        m = WA_LINE.match(line)
        if m:
            a, b = re.split(r"[/.-]", m.group("date"))[:2]
            if int(a) > 12:
                return True
            if int(b) > 12:
                return False
    return True   # Indian exports are day-first


def parse_whatsapp(text):
    lines = text.replace("‎", "").replace(" ", " ").splitlines()
    dayfirst = _guess_dayfirst(lines)
    msgs = []
    for line in lines:
        m = WA_LINE.match(line)
        if m and ": " in m.group("rest"):
            sender, body = m.group("rest").split(": ", 1)
            try:
                ts = _parse_wa_datetime(m.group("date"), m.group("time"), m.group("ampm"), dayfirst)
            except ValueError:
                continue
            msgs.append(dict(sender=sender.strip(), timestamp=ts, text=body.strip(), media_type=None))
        elif m:
            continue                      # system line ("Messages are end-to-end encrypted", "X added Y")
        elif msgs and line.strip():
            msgs[-1]["text"] += "\n" + line.strip()   # continuation of a multi-line message
    for msg in msgs:
        low = (msg["text"] or "").strip().lower()
        for marker, kind in MEDIA_MARKERS.items():
            if marker in low:
                msg["media_type"], msg["text"] = kind, MEDIA_TEXT[kind]
        if low in DELETED:
            msg["text"] = None
    participants = sorted({m["sender"] for m in msgs})
    return participants, msgs


def _fix_mojibake(s):
    try:
        return s.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s


def parse_instagram(raw):
    data = json.loads(raw)
    participants = [_fix_mojibake(p["name"]) for p in data.get("participants", [])]
    msgs = []
    for m in data.get("messages", []):
        media = "image" if m.get("photos") else "video" if m.get("videos") else "audio" if m.get("audio_files") else None
        text = _fix_mojibake(m["content"]) if m.get("content") else (MEDIA_TEXT[media] if media else None)
        msgs.append(dict(sender=_fix_mojibake(m.get("sender_name", "unknown")),
                         timestamp=datetime.fromtimestamp(m["timestamp_ms"] / 1000),
                         text=text, media_type=media))
    msgs.sort(key=lambda x: x["timestamp"])
    return participants or sorted({m["sender"] for m in msgs}), msgs


def parse_telegram(raw):
    data = json.loads(raw)
    msgs = []
    for m in data.get("messages", []):
        if m.get("type") != "message":
            continue
        t = m.get("text", "")
        if isinstance(t, list):
            t = "".join(p if isinstance(p, str) else p.get("text", "") for p in t)
        media = "image" if m.get("photo") else {"video_file": "video", "voice_message": "audio",
                                                 "audio_file": "audio"}.get(m.get("media_type"))
        msgs.append(dict(sender=m.get("from") or "unknown", timestamp=datetime.fromisoformat(m["date"]),
                         text=t or (MEDIA_TEXT[media] if media else None), media_type=media))
    return sorted({m["sender"] for m in msgs}), msgs


PARSERS = {"whatsapp": parse_whatsapp, "instagram": parse_instagram, "telegram": parse_telegram}
APP_CODE = {"whatsapp": "wa", "instagram": "ig", "telegram": "tg"}


def parse(source, raw_bytes):
    text = raw_bytes.decode("utf-8-sig", errors="replace")
    return PARSERS[source](text)
