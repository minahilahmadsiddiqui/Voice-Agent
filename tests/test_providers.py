"""Provider plumbing that can be checked without network: Gemini message conversion,
tool schemas accepted by the Gemini SDK, and the live service factories."""

import json

from google.genai import types

from app.callflow.tools import TOOLS
from app.llm_client import GeminiChat
from app.postcall import EXTRACT_TOOL
from sim.text_agent import tool_defs


def _chat():
    chat = GeminiChat.__new__(GeminiChat)  # no client needed for conversion
    chat.model = "gemini-test"
    return chat


def test_every_tool_schema_is_accepted_by_gemini():
    for t in tool_defs(list(TOOLS)) + [EXTRACT_TOOL]:
        decl = types.FunctionDeclaration(name=t["name"], description=t["description"],
                                         parameters_json_schema=t["input_schema"])
        assert decl.name == t["name"]
        # Gemini's function-calling schema rejects union types like ["string", "number"].
        assert '"type": [' not in json.dumps(t["input_schema"])


def test_gemini_history_conversion():
    msgs = [
        {"role": "user", "content": "Please enter the tax ID."},
        {"role": "assistant", "content": [{"type": "tool_use", "id": "c1", "name": "press_digits",
                                           "input": {"digits": "841552037#"}}]},
        {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "c1", "content": json.dumps({"sent": "841552037#"})},
            {"type": "text", "text": "Please hold."}]},
    ]
    contents = _chat()._contents(msgs)
    assert [c.role for c in contents] == ["user", "model", "user"]
    assert contents[1].parts[0].function_call.name == "press_digits"
    fr = contents[2].parts[0].function_response
    assert fr.name == "press_digits" and fr.response == {"sent": "841552037#"}
    assert contents[2].parts[1].text == "Please hold."


def test_gemini_raw_model_content_is_sent_back_verbatim():
    raw = types.Content(role="model", parts=[types.Part(text="Benefits.", thought_signature=b"sig")])
    contents = _chat()._contents([{"role": "user", "content": "menu"},
                                  {"role": "assistant", "content": [{"type": "text", "text": "Benefits."}], "raw": raw}])
    assert contents[1] is raw


def test_service_factories_build(monkeypatch):
    from app import pipeline
    from app.config import load_scenario, settings

    monkeypatch.setattr(settings, "deepgram_api_key", "x")
    monkeypatch.setattr(settings, "google_api_key", "x")
    monkeypatch.setattr(settings, "anthropic_api_key", "x")
    for provider in ("google", "anthropic"):
        monkeypatch.setattr(settings, "llm_provider", provider)
        assert pipeline.make_llm() is not None
    monkeypatch.setattr(settings, "tts_provider", "deepgram")
    assert type(pipeline.make_tts()).__name__ == "DeepgramTTSService"
    assert pipeline.make_stt(load_scenario("lana_kane")) is not None
