# The Task, Explained Simply

Study notes. Read top to bottom once, then use as a dictionary.

---

## Part A — The email

| What the email says | What it really means |
|---|---|
| "Amplify is moving very fast" | Busy startup. They value people who deliver without hand-holding. |
| "We care about solutions and results" | They judge: **does it work on the call?** Not slides, not fancy code. |
| "Not production-grade... ability to think through a problem and prototype" | A **prototype** = a first working version. They want to see your **thinking** (why you built it this way) + something that **works**. |
| "Dental insurance verification takes place over the phone" | Offices phone insurance companies to ask what a patient's plan pays. |
| "APIs... frequently missing high value data points... SRP" | An **API** = a way for software to ask another system for data. Insurance APIs give basics, but not SRP details. So humans still call. |
| "Build a voice agent that places an outbound phone call" | **Voice agent** = AI that listens and talks. **Outbound** = OUR agent dials THEM. |
| "to a live human insurance representative (Haider)" | A real person answers, not a recording. |
| "comes back with a structured object" | At the end: clean data (JSON), not a chat log. |
| "Haider will play the insurance rep and blind rank the solutions" | **Blind rank** = he doesn't know whose agent is whose. He ranks all candidates best to worst. You're competing. |
| "identify itself" | Say who it is and who it calls for. |
| "get through the verification gauntlet" | **Gauntlet** = a series of checks. Tax ID, NPI, patient name, DOB, member ID... rep won't help until these pass. |
| "ask the right questions in the right order" | Logical order, nothing missed, nothing asked twice. |
| "handle the hedging" | **Hedging** = vague answers: "should be covered", "it depends". Agent must ask a follow-up. |
| "and the 'let me pull that up' pauses" | Rep goes quiet while searching. Agent must WAIT, not talk over, not hang up. |
| "hang up with the data" | End politely, then output the JSON. |
| "Haider will not make it easy" | Expect tricks: interruptions, wrong values, "are you a robot?", refusals. |
| "a claude-written conversation example" | The PDF is an **example**, not a script. Haider will NOT follow it word for word. The agent must handle any order. |
| "stripped-down, simplified version of the real work" | Real product is bigger. This is a slice. |
| "connect again in two weeks to do some demos" | Demo = live call with Haider. |
| "determine priority for contract work" | Best-ranked candidates get work first. |

---

## Part B — The PDF

### B1. What the PDF is
A **fake (synthetic) example call** written by Claude. All names and numbers are made up. It shows what a **perfect call** looks like and what **perfect output** looks like.

### B2. The scenario
- **Caller:** Amplify's agent, for **Cedar Park Dental** (Denver)
- **Called:** **Meridian Dental Benefits**, provider services line
- **Patient:** Lana Kane, DOB 07/09/1983, Member ID MDB40719883
- **Goal:** SRP benefits
- **Call length:** 14m 22s, of which **8m 41s on hold**

### B3. Dictionary

**Phone / call words**
- **IVR** — the robot phone menu ("press 1 for benefits")
- **DTMF** — the keypad beep tones. `841552037#` = typing tax ID then pound key
- **Hold queue** — waiting line with music
- **Provider** — the dentist / practice (our side)
- **Payer / carrier** — the insurance company (their side)
- **Callback number** — practice phone number in case the rep needs to call back

**Identity words**
- **Tax ID** — the practice's business tax number (84-1552037)
- **NPI** — National Provider Identifier, the dentist's 10-digit ID (1477588213)
- **Member ID** — the patient's insurance card number
- **Subscriber** — the person who owns the plan. Lana is the subscriber (not a child/spouse on someone else's plan)

**Plan words**
- **Active** — insurance is valid today
- **Effective date** — when coverage started (03/01/2024)
- **Calendar year plan** — benefits reset every Jan 1
- **In network** — the dentist has a contract with this insurer (better rates)
- **Basic class** — insurers group services: preventive / basic / major. Perio (gum work) is basic here, paid at 80%
- **Deductible** — what the patient pays first before insurance pays ($50, already met)
- **Annual maximum** — the most insurance pays per year ($1,500)
- **Remaining** — how much of that is left ($1,247 after correction)

**Dental words**
- **SRP** — Scaling and Root Planing, a deep cleaning under the gums for gum disease
- **Quadrant** — mouth split in 4: **UR** upper right, **UL** upper left, **LR** lower right, **LL** lower left
- **D4341** — SRP on 4+ teeth in one quadrant
- **D4342** — SRP on 1–3 teeth in one quadrant
- **D1110** — regular adult cleaning ("prophy")
- **D4910** — periodontal maintenance, the follow-up cleaning after SRP
- **Frequency limit** — how often insurance pays (1 per quadrant per 24 months)
- **Date of service (DOS)** — the day treatment is done
- **Quadrants per DOS** — how many quadrants can be done in one visit (2)
- **Perio charting** — measurement of gum pockets around each tooth
- **Pocket depth** — gap between gum and tooth; 4mm+ means disease
- **Bone loss** — shown on X-rays (radiographs)
- **Pre-authorization / pre-treatment estimate** — asking insurance before treatment. Here: recommended, not required
- **Downgrade** — insurance pays it as a cheaper code. Here: if paperwork is weak, SRP gets paid as a regular cleaning (D1110)
- **Waiting period** — must wait 90 days after SRP before D4910 is covered

**Closing words**
- **Read-back** — agent repeats everything so the rep can correct mistakes
- **Reference number** — the call's ID in the insurer's system (proof the call happened)
- **Disclaimer** — "not a guarantee of payment". Saved word for word

### B4. The call in 6 phases
1. **Robot phase** — IVR menu → say "benefits" → type tax ID → hold 8m 41s in silence
2. **Prove who we are** — rep Denise asks; agent gives practice, doctor, tax ID, NPI, callback
3. **Prove the patient** — name, DOB, member ID, "she's the subscriber". Rep: active since 03/01/2024, calendar year
4. **Ask the questions** — coverage % → deductible → max & remaining → frequency → claim history by quadrant → "what has NOTHING on file?" → date math → paperwork → downgrade → quadrants per visit → D4910 → waiting period
5. **Read-back** — rep corrects remaining $1,340 → $1,247 (a claim finalized last week)
6. **Close** — reference number 771402988, rep's full name Denise Okafor, disclaimer confirmed

### B5. The JSON output, in 4 groups
- **member** — who the patient is and if the plan is active
- **srp** — coverage, deductible, max, remaining, frequency, quadrants per visit, history per quadrant (with next eligible dates), documentation rules, downgrade rule
- **d4910** — coverage, frequency, shared with D1110, waiting period
- **call** — rep name, reference, hold seconds (521), total seconds (862), disclaimer, source ("payer_rep_verbal" = the rep said it)

Notice: `"remaining_corrected_on_readback": true` — the JSON even records that a value changed during read-back.

**The rule:** every field has a source. Unanswered → `null`. **Never guess.**

### B6. The 5 lessons ("mechanics that matter")
1. **Most of the call is not conversation.** Survive the menu, keypad, and long hold. Music ≠ hang up.
2. **Authentication runs outbound.** We must prove we're the practice before asking anything.
3. **A percentage alone is worthless.** 80% means nothing without deductible, remaining max, frequency, last paid dates. The rep won't volunteer them — the agent must ask, including doing the date math and confirming it.
4. **Absence is data.** "UL and LL have nothing on file" = they can be treated now. This is the most useful answer of all, and it only comes from asking what's NOT there.
5. **Read-back, reference number, caveat.** Catches mistakes ($93 change). Reference + disclaimer make the data defensible if a claim is denied later.

---

## Part C — What this means for us (hidden requirements)

1. **Haider won't follow the PDF.** Agent must handle any order, extra info, corrections.
2. **It must work on a real phone call.** Not just in a browser.
3. **It must be fast.** Long silences sound robotic. Aim for replies in ~1 second.
4. **It must hear and say numbers perfectly.** IDs, dates, dollars.
5. **It must be patient.** Hold, silence, "let me pull that up".
6. **It must be honest.** Says it's an automated assistant. Never invents data.
7. **Output must match the PDF's JSON shape**, so they can compare easily.
8. **Show your thinking.** Clear docs on why each choice was made — that's half of what they judge.
