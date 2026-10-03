# Demo Runbook — Oct 4

Follow top to bottom. Tick each box.

## The day before (Oct 3)
- [ ] Haider's phone number added to Twilio **Verified Caller IDs** (he reads you the code).
- [ ] Ask what time the demo is, and whether they'll watch your screen (video call).
- [ ] One full test call to **your own phone**, start to finish. Check `/calls/latest`.
- [ ] Laptop charger, stable internet, earphones, phone charged.

## Free-quota rule
Gemini free limits reset at **midnight Pacific = 12:00 noon Pakistan time**.
On demo day, do **at most one** test call before the demo, so the quota is fresh for the real one.

## 30 minutes before

Open **3 terminals** in `C:\Voice Agent`:

```powershell
# Terminal 1 — the tunnel (your free static domain)
ngrok http 8765 --url=https://YOUR-DOMAIN.ngrok-free.app

# Terminal 2 — the agent server
.\.venv\Scripts\python.exe -m app.main

# Terminal 3 — health check
curl http://localhost:8765/
```
- [ ] Health check shows `"missing_keys": []` and your ngrok URL as `public_url`.
- [ ] `.\.venv\Scripts\python.exe -m pytest -q` → all tests pass (takes ~10 s).

## The demo call

```powershell
.\.venv\Scripts\python.exe scripts\place_call.py --to +1HAIDERSNUMBER
```
- Twilio trial: Haider first hears a short trial message and **presses any key**. Warn him in advance.
- Let the call run. **Don't touch anything.** The agent waits for him to speak first; after 3 s of silence it says "Hello?".
- Watch Terminal 2: `REPLY GAP` lines show each response time.

## Right after the call — show the result
Open in the browser:
- **http://localhost:8765/calls/latest** → the JSON in the PDF's shape (+ any discrepancies)
- **http://localhost:8765/calls/latest/sourced** → every field with Haider's exact words + the transcript

Point out: `remaining_corrected_on_readback`, the per-quadrant `next_eligible`, the reference number, the verbatim disclaimer, and any `null` (never guessed).

Files are also in `calls\<CallSid>\` (`reference.json`, `sourced.json`, `transcript.txt`), and Twilio keeps a **recording** of the call (Console → Monitor → Call logs → Recordings).

## What to say (2 minutes)
1. "The LLM listens; the code drives." Checklist in code, next question scripted, one LLM call per turn.
2. "Nothing is guessed." Quotes must match what the rep said; sanity checks on numbers; maths in code; read-back; post-call reconcile.
3. "Built for a real phone line." Menu + keypad, hold-proof, 'let me look' handled instantly, never trapped the rep.
4. "Zero cost, measured." Free-tier limits measured and designed around (model pool, fallbacks).
5. "Tested adversarially." 64 tests, simulator personas: skeptical 98%, hold-and-fix 100%.

## If something goes wrong (stay calm — have a plan)

| Problem | Do this |
|---|---|
| Call doesn't ring | Check Terminal 1 (ngrok running?) and `.env` `PUBLIC_URL`. Is Haider's number verified? |
| Agent silent / very slow | Free tier is slow right now. Let it run — the watchdog and fillers keep it going. Explain the model pool. |
| Call drops | Place it again (`place_call.py`). The previous call's result is still saved. |
| Total failure | Show a **saved successful call**: `calls\<sid>\transcript.txt` + `reference.json`, and the Twilio recording. Then run the text simulator live: `.\.venv\Scripts\python.exe -m sim.run --persona skeptical` |

## Backup prepared in advance
- [ ] One **successful phone test call** saved (note its folder name: `calls\________`).
- [ ] Its Twilio recording link noted.
- [ ] `docs\DESIGN.md` open in a tab (the 1-page design).
