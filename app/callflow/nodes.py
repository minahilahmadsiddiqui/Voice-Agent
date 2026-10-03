"""Pipecat Flows adapter: turns our stages + tools into Flows NodeConfigs for live calls."""

import asyncio
from collections.abc import Awaitable, Callable

from pipecat.flows import FlowManager, FlowsFunctionSchema, NodeConfig
from pipecat.flows.types import NO_RESPONSE

from app.callflow.prompts import role_prompt, task_prompt
from app.callflow.tools import RESPOND_ON_ENTER, STAGE_TOOLS, TOOLS, run_tool
from app.state import CallState

SendDtmf = Callable[[str], Awaitable[None]]
Say = Callable[[str], Awaitable[None]]


def _function(name: str, state: CallState, send_dtmf: SendDtmf, say: Say | None) -> FlowsFunctionSchema:
    tool = TOOLS[name]

    async def handler(args, flow_manager: FlowManager):
        outcome = run_tool(state, name, dict(args or {}))
        if outcome.dtmf:
            await send_dtmf(outcome.dtmf)
        if outcome.confirm:
            # A value looks misheard (or the rep is back from hold with news): the LLM speaks.
            nxt = build_node(state.stage, state, send_dtmf, say=say, scripted=False) if outcome.next_stage else None
            return outcome.result, nxt
        if outcome.next_stage or outcome.respond:
            if "?" not in state.agent_reply:
                await asyncio.sleep(0.05)  # let text streamed just before the tool call reach the gate
        asked = "?" in state.agent_reply  # the LLM already asked something in this reply
        if outcome.next_stage:
            return outcome.result, await enter_stage(state, send_dtmf, say, skip_line=asked)
        if not outcome.respond:
            return outcome.result, NO_RESPONSE
        if asked:
            return outcome.result, NO_RESPONSE
        # The code asks the next question from the checklist: no second LLM round trip.
        line = state.next_line() if say else None
        if line:
            await say(line)
            return outcome.result, NO_RESPONSE
        return outcome.result, None

    return FlowsFunctionSchema(
        name=tool.name, description=tool.description,
        properties=tool.properties, required=tool.required, handler=handler,
    )


async def enter_stage(state: CallState, send_dtmf: SendDtmf, say: Say | None, skip_line: bool = False) -> NodeConfig:
    """Node for the stage we just moved to. If its opening line is scripted (a question, the
    read-back), the code says it at once and the LLM doesn't need to run."""
    line = state.next_line() if say and not skip_line else None
    node = build_node(state.stage, state, send_dtmf, say=say, scripted=bool(line) or skip_line)
    if line:
        await say(line)
    return node


def build_node(stage: str, state: CallState, send_dtmf: SendDtmf, first: bool = False,
               say: Say | None = None, scripted: bool = False) -> NodeConfig:
    """scripted: the opening line was already said by code, so the LLM waits for the rep."""
    node: NodeConfig = {
        "name": stage,
        "task_messages": [{"role": "developer", "content": task_prompt(state, stage)}],
        "functions": [_function(n, state, send_dtmf, say) for n in STAGE_TOOLS[stage]],
        "respond_immediately": RESPOND_ON_ENTER[stage] and not scripted,
    }
    if first:
        node["role_message"] = role_prompt(state)  # persists across nodes
    if stage == "end":
        node["post_actions"] = [{"type": "end_conversation"}]
    return node
