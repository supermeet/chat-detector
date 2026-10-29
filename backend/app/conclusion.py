"""Plain-language conclusion of a case: what the pattern is, which Acts/sections apply, what to do next.

Written by Gemini when GEMINI_API_KEY is set, otherwise by fixed rules. Privacy contract:
Gemini receives ONLY the model's extracted facts (level, behaviour type, counts, ratios, template reasons,
evidence categories). No message text, names, handles or media ever leave the backend. Gemini may only cite
sections from LEGAL_OPTIONS; anything else it returns is dropped.
"""
import hashlib
import json
import urllib.error
import urllib.request

from .config import settings
from .report import LEGAL, build_pack
from .scoring import person_view
from .store import store

LEGAL_OPTIONS = {v[0]: v[1] for v in LEGAL.values()}
_cache = {}

FACT_KEYS = ["msgs_per_day", "span_days", "reply_ratio", "unanswered_streak_max", "night_ratio", "rejected_flag",
             "msgs_after_reject", "sexual_after_reject", "insult_after_reject", "surveillance_count", "threat_count",
             "sextortion_count", "media_count", "accounts_count", "platforms_count", "new_account_after_block",
             "block_count", "text_available_ratio", "minor_involved"]


def case_facts(pid):
    """Everything the conclusion may use. Deliberately text-free."""
    person = store.persons[pid]
    v = person_view(person, detail=True)
    pack = build_pack(pid)
    cats = {}
    for it in pack["items"]:
        cats[it["category"]] = cats.get(it["category"], 0) + 1
    facts = {k: v["facts"].get(k) for k in FACT_KEYS if v["facts"].get(k) is not None}
    return dict(
        level=v["level"], behaviour_type=v["label"], risk=v["risk"], early=v.get("early", False),
        relationship=v["relationship"], marked_safe_by_user=v["trusted"], is_group=v["is_group"],
        reasons=v["reasons"] or v.get("minor_signals", []), reasons_down=v.get("reasons_down", []),
        consent_phases=[p["phase"] for p in v["consent_timeline"]],
        evidence_categories=cats, facts=facts,
        rule_based_sections=[l["section"] for l in pack["legal"]],
    ), pack


def _rules(facts, pack):
    lt = facts["behaviour_type"]
    lines = {
        "sextortion": "This looks like sextortion: threats or demands linked to images of you.",
        "stalking": "This looks like stalking: repeated, one-sided contact that tracks where you are or who you're with.",
        "harassment_after_no": "This person kept contacting you after you clearly said no.",
        "group_bullying": "You are being targeted with insults in a group.",
    }
    level = facts["level"]
    if level in ("info", "warn"):
        summary = ("Nothing here needs action right now." if level == "info"
                   else "There are early warning signs, but not enough history to call it a pattern yet.")
    else:
        summary = lines.get(lt, "This contact shows a harmful pattern.")
    if facts["reasons"]:
        summary += " Main signals: " + "; ".join(r[0].lower() + r[1:] for r in facts["reasons"][:3]) + "."
    steps = [c["name"] + ": " + c["detail"] for c in pack["channels"][:3]] if level in ("high", "critical") else \
        ["Keep the messages; don't delete them.", "Mark the person as not harassment if this is someone you trust."]
    return dict(source="rules", model=None, summary=summary,
                acts=[dict(section=l["section"], why=l["description"]) for l in pack["legal"]],
                next_steps=steps, caution="Automated analysis, not legal advice.")


PROMPT = """You are a legal-aid assistant for SafeSphere, an Indian anti-harassment app. Write the conclusion of a case
for the victim, from the behaviour model's findings below. You do NOT see the messages.

Rules:
- Speak to the user ("you"), calm and supportive, plain English, no blame.
- "summary": 3-5 sentences. Say what pattern the findings show and how strong the signals are. "risk" is a model
  probability, not proof: never say "certain", "absolute" or "confirmed". If level is info or warn,
  or "early" is true, say clearly that it is not (yet) enough to act on, and do not overstate.
- "acts": only entries from ALLOWED_SECTIONS that fit these facts (can be empty). Copy the "section" code exactly
  (for example "BNS 78"), never the description. For each, one sentence "why" tied to the facts.
- "next_steps": 3-5 short, concrete steps in priority order (Indian channels: cybercrime.gov.in, 1930, 112, NCW/181,
  StopNCII, platform grievance officer, school/college/workplace committee) suited to the level and type.
- "caution": one sentence that this is automated analysis and not legal advice.
Return JSON only: {"summary": str, "acts": [{"section": str, "why": str}], "next_steps": [str], "caution": str}

ALLOWED_SECTIONS:
%s

CASE FACTS:
%s
"""


def _call(model, body):
    """stdlib urllib on purpose: it uses the OS certificate store, so it also works behind HTTPS-inspecting networks."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), method="POST",
                                 headers={"x-goog-api-key": settings.GEMINI_API_KEY, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=settings.GEMINI_TIMEOUT) as r:
            data = json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Gemini {model} error {e.code}: {e.read().decode('utf-8', 'replace')[:200]}") from e
    return data["candidates"][0]["content"]["parts"][0]["text"]


def _gemini(facts):
    gen = dict(temperature=0.2, responseMimeType="application/json")
    if settings.GEMINI_THINKING_LEVEL:
        gen["thinkingConfig"] = dict(thinkingLevel=settings.GEMINI_THINKING_LEVEL)
    allowed = [dict(section=k, covers=v) for k, v in LEGAL_OPTIONS.items()]
    body = dict(contents=[dict(role="user", parts=[dict(text=PROMPT % (
        json.dumps(allowed, indent=1, ensure_ascii=False), json.dumps(facts, indent=1, ensure_ascii=False)))])],
        generationConfig=gen)
    model = settings.GEMINI_MODEL
    try:
        text = _call(model, body)
    except (RuntimeError, OSError):
        if not settings.GEMINI_FALLBACK_MODEL:
            raise
        model = settings.GEMINI_FALLBACK_MODEL     # busy/retired model: try the lighter one once
        body["generationConfig"].pop("thinkingConfig", None)
        text = _call(model, body)
    out = json.loads(text)
    by_desc = {v.lower(): k for k, v in LEGAL_OPTIONS.items()}
    acts = []
    for a in out.get("acts", []):
        if not isinstance(a, dict):
            continue
        sec = str(a.get("section", "")).strip()
        sec = sec if sec in LEGAL_OPTIONS else by_desc.get(sec.lower())   # tolerate the description instead of the code
        if sec:   # anything not on the vetted list is dropped
            acts.append(dict(section=sec, why=str(a.get("why", "")).strip()))
    return dict(source="gemini", model=model, summary=str(out.get("summary", "")).strip(), acts=acts,
                next_steps=[str(s) for s in out.get("next_steps", [])][:5],
                caution=str(out.get("caution", "Automated analysis, not legal advice.")))


def suggest_variants(term):
    """Spelling / code-word variants of ONE slang term. Gemini receives only the term."""
    prompt = ("List up to 6 spellings, leetspeak or code-word variants that people in India use online to dodge "
              "filters for this Hinglish/English slang term. Return a JSON array of strings only.\nTERM: %s"
              % json.dumps(term, ensure_ascii=False))
    body = dict(contents=[dict(role="user", parts=[dict(text=prompt)])],
                generationConfig=dict(temperature=0.3, responseMimeType="application/json"))
    out = json.loads(_call(settings.GEMINI_FALLBACK_MODEL or settings.GEMINI_MODEL, body))
    return [str(v).strip() for v in out if isinstance(v, (str, int)) and str(v).strip()][:6]


def conclude(pid):
    facts, pack = case_facts(pid)
    fingerprint = hashlib.sha256(json.dumps(facts, sort_keys=True, default=str).encode()).hexdigest()
    if _cache.get(pid, {}).get("fp") == fingerprint:
        return _cache[pid]["out"]
    out, error = None, None
    if settings.GEMINI_API_KEY:
        try:
            out = _gemini(facts)
            if not out["summary"]:
                raise RuntimeError("Gemini returned an empty summary")
        except Exception as e:  # network, quota, bad JSON: fall back, never fail the user
            error = str(e)[:300]
    if out is None:
        out = _rules(facts, pack)
    out.update(level=facts["level"], behaviour_type=facts["behaviour_type"], shared_with_ai="facts only, no message text",
               fallback_reason=error)
    _cache[pid] = dict(fp=fingerprint, out=out)
    return out


def status():
    return dict(mode="gemini" if settings.GEMINI_API_KEY else "rules", model=settings.GEMINI_MODEL if settings.GEMINI_API_KEY else None)
