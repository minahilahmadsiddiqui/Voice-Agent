# Problem Statement — SRP Benefits Verification Voice Agent

**Goal:** build a voice agent that phones a live dental insurance rep, proves it represents the practice, gets the Scaling and Root Planing (SRP) benefits out of the rep, and hangs up with a validated JSON record where every field has a source.

---

## 1. Background

Before treatment, a dental practice has to confirm what the patient's insurance will pay. Eligibility APIs cover the basics but often leave out the details an **SRP treatment plan** depends on:

- How often SRP is allowed, per quadrant
- Which quadrants have already been paid, and when
- What documentation the payer requires, and when a claim is downgraded
- How periodontal maintenance (D4910) is handled after SRP

So staff still call the payer's provider line. A typical call takes 10–15 minutes, and most of that is phone menus and hold time. Amplify wants an agent that makes these calls.

### Domain terms

| Term | Meaning |
|---|---|
| **SRP** | Scaling and Root Planing, a deep cleaning for gum disease |
| **D4341** | SRP, 4 or more teeth in a quadrant |
| **D4342** | SRP, 1–3 teeth in a quadrant |
| **D4910** | Periodontal maintenance, the follow-up cleaning after SRP |
| **D1110** | Adult prophylaxis, a regular cleaning. SRP is often downgraded to this |
| **Quadrant** | One quarter of the mouth: UR, UL, LR, LL (upper/lower, right/left) |
| **Frequency limit** | How often a code can be paid, e.g. once per quadrant every 24 months |
| **Downgrade** | The payer processes the claim as a cheaper code when documentation falls short |
| **Tax ID / NPI** | Identifiers the practice gives to authenticate on the call |

---

## 2. The challenge

- The agent places an **outbound** call to a live human rep, **Haider**, who is in the **US**.
- Haider plays the insurance rep **adversarially** and **blind-ranks** every candidate's agent.
- The agent runs the whole call: introduces itself, gets through verification, asks the right questions in the right order, handles hedging and "let me pull that up" pauses, and hangs up with the data.
- Amplify wants a **prototype that shows problem-solving**, not a production system.
- We have **6 days** to build and test before the demo. The ranking sets priority for Amplify contract work.

---

## 3. The call, stage by stage

The agent works through these stages in order. It can go back to an earlier stage if the rep corrects something or asks for information again.

1. **Phone menu** (may not happen): say "benefits" or press 1, and enter the tax ID on the keypad followed by `#`. Haider may skip the menu and answer as a person.
2. **Hold:** stay silent through hold music and silence. Never hang up because of it. Recognise when a person says hello.
3. **Introduction:** say it is an automated assistant calling for **Cedar Park Dental**. Give the provider, tax ID, NPI and callback number.
4. **Patient verification:** give the patient's name, date of birth, member ID and relationship to the subscriber. Confirm coverage is active, and get the effective date and benefit year.
5. **Benefit questions:** coverage %, deductible, annual maximum and amount remaining, frequency limit.
6. **Claim history by quadrant:** which quadrants have been paid and when. Also ask which quadrants have **nothing** on file.
7. **Date math, confirmed back:** work out each quadrant's next eligible date and ask the rep to confirm it and how it is counted.
8. **Rules:** documentation requirements, downgrade rule, quadrants allowed per visit.
9. **D4910:** coverage, frequency, whether it shares a limit with D1110, and any waiting period after SRP.
10. **Read-back:** repeat every value and record any corrections. In the reference call, the remaining maximum changed by $93 at this step.
11. **Close:** get the reference number and the rep's full name. Capture the "not a guarantee of payment" disclaimer word for word.
12. **Output:** hang up and produce validated JSON.

---

## 4. Data to capture

Each field stores its **value**, its **status** (`answered` / `refused` / `unknown` / `corrected_on_readback`), the rep's **exact words**, and the **transcript turn** it came from. A question the rep never answered becomes `null` and is **never guessed**.

| Group | Field | Why it matters | Example (reference call) |
|---|---|---|---|
| Member | Name, DOB, member ID, subscriber, active, effective date, benefit year | Confirms the right plan and time period | Lana Kane, active since 2024-03-01, calendar year |
| SRP | Coverage % for D4341 / D4342, benefit class | The headline number | 80%, basic |
| SRP | Deductible amount and whether met | Changes what the patient pays | $50, met |
| SRP | Annual maximum and remaining | The most the plan will pay | $1,500 / $1,247 |
| SRP | Frequency limit and how it is counted | When treatment can be repeated | 1 per quadrant / 24 months, counted from date of service |
| SRP | Per-quadrant history: code, paid date, next eligible | **The field the treatment plan depends on** | UR, LR paid 2025-02-04 → eligible 2027-02-04; UL, LL open now |
| SRP | Quadrants per date of service | Scheduling | 2 |
| SRP | Documentation: charting, X-rays, minimum pocket depth, bone loss, pre-authorization | Avoids denials | 4 mm + bone loss; pre-authorization recommended, not required |
| SRP | Downgrade rule | The fallback payment | Paid as D1110 if documentation doesn't support the diagnosis |
| D4910 | Coverage %, frequency, shared with D1110, waiting period after SRP | Follow-up care | 80%, 2 per year shared with D1110, 90 days |
| Call | Rep name, reference number, disclaimer, hold time, call length | Makes the quote defensible later | Denise Okafor, ref 771402988 |

---

## 5. What makes it hard

### What Haider will likely do

- Refuse to continue until he gets the NPI, the tax ID, or the right spelling
- Ask "Are you a robot?" or "Who am I speaking with?"
- Say "let me pull that up", then go silent or put the agent on hold
- Answer two questions at once, or a question the agent hasn't asked yet
- Give vague answers ("it depends", "should be covered") that need a follow-up
- Give a wrong value and correct it later, especially on read-back
- Say the patient isn't found or the DOB doesn't match, or refuse to give out some information
- Talk over the agent, rush it, or try to end the call early

### Technical traps

- **Speed:** the agent needs to reply in under about 1 second, or it sounds robotic.
- **Turn-taking:** "Let me look…" is not the end of the rep's turn, and hold music is not speech.
- **Numbers:** IDs, dates and dollar amounts must be heard correctly by speech-to-text and read out correctly by text-to-speech.
- **Tracking:** the agent must always know which fields are still missing, and never ask for one twice.
- **Accuracy:** date math and the final JSON must be correct, with nothing made up.

---

## 6. Success criteria

| # | Criterion | How we measure it |
|---|---|---|
| 1 | Gets through the phone menu and hold without hanging up | Simulator and live test calls |
| 2 | Authenticates correctly on the first try | No authentication failures in test calls |
| 3 | Captures all required fields, or marks each one explicitly as refused or unknown | Field coverage in the test scorecard |
| 4 | Field values are correct | ≥ 95% match against simulator ground truth |
| 5 | Reads everything back and records corrections | Correction test cases pass |
| 6 | Gets the reference number, rep name and verbatim disclaimer | Present in every completed call |
| 7 | Sounds natural | Median response time < 1.2 s; numbers are clear over a real phone line |
| 8 | The JSON validates and every field has a source | Pydantic validation plus transcript links |

### In scope
One payer call, one patient, SRP (D4341/D4342) plus D4910. The patient and practice details come from a config file. The deliverables are a results viewer, the call recording, the transcript, and the code on GitHub.

### Out of scope
Production scaling, a real practice-management system or scheduling integration, HIPAA-grade hosting, multiple payers, and procedures other than SRP and D4910.

---

## 7. Assumptions and open questions

- **Assumption:** the scenario uses the reference data (Cedar Park Dental / Lana Kane) unless Amplify provides different details.
- **Assumption:** Haider may or may not simulate a phone menu and hold queue, so the agent must handle both.
- **Open:** Haider's exact US phone number, and whether it's a mobile or a landline.
- **Open:** will Amplify provide the demo patient and practice details ahead of time?
- **Open:** is recording the call acceptable to Haider? The agent will say at the start that the call may be recorded.
