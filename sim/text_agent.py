"""Text-mode agent: the same prompts, tools and CallState as the live call, minus audio.

It drives the LLM (Gemini or Claude, via app.llm_client) with a tool loop that mirrors what
Pipecat Flows does on a call: current stage's task prompt, current stage's tools,
code-decided transitions, silence on hold, NO_RESPONSE after keypad presses.
"""

import json
import time
from dataclasses import dataclass, field

from app.callflow.prompts import role_prompt, task_prompt
from app.callflow.tools import RESPOND_ON_ENTER, STAGE_TOOLS, TOOLS, run_tool
from app.state import CallState

MAX_STEPS = 6  # LLM calls per agent turn (tool loops)


def tool_defs(names: list[str]) -> list[dict]:
    return [{
        "name": TOOLS[n].name,
        "description": TOOLS[n].description,
        "input_schema": {"type": "object", "properties": TOOLS[n].properties, "required": TOOLS[n].required},
    } for n in names]


@dataclass
class AgentTurn:
    spoken: str = ""
    digits: str = ""
    tools: list[str] = field(default_factory=list)
    suppressed: str = ""  # text the LLM produced while muted (should be empty)
    llm_ms: list[int] = field(default_factory=list)


class TextAgent:
    def __init__(self, state: CallState, client, temperature: float = 0.2):
        """client: an app.llm_client chat (GeminiChat / AnthropicChat) or a test fake."""
        self.state = state
        self.client = client
        self.temperature = temperature
        self.messages: list[dict] = []
        self.role = role_prompt(state)

    def _add_user(self, blocks: list[dict]) -> None:
        if self.messages and self.messages[-1]["role"] == "user":
            content = self.messages[-1]["content"]
            if isinstance(content, str):
                content = [{"type": "text", "text": content}]
            self.messages[-1]["content"] = content + blocks
        else:
            self.messages.append({"role": "user", "content": blocks})

    async def hear(self, text: str) -> AgentTurn:
        """The other side said `text`; returns what the agent says/does in response."""
        self._add_user([{"type": "text", "text": text}])
        return await self._respond()

    async def _respond(self) -> AgentTurn:
        turn = AgentTurn()
        for _ in range(MAX_STEPS):
            stage = self.state.stage
            names = STAGE_TOOLS[stage]
            tools, choice = tool_defs(names), "auto"
            if not names:
                # No tools in this stage; history still holds tool calls, so keep definitions, disallow use.
                tools, choice = tool_defs(STAGE_TOOLS["close"]), "none"
            t0 = time.perf_counter()
            reply = await self.client.create(
                system=f"{self.role}\n\n# Current stage\n{task_prompt(self.state, stage)}",
                messages=self.messages, tools=tools, tool_choice=choice,
                max_tokens=500, temperature=self.temperature,
            )
            turn.llm_ms.append(round((time.perf_counter() - t0) * 1000))

            muted = self.state.muted
            text, uses = reply.text, reply.tool_uses
            blocks = []
            if text and muted:
                turn.suppressed += text  # gated, exactly like SpeechGate on a live call
            elif text:
                turn.spoken = f"{turn.spoken} {text}".strip()
                blocks.append({"type": "text", "text": text})
            blocks += [{"type": "tool_use", "id": u.id, "name": u.name, "input": u.input} for u in uses]
            if blocks:
                self.messages.append({"role": "assistant", "content": blocks, "raw": reply.raw})
            if not uses:
                break

            results, respond, moved = [], True, False
            for u in uses:
                outcome = run_tool(self.state, u.name, dict(u.input or {}))
                turn.tools.append(u.name)
                if outcome.dtmf:
                    turn.digits += outcome.dtmf
                if outcome.next_stage:
                    moved = True
                if not outcome.respond:
                    respond = False
                results.append({"type": "tool_result", "tool_use_id": u.id,
                                 "content": json.dumps(outcome.result, default=str)})
            self._add_user(results)
            if moved:
                respond = RESPOND_ON_ENTER[self.state.stage]
            if not respond:
                break
        if turn.spoken:
            self.state.add_turn("agent", turn.spoken)
        return turn
