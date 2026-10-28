# Research Report: Personal & Social Harassment in the AI Era (PS 5, Hacksploit 2026)

## 1. What is actually happening (2025–2026)

| Threat | What happened | Source |
|---|---|---|
| AI "nudify" deepfakes | About 10% of cases reaching an Indian abuse helpline now involve AI-manipulated images, mostly used for **blackmail or shaming**. In one case a loan-application photo was put through a nudify app after the victim stopped paying. | Rati Foundation / Tattle via [StopVAW](https://www.stopvaw.org/india_ai_deepfakes_limiting_women_s_internet_use), [MIR](https://www.mironline.ca/?p=81296) |
| Grok "undress" scandal (Jan 2026) | Grok on X was used at scale to sexualise photos of real women. MeitY notified X on 2 Jan 2026. The UK criminalised *creating* non-consensual intimate images, Indonesia and Malaysia restricted Grok, and the EU opened a DSA review. | [Express & Star](https://www.expressandstar.com/uk-news/2026/01/13/creating-non-consensual-sexual-images-to-become-illegal-amid-grok-ai-backlash/), [NYU Stern](https://bhr.stern.nyu.edu/quick-take/the-grok-nudify-controversy-is-another-example-of-the-need-for-international-ai-regulation/) |
| Women going offline | Women in India report self-censoring and leaving platforms out of fear of being morphed. This is the "chilling effect". | [DESIblitz](https://www.desiblitz.com/content/how-ai-deepfakes-are-driving-indian-women-offline), [Digit](https://www.digit.in/features/general/indias-deepfake-crisis-women-are-falling-prey-to-ai-menace-more-than-men.html/amp/) |
| Unequal access to justice | Celebrities win takedown orders. Ordinary victims, mostly women, rarely do, and notice-and-takedown can't keep up with re-uploads. | [NALSAR Tech Law Forum](https://techlawforum.nalsar.ac.in/rethinking-judicial-approaches-to-sexually-explicit-deepfakes-the-case-for-article-21-based-relief-against-nudifying-websites/) |
| Regulation | **IT Rules amendment, notified 10 Feb 2026, in force 20 Feb 2026.** Synthetically Generated Information (SGI) must be labelled, takedown within **3 hours**, and within **2 hours for non-consensual intimate imagery (NCII)**, including morphed images. | [Business Today](https://www.businesstoday.in/technology/story/govt-tightens-rules-on-ai-generated-content-mandates-labels-and-faster-takedowns-515505-2026-02-10), [iPleaders](https://blog.ipleaders.in/it-rules-2026/), [Mondaq](https://www.mondaq.com/india/new-technology/1760554/it-rules-2026-deepfake-regulation-three-hour-takedowns-and-ai-labelling-obligations) |

> I couldn't verify 2026 NCRB cyberstalking counts online. Cite the NCRB "Crime in India" report directly before the pitch.

## 2. Threat taxonomy (what the system must catch)

1. **Cyberstalking**: repeated unwanted contact, contact after being blocked from alternate accounts, monitoring ("I saw you at…"), messages late at night, and escalation over days. *Keywords alone miss this*, because each message can look harmless ("hi", "reply na", "why online but not replying").
2. **Cyberbullying**: insults, body-shaming, exclusion, pile-ons, and code-mixed Hinglish abuse ("chapri", "bhenchod" variants, leetspeak like "b1tch", emoji codes 🍆🍑).
3. **Digital sexual harassment**: unsolicited explicit images ("cyber-flashing"), sexual comments, and grooming of minors.
4. **AI-enabled abuse (new)**:
   - Nudify/deepfake images used to **sextort** ("send money or I post this").
   - Voice-clone threats and fake audio.
   - LLM-generated harassment at scale (bots and many accounts).
   - Morphed photos on loan-app recovery harassment, a pattern specific to India.
5. **Doxxing and threats**: sharing an address or phone number, and threats of physical harm.

## 3. Gaps in existing solutions

- Platform filters scan **single messages**. They can't see that one person sent 80 messages in 3 days at 2 AM.
- Hinglish and code words evade English-trained classifiers.
- Victims carry the burden of evidence: screenshots are easy to dispute, and they don't know where to report.
- Re-uploads beat takedowns. Hash-matching through **StopNCII.org** exists, but few victims know about it.

## 4. Proposed solution: **SafeSphere** (victim-side guardian)

A personal safety assistant that a user feeds their chats, DMs, images and voice notes into (by import or share-sheet). It:

1. **Behavioral engine**: profiles each sender by **frequency, persistence, time of day, ignored-message ratio, toxicity trend, and alias accounts**, and outputs a *stalking risk score* with an explanation.
2. **Multimodal filter**: text (multilingual toxicity model plus a Hinglish lexicon), images (NSFW classifier plus a deepfake/manipulation check), and audio (Whisper transcription, then the text pipeline).
3. **Adaptive slang lexicon**: a JSON lexicon that grows two ways. Users flag missed messages, and an optional LLM proposes new slang/code-word entries for human review. No model retraining is needed.
4. **One-click evidence pack and report**: timestamped, SHA-256-hashed evidence (tamper-evident), mapped to legal sections (IT Act 66E/67/67A, BNS 78 stalking, 79, 351, 356), with direct routes to **cybercrime.gov.in / 1930**, **NCW**, and **StopNCII**. It also cites the 2-hour NCII takedown rule when the user writes to a platform.
5. **Metrics**: precision, recall, F1 and detection rate on a labelled test set (`poc/eval.py`).

### Why this wins on the judging criteria
- It directly covers all 5 deliverables (see `ARCHITECTURE.md` §6).
- It is grounded in the Feb 2026 IT Rules, which makes it timely and India-specific.
- It is victim-centric: it produces *court-usable evidence*, not just a warning.
