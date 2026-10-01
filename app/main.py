"""FastAPI server: starts calls, receives Twilio media streams and callbacks.

Run:  python -m app.main
"""

import json

import uvicorn
from fastapi import FastAPI, HTTPException, Request, WebSocket
from fastapi.responses import Response
from loguru import logger
from pipecat.runner.utils import parse_telephony_websocket
from pydantic import BaseModel

from app.browser import mount_ui
from app.browser import router as browser_router
from app.config import CALLS_DIR, settings
from app.ivr_test import router as ivr_router
from app.pipeline import run_call
from app.storage import set_recording
from app.telephony import start_call

app = FastAPI(title="SRP Voice Agent")
app.include_router(ivr_router)
app.include_router(browser_router)
mount_ui(app)


class CallRequest(BaseModel):
    to: str
    mode: str = "verify"  # verify | chat | ivr_test | tts_test
    scenario: str = "lana_kane"
    voice: str | None = None


@app.get("/")
def health():
    return {
        "ok": True,
        "browser": "/client/",
        "llm": f"{settings.llm_provider}:{settings.model_for('agent')}",
        "tts": settings.tts_provider,
        "missing_keys": settings.missing_for_voice(),
        "public_url": settings.public_url,
    }


@app.post("/call")
def call(req: CallRequest):
    try:
        sid = start_call(req.to, req.mode, req.scenario, req.voice)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"call_sid": sid}


@app.websocket("/ws")
async def media_stream(websocket: WebSocket):
    await websocket.accept()
    transport_type, call_data = await parse_telephony_websocket(websocket)
    if transport_type != "twilio":
        logger.error(f"Unexpected transport {transport_type}")
        await websocket.close()
        return
    await run_call(websocket, dict(call_data))


@app.post("/twilio/status")
async def call_status(request: Request):
    form = await request.form()
    logger.info(f"Call {form.get('CallSid')} status={form.get('CallStatus')} duration={form.get('CallDuration')}")
    return Response(status_code=204)


@app.post("/twilio/recording")
async def recording_ready(request: Request):
    form = dict(await request.form())
    sid = form.get("CallSid", "unknown")
    url = f"{form.get('RecordingUrl')}.mp3"
    logger.info(f"Recording for {sid}: {url} ({form.get('RecordingDuration')}s)")
    CALLS_DIR.mkdir(exist_ok=True)
    (CALLS_DIR / f"{sid}.recording.json").write_text(json.dumps({**form, "mp3_url": url}, indent=2))
    set_recording(sid, url)
    return Response(status_code=204)


if __name__ == "__main__":
    print(f"\n  Browser mode: http://localhost:{settings.port}/client/\n")
    uvicorn.run(app, host="0.0.0.0", port=settings.port)
