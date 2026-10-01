"""Tools the agent LLM can call, and which stage offers which tools.

Each handler takes (state, args) and returns an Outcome: the result the LLM sees,
the next stage (if the call should move on), and whether the LLM should speak now.
Stage transitions are decided HERE, in code, from the checklist - never by the LLM.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app import speech_format as sf
from app.fields import QUADRANT_NAMES, QUADRANTS, RECORDABLE_PATHS
from app.schema import FieldStatus
from app.state import SKIPPABLE, CallState


@dataclass
class Outcome:
    result: dict
    next_stage: str | None = None
    respond: bool = True  # False: stay silent until the other side speaks
    dtmf: str | None = None  # keypad tones to send


@dataclass
class Tool:
    name: str
    description: str
    properties: dict
    required: list[str]
    handler: Callable[[CallState, dict], Outcome]
    extra: dict = field(default_factory=dict)


def _advance(state: CallState, result: dict) -> Outcome:
    """After recording: move on when the current stage's checklist is complete."""
    if state.stage in ("verify", "benefits", "history", "rules", "maintenance", "close") and state.stage_done(state.stage):
        nxt = state.next_stage()
        result["stage_complete"] = True
        return Outcome(result, next_stage=nxt)
    result["still_missing"] = [f"{p}: {state.ask_for(p)}" for p in state.missing(state.stage)]
    return Outcome(result)


# ---------- phone menu / hold ----------

def press_digits(state: CallState, args: dict) -> Outcome:
    digits = "".join(c for c in str(args.get("digits", "")) if c in "0123456789*#")
    if not digits:
        return Outcome({"error": "no valid keys; use 0-9, * and #"})
    state.digits_sent.append(digits)
    state.log("dtmf", digits=digits)
    return Outcome({"sent": digits}, respond=False, dtmf=digits)


def on_hold(state: CallState, args: dict) -> Outcome:
    # Mid-call hold ("let me put you on a brief hold"): come back to the same stage.
    if state.stage not in ("ivr", "hold"):
        state.resume_stage = state.stage
    state.log("on_hold", resume=state.resume_stage)
    return Outcome({"ok": True, "note": "on hold: stay silent until the person comes back"},
                   next_stage="hold", respond=False)


# Safety net for the live call: if the LLM misses that a person is talking while we are on
# the phone menu or on hold, the code notices and moves on (otherwise the agent would stay
# silent forever).
_RECORDING = re.compile(
    r"your call is important|please (continue to |stay on the line and |remain on the line and )?hold"
    r"|estimated (wait|hold)|next available|representative will|will be with you"
    r"|calls? (may|will) be (recorded|monitored)|quality (and|assurance|purposes)|\bpress \w+|\bsay \w+ or\b"
    r"|para espa|www\.|dot com", re.I)
_PERSON = re.compile(
    r"\bthis is (?!(meridian|the|a|an|our|your)\b)\w+|\bmy name is\b|how (can|may) i help|what can i do for you"
    r"|who (am i speaking|is this|'s this|is calling)|who'?s calling|can i (get|have) (your|the)"
    r"|thanks? (you )?for (holding|waiting)|(are )?you still there|sorry (about|for) the (wait|hold)"
    r"|i'?m back|^\W*(hello|hi)\b", re.I)


def looks_like_person(text: str, mid_call: bool = False) -> bool:
    """Heuristic: does this turn sound like a live person rather than a recording?

    mid_call: the rep put us on hold mid-call, so anything that isn't a recording and has a
    few words is the rep coming back ("okay so I show D4341 paid...").
    """
    text = (text or "").strip()
    if not text or _RECORDING.search(text):
        return False
    return bool(_PERSON.search(text)) or (mid_call and len(text.split()) >= 4)


def human_detected(state: CallState, args: dict) -> Outcome:
    full = (args.get("rep_full_name") or "").strip()
    name = (args.get("rep_first_name") or "").strip() or (full.split()[0] if full else None)
    state.rep_first_name = name
    state.mark_human()
    # "This is Haider Ali" on pickup: keep the full name so close doesn't ask again.
    if len(full.split()) >= 2:
        state.record("call.rep", full, full)
    # The greeting was heard while we still thought it was the phone system.
    if state.transcript and state.transcript[-1].speaker == "ivr":
        state.transcript[-1].speaker = "rep"
    state.log("human", rep=name, hold_sec=state.hold_sec)
    resume, state.resume_stage = state.resume_stage, None
    if resume is None:
        return Outcome({"ok": True, "rep_first_name": name}, next_stage="verify")
    # Back from a mid-call hold: continue where we were (or the next open stage).
    nxt = resume if not (resume in SKIPPABLE and state.stage_done(resume)) else state.next_stage(after=resume)
    return Outcome({"ok": True, "note": "the rep is back; thank them briefly and continue"}, next_stage=nxt)


# ---------- recording ----------

def record_fields(state: CallState, args: dict) -> Outcome:
    recorded, errors = [], []
    for item in args.get("fields") or []:
        err = state.record(item.get("path", ""), item.get("value"), item.get("quote"))
        (errors if err else recorded).append(err or item.get("path"))
    result: dict[str, Any] = {"recorded": recorded}
    if errors:
        result["errors"] = errors
    return _advance(state, result)


def mark_unresolved(state: CallState, args: dict) -> Outcome:
    status = FieldStatus.REFUSED if args.get("status") == "refused" else FieldStatus.UNKNOWN
    err = state.mark(args.get("path", ""), status, args.get("quote"))
    return _advance(state, {"error": err} if err else {"marked": args.get("path"), "status": status.value})


def record_quadrant(state: CallState, args: dict) -> Outcome:
    recorded, errors, eligible = [], [], {}
    for item in args.get("quadrants") or []:
        q = str(item.get("quadrant", "")).upper()
        err = state.record_quadrant(q, bool(item.get("on_file")), item.get("code"),
                                    item.get("paid_date"), item.get("quote"))
        if err:
            errors.append(err)
            continue
        recorded.append(q)
        ne = state.next_eligible(q)
        if ne == "now":
            eligible[q] = f"{QUADRANT_NAMES[q]}: eligible now"
        elif ne:
            eligible[q] = f"{QUADRANT_NAMES[q]}: next eligible {sf.spoken_date(ne)} ({ne})"
        else:
            eligible[q] = f"{QUADRANT_NAMES[q]}: next eligible date unknown (frequency not captured)"
    result: dict[str, Any] = {"recorded": recorded, "next_eligible": eligible}
    if errors:
        result["errors"] = errors
    return _advance(state, result)


def member_not_found(state: CallState, args: dict) -> Outcome:
    state.member_not_found_count += 1
    state.log("member_not_found", count=state.member_not_found_count)
    if state.member_not_found_count == 1:
        pt = state.scenario.patient
        return Outcome({
            "instruction": "Retry once: spell the member ID phonetically and confirm name spelling and date of birth.",
            "member_id_phonetic": sf.spell_id(pt.member_id, phonetic=True),
            "date_of_birth": sf.spoken_date(pt.dob),
        })
    state.mark("member.active", FieldStatus.UNKNOWN, args.get("quote"))
    state.ended_reason = "member_not_found"
    return Outcome({"instruction": "Member could not be found. Ask for a reference number, then close politely."},
                   next_stage=state.next_stage(after="readback"))


def readback_done(state: CallState, args: dict) -> Outcome:
    applied, errors = [], []
    for item in args.get("corrections") or []:
        err = state.correct(item.get("path", ""), item.get("value"), item.get("quote"))
        (errors if err else applied).append(err or item.get("path"))
    if errors:
        return Outcome({"errors": errors, "note": "fix the paths/values and call readback_done again"})
    state.readback_done = True
    state.log("readback", corrections=applied)
    return Outcome({"corrections_applied": applied}, next_stage=state.next_stage())


def end_call(state: CallState, args: dict) -> Outcome:
    state.ended_reason = args.get("reason") or "ended_by_agent"
    state.log("end_call", reason=state.ended_reason)
    # Ask ONCE, briefly, for the reference number; if the rep still has to go, let them go.
    # Never trap the rep on the call. Whatever is missing ends up as an explicit null.
    if state.stage != "close" and not state.stage_done("close") and not state.asked_before_leaving:
        state.asked_before_leaving = True
        return Outcome({"instruction": "Say one short, polite line, e.g. \"Of course. Before you go, could I "
                                       "just get a reference number?\" If they still need to go, thank them "
                                       "and call end_call again. Do not insist."},
                       next_stage="close")
    return Outcome({"ok": True}, next_stage="end")


QUOTE = {"type": "string", "description": "The rep's exact words for this fact."}

TOOLS: dict[str, Tool] = {t.name: t for t in [
    Tool("press_digits", "Send keypad tones to the phone menu, e.g. '1' or '841552037#'.",
         {"digits": {"type": "string", "description": "Keys: 0-9, * and #."}}, ["digits"], press_digits),
    Tool("on_hold", "Call when you are put on hold: the phone system plays hold music or a wait time, or "
                    "the rep says they are putting you on hold. Not for a short 'let me check'.",
         {}, [], on_hold),
    Tool("human_detected", "Call when a live person (not a recording) starts talking to you.",
         {"rep_first_name": {"type": "string", "description": "The rep's first name if they gave it."},
          "rep_full_name": {"type": "string", "description": "First and last name, only if they gave both."}},
         [], human_detected),
    Tool("record_fields", "Record one or more benefit facts the rep just stated.",
         {"fields": {"type": "array", "items": {"type": "object", "properties": {
             "path": {"type": "string", "enum": RECORDABLE_PATHS},
             "value": {"type": "string", "description": "The value as text in the path's format, e.g. 80, 1500, true, 2025-02-04."},
             "quote": QUOTE}, "required": ["path", "value", "quote"]}}},
         ["fields"], record_fields),
    Tool("mark_unresolved", "Mark a field the rep refused or could not answer after one follow-up.",
         {"path": {"type": "string", "enum": RECORDABLE_PATHS + [f"srp.history.{q}" for q in QUADRANTS]},
          "status": {"type": "string", "enum": ["refused", "unknown"]}, "quote": QUOTE},
         ["path", "status"], mark_unresolved),
    Tool("record_quadrant", "Record SRP claim history for one or more quadrants (UR, UL, LR, LL).",
         {"quadrants": {"type": "array", "items": {"type": "object", "properties": {
             "quadrant": {"type": "string", "enum": QUADRANTS},
             "on_file": {"type": "boolean", "description": "true = SRP paid on file; false = rep confirmed nothing on file."},
             "code": {"type": "string", "description": "D4341 or D4342, when on file."},
             "paid_date": {"type": "string", "description": "Date of service paid, YYYY-MM-DD, when on file."},
             "quote": QUOTE}, "required": ["quadrant", "on_file", "quote"]}}},
         ["quadrants"], record_quadrant),
    Tool("member_not_found", "Call when the rep says they cannot find the member.",
         {"quote": QUOTE}, [], member_not_found),
    Tool("readback_done", "Call after the rep responds to the read-back.",
         {"corrections": {"type": "array", "items": {"type": "object", "properties": {
             "path": {"type": "string", "enum": RECORDABLE_PATHS},
             "value": {"type": "string", "description": "The corrected value as text."},
             "quote": QUOTE}, "required": ["path", "value", "quote"]}}},
         ["corrections"], readback_done),
    Tool("end_call", "End the call early only if the rep refuses to continue, asks you to call back, or must "
                     "leave. The first time, you may ask once for a reference number; if they still "
                     "need to go, call it again and let them go.",
         {"reason": {"type": "string"}}, ["reason"], end_call),
]}

# Every collecting stage can store anything the rep volunteers (incl. quadrant history)
# and handle a hold.
COLLECT = ["record_fields", "record_quadrant", "mark_unresolved", "on_hold", "end_call"]

STAGE_TOOLS: dict[str, list[str]] = {
    "ivr": ["press_digits", "on_hold", "human_detected"],
    "hold": ["human_detected"],
    "verify": COLLECT + ["member_not_found"],
    "benefits": COLLECT,
    "history": COLLECT,
    "rules": COLLECT,
    "maintenance": COLLECT,
    "readback": ["readback_done", "record_fields", "record_quadrant", "on_hold", "end_call"],
    "close": COLLECT,
    "end": [],
}

# The phone rings first and the other side speaks first; everywhere else the agent
# speaks as soon as it arrives in a stage (asks the next question).
RESPOND_ON_ENTER = {s: s not in ("ivr", "hold") for s in STAGE_TOOLS}


def run_tool(state: CallState, name: str, args: dict) -> Outcome:
    if name not in STAGE_TOOLS.get(state.stage, []):
        return Outcome({"error": f"{name} is not available in stage {state.stage}"})
    outcome = TOOLS[name].handler(state, args or {})
    if outcome.next_stage:
        state.log("stage", frm=state.stage, to=outcome.next_stage)
        state.stage = outcome.next_stage
        if state.stage == "end":
            state.ended_reason = state.ended_reason or "completed"
    return outcome
