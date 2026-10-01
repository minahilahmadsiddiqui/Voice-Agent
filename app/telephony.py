"""Placing outbound calls through Twilio."""

from loguru import logger
from twilio.rest import Client
from twilio.twiml.voice_response import Connect, Stream, VoiceResponse

from app.config import settings

REQUIRED = ("twilio_account_sid", "twilio_auth_token", "twilio_from_number", "public_url")


def stream_twiml(mode: str, scenario: str, voice: str | None) -> str:
    """TwiML that connects the answered call's audio to our websocket."""
    response = VoiceResponse()
    connect = Connect()
    stream = Stream(url=settings.ws_url)
    stream.parameter(name="mode", value=mode)
    stream.parameter(name="scenario", value=scenario)
    if voice:
        stream.parameter(name="voice", value=voice)
    connect.append(stream)
    response.append(connect)
    return str(response)


def start_call(to: str, mode: str = "verify", scenario: str = "lana_kane", voice: str | None = None) -> str:
    """Dial `to` and stream the call to the agent. Returns the Twilio call SID."""
    missing = settings.missing(*REQUIRED) + settings.missing_for_voice()
    if voice and "CARTESIA_VOICE_ID" in missing:
        missing.remove("CARTESIA_VOICE_ID")
    if missing:
        raise RuntimeError(f"Missing settings in .env: {', '.join(missing)}")

    client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
    call = client.calls.create(
        to=to,
        from_=settings.twilio_from_number,
        twiml=stream_twiml(mode, scenario, voice),
        record=True,
        recording_status_callback=f"{settings.public_url}/twilio/recording",
        recording_status_callback_event=["completed"],
        status_callback=f"{settings.public_url}/twilio/status",
        status_callback_event=["initiated", "ringing", "answered", "completed"],
    )
    logger.info(f"Placed call {call.sid} to {to} (mode={mode})")
    return call.sid
