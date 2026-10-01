"""Pipecat Flows adapter: turns our stages + tools into Flows NodeConfigs for live calls."""

from collections.abc import Awaitable, Callable

from pipecat.flows import FlowManager, FlowsFunctionSchema, NodeConfig
from pipecat.flows.types import NO_RESPONSE

from app.callflow.prompts import role_prompt, task_prompt
from app.callflow.tools import RESPOND_ON_ENTER, STAGE_TOOLS, TOOLS, run_tool
from app.state import CallState

SendDtmf = Callable[[str], Awaitable[None]]


def _function(name: str, state: CallState, send_dtmf: SendDtmf) -> FlowsFunctionSchema:
    tool = TOOLS[name]

    async def handler(args, flow_manager: FlowManager):
        outcome = run_tool(state, name, dict(args or {}))
        if outcome.dtmf:
            await send_dtmf(outcome.dtmf)
        if outcome.next_stage:
            return outcome.result, build_node(state.stage, state, send_dtmf)
        if not outcome.respond:
            return outcome.result, NO_RESPONSE
        return outcome.result, None

    return FlowsFunctionSchema(
        name=tool.name, description=tool.description,
        properties=tool.properties, required=tool.required, handler=handler,
    )


def build_node(stage: str, state: CallState, send_dtmf: SendDtmf, first: bool = False) -> NodeConfig:
    node: NodeConfig = {
        "name": stage,
        "task_messages": [{"role": "developer", "content": task_prompt(state, stage)}],
        "functions": [_function(n, state, send_dtmf) for n in STAGE_TOOLS[stage]],
        "respond_immediately": RESPOND_ON_ENTER[stage],
    }
    if first:
        node["role_message"] = role_prompt(state)  # persists across nodes
    if stage == "end":
        node["post_actions"] = [{"type": "end_conversation"}]
    return node
