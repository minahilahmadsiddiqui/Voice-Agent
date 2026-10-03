# SRP Benefits Verification Agent — Design (1 page)

**Goal:** phone a live payer rep, prove we are the practice, extract the SRP benefits a treatment plan depends on, and hang up with a validated JSON record where **every field has a source and nothing is guessed**.

## Architecture

```
 Twilio call ⇄ ngrok ⇄ FastAPI ⇄ Pipecat pipeline (one per call)
   audio in → Silero VAD + Smart Turn → Deepgram Nova-3 (STT) → StallAck → Gemini (LLM, tools)
   audio out ← Twilio ← Deepgram Aura-2 (TTS) ← SpeechGate ←────────────────┘
                                          │
                     CallState: the checklist (code)  ← tools write facts + quotes
                                          │
       hang-up → post-call re-extraction + reconcile → reference.json / sourced.json / SQLite
```

## The core idea: the LLM listens, the code drives

| The LLM does | The code does |
|---|---|
| Understand the rep's free-form speech | Hold the checklist of every field (`fields.py`) and what's still missing |
| Record facts via tools, **with the rep's exact words** | Decide the stage and the **next question** (scripted, PDF wording) |
| Handle the unexpected (questions, hedges, corrections) | Introduction, read-back, date math, sanity checks, hold/stall handling |

Why: an LLM alone forgets, skips, repeats and invents. A code-driven checklist can't drift, and it halves latency (one LLM call per turn instead of two).

**Stages:** `ivr → hold → verify → benefits → history → rules → maintenance → readback → close → end`. Stages already answered (volunteered early) are skipped.

## Accuracy: nothing is guessed

1. **Facts only through tools, with a quote.** A quote must be **grounded**: its words must appear in the rep's recent turns, or it is rejected (stopped an invented "effective January first").
2. **Sanity checks** on numbers STT tends to garble (8% vs 80%, "$12.47" vs $1,247, remaining > max) → the agent must confirm, never silently fix.
3. **Code does the maths:** next-eligible per quadrant (paid + 24 months, or "now" if nothing on file), then **confirmed back** to the rep.
4. **Absence is data:** the agent asks which quadrants have *nothing* on file.
5. **Read-back** generated from state; corrections are flagged `corrected_on_readback`. Reference number read back digit by digit; disclaimer captured verbatim.
6. **Post-call pass** re-reads the full transcript; agreement confirms, misses are filled, conflicts become `needs_review`, read-back corrections always win.
7. Unanswered → explicit `null` with a status (`refused` / `unknown` / `not_asked`).

## Reliability on a real call

| Situation | Handling |
|---|---|
| Phone menu, keypad, 9-min hold | Speech or DTMF; **SpeechGate** mutes on hold; idle hang-up raised 5 → 30 min |
| AI misses that a person is talking | Code detects greetings and un-mutes (0.8 s) |
| "Let me look…" | Code answers "Sure, take your time." instantly; LLM not called |
| "Let me put you on hold" | "Sure, I'll hold." → muted until the rep is back; answer given on return is recorded |
| Noise / echo / "mm-hm" | Only 2+ real words interrupt; never "please repeat" after noise |
| Slow or rate-limited LLM | Model pool switches model inside the same turn (429/503 or no first token in 2.5 s); "Got it." filler after 1.3 s; watchdog asks the next question after 6 s |
| Malformed tool call | Validated; never crashes the call |
| Rep must leave | Ask **once** for a reference number; then let them go |

## Zero-cost stack (measured, Oct 2026)

| Part | Tool | Free tier fact that shaped the design |
|---|---|---|
| Brain | Gemini Flash-Lite pool | 15 req/min per model; Flash only 20 req/**day** → pool + 1 call/turn |
| Ears + mouth | Deepgram Nova-3 + Aura-2 | one free credit; key-term hints for codes/names |
| Phone | Twilio trial | calls verified numbers only |
| Framework | Pipecat 1.12 + Flows | open source; same brain runs in browser, phone and text simulator |

## Testing

- **64 unit tests**, incl. a replay of the PDF call that must reproduce its JSON exactly.
- **Text simulator** with adversarial reps: *skeptical* (robot question, demands IDs, hedges) **98%**, *hold-and-fix* (mid-call hold, wrong quadrant then corrected) **100%**, *rushed* (batched, out-of-order answers) full call completed.
- **Browser voice tests** drove the latency work: reply gaps 13–28 s → 1–2.4 s typical.

## Limits and next steps (production)

- Free-tier LLM latency varies (1–5 s); a paid low-latency model would give sub-second replies.
- More payers and IVR variants; per-payer question tweaks.
- PHI handling (HIPAA BAAs with vendors), call recording consent rules per state.
- Confidence scores per field from STT word confidence; human review queue for `needs_review`.
