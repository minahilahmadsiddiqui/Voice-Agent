"""The Pipecat Flows adapter builds valid nodes and its handlers follow the tool outcomes."""

import asyncio

from pipecat.flows import FlowsFunctionSchema
from pipecat.flows.types import NO_RESPONSE

from app.callflow.nodes import build_node
from app.callflow.tools import STAGE_TOOLS
from app.config import load_scenario
from app.fields import STAGES
from app.state import CallState


def _state():
    return CallState(load_scenario("lana_kane"))


def test_every_stage_builds_a_node():
    s = _state()

    async def dtmf(_):
        pass

    for stage in STAGES:
        node = build_node(stage, s, dtmf, first=(stage == "ivr"))
        assert node["name"] == stage
        assert [fn.name for fn in node["functions"]] == STAGE_TOOLS[stage]
        assert all(isinstance(fn, FlowsFunctionSchema) for fn in node["functions"])
        assert node["task_messages"][0]["role"] == "developer"
        assert "{{" not in node["task_messages"][0]["content"]  # Flows would treat it as a template
    assert "role_message" in build_node("ivr", s, dtmf, first=True)
    assert build_node("end", s, dtmf)["post_actions"] == [{"type": "end_conversation"}]
    assert build_node("ivr", s, dtmf)["respond_immediately"] is False
    assert build_node("verify", s, dtmf)["respond_immediately"] is True


def test_handlers_send_dtmf_and_transition():
    s = _state()
    sent = []

    async def dtmf(d):
        sent.append(d)

    async def run():
        ivr = build_node("ivr", s, dtmf, first=True)
        fns = {fn.name: fn for fn in ivr["functions"]}
        result, nxt = await fns["press_digits"].handler({"digits": "841552037#"}, None)
        assert sent == ["841552037#"] and nxt is NO_RESPONSE
        result, nxt = await fns["on_hold"].handler({}, None)
        assert nxt["name"] == "hold" and s.muted
        hold_fns = {fn.name: fn for fn in nxt["functions"]}
        result, nxt = await hold_fns["human_detected"].handler({"rep_first_name": "Denise"}, None)
        assert nxt["name"] == "verify" and "Denise" in nxt["task_messages"][0]["content"]

    asyncio.run(run())


def test_long_hold_does_not_hang_up():
    """Pipecat's default idle timeout (5 min) would end the call during a long hold queue."""
    from pipecat.pipeline.pipeline import Pipeline

    from app.pipeline import MAX_IDLE_SECS, make_worker

    worker = make_worker(Pipeline([]))
    assert MAX_IDLE_SECS >= 25 * 60
    assert worker._idle_timeout_secs == MAX_IDLE_SECS
