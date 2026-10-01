# Setup Checklist (everything free)

## A. Software on your laptop — ALREADY DONE ✅
I checked on 2026-10-01:

- [x] Python 3.13 (project virtual environment `.venv`)
- [x] Pipecat 1.12 + all Python packages installed
- [x] Git
- [x] VS Code
- [x] Google Chrome (for browser voice testing)
- [x] ngrok program installed
- [ ] A headset / earphones with mic (recommended — avoids echo in browser tests)

## B. Free accounts + keys — TO DO

| # | Account | Website | What you copy | Used for | Needed when |
|---|---|---|---|---|---|
| 1 | Google AI Studio | aistudio.google.com | `GOOGLE_API_KEY` | 🧠 Brain | Day 1 |
| 2 | Deepgram | console.deepgram.com | `DEEPGRAM_API_KEY` | 👂 Ears + 👄 Mouth | Day 1 |
| 3 | Twilio | twilio.com/try-twilio | Account SID, Auth Token, free US phone number | 📞 Real calls | Day 2 |
| 4 | ngrok | dashboard.ngrok.com | Authtoken + free static domain | Lets Twilio reach your laptop | Day 2 |

No credit card needed for any of them.

## C. The `.env` file — TO DO
One private file in the project that holds all keys. We copy `.env.example` → `.env` and paste keys in.
Never share it, never upload it to GitHub (`.gitignore` already blocks it).

## D. Phone verification — TO DO (needs Haider)
- [ ] Verify YOUR phone number in Twilio (for Day 2 testing)
- [ ] Get Haider's phone number
- [ ] Verify Haider's number in Twilio (he receives a code, shares it with you)

## E. Order
1. Gemini key → 2. Deepgram key → 3. `.env` → 4. Browser voice test (you play Haider)
5. Twilio → 6. ngrok → 7. Call your own phone → 8. Verify Haider's number
