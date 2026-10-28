"""Keeps the slang list current on its own: behaviour teaches vocabulary.

The behaviour model flags harassment from patterns even when no known bad word is used. Words that then keep
appearing in those flagged chats, from several different senders, and never in chats the model or the user
considers safe, are proposed for the slang list (src "Auto"). A person still approves each one: an automatic
learner could otherwise be gamed into flagging innocent words.

Only the single word and its counts are kept, never the messages it came from.
"""
from collections import defaultdict

from .lexicon import lex, skeleton
from .scoring import LEVELS, label_texts
from .store import store

MIN_SENDERS = 2
MIN_LEN = 4
LABEL_CATEGORY = {"insult": "Bullying", "sexual": "Sexual harassment", "threat": "Threat",
                  "sextortion": "Sextortion", "surveillance": "Stalking"}
# everyday English / Hinglish words that show up in any chat
STOP = set("""
that this with have what your youre they them their there then than been were here will dont cant also only just
like very when from about know want really yeah sure thanks sorry good morning night today tomorrow time everyone
nobody always never even still much more some something someone abhi kaha kahan kahin haan acha acha theek please
reply hello okay bahut bohot sabko sabse karo raha rahi hain wala wali phir kabhi sach kisi kitni kitna apni apna
apne hota hoti lagti lagta dekh dekho bolo bata batao chal chalo nahi kyun kuch mein mera meri tera teri tujhe mujhe
yaar bhai aaja kya kyu
""".split())


def _sender_key(m):
    acc = store.accounts.get(m.account_id)
    return (m.app, acc.handle.split("/")[-1] if acc else m.account_id)   # room copies count as the same sender


def _words(persons):
    """word skeleton -> {senders}, plus word -> texts it appeared in (for the category guess)."""
    senders, texts = defaultdict(set), defaultdict(list)
    for p in persons:
        for m in store.person_messages(p.id):
            if m.is_user or not m.text or m.event != "message":
                continue
            _, tokens, _ = lex.analyse(m.text)
            for t in tokens:
                w = skeleton(t["w"])
                if t["hit"] or len(w) < MIN_LEN or w.isdigit() or w in STOP:
                    continue
                senders[w].add(_sender_key(m))
                texts[w].append(m.text)
    return senders, texts


def run():
    """Propose new words; returns the pending entries it added."""
    flagged, safe = [], []
    for p in store.persons.values():
        level = (p.result or {}).get("level")
        if p.trusted or level == "info":
            safe.append(p)
        elif level and LEVELS.index(level) >= 2:
            flagged.append(p)
    if not flagged:
        return []
    bad, texts = _words(flagged)
    good, _ = _words(safe)
    taken = {skeleton(x["term"]) for x in lex.pending} | lex.rejected
    for t in lex.terms():
        taken |= {skeleton(f) for f in [t["term"]] + t["variants"]}
    added = []
    for w, who in sorted(bad.items(), key=lambda kv: -len(kv[1])):
        if len(who) < MIN_SENDERS or w in good or w in taken:
            continue
        labels = [lab for lab in label_texts(texts[w]) if lab in LABEL_CATEGORY]
        cat = LABEL_CATEGORY[max(set(labels), key=labels.count)] if labels else "Bullying"
        chats = len({k for k in who})
        added.append(lex.add_pending(w, cat, "warn", "Auto",
                                     f"Seen from {chats} senders in chats flagged as harmful, 0 safe chats."))
    return added
