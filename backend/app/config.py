"""Settings, read from environment variables or backend/.env (see .env.example)."""
import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BACKEND_DIR.parent


def _load_dotenv(path):
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_dotenv(BACKEND_DIR / ".env")


def _get(name, default=""):
    return os.environ.get(name, default)


class Settings:
    # behaviour model (trained in ml/behavior) and its code
    ML_DIR = Path(_get("SAFESPHERE_ML_DIR", str(ROOT_DIR / "ml" / "behavior")))
    MODEL_DIR = Path(_get("SAFESPHERE_MODEL_DIR", str(BACKEND_DIR / "models")))
    METRICS_PATH = Path(_get("SAFESPHERE_METRICS_PATH", str(BACKEND_DIR / "models" / "metrics.json")))

    # API key the UI must send as X-API-Key (empty = no auth, for local dev only)
    API_KEY = _get("SAFESPHERE_API_KEY")
    ALLOWED_ORIGINS = [o.strip() for o in _get("SAFESPHERE_ALLOWED_ORIGINS", "*").split(",") if o.strip()]

    # deepfake connector: "stub" | "http" | "python"
    DEEPFAKE_MODE = _get("DEEPFAKE_MODE", "stub")
    DEEPFAKE_URL = _get("DEEPFAKE_URL")                 # http mode: base URL, we POST to {URL}/{kind}
    DEEPFAKE_API_KEY = _get("DEEPFAKE_API_KEY")         # http mode: sent as "Authorization: Bearer <key>"
    DEEPFAKE_PYTHON = _get("DEEPFAKE_PYTHON")           # python mode: "package.module:function"
    DEEPFAKE_TIMEOUT = float(_get("DEEPFAKE_TIMEOUT", "60"))

    MAX_UPLOAD_MB = float(_get("SAFESPHERE_MAX_UPLOAD_MB", "50"))

    # case conclusion (summary + applicable Acts) by Gemini; empty key = rule-based conclusion
    GEMINI_API_KEY = _get("GEMINI_API_KEY")
    GEMINI_MODEL = _get("GEMINI_MODEL", "gemini-3.5-flash")
    GEMINI_FALLBACK_MODEL = _get("GEMINI_FALLBACK_MODEL", "gemini-flash-lite-latest")   # on 404/429/5xx/timeout
    GEMINI_THINKING_LEVEL = _get("GEMINI_THINKING_LEVEL", "low")   # a short structured summary needs little thinking
    GEMINI_TIMEOUT = float(_get("GEMINI_TIMEOUT", "20"))   # per model; then the fallback model, then rules

    # the built UI (frontend/build.py) served at "/"
    FRONTEND_PATH = Path(_get("SAFESPHERE_FRONTEND", str(ROOT_DIR / "frontend" / "index.html")))


settings = Settings()
