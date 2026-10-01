"""The model pool moves to the next model when one is rate limited."""

import asyncio

from google.genai import errors

from app.gemini_pool_llm import PooledGoogleLLMService
from app.model_pool import ModelPool, cooldown_secs, thinking_level


class _RateLimited(errors.APIError):
    def __init__(self, msg="Please retry in 30s"):
        self.code, self.message, self.status, self.details = 429, msg, "RESOURCE_EXHAUSTED", {}

    def __str__(self):
        return self.message


def test_pool_skips_resting_models():
    pool = ModelPool(["a", "b", "c"])
    pool.cool("a", _RateLimited())
    assert pool.order() == ["b", "c"]
    pool.cool("b", _RateLimited())
    pool.cool("c", _RateLimited("Please retry in 5s"))
    assert pool.order()[0] == "c" and 0 < pool.wait_secs() <= 6  # all resting: soonest first


def test_cooldowns_and_thinking():
    assert 30 < cooldown_secs(_RateLimited("Please retry in 30s")) < 32
    assert cooldown_secs(_RateLimited("quotaId GenerateRequestsPerDayPerProject")) >= 3600
    assert thinking_level("gemini-3.6-flash") == "minimal"
    assert thinking_level("gemini-3.8-flash") == "low"
    assert thinking_level("gemini-2.5-flash") is None


def test_live_service_falls_through_to_next_model_in_same_turn(monkeypatch):
    from pipecat.services.google import llm as gllm

    tried = []

    async def fake_parent_stream(self, context):
        tried.append(self._settings.model)
        if self._settings.model == "first":
            raise _RateLimited()
        yield "chunk-from-" + self._settings.model

    monkeypatch.setattr(gllm.GoogleLLMService, "_stream_response", fake_parent_stream)
    svc = PooledGoogleLLMService(pool=ModelPool(["first", "second"]), api_key="x",
                                 settings=gllm.GoogleLLMService.Settings(model="first"))

    async def run():
        return [c async for c in svc._stream_response(None)]

    assert asyncio.run(run()) == ["chunk-from-second"]
    assert tried == ["first", "second"]


def test_slow_model_is_skipped_within_the_same_turn(monkeypatch):
    from pipecat.services.google import llm as gllm

    async def slow_then_fast(self, context):
        if self._settings.model == "slow":
            await asyncio.sleep(5)
        yield "chunk-from-" + self._settings.model

    monkeypatch.setattr(gllm.GoogleLLMService, "_stream_response", slow_then_fast)
    svc = PooledGoogleLLMService(pool=ModelPool(["slow", "fast"]), first_chunk_timeout=0.1, api_key="x",
                                 settings=gllm.GoogleLLMService.Settings(model="slow"))

    async def run():
        return [c async for c in svc._stream_response(None)]

    assert asyncio.run(run()) == ["chunk-from-fast"]
    assert svc._pool.order() == ["fast"]  # the slow one rests for a while
