# Decision Log

One line per decision: what we chose, and the evidence behind it.

| Date | Decision | Evidence |
|---|---|---|
| 2026-09-29 | Python 3.13 venv (not the machine default 3.15 alpha) | 3.15 is a pre-release; Pipecat's native deps (onnxruntime for Silero / Smart Turn) target stable Pythons |
| 2026-09-29 | Pipecat 1.12, Flows imported from `pipecat.flows` | 1.12 ships Flows built in and warns if the standalone `pipecat-ai-flows` package is also installed |
| 2026-09-29 | Keypad tones sent as in-band audio (Pipecat default for Twilio) | Pipecat's Twilio transport has no native DTMF, so `OutputDTMFFrame` is played as generated tone audio. To be confirmed on a real call against the test menu (`/ivr/voice`) |
| 2026-09-29 | Turn-taking: Silero VAD + Smart Turn v3 (Pipecat default stop strategy) | Default in 1.12; tuning planned for Day 4 |
| 2026-09-29 | `.env` overrides shell environment variables | Machine already has an `ANTHROPIC_API_KEY` set, which silently won over `.env` |
| 2026-09-29 | The call's logic (stages, tools, checklist) is transport-agnostic; Pipecat Flows is a thin adapter | The same code runs on live calls and in the text simulator, so tests exercise exactly what runs on the phone |
| 2026-09-29 | Stage transitions decided in code from the checklist, not by the LLM | Order can't drift, nothing gets skipped, and answers volunteered early make later stages skip automatically (tested) |
| 2026-09-29 | Hold: `SpeechGate` drops LLM text on hold instead of relying on the prompt | Guarantees silence through music and recorded messages |
| 2026-09-29 | Pipecat idle timeout raised from 5 to 30 min | Pipecat's default would cancel the pipeline (hang up) during a long hold; the reference call held 8m 41s |
| 2026-09-29 | Read-back script generated from state; next-eligible dates computed in code | The LLM never does arithmetic or recalls numbers from memory |
| 2026-09-29 | Post-call pass with Opus 5.5 + reconciliation; read-back corrections always win | A second, slower reading catches what the live model missed under latency pressure |
| 2026-09-29 | Output in two shapes: PDF shape (`reference.json`) + fully sourced (`sourced.json`) | Reviewers can diff against their example; the sourced version shows every field's evidence |
| 2026-09-29 | Reference call replay test: must reproduce the PDF's JSON exactly | Passes (tests/test_reference_call.py) |
| 2026-09-29 | Free-first stack: Gemini free tier (brain) + Deepgram Nova-3/Aura (ears + mouth on one free credit); Claude and Cartesia kept as one-setting alternatives | Budget constraint; switching is `LLM_PROVIDER` / `TTS_PROVIDER` in `.env` |
| 2026-09-29 | Browser mode (Pipecat SmallWebRTC) for day-to-day voice testing | Free, no phone needed; runs the exact same verification call. Verified: WebRTC connection reaches "connected" and the session starts |
| 2026-09-29 | Tool values passed as text; code converts them | Gemini's function-calling schema rejects union types; plain strings work on both providers and `coerce()` already parses "80", "$1,340", "03/01/2024" |
| 2026-09-29 | Gemini replies stored raw in simulator history | Gemini 3 requires thought signatures to be sent back unchanged in multi-turn tool use |
| 2026-10-01 | Code safety net for "person detected": if the LLM doesn't call `human_detected` within 2.5 s of a person-sounding turn on menu/hold, the code does | Review found the agent could stay muted forever if the LLM replied in text instead of calling the tool |
| 2026-10-01 | Say "Hello?" if the call is answered and nobody speaks for 8 s | Rep may pick up silently; both sides waiting = dead air |
| 2026-10-01 | Mid-call holds: `on_hold` in every stage, return to the same stage after | "Let me put you on a brief hold" mid-call previously had no handling |
| 2026-10-01 | Rep wants to leave: ask ONCE, in one short polite line, for the reference number; if they still insist, let them go. Unasked fields end as explicit `not_asked` nulls | Never trap the rep on the call, but don't give up the most defensible field without one try |
| 2026-10-01 | Full name given on pickup ("this is Haider Ali") is saved and never asked again; a first name only triggers a last-name ask once | No asking twice |
| 2026-10-01 | Close is skipped when its items were already given; read-back changes count as corrections | Prevented a stuck close stage and a wrong `remaining_corrected_on_readback` |
| 2026-10-01 | Quadrant history can be recorded in any stage; "on file, date unknown" is kept | Reps volunteer history early; absence of a date is still data |
| 2026-10-01 | Live-call brain: Groq (free, ~30 req/min, very fast) instead of Gemini Flash; Gemini kept for the one-shot post-call check | Measured: Gemini Flash free tier = 5 requests/min per model (first simulated call hit 429 on the IVR). A call needs ~10-15/min (each rep turn = 1-2 LLM calls). Flash also returned 503 "overloaded" several times |
| 2026-10-01 | Gemini 3 Flash at the lowest thinking level everywhere speed matters (Pipecat default live; added to the simulator) | Measured: default thinking ate the 200-token output budget (empty reply) and took 3-4 s; minimal = ~1.3 s |
| 2026-10-01 | Simulator waits and retries on 429/503 instead of crashing | Free tiers rate-limit; tests must still finish |
| 2026-10-01 | Live brain: pool of Gemini models (Flash-Lite first) that switches model inside the same turn on 429/503 | Measured free tier: Flash-Lite 15 req/min, Flash 5 req/min and only 20 req/DAY; Groq 8,000 tokens/min (~3 of our requests/min). One model alone would freeze mid-call |
| 2026-10-01 | Simulated rep runs on Groq (gpt-oss-120b), not Gemini Flash | One simulated call used up the Flash daily quota (20/day) |
| 2026-10-01 | Browser mode: added `/start` + `/sessions/{id}/api/offer` | The prebuilt page (v1.7) uses this flow; our server only had `/api/offer` -> 404 |
| 2026-10-01 | TTS text filter: raw IDs are read digit by digit | First voice test: LLM wrote "841552037"; TTS would read it as a large number |
| 2026-10-01 | Sanity checks on captured numbers (odd %, cents, remaining > max, unusual max) -> agent must confirm with the rep; "12 47"/"12.47" parsed as $1,247; reference number always read back | First voice test: STT heard "80%" as "8%", "fifteen hundred" as "50 hundred", "twelve forty-seven" as "$12.47" |
| 2026-10-01 | Read-back: say the correction back and record it before asking anything else | First voice test: agent asked for the reference number before handling the $1,247 correction |
| 2026-10-01 | "Let me look" / "one moment" answered instantly from code ("Sure, take your time.") and not sent to the LLM | Voice test: dead air after "let me look" (turn detector waited because the rep sounded unfinished, then the LLM took ~1 s) |
| 2026-10-01 | Only 2+ recognised words interrupt the agent while it speaks; a noise/echo interruption never makes it say "please repeat" | Voice test: frequent "can you repeat" — Pipecat's default asks the user to repeat after any unrecognised interruption (cough, echo, breath) |
| 2026-10-01 | One LLM call per turn when possible: the model asks its next question in the same reply as the tool call; the second call is skipped if a question was already asked (and not skipped when a value must be confirmed) | Voice test felt slow: each answer cost 2 LLM round trips (~1.1 s each) |
| 2026-10-01 | Smart Turn max wait 3 s -> 1.5 s | Short answers ("Two.") sounded unfinished to the turn detector, adding up to 3 s |
| 2026-10-01 | `REPLY GAP` logged on every turn | Measure latency instead of guessing |
| 2026-10-01 | The CODE asks the next question (scripted from the checklist in `fields.py`) and speaks the read-back; the LLM only listens, records facts, and handles anything unexpected | Voice test 2: 20-28 s silences. Log showed free Gemini taking 6-14 s per call, and 2 calls per turn. Now 1 call per turn; order can't drift; read-back starts instantly |
| 2026-10-01 | Model pool also skips a model that hasn't started answering within 2.5 s (it rests 60 s) | Free-tier latency swings from 1.3 s to 14 s minute to minute |
| 2026-10-01 | If no reply 1.3 s after the rep stops, say a short "Got it." / "Okay." | Dead air feels broken; a human rep would hear an acknowledgement |
| 2026-10-01 | Pool order: Flash-Lite (15/min) -> 3.5 Flash -> 3.6 Flash (20/day each) -> 3.1 Flash-Lite (slowest, no deadline) | Measured with the real prompt: 1.3-2.7 s / 2.7 s / 3.1 s / 4.2-5.6 s |
| 2026-10-01 | Agent has a name ("Ava") and still says it is an automated assistant | Voice test 3: asked its name, it said "My name is Assistant" |
| 2026-10-01 | Answer silence -> "Hello?" after 3 s (was 8); a person greeting moves to the introduction after 0.8 s (was 2.5) | Voice test 3: awkward wait after connecting |
| 2026-10-01 | Code-spoken lines (filler, stall ack, scripted questions) go straight to the voice from the SpeechGate, not the top of the pipeline | Voice test 3: a "Got it." queued at the top waited behind the LLM and played after the question |
| 2026-10-01 | Filler at most once per 6 s and never for 1-2 word fragments | Voice test 3: "Got it. Got it." |
| 2026-10-01 | Measured after the scripted-question change: reply gaps 1.0-2.4 s typical, 4.5 s worst (was 13-28 s) | server log, voice test 3 |
| _pending_ | Gemini vs Claude for the live call | Run the same personas on both once keys exist; keep the one with better field accuracy |
| _pending_ | Cartesia voice | Day 1 TTS test: each voice reads tax ID, member ID, DOB over a real call (`--mode tts_test --voice <id>`) |
| _pending_ | Live-call LLM | Day 3: 5 personas × 2 fast models |
