# Architecture — Explained Simply

## 1. The big idea in one picture

A voice agent is like a person on the phone. It needs **4 body parts**:

| Body part | Job | Tool we use | Free? |
|---|---|---|---|
| 📞 **Phone line** | Makes the real call, carries the sound | **Twilio** | ✅ Free trial credit |
| 👂 **Ears** | Turns Haider's voice into text | **Deepgram Nova-3** (Speech-to-Text) | ✅ Free credit on signup |
| 🧠 **Brain** | Understands what Haider said and saves the facts | **Google Gemini Flash-Lite** (a pool of free models) | ✅ Free tier |
| 👄 **Mouth** | Turns the agent's text into a voice | **Deepgram Aura-2** (Text-to-Speech) | ✅ Same free Deepgram credit |

And one **🦴 skeleton** that connects them all in real time: **Pipecat** (free, open source).

---

## 2. The whole system (diagram)

```
                         YOUR LAPTOP
   ┌───────────────────────────────────────────────────────────┐
   │                                                           │
   │  ① You run:  python scripts/place_call.py                 │
   │       │                                                   │
   │       ▼                                                   │
   │  FastAPI server (our app) ── asks Twilio: "call Haider" ──┼──► TWILIO ──► 📱 Haider's phone rings
   │                                                           │                    │
   │                                                           │      Haider answers│
   │                                                           │                    ▼
   │  ② Live sound flows both ways  ◄── ngrok tunnel ◄─────────┼──── TWILIO streams the call audio
   │                                                           │
   │  ┌─────────────── PIPECAT PIPELINE ─────────────────┐     │
   │  │                                                  │     │
   │  │  Haider's voice                                  │     │
   │  │      ▼                                           │     │
   │  │  Silero VAD + Smart Turn  "is he talking?        │     │
   │  │      ▼                     is he finished?"      │     │
   │  │  👂 Deepgram STT  → text: "Fifty dollars, met"   │     │
   │  │      ▼                                           │     │
   │  │  🧠 Gemini  ←→  📋 CHECKLIST (CallState)          │     │
   │  │      │          saves: deductible = $50, met     │     │
   │  │      │          + Haider's exact words + turn #  │     │
   │  │      ▼                                           │     │
   │  │  🔇 SpeechGate  (blocks talking while on hold)   │     │
   │  │      ▼                                           │     │
   │  │  👄 Deepgram TTS → "Thanks. And the annual max?" │     │
   │  │      ▼                                           │     │
   │  └──── back to Twilio → Haider hears it ────────────┘     │
   │                                                           │
   │  ③ Call ends → Post-call check (Gemini re-reads           │
   │     the whole transcript, catches anything missed)        │
   │       ▼                                                   │
   │  ④ OUTPUT:  reference.json  (same shape as the PDF)       │
   │             sourced.json    (every field + quote + turn)  │
   │             SQLite database (history of all calls)        │
   └───────────────────────────────────────────────────────────┘
```

---

## 3. One sentence, step by step (what happens in ~1 second)

1. Haider says: *"Fifty dollars individual, and it's met."*
2. **Twilio** sends that sound to our laptop (through **ngrok**).
3. **Silero VAD** notices: someone is speaking. **Smart Turn** notices: he finished.
4. **Deepgram** writes it as text.
5. **Gemini** reads it and calls a **tool**: `record(deductible.amount = 50, met = true, quote = "Fifty dollars...")`.
6. Our **code** saves it in the **checklist**, and sees what's still missing: *annual max*.
7. The **code** picks the next question from its list: *"And the annual maximum, and how much is remaining?"* (no second AI call → faster)
8. **Deepgram Aura** turns it into voice → Twilio → Haider hears it.

---

## 4. The smartest part: the CHECKLIST (code is the boss, not the AI)

AI models sometimes **forget, skip, or make things up**. So we don't let the AI run the call alone.

- `app/fields.py` = the **list of every question** that must be answered.
- `app/state.py` = the **checklist** that tracks each answer: value, status, Haider's exact words, which turn.
- **The code decides** what's missing, moves to the next stage, and **asks the next question itself**. The AI just *listens and saves*. (Also: the code says the introduction and the read-back.)
- Every saved quote is **checked against what Haider really said**. A made-up quote is rejected.
- The AI can only save a fact by **calling a tool with a quote**. No quote → nothing saved.
- Not answered → `null`. **Never guessed.**
- **Date math** (next eligible 02/04/2027) is done **by code**, not the AI. AI is bad at math.
- **Read-back** is built **from the checklist**, not from the AI's memory.

### The stages (one at a time, like chapters)

```
ivr → hold → verify → benefits → history → rules → maintenance → readback → close → end
menu   wait   who we   coverage   which      paperwork  D4910        repeat     ref #    hang
              are +    deductible quadrants  downgrade  follow-up    all +      name     up
              patient  max, freq  paid when  per visit  cleaning     fix        disclaimer
```

Each stage gives the AI:
- a **short instruction** ("you still need: annual max, frequency")
- **only the tools that stage needs**

If Haider answers something early (e.g. gives the deductible while verifying), it's saved — and that question is **skipped** later. No repeating.

---

## 5. Every tool, and WHY we picked it

| Tool | What it is | Why this one | Free? |
|---|---|---|---|
| **Python 3.13** | Programming language | Every voice AI tool supports it best | ✅ |
| **Pipecat** | Framework that connects ears → brain → mouth in real time | Built exactly for phone voice agents. Handles interruptions, streaming, Twilio. Open source | ✅ |
| **Pipecat Flows** | Pipecat add-on for **stages** | Our call has clear stages; Flows gives each stage its own prompt + tools | ✅ |
| **Twilio** | Phone company for code | Most popular; Pipecat supports it directly; free trial can call verified numbers | ✅ trial (~$15 credit) |
| **ngrok** | Gives your laptop a public web address | Twilio is on the internet; your laptop is not. ngrok opens a safe tunnel | ✅ free account |
| **Deepgram Nova-3** | Speech-to-Text (ears) | Very fast, good on phone audio, can be told special words ("D4341", "quadrant") | ✅ free signup credit |
| **Deepgram Aura-2** | Text-to-Speech (mouth) | Fast, natural, uses the **same** free Deepgram credit — one key for ears + mouth | ✅ |
| **Google Gemini Flash-Lite** (pool of 4 models) | LLM (brain) | Good at tool calling, **free tier**. Each model has its own limit (Flash-Lite 15/min; Flash only 20/day), so a pool switches model when one is busy or slow | ✅ free tier |
| **Groq** (optional) | LLM that plays the fake Haider in tests | Free, very fast; keeps tests from using the agent's Gemini quota | ✅ free |
| **Silero VAD** | Detects "someone is speaking" | Runs on your laptop, tiny, free. Stops music/silence being treated as words | ✅ local |
| **Smart Turn** | Detects "he finished his sentence" | So "Let me look…" isn't treated as the end of his answer | ✅ local |
| **FastAPI + Uvicorn** | Small web server | Twilio needs a web address to send audio to | ✅ |
| **Pydantic** | Checks the JSON shape | Output is always valid and matches the PDF format | ✅ |
| **SQLite** | Tiny database in one file | Stores every call's results, no setup | ✅ |
| **pytest** | Runs automatic tests | Proves the code works after every change | ✅ |
| **Text simulator** (`sim/`) | A fake Haider (cooperative, skeptical, rushed, hold-and-fix), played by an AI, in text | Test 100 calls fast, without voice or phone costs | ✅ |
| **Browser mode** | Talk to the agent in Chrome | Practise voice calls with **no phone and no Twilio** | ✅ |

Optional, NOT needed (paid): Claude (brain), Cartesia (mouth). The code can switch to them with one setting, but we stay free.

---

## 6. Big design choices (great interview answers)

**Q: Why ears → brain → mouth (3 separate tools) instead of one "speech-to-speech" AI?**
A: Control. With text in the middle we get: exact transcripts (needed for quotes), reliable tool calling, correct numbers, and we can block talking on hold. Speech-to-speech models are harder to control and to audit.

**Q: Why does code control the stages instead of the AI?**
A: The AI can forget or skip questions. A checklist in code guarantees nothing is missed, nothing is asked twice, and the order never drifts.

**Q: How do you stop it from making things up?**
A: Facts can only be saved through a tool with the rep's exact quote. Missing answers become `null`. Math is done in code. Read-back is generated from saved data.

**Q: What if it's on hold for 10 minutes?**
A: The SpeechGate blocks all talking on hold. Pipecat's default 5-minute "idle hang-up" is raised to 30 minutes.

**Q: What if the AI mishears something live?**
A: Two safety nets: (1) read-back — Haider corrects it on the call; (2) after the call a second pass re-reads the full transcript and flags conflicts as `needs_review`.

**Q: How did you test it?**
A: Automatic tests (replays the PDF's call and must produce the PDF's exact JSON), a text simulator with tough fake reps, browser voice tests, then real phone calls.

---

## 7. Free accounts we need to create

| # | Account | What we get | Card needed? |
|---|---|---|---|
| 1 | Google AI Studio | `GOOGLE_API_KEY` (brain) | No |
| 2 | Deepgram | `DEEPGRAM_API_KEY` (ears + mouth) | No |
| 3 | Twilio | Account SID, Auth Token, a free US phone number | No (trial) |
| 4 | ngrok | Auth token + free public address | No |

Trial limits to remember:
- Twilio trial calls only **verified** numbers (Haider must verify his once).
- Twilio trial plays a short "trial account" message first; Haider presses a key.
- Gemini free tier: Flash-Lite 15 requests/min; Flash models only 20/day. Limits reset at 12:00 noon Pakistan time. Don't burn them with many tests on demo morning.
