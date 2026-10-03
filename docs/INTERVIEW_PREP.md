# Interview Prep — Questions and Simple Answers

Read each answer, then say it out loud **in your own words**. Don't memorise; understand.
Short version first (say this), detail after (if they dig).

---

## A. The big picture

**1. Walk me through your system.**
> The agent is a Pipecat pipeline: Twilio carries the call, Deepgram turns speech into text, Gemini understands it and records facts through tools, Deepgram speaks the reply. The key design choice: **the LLM listens, the code drives.** A checklist in code knows every field we need, what's missing, and asks the next question. At hang-up we re-check the transcript and write the JSON in the PDF's exact shape, plus a version where every field has its source quote.

**2. Why didn't you just give the whole job to the LLM with one big prompt?**
> In earlier versions the LLM asked the questions itself. In tests it skipped and repeated questions, gave the patient before the provider IDs, and once invented a quote. So the LLM only does what it's good at — understanding messy speech. Order, completeness, maths and the read-back are code, so they can't drift. It also made it twice as fast: one LLM call per turn instead of two.

**3. Why STT → LLM → TTS, and not a speech-to-speech model?**
> Control and auditability. With text in the middle I get an exact transcript to quote from, reliable tool calls, correct numbers, and I can mute the agent on hold in code. Speech-to-speech is lower latency but harder to control and to prove what was said.

**4. Why Pipecat?**
> It's open source and built for phone voice agents: Twilio support, streaming, interruptions, turn detection, and Flows for stages. The same brain code runs on a phone call, in the browser and in my text simulator, so tests exercise exactly what runs live.

## B. Accuracy — "how do I trust this data?"

**5. How do you stop it from making things up?**
> Four layers. (1) A fact only enters through a tool with the rep's exact words. (2) The code checks the quote really appears in what the rep said — I added this after the model invented "effective January first" in a test. (3) Anything unanswered is an explicit null with a reason, never a guess. (4) The read-back lets the rep correct us, and a post-call pass re-reads the whole transcript and flags conflicts.

**6. What if speech-to-text mishears a number?**
> Sanity checks: 8% coverage, an amount with cents, or remaining bigger than the max are flagged, and the agent must confirm with the rep — it never silently "fixes" it. Also, "twelve forty-seven" is understood as $1,247. And the read-back catches the rest — in the reference call the remaining changed by $93 there.

**7. How do you compute "next eligible"?**
> In code: paid date + frequency months (24), or "now" if nothing is on file or the window has passed. Then the agent says it back — "Upper right comes eligible again February 4th, 2027 — is that date of service to date of service?" — because the counting rule can differ by payer.

**8. Why ask about quadrants with nothing on file?**
> Because absence is data. Upper left and lower left being empty means they can be treated today — that's the field the treatment plan turns on, and the rep won't say it unless asked.

**9. What's the difference between reference.json and sourced.json?**
> reference.json is exactly the PDF's shape, easy to compare. sourced.json has every field with status (answered, refused, corrected on read-back, needs review), the rep's exact words, and the transcript turn number. If a claim is denied later, staff can show what the payer said.

## C. The phone call itself

**10. How does it handle the phone menu and hold?**
> It answers the menu by voice or keypad tones (DTMF) — the tax ID is typed, never spoken. On hold, a SpeechGate drops anything it tries to say, so silence is guaranteed. Pipecat's default hangs up after 5 idle minutes; I raised it to 30, because hold music is never a reason to hang up.

**11. How does it know when a human picks up?**
> The LLM calls a tool when it hears a person. As a safety net, the code also detects greetings like "this is…", "how can I help" and switches within a second — that net fired in my first voice test.

**12. "Let me pull that up" — what happens?**
> The code recognises it and says "Sure, take your time" instantly, then waits. The LLM isn't even called. If the rep puts us on hold, it says "Sure, I'll hold" and mutes until they're back, and whatever they say on return is recorded.

**13. What if the rep says "Are you a robot?"**
> It says yes, it's an automated assistant calling for Cedar Park Dental, and continues. Honesty matters — it introduces itself as automated from the first sentence.

**14. What if the rep tries to end the call early?**
> It asks once, politely, for a reference number. If they insist, it lets them go — never traps them — and the unasked fields come out as `not_asked` nulls.

**15. What's the latency?**
> Measured per turn: speech-to-text ~0.5 s, LLM 1–2 s on the free tier, text-to-speech ~0.3 s. Early tests had 13–28 s gaps because the free LLM got slow and each turn used two calls. I fixed it with one call per turn, a pool that switches model if one hasn't answered in 2.5 s, and a short "Got it." if a reply takes longer than 1.3 s. A paid low-latency model would get it under a second.

## D. Engineering judgement

**16. Why is everything free? Doesn't that hurt quality?**
> It was a constraint I set myself, and it forced good engineering: I measured each free tier (Flash 20 requests/day, Flash-Lite 15/minute, Groq 8,000 tokens/minute) and designed around it — the model pool, one call per turn. Switching to a paid model is one setting.

**17. How did you test it?**
> Three levels. 64 unit tests — one replays the PDF call and must reproduce its JSON exactly. A text simulator where an LLM plays adversarial reps — skeptical 98%, hold-and-fix 100%. And live voice tests in the browser, which drove the latency and turn-taking fixes.

**18. What was the hardest bug?**
> The 20-second silences. The log showed the free LLM taking 6–14 seconds, twice per turn. I couldn't make Google faster, so I made the agent need it less: the code asks the next question, slow models are skipped, and fillers cover the rest.

**19. What would you do with two more weeks?**
> Paid low-latency LLM, more payers and IVR variations, per-field confidence from STT, a human review queue for `needs_review` fields, and HIPAA: BAAs with vendors, recording-consent rules per state.

**20. How would this scale to many calls?**
> Each call is an independent pipeline, so it scales horizontally — more server instances behind a queue. The limits are vendor concurrency and rate limits, so production would use paid tiers.

## E. Questions YOU can ask them
- "Which payers cause your team the most trouble today?"
- "How do staff use the data after the call — straight into the practice management system?"
- "What did Haider find hardest for the other agents?"
