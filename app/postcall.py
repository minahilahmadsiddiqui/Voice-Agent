"""After the call: a stronger model re-reads the whole transcript, then we reconcile.

The live agent captures fields in real time under latency pressure. Afterwards, with no
time pressure, a more capable model extracts the same fields from the transcript. Then:
  - both agree                 -> keep (confirmed twice)
  - live missed it             -> take the extraction, source = "postcall"
  - they disagree              -> keep the one backed by the later transcript turn
                                  (a correction beats the original), status = needs_review
  - read-back corrections      -> always win (the rep explicitly confirmed them)
Dates (next eligible) are always recomputed in code from the reconciled values.
"""

import json

from loguru import logger

from app.config import settings
from app.llm_client import make_chat
from app.fields import QUADRANTS, RECORDABLE_PATHS, SPECS
from app.schema import FieldStatus
from app.state import RESOLVED, CallState, coerce, parse_date

EXTRACT_TOOL = {
    "name": "submit_extraction",
    "description": "Submit every benefit fact the insurance rep stated in the transcript.",
    "input_schema": {
        "type": "object",
        "properties": {
            "fields": {"type": "array", "items": {"type": "object", "properties": {
                "path": {"type": "string", "enum": RECORDABLE_PATHS},
                "value": {"type": "string", "description": "The value as text, e.g. 80, 1500, true, 2025-02-04."},
                "status": {"type": "string", "enum": ["answered", "refused", "unknown"]},
                "quote": {"type": "string"},
                "turn": {"type": "integer"},
            }, "required": ["path", "value", "status", "quote", "turn"]}},
            "quadrants": {"type": "array", "items": {"type": "object", "properties": {
                "quadrant": {"type": "string", "enum": QUADRANTS},
                "on_file": {"type": "string", "enum": ["yes", "no", "unknown"],
                            "description": "yes = SRP paid on file; no = rep said nothing on file."},
                "code": {"type": "string", "description": "D4341 or D4342, empty if none."},
                "paid_date": {"type": "string", "description": "YYYY-MM-DD, empty if none."},
                "quote": {"type": "string"},
                "turn": {"type": "integer"},
            }, "required": ["quadrant", "on_file", "quote", "turn"]}},
        },
        "required": ["fields", "quadrants"],
    },
}


def transcript_text(state: CallState) -> str:
    return "\n".join(f"[{t.idx}] {t.speaker.upper()}: {t.text}" for t in state.transcript)


def extraction_prompt(state: CallState) -> str:
    guide = "\n".join(f"- {f.path}: {f.ask} ({f.kind}{': ' + '|'.join(f.choices) if f.choices else ''})"
                      for f in SPECS.values())
    return (
        "Below is the transcript of a dental insurance benefits verification call. AGENT is our automated "
        "caller; REP is the insurance representative; IVR is the phone system.\n\n"
        "Extract every fact the REP stated or confirmed. Rules:\n"
        "- Only facts the rep said or explicitly confirmed. Never infer typical values.\n"
        "- If the rep corrected a value later (for example on the read-back), report the FINAL value, "
        "quoting and citing the turn of the correction.\n"
        "- A field the agent asked about but the rep declined: status refused. Asked but no clear answer: unknown. "
        "Never asked: omit it.\n"
        "- For quadrant history (UR, UL, LR, LL): on_file true with code and paid date if the rep said SRP was "
        "paid there; on_file false only if the rep said or confirmed nothing is on file.\n"
        "- quote = the rep's exact words; turn = the [number] of that line.\n\n"
        f"Fields:\n{guide}\n\nTranscript:\n{transcript_text(state)}"
    )


async def extract(state: CallState) -> dict | None:
    key = settings.llm_key_name
    if not getattr(settings, key):
        logger.warning(f"No {key.upper()}: skipping post-call extraction")
        return None
    reply = await make_chat("postcall").create(
        system="You extract structured data from call transcripts. Be exact; never guess.",
        messages=[{"role": "user", "content": extraction_prompt(state)}],
        tools=[EXTRACT_TOOL], tool_choice={"name": "submit_extraction"},
        max_tokens=4000, temperature=0,
    )
    return reply.tool_uses[0].input if reply.tool_uses else None


def _on_file(v) -> bool | None:
    if isinstance(v, bool) or v is None:
        return v
    return {"yes": True, "true": True, "no": False, "false": False}.get(str(v).strip().lower())


def reconcile(state: CallState, extraction: dict) -> list[dict]:
    """Merge the post-call extraction into state. Returns the list of discrepancies."""
    notes: list[dict] = []
    for item in extraction.get("fields", []):
        path = item.get("path")
        if path not in SPECS:
            continue
        cap = state.values[path]
        if cap.status == FieldStatus.CORRECTED:
            continue
        status = item.get("status", "answered")
        if status != "answered":
            if cap.status == FieldStatus.PENDING:
                state.mark(path, FieldStatus(status), item.get("quote"))
                cap.source = "postcall"
            continue
        try:
            value = coerce(SPECS[path], item.get("value"))
        except ValueError:
            continue
        turn = item.get("turn")
        if cap.status not in RESOLVED or cap.value is None:
            cap.value, cap.status, cap.quote, cap.turn, cap.source = (
                value, FieldStatus.ANSWERED, item.get("quote"), turn, "postcall")
            notes.append({"path": path, "kind": "missed_live", "value": str(value)})
        elif cap.value != value:
            live_turn = cap.turn if cap.turn is not None else -1
            notes.append({"path": path, "kind": "conflict", "live": str(cap.value), "postcall": str(value),
                          "live_turn": cap.turn, "postcall_turn": turn})
            if turn is not None and turn > live_turn:
                cap.previous_value, cap.value, cap.quote, cap.turn = cap.value, value, item.get("quote"), turn
            cap.status = FieldStatus.NEEDS_REVIEW
    for item in extraction.get("quadrants", []):
        q = str(item.get("quadrant", "")).upper()
        on_file = _on_file(item.get("on_file"))
        if q not in state.quadrants or on_file is None:
            continue
        qc = state.quadrants[q]
        try:
            paid = parse_date(item["paid_date"]) if on_file and item.get("paid_date") else None
        except ValueError:
            paid = None
        if qc.status not in RESOLVED:
            state.record_quadrant(q, on_file, item.get("code"), paid, item.get("quote"))
            qc.turn, qc.source = item.get("turn"), "postcall"
            notes.append({"path": f"srp.history.{q}", "kind": "missed_live"})
        elif qc.on_file != on_file or (on_file and qc.paid != paid):
            notes.append({"path": f"srp.history.{q}", "kind": "conflict",
                          "live": f"{qc.on_file} {qc.paid}", "postcall": f"{on_file} {paid}"})
            qc.status = FieldStatus.NEEDS_REVIEW
    state.log("reconcile", discrepancies=len(notes))
    return notes


async def run_postcall(state: CallState) -> list[dict]:
    try:
        extraction = await extract(state)
    except Exception as e:  # never lose the live result because the second pass failed
        logger.error(f"Post-call extraction failed: {e}")
        return [{"kind": "error", "detail": str(e)}]
    if not extraction:
        return []
    notes = reconcile(state, extraction)
    logger.info(f"Post-call reconcile: {json.dumps(notes)}")
    return notes
