"""A line typed in the browser Playground counts as a rep turn, like speech does.

Typed text skips the user-turn events. Without this, the rep's words weren't saved and the
agent went quiet after every tool call until pinged.
"""

import asyncio

from pipecat.frames.frames import LLMMessagesAppendFrame
from pipecat.tests.utils import run_test

from app.config import load_scenario
from app.pipeline import StallAck
from app.state import CallState


def test_typed_rep_line_is_a_rep_turn():
    state = CallState(load_scenario("lana_kane"), call_sid="t")
    state.stage = "benefits"
    seen = []

    async def on_typed(text):
        seen.append(text)

    ack = StallAck(state, speak=None)
    ack._on_typed = on_typed
    frames = [
        LLMMessagesAppendFrame(messages=[{"role": "user", "content": "Both 80% after deductible."}], run_llm=True),
        LLMMessagesAppendFrame(messages=[{"role": "developer", "content": "stage task"}]),  # Flows, not the rep
    ]
    # Both frames still reach the LLM; only the rep's line counts as a turn.
    asyncio.run(run_test(ack, frames_to_send=frames,
                         expected_down_frames=[LLMMessagesAppendFrame, LLMMessagesAppendFrame]))
    assert seen == ["Both 80% after deductible."]
