"""A fake payer phone menu for testing, served as Twilio webhooks.

Point a second Twilio number's "A call comes in" webhook at  POST {PUBLIC_URL}/ivr/voice
Then have the agent call that number in ivr_test mode. The menu:
  1. "For eligibility and benefits, say benefits or press one."
  2. "Enter the provider tax ID followed by pound."  -> checks the digits the agent keyed
  3. Hold music, then a rep greeting ("Thanks for holding, this is Denise...")
Results (what the menu heard and whether the tax ID matched) are logged and kept at GET /ivr/log.
"""

import os
import time

from fastapi import APIRouter, Request
from fastapi.responses import Response
from loguru import logger
from twilio.twiml.voice_response import Gather, VoiceResponse

from app.config import load_scenario

router = APIRouter(prefix="/ivr")

# Classic Twilio-hosted hold music; override with HOLD_MUSIC_URL if it ever moves.
HOLD_MUSIC_URL = os.environ.get(
    "HOLD_MUSIC_URL", "http://com.twilio.music.classical.s3.amazonaws.com/BusyStrings.mp3"
)
HOLD_MUSIC_LOOPS = int(os.environ.get("IVR_HOLD_MUSIC_LOOPS", "1"))
HOLD_SILENCE_SECONDS = int(os.environ.get("IVR_HOLD_SILENCE_SECONDS", "5"))
VOICE = "Polly.Joanna"

EVENTS: list[dict] = []


def _log(call_sid: str, step: str, **data) -> None:
    event = {"t": round(time.time()), "call_sid": call_sid, "step": step, **data}
    EVENTS.append(event)
    logger.info(f"IVR {step}: {data}")


def _twiml(r: VoiceResponse) -> Response:
    return Response(content=str(r), media_type="application/xml")


@router.post("/voice")
async def menu(request: Request):
    form = await request.form()
    _log(form.get("CallSid", ""), "answered", caller=form.get("From"))
    r = VoiceResponse()
    g = Gather(
        input="dtmf speech", num_digits=1, action="/ivr/menu", timeout=8,
        hints="benefits, eligibility, claims",
    )
    g.say(
        "Thank you for calling Meridian Dental Benefits provider services. "
        "For eligibility and benefits, say benefits or press one. For claims, say claims or press two.",
        voice=VOICE,
    )
    r.append(g)
    r.say("Sorry, I didn't get that.", voice=VOICE)
    r.redirect("/ivr/voice")
    return _twiml(r)


@router.post("/menu")
async def menu_choice(request: Request):
    form = await request.form()
    digits, speech = form.get("Digits", ""), (form.get("SpeechResult") or "").lower()
    _log(form.get("CallSid", ""), "menu", digits=digits, speech=speech)
    r = VoiceResponse()
    if digits == "1" or "benefit" in speech or "eligib" in speech:
        g = Gather(input="dtmf", finish_on_key="#", action="/ivr/taxid", timeout=15)
        g.say("Please enter the provider tax ID, followed by the pound key.", voice=VOICE)
        r.append(g)
        r.say("I didn't receive a tax ID.", voice=VOICE)
        r.redirect("/ivr/voice")
    else:
        r.say("That option is not available in this test.", voice=VOICE)
        r.redirect("/ivr/voice")
    return _twiml(r)


@router.post("/taxid")
async def tax_id(request: Request):
    form = await request.form()
    digits = form.get("Digits", "")
    expected = "".join(c for c in load_scenario("lana_kane").practice.tax_id if c.isdigit())
    ok = digits == expected
    _log(form.get("CallSid", ""), "tax_id", received=digits, expected=expected, match=ok)
    r = VoiceResponse()
    if not ok:
        r.say("That tax ID was not recognized.", voice=VOICE)
        r.redirect("/ivr/voice")
        return _twiml(r)
    r.say("Thank you. Please hold. Your estimated wait is nine minutes.", voice=VOICE)
    # Hold queue: music (the agent must stay silent through it), then some dead air.
    r.play(HOLD_MUSIC_URL, loop=HOLD_MUSIC_LOOPS)
    r.pause(length=HOLD_SILENCE_SECONDS)
    g = Gather(input="speech", action="/ivr/rep", timeout=10, speech_timeout="auto")
    g.say("Thanks for holding, Meridian provider services, this is Denise. "
          "Can I get your name and the practice?", voice=VOICE)
    r.append(g)
    r.say("Hello? I can't hear you. Goodbye.", voice=VOICE)
    return _twiml(r)


@router.post("/rep")
async def rep(request: Request):
    form = await request.form()
    _log(form.get("CallSid", ""), "rep_heard", speech=form.get("SpeechResult"))
    r = VoiceResponse()
    r.say("Thanks, this was only a test. Goodbye.", voice=VOICE)
    r.hangup()
    return _twiml(r)


@router.get("/log")
def log():
    return EVENTS[-50:]
