"""Browser mode: talk to the agent through your laptop's mic and speakers (free, no phone).

Open http://localhost:8765/client/ and click Connect. You play the phone menu and/or the
insurance rep; the agent runs exactly the same verification call it runs on a phone.
Audio travels over WebRTC between the browser and this server - no Twilio involved.

Set BROWSER_MODE in .env to chat / ivr_test / tts_test to use a test mode instead.
"""

import os
import uuid
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Request
from fastapi.responses import RedirectResponse, Response
from loguru import logger
from pipecat.transports.base_transport import TransportParams
from pipecat.transports.smallwebrtc.connection import SmallWebRTCConnection
from pipecat.transports.smallwebrtc.request_handler import (
    IceCandidate,
    SmallWebRTCPatchRequest,
    SmallWebRTCRequest,
    SmallWebRTCRequestHandler,
)
from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport

from app.config import settings
from app.pipeline import run_session

router = APIRouter()
_handler = SmallWebRTCRequestHandler()


async def _run(connection: SmallWebRTCConnection) -> None:
    missing = settings.missing_for_voice()
    if missing:
        logger.error(f"Browser session refused: add {', '.join(missing)} to .env (see .env.example), then restart.")
        await connection.disconnect()
        return
    transport = SmallWebRTCTransport(
        webrtc_connection=connection,
        params=TransportParams(audio_in_enabled=True, audio_out_enabled=True),
    )
    await run_session(
        transport,
        mode=os.environ.get("BROWSER_MODE", "verify"),
        scenario_name=os.environ.get("BROWSER_SCENARIO", "lana_kane"),
        call_sid=f"web-{datetime.now():%Y%m%d-%H%M%S}",
        sample_rate=None,
        kind="browser",
    )


@router.post("/api/offer")
async def offer(request: SmallWebRTCRequest, background_tasks: BackgroundTasks):
    async def on_connection(connection: SmallWebRTCConnection):
        background_tasks.add_task(_run, connection)

    return await _handler.handle_web_request(request=request, webrtc_connection_callback=on_connection)


@router.patch("/api/offer")
async def ice_candidate(request: SmallWebRTCPatchRequest):
    await _handler.handle_patch_request(request)
    return {"status": "success"}


# The prebuilt page first POSTs /start, then sends its WebRTC offer to
# /sessions/{id}/api/offer (same flow as Pipecat's own runner).
_sessions: set[str] = set()


@router.post("/start")
async def start():
    session_id = str(uuid.uuid4())
    _sessions.add(session_id)
    return {"sessionId": session_id,
            "iceConfig": {"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]}}


@router.api_route("/sessions/{session_id}/api/offer", methods=["POST", "PATCH"])
async def session_offer(session_id: str, request: Request, background_tasks: BackgroundTasks):
    if session_id not in _sessions:
        return Response(content="Unknown session", status_code=404)
    data = await request.json()
    if request.method == "PATCH":
        await _handler.handle_patch_request(SmallWebRTCPatchRequest(
            pc_id=data["pc_id"], candidates=[IceCandidate(**c) for c in data.get("candidates", [])]))
        return {"status": "success"}
    req = SmallWebRTCRequest(sdp=data["sdp"], type=data["type"], pc_id=data.get("pc_id"),
                             restart_pc=data.get("restart_pc"))
    return await offer(req, background_tasks)


@router.get("/browser", include_in_schema=False)
def browser():
    return RedirectResponse(url="/client/")


def mount_ui(app) -> None:
    from pipecat_ai_small_webrtc_prebuilt.frontend import SmallWebRTCPrebuiltUI

    app.mount("/client", SmallWebRTCPrebuiltUI)
