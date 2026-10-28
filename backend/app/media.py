"""Combine the deepfake connector's scores with message context into one verdict (FINAL_IDEA §4.3)."""
from .scoring import label_texts

EXPLICIT_T, FACE_T, FAKE_T = 0.7, 0.7, 0.5
THREAT_LABELS = {"sextortion", "threat"}

ACTIONS = {
    "ai_sextortion": ["Don't pay, don't delete, don't reply.", "Hash the image on StopNCII.org to block re-uploads.",
                      "Call 1930 and report on cybercrime.gov.in.", "Generate the evidence pack."],
    "intimate_image_leak": ["Don't delete the messages.", "Hash the image on StopNCII.org.",
                            "Report on cybercrime.gov.in (Women/Child section).", "Generate the evidence pack."],
    "deepfake_intimate_image": ["Hash the image on StopNCII.org.", "Report to the platform: IT Rules 2026 require removal within 2 hours.",
                                "Generate the evidence pack."],
    "cyber_flashing": ["Block and report the sender on the platform.", "Generate the evidence pack if it continues."],
    "voice_clone_threat": ["Verify by calling the real person back on a known number.", "Don't send money.",
                           "Call 1930 if money was demanded."],
    "voice_clone": ["Verify by calling the real person back on a known number."],
    "deepfake_humiliation": ["Report to the platform for removal.", "Generate the evidence pack."],
    "likely_manipulated": ["Treat this media with caution; it shows signs of manipulation."],
    "no_issue_found": [],
}
HEADLINES = {
    "ai_sextortion": "Likely AI sextortion: a manipulated intimate image of you, sent with a threat or demand",
    "intimate_image_leak": "An intimate image that matches your face",
    "deepfake_intimate_image": "A likely manipulated intimate image that matches your face",
    "cyber_flashing": "Unsolicited explicit media",
    "voice_clone_threat": "Likely cloned voice, used with a threat or money demand",
    "voice_clone": "Likely cloned or synthetic voice",
    "deepfake_humiliation": "A likely manipulated image or video of you",
    "likely_manipulated": "This media shows signs of manipulation",
    "no_issue_found": "No issue found",
}
LEVEL = {"ai_sextortion": "critical", "intimate_image_leak": "critical", "deepfake_intimate_image": "critical",
         "voice_clone_threat": "critical", "cyber_flashing": "high", "voice_clone": "high",
         "deepfake_humiliation": "high", "likely_manipulated": "warn", "no_issue_found": "info"}


def verdict(df_result, context_text=None):
    texts = [t for t in [context_text, df_result.get("transcript")] if t]
    ctx_labels = [label for label in label_texts(texts) if label]
    threat = any(lab in THREAT_LABELS for lab in ctx_labels)
    fake = df_result["deepfake_score"] >= FAKE_T
    nsfw = df_result.get("nsfw_score")
    face = df_result.get("face_match")
    explicit = nsfw is not None and nsfw >= EXPLICIT_T
    is_user = face is not None and face >= FACE_T

    if df_result["kind"] == "audio":
        key = ("voice_clone_threat" if threat else "voice_clone") if fake else "no_issue_found"
    elif explicit and is_user:
        key = ("ai_sextortion" if threat else "deepfake_intimate_image") if fake else "intimate_image_leak"
    elif explicit:
        key = "cyber_flashing"
    elif fake and is_user:
        key = "deepfake_humiliation"
    elif fake:
        key = "likely_manipulated"
    else:
        key = "no_issue_found"

    steps = [
        dict(step="nudity_check", value=nsfw, flagged=explicit),
        dict(step="face_match", value=face, flagged=is_user),
        dict(step="deepfake_model", value=df_result["deepfake_score"], flagged=fake,
             wording=f"Likely manipulated ({df_result['deepfake_score']:.0%})" if fake
             else f"No strong sign of manipulation ({df_result['deepfake_score']:.0%})"),
        dict(step="context", value=ctx_labels, flagged=threat),
    ]
    return dict(verdict=key, level=LEVEL[key], headline=HEADLINES[key], actions=ACTIONS[key], steps=steps,
                is_stub=df_result.get("is_stub", False))
