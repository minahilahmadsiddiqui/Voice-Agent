"""One small chat interface over Gemini and Claude, for code that calls an LLM directly
(the text simulator, the simulated rep and the post-call extraction).

Live calls don't use this: there Pipecat's own LLM services handle streaming.

Messages use one neutral format (the Anthropic shape):
  {"role": "user" | "assistant", "content": str | [blocks]}
  blocks: {"type": "text", "text"} | {"type": "tool_use", "id", "name", "input"}
          | {"type": "tool_result", "tool_use_id", "content"}
An assistant message may also carry "raw": the provider's own content object, which is
sent back verbatim (Gemini 3 requires its thought signatures to be returned unchanged).
"""

import json
import uuid
from dataclasses import dataclass, field
from typing import Any

from app.config import settings


@dataclass
class ToolUse:
    id: str
    name: str
    input: dict


@dataclass
class Reply:
    text: str = ""
    tool_uses: list[ToolUse] = field(default_factory=list)
    raw: Any = None  # provider-native assistant content, to store in history


class AnthropicChat:
    provider = "anthropic"

    def __init__(self, model: str, api_key: str | None = None):
        from anthropic import AsyncAnthropic

        self.model = model
        self.client = AsyncAnthropic(api_key=api_key or settings.anthropic_api_key)

    async def create(self, *, system: str, messages: list[dict], tools: list[dict] | None = None,
                     tool_choice: str | dict = "auto", max_tokens: int = 500, temperature: float = 0.2) -> Reply:
        kwargs: dict[str, Any] = {}
        if tools:
            kwargs["tools"] = tools
            if tool_choice == "none":
                kwargs["tool_choice"] = {"type": "none"}
            elif isinstance(tool_choice, dict):
                kwargs["tool_choice"] = {"type": "tool", "name": tool_choice["name"]}
        clean = [{"role": m["role"], "content": m["content"]} for m in messages]
        resp = await self.client.messages.create(
            model=self.model, max_tokens=max_tokens, temperature=temperature,
            system=system, messages=clean, **kwargs,
        )
        text = " ".join(b.text for b in resp.content if b.type == "text").strip()
        uses = [ToolUse(b.id, b.name, dict(b.input or {})) for b in resp.content if b.type == "tool_use"]
        return Reply(text, uses)


class GeminiChat:
    provider = "google"

    def __init__(self, model: str, api_key: str | None = None):
        from google import genai

        self.model = model
        self.client = genai.Client(api_key=api_key or settings.google_api_key)

    def _contents(self, messages: list[dict]):
        from google.genai import types

        names: dict[str, str] = {}  # tool_use id -> tool name (Gemini responses need the name)
        contents = []
        for m in messages:
            blocks = m["content"]
            if isinstance(blocks, str):
                blocks = [{"type": "text", "text": blocks}]
            for b in blocks:
                if b["type"] == "tool_use":
                    names[b["id"]] = b["name"]
            if m["role"] == "assistant" and m.get("raw") is not None:
                contents.append(m["raw"])
                continue
            parts = []
            for b in blocks:
                if b["type"] == "text" and b["text"]:
                    parts.append(types.Part(text=b["text"]))
                elif b["type"] == "tool_use":
                    parts.append(types.Part(function_call=types.FunctionCall(name=b["name"], args=b["input"])))
                elif b["type"] == "tool_result":
                    try:
                        payload = json.loads(b["content"])
                    except (TypeError, ValueError):
                        payload = {"result": b["content"]}
                    if not isinstance(payload, dict):
                        payload = {"result": payload}
                    parts.append(types.Part(function_response=types.FunctionResponse(
                        name=names.get(b["tool_use_id"], "tool"), response=payload)))
            if parts:
                contents.append(types.Content(role="model" if m["role"] == "assistant" else "user", parts=parts))
        return contents

    async def create(self, *, system: str, messages: list[dict], tools: list[dict] | None = None,
                     tool_choice: str | dict = "auto", max_tokens: int = 500, temperature: float = 0.2) -> Reply:
        from google.genai import types

        config: dict[str, Any] = {
            "system_instruction": system, "temperature": temperature, "max_output_tokens": max_tokens,
        }
        if tools:
            config["tools"] = [types.Tool(function_declarations=[
                types.FunctionDeclaration(name=t["name"], description=t["description"],
                                          parameters_json_schema=t["input_schema"]) for t in tools])]
            if tool_choice == "none":
                fcc = types.FunctionCallingConfig(mode="NONE")
            elif isinstance(tool_choice, dict):
                fcc = types.FunctionCallingConfig(mode="ANY", allowed_function_names=[tool_choice["name"]])
            else:
                fcc = types.FunctionCallingConfig(mode="AUTO")
            config["tool_config"] = types.ToolConfig(function_calling_config=fcc)
        resp = await self.client.aio.models.generate_content(
            model=self.model, contents=self._contents(messages),
            config=types.GenerateContentConfig(**config),
        )
        content = resp.candidates[0].content if resp.candidates else None
        parts = (content.parts if content else None) or []
        text = " ".join(p.text for p in parts if getattr(p, "text", None) and not getattr(p, "thought", False)).strip()
        uses = [ToolUse(p.function_call.id or f"call_{uuid.uuid4().hex[:8]}", p.function_call.name,
                        dict(p.function_call.args or {}))
                for p in parts if getattr(p, "function_call", None)]
        return Reply(text, uses, raw=content)


def make_chat(role: str) -> AnthropicChat | GeminiChat:
    """role: agent | rep | postcall. Picks provider and model from settings."""
    model = settings.model_for(role)
    if settings.llm_provider == "anthropic":
        return AnthropicChat(model)
    return GeminiChat(model)
