# SRP Voice Agent

An outbound voice agent that phones a dental insurance rep, verifies the practice and patient, and comes back with a structured, sourced record of Scaling and Root Planing (SRP) benefits.

- **Design (1 page): [docs/DESIGN.md](docs/DESIGN.md)** · Decisions with evidence: [docs/DECISION_LOG.md](docs/DECISION_LOG.md)
- What we're solving: [PROBLEM_STATEMENT.md](PROBLEM_STATEMENT.md) · Demo steps: [docs/DEMO_RUNBOOK.md](docs/DEMO_RUNBOOK.md)
- Original plans (historical): [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md), [6_DAY_PLAN.md](6_DAY_PLAN.md)

**Stack (all free tiers):** Pipecat 1.12 (+ Flows) · Deepgram Nova-3 (ears) + Aura-2 (mouth) · Gemini Flash-Lite model pool (brain; Groq or Claude are one setting) · Twilio (phone calls only) · FastAPI · Pydantic · SQLite

## Free setup: two keys, no phone needed

| Key | Where | Cost |
|---|---|---|
| `GOOGLE_API_KEY` | [aistudio.google.com](https://aistudio.google.com) → Get API key | Free tier |
| `DEEPGRAM_API_KEY` | [console.deepgram.com](https://console.deepgram.com) → API Keys | Free starting credit (covers both ears and mouth) |
| `GROQ_API_KEY` (optional) | [console.groq.com](https://console.groq.com/keys) | Free; plays the simulated rep so tests don't use the agent's Gemini quota |

With just these two you can:
- **Talk to the agent in your browser:** run `python -m app.main`, open http://localhost:8765/client/, click Connect, and play the insurance rep.
- **Run the text simulator:** `python -m sim.run`

Twilio is only needed to place real phone calls. Its free trial works for calls to your own verified phone; a paid top-up only removes the trial announcement before the demo. To use Claude instead of Gemini, set `LLM_PROVIDER=anthropic` and `ANTHROPIC_API_KEY`.

---

## How it works

1. **The LLM listens, the code drives.** `app/fields.py` lists every field the call has to resolve and the question for it. `CallState` tracks each one's value, status, the rep's exact words and the transcript turn. The LLM understands the rep and records facts through tools; the **code** picks the stage and speaks the next question, the introduction and the read-back (one LLM call per turn, and the order can't drift).
2. **Stages** (`app/callflow/`): phone menu → hold → verify → benefits → claim history by quadrant → rules → D4910 → read-back → close. Each stage has a short prompt listing what's already captured and what's still missing, plus only the tools that stage needs.
3. **Nothing is guessed.** Facts go in only through tools, with a quote, and the quote must appear in what the rep actually said (`CallState.quote_is_grounded`). Odd numbers (8%, cents, remaining > max) must be confirmed with the rep. Anything unanswered comes out as an explicit `null` with a reason.
4. **Code does the maths.** Next-eligible dates are computed in code, then confirmed with the rep. The read-back is generated from the state, not from the LLM's memory.
5. **Hold-proof and phone-polite.** A `SpeechGate` drops anything the LLM tries to say on hold; Pipecat's 5-minute idle hang-up is raised to 30 minutes. "Let me look" gets an instant "Sure, take your time." from code; "let me put you on hold" mutes the agent until the rep is back. Only 2+ real words interrupt the agent, and a noise never makes it say "please repeat".
6. **Free-tier proof.** The brain is a pool of Gemini models, each with its own free limit; a rate-limited, overloaded or slow (no first token in 2.5 s) model is skipped inside the same turn. A short "Got it." covers slow replies and a watchdog asks the next question if the LLM returns nothing.
7. **After the call,** a second model pass re-reads the transcript and reconciles with the live capture. Read-back corrections win, and conflicts are flagged `needs_review`.
8. **Two outputs:** `reference.json` is in exactly the shape of Amplify's reference PDF; `sourced.json` has every field with its status, quote and turn.

The brain (`app/callflow/tools.py`, `prompts.py`, `app/state.py`) knows nothing about audio. The same code runs on a live call (through the Pipecat Flows adapter in `nodes.py`) and in the text simulator (`sim/`), so the tests exercise exactly what runs on the phone.

## Setup (Windows / PowerShell)

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
copy .env.example .env      # then fill in the keys
.\.venv\Scripts\python.exe -m pytest -q
```

## Talk to it in the browser (free)

```powershell
.\.venv\Scripts\python.exe -m app.main
# open http://localhost:8765/client/  ->  Connect  ->  allow the microphone
```

The agent waits for you to speak first, just as on a phone call. Start with a phone-menu line ("For benefits, say benefits or press one") or go straight to the rep ("Thanks for holding, this is Denise, can I get your name and the practice?"). Results are saved to `calls/web-<timestamp>/` when you disconnect. Use headphones so the agent doesn't hear itself.

## Test in text mode (needs the LLM key only)

```powershell
.\.venv\Scripts\python.exe -m sim.run --persona cooperative            # prints the conversation + scorecard
.\.venv\Scripts\python.exe -m sim.run --persona cooperative --runs 3 --quiet
.\.venv\Scripts\python.exe -m sim.run --agent-model claude-haiku-4-5-20251001 --no-postcall
```

Personas: `cooperative` (the PDF call), `skeptical` (robot question, demands tax ID + NPI, hedges), `rushed` (batched, out-of-order answers, tries to end early), `hold_and_fix` (mid-call hold, wrong quadrant then corrected). With a Groq key the simulated rep runs on Groq (`--rep-model qwen/qwen3.8-27b` plays the rep most reliably), so it doesn't use the agent's Gemini quota.

The simulator plays a scripted phone menu and hold queue, then an LLM plays the rep from `sim/personas/<name>.yaml`. The scorecard compares the output with `sim/ground_truth/` field by field. It also checks behaviour: menu navigation, silence on hold, no new questions during "let me look" pauses, read-back done, and call completed. It reports accuracy both before and after the post-call pass.

## Place a real call

Three terminals:

```powershell
# 1. Tunnel so Twilio can reach your machine (free static domain = PUBLIC_URL in .env)
ngrok http 8765 --url=https://YOUR-DOMAIN.ngrok-free.app

# 2. The server
.\.venv\Scripts\python.exe -m app.main

# 3. Place a call
.\.venv\Scripts\python.exe scripts\place_call.py --to +1XXXXXXXXXX                  # THE verification call
.\.venv\Scripts\python.exe scripts\place_call.py --to +1XXXXXXXXXX --mode chat      # free chat
.\.venv\Scripts\python.exe scripts\place_call.py --to +1XXXXXXXXXX --mode tts_test  # read IDs aloud
.\.venv\Scripts\python.exe scripts\place_call.py --ivr --mode ivr_test              # fake payer menu
```

| Mode | What it does |
|---|---|
| `verify` (default) | The full benefits verification call |
| `chat` | Free chat: phone line, latency, interrupting the agent |
| `tts_test` | Reads the tax ID, NPI, member ID, DOB and amounts aloud. Try `--voice <id>` for each candidate |
| `ivr_test` | Answers a phone menu by voice, sends **keypad tones** for the tax ID, stays silent on hold, greets the rep |

`--ivr` calls `TWILIO_IVR_TEST_NUMBER`. You can combine it with `--mode verify` to run the full call against the fake menu.

### The fake payer menu

1. Buy a second Twilio number and put it in `TWILIO_IVR_TEST_NUMBER`.
2. In the Twilio console, set that number's **"A call comes in"** webhook to `POST {PUBLIC_URL}/ivr/voice`.
3. The menu asks for "benefits", then the tax ID + `#`, plays hold music, then "Denise" greets the agent.
4. `{PUBLIC_URL}/ivr/log` shows what the menu received. `"match": true` on the `tax_id` step means **keypad tones work**.

## Outputs

Each call (live or simulated) writes `calls/<CallSid>/`:

| File | Contents |
|---|---|
| `reference.json` | The result in the reference PDF's shape |
| `sourced.json` | Every field: value, status (`answered` / `refused` / `unknown` / `corrected_on_readback` / `needs_review`), quote, turn, source |
| `reference_live_only.json` | The result before the post-call pass, to show what reconciliation changed |
| `discrepancies.json` | Where live capture and post-call extraction disagreed |
| `transcript.txt` | Numbered turns (quotes point to these numbers) |
| `events.json` | Stage changes, tool calls and timings |
| `score.json` | Simulator only: scorecard and behaviour checks |

Everything also goes into `calls/calls.db` (SQLite: `calls`, `fields`, `turns`). While the server runs,
**http://localhost:8765/calls/latest** shows the latest result and `/calls/latest/sourced` every field with its quote plus the transcript.

## Layout

```
app/
  fields.py         The checklist: every field, its stage, type and question
  state.py          CallState: captured values, transcript, stage logic, read-back script
  callflow/
    tools.py        Tools + which stage offers them; transitions decided here
    prompts.py      Role prompt + per-stage task prompts built from the state
    nodes.py        Pipecat Flows adapter (live calls)
  pipeline.py       Pipecat pipeline per call (verify + test modes), SpeechGate
  postcall.py       Transcript re-extraction (second model pass) + reconciliation
  model_pool.py     Free-tier model pool: rest a model on 429/503, pick the next
  gemini_pool_llm.py  Pipecat Gemini service backed by the pool (switches inside a turn)
  export.py         reference.json (PDF shape) + sourced.json
  results.py        End-of-call: post-call pass, files, database
  storage.py        SQLite
  eligibility.py    Next-eligible date math
  speech_format.py  IDs / dates / money -> speakable text
  schema.py         Pydantic output model
  telephony.py      Twilio outbound call + TwiML
  ivr_test.py       Fake payer phone menu for testing
  main.py           FastAPI: /call, /ws (Twilio media), /twilio/* callbacks, /ivr/*
sim/                Text-mode simulator: agent, rep, personas, ground truth, scorecard
scenarios/          Practice + patient + payer details per call
scripts/            CLI helpers
tests/              64 unit tests, incl. a replay of the reference call that must reproduce the PDF's JSON exactly
docs/               Design, decision log, demo runbook, interview prep, simple explanations (00_*)
```
