"""Pipecat's Gemini service, but backed by a pool of models (see app/model_pool.py).

If the current model is rate limited, overloaded, or simply slow to start answering, the
same request is re-sent to the next model in the pool, within the same turn.
"""

import asyncio
from collections.abc import AsyncIterator

from google.genai import errors
from loguru import logger
from pipecat.services.google.llm import GoogleLLMService

from app.model_pool import ModelPool, is_retryable

# Free-tier Gemini sometimes takes 6-14 s before the first word (measured on a voice test).
# A healthy reply starts in ~1-2 s, so past this we stop waiting and ask the next model.
FIRST_CHUNK_TIMEOUT_SECS = 2.5
SLOW_MODEL_REST_SECS = 60


class _Slow(Exception):
    code = None


class PooledGoogleLLMService(GoogleLLMService):
    def __init__(self, *, pool: ModelPool, first_chunk_timeout: float = FIRST_CHUNK_TIMEOUT_SECS, **kwargs):
        super().__init__(**kwargs)
        self._pool = pool
        self._first_chunk_timeout = first_chunk_timeout

    async def _stream_response(self, context) -> AsyncIterator:
        last_error: Exception | None = None
        candidates = self._pool.order()
        for i, model in enumerate(candidates):
            # Pipecat picks the thinking level from the model name on every request.
            self._settings.model = model
            stream = super()._stream_response(context)
            is_last = i == len(candidates) - 1
            try:
                # The request is actually sent here. The last candidate gets no deadline.
                first_chunk = stream.__anext__()
                first = await (first_chunk if is_last else asyncio.wait_for(first_chunk, self._first_chunk_timeout))
            except StopAsyncIteration:
                return
            except asyncio.TimeoutError:
                await stream.aclose()
                self._pool.rest(model, SLOW_MODEL_REST_SECS, f"no reply after {self._first_chunk_timeout}s")
                continue
            except errors.APIError as e:
                if not is_retryable(e):
                    raise
                self._pool.cool(model, e)
                last_error = e
                continue
            yield first
            async for chunk in stream:
                yield chunk
            return
        if last_error:
            raise last_error
        logger.error("Every model in the pool was slow or unavailable")
