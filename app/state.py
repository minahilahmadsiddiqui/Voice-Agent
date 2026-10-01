"""CallState: the single source of truth during a call.

The LLM never "remembers" benefits. Every fact goes through a tool into this object,
with the rep's exact words and the transcript turn it came from. The code - not the
LLM - decides what is still missing and which stage comes next.
"""

import re
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from app import speech_format as sf
from app.config import Scenario
from app.eligibility import next_eligible
from app.fields import QUADRANT_NAMES, QUADRANTS, SPECS, STAGES, FieldSpec, fields_for
from app.schema import FieldStatus

RESOLVED = {FieldStatus.ANSWERED, FieldStatus.REFUSED, FieldStatus.UNKNOWN,
            FieldStatus.CORRECTED, FieldStatus.PROVIDED}
# Stages that collect fields, in call order. readback and close always run.
COLLECTING = ["verify", "benefits", "history", "rules", "maintenance"]
SKIPPABLE = COLLECTING + ["close"]


@dataclass
class Captured:
    value: Any = None
    status: FieldStatus = FieldStatus.PENDING
    quote: str | None = None
    turn: int | None = None
    previous_value: Any = None
    source: str = "live"  # live | postcall | scenario
    stage: str | None = None  # call stage it was captured in


@dataclass
class QuadrantCapture:
    status: FieldStatus = FieldStatus.PENDING
    on_file: bool | None = None  # False = rep confirmed nothing on file
    code: str | None = None
    paid: date | None = None
    quote: str | None = None
    turn: int | None = None
    source: str = "live"


@dataclass
class Turn:
    idx: int
    speaker: str  # rep | agent | ivr
    text: str
    t: float


class ValueError_(ValueError):
    pass


# ---------- value coercion: the LLM passes strings/numbers, we store typed values ----------

def _num(raw: Any) -> float:
    if isinstance(raw, bool):
        raise ValueError_("expected a number")
    if isinstance(raw, (int, float)):
        return float(raw)
    s = str(raw).replace(",", "").replace("$", "").replace("%", "").strip()
    m = re.search(r"-?\d+(\.\d+)?", s)
    if not m:
        raise ValueError_(f"not a number: {raw!r}")
    return float(m.group())


def parse_date(raw: Any) -> date:
    if isinstance(raw, date):
        return raw
    s = str(raw).strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%m-%d-%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    raise ValueError_(f"not a date (use YYYY-MM-DD): {raw!r}")


def _bool(raw: Any) -> bool:
    if isinstance(raw, bool):
        return raw
    s = str(raw).strip().lower()
    if s in {"true", "yes", "y", "1", "required", "met"}:
        return True
    if s in {"false", "no", "n", "0", "not required", "not met"}:
        return False
    raise ValueError_(f"not true/false: {raw!r}")


def coerce(spec: FieldSpec, raw: Any) -> Any:
    if spec.kind == "pct":
        v = _num(raw)
        if not 0 <= v <= 100:
            raise ValueError_("percent must be 0-100")
        return int(round(v))
    if spec.kind == "money":
        v = _num(raw)
        return int(v) if v.is_integer() else v
    if spec.kind == "int":
        return int(round(_num(raw)))
    if spec.kind == "bool":
        return _bool(raw)
    if spec.kind == "date":
        return parse_date(raw)
    if spec.kind == "enum":
        s = str(raw).strip().lower().replace(" ", "_").replace("-", "_")
        for c in spec.choices:
            if s and (s == c or s.startswith(c) or c.startswith(s)):
                return c
        raise ValueError_(f"must be one of {', '.join(spec.choices)}")
    s = str(raw).strip()
    if not s:
        raise ValueError_("empty value")
    return s


def _speak(spec: FieldSpec, value: Any) -> str:
    """How a captured value is said aloud during read-back."""
    if value is None:
        return "not provided"
    if spec.kind == "money":
        return sf.money(value)
    if spec.kind == "pct":
        return f"{sf.number_to_words(value)} percent"
    if spec.kind == "date":
        return sf.spoken_date(value)
    if spec.kind == "bool":
        return "yes" if value else "no"
    return str(value).replace("_", " ")


def _unslash(text: str) -> str:
    """'1 per quadrant / 24 months' -> '1 per quadrant every 24 months' (TTS would say 'slash')."""
    return re.sub(r"\s*/\s*", " every ", text)


class CallState:
    def __init__(self, scenario: Scenario, call_sid: str = "sim", today: date | None = None):
        self.scenario = scenario
        self.call_sid = call_sid
        self.today = today or date.today()
        self.stage = "ivr"
        self.values: dict[str, Captured] = {p: Captured() for p in SPECS}
        self.quadrants: dict[str, QuadrantCapture] = {q: QuadrantCapture() for q in QUADRANTS}
        self.transcript: list[Turn] = []
        self.events: list[dict] = []
        self.digits_sent: list[str] = []
        self.member_not_found_count = 0
        self.rep_first_name: str | None = None
        self.readback_done = False
        self.resume_stage: str | None = None  # stage to return to after a mid-call hold
        self.asked_before_leaving = False  # rep wanted to go; we asked once for the reference
        self.ended_reason: str | None = None
        self.connected_at = time.time()
        self.human_at: float | None = None
        self.ended_at: float | None = None

    # ---------- transcript ----------

    def add_turn(self, speaker: str, text: str) -> int:
        text = (text or "").strip()
        if not text:
            return self.last_rep_turn() or 0
        turn = Turn(len(self.transcript), speaker, text, time.time())
        self.transcript.append(turn)
        return turn.idx

    def last_rep_turn(self) -> int | None:
        for t in reversed(self.transcript):
            if t.speaker == "rep":
                return t.idx
        return None

    def last_rep_text(self) -> str | None:
        i = self.last_rep_turn()
        return self.transcript[i].text if i is not None else None

    def log(self, event: str, **data) -> None:
        self.events.append({"t": round(time.time() - self.connected_at, 1), "event": event, **data})

    @property
    def muted(self) -> bool:
        """On hold the agent must not speak at all."""
        return self.stage == "hold"

    # ---------- recording ----------

    def record(self, path: str, raw: Any, quote: str | None = None) -> str | None:
        """Store a value. Returns an error message for the LLM, or None on success."""
        spec = SPECS.get(path)
        if spec is None:
            return f"unknown path {path!r}"
        try:
            value = coerce(spec, raw)
        except ValueError as e:
            return f"{path}: {e}"
        cap = self.values[path]
        changed = cap.status in RESOLVED and cap.value is not None and cap.value != value
        if changed:
            cap.previous_value = cap.value
        # A value the rep changes during read-back or close is a correction.
        corrected = changed and self.stage in ("readback", "close")
        cap.value = value
        cap.status = FieldStatus.CORRECTED if corrected else FieldStatus.ANSWERED
        cap.quote, cap.turn = quote or self.last_rep_text(), self.last_rep_turn()
        cap.stage = self.stage
        self.log("record", path=path, value=str(value))
        return None

    def mark(self, path: str, status: FieldStatus, quote: str | None = None) -> str | None:
        if path.startswith("srp.history."):
            q = path.rsplit(".", 1)[-1]
            if q not in self.quadrants:
                return f"unknown quadrant {q!r}"
            qc = self.quadrants[q]
            qc.status, qc.quote, qc.turn = status, quote or self.last_rep_text(), self.last_rep_turn()
        elif path in self.values:
            cap = self.values[path]
            cap.value, cap.status = None, status
            cap.quote, cap.turn = quote or self.last_rep_text(), self.last_rep_turn()
        else:
            return f"unknown path {path!r}"
        self.log("mark", path=path, status=status.value)
        return None

    def correct(self, path: str, raw: Any, quote: str | None = None) -> str | None:
        """A correction the rep made on read-back: keeps the old value for the audit trail."""
        before = self.values[path].value if path in self.values else None
        err = self.record(path, raw, quote)
        if err:
            return err
        cap = self.values[path]
        cap.previous_value = before
        cap.status = FieldStatus.CORRECTED
        return None

    def record_quadrant(self, q: str, on_file: bool, code: str | None = None,
                        paid: Any = None, quote: str | None = None) -> str | None:
        q = q.upper()
        if q not in self.quadrants:
            return f"quadrant must be one of {', '.join(QUADRANTS)}"
        qc = self.quadrants[q]
        if on_file:
            # On file without a date is still data ("shows paid, can't see the date"):
            # keep it, and its next eligible date stays unknown.
            try:
                qc.paid = parse_date(paid) if paid else None
            except ValueError as e:
                return str(e)
            qc.code = (code or "").upper() or None
        else:
            qc.paid, qc.code = None, None
        qc.on_file, qc.status = on_file, FieldStatus.ANSWERED
        qc.quote, qc.turn = quote or self.last_rep_text(), self.last_rep_turn()
        self.log("quadrant", quadrant=q, on_file=on_file, paid=str(qc.paid))
        return None

    # ---------- derived ----------

    def value(self, path: str) -> Any:
        return self.values[path].value if path in self.values else None

    def next_eligible(self, q: str) -> str | None:
        qc = self.quadrants[q]
        if qc.status not in RESOLVED or qc.on_file is None:
            return None
        if qc.on_file and qc.paid is None:
            return None  # paid, date unknown
        return next_eligible(qc.paid, self.value("srp.frequency_months"), self.today)

    def resolved(self, path: str) -> bool:
        if path.startswith("srp.history."):
            return self.quadrants[path.rsplit(".", 1)[-1]].status in RESOLVED
        return self.values[path].status in RESOLVED

    def missing(self, stage: str) -> list[str]:
        """Required checklist items of a stage that are not resolved yet."""
        items = [f.path for f in fields_for(stage, required_only=True)]
        if stage == "history":
            items = [f"srp.history.{q}" for q in QUADRANTS] + items
        return [p for p in items if not self.resolved(p) or (p == "call.rep" and not self._rep_name_complete())]

    def _rep_name_complete(self) -> bool:
        """A first name heard in passing ("this is Haider") isn't the full name yet. Once we
        asked in close, whatever the rep gave is final (no asking twice)."""
        cap = self.values["call.rep"]
        return cap.value is None or len(str(cap.value).split()) >= 2 or cap.stage == "close"

    def close_out_pending(self) -> None:
        """End of call: anything never asked becomes an explicit not_asked null, never a guess."""
        for cap in self.values.values():
            if cap.status == FieldStatus.PENDING:
                cap.value, cap.status = None, FieldStatus.NOT_ASKED
        for qc in self.quadrants.values():
            if qc.status == FieldStatus.PENDING:
                qc.status = FieldStatus.NOT_ASKED

    def stage_done(self, stage: str) -> bool:
        if stage == "readback":
            return self.readback_done
        return not self.missing(stage)

    def next_stage(self, after: str | None = None) -> str:
        """The stage to run after `after` (default: the current one), skipping stages
        already fully answered. Close is skipped too when the rep already gave its items."""
        order = STAGES
        after = after or self.stage
        if after in ("ivr", "hold"):
            start = order.index("verify")
        else:
            start = order.index(after) + 1
        for s in order[start:]:
            if s in SKIPPABLE and self.stage_done(s):
                continue
            return s
        return "end"

    # ---------- text for prompts and read-back ----------

    def ask_for(self, path: str) -> str:
        if path.startswith("srp.history."):
            q = path.rsplit(".", 1)[-1]
            return f"SRP claim history for the {QUADRANT_NAMES[q]} ({q}) quadrant"
        return SPECS[path].ask

    def captured_lines(self) -> list[str]:
        out = []
        for p, cap in self.values.items():
            if cap.status in RESOLVED:
                v = cap.value if cap.value is not None else f"<{cap.status.value}>"
                out.append(f"{p} = {v}")
        for q, qc in self.quadrants.items():
            if qc.status in RESOLVED:
                what = f"paid {qc.paid} ({qc.code})" if qc.on_file else (
                    "nothing on file" if qc.on_file is False else f"<{qc.status.value}>")
                out.append(f"srp.history.{q} = {what}; next eligible {self.next_eligible(q)}")
        return out

    def quadrant_summary_spoken(self) -> str:
        paid: dict[date, list[str]] = {}
        open_q, unknown = [], []
        for q, qc in self.quadrants.items():
            if qc.on_file and qc.paid:
                paid.setdefault(qc.paid, []).append(QUADRANT_NAMES[q])
            elif qc.on_file is False:
                open_q.append(QUADRANT_NAMES[q])
            else:
                unknown.append(QUADRANT_NAMES[q])
        parts = [f"{' and '.join(qs)} paid {sf.spoken_date(d)}" for d, qs in paid.items()]
        if open_q:
            parts.append(f"{' and '.join(open_q)} have nothing on file")
        if unknown:
            parts.append(f"{' and '.join(unknown)} not confirmed")
        return "; ".join(parts)

    def readback_script(self) -> str:
        """The read-back, generated from state (not LLM memory), ready to be spoken."""
        v, S = self.value, SPECS
        p = self.scenario.patient
        say = lambda path: _speak(S[path], v(path))  # noqa: E731
        lines = [f"Let me read this back. {p.name}"]
        if v("member.active") is not None:
            lines.append("active" if v("member.active") else "not active")
        if v("member.benefit_year"):
            lines.append(f"{say('member.benefit_year')} year plan")
        c1, c2 = v("srp.codes.D4341.coverage_pct"), v("srp.codes.D4342.coverage_pct")
        if c1 is not None and c1 == c2:
            lines.append(f"D forty-three forty-one and D forty-three forty-two at {say('srp.codes.D4341.coverage_pct')}")
        else:
            lines.append(f"D forty-three forty-one at {say('srp.codes.D4341.coverage_pct')}, "
                         f"D forty-three forty-two at {say('srp.codes.D4342.coverage_pct')}")
        if v("srp.deductible.amount") is not None:
            met = v("srp.deductible.met")
            lines.append(f"{say('srp.deductible.amount')} deductible, "
                         f"{'met' if met else 'not met' if met is False else 'status unknown'}")
        if v("srp.remaining") is not None or v("srp.annual_max") is not None:
            lines.append(f"{say('srp.remaining')} remaining of a {say('srp.annual_max')} maximum")
        if v("srp.frequency"):
            lines.append(f"frequency {_unslash(v('srp.frequency'))}")
        lines.append(self.quadrant_summary_spoken())
        if v("srp.quadrants_per_dos") is not None:
            lines.append(f"{sf.number_to_words(v('srp.quadrants_per_dos'))} quadrants per date of service")
        docs = []
        if v("srp.documentation.perio_charting"):
            docs.append("perio charting")
        if v("srp.documentation.radiographs"):
            docs.append("radiographs")
        if docs:
            depth = v("srp.documentation.min_pocket_depth_mm")
            bone = " with bone loss" if v("srp.documentation.bone_loss_required") else ""
            lines.append(f"{' and '.join(docs)} required"
                         + (f", {sf.number_to_words(depth)} millimeter pockets{bone}" if depth else ""))
        if v("srp.documentation.preauth"):
            lines.append(f"pre-authorization {say('srp.documentation.preauth')}")
        if v("srp.downgrade.to"):
            lines.append(f"downgrades to {v('srp.downgrade.to')} if documentation is insufficient")
        if v("d4910.coverage_pct") is not None:
            shared = ", shared with prophy" if v("d4910.shared_with_d1110") else ""
            wait = v("d4910.wait_after_srp_days")
            lines.append(f"D forty-nine ten at {say('d4910.coverage_pct')}, {_unslash(v('d4910.frequency') or '')}{shared}"
                         + (f", {sf.number_to_words(wait)} days after SRP" if wait else ""))
        return ". ".join(x for x in lines if x) + ". Is anything wrong?"

    # ---------- timing ----------

    def mark_human(self) -> None:
        if self.human_at is None:
            self.human_at = time.time()

    @property
    def hold_sec(self) -> int | None:
        return round(self.human_at - self.connected_at) if self.human_at else None

    @property
    def duration_sec(self) -> int:
        return round((self.ended_at or time.time()) - self.connected_at)
