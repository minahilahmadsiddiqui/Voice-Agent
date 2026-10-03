"""Builds and runs the Pipecat voice pipeline for one phone call.

STT (Deepgram) -> LLM (Claude) -> TTS (Cartesia) cascade over a Twilio media stream.
  verify    THE REAL CALL: Pipecat Flows stages driven by the CallState checklist
  chat      free conversation, to check the phone line, latency and barge-in
  ivr_test  navigate a phone menu with speech + keypad tones, wait on hold, greet the rep
  tts_test  read the scenario's IDs and dates aloud (for comparing voices), then hang up
"""

import asyncio
import json
import random
import time

from fastapi import WebSocket
from loguru import logger
from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.audio.dtmf.types import KeypadEntry
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.flows import FlowManager
from pipecat.frames.frames import (
    EndFrame,
    Frame,
    FunctionCallResultProperties,
    LLMTextFrame,
    OutputDTMFFrame,
    TTSSpeakFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.serializers.twilio import TwilioFrameSerializer
from pipecat.services.anthropic.llm import AnthropicLLMService
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.services.deepgram.tts import DeepgramTTSService
from pipecat.services.google.llm import GoogleLLMService
from pipecat.services.groq.llm import GroqLLMService
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.llm_service import FunctionCallParams
from pipecat.workers.runner import WorkerRunner
from pipecat.audio.turn.smart_turn.base_smart_turn import SmartTurnParams
from pipecat.audio.turn.smart_turn.local_smart_turn_v3 import LocalSmartTurnAnalyzerV3
from pipecat.frames.frames import TranscriptionFrame
from pipecat.turns.empty_user_turn import EmptyUserTurnConfig
from pipecat.turns.user_start import MinWordsUserTurnStartStrategy
from pipecat.turns.user_stop import TurnAnalyzerUserTurnStopStrategy
from pipecat.turns.user_turn_strategies import UserTurnStrategies
from pipecat.utils.text.base_text_filter import BaseTextFilter
from pipecat.transports.websocket.fastapi import (
    FastAPIWebsocketParams,
    FastAPIWebsocketTransport,
)

from app import speech_format as sf
from app.callflow.nodes import build_node, enter_stage
from app.gemini_pool_llm import PooledGoogleLLMService
from app.model_pool import ModelPool, parse_pool
from app.callflow.tools import is_hold_request, is_stall, looks_like_person, run_tool
from app.config import CALLS_DIR, Scenario, groq_reasoning, load_scenario, settings
from app.results import finalize_call
from app.state import CallState

TWILIO_SAMPLE_RATE = 8000
# Pipecat cancels a pipeline (= hangs up) after 5 idle minutes by default. A payer's hold
# queue can be longer than that, and hold music is never a reason to hang up.
MAX_IDLE_SECS = 30 * 60

# Words Deepgram should favour on insurance calls (Nova-3 keyterm prompting).
BASE_KEYTERMS = [
    "SRP", "scaling and root planing", "D4341", "D4342", "D4910", "D1110",
    "prophy", "periodontal maintenance", "quadrant", "upper right", "upper left",
    "lower right", "lower left", "deductible", "annual maximum", "pre-authorization",
    "pre-treatment estimate", "radiographs", "perio charting", "pocket depth", "bone loss",
    "downgrade", "reference number", "NPI", "tax ID", "member ID", "subscriber",
    "periodontics", "periodontal", "pre-treatment estimate", "date of service",
    # The demo rep's name (first voice test heard "Haider" as "Heather").
    "Haider",
]


def scenario_keyterms(sc: Scenario) -> list[str]:
    return BASE_KEYTERMS + [sc.payer.name, sc.practice.name, sc.practice.provider_name, sc.patient.name]


def chat_prompt(sc: Scenario) -> str:
    return (
        f"You are an automated assistant calling on behalf of {sc.practice.name}. "
        "This is a test call to check the phone line. Chat briefly and naturally with the person. "
        "Keep every reply to one or two short sentences: your words are spoken aloud on a phone call, "
        "so never use lists, markdown, emoji or symbols. If asked, say honestly that you are an "
        "automated assistant. Wait for the other person to speak first."
    )


def ivr_prompt(sc: Scenario) -> str:
    tax_digits = "".join(c for c in sc.practice.tax_id if c.isdigit())
    return (
        f"You are an automated assistant phoning the {sc.payer.name} provider services line on "
        f"behalf of {sc.practice.name}. Your words are spoken aloud on a phone call.\n"
        "Rules:\n"
        "- Recorded menu offering options: when it offers eligibility or benefits, say just "
        "'Benefits', or call press_digits with the key it names.\n"
        f"- When asked to enter the provider tax ID, call press_digits with '{tax_digits}#'. "
        "Do not say the digits aloud.\n"
        "- On hold, music, or recorded messages ('your call is important', 'estimated wait'): "
        "stay completely silent. Reply with nothing at all. Never hang up.\n"
        "- When a live person greets you, say: 'Hi, this is an automated assistant calling on "
        f"behalf of {sc.practice.name}. This is a test call, thank you, goodbye.' and then stop."
    )


def tts_test_lines(sc: Scenario) -> list[str]:
    p, m = sc.practice, sc.patient
    return [
        "This is a voice clarity test.",
        f"Provider tax ID, {sf.spell_digits(p.tax_id)}.",
        f"N P I, {sf.spell_digits(p.npi)}.",
        f"Member ID, {sf.spell_id(m.member_id)}.",
        f"Spelled out, {sf.spell_id(m.member_id, phonetic=True)}.",
        f"Date of birth, {sf.spoken_date(m.dob)}.",
        f"Callback number, {sf.phone_number(p.callback_phone)}.",
        f"Remaining maximum, {sf.money(1247)}.",
        "End of test. Goodbye.",
    ]


PRESS_DIGITS = FunctionSchema(
    name="press_digits",
    description="Send keypad (DTMF) tones to the phone menu, e.g. '1' or '841552037#'.",
    properties={
        "digits": {"type": "string", "description": "Keys to press: 0-9, * and #."},
    },
    required=["digits"],
)


async def press_digits(params: FunctionCallParams):
    raw = str(params.arguments.get("digits", ""))
    buttons = [KeypadEntry(c) for c in raw if c in "0123456789*#"]
    logger.info(f"DTMF -> {raw!r}")
    if buttons:
        await params.llm.push_frame(OutputDTMFFrame(buttons=buttons))
    # Don't let the LLM talk right after keying digits: the menu speaks next.
    await params.result_callback(
        {"sent": "".join(b.value for b in buttons)},
        properties=FunctionCallResultProperties(run_llm=False),
    )


def make_worker(pipeline: Pipeline, sample_rate: int | None = TWILIO_SAMPLE_RATE) -> PipelineWorker:
    """sample_rate: 8000 for phone calls; None lets a browser session use Pipecat's defaults."""
    rates = {"audio_in_sample_rate": sample_rate, "audio_out_sample_rate": sample_rate} if sample_rate else {}
    return PipelineWorker(
        pipeline,
        params=PipelineParams(
            **rates,
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
        idle_timeout_secs=MAX_IDLE_SECS,
    )


def save_call_log(call_sid: str, mode: str, started: float, context: LLMContext) -> None:
    CALLS_DIR.mkdir(exist_ok=True)
    path = CALLS_DIR / f"{call_sid}.json"
    data = {
        "call_sid": call_sid,
        "mode": mode,
        "duration_sec": round(time.time() - started),
        "messages": context.get_messages(),
    }
    path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    logger.info(f"Saved call log: {path}")


async def run_call(websocket: WebSocket, call_data: dict) -> None:
    """A Twilio phone call: media stream over a websocket, 8 kHz audio."""
    body = call_data.get("body") or {}
    call_sid = call_data["call_id"]
    serializer = TwilioFrameSerializer(
        stream_sid=call_data["stream_id"],
        call_sid=call_sid,
        account_sid=settings.twilio_account_sid,
        auth_token=settings.twilio_auth_token,
    )
    transport = FastAPIWebsocketTransport(
        websocket=websocket,
        params=FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            add_wav_header=False,
            serializer=serializer,
        ),
    )
    await run_session(
        transport, mode=body.get("mode", "verify"), scenario_name=body.get("scenario", "lana_kane"),
        call_sid=call_sid, sample_rate=TWILIO_SAMPLE_RATE, voice=body.get("voice"), kind="live",
    )


# ---------- services, chosen from settings ----------

def make_stt(sc: Scenario) -> DeepgramSTTService:
    return DeepgramSTTService(
        api_key=settings.deepgram_api_key,
        settings=DeepgramSTTService.Settings(
            model="nova-3-general", keyterm=scenario_keyterms(sc), smart_format=True, numerals=True,
        ),
    )


class SpeakableIdsFilter(BaseTextFilter):
    """Last check before the voice: raw IDs are read digit by digit (see speech_format)."""

    async def filter(self, text: str) -> str:
        return sf.speakable_ids(text)


def make_tts(voice: str | None = None):
    filters = [SpeakableIdsFilter()]
    if settings.tts_provider == "cartesia":
        return CartesiaTTSService(
            api_key=settings.cartesia_api_key, text_filters=filters,
            settings=CartesiaTTSService.Settings(voice=voice or settings.cartesia_voice_id),
        )
    return DeepgramTTSService(
        api_key=settings.deepgram_api_key, text_filters=filters,
        settings=DeepgramTTSService.Settings(voice=voice or settings.deepgram_voice),
    )


def make_llm(system_instruction: str | None = None, temperature: float = 0.2, max_tokens: int = 400):
    extra = {"system_instruction": system_instruction} if system_instruction else {}
    if settings.llm_provider == "groq":
        return GroqLLMService(
            api_key=settings.groq_api_key,
            settings=GroqLLMService.Settings(
                model=settings.groq_model, temperature=temperature, max_tokens=max_tokens,
                reasoning_effort=groq_reasoning(settings.groq_model), **extra),
        )
    if settings.llm_provider == "anthropic":
        return AnthropicLLMService(
            api_key=settings.anthropic_api_key,
            settings=AnthropicLLMService.Settings(
                model=settings.llm_model, temperature=temperature, max_tokens=max_tokens, **extra),
        )
    pool = ModelPool(parse_pool(settings.gemini_model))
    return PooledGoogleLLMService(
        pool=pool,
        api_key=settings.google_api_key,
        settings=GoogleLLMService.Settings(
            model=pool.models[0], temperature=temperature, max_tokens=max_tokens, **extra),
    )


async def run_session(transport, *, mode: str, scenario_name: str, call_sid: str,
                      sample_rate: int | None, voice: str | None = None, kind: str = "live") -> None:
    """One voice session over any transport (Twilio phone call or browser WebRTC)."""
    sc = load_scenario(scenario_name)
    logger.info(f"Session {call_sid} ({kind}) mode={mode} llm={settings.llm_provider} tts={settings.tts_provider}")
    stt, tts = make_stt(sc), make_tts(voice)
    if mode == "verify":
        await run_verification(transport, stt, tts, sc, scenario_name, call_sid, sample_rate, kind)
        return

    llm = make_llm(ivr_prompt(sc) if mode == "ivr_test" else chat_prompt(sc), temperature=0.3, max_tokens=300)
    tools = ToolsSchema(standard_tools=[PRESS_DIGITS]) if mode == "ivr_test" else None
    if tools:
        llm.register_function("press_digits", press_digits)

    context = LLMContext(messages=[], tools=tools) if tools else LLMContext(messages=[])
    aggregators = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(vad_analyzer=SileroVADAnalyzer()),
    )
    pipeline = Pipeline([
        transport.input(),
        stt,
        aggregators.user(),
        llm,
        tts,
        transport.output(),
        aggregators.assistant(),
    ])
    task = make_worker(pipeline, sample_rate)
    started = time.time()

    @transport.event_handler("on_client_connected")
    async def on_connected(_transport, _client):
        if mode == "tts_test":
            # Speak the fixed script, then EndFrame ends the session (hangs up a phone call).
            await task.queue_frames([TTSSpeakFrame(t) for t in tts_test_lines(sc)] + [EndFrame()])
        # chat / ivr_test: the other side speaks first ("Hello?" or the IVR greeting).

    @transport.event_handler("on_client_disconnected")
    async def on_disconnected(_transport, _client):
        logger.info(f"Session {call_sid} disconnected")
        save_call_log(call_sid, mode, started, context)
        await task.cancel()

    await WorkerRunner(handle_sigint=False).run(task)


class SpeechGate(FrameProcessor):
    """Drops everything the LLM tries to say while the call is on hold.

    Prompts ask for silence on hold; this makes it a guarantee: hold music is
    never a reason to talk (or to hang up).
    """

    def __init__(self, state: CallState):
        super().__init__()
        self._state = state

    async def speak(self, text: str, append_to_context: bool = True) -> None:
        """Say a line from code, straight to the voice. Queued at the top of the pipeline it
        would wait behind the LLM's current reply (a "Got it." landing after the question)."""
        if self._state.muted:
            return
        await self.push_frame(TTSSpeakFrame(text, append_to_context=append_to_context), FrameDirection.DOWNSTREAM)

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if self._state.muted and isinstance(frame, (LLMTextFrame, TTSSpeakFrame)):
            return
        if isinstance(frame, LLMTextFrame) and frame.text.strip():
            if not self._state.agent_reply and self._state.rep_stopped_at:
                gap = time.time() - self._state.rep_stopped_at
                logger.info(f"REPLY GAP {gap:.2f}s (rep stopped -> first words to the voice)")
            # The LLM already said something this turn: a tool call in the same reply
            # doesn't need a second LLM round trip to speak (see callflow/nodes.py).
            self._state.agent_reply += frame.text
        await self.push_frame(frame, direction)


STALL_ACK = "Sure, take your time."
STALL_ACK_GAP_SECS = 20  # don't repeat "take your time" more often than this


class StallAck(FrameProcessor):
    """Rep says "let me look" / "one moment": answer at once, from code, and don't wake the LLM.

    Without this, the turn detector waits (the rep sounds unfinished) and then the LLM takes
    a second, so the rep hears dead air. Sits between STT and the user aggregator.
    """

    def __init__(self, state: CallState, speak, go_on_hold=None):
        super().__init__()
        self._state = state
        self._speak = speak  # SpeechGate.speak: straight to the voice
        self._go_on_hold = go_on_hold  # switches the call to the hold stage (mute until they're back)
        self._last_ack = 0.0

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if (isinstance(frame, TranscriptionFrame) and self._go_on_hold
                and self._state.stage not in ("ivr", "hold", "end") and is_hold_request(frame.text)):
            self._state.add_turn("rep", frame.text)
            await self._speak("Sure, I'll hold.")
            await self._go_on_hold()
            return
        if (isinstance(frame, TranscriptionFrame) and self._state.stage not in ("ivr", "hold", "end")
                and is_stall(frame.text)):
            self._state.add_turn("rep", frame.text)
            if time.time() - self._last_ack > STALL_ACK_GAP_SECS:
                self._last_ack = time.time()
                await self._speak(STALL_ACK)
            return  # swallowed: the LLM doesn't answer a stall
        await self.push_frame(frame, direction)


# Our voice was cut off by a noise or echo with no recognisable words: never say "please
# repeat" (annoying); just pick up where we were.
RESUME_AFTER_NOISE = (
    "A noise interrupted you and no words were recognized. Do not ask the rep to repeat anything. "
    "If your last question was cut off, ask it again briefly; otherwise say nothing."
)

IDLE_CHECK_SECS = 30  # rep silent this long after we spoke -> one gentle check-in
FILLER_AFTER_SECS = 1.3  # no reply yet this long after the rep stopped -> "Got it."
FILLER_GAP_SECS = 6  # at most one filler in this window
WATCHDOG_SECS = 6  # still nothing said this long after the rep stopped -> code asks the next question
FILLERS = ["Got it.", "Okay.", "Okay, thanks."]
SMART_TURN_STOP_SECS = 1.5  # longest wait when the rep sounds unfinished (Pipecat default 3)
ANSWER_SILENCE_SECS = 3  # call answered but nobody speaks -> say "Hello?"
HUMAN_FALLBACK_SECS = 0.8  # person spoke on menu/hold and the LLM didn't react -> code moves on


async def run_verification(transport, stt, tts, sc: Scenario, scenario_name: str, call_sid: str,
                           sample_rate: int | None = TWILIO_SAMPLE_RATE, kind: str = "live") -> None:
    """The real call: Pipecat Flows stages driven by the CallState checklist."""
    state = CallState(sc, call_sid=call_sid)
    llm = make_llm()
    context = LLMContext(messages=[])
    aggregators = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            vad_analyzer=SileroVADAnalyzer(), user_idle_timeout=IDLE_CHECK_SECS,
            user_turn_strategies=UserTurnStrategies(
                # While we speak, only 2+ real words interrupt us (not a cough, "mm-hm" or echo).
                start=[MinWordsUserTurnStartStrategy(min_words=2)],
                # Smart Turn waits up to 3 s by default when the rep *sounds* unfinished,
                # which felt slow on short answers ("Two.", "Ninety days.").
                stop=[TurnAnalyzerUserTurnStopStrategy(
                    turn_analyzer=LocalSmartTurnAnalyzerV3(params=SmartTurnParams(stop_secs=SMART_TURN_STOP_SECS)))],
            ),
            empty_user_turn=EmptyUserTurnConfig(interrupted_prompt=RESUME_AFTER_NOISE),
        ),
    )
    gate = SpeechGate(state)
    stall_ack = StallAck(state, gate.speak)
    pipeline = Pipeline([
        transport.input(),
        stt,
        stall_ack,
        aggregators.user(),
        llm,
        gate,
        tts,
        transport.output(),
        aggregators.assistant(),
    ])
    task = make_worker(pipeline, sample_rate)
    flow_manager = FlowManager(worker=task, llm=llm, context_aggregator=aggregators)

    async def send_dtmf(digits: str) -> None:
        logger.info(f"DTMF -> {digits}")
        await task.queue_frame(OutputDTMFFrame(buttons=[KeypadEntry(c) for c in digits]))

    async def go_on_hold() -> None:
        run_tool(state, "on_hold", {})  # remembers the stage to come back to
        await flow_manager.set_node_from_config(build_node("hold", state, send_dtmf, say=say))

    stall_ack._go_on_hold = go_on_hold

    async def say(text: str) -> None:
        """The code speaks a scripted line (next question, read-back) - no LLM round trip."""
        if state.rep_stopped_at and not state.agent_reply:
            logger.info(f"REPLY GAP {time.time() - state.rep_stopped_at:.2f}s (scripted line)")
        state.agent_reply += text
        await gate.speak(text)

    last_filler = {"t": 0.0}

    async def watchdog(stopped_at: float):
        # Free LLMs sometimes return an empty reply. Never leave the rep in silence: if
        # nothing was said, the code asks the next question on the checklist.
        await asyncio.sleep(WATCHDOG_SECS)
        if state.rep_stopped_at == stopped_at and not state.agent_reply and not state.muted:
            line = state.next_line()
            if line:
                logger.warning("No reply from the LLM: asking the next question from code")
                await say(line)

    async def filler_if_slow(stopped_at: float):
        # The free LLM sometimes takes seconds. Rather than dead air, acknowledge briefly.
        await asyncio.sleep(FILLER_AFTER_SECS)
        if (state.rep_stopped_at == stopped_at and not state.agent_reply and not state.muted
                and time.time() - last_filler["t"] > FILLER_GAP_SECS):
            last_filler["t"] = time.time()
            logger.info("Reply is slow: saying a short acknowledgement")
            await gate.speak(random.choice(FILLERS), append_to_context=False)

    idle = {"prompted": False}

    async def hello_if_silent():
        # Someone picked up but nobody speaks: say hello once instead of dead air.
        await asyncio.sleep(ANSWER_SILENCE_SECS)
        if state.stage == "ivr" and not state.transcript:
            logger.info("No speech after answer: saying hello")
            await gate.speak("Hello?")

    async def force_human_if_missed(digits_before: int):
        # The LLM should call human_detected itself; if it hasn't shortly after a person
        # spoke (or wrongly went on hold), the code does it, so the agent can never stay
        # stuck on mute.
        await asyncio.sleep(HUMAN_FALLBACK_SECS)
        if state.stage not in ("ivr", "hold") or len(state.digits_sent) != digits_before:
            return  # the LLM handled it
        stage = state.stage
        outcome = run_tool(state, "human_detected", {})
        logger.warning(f"LLM missed a live person in stage {stage}: moving to {outcome.next_stage}")
        if outcome.next_stage and outcome.confirm:  # back from a mid-call hold: the LLM records + speaks
            await flow_manager.set_node_from_config(build_node(state.stage, state, send_dtmf, say=say))
        elif outcome.next_stage:
            await flow_manager.set_node_from_config(await enter_stage(state, send_dtmf, say))

    @transport.event_handler("on_client_connected")
    async def on_connected(_transport, _client):
        state.connected_at = time.time()
        # Outbound: the phone system or the rep speaks first, so the first node waits.
        await flow_manager.initialize(build_node("ivr", state, send_dtmf, first=True, say=say))
        asyncio.create_task(hello_if_silent())

    @aggregators.user().event_handler("on_user_turn_started")
    async def on_user_started(_agg, _strategy):
        idle["prompted"] = False

    @aggregators.user().event_handler("on_user_turn_stopped")
    async def on_user_stopped(_agg, _strategy, message):
        text = message.content or ""
        state.agent_reply = ""  # a new LLM reply starts now
        state.rep_stopped_at = time.time()
        mid_call = state.resume_stage is not None
        speaker = "ivr" if state.stage in ("ivr", "hold") and not mid_call else "rep"
        state.add_turn(speaker, text)
        if state.stage in ("ivr", "hold") and looks_like_person(text, mid_call=mid_call):
            asyncio.create_task(force_human_if_missed(len(state.digits_sent)))
        elif state.stage not in ("ivr", "hold", "end") and text.strip() and not is_stall(text):
            # (an empty turn = a swallowed "let me look": we already said "take your time")
            if len(text.split()) >= 3 and not text.rstrip().endswith("?"):
                asyncio.create_task(filler_if_slow(state.rep_stopped_at))
            asyncio.create_task(watchdog(state.rep_stopped_at))

    @aggregators.assistant().event_handler("on_assistant_turn_stopped")
    async def on_assistant_stopped(_agg, message):
        if not state.muted:
            state.add_turn("agent", message.content or "")

    @aggregators.user().event_handler("on_user_turn_idle")
    async def on_idle(_agg):
        # "Let me pull that up" can take a while; check in once, never hang up.
        if state.stage in ("ivr", "hold", "end") or idle["prompted"]:
            return
        idle["prompted"] = True
        await gate.speak("I'm still here whenever you're ready.")

    @transport.event_handler("on_client_disconnected")
    async def on_disconnected(_transport, _client):
        logger.info(f"Session {call_sid} disconnected at stage {state.stage}")
        state.ended_reason = state.ended_reason or f"disconnected_during_{state.stage}"
        await task.cancel()

    await WorkerRunner(handle_sigint=False).run(task)
    await finalize_call(state, kind=kind, scenario=scenario_name)
