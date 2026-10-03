"""Free-tier survival: spread requests over several Gemini models.

Each Gemini model has its OWN free-tier rate limit (measured 2026-10-01: Flash-Lite 15
requests/min, Flash 5/min). One live call needs ~10-15 requests/min, so a single model can
run dry mid-call. A pool tries models in order; a model that answers 429 (rate limited) or
503 (overloaded) cools down and the same request goes straight to the next one, so the rep
never hears silence.
"""

import re
import time

from loguru import logger

# Gemini 3.7 / 3.8 Flash reject the "minimal" thinking level.
_LOW_ONLY = ("gemini-3.7-flash", "gemini-3.8-flash")


def thinking_level(model: str) -> str | None:
    """Fastest thinking level a Gemini model accepts (None: model has no thinking_level)."""
    if not model.startswith("gemini-3"):
        return None
    return "low" if model.startswith(_LOW_ONLY) else "minimal"


def parse_pool(raw: str) -> list[str]:
    return [m.strip() for m in raw.split(",") if m.strip()]


class ModelPool:
    def __init__(self, models: list[str]):
        if not models:
            raise ValueError("empty model pool")
        self.models = models
        self._cool_until: dict[str, float] = {}

    def order(self) -> list[str]:
        """Models ready now, in preference order; if all are cooling, the soonest-ready first."""
        now = time.time()
        ready = [m for m in self.models if self._cool_until.get(m, 0) <= now]
        if ready:
            return ready
        return sorted(self.models, key=lambda m: self._cool_until.get(m, 0))

    def wait_secs(self) -> float:
        """How long until the best model is ready (0 if one is ready now)."""
        return max(0.0, self._cool_until.get(self.order()[0], 0) - time.time())

    def cool(self, model: str, err: Exception) -> None:
        self.rest(model, cooldown_secs(err), str(_code(err)))

    def rest(self, model: str, secs: float, why: str) -> None:
        self._cool_until[model] = time.time() + secs
        logger.warning(f"Model {model} unavailable ({why}), resting {secs:.0f}s; trying the next one")


DAILY_LIMIT_REST_SECS = 15 * 60


def _code(err: Exception) -> int | None:
    return getattr(err, "code", None) or getattr(err, "status_code", None)


def is_retryable(err: Exception) -> bool:
    return _code(err) in (429, 500, 503)


def cooldown_secs(err: Exception) -> float:
    text = str(err)
    if _code(err) != 429:
        return 20.0  # overloaded: try again soon
    if "PerDay" in text:
        # Daily quota (probably) used up. Don't bench the model for hours on one error:
        # retrying costs a single request, and benching our best model would push every
        # turn onto slow fallbacks.
        return DAILY_LIMIT_REST_SECS
    m = re.search(r"retry in ([\d.]+)s|'retryDelay': '(\d+)s'", text)
    return float(m.group(1) or m.group(2)) + 1 if m else 60.0
