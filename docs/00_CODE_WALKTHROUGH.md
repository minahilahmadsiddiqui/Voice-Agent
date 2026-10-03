# Code Walkthrough — Every File, Simply

Read with `00_ARCHITECTURE_SIMPLE.md` open next to it.

## The 3 layers

```
1. PHONE / BROWSER LAYER   (how sound gets in and out)
   main.py, telephony.py, browser.py, ivr_test.py

2. VOICE PIPELINE LAYER    (ears → brain → mouth, in real time)
   pipeline.py, gemini_pool_llm.py, model_pool.py, speech_format.py

3. BRAIN LOGIC LAYER       (what to ask, what's missing, what's true)  ← the heart
   fields.py, state.py, callflow/tools.py, callflow/prompts.py, callflow/nodes.py

4. AFTER THE CALL          (check, export, save)
   results.py, postcall.py, export.py, schema.py, storage.py
```

Layer 3 knows **nothing about audio**. That's why the same brain runs on a phone call, in the browser, and in the text simulator.

---

## Layer 1 — Phone / browser

| File | What it does | One-line analogy |
|---|---|---|
| `app/main.py` | Starts the web server. Has the addresses Twilio talks to: `/call` (start a call), `/ws` (live call audio), `/twilio/status`, `/twilio/recording` | The building's reception desk |
| `app/telephony.py` | Asks Twilio to dial a number, and tells Twilio "send the call audio to our `/ws` address". Also turns on call recording | The person who dials the phone |
| `app/browser.py` | Browser mode: talk to the agent through Chrome's mic (WebRTC), no phone needed | A practice phone on your desk |
| `app/ivr_test.py` | A fake insurance phone menu (for testing the keypad / hold handling on a real call) | A training dummy |
| `scripts/place_call.py` | Command you run to start a real call | The "call" button |

## Layer 2 — Voice pipeline

| File | What it does |
|---|---|
| `app/pipeline.py` | Builds the Pipecat pipeline: **mic → VAD (is someone talking?) → Deepgram ears → Gemini brain → SpeechGate → Deepgram mouth → speaker**. Also: keeps the call alive 30 min on hold, says "Hello?" if nobody talks after pickup, and the safety net that un-mutes if the AI misses that a person is back |
| `app/model_pool.py` | The free-tier trick: a list of Gemini models, each with its own limit. If one says "too many requests", it rests and the next one is used |
| `app/gemini_pool_llm.py` | Plugs the pool into Pipecat, so the switch happens **inside the same turn** (no silence) |
| `app/speech_format.py` | Turns data into speakable words: `84-1552037` → "eight four, one five five, two zero three seven"; `2027-02-04` → "February fourth, twenty twenty-seven"; `MDB...` → "M as in Mary, D as in David..." |

`SpeechGate` (inside pipeline.py): while on hold, anything the AI tries to say is thrown away. A guarantee, not a hope. It is also the "mouth door" the code uses to say its own lines instantly (`speak()`).

Other helpers inside `pipeline.py`:
- `StallAck` — hears "let me look" → says "Sure, take your time." at once (no AI call); hears "let me put you on hold" → "Sure, I'll hold." and mutes.
- `say()` — the code speaks a scripted line (next question, intro, read-back).
- `filler_if_slow()` — "Got it." if the reply takes over 1.3 s.
- `watchdog()` — if nothing was said 6 s after Haider stopped, asks the next question.
- `force_human_if_missed()` — a person is talking but the AI still thinks it's the phone menu → switch to talking.
- `REPLY GAP` log lines — how long each reply took.

## Layer 3 — The brain logic (most important — know this well)

| File | What it does |
|---|---|
| `app/fields.py` | **The question list.** Every field the call must answer: path (`srp.deductible.amount`), type (money/percent/date/yes-no), which stage asks it, and how to ask it. Change the list here → prompts, tools, read-back and scoring all follow |
| `app/state.py` | **The checklist (CallState).** For each field: value, status (answered / refused / unknown / corrected / not_asked), the rep's exact quote, which transcript turn. Decides what's missing and the next stage. Converts "$1,340" → 1340, "03/01/2024" → a date. `next_line()` = the next thing the code says (question, intro, read-back). `quote_is_grounded()` = rejects made-up quotes. `sanity_hint()` = flags odd numbers to confirm |
| `app/eligibility.py` | **Date math in code:** paid 2025-02-04 + 24 months → eligible 2027-02-04 (or "now" if never paid / already passed) |
| `app/callflow/tools.py` | **The only way the AI can change anything.** Tools: `press_digits`, `on_hold`, `human_detected`, `record_fields`, `record_quadrant`, `mark_unresolved`, `member_not_found`, `readback_done`, `end_call`. Each tool returns: result + next stage (decided by code) + speak now or stay quiet. Also says which stage gets which tools |
| `app/callflow/prompts.py` | What we tell the AI: one **role prompt** (who you are, how to speak, never guess) + a short **stage prompt** (what's captured, what's still missing) |
| `app/callflow/nodes.py` | Translates our stages + tools into Pipecat Flows "nodes" for the live call |

### The stages
`ivr → hold → verify → benefits → history → rules → maintenance → readback → close → end`

Stages already fully answered are **skipped** (if the rep volunteered everything early).

## Layer 4 — After the call

| File | What it does |
|---|---|
| `app/results.py` | Runs at hang-up: post-call check → mark never-asked fields `not_asked` → write files → save to database |
| `app/postcall.py` | A second AI pass reads the **full transcript** calmly and compares with what was captured live. Agree → confirmed. Live missed it → fill in. Disagree → `needs_review`. Read-back corrections always win |
| `app/export.py` | Writes `reference.json` (**exactly the PDF's shape**) and `sourced.json` (every field + status + quote + turn) |
| `app/schema.py` | The JSON shape rules (Pydantic) — output is always valid |
| `app/storage.py` | Saves every call in a small SQLite database |

Output folder per call: `calls/<call id>/` → `reference.json`, `sourced.json`, `transcript`, `discrepancies.json`, `events.json`.

## Testing tools

| File / folder | What it does |
|---|---|
| `sim/run.py` | Text simulator: plays a full call — scripted phone menu + hold, then an AI playing the rep — and **scores** the JSON against the expected answer |
| `sim/rep.py` + `sim/personas/*.yaml` | The fake rep and their personality (cooperative, difficult, ...) |
| `sim/text_agent.py` | Runs our exact brain (same prompts, tools, state) without audio |
| `sim/scorecard.py` | Field-by-field accuracy |
| `sim/ground_truth/reference_call.json` | The PDF's JSON — the "answer key" |
| `tests/` | Automatic tests (`pytest`). E.g. `test_reference_call.py` replays the PDF's call and must produce the PDF's JSON exactly; `test_adversarial.py` covers tricky Haider moves |
| `scenarios/lana_kane.yaml` | The call's inputs: practice, provider, tax ID, NPI, patient |

## How to run things

```powershell
# automatic tests
.venv\Scripts\python -m pytest -q

# text simulator (AI plays the rep)
.venv\Scripts\python -m sim.run --persona cooperative

# browser voice test (you play the rep)
.venv\Scripts\python -m app.main
#   then open http://localhost:8765/client/  and click Connect
```
