"""Hinglish/English text pools per intent, split into disjoint train/test lines.

Lines are combined with fillers and noise at generation time, so a few dozen base lines per
intent produce thousands of distinct messages. Train and test never share a base line.
"""
import random

POOLS = {
    "greeting": [
        "hi", "hello", "hey", "hii", "good morning", "gm", "good night", "gn", "kya haal hai",
        "kaise ho", "hey there", "hello ji", "namaste", "sup", "yo", "hi kaisi ho", "hey wassup",
        "good evening", "morning", "subah subah hi", "hello hello", "hi again", "hey you",
        "kya chal raha hai", "aur batao",
    ],
    "small_talk": [
        "kya kar rahe ho", "khana khaya", "aaj college gaye?", "exam kab hai", "movie dekhi?",
        "weekend plans?", "bahut garmi hai aaj", "kal ka match dekha", "assignment ho gaya?",
        "tired hoon aaj", "what are you doing", "office kaisa tha", "new song suna?",
        "kal milte hain?", "traffic bahut tha", "chai pi li?", "netflix pe kya dekh rahe ho",
        "result aaya?", "class bunk kar di", "mummy ne bulaya", "aaj baarish ho rahi hai",
        "bas aise hi", "kuch nahi yaar", "bored hoon", "lunch kya tha",
    ],
    "flirt": [
        "you look cute today", "tumhari smile bahut pyari hai", "miss you", "thinking about you",
        "you're so pretty", "date pe chalogi?", "aaj bahut acchi lag rahi thi", "can't stop thinking of you",
        "tum special ho", "coffee chalein?", "your dp is so nice", "dil le gayi tum", "you're my favourite",
        "wish you were here", "tumse baat karke accha lagta hai", "you have pretty eyes",
        "kab miloge", "send a selfie na", "you make me smile", "crush ho tum meri",
    ],
    "sexual": [
        "send nudes", "send pics na bas ek baar", "show me your body", "video call pe aao akele",
        "what are you wearing", "come to my room tonight", "i want to see you without clothes",
        "nangi pic bhej", "sexy lag rahi ho", "bed pe kya kar rahi ho", "let's sext",
        "photo bhej na private wali", "tumhari body kamaal hai", "akele milo na raat ko",
        "show me more", "i know you want it too", "ek hot pic bhejo", "send something spicy",
    ],
    "insult": [
        "you are so ugly", "full chapri hai tu", "moti kahin ki", "nobody likes you", "loser",
        "pagal hai kya", "shakal dekhi hai apni", "gawar", "kitni dumb hai tu", "bewakoof",
        "you're worthless", "tu kisi kaam ki nahi", "kutti", "kamini", "go cry somewhere",
        "everyone laughs at you", "kaali kalooti", "tere jaisi ladki", "useless", "cheap lagti hai",
    ],
    "banter_swear": [
        "abe saale", "chal be", "bhai tu pagal hai", "abey chutiye kal kya hua", "saala kamina hai tu",
        "bc kya scene hai", "abe gadhe", "teri toh", "chup kar be", "haha kamine", "ullu ke pathe",
        "tu na sach me", "noob hai tu", "saale treat de", "abe nalle", "bhai kya bakwas hai",
    ],
    "threat": [
        "i will kill you", "dekh lena tujhe", "maar dunga", "chhodunga nahi tujhe", "you will regret this",
        "acid daal dunga", "i will find you", "tera ghar pata hai mujhe", "bahar nikal phir batata hoon",
        "teri life barbaad kar dunga", "you won't be safe", "tujhe sabak sikhaunga",
        "wait and watch kya karta hoon", "tere bhai ko bhi dekh lunga",
    ],
    "sextortion": [
        "10k bhej warna ye photo sabko bhej dunga", "pay or i post your pics", "i have your pics",
        "paise bhej nahi toh viral kar dunga", "your morphed photo is ready", "send money or everyone sees",
        "deepfake bana diya hai tera", "tere ghar walon ko bhej dunga ye photo", "5000 bhej abhi",
        "insta pe daal dunga agar paise nahi diye", "i will leak this", "upi kar warna",
    ],
    "surveillance": [
        "saw you outside college today", "who were you with", "where are you right now",
        "i know where you live", "tum kiske saath thi", "i am outside your house", "send your location",
        "kal metro me dekha tha tujhe", "uss ladke ke saath kya kar rahi thi", "i'm watching you",
        "following you is easy", "tumhara gym time pata hai", "red dress me thi na aaj",
        "aaj late kyu aayi ghar",
    ],
    "clingy": [
        "reply na", "why are you online but not replying", "block kyu kiya", "please reply",
        "ignore mat karo", "answer me", "itna attitude kyu", "ek baar baat kar lo", "hello??",
        "kab tak ignore karogi", "seen karke reply nahi", "i'll keep texting till you reply",
        "pick up the call", "why are you avoiding me", "new account bana liya, ab?", "?", "??",
    ],
    "apology": [
        "sorry, i won't message again", "my bad, sorry", "sorry agar bura laga", "okay, i'll stop",
        "sorry, respect your choice", "theek hai, nahi karunga message", "apologies",
    ],
    "media": ["📷 Photo", "🎥 Video", "🎤 Voice message"],
    # user-side replies
    "warm_reply": [
        "haha you're sweet", "aww thank you", "miss you too", "😊😊", "you too", "haan chalo",
        "pakka milte hain", "hehe stop it 😂", "love you", "same here", "tum bhi", "❤️",
        "accha laga sunke", "yes let's go", "sure, kal?", "😘",
    ],
    "playful_reply": [
        "haha chal be", "😂😂", "abe ja na", "lol", "tu pagal hai", "hahaha", "shut up 😂", "kamine",
        "bakwas mat kar", "lmao", "teri toh 😂", "noob",
    ],
    "neutral_reply": [
        "ok", "hmm", "haan", "theek hai", "fine", "acha", "busy hoon", "baad me baat karte", "okay",
        "ji", "kal batati hoon", "pata nahi", "nahi", "haan khaya",
    ],
    "deflect_reply": [
        "k", "busy", "bhaiya pls", "later", "i have to go", "not now", "hmm ok bye", "sone ja rahi hoon",
        "mummy bula rahi hai", "baad me", "kuch kaam hai",
    ],
    "rejection": [
        "please stop messaging me", "i'm not interested", "mujhe baat nahi karni", "stop it",
        "don't text me again", "leave me alone", "block kar dungi", "please mat karo", "no",
        "i said no", "mujhe pareshan mat karo", "i will report you",
    ],
}

FILLERS_PRE = ["", "", "", "arre ", "yaar ", "suno ", "listen ", "oye ", "bro ", "ji "]
FILLERS_POST = ["", "", "", " yaar", " na", " 😊", " 🙂", " 😂", " pls", " ?", " !!", " 🥺", " 😏"]
LEET = {"a": "@", "i": "1", "e": "3", "o": "0", "s": "$"}


def split_pools(seed=42, test_frac=0.3):
    rng = random.Random(seed)
    train, test = {}, {}
    for k, lines in POOLS.items():
        lines = lines[:]
        rng.shuffle(lines)
        n_test = max(1, int(len(lines) * test_frac))
        test[k], train[k] = lines[:n_test], lines[n_test:]
    return train, test


def _choice(rng, seq):
    return seq[int(rng.integers(len(seq)))]


def noisy(text, rng, p=0.25):
    """Leetspeak, repeated letters, dropped vowels and fillers: the obfuscation real users apply.
    rng is a numpy Generator."""
    if text.startswith(("📷", "🎥", "🎤")):
        return text
    t = text
    if rng.random() < p:
        t = "".join(LEET.get(c, c) if rng.random() < 0.3 else c for c in t)
    if rng.random() < p and len(t) > 3:
        i = int(rng.integers(len(t)))
        t = t[:i] + t[i] * int(rng.integers(2, 5)) + t[i + 1:]
    if rng.random() < p * 0.5:
        t = "".join(c for c in t if c not in "aeiou" or rng.random() < 0.6)
    return (_choice(rng, FILLERS_PRE) + t + _choice(rng, FILLERS_POST)).strip()


def sample_text(pools, intent, rng):
    return noisy(_choice(rng, pools[intent]), rng)
