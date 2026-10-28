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


class Feedback(BaseModel):
    person_id: str
    kind: Literal["not_harassment", "missed_harassment"]
    note: Optional[str] = None
