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
| _pending_ | Gemini vs Claude for the live call | Run the same personas on both once keys exist; keep the one with better field accuracy |
| _pending_ | Cartesia voice | Day 1 TTS test: each voice reads tax ID, member ID, DOB over a real call (`--mode tts_test --voice <id>`) |
| _pending_ | Live-call LLM | Day 3: 5 personas × 2 fast models |
