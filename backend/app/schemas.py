"""Request bodies. Responses are plain JSON documented in docs/API_CONTRACT.md."""
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

App = Literal["wa", "ig", "tg", "sms", "snap", "fb", "web"]
Relationship = Literal["stranger", "acquaintance", "friend", "partner", "family"]


class Notification(BaseModel):
    app: App = Field(..., description="Source app code")
    sender: str = Field(..., description="Display name shown in the notification")
    sender_handle: Optional[str] = Field(None, description="Handle/number if known; defaults to sender")
    text: Optional[str] = Field(None, description="Message text; null when the preview is hidden")
    timestamp: Optional[datetime] = Field(None, description="ISO time; defaults to now (UTC)")
    is_user: bool = Field(False, description="True for the user's own reply")
    event: Literal["message", "block"] = "message"
    media_type: Optional[Literal["image", "video", "audio"]] = None
    chat: Optional[str] = Field(None, description="Group name for group chats")
    is_group: bool = False
    room: Optional[str] = Field(
        None, description="Live chatroom name: the message is also scored as part of the room's group person")
    relationship: Optional[Relationship] = Field(
        None, description="If known (e.g. sender is a saved contact): sets the person's relationship once")


class PersonPatch(BaseModel):
    display_name: Optional[str] = None
    relationship: Optional[Relationship] = None
    relationship_age_days: Optional[float] = None
    trusted: Optional[bool] = None
    minor_involved: Optional[bool] = None


class LinkRequest(BaseModel):
    account_id: Optional[str] = None
    other_person_id: Optional[str] = None


class UnlinkRequest(BaseModel):
    account_id: str


class MediaPatch(BaseModel):
    person_id: str


LexCategory = Literal["Refusal signal", "Bullying", "Sextortion", "Extortion", "Stalking", "Threat",
                      "Sexual harassment", "Self-harm incitement"]
Severity = Literal["info", "warn", "high", "critical"]


class LexTerm(BaseModel):
    term: str = Field(..., min_length=1, max_length=60)
    cat: LexCategory
    sev: Severity = "warn"
    variants: list[str] = []


class LexPending(BaseModel):
    term: str = Field(..., min_length=1, max_length=60)
    cat: LexCategory = "Bullying"
    sev: Severity = "warn"
    src: Literal["User", "AI", "Auto"] = "User"
    note: str = ""


class LexEdits(BaseModel):
    term: Optional[str] = None
    cat: Optional[LexCategory] = None
    sev: Optional[Severity] = None
    variants: list[str] = []


class LexText(BaseModel):
    text: str = Field(..., max_length=2000)


class LexSuggest(BaseModel):
    term: str = Field(..., min_length=1, max_length=60)


class Feedback(BaseModel):
    person_id: str
    kind: Literal["not_harassment", "missed_harassment"]
    note: Optional[str] = None
