# Step 1 + Step 2: Understanding the Problem and System Design

---

# PART 1: UNDERSTANDING THE PROBLEM

## The story in plain words

A dental clinic (Cedar Park Dental) wants to do a **deep cleaning** on a patient (Lana Kane). It's called **SRP**. Before treatment, the clinic has to know what her insurance will pay.

The usual insurance lookups online leave out the important SRP details. So today a staff member phones the insurance company. They press menu buttons, wait on hold for about 9 minutes, then talk to a person and ask lots of questions. That takes 10–15 minutes.

**Our job:** build an AI that makes that call by itself. It talks to a real human, collects the answers, and returns them as clean, organized data (JSON).

**The twist:** the human is **Haider**, and he will play a *difficult* insurance rep on purpose. He compares everyone's agents without knowing whose is whose ("blind ranking").

## Words you need to know

| Word | Simple meaning |
|---|---|
| SRP | Deep cleaning of the gums |
| D4341 / D4342 | Insurance codes for SRP: 4+ teeth in one area, or 1–3 teeth |
| D4910 | The follow-up cleaning after SRP |
| D1110 | A normal cleaning, the cheaper one |
| Quadrant | The mouth split into 4 parts: UR, UL, LR, LL (upper/lower, right/left) |
| Frequency limit | How often insurance will pay, e.g. "once per quadrant every 24 months" |
| Downgrade | Insurance pays for the cheaper code if your paperwork isn't good enough |
| Deductible | The amount the patient pays first, before insurance starts paying |
| Annual maximum | The most insurance pays in a year. "Remaining" is what's left |
| IVR | The robot phone menu: "Press 1 for benefits" |
| DTMF | The beep tones made when you press phone keys |
| Tax ID / NPI | The clinic's ID numbers, used to prove who's calling |
| Read-back | Repeating everything back at the end so mistakes get caught |

## What the agent must do, in order (from the PDF)

1. **Get through the phone menu.** Say "benefits", type the tax ID with keypad tones, then wait on hold silently. Hold music is NOT a reason to hang up.
2. **Introduce itself honestly.** Say it's an automated assistant for Cedar Park Dental, then give the doctor's name, tax ID, NPI and callback number.
3. **Identify the patient.** Give her name, date of birth, member ID, and say she's the subscriber.
4. **Ask the money questions.** Coverage %, deductible (and whether it's met), annual maximum and how much is left.
5. **Ask the SRP rules.** How often SRP is allowed, which quadrants were already paid and when, **which quadrants have nothing on file**, and the next eligible date for each paid quadrant. The agent works out that date and asks the rep to confirm it.
6. **Ask the paperwork rules.** Documents needed, when the claim gets downgraded, and how many quadrants per visit.
7. **Ask about D4910.** Coverage, how often, whether it shares the limit with normal cleanings, and the waiting period after SRP.
8. **Read everything back.** Catch corrections (in the PDF the rep fixes $1,340 to $1,247).
9. **Close properly.** Get a reference number, the rep's full name, and the "not a guarantee of payment" warning word for word.
10. **Output JSON.** Every field shows where it came from. Unanswered means `null`. NEVER guess.

## The 5 lessons the PDF stresses (this is how they'll judge)

1. **Survive the boring part.** The menu, keypad tones and long hold all have to work.
2. **Prove who you are first.** If verification goes wrong, the call ends.
3. **A percentage alone is useless.** The value is in the follow-up questions.
4. **"Nothing on file" is an answer.** Empty quadrants mean they can be treated today.
5. **Read-back + reference number + warning.** These make the quote trustworthy.

## How Haider will probably try to break it

- Refusing to answer until the agent has identified itself properly
- Asking for things to be repeated or spelled out
- Long "let me pull that up…" pauses
- Answering several questions at once, or out of order
- Vague answers like "it depends on the plan"
- Asking "Are you a robot?"
- Talking over the agent
- Correcting a number during the read-back
- Saying "I can't find that member"

**Winning means:** the call feels natural, never gets stuck, never makes up data, and ends with correct JSON.

---

# PART 2: SYSTEM DESIGN (ARCHITECTURE)

## The big picture

Think of the agent as a person with **ears, a brain, a notepad, a calculator and a mouth**.

```
  Haider's phone
       ^  |
       |  v
 +-------------+
 | PHONE LINE  |  Twilio: dials the number, carries audio both ways
 +-------------+
       ^  |  audio
       |  v
 +----------------------- OUR SERVER (Python) ------------------------+
 |                                                                    |
 |  EARS (speech -> text)  -->  TURN DETECTOR ("has he finished?")    |
 |   Deepgram                          |                              |
 |                                     v                              |
 |                  BRAIN (AI model: Gemini, free)                    |
 |                  decides what to say next                          |
 |                     |                  ^                           |
 |      writes answers |                  | "what's still missing?"   |
 |                     v                  |                           |
 |            NOTEPAD / CHECKLIST (plain code)  <-- CALCULATOR        |
 |            which questions are answered,         (date math in     |
 |            which stage we're in                   code)            |
 |                     |                                              |
 |  MOUTH (text -> speech)  <--  NUMBER READER                        |
 |   Deepgram Aura                ("8-4... 1-5-5...")                 |
 +--------------------------------------------------------------------+
                     |  after the call ends
                     v
     AFTER-CALL CHECKER: rebuilds the JSON from the full transcript,
     validates it, puts null for anything missing
                     v
          Saved JSON + simple results web page
```

There's also a **practice ground**: a text-only fake "difficult rep" (several personalities) the agent can practice on for free. A scorecard marks how many fields it got right.

## The call as stages (like levels in a game)

```
Phone menu -> Hold (stay silent) -> Introduce clinic -> Identify patient
-> Money questions -> Quadrant history -> Paperwork rules -> D4910
-> Read-back (fix corrections) -> Close (ref #, name, warning) -> Hang up
```

The agent only moves to the next stage when the checklist says that stage is done.

## Key decisions and WHY

| Decision | Why |
|---|---|
| Ears -> brain -> mouth as separate parts (not one speech-to-speech AI) | Every step gives us text we can check. ID numbers can be verified, and we get a transcript to prove each answer. |
| Code decides the stage, not the AI | The AI can wander or skip questions. Code keeps the order fixed. Early answers get ticked off and are never asked again. |
| The AI never does maths | Code working out "02/04/2025 + 24 months" is always right. |
| The read-back is built from the notepad | It reads back what was actually recorded, not what the AI "remembers". |
| A second check after the call | It catches anything missed live. Read-back corrections always win. |
| Unanswered -> `null` | The PDF requires it. Never guess. |
| A special number reader | Voices often say IDs wrongly. We control how they're spoken, digit by digit. |
| Honest about being an AI | It's ethical, the PDF does it, and it defuses "are you a robot?" |

## Free tools

| Part | Tool | Cost |
|---|---|---|
| Voice framework | Pipecat (open source) | Free |
| Brain | Google Gemini Flash (AI Studio key) | Free tier, no card |
| Ears + mouth | Deepgram (Nova-3 + Aura) | Free $200 credit, no card |
| Server + checks | Python, FastAPI, Pydantic | Free |
| Public link for the phone service | Cloudflare Tunnel / ngrok | Free |
| Testing by voice | Browser mode (talk into your mic) | Free |
| Real phone call | Twilio trial | Free credit, WITH LIMITS |

### Two honest warnings about "free"

1. **Twilio's free trial** can only call phone numbers you've verified first. Every call also starts with a short "trial account" message, and the listener may need to press a key. Workaround: verify Haider's number ahead of time and tell him about the message. (Upgrading for about $20 removes both limits, but only if you ever choose to.)
2. **Speed.** The laptop is in Pakistan and Haider is in the US, so each reply could take an extra 0.3–0.6 seconds. A free option to try is GitHub Codespaces (a free US cloud computer, no card).

---

# OPEN QUESTIONS

1. How will the demo call happen? Will they give us Haider's phone number?
2. Do we already have Gemini and Deepgram API keys in a `.env` file?
3. Is anything here unclear?
