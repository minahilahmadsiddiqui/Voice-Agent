# Demo Runbook — Oct 15 (browser demo)

Follow top to bottom. Tick each box.

## How the demo works

```
 Haider (US)                          Your laptop (Pakistan)
 Chrome  ──── internet ────►  ngrok  ──►  agent server (port 8765)
 /client/  (his mic + speakers)              │
                                             ▼
 You share your screen  ◄──────────  /live  (transcript + checklist + JSON)
```

- The agent runs on **your laptop**. Haider opens a link in **his** browser and talks to it.
- He plays the insurance rep (and the phone menu, if he wants).
- His voice goes straight to your laptop over WebRTC. If his router blocks that, the **TURN server** (metered.ca) relays it.
- You watch, and share **http://localhost:8765/live** on the video call.
- There's no phone and no Twilio. Everything is free.

## Before demo day (Oct 13–14)

- [ ] **Commit your code** (`git add -A`, `git commit`). That gives you a safe copy to go back to.
- [ ] Ask Haider: what time, which video app (Meet / Zoom), and does he have **Chrome + headphones**?
- [ ] `.env` has `GOOGLE_API_KEY`, `DEEPGRAM_API_KEY`, `TURN_URLS`, `TURN_USERNAME`, `TURN_CREDENTIAL`, `PUBLIC_URL`.
- [ ] **Rehearsal 1, you alone:** full call through `http://localhost:8765/client/` with headphones and `/live` open. It must reach the read-back and save `calls\web-<time>\reference.json`.
- [ ] **Rehearsal 2, from another network:** a friend on **mobile data** (not your Wi-Fi) opens your ngrok link `/client/` and does a full call. This is the only way to prove the path Haider will use.
- [ ] Record one good rehearsal of your screen (free: **Win + Alt + R**, Xbox Game Bar). That's your backup video.
- [ ] Note the backup call folder: `calls\web-________________`
- [ ] Send Haider the message below the day before.

### Message to send Haider

> Hi Haider, for tomorrow's demo the agent runs in the browser (no phone line, to keep it zero-cost).
> 1. Please use **Chrome** and **headphones** (otherwise the agent hears itself).
> 2. I'll send you a link. ngrok may show a warning page; just click **Visit Site**.
> 3. Click **Connect** and allow the microphone.
> 4. The agent waits for you to speak first, like a real call. You can start with a phone menu ("For benefits, press one") or as the rep ("Thanks for holding, this is Denise…").
> 5. Play the rep however you like: put it on hold, give wrong numbers then correct them, ask if it's a robot.

## Free-quota rule

Gemini free limits reset at **midnight Pacific = 12:00 noon Pakistan time**.
On demo day, do **at most one** short test before the demo, so the quota is fresh.
Don't run the text simulator on demo day (it uses the same Gemini quota).

## 30 minutes before

Close other heavy apps. Plug in the charger. Use cable internet if you can.

Open **3 terminals** in `C:\Voice Agent`:

```powershell
# Terminal 1 — the tunnel (your free static ngrok domain, same as PUBLIC_URL in .env)
ngrok http 8765 --url=https://left-tableful-justly.ngrok-free.dev

# Terminal 2 — the agent server
.\.venv\Scripts\python.exe -m app.main

# Terminal 3 — checks
curl http://localhost:8765/
curl -X POST http://localhost:8765/start
.\.venv\Scripts\python.exe -m pytest -q
```

- [ ] `curl /` shows `"missing_keys": []`.
- [ ] `curl -X POST /start` lists a `turn:global.relay.metered.ca` server. If it only shows `stun:`, the TURN settings didn't load. Fix `.env`, then restart Terminal 2.
- [ ] `pytest` → **72 passed**.
- [ ] Open `https://left-tableful-justly.ngrok-free.dev/client/` on **your phone, using mobile data**. The page loads. (Don't click Connect, to save quota.)
- [ ] Open **http://localhost:8765/live** in a browser tab, ready to share.

## The demo call

1. Join the video call. Share the **/live** tab.
2. Send Haider the link: `https://left-tableful-justly.ngrok-free.dev/client/`
3. He clicks **Visit Site** (ngrok warning), then **Connect**, then allows the mic.
4. **Only Haider clicks Connect.** Don't open `/client/` yourself, or a second call starts.
5. Let it run. **Don't touch anything.** If he stays silent for 3 s, the agent says "Hello?".
6. Watch Terminal 2. The `REPLY GAP` lines show each response time.
7. When the agent says goodbye, the call ends. If it doesn't end, Haider clicks **Disconnect**. Results are saved at that moment.

### What Haider sees on /live (through your screen share)
- His answers turn green, each with **his exact words** and turn number. Click a `#turn` link to jump to that line.
- "Still to ask" shrinks as the call goes on.
- When the call ends, the final JSON and the reason for each empty field appear at the top.

## Right after the call — show the result

Open in the browser:
- **http://localhost:8765/calls/latest** → the JSON in the PDF's shape (+ any discrepancies)
- **http://localhost:8765/calls/latest/sourced** → every field with Haider's exact words + the transcript

Point out: `remaining_corrected_on_readback`, the per-quadrant `next_eligible`, the reference number, the verbatim disclaimer, and any `null` (never guessed).

The files are also in `calls\web-<time>\` (`reference.json`, `sourced.json`, `transcript.txt`).

## What to say (2 minutes)

1. **"The LLM listens; the code drives."** The checklist lives in code, the next question is scripted, one LLM call per turn.
2. **"Nothing is guessed."** Quotes must match what the rep said. Odd numbers get double-checked. Date maths is done in code. Then a read-back and a post-call reconcile.
3. **"Built for a real phone line."** Menu + keypad, hold-proof, "let me look" handled instantly, never traps the rep. Only the audio channel is the browser today. The phone version (Twilio) is in the code and would plug in with a paid number.
4. **"Zero cost, measured."** Free-tier limits measured and designed around (a pool of Gemini models, fallbacks, a filler line when it's slow).
5. **"Tested adversarially."** 72 automated tests, plus a simulator with four rep personas. Latest runs: cooperative 100%, rushed 100%, hold-and-fix 100%, skeptical 95–100% of 43 fields.

## If something goes wrong (stay calm, have a plan)

| Problem | Do this |
|---|---|
| Haider's page doesn't load | Is Terminal 1 (ngrok) running? Is the link exactly right, with `/client/` at the end? |
| Page loads, Connect spins / no audio | Network blocked. Check `curl -X POST /start` shows TURN. Ask him to try his phone hotspot. |
| Agent can't hear him | Chrome mic permission (lock icon in the address bar → Microphone → Allow). Check the right mic is chosen in the page. |
| Agent hears itself / talks over itself | He needs headphones. |
| Terminal 2 says `Browser session refused` | A key is missing in `.env`. Add it, restart Terminal 2, reconnect. |
| Agent silent / very slow | Free tier is busy. Let it run; the watchdog and filler lines keep it going. Explain the model pool. |
| Call drops | He clicks Connect again. The earlier call's result is still saved. |
| Total failure | Show the **backup**: the saved `calls\web-…` folder (`transcript.txt` + `reference.json`) and your rehearsal video. Then run the text simulator live: `.\.venv\Scripts\python.exe -m sim.run --persona skeptical` |

## Backup prepared in advance

- [ ] One **successful browser call** saved (folder name written above).
- [ ] Rehearsal screen recording saved (Videos → Captures).
- [ ] `docs\DESIGN.md` open in a tab (the 1-page design).
