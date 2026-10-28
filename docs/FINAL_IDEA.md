# SafeSphere: Final Idea
**Hacksploit 2026 · PS 5: Detection and Prevention of Personal & Social Harassment**

> *We detect patterns, not just words, and turn victims' fear into evidence.*

---

## 1. Problem

Digital harassment has moved past abusive words to **patterns and AI**:

- **AI deepfakes and nudify apps.** In Jan 2026, Grok on X was used to sexualise photos of real women at scale. MeitY sent X a notice, the UK criminalised *creating* such images, and Indonesia and Malaysia restricted Grok.
- **Sextortion in India.** About 1 in 10 cases reaching an Indian abuse helpline now involves AI-manipulated images, mostly used for blackmail (Rati Foundation / Tattle). One case involved a loan-app photo that was morphed after the victim stopped paying.
- **The chilling effect.** Women are leaving platforms and self-censoring out of fear of being morphed.
- **Unequal justice.** Celebrities win takedown orders. Ordinary victims are left with screenshots and re-uploads.
- **New law.** The IT Rules amendment was notified on 10 Feb 2026 and took effect on **20 Feb 2026**. It requires labelling of AI-generated content, takedown within **3 hours**, and **2 hours for non-consensual intimate imagery (NCII)**, including deepfakes.

### Why current tools fail
1. **They check one message at a time.** A stalker who sends "hi", "reply na", "why online?" 80 times at 2 AM is never flagged.
2. **They're blind to Hinglish and code words.** Variants like "ch@pri", "b1tch", 🍆🍑 codes and spaced-out letters slip through.
3. **They don't understand consent.** The same message can be flirting or harassment depending on the reply.
4. **The victim carries the burden.** Screenshots are easy to dispute, and victims don't know where to report.

---

## 2. Solution: SafeSphere

A **victim-side, phone-first guardian app** that:
1. reads incoming messages from all chat apps in one feed
2. scores **people** (not single messages) on behaviour and consent
3. links a harasser's accounts across platforms
4. checks media with **our own trained deepfake detectors** (image, video, audio)
5. adapts to new slang
6. generates **tamper-evident evidence packs** mapped to Indian law, with one-tap reporting

---

## 3. How it reads messages on the phone

**Main source: Android `NotificationListenerService`**, the same API smartwatches use. It reads sender, text, app and time from WhatsApp, Instagram, Telegram, Snapchat, Messenger and SMS.

| Permission | Purpose |
|---|---|
| Notification access (`BIND_NOTIFICATION_LISTENER_SERVICE`) | Read incoming messages. Granted by the user in Settings. |
| `POST_NOTIFICATIONS` | Show our own alerts |
| `INTERNET` | Send *only flagged* items to the backend |
| `CAMERA` | One-time face enrolment (stays on the device) |
| Folder access (Storage Access Framework, WhatsApp Media folder) | Read received images and voice notes |
| Battery-optimisation exemption + autostart | Keeps the listener alive on Xiaomi, Oppo, Vivo, Realme |

We **don't** request SMS, Contacts or Accessibility permissions.

### When notifications don't include the text
| Case | Handling |
|---|---|
| Preview hidden ("New message") | **Behaviour from metadata alone**: who, how often, when |
| Grouped ("5 new messages") | Counted as 5 events |
| Instagram message request ("X wants to send you a message") | **A signal in itself**: a new unknown account trying to reach the user |
| 📷 Photo / 🎤 Voice note | Read from the WhatsApp Media folder, or "Share to SafeSphere" |
| Muted chats / history before install | Import the chat export |
| iPhone | No notification access. Import, share-sheet and screenshot OCR only. |

**Three levels of detection:**
1. **Metadata only, always available:** catches the "silent stalker".
2. **Message text:** toxicity, consent tracking, sextortion intent.
3. **Full context, filled in by the user:** chat export (both sides), screenshot OCR, the one-tap "Is this unwanted?" answer.

Missing text lowers our **confidence**, not our **detection**.

**Bonus:** we capture messages before the sender deletes them, so deleted messages are preserved as evidence.

---

## 4. Core engines

### 4.1 Behaviour and consent engine (deliverable 1)
**Key idea: flirting and harassment use the same words. What separates them is reciprocity and consent.**

| Signal | Flirting / banter | Harassment |
|---|---|---|
| Reciprocity | Two-way, user starts conversations too | One-sided |
| User's reply tone | Positive, playful, flirts back | Deflects, rejects ("please stop", "k", "bhaiya"), silence, blocks |
| **After a "no"** ⭐ | Sender backs off | Continues, escalates, new account |
| Explicitness | Matches the user's level | Sender escalates while the user stays cold |

**Reply classifier:** labels each of the user's replies as `accept / playful / neutral / deflect / reject / block`.

**Consent tracker:** `NEUTRAL → MUTUAL` or `NEUTRAL → UNRECIPROCATED → REJECTED → VIOLATION`. A "no" is sticky: once the user rejects, later flirty or sexual messages count much more heavily.

**Features per person:** reciprocity, conversations started by each side, reply effort, reply latency trend, **messages after the rejection**, escalation gap, unanswered streak, share of night messages (00–05), messages per day, active days, number of accounts and platforms, monitoring phrases, known contact, relationship age.

**Model:** gradient boosting on these features, plus hard rules. It explains every flag, for example *"User said 'please stop' on 12 Oct; 23 messages since, 62% at night, 3 accounts."*

**Grey zone (risk 0.4–0.6):** the app asks *"Is this person bothering you?"* The answer sets that contact's trust level and becomes new training data. An AI model may explain ambiguous cases, but it never makes the decision.

### 4.2 Linking one person across accounts
Every handle is an account, and accounts are grouped into a person. Linking signals:
- same phone number
- fuzzy match on names and handles (`rahul_k`, `r4hul_k`)
- **writing-style fingerprint** (letter patterns, sentence embeddings, emoji habits, Hinglish spelling)
- **a new account appearing 24–48 h after a block**
- the same media resent (matched by image fingerprint)
- shared context

The app outputs a match % with reasons, **the user confirms or rejects every link**, and manual merging is allowed.

### 4.3 Multimodal threat filtering (deliverable 2)
**Text:** fine-tuned **MuRIL / HingBERT**. Fallback: `unitary/multilingual-toxic-xlm-roberta`.
- **Final score = max(model, adaptive word list).**
- Labels: `none / insult / sexual / threat / sextortion / surveillance / self-harm-push`.

**Media pipeline:**
```
Media → 1. nudity check → 2. face match vs the user's enrolled selfie
      → 3. OUR deepfake detectors (image / video / audio) → 4. text sent with it
      → combined verdict
```
- **Video:** about 1 frame per second through the image model, and the soundtrack through the audio model.
- **Our models are wrapped** behind `POST /detect/{image|video|audio}` returning `{score, label, heatmap?}`, with ONNX export where possible.
- **Wording:** always "likely manipulated (87%)", never "fake".

| Explicit | User's face | Deepfake | Context | Verdict |
|---|---|---|---|---|
| ✔ | ✔ | ✔ | money / threat | 🔴 AI sextortion |
| ✔ | ✔ | ✘ | any | 🔴 Real intimate image leaked |
| ✔ | ✘ | – | unsolicited | 🟠 Cyber-flashing (unwanted explicit image) |
| – | – | ✔ audio | "it's me, send money / come alone" | 🔴 Voice-clone threat or scam |
| ✘ | ✔ | ✔ | mocking | 🟠 Deepfake used to humiliate |

### 4.4 Slang adaptation (deliverable 3)
- A JSON word list with categories, severity and variants.
- **Normalisation** handles leetspeak, symbols, repeated and spaced-out letters, and emoji codes.
- **Feedback loop:** the user reports a missed term → an AI model suggests variants → a human approves → the list hot-reloads. **No retraining is needed.**
- The AI model receives **only slang terms, never chat content**.

---

## 5. What we flag

| # | Category | Triggers |
|---|---|---|
| 1 | **Stalking / obsessive contact** | Frequency, persistence, night messages, unanswered streak, **continuing after a "no"** |
| 2 | **Surveillance / control** | Location demands, "saw you at…", "who were you with", "I'm outside" |
| 3 | **Evasion / multiple accounts** | New account after a block, a linked person across apps, repeated requests from strangers |
| 4 | **Bullying / abuse** | Insults, slurs, body-shaming, Hinglish or coded abuse, pile-ons, pushing self-harm |
| 5 | **Sexual harassment** | Unwanted sexual remarks, pressure for pictures, cyber-flashing, sexual content after a "no", anything sexual involving a minor |
| 6 | **Sextortion / blackmail** | "Pay or I'll post", "I have your pics", "viral kar dunga" ("I'll make it viral") |
| 7 | **AI-manipulated media** | Deepfake image, video or audio, especially of the user's own face; voice clones |
| 8 | **Threats / doxxing** | Threats of violence, rape or acid attack; sharing the user's address or number |

**Not flagged:** mutual flirting, banter between friends, frequent chats with known trusted contacts, and one-off mild rudeness (logged only).

### Severity levels
| Level | When | Action |
|---|---|---|
| 🟢 Info | One mild message or an early pattern | Logged silently |
| 🟡 Warn | A pattern is building | "Is this person bothering you?" with mute or block options |
| 🟠 High | Stalking, after a "no", surveillance, multiple accounts, sexual harassment | Alert with reasons, evidence pack prepared, report options |
| 🔴 Critical | Sextortion, intimate or deepfake image of the user, threats, a minor involved | Panic screen: **"Don't pay, don't delete, don't reply"**, then StopNCII, 1930, the cybercrime portal and a trusted-contact alert |

**Hard rules:** sextortion, intimate images of the user, threats and minors go **straight to Critical**.

---

## 6. Evidence and reporting (deliverable 4)

**The app never reports anything on its own.** The user decides.

**Evidence pack contents:**
- the person's profile and all linked accounts, with match % and reasons
- every flagged item with its original timestamp, app, category, and a **SHA-256 hash** (a fingerprint showing it wasn't altered), plus captured deleted messages
- a **fingerprint for the whole pack**
- the pattern summary: consent timeline, frequency and timing charts, escalation
- media analysis: deepfake score, face match, heatmap
- **suggested legal provisions** (to check with a legal adviser):
  - Stalking: BNS 78
  - Sexual harassment: BNS 75; insulting a woman's modesty: BNS 79
  - Intimidation and threats: BNS 351
  - Extortion: BNS 308
  - Defamation: BNS 356
  - Private or intimate images: IT Act 66E / 67 / 67A
  - Impersonation accounts: IT Act 66C / 66D
  - Minors: IT Act 67B + POCSO
- a **pre-filled complaint** citing the IT Rules 2026 2-hour and 3-hour deadlines

| Situation | Channel |
|---|---|
| Any cyber harassment | **cybercrime.gov.in**, "Women/Child related crime" section (anonymous reports allowed) |
| Money demanded or paid | **1930** helpline |
| Intimate or deepfake image | **StopNCII.org** (fingerprints on the device, blocks re-uploads) |
| Women | **NCW** complaint, **181** women's helpline |
| Minor | Cybercrime portal + **POCSO e-Box (NCPCR)** |
| Content or account removal | In-app report + platform **Grievance Officer** |
| Immediate danger | **112** + trusted contact |

---

## 7. Datasets and training

| Dataset | Use |
|---|---|
| HASOC (2019–21, code-mixed) | Hinglish offensive content |
| TRAC-1 / TRAC-2 | Aggression and misogyny (Hindi-English) |
| MACD (ShareChat) | Abuse in Indian languages |
| Jigsaw Toxic + Multilingual | Insult, threat and obscene labels |
| Twitter cyberbullying (Kaggle) | Bullying categories |
| **Our synthetic data** | Sextortion, monitoring phrases and stalking messages, which no public set has. Generated with an AI model, plus Hinglish transliteration, leetspeak and emoji variants. |
| **Synthetic conversations** (about 2–5k) | Behaviour and consent model. Scenarios: mutual flirting, one-sided persistent, rejected then continued, friends' banter, couple fighting, polite stalker, sextortion. |
| **Hand-written test set** (about 100 conversations) | Realistic held-out evaluation |
| Our deepfake datasets | Already used to train our image, video and audio detectors |

Check each dataset's licence before use.

---

## 8. Metrics (deliverable 5)

- **Text:** precision, recall and F1 for each label on a held-out Hinglish test set.
- **Stalking ⭐ (headline chart):** detection rate, **keyword-only vs our behaviour model**.
- **False-positive rate on mutual flirting and banter.** This proves we tell flirting from harassment.
- **Account linking:** accuracy at matching accounts to the right person.
- **Deepfake:** our models' detection rate, plus the false-alarm rate of the combined media pipeline.

---

## 9. Architecture

```
PHONE (target: Flutter + Kotlin listener)      SERVER (FastAPI, laptop for the hackathon)
 Notification listener ─┐                      ┌ Text model (MuRIL/HingBERT) + word list
 Chat / screenshot import ┼─► quick on-device ─►├ Reply classifier + consent tracker
 Share to SafeSphere     │    check (~10 ms)    ├ Behaviour risk model (gradient boosting)
 Face enrolment          │                     ├ Account-linking engine
 Alerts / panic mode  ◄──┘                     ├ Nudity check + face match + OUR deepfake models
                                               ├ Risk combiner → Info / Warn / High / Critical
                                               └ Evidence pack (SHA-256, legal map, report links)
```

**Privacy by design:**
- Only a fixed list of messaging apps is read.
- Clean messages never leave the device.
- Only flagged items are uploaded.
- The local database is encrypted.
- The AI model sees slang terms only.
- The user can view and delete everything.

---

## 10. 24-hour deliverable

**Main deliverable: a web app on the laptop**, a React dashboard with a FastAPI backend. All models run on the laptop.

The phone story stays alive through the **Live Feed Simulator**. It replays scripted chats in the exact notification format, including hidden previews and "📷 Photo", so alerts appear in real time. The Android listener is shown as an architecture slide with its code, and it's a stretch goal.

**Screens** (prototype: `ui/index.html`):
1. Live Feed: simulated notifications with real-time alerts
2. People: linked accounts, risk score, consent timeline, reasons
3. Media Check: upload, then the four-step pipeline and verdict
4. Import Chat: WhatsApp .txt, Instagram JSON, screenshot OCR, Telegram
5. Evidence & Report: SHA-256 pack, legal provisions, complaint, channels
6. Metrics: keyword vs behaviour, per-category scores, false alarms on flirting

**Browser extension:** dropped, because it isn't phone-first. Mentioned as future work.

### Timeline
| Hours | Backend / ML | Front-end | Deepfake team |
|---|---|---|---|
| 0–3 | FastAPI skeleton, word list, synthetic data generator | React scaffold | Wrap models behind `/detect/*` |
| 3–10 | Text model (ready-made model first, MuRIL fine-tune on Colab), reply classifier, consent tracker | Live feed simulator, Import | Nudity check + face match |
| 10–16 | Behaviour model, account linking, risk combiner | People, Media Check | Combined media verdict |
| 16–20 | Evidence pack, `eval.py` | Evidence, Metrics | Integration |
| 20–24 | **Feature freeze**, demo data, rehearsal, slides. Android listener only if everything else is done. | | |

### Demo flow (3 min)
1. Messages stream in. Friend banter and mutual flirting stay **clean**.
2. Rahul escalates, then returns on a new Instagram account, which is **linked at 91%**. The consent timeline shows **"continued after no"**.
3. A notification with a hidden preview is still scored on metadata.
4. An unknown account sends a photo. The **deepfake + face-match** check triggers 🔴 **AI sextortion**.
5. One tap generates the **evidence pack** with fingerprints, legal provisions and the 2-hour takedown complaint.
6. The metrics slide shows **keyword vs behaviour**, with a low false-alarm rate on flirting.

---

## 11. What makes us different

1. **Consent-aware behaviour scoring**: flirting vs harassment decided by reciprocity and continuing after a "no"
2. **Detection from metadata alone**: catches stalkers who never use a bad word
3. **Linking one harasser across accounts and platforms**, confirmed by the user
4. **Our own deepfake detectors combined with a match against the user's face**, which recognises "this is a fake of *you*"
5. **Hinglish-first**, with slang updates that need no retraining
6. **Court-ready evidence**: SHA-256 fingerprints, captured deleted messages, Indian legal mapping, IT Rules 2026 deadlines
7. **Privacy-first and victim-controlled**: nothing is reported automatically

## 12. Honest limitations

- Deepfake detection is probabilistic, so it's shown as a confidence level and paired with a human decision.
- There's no public stalking or consent dataset, so the behaviour model is trained on synthetic data. We say this openly.
- Live notifications only show incoming messages, so the user's side comes from imports and feedback.
- iPhone has no notification access: import and OCR only.
- Android 13+ greys out notification access for apps installed directly from an APK. Fix: App info → ⋮ → "Allow restricted settings".
- Mutual banter between friends can still produce false alarms. Known-contact trust and the "Not harassment" button reduce them.

## 13. Future scope

- A production Android app on the Play Store
- iOS share extension and screenshot OCR
- Monitoring Instagram and WhatsApp Web through a browser extension
- Integration with the StopNCII API
- Opt-in, anonymised reporting of trends to cyber cells
- Regional languages: Tamil, Bengali, Marathi

---

### Sources
- [StopVAW: AI deepfakes limiting women's internet use in India](https://www.stopvaw.org/india_ai_deepfakes_limiting_women_s_internet_use)
- [MIR: AI's rise in India exposing women to new digital harms](https://www.mironline.ca/?p=81296)
- [DESIblitz: How AI deepfakes are driving Indian women offline](https://www.desiblitz.com/content/how-ai-deepfakes-are-driving-indian-women-offline)
- [NALSAR Tech Law Forum: Sexually explicit deepfakes and Article 21](https://techlawforum.nalsar.ac.in/rethinking-judicial-approaches-to-sexually-explicit-deepfakes-the-case-for-article-21-based-relief-against-nudifying-websites/)
- [Express & Star: Creating non-consensual sexual images to become illegal amid Grok backlash](https://www.expressandstar.com/uk-news/2026/01/13/creating-non-consensual-sexual-images-to-become-illegal-amid-grok-ai-backlash/)
- [NYU Stern: The Grok nudify controversy](https://bhr.stern.nyu.edu/quick-take/the-grok-nudify-controversy-is-another-example-of-the-need-for-international-ai-regulation/)
- [Business Today: Govt mandates labels and faster takedowns (IT Rules 2026)](https://www.businesstoday.in/technology/story/govt-tightens-rules-on-ai-generated-content-mandates-labels-and-faster-takedowns-515505-2026-02-10)
- [iPleaders: IT Rules 2026](https://blog.ipleaders.in/it-rules-2026/)
- [Mondaq: Three-hour takedowns and AI labelling obligations](https://www.mondaq.com/india/new-technology/1760554/it-rules-2026-deepfake-regulation-three-hour-takedowns-and-ai-labelling-obligations)
