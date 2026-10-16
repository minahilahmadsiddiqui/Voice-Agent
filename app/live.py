"""Live view: watch a call fill in its checklist while it happens.

Open http://localhost:8765/live in a second tab (or share it on screen) while someone talks
to the agent. The page polls /live/state once a second: the transcript, every checklist field
with the rep's exact words, what is still to ask, and at the end the final JSON with every
empty field explained. It only reads CallState; it never changes the call.
"""

import re
import time
from datetime import date
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from fastapi.responses import FileResponse

from app.fields import FIELDS, QUADRANT_NAMES, QUADRANTS, SPECS
from app.schema import FieldStatus
from app.speech_format import display_digits
from app.state import COLLECTING, RESOLVED, CallState

router = APIRouter()
PAGE = Path(__file__).with_name("live_page.html")

GROUPS = {
    "verify": "Member eligibility",
    "benefits": "Benefits",
    "history": "Claim history",
    "rules": "Rules & documentation",
    "maintenance": "D4910 maintenance",
    "close": "Call record",
}
STAGE_LABELS = {
    "ivr": "Phone menu", "hold": "On hold", "verify": "Verify", "benefits": "Benefits",
    "history": "History", "rules": "Rules", "maintenance": "D4910", "readback": "Read-back",
    "close": "Close", "end": "Done",
}
# Why a field has no value - shown next to every null in the final result.
NULL_REASONS = {
    FieldStatus.REFUSED: "The rep declined to give it.",
    FieldStatus.UNKNOWN: "Asked, but the rep had no usable answer.",
    FieldStatus.NOT_ASKED: "The call ended before we got to it.",
    FieldStatus.NEEDS_REVIEW: "Live capture and the post-call check disagree; a person should check.",
    FieldStatus.PENDING: "Not asked yet.",
}

RESOLVED_VALUES = {s.value for s in RESOLVED}

_current: CallState | None = None
_result: dict | None = None


def track(state: CallState) -> None:
    """A new call started: show it on the live page."""
    global _current, _result
    _current, _result = state, None


def finish(state: CallState, result: dict) -> None:
    """The call's results are saved: show the final JSON."""
    global _result
    if state is _current:
        _result = result


def _label(ask: str) -> str:
    """'SRP frequency limitation, normalized like ...' -> 'SRP frequency limitation'."""
    ask = re.split(r", (?:normalized|snake_case|e\.g\.)", ask)[0]
    ask = re.sub(r"\s*\(.*?\)", "", ask).strip()
    return ask[:1].upper() + ask[1:]


def _show(kind: str, value: Any) -> str | None:
    if value is None:
        return None
    if kind == "bool":
        return "Yes" if value else "No"
    if kind == "pct":
        return f"{value}%"
    if kind == "money":
        return f"${value:,.2f}" if isinstance(value, float) and not value.is_integer() else f"${int(value):,}"
    if isinstance(value, date):
        return value.isoformat()
    return str(value).replace("_", " ")


def _quadrant_value(state: CallState, q: str) -> str | None:
    qc = state.quadrants[q]
    if qc.on_file is None:
        return None
    if not qc.on_file:
        return "Nothing on file · eligible now"
    paid = f"Paid {qc.paid.isoformat()}" if qc.paid else "Paid (date unknown)"
    code = f" ({qc.code})" if qc.code else ""
    ne = state.next_eligible(q)
    return f"{paid}{code}" + (f" · next eligible {ne}" if ne else "")


def _fields(state: CallState) -> list[dict]:
    out = []
    for f in FIELDS:
        cap = state.values[f.path]
        out.append({
            "path": f.path, "group": f.stage, "label": _label(f.ask), "required": f.required,
            "status": cap.status.value, "value": _show(f.kind, cap.value),
            "previous": _show(f.kind, cap.previous_value), "quote": cap.quote, "turn": cap.turn,
            "source": cap.source,
        })
    history = [{
        "path": f"srp.history.{q}", "group": "history", "label": f"SRP history, {QUADRANT_NAMES[q]} ({q})",
        "required": True, "status": qc.status.value, "value": _quadrant_value(state, q), "previous": None,
        "quote": qc.quote, "turn": qc.turn, "source": qc.source,
    } for q, qc in state.quadrants.items()]
    # Quadrants first in the history group, the order the agent asks them.
    i = next(i for i, x in enumerate(out) if x["group"] == "history")
    return out[:i] + history + out[i:]


def _missing(state: CallState) -> list[dict]:
    """Required items not resolved yet, the current stage first."""
    order = COLLECTING + ["close"]
    if state.stage in order:
        order = order[order.index(state.stage):] + order[:order.index(state.stage)]
    out = []
    for stage in order:
        for path in state.missing(stage):
            label = state.ask_for(path) if path.startswith("srp.history.") else SPECS[path].ask
            out.append({"path": path, "group": stage, "label": _label(label), "current": stage == state.stage})
    return out


def _nulls(fields: list[dict]) -> list[dict]:
    return [{"path": f["path"], "label": f["label"], "status": f["status"],
             "reason": NULL_REASONS.get(FieldStatus(f["status"]), ""), "quote": f["quote"]}
            for f in fields if f["value"] is None]


def snapshot() -> dict:
    state = _current
    if state is None:
        return {"status": "idle"}
    status = "done" if _result else "finalizing" if state.ended_reason or state.stage == "end" else "live"
    fields = _fields(state)
    snap = {
        "status": status,
        "call_sid": state.call_sid,
        "stage": state.stage,
        "stages": [{"key": k, "label": v} for k, v in STAGE_LABELS.items()],
        "elapsed_sec": round((state.ended_at or time.time()) - state.connected_at),
        "patient": state.scenario.patient.name,
        "practice": state.scenario.practice.name,
        "transcript": [{"idx": t.idx, "speaker": t.speaker, "text": display_digits(t.text)} for t in state.transcript],
        "groups": GROUPS,
        "fields": fields,
        "missing": [] if status == "done" else _missing(state),
        "captured": sum(f["status"] in RESOLVED_VALUES for f in fields),
        "total": len(fields),
    }
    if _result:
        snap["result"] = {
            "reference": _result["reference"],
            "discrepancies": _result["discrepancies"],
            "nulls": _nulls(fields),
            "dir": _result["dir"],
        }
    return snap


@router.get("/live", include_in_schema=False)
def live_page():
    return FileResponse(PAGE)


@router.get("/live/state")
def live_state():
    return snapshot()
