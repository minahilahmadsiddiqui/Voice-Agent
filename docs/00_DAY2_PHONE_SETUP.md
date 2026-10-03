# Day 2 — Real Phone Call Setup (free)

Two free accounts: **Twilio** (the phone line) and **ngrok** (lets Twilio reach your laptop).

```
Your laptop (agent) ←── ngrok tunnel ←── Twilio ──→ 📱 phone rings
```

Why ngrok? Twilio lives on the internet. When the call connects, Twilio must send the live
audio to your laptop. Your laptop has no public address, so ngrok gives it one (a tunnel).

---

## 1. Twilio (≈10 min, no card)

1. Go to **https://www.twilio.com/try-twilio** → sign up (email + password).
2. Verify your email, then verify **your own phone number** (they text you a code).
   - This number becomes a **verified caller ID** → the trial is allowed to call it.
3. Onboarding questions: pick anything (e.g. "Voice", "With code", "Python").
4. On the **Console home page**, find **Account Info**:
   - **Account SID** (starts with `AC...`) → copy
   - **Auth Token** (click "show") → copy
5. Get a free phone number: click **"Get a phone number"** (or Phone Numbers → Manage → Buy a number).
   Pick a **US** number with **Voice** capability. It's paid from the free trial credit.
   Copy it in the form `+1XXXXXXXXXX`.
6. Allow calls to Pakistan (for testing on your own phone):
   **Voice → Settings → Geo permissions** → tick **Pakistan** → Save.
   (The US is already allowed — that's Haider.)

## 2. ngrok (≈5 min, no card)

1. Go to **https://dashboard.ngrok.com/signup** → sign up.
2. Left menu **"Your Authtoken"** → copy it.
3. Left menu **"Domains"** → you get **one free static domain** (e.g. `something.ngrok-free.app`) → copy it.
4. In a terminal, run once (paste your token):
   ```
   ngrok config add-authtoken YOUR_TOKEN
   ```

## 3. Put them in `.env`

```
TWILIO_ACCOUNT_SID=AC...
TWILIO_AUTH_TOKEN=...
TWILIO_FROM_NUMBER=+1XXXXXXXXXX
PUBLIC_URL=https://something.ngrok-free.app
```
(PUBLIC_URL = your ngrok domain with `https://` in front, no `/` at the end.)

## Trial limits to remember
- Calls only to **verified** numbers (yours now; Haider's before the demo).
- Callers hear a short **"trial account" message** and must **press any key** first.
- Free credit: about $15 — plenty for testing and the demo.

## To verify Haider's number later
Console → **Phone Numbers → Manage → Verified Caller IDs → Add** → enter his number →
Twilio calls/texts him a code → he tells you the code → done.
