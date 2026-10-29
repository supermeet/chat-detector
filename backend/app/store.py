"""In-memory store. Privacy by default: nothing is written to disk, and DELETE /data wipes everything.

Accounts are (app, handle) pairs. Each account belongs to exactly one person; a person can own
several accounts once the user confirms a link.
"""
import itertools
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


@dataclass
class Message:
    id: int
    account_id: str
    app: str
    timestamp: datetime
    is_user: bool
    text: Optional[str]
    event: str = "message"            # "message" | "block"
    media_type: Optional[str] = None  # "image" | "video" | "audio"
    chat: Optional[str] = None
    is_group: bool = False
    source: str = "notification"      # "notification" | "import"


@dataclass
class Account:
    id: str
    app: str
    handle: str
    display_name: str
    person_id: str
    first_seen: datetime
    last_seen: datetime


@dataclass
class Person:
    id: str
    display_name: str
    account_ids: list
    relationship: str = "stranger"
    relationship_age_days: float = 0.0
    trusted: bool = False
    minor_involved: bool = False
    is_group: bool = False
    is_room: bool = False             # a live chatroom: all members' messages aimed at the user, scored together
    result: Optional[dict] = None     # last score from the behaviour model
    rejected_links: set = field(default_factory=set)


@dataclass
class Alert:
    id: int
    person_id: str
    level: str
    label: str
    summary: str
    reasons: list
    created_at: datetime
    dismissed: bool = False


@dataclass
class MediaCheck:
    id: int
    kind: str
    filename: str
    sha256: str
    size_bytes: int
    person_id: Optional[str]
    context_text: Optional[str]
    result: dict
    created_at: datetime


class Store:
    def __init__(self):
        self.lock = threading.RLock()
        self.reset()

    def reset(self):
        with getattr(self, "lock", threading.RLock()):
            self.messages: dict[int, Message] = {}
            self.accounts: dict[str, Account] = {}
            self.persons: dict[str, Person] = {}
            self.alerts: dict[int, Alert] = {}
            self.media: dict[int, MediaCheck] = {}
            self.feedback: list[dict] = []
            self.rooms: dict[str, str] = {}   # room name -> room person id
            self._msg_ids = itertools.count(1)
            self._alert_ids = itertools.count(1)
            self._media_ids = itertools.count(1)
            self._person_ids = itertools.count(1)

    # --- accounts / persons -------------------------------------------------------------
    def get_or_create_account(self, app, handle, display_name=None, ts=None):
        acc_id = f"{app}:{handle}".lower()
        ts = ts or utcnow()
        acc = self.accounts.get(acc_id)
        if acc is None:
            pid = f"p{next(self._person_ids)}"
            acc = Account(acc_id, app, handle, display_name or handle, pid, ts, ts)
            self.accounts[acc_id] = acc
            self.persons[pid] = Person(pid, display_name or handle, [acc_id])
        else:
            acc.first_seen = min(acc.first_seen, ts)
            acc.last_seen = max(acc.last_seen, ts)
        return acc

    def person_messages(self, person_id):
        accs = set(self.persons[person_id].account_ids)
        return sorted((m for m in self.messages.values() if m.account_id in accs), key=lambda m: m.timestamp)

    def link(self, person_id, account_id):
        """Move an account (and its old person's other accounts) into person_id."""
        target = self.persons[person_id]
        acc = self.accounts[account_id]
        old_pid = acc.person_id
        if old_pid == person_id:
            return target
        old = self.persons[old_pid]
        for aid in old.account_ids:
            self.accounts[aid].person_id = person_id
            if aid not in target.account_ids:
                target.account_ids.append(aid)
        target.is_group = target.is_group or old.is_group
        target.minor_involved = target.minor_involved or old.minor_involved
        for a in self.alerts.values():
            if a.person_id == old_pid:
                a.person_id = person_id
        del self.persons[old_pid]
        return target

    def unlink(self, person_id, account_id):
        """Split an account out into its own new person."""
        p = self.persons[person_id]
        if account_id not in p.account_ids or len(p.account_ids) == 1:
            return p, None
        p.account_ids.remove(account_id)
        acc = self.accounts[account_id]
        pid = f"p{next(self._person_ids)}"
        acc.person_id = pid
        newp = Person(pid, acc.display_name, [account_id], is_group=p.is_group)
        newp.rejected_links.add(person_id)
        p.rejected_links.add(pid)
        self.persons[pid] = newp
        return p, newp


store = Store()
