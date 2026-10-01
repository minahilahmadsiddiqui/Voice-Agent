# 6-Day Plan — SRP Benefits Verification Voice Agent

Six days from start to demo. **Days 1–4 build the agent. Days 5–6 are real-call testing, polish and demo preparation.** Live testing gets two full days because it decides the ranking: the agent has to hold up when a real person makes the call hard.

| Day | Theme | End-of-day proof |
|---|---|---|
| **1** | Accounts, setup, and the risky pieces | The agent calls your phone, speaks, hears you, and sends keypad tones |
| **2** | The agent's brain | A full call against the text simulator produces valid JSON |
| **3** | Difficult personas + US deployment | All personas pass in text mode; the server runs in the US |
| **4** | Turn-taking + viewer + first live calls | 3 live calls work; the viewer shows results — **feature complete** |
| **5** | Live-call round 2 + docs | Many adversarial live calls; README and decision log done |
| **6** | Rehearsal, backup, freeze | Backup recording, rehearsed demo, `v1.0` tagged |

> **If you fall behind:** the cut list at the bottom says what to drop first. Never cut live testing.

---

## Day 1 — Accounts, setup, and the risky pieces

**Goal:** remove every infrastructure risk before building any agent logic.

### Morning — accounts and keys (free first)
- [ ] **Google AI Studio** API key (free): the brain (`GOOGLE_API_KEY`)
- [ ] **Deepgram** account and API key (free credit): ears and mouth (`DEEPGRAM_API_KEY`)
- [ ] With just these two: browser mode (`http://localhost:8765/client/`) and the text simulator work
- [ ] **Twilio free trial**: one US number; verify your own mobile; Geo Permissions → United States (+ Pakistan for your mobile). Upgrade (one-time top-up, not monthly) only before the practice calls with friends and the demo, to remove the trial announcement
- [ ] Optional: Anthropic key (Claude, `LLM_PROVIDER=anthropic`) to compare against Gemini; Cartesia to compare voices
- [ ] Create an **ngrok** account and install the auth token (phone calls only)
- [ ] Create a **GitHub** repo and push the planning docs
- [ ] **Email Amplify** your questions: Will Haider simulate a phone menu or hold? Will they provide the patient and practice details? Which US number will Haider answer on? Is recording OK?

### Midday — project setup
- [x] Set up the repo layout from IMPLEMENTATION_PLAN.md §3
- [x] `pyproject.toml` with Pipecat 1.12 (Flows built in), `fastapi`, `uvicorn`, `pydantic`, `twilio`, `python-dotenv`, `pyyaml`
- [x] Write `.env.example`, keep `.env` out of git, and write `config.py` to load both
- [x] Write `scenarios/lana_kane.yaml` with the practice, provider, patient and target phone number

### Afternoon — verify the three risks
- [x] *Code:* `POST /call` and `scripts/place_call.py` have Twilio dial a number and stream the audio to `/ws`
- [x] *Code:* basic pipeline Deepgram → Haiku 4.5 → Cartesia with interruptions on (`--mode chat`)
- [x] *Code:* fake payer menu at `/ivr/voice` (menu → tax ID + `#` → hold music → rep greeting); the agent keys digits with a `press_digits` tool. Pipecat already plays keypad tones as audio on Twilio, so no separate `dtmf.py` is needed
- [ ] **Risk 1: outbound call.** Run `place_call.py --to <your phone>` and have a two-minute free conversation with it
- [ ] **Risk 2: keypad tones.** Run `place_call.py --ivr`; `/ivr/log` must show `"match": true` for the tax ID
- [ ] **Risk 3: calling permissions.** Place a test call to a real US phone (a friend's US number, or the Twilio Dev Phone on a US Twilio number) and check the audio quality
- [ ] Turn on Twilio recording and confirm the recording URL arrives

### Evening — first building blocks
- [x] Write `speech_format.py` plus unit tests (tax ID, NPI, member ID, DOB, phone, money)
- [ ] **TTS number test:** run `place_call.py --to <your phone> --mode tts_test --voice <id>` for each shortlisted Cartesia voice; log the winner in `DECISION_LOG.md`
- [x] Draft `schema.py` (the Pydantic output model) from the reference JSON

**Done when:** the agent rings your phone, talks naturally, sends keypad tones that a Twilio test menu accepts, and a recording is saved.

---

## Day 2 — The agent's brain

**Goal:** the full call flow works end to end in text mode and produces valid JSON.

### Morning — state and tools
- [x] `state.py`: `CallState` with `Captured` fields (value / status / quote / turn) and a `missing()` list for each stage; typed coercion of the rep's answers ("$1,340" → 1340, "03/01/2024" → date)
- [x] `eligibility.py`: next-eligible date math plus unit tests (24 months date to date, month-end clamping, "open now")
- [x] `callflow/tools.py`: `record_fields` (several at once), `record_quadrant`, `mark_unresolved`, `readback_done` (corrections), `press_digits`, `on_hold`, `human_detected`, `member_not_found`, `end_call`

### Midday — call stages
- [x] `callflow/nodes.py`: Pipecat Flows nodes for ivr, hold, verify, benefits, history, rules, maintenance, readback, close, end
- [x] `callflow/prompts.py`: one role prompt (polite, brief, honest that it's automated, never guesses) plus a short task prompt per stage built from `state.missing()`
- [x] Transitions decided in code: move on when a stage's checklist is resolved; skip stages already answered out of order
- [x] Hold: `SpeechGate` drops anything the LLM says on hold; greeting detection; **Pipecat's 5-minute idle hang-up raised to 30 minutes**
- [x] Read-back: generated from the state (not the LLM's memory), in spoken form

### Afternoon — simulator
- [x] `sim/text_agent.py` + `sim/rep.py` + `sim/run.py`: the same brain against a scripted phone menu and hold, then an LLM rep, in **text mode**
- [x] Persona 1 **Cooperative** (the reference call) with its ground-truth file
- [x] `sim/scorecard.py`: field-by-field accuracy against ground truth, plus behaviour checks (menu, silence on hold, pauses, read-back)
- [x] Offline: the reference call replayed through the real tools reproduces **the PDF's JSON exactly**; a scripted run through the simulator scores **100%**
- [ ] With an API key: `python -m sim.run --persona cooperative --runs 3` until the LLM run scores **100%**

### Evening — after the call
- [x] `postcall.py`: transcript → strong LLM (Opus 5.5) → fields with quotes; reconcile with the live state (read-back corrections win; conflicts flagged `needs_review`); dates recomputed in code
- [x] `export.py`: the result in **exactly the reference PDF's JSON shape**, next to the sourced version
- [x] Measure `hold_sec` (call answered → first human greeting) and `duration_sec` (answered → hang-up)
- [x] `storage.py`: SQLite tables `calls`, `fields`, `turns`; per-call folder `calls/<CallSid>/`
- [ ] With keys: one real phone call (`place_call.py --to <your phone>`) where you play the cooperative rep yourself; check the JSON

**Done when:** a text-mode run and one real call both finish with complete, valid JSON that matches the reference.

---

## Day 3 — Difficult personas + US deployment

**Goal:** the agent's logic holds up against the likely tactics, and the server runs where response times are low.

### Morning — difficult personas
- [ ] Add personas with ground truth: **Strict authenticator, Hedger, Corrector, Rapid-fire, Robot-challenger, Stonewaller, Long pauses**
- [ ] Run all 8; fix the prompts, transitions and tools where they fail

### Midday — model choice
- [ ] **LLM comparison:** 5 personas × 2 fast models; log the winner (accuracy + response time) in `DECISION_LOG.md`
- [ ] Add Deepgram keyterms from the scenario (names, IDs, dental codes)

### Afternoon — US deployment
- [ ] Dockerfile; deploy to a US-East VM (Fly.io / Render / a VPS); point the Twilio webhooks at it
- [ ] Place one call from the deployed server; measure response times with Pipecat metrics (target a median under 1.2 s)

### Evening — regression
- [ ] Re-run all 8 personas; target **≥ 95%** field accuracy
- [ ] Write a **rep script** for friends to use on Days 4–5 (the tactics from PROBLEM_STATEMENT.md §5, plus a hidden answer key)

**Done when:** all personas score ≥ 95% in text mode and a call from the US server works.

---

## Day 4 — Turn-taking, viewer, first live calls (feature complete)

**Goal:** the agent sounds natural on real calls, and every feature exists.

### Morning — turn-taking
- [ ] Tune the VAD and Smart Turn settings; test end-of-turn waits of 0.5 / 0.8 / 1.2 s against "let me pull that up" pauses
- [ ] Make sure "Sure, take your time" is said only once per pause, with one "Still there?" after about 20 s
- [ ] Check the agent stops speaking when interrupted and doesn't repeat itself afterward
- [ ] Test hold music by playing music into the phone for 2–3 minutes; the agent must stay silent and then greet the rep

### Midday — results viewer
- [ ] `/calls` list page and `/calls/{id}` detail page
- [ ] Summary card, colour-coded JSON (hover shows the rep's quote), quadrant grid, highlighted transcript, recording player, response-time stats
- [ ] A CLI command or simple form to place a call: `python -m app.call --scenario lana_kane --to +1...`

### Afternoon — live calls, round 1
- [ ] **3 full live calls** with a friend reading the rep script (a phone menu, hold, a correction, at least one hard tactic per call)
- [ ] Check each call's JSON against the answer key; list every failure

### Evening — fixes
- [ ] Fix what the live calls exposed (mishearing, timing, awkward wording)
- [ ] Turn each failure into a simulator persona or test so it stays fixed

**Done when:** 3 live calls finish with correct JSON, the viewer shows them, and nothing is left to build. **Feature complete.**

---

## Day 5 — Live-call round 2 + docs

**Goal:** make the agent reliable against a hard rep, and document it for reviewers.

### Morning — adversarial live calls
- [ ] **At least 6 live calls**, ideally with 2–3 different people and accents, including at least one to a real **US** phone, since that's the line Haider will answer on
- [ ] Each call plays Haider at his hardest: NPI challenge, "are you a robot?", hedging, answers out of order, long silences, a mid-call hold, a read-back correction, and trying to end the call early
- [ ] Record accuracy and response times for each call in a results table

### Midday — fixes
- [ ] Fix the top 3 failures from this morning's calls; re-run the simulator suite to check nothing broke
- [ ] 2 more live calls to confirm the fixes

### Afternoon — docs
- [ ] **README.md:** the problem in 3 lines, an architecture diagram, setup in about 5 commands, how to run the simulator, design decisions, results (scorecard + live-call table + response times), known limits and next steps
- [ ] Finish `DECISION_LOG.md` (LLM, TTS voice, turn settings, hosting)
- [ ] Code cleanup, type hints, key unit tests passing; push to GitHub

**Done when:** at least 8 live calls are logged with results, the README is complete, and the repo is clean.

---

## Day 6 — Rehearsal, backup, freeze

**Goal:** the demo can't fail silently.

### Morning — dress rehearsal
- [ ] **Full dress rehearsal:** a friend plays Haider at his hardest, from start to finish, over the real setup
- [ ] Fix only what's critical; no new features

### Midday — backup and demo script
- [ ] Record the screen and audio of the best full call as the **backup demo**
- [ ] Prepare a 5-minute demo script: the problem → the architecture → a live call → the viewer → the scorecard + live results → what we'd build next

### Afternoon — freeze
- [ ] Pre-demo checklist: Twilio balance, API credits, server up, Haider's number in the scenario, recording on
- [ ] Tag release `v1.0` and push; after this only critical fixes
- [ ] One last test call from the frozen build

**Done when:** a stranger can clone the repo, follow the README, and place a call; you have a backup recording; the demo script is rehearsed.

---

## Cut list (if you fall behind, drop in this order)

1. The OpenAI model comparison: just use Haiku 4.5
2. The viewer's extras (response-time stats, transcript highlighting); keep the JSON, transcript and recording
3. The Stonewaller and Rapid-fire personas (keep Cooperative, Strict, Hedger, Corrector, Long pauses, Robot-challenger)
4. Docker: deploy with a plain `uvicorn` process on the VM
5. The TTS voice comparison: pick one voice and move on

**Never cut:** the read-back stage, explicit `null`s for unanswered questions, hold handling, live-call testing, the backup recording.
