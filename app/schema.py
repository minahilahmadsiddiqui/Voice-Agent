"""Output schema: the structured SRP benefits object a call produces.

Mirrors Amplify's reference JSON, but every captured value is wrapped in `Sourced`
so it carries its status, the rep's exact words, and the transcript turn it came from.
A question the rep never answered stays `value=None` with status `unknown` - never a guess.
"""

from datetime import date
from enum import Enum
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")

Quadrant = Literal["UR", "UL", "LR", "LL"]


class FieldStatus(str, Enum):
    PENDING = "pending"  # not asked yet (only valid during a call)
    PROVIDED = "provided"  # our own input (from the scenario), accepted by the rep
    ANSWERED = "answered"
    REFUSED = "refused"  # rep declined to give it
    UNKNOWN = "unknown"  # asked, no usable answer
    CORRECTED = "corrected_on_readback"
    NEEDS_REVIEW = "needs_review"  # live capture and post-call extraction disagree
    NOT_ASKED = "not_asked"  # the call ended before we got to it (e.g. the rep had to leave)


class Sourced(BaseModel, Generic[T]):
    value: T | None = None
    status: FieldStatus = FieldStatus.PENDING
    quote: str | None = None  # the rep's exact words
    turn: int | None = None  # transcript turn index
    previous_value: T | None = None  # set when corrected on read-back
    source: Literal["live", "postcall", "scenario"] = "live"


class Member(BaseModel):
    name: Sourced[str] = Field(default_factory=Sourced)
    dob: Sourced[date] = Field(default_factory=Sourced)
    member_id: Sourced[str] = Field(default_factory=Sourced)
    subscriber: Sourced[bool] = Field(default_factory=Sourced)
    active: Sourced[bool] = Field(default_factory=Sourced)
    effective: Sourced[date] = Field(default_factory=Sourced)
    benefit_year: Sourced[Literal["calendar", "plan", "fiscal"]] = Field(default_factory=Sourced)


class CodeCoverage(BaseModel):
    coverage_pct: Sourced[int] = Field(default_factory=Sourced)


class Deductible(BaseModel):
    amount: Sourced[float] = Field(default_factory=Sourced)
    met: Sourced[bool] = Field(default_factory=Sourced)
    applies_to_srp: Sourced[bool] = Field(default_factory=Sourced)


class QuadrantHistory(BaseModel):
    status: FieldStatus = FieldStatus.PENDING
    on_file: bool | None = None  # False = rep confirmed nothing on file ("absence is data")
    code: str | None = None  # D4341 / D4342
    paid: date | None = None
    next_eligible: str | None = None  # ISO date, "now", or None if unknown (computed in code)
    quote: str | None = None
    turn: int | None = None
    source: Literal["live", "postcall"] = "live"


class Documentation(BaseModel):
    perio_charting: Sourced[bool] = Field(default_factory=Sourced)
    radiographs: Sourced[bool] = Field(default_factory=Sourced)
    narrative: Sourced[bool] = Field(default_factory=Sourced)
    min_pocket_depth_mm: Sourced[int] = Field(default_factory=Sourced)
    bone_loss_required: Sourced[bool] = Field(default_factory=Sourced)
    preauth: Sourced[Literal["required", "recommended_not_required", "not_required"]] = Field(
        default_factory=Sourced
    )


class Downgrade(BaseModel):
    to: Sourced[str] = Field(default_factory=Sourced)
    trigger: Sourced[str] = Field(default_factory=Sourced)


class SRP(BaseModel):
    codes: dict[str, CodeCoverage] = Field(
        default_factory=lambda: {"D4341": CodeCoverage(), "D4342": CodeCoverage()}
    )
    benefit_class: Sourced[Literal["preventive", "basic", "major"]] = Field(default_factory=Sourced)
    deductible: Deductible = Field(default_factory=Deductible)
    annual_max: Sourced[float] = Field(default_factory=Sourced)
    remaining: Sourced[float] = Field(default_factory=Sourced)
    frequency: Sourced[str] = Field(default_factory=Sourced)
    frequency_months: Sourced[int] = Field(default_factory=Sourced)
    frequency_counting: Sourced[str] = Field(default_factory=Sourced)  # e.g. "date_of_service"
    quadrants_per_dos: Sourced[int] = Field(default_factory=Sourced)
    history: dict[Quadrant, QuadrantHistory] = Field(
        default_factory=lambda: {q: QuadrantHistory() for q in ("UR", "UL", "LR", "LL")}
    )
    documentation: Documentation = Field(default_factory=Documentation)
    downgrade: Downgrade = Field(default_factory=Downgrade)


class PerioMaintenance(BaseModel):
    coverage_pct: Sourced[int] = Field(default_factory=Sourced)
    frequency: Sourced[str] = Field(default_factory=Sourced)
    shared_with_d1110: Sourced[bool] = Field(default_factory=Sourced)
    wait_after_srp_days: Sourced[int] = Field(default_factory=Sourced)


class CallInfo(BaseModel):
    rep: Sourced[str] = Field(default_factory=Sourced)
    reference: Sourced[str] = Field(default_factory=Sourced)
    disclaimer: Sourced[str] = Field(default_factory=Sourced)  # verbatim
    call_sid: str | None = None
    hold_sec: int | None = None
    duration_sec: int | None = None
    recording_url: str | None = None
    source: Literal["payer_rep_verbal"] = "payer_rep_verbal"


class BenefitsVerification(BaseModel):
    member: Member = Field(default_factory=Member)
    srp: SRP = Field(default_factory=SRP)
    d4910: PerioMaintenance = Field(default_factory=PerioMaintenance)
    call: CallInfo = Field(default_factory=CallInfo)
