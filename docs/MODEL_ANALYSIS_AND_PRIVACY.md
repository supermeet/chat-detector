# SafeSphere: Model Training Analysis & Privacy Design

---

# Part 1: Behavioural model: final analysis

## 1.1 What we trained
| Item | Detail |
|---|---|
| Task | For each **person** (all their accounts merged), decide whether contact is safe or harmful, and which of 8 behaviour types it is |
| Classes | safe_mutual, banter, normal_frequent, unreciprocated *(safe / warn zone)* · stalking, harassment_after_no, group_bullying, sextortion *(harmful)* |
| Inputs | ~50 behaviour + consent features: frequency, night-time share, reply ratio, unanswered streaks, messages after a "no", escalation, accounts/apps used, new account after a block, relationship, text availability |
| Models | Keyword filter (baseline) · Logistic regression (baseline) · **LightGBM**, with a multiclass head for the behaviour type and a binary head for harm risk (monotonic constraints + calibration) |
| Text models | TF-IDF character n-grams: message intent + the user's reply type (stand-in for MuRIL) |
| Hard rules | Sextortion, threat or a minor involved → **Critical**, regardless of score. Severe text labels need ≥ 80% confidence. |

## 1.2 Data
| Set | Persons | Messages | Notes |
|---|---|---|---|
| Team dataset: train | 4,800 | 315,659 | 600 per class; 1,053 hard cases; 31% of message text hidden |
| Team dataset: test | 1,200 | 79,909 | Disjoint templates, different seed |
| Our simulator: train | 2,400 | 745,309 | Second, independent generator (longer conversations) |
| Our simulator: test | 1,200 | 384,594 | Used to check that the model generalises |
| **Training total** | **7,200** | **~1.06 M** | 15% simulated label noise added during training |

**Hard cases** include safe conversations designed to look harmful (clingy partner, worried parent, long reply gaps, swearing friend, "said no once, then stopped") and harmful ones designed to look safe (polite stalker, fearful polite replies).

## 1.3 Results
Binary harmful detection, using **labels predicted by the text model** (the realistic setting):

| Test set | Keyword | Logistic regression | **LightGBM (ours)** |
|---|---|---|---|
| **Team test: F1** | 0.718 | 0.893 | **0.985** |
| Team test: precision / recall | 0.760 / 0.680 | 0.807 / 0.998 | **0.975 / 0.995** |
| Team test: **false alarms on hard negatives** | 25.6% | 6.9% | **0.6%** |
| **Simulator test: F1** | 0.608 | 0.892 | **0.933** |
| Simulator test: precision / recall | 0.650 / 0.572 | 0.826 / 0.968 | **0.891 / 0.980** |
| Simulator test: false alarms on hard negatives | 40.0% | 37.3% | **26.4%** |

| Other metric | Value |
|---|---|
| Behaviour-type macro-F1 (8 classes) | 0.967 team test · 0.858 simulator test |
| With perfect message labels (upper bound) | F1 0.995, 0% hard-negative false alarms |
| **Metadata only (no text at all)** | F1 0.992, vs 0.995 with text |
| Without consent features | F1 0.992 |
| Time to detect | All sampled harmful people flagged at the first check (≤ 5 messages) |
| Training time | ~5 minutes on a Colab CPU |

## 1.4 What we learned
1. **Behaviour beats keywords.** A keyword filter catches 68% of harmful people and flags a quarter of the tricky safe conversations. Our model catches 99.5% and wrongly flags 0.6% of them on the team test set.
2. **Stalking can be caught without reading any message.** The metadata-only model scores almost the same (0.992). This backs up the claim that we can detect a stalker even when notification previews are hidden.
3. **One generator isn't enough.** Trained on the team dataset alone, the model scored 0.997 on its own test set but only **0.65** on the other generator's, falsely flagging 91% of hard negatives there. It had learned one generator's quirks. Training on both generators raised cross-generator F1 to 0.93.
4. **Hard rules need confident inputs.** When the text model mislabelled harmless lines as "threat", the Critical rule fired on 89% of safe people in the simulator test. Requiring ≥ 80% confidence for threat/sextortion labels brought that down to 11%. A single misread line also no longer forces Critical: the rule needs 2 severe messages, or 1 plus some behaviour risk (a minor involved always forces Critical).
5. **The weak spot is the text model, not the behaviour model.** The behaviour model itself flags only 3 of 450 safe simulator people. Most of the remaining false alarms are worried-parent messages ("aaj late kyu aayi ghar", "why did you come home late today") that TF-IDF misreads as threats.

## 1.4b Found while wiring the live UI (29 Oct)
6. **Time of day matters, so the demo needs a scenario clock.** Streaming the scripts at 12:54 AM made "100% of
   messages at night" the top signal. The Live Feed now plays scripts on a scenario clock (evenings; sextortion late at
   night).
7. **Evidence gate.** One harmless first message ("you looked really nice in class today") scored Critical when
   streamed live, minutes apart. The training data spreads conversations over days, so a minute-scale burst is new to
   the model. A person now stays at most **Warn** until there are 5+ messages from them, or they keep going after a
   "no". Hard rules (confident threat or sextortion, a minor) still fire immediately.

   | After the first… | False alarms on safe chats | Harmful caught (with gate) | Harmful caught (no gate) |
   |---|---|---|---|
   | 3 messages | 0% | 4.7% | 25.3% |
   | 5 messages | 0% | 52.7% | 52.7% |
   | 10 messages | 0% | 79.3% | 79.3% |

   On the synthetic test set the gate only costs early recall at 3 messages. Its benefit is in live bursts that the
   synthetic data doesn't contain. Say this honestly.
8. **"Sextortion" label needs evidence.** Short chats looked like sextortion to the model. The label now needs a
   demand/threat message or media, but only when most messages are readable. Behaviour-type macro-F1 is 0.967 (team
   test) and 0.831 (second generator; 0.858 before the rule, 0.791 with a broader version). Binary harm detection is
   unchanged.

## 1.4c Case conclusion with Gemini
The Evidence screen's conclusion (summary, applicable Acts, next steps) is written by **Gemini (`gemini-3.5-flash`,
fallback `gemini-flash-lite-latest`)** from the model's **extracted facts only**: no message text, names or handles.
Gemini may only cite sections from the backend's vetted list (BNS 75/78/79/308/351/356, IT Act 66C/66D, 66E/67/67A,
67B + POCSO); anything else is dropped. Without a key, or on any error, a rule-based conclusion is used. A test checks
that no message text or handle reaches the prompt.

## 1.5 Limitations (say these before the judges do)
- **All data is synthetic.** The numbers show the method works, not how it performs in the real world.
- Consent and reply labels come from simulated replies. Real users say "no" in many more ways.
- The TF-IDF text model is a placeholder. Real Hinglish needs a fine-tuned MuRIL or HingBERT.
- The team test set and the training data come from the same generator, so 0.985 is optimistic. **The 0.93 simulator-test score is the more honest generalisation number.**

## 1.6 Next steps
1. A **hand-written test set** of ~100 realistic chats, double-labelled by the team (`external.py handwritten`). This becomes the headline metric.
2. Replace TF-IDF with **MuRIL** fine-tuned on HASOC/TRAC plus our intents, which should fix the worried-parent false alarms.
3. Add per-contact trust learned from the user's "Not harassment" feedback.
4. Re-check the risk thresholds against the hand-written set.

---

# Part 2: Privacy: what we do and why

## 2.1 The core tension (say it upfront)
SafeSphere reads messages, which is sensitive. It reads **two people's** data: the user's and the sender's (a third party). Done wrong, a safety app can itself become **stalkerware**. Our design answer is **process locally, store little, upload only what's flagged, and keep the user in control.**

## 2.2 Privacy principles → concrete measures

| # | Principle | What we actually do |
|---|---|---|
| 1 | **Data minimisation** | Read only an allow-list of chat apps (WhatsApp, Instagram, Telegram, SMS…). Never banking, OTP or email apps. We compute **behaviour features** (counts, timings, ratios) and do not keep raw text for clean messages. |
| 2 | **On-device first** | The notification listener, feature extraction and the small text model (ONNX / TFLite) run **on the phone**. Clean messages never leave the device. |
| 3 | **Upload only what's flagged, process and forget** | Only flagged media goes to the server for the deepfake model. The server is **stateless**: it analyses in memory, returns a score and deletes the file, with no logging of content. (Future: run the deepfake models on-device too.) |
| 4 | **Encryption everywhere** | Local database encrypted with **SQLCipher**, keys in the **Android Keystore**. TLS 1.3 with certificate pinning in transit. Evidence packs encrypted with a user-held key. |
| 5 | **No AI model sees chats** | Gemini writes the case conclusion from extracted facts only (e.g. `msgs_after_reject: 23`), never message text, names or handles. A test enforces this. Without a key it is off. The risk decision is always made by our own model. |
| 6 | **Biometrics stay on the phone** | The face-enrolment embedding is stored only on the device, never uploaded, and can be deleted with one tap. |
| 7 | **User control** | Per-app toggles, pause monitoring, a "what we store" dashboard, export my data, and **delete everything**. Nothing is ever reported automatically: the user decides. |
| 8 | **Retention limits** | Clean-message metadata auto-deletes after 30 days. Flagged evidence is kept until the user deletes it, because it may be needed for a police complaint. |
| 9 | **Training privacy** | User data is **not** used for training by default. Opt-in feedback ("Not harassment" / "missed this") shares only the label and anonymised features, **no text**. Future: federated learning with differential privacy. |
| 10 | **Minimal sharing in alerts** | A trusted-contact alert sends "I may need help", plus optional location if the user chooses. It never sends chats. |

## 2.3 Preventing misuse as stalkerware
An abuser could install the app on a partner's phone to read their chats. Safeguards:
- The **app is unlocked with a fingerprint or face check**, so the data can't be opened from someone else's hands.
- **No remote dashboard and no cloud copy of chats.** Nobody can read the data from another device.
- A **visible "protection active" notification** that can't be silently hidden.
- **No export to another device** without on-device authentication.
- Disguise mode (for victims) changes the icon only. The data is still locked behind the fingerprint or face check.

## 2.4 Third-party (sender) data
- We process the sender's messages **only on the recipient's own device**, for the recipient's safety and possible legal action. They are messages the user has already received.
- Evidence packs contain only **flagged** messages, not the whole history.
- Account linking suggestions are **never shown as certain**, and the user must confirm them. This avoids wrongly accusing someone.

## 2.5 Indian law we align with (verify with a legal mentor)
| Law / rule | How it applies |
|---|---|
| **Digital Personal Data Protection Act, 2023** (and its Rules) | Notice and consent at onboarding, purpose limitation, right to access/erase, breach notification, and **verifiable parental consent for users under 18** |
| IT Act 2000 §43A + SPDI Rules 2011 | "Reasonable security practices" for sensitive data such as biometrics → encryption, access control |
| IT Rules 2026 amendment | Our complaints cite the 2-hour/3-hour takedown deadlines. We don't host user content ourselves. |
| Google Play notification-listener policy | Clear disclosure of why notification access is needed; a safety use case |

> Note: under-18 users are a key group for cyberbullying, but DPDP requires parental consent for them. We'd offer a teen mode with guardian consent and a limited feature set.

## 2.6 Privacy in the hackathon build vs production
| | Hackathon demo | Production plan |
|---|---|---|
| Processing | Web app + laptop backend, **synthetic data only** | On-device features and text model; stateless server for media |
| Storage | Browser memory, nothing persisted | SQLCipher + Keystore, 30-day retention |
| AI model | Not used on chats | Facts only, opt-in |
| Training data | Fully synthetic | Opt-in, anonymised features only |

## 2.7 One-paragraph answer for the mentor
> "SafeSphere works on-device first. The phone reads only messaging-app notifications, turns them into behaviour features locally, and deletes clean messages. Only flagged items, such as a suspicious image, go to our server, which analyses them in memory and keeps nothing. Everything stored is encrypted with keys in the Android Keystore, face data never leaves the phone, and no AI model ever sees chat text. The user can pause, export or delete everything, and nothing is reported without their decision. To stop the app being misused as stalkerware, it's locked with a fingerprint or face check, has no remote access or cloud copy of chats, and always shows a visible notification. We follow the DPDP Act's consent, purpose-limitation and erasure rules, including parental consent for minors."
