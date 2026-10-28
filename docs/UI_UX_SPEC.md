# SafeSphere: UI / UX Specification

The full list of screens, features, buttons and states for the **web app (24-hour deliverable)** and the **Android app (target)**.

**Priority tags**
- **P0** = must have for the hackathon demo
- **P1** = nice to have if time allows
- **P2** = future / phone app only

**Status in the prototype** (`ui/index.html`):
- ✅ built
- 🟡 built but not wired to the backend
- ⬜ not built

---

## 0. UX principles (trauma-informed design)

Our users may be frightened, ashamed or in crisis. Every screen follows these rules:

| # | Principle | How it shows up in the UI |
|---|---|---|
| 1 | **Calm, not alarming** | Plain language with no sirens. Red is used only for Critical. The tone is "You're not alone. Here's what to do." |
| 2 | **Never blame the victim** | No "Why did you share this?" Use "This is not your fault" on Critical screens. |
| 3 | **Explicit media is blurred by default** | Every flagged image or video shows blurred, with a **Tap to reveal** button and a warning. |
| 4 | **The user is in control** | Nothing is reported automatically. Every link, flag and report can be confirmed, undone or dismissed. |
| 5 | **Explain every flag** | Each alert has a "Why?" section with plain reasons, never just a score. |
| 6 | **Quick exit / discreet mode** | A **Quick Exit** button (and the Esc key ×2) switches instantly to a neutral screen. Optional disguised app icon and name. |
| 7 | **Few steps in a crisis** | From a Critical alert to the evidence pack and a report channel takes **2 taps or fewer**. |
| 8 | **Privacy shown openly** | A "Processed on device" badge and a clear statement of what is uploaded and why. |
| 9 | **Accessible** | WCAG AA contrast, keyboard navigation, screen-reader labels, colour plus icon plus text for severity (never colour alone), Hindi/English toggle. |
| 10 | **Works at phone width** | Responsive down to 360 px. The sidebar becomes top tabs on small screens. |

---

## 1. Design system

### 1.1 Severity scale (used everywhere)
| Level | Colour | Icon | Label | Use |
|---|---|---|---|---|
| Info | Green `#2f9e6e` | 🟢 | Info | Logged, no alert |
| Warn | Amber `#c98a00` | 🟡 | Warn | Gentle check-in |
| High | Orange `#e2622b` | 🟠 | High | Alert with an evidence option |
| Critical | Red `#d6264f` | 🔴 | Critical | Panic flow |

### 1.2 Tokens
- **Brand:** purple `#6d4aff` (trustworthy, not police-blue).
- **Light and dark themes** are defined as CSS variables, and the app follows the system setting.
- **Font:** system UI. 14 px body, 22 px page title, 12 px meta text.
- **Corners:** cards 14 px, buttons 10 px, chips are pill-shaped.
- **App badges:** WA (green), IG (gradient), TG (blue), SMS (grey), Snap (yellow).

### 1.3 Reusable components
| Component | Description |
|---|---|
| `SeverityChip` | A coloured pill with an icon and label |
| `CategoryTag` | A small grey tag (Stalking, Sextortion…) |
| `AppBadge` | A square icon showing which app the message came from |
| `RiskBar` | A horizontal bar from 0 to 100, coloured by severity |
| `NotificationCard` | App badge, sender, time, text, severity and category |
| `AlertCard` | Severity, category, plain explanation, sender and action buttons |
| `PersonRow` | Avatar, name, number of accounts, tags, risk bar and score |
| `ConsentTimeline` | A segmented bar (Neutral → Mutual / Unreciprocated → Rejected → Violation) with dates |
| `ReasonList` | A bulleted "Why we flagged this" list with key facts in bold |
| `BlurredMedia` | Blurred thumbnail, "Sensitive content" label and a **Tap to reveal** button |
| `PipelineStep` | Status icon (waiting / running / pass / flagged), step name and result |
| `HashText` | Monospace SHA-256 text with a **Copy** button |
| `Toast` | A short pop-up in the bottom-right, auto-dismissed after 4.5 s, with an action link |
| `ConfirmDialog` | Used for destructive or irreversible actions |
| `EmptyState` | Icon, one sentence and the main action button |

---

## 2. Global layout

### 2.1 Sidebar (desktop) / top tabs (mobile)
| Item | Badge | Priority | Status |
|---|---|---|---|
| 🏠 Home / Overview | — | P1 | ⬜ |
| 📡 Live Feed | Unread alert count (red) | P0 | ✅ |
| 👤 People | Number of High/Critical people | P0 | ✅ |
| 🖼️ Media Check | — | P0 | ✅ |
| 📥 Import Chat | — | P0 | 🟡 |
| 🧾 Evidence & Report | Number of packs | P0 | ✅ |
| 📊 Metrics | — | P0 | ✅ (placeholder data) |
| 🔤 Slang List | Number of pending suggestions | P1 | ⬜ |
| ⚙️ Settings | — | P1 | ⬜ |
| 🆘 Get Help Now | — (always red, pinned at the bottom) | P0 | ⬜ |

### 2.2 Global header and footer
| Element | Action | Priority |
|---|---|---|
| **Protection status** ("● Protection active / paused") | Click to pause or resume monitoring | P0 ✅ (display only) |
| **🚪 Quick Exit** button (top right, always visible) | Switches immediately to a neutral page (e.g. a weather or news page) and clears the view | P1 ⬜ |
| **🌐 EN / हिं** toggle | Switches the language | P2 ⬜ |
| **🌓 Theme** toggle | Light, dark or system | P1 ⬜ |
| **🔔 Notification bell** | Opens the latest alerts | P1 ⬜ |

---

## 3. Screens

### 3.1 Onboarding (phone app, P2. Show as slides in the demo)

| Step | Content | Buttons |
|---|---|---|
| 1. Welcome | "SafeSphere quietly watches for harassment, stalking and deepfakes, and helps you collect evidence." | **Get started** |
| 2. Privacy promise | What we read (messaging app notifications only), what stays on the device, what is uploaded (flagged items only) | **I understand** · *Read the full privacy policy* |
| 3. Notification access | Explanation and illustration | **Open settings** → the app detects the grant → ✅ **Continue**. Help link: *"It's greyed out?"*, which explains Allow restricted settings |
| 4. Choose apps | Toggles for WhatsApp, Instagram, Telegram, Snapchat, Messenger and SMS | **Continue** |
| 5. Keep running | Battery-optimisation explanation | **Allow** · *How to enable autostart on my phone* (brand-specific guide) |
| 6. Media folder (optional) | Lets the app check images and voice notes | **Choose WhatsApp Media folder** · **Skip** |
| 7. Face enrolment (optional) | "Lets us tell you if a fake image shows your face. Your face data never leaves this phone." | **Take selfie** · **Skip** |
| 8. Trusted contact (optional) | Name and phone number of someone to alert in an emergency | **Add contact** · **Skip** |
| 9. Import history (optional) | Import past chats | **Import a chat** · **Finish** |

Progress dots are shown at the top. Every optional step can be skipped and set up later in Settings.

---

### 3.2 Home / Overview (P1)

**Purpose:** an at-a-glance safety status.

| Element | Detail |
|---|---|
| Greeting and status card | "You're protected. 2 people need attention." Coloured by the worst current level. |
| KPI tiles (4) | Messages scanned · People tracked · Flagged · Critical |
| "Needs attention" list | The top 3 people at High or Critical, each with a **View** button |
| Recent alerts (5) | `AlertCard` list with **See all** |
| Quick actions | **Check a photo/video** · **Import a chat** · **Get help now** |

---

### 3.3 Live Feed (P0) ✅

**Purpose:** a real-time stream of incoming notifications, plus alerts.

**Layout:** KPI tiles at the top, then two columns: the notification stream on the left and the alerts panel on the right. On phones the two columns stack.

| Feature | Detail | Status |
|---|---|---|
| KPI tiles | Messages scanned, people tracked, flagged messages, critical alerts. They update live. | ✅ |
| Notification stream | Newest first. Each card shows app, sender, time, text, severity chip and category tag. Clean messages show "✓ Clean, stays on device". | ✅ |
| Hidden-preview card | Shows "New message, preview hidden: scored on metadata only" | ✅ |
| Media placeholder | "📷 Photo" with a **Check this media** button | ⬜ |
| Coloured left border | Matches the severity level | ✅ |
| Alerts panel | `AlertCard`s for High and Critical | ✅ |
| Critical toast | Pop-up in the bottom-right | ✅ |
| Filters | All · Flagged only · by app · by level | ⬜ P1 |
| Search | Search sender or text | ⬜ P1 |

**Buttons**
| Button | Where | Action | Status |
|---|---|---|---|
| **▶ Start simulation / ⏸ Pause / ▶ Resume** | Header | Plays the scripted demo feed | ✅ |
| **Reset** | Header | Clears the feed and counters | ✅ |
| **Speed** (1× / 2×) | Header | Demo playback speed | ⬜ P1 |
| **Load scenario ▾** | Header | Choose a script: Silent stalker / Sextortion / Class bullying / Mutual flirt | ⬜ P1 |
| **View person** | AlertCard | Opens People with that person selected | ✅ |
| **Evidence & report** | Critical AlertCard | Opens Evidence with that person selected | ✅ |
| **Dismiss** | AlertCard | Hides the alert. It stays logged. | ⬜ P1 |
| **Not harassment** | AlertCard / NotificationCard | Marks a false positive, lowers that contact's risk and logs feedback | ⬜ P0 |
| **Missed this? Flag it** | Clean NotificationCard | Marks a false negative and offers to add terms to the slang list | ⬜ P1 |
| **Check this media** | Media placeholder | Opens Media Check with the file preloaded | ⬜ P1 |

**Empty state:** "Press **Start simulation** to stream a scripted demo chat." (✅)

---

### 3.4 People (P0) ✅

**Purpose:** see each harasser as one person across accounts, with the reasons.

**Left: ranked list**
| Element | Status |
|---|---|
| `PersonRow` sorted by risk (avatar, name, number of accounts, category tags, risk bar, severity, score) | ✅ |
| Filter: All · High+ · Known contacts · Strangers | ⬜ P1 |
| Search | ⬜ P1 |
| **+ Merge people manually** button | ⬜ P1 |

**Right: person detail**
| Section | Content | Status |
|---|---|---|
| Header | Avatar, name, severity chip, risk out of 100 | ✅ |
| Linked accounts | App badge, handle, link label ("Linked 91%") and a one-line reason | ✅ |
| Consent timeline | Segmented bar. **P1:** hover shows the date and message that caused each change (e.g. "12 Oct: 'please stop'") | ✅ (bar only) |
| Why we flagged this | `ReasonList` | ✅ |
| Behaviour features | Key/value rows (messages per day, reply ratio, messages after "no"…) | ✅ |
| Activity chart | Messages per day plus a night-time heatmap | ⬜ P1 |
| Message history | All messages from this person across accounts, flagged ones highlighted | ⬜ P1 |
| Relationship setting | Dropdown: Stranger · Acquaintance · Friend · Partner · Family. Feeds the model. | ⬜ P1 |

**Buttons**
| Button | Action | Status |
|---|---|---|
| **✓ Confirm link** | Confirms the account match, merges for good, updates risk | 🟡 |
| **✗ Not the same person** | Splits the account out and trains the linker | 🟡 |
| **Build evidence pack** (primary) | Opens Evidence with this person selected | ✅ |
| **Not harassment** | Marks as safe or trusted, lowers alerts, logs feedback | 🟡 |
| **Alert trusted contact** | Opens a confirm dialog, then sends a pre-written message | 🟡 |
| **Mute alerts** | Snoozes for 24 h, 7 days or always | ⬜ P1 |
| **How to block** | Step-by-step blocking guide for each app | ⬜ P1 |

---

### 3.5 Media Check (P0) ✅

**Purpose:** analyse an image, video or voice note with the four-step pipeline.

| Element | Detail | Status |
|---|---|---|
| Drop zone | Drag and drop or click. Accepts image, video and audio. Shows file name and size. | ✅ |
| Blurred preview | Blurred by default | ✅ |
| **Tap to reveal** | Un-blurs after a warning dialog | ⬜ P0 |
| Context field | Text box: "Message sent with this media (optional)" | ⬜ P0 (currently static text) |
| Pipeline steps | 1 Nudity check · 2 Face match · 3 Deepfake model · 4 Context. Each shows waiting, running, pass or flagged, with a score. | ✅ (mock) |
| Verdict card | Severity, a one-line verdict, and a "What to do" list | ✅ (mock) |
| Heatmap toggle | Overlays the deepfake model's heatmap if it produces one | ⬜ P1 |
| Video timeline | Score for each frame across the video | ⬜ P1 |
| Audio waveform | Waveform plus a voice-clone score and transcript | ⬜ P1 |
| Confidence wording | Always "Likely manipulated (88%)", never "Fake" | ✅ |

**Buttons**
| Button | Action | Status |
|---|---|---|
| **Choose file** | Opens the file picker | ✅ |
| **Analyse** | Runs `POST /detect/{type}` (currently runs on upload) | 🟡 |
| **Tap to reveal / Hide** | Toggles the blur | ⬜ P0 |
| **Generate evidence pack →** | Opens Evidence with this media attached | ✅ |
| **Hash on StopNCII** | Opens StopNCII.org in a new tab, with a short guide | ⬜ P0 |
| **Add to a person** | Attaches the media to an existing person's case | ⬜ P1 |
| **Analyse another** | Resets the screen | ⬜ P1 |

**Error states:** unsupported file type · file too large (over 50 MB) · model server unreachable ("Couldn't reach the analysis server. Retry?") with a **Retry** button.

---

### 3.6 Import Chat (P0) 🟡

**Purpose:** add history and both sides of the conversation.

| Source card | Instructions | Button | Status |
|---|---|---|---|
| 💬 WhatsApp | Chat → ⋮ → More → Export chat → .txt | **Upload .txt** | 🟡 |
| 📸 Instagram | Download your information → messages JSON | **Upload .json** | 🟡 |
| ✈️ Telegram | Desktop → Export chat history → JSON | **Upload .json** | 🟡 |
| 🖼️ Screenshots (OCR) | Any app, works on iPhone | **Upload images** | 🟡 |

**After upload (P0 ⬜):**
1. **Parse preview:** "Found 1,240 messages between You and Rahul K, 3 Aug – 14 Oct."
2. **Who are you?** A dropdown to pick which participant is the user, so the reply classifier knows which side is theirs.
3. **Link to person:** a dropdown with existing people, or "+ New person".
4. **Import & analyse** button → progress bar → summary card: "23 flagged messages · consent violated on 12 Oct" with a **View person** button.

Errors: unrecognised format (with a sample of the expected format), empty file, and OCR text that's unreadable (shown with a confidence level).

---

### 3.7 Evidence & Report (P0) ✅

**Purpose:** a tamper-evident pack and one-tap routes to report.

| Section | Content | Status |
|---|---|---|
| Person selector | Dropdown of flagged people | ✅ |
| Flagged items table | Time · app/account · message · category · SHA-256 | ✅ |
| Include/exclude checkboxes | The user chooses which items go in the pack | ⬜ P1 |
| Media items | Blurred thumbnails plus a hash for each | ⬜ P1 |
| Deleted messages | Rows tagged "Deleted by sender" | ⬜ P1 |
| Pack fingerprint | A SHA-256 over all items | ✅ |
| Pattern summary | Consent timeline plus activity chart (embedded) | ⬜ P1 |
| Legal provisions | BNS / IT Act sections with plain descriptions and a "not legal advice" note | ✅ |
| Pre-filled complaint | An editable text box | ✅ (read-only) |
| Report channels | Six cards: cybercrime.gov.in, 1930, StopNCII, NCW/181, Grievance Officer, 112 | ✅ (no links yet) |
| Smart suggestion | Highlights the right channel, e.g. sextortion → **1930 + StopNCII first** | ⬜ P1 |

**Buttons**
| Button | Action | Status |
|---|---|---|
| **Generate pack** | Computes the hashes and shows the pack fingerprint | ✅ |
| **⬇ Download JSON** | Saves the machine-readable pack | ✅ |
| **⬇ Download PDF** | A printable report for the police or a lawyer | ⬜ P0 |
| **📋 Copy complaint** | Copies the complaint text to the clipboard | ⬜ P0 |
| **✏️ Edit complaint** | Makes the text editable | ⬜ P1 |
| **Open portal →** (on each channel card) | Opens cybercrime.gov.in, StopNCII etc. in a new tab | ⬜ P0 |
| **📞 Call 1930 / 112** | A `tel:` link (on phones) | ⬜ P0 |
| **Share pack** | System share sheet (phone) | ⬜ P2 |
| **Verify pack** | Re-hashes the items to prove nothing changed | ⬜ P1 |

---

### 3.8 Critical / Panic screen (P0 ⬜)

Opens automatically on a Critical alert as a full-screen overlay. It can also be opened from **🆘 Get Help Now**.

| Element | Content |
|---|---|
| Heading | "You're not alone. This is not your fault." |
| What happened | One line, e.g. "Someone sent a manipulated intimate image of you with a money demand." |
| **3 rules** (large icons) | 🚫 **Don't pay** · 🗑️ **Don't delete** · 💬 **Don't reply** |
| Step-by-step checklist | ☐ Evidence saved (auto-checked) · ☐ Hash on StopNCII · ☐ Call 1930 · ☐ Report on cybercrime.gov.in · ☐ Tell someone you trust |
| Buttons | **📞 Call 1930** (primary) · **Open StopNCII** · **Report online** · **Alert trusted contact** · **View evidence** · **I'm safe for now** (closes the screen) |
| Support line | Links to mental-health helplines (e.g. Tele-MANAS **14416**) |

---

### 3.9 Metrics (P0) ✅ (placeholder data)

| Element | Detail | Status |
|---|---|---|
| Headline chart | Grouped bars: keyword-only vs SafeSphere, showing precision, recall, F1 and detection rate | ✅ |
| Per-category table | Precision / recall / F1 for each category | ✅ |
| False-alarm rate on flirting/banter | A large number, where lower is better | ✅ (empty) |
| Confusion matrix | A heatmap for each category | ⬜ P1 |
| Account-linking accuracy | A stat tile | ⬜ P1 |
| Deepfake metrics | Detection rate and false-alarm rate per type (image, video, audio) | ⬜ P0 |
| Dataset info | Test set size, sources, and a "synthetic" disclosure | ⬜ P0 |
| **Load results** button | Loads the `eval.py` output JSON | ⬜ P0 |
| **Run evaluation** button | Calls `POST /eval` and shows a spinner | ⬜ P1 |
| Placeholder banner | "⚠ Sample values" until real results are loaded | ✅ |

---

### 3.10 Slang List (P1 ⬜)

**Purpose:** show that the system keeps learning new slang.

| Element | Detail |
|---|---|
| Term table | Term · category · severity · variants · source (seed / user / AI) · date added |
| Search and category filter | — |
| **Pending suggestions** queue | Terms proposed by an AI model or users, each with **✓ Approve / ✗ Reject / ✏️ Edit** |
| **+ Add term** | Form: term, category, severity, variants |
| **✨ Suggest variants** | Calls the AI model for spellings and code-word variants of a term |
| **Test a message** | Paste text, see the normalised text and matched terms highlighted |
| Change log | "Added 'ch@pri' variant · 2 h ago" |

---

### 3.11 Settings (P1 ⬜)

| Group | Controls |
|---|---|
| Protection | Monitoring on/off · apps monitored (toggles) · alert sensitivity (Low / Balanced / High) |
| People | Trusted contacts list (**+ Add**, **Remove**) · known/safe contacts list |
| Face | **Re-enrol face** · **Delete face data** |
| Discretion | Quick Exit on/off · disguised app name and icon · hide notification previews |
| Privacy | Status of upload-only-flagged · **Export my data** · **Delete all data** (confirm dialog, irreversible) |
| Language and theme | EN / हिं · light / dark / system |
| About | Model versions, privacy policy, helpline list |

---

## 4. Notifications sent by SafeSphere (phone app, P2)

| Level | Notification text example | Tap action |
|---|---|---|
| Warn | "Rahul has sent 30 messages tonight without a reply. Is this bothering you?" with **Yes / No** buttons | Answers the check-in |
| High | "Rahul is back on a new Instagram account (91% match)." | Person detail |
| Critical | "Possible sextortion. Tap for help. Don't pay." | Panic screen |

Notifications never show explicit content or the harasser's message text on the lock screen.

---

## 5. States to design for every screen

| State | Pattern |
|---|---|
| Empty | `EmptyState`: icon, one sentence, main action |
| Loading | Skeleton cards. Pipeline steps spin. |
| Error | An inline banner with the cause in plain words and a **Retry** button |
| Offline / server down | "Analysis server unreachable. On-device checks still running." |
| Low confidence | A "Low confidence: preview hidden" tag on metadata-only results |
| Placeholder data | A "⚠ Sample values" banner |

---

## 6. Accessibility checklist

- [ ] Text contrast ≥ 4.5:1 in both themes
- [ ] Severity always shown as colour **and** icon **and** text
- [ ] Every button has a visible focus ring and an `aria-label`
- [ ] Keyboard-only navigation: Tab through the sidebar and Enter to open
- [ ] Toasts use `aria-live="polite"`. The Critical overlay traps focus.
- [ ] Charts have an `aria-label` and a table alternative
- [ ] Respects `prefers-reduced-motion` (disables pop and spin animations)
- [ ] Tap targets ≥ 44 px on mobile

---

## 7. Buttons → backend endpoints

| UI action | Endpoint |
|---|---|
| Stream live / simulated message | `POST /ingest/notification` |
| Import chat | `POST /import/{whatsapp,instagram,telegram,ocr}` |
| Media analyse | `POST /detect/{image,video,audio}` |
| Person list / detail | `GET /people`, `GET /people/{id}` |
| Confirm / reject link | `POST /people/{id}/link` · `POST /people/{id}/unlink` |
| Not harassment / missed flag | `POST /feedback` |
| Generate evidence pack | `POST /report/{person_id}` → JSON / PDF |
| Slang suggestions | `GET /lexicon`, `POST /lexicon/suggest`, `POST /lexicon/approve` |
| Metrics | `GET /metrics`, `POST /eval` |
| Alert trusted contact | `POST /alert/trusted` |

---

## 8. Build order for the 24-hour hackathon

1. **Already done (✅):** Live Feed, People, Media Check (mock), Evidence (real hashing, JSON download), Metrics (placeholder).
2. **Next P0 work:**
   - wire the screens to the FastAPI endpoints
   - the Critical/Panic screen
   - **Tap to reveal** on blurred media
   - the editable context field on Media Check
   - the Not harassment button
   - import parsing with a "Who are you?" step
   - PDF download and Copy complaint
   - channel links and `tel:` buttons
   - the real metrics loader
   - the 🆘 Get Help Now button
3. **P1 if time allows:** Home overview, scenario picker, Slang List, Quick Exit, filters and search, activity charts, Settings.
4. **P2 (phone):** onboarding flow, system notifications, share sheet, disguised icon.
