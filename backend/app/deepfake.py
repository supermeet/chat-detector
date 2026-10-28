"""Connector to the team's deepfake / nudity / face-match models.

Pick one with DEEPFAKE_MODE in backend/.env:

  stub    Placeholder results, clearly marked is_stub=true. Default until the real models are connected.
  http    The models run as a service. We POST multipart `file` (+ `context_text`) to {DEEPFAKE_URL}/{kind}
          with header "Authorization: Bearer {DEEPFAKE_API_KEY}". kind = image | video | audio.
  python  The models are importable here. DEEPFAKE_PYTHON="package.module:function", called as
          function(kind: str, data: bytes, filename: str) -> dict

Whatever the service returns is normalised by `normalise()`. Accepted field names (all optional
except a deepfake score):
  deepfake_score | fake_score | score | probability   (0..1, probability the media is manipulated)
  label                                               ("fake"/"real"/"manipulated"/...)
  nsfw_score | nudity_score | explicit_score          (0..1)
  face_match | face_match_score                       (0..1, similarity to the user's enrolled face)
  heatmap | heatmap_url                               (base64 PNG or URL)
  frames                                              (video: list of {"t": seconds, "score": 0..1})
  transcript                                          (audio: speech-to-text, scored by our text model)
"""
import importlib

import requests

from .config import settings


class DeepfakeError(RuntimeError):
    pass


def _first(d, *keys):
    for k in keys:
        if d.get(k) is not None:
            return d[k]
    return None


def normalise(raw, kind):
    if not isinstance(raw, dict):
        raise DeepfakeError(f"deepfake service returned {type(raw).__name__}, expected a JSON object")
    score = _first(raw, "deepfake_score", "fake_score", "score", "probability")
    if score is None:
        raise DeepfakeError(f"deepfake service response has no score field: {sorted(raw)}")
    score = float(score)
    if score > 1:                       # some models return percentages
        score /= 100.0
    return dict(
        kind=kind,
        deepfake_score=round(score, 4),
        label=raw.get("label") or ("likely_manipulated" if score >= 0.5 else "likely_authentic"),
        nsfw_score=_maybe_float(_first(raw, "nsfw_score", "nudity_score", "explicit_score")),
        face_match=_maybe_float(_first(raw, "face_match", "face_match_score")),
        heatmap=_first(raw, "heatmap", "heatmap_url"),
        frames=raw.get("frames"),
        transcript=raw.get("transcript"),
        model=raw.get("model") or raw.get("model_name"),
        is_stub=bool(raw.get("is_stub", False)),
    )


def _maybe_float(v):
    if v is None:
        return None
    v = float(v)
    return round(v / 100.0 if v > 1 else v, 4)


def _stub(kind, data, filename):
    # fixed placeholder values so the demo flow is repeatable; always marked is_stub
    if kind == "audio":
        return dict(deepfake_score=0.84, model="stub", is_stub=True, transcript=None)
    return dict(deepfake_score=0.88, nsfw_score=0.93, face_match=0.81, model="stub", is_stub=True)


def _http(kind, data, filename, context_text):
    if not settings.DEEPFAKE_URL:
        raise DeepfakeError("DEEPFAKE_MODE=http but DEEPFAKE_URL is not set")
    headers = {"Authorization": f"Bearer {settings.DEEPFAKE_API_KEY}"} if settings.DEEPFAKE_API_KEY else {}
    try:
        r = requests.post(f"{settings.DEEPFAKE_URL.rstrip('/')}/{kind}", headers=headers,
                          files={"file": (filename, data)}, data={"context_text": context_text or ""},
                          timeout=settings.DEEPFAKE_TIMEOUT)
    except requests.RequestException as e:
        raise DeepfakeError(f"could not reach deepfake service: {e}") from e
    if r.status_code >= 400:
        raise DeepfakeError(f"deepfake service error {r.status_code}: {r.text[:300]}")
    return r.json()


_py_fn = None


def _python(kind, data, filename):
    global _py_fn
    if _py_fn is None:
        if ":" not in settings.DEEPFAKE_PYTHON:
            raise DeepfakeError('DEEPFAKE_PYTHON must look like "package.module:function"')
        mod, fn = settings.DEEPFAKE_PYTHON.split(":", 1)
        _py_fn = getattr(importlib.import_module(mod), fn)
    return _py_fn(kind, data, filename)


def analyse(kind, data, filename, context_text=None):
    mode = settings.DEEPFAKE_MODE
    if mode == "http":
        raw = _http(kind, data, filename, context_text)
    elif mode == "python":
        raw = _python(kind, data, filename)
    else:
        raw = _stub(kind, data, filename)
    return normalise(raw, kind)


def status():
    return dict(mode=settings.DEEPFAKE_MODE, url=settings.DEEPFAKE_URL or None,
                key_configured=bool(settings.DEEPFAKE_API_KEY), python=settings.DEEPFAKE_PYTHON or None,
                connected=settings.DEEPFAKE_MODE != "stub")
