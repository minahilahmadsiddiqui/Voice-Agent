"""The checklist: every benefit field the call must resolve, which stage asks for it,
its value type, and how to ask for it.

This registry drives everything: the stage prompts ("still missing: ..."), tool schemas
(which paths the LLM may record), value coercion, the read-back script and the scorecard.
"""

from dataclasses import dataclass

STAGES = ["ivr", "hold", "verify", "benefits", "history", "rules", "maintenance", "readback", "close", "end"]
QUADRANTS = ["UR", "UL", "LR", "LL"]
QUADRANT_NAMES = {"UR": "upper right", "UL": "upper left", "LR": "lower right", "LL": "lower left"}


@dataclass(frozen=True)
class FieldSpec:
    path: str
    kind: str  # pct | money | int | bool | date | str | enum
    stage: str
    ask: str  # what to find out, in plain words (shown to the agent LLM)
    required: bool = True
    choices: tuple[str, ...] = ()


FIELDS: list[FieldSpec] = [
    # --- verify: member eligibility (identity fields come from the scenario) ---
    FieldSpec("member.active", "bool", "verify", "is coverage active"),
    FieldSpec("member.effective", "date", "verify", "coverage effective date"),
    FieldSpec("member.benefit_year", "enum", "verify", "calendar year or plan year",
              choices=("calendar", "plan", "fiscal")),
    FieldSpec("member.subscriber", "bool", "verify", "is the patient the subscriber", required=False),
    # --- benefits: the numbers a percentage is worthless without ---
    FieldSpec("srp.codes.D4341.coverage_pct", "pct", "benefits", "coverage percent for D4341"),
    FieldSpec("srp.codes.D4342.coverage_pct", "pct", "benefits", "coverage percent for D4342"),
    FieldSpec("srp.benefit_class", "enum", "benefits", "benefit class SRP falls under",
              choices=("preventive", "basic", "major")),
    FieldSpec("srp.deductible.amount", "money", "benefits", "individual deductible amount"),
    FieldSpec("srp.deductible.met", "bool", "benefits", "has the deductible been met this year"),
    FieldSpec("srp.deductible.applies_to_srp", "bool", "benefits",
              "does the deductible apply to SRP", required=False),
    FieldSpec("srp.annual_max", "money", "benefits", "annual maximum"),
    FieldSpec("srp.remaining", "money", "benefits", "remaining annual maximum"),
    FieldSpec("srp.frequency", "str", "benefits",
              "SRP frequency limitation, normalized like '1 per quadrant / 24 months'"),
    FieldSpec("srp.frequency_months", "int", "benefits", "length of the SRP frequency window in months"),
    # --- history: per-quadrant claims (recorded with record_quadrant) + how it's counted ---
    FieldSpec("srp.frequency_counting", "enum", "history",
              "is the frequency counted date of service to date of service, or by calendar/benefit year",
              choices=("date_of_service", "calendar_year", "benefit_year")),
    # --- rules: documentation, downgrades, scheduling ---
    FieldSpec("srp.documentation.perio_charting", "bool", "rules", "is perio charting required"),
    FieldSpec("srp.documentation.radiographs", "bool", "rules", "are radiographs (x-rays) required"),
    FieldSpec("srp.documentation.narrative", "bool", "rules", "is a narrative required", required=False),
    FieldSpec("srp.documentation.min_pocket_depth_mm", "int", "rules", "minimum pocket depth in mm"),
    FieldSpec("srp.documentation.bone_loss_required", "bool", "rules", "must radiographs show bone loss"),
    FieldSpec("srp.documentation.preauth", "enum", "rules", "is pre-authorization required",
              choices=("required", "recommended_not_required", "not_required")),
    FieldSpec("srp.downgrade.to", "str", "rules", "procedure code SRP downgrades to, e.g. D1110"),
    FieldSpec("srp.downgrade.trigger", "str", "rules",
              "when the downgrade happens, snake_case, e.g. documentation_does_not_support_diagnosis"),
    FieldSpec("srp.quadrants_per_dos", "int", "rules", "how many quadrants per date of service"),
    # --- maintenance: D4910 ---
    FieldSpec("d4910.coverage_pct", "pct", "maintenance", "coverage percent for D4910 periodontal maintenance"),
    FieldSpec("d4910.frequency", "str", "maintenance", "D4910 frequency, normalized like '2 per calendar year'"),
    FieldSpec("d4910.shared_with_d1110", "bool", "maintenance", "does D4910 share its frequency with D1110 prophy"),
    FieldSpec("d4910.wait_after_srp_days", "int", "maintenance",
              "waiting period in days between SRP and the first D4910"),
    # --- close: what makes the quote defensible ---
    FieldSpec("call.reference", "str", "close", "call reference number (digits only)"),
    FieldSpec("call.rep", "str", "close", "rep's full name"),
    FieldSpec("call.disclaimer", "str", "close", "the rep's disclaimer, word for word"),
]

SPECS: dict[str, FieldSpec] = {f.path: f for f in FIELDS}

# Member identity comes from the scenario, not the rep.
PROVIDED_PATHS = ["member.name", "member.dob", "member.member_id"]

# Quadrant history lives at srp.history.<Q>; each quadrant is one checklist item of the history stage.
QUADRANT_PATHS = [f"srp.history.{q}" for q in QUADRANTS]

RECORDABLE_PATHS = [f.path for f in FIELDS]


def fields_for(stage: str, required_only: bool = False) -> list[FieldSpec]:
    return [f for f in FIELDS if f.stage == stage and (f.required or not required_only)]


def field_guide() -> str:
    """One line per recordable path, for the agent's role prompt."""
    lines = []
    for f in FIELDS:
        fmt = {
            "pct": "integer percent", "money": "number in dollars", "int": "integer",
            "bool": "true/false", "date": "YYYY-MM-DD", "str": "text",
            "enum": " | ".join(f.choices),
        }[f.kind]
        lines.append(f"- {f.path}: {f.ask} ({fmt})")
    return "\n".join(lines)


# ---------- what the agent says next: scripted in code, not generated ----------
# After the rep answers, the LLM only records the facts; the code picks the next question
# from this list (first group with anything still missing). One LLM round trip per turn
# instead of two, and the order can't drift. Wording follows the reference call.

QUESTIONS: dict[str, list[tuple[tuple[str, ...], str]]] = {
    "benefits": [
        (("srp.codes.D4341.coverage_pct", "srp.codes.D4342.coverage_pct", "srp.benefit_class"),
         "Benefits for scaling and root planing. What's the coverage percentage for D4341 and D4342?"),
        (("srp.deductible.amount", "srp.deductible.met"), "What's the deductible, and how much has she met this year?"),
        (("srp.annual_max", "srp.remaining"), "And the annual maximum, and how much is remaining?"),
        (("srp.frequency", "srp.frequency_months"), "What's the frequency limitation on SRP?"),
    ],
    "rules": [
        (("srp.documentation.perio_charting", "srp.documentation.radiographs",
          "srp.documentation.min_pocket_depth_mm", "srp.documentation.bone_loss_required", "srp.documentation.preauth"),
         "What are the documentation requirements for SRP? Charting, radiographs, narrative, pre-authorization?"),
        (("srp.downgrade.to", "srp.downgrade.trigger"), "Does SRP ever downgrade, and to what?"),
        (("srp.quadrants_per_dos",), "How many quadrants per date of service?"),
    ],
    "maintenance": [
        (("d4910.coverage_pct", "d4910.frequency", "d4910.shared_with_d1110"),
         "And periodontal maintenance, D4910. Coverage, frequency, and how does it interact with D1110?"),
        (("d4910.wait_after_srp_days",), "Any waiting period between the SRP and the first D4910?"),
    ],
}

# When only part of a group is missing, ask just for that part.
FOLLOWUPS: dict[str, str] = {
    "srp.codes.D4341.coverage_pct": "And the coverage percentage for D4341?",
    "srp.codes.D4342.coverage_pct": "And for D4342, the one to three teeth code?",
    "srp.benefit_class": "Is that basic or major?",
    "srp.deductible.amount": "And what's the deductible amount?",
    "srp.deductible.met": "Has she met the deductible this year?",
    "srp.annual_max": "And what's the annual maximum?",
    "srp.remaining": "And how much is remaining?",
    "srp.frequency": "What's the frequency limitation on SRP?",
    "srp.frequency_months": "How many months is that frequency window?",
    "srp.documentation.perio_charting": "Is perio charting required?",
    "srp.documentation.radiographs": "Are radiographs required?",
    "srp.documentation.min_pocket_depth_mm": "Is there a minimum pocket depth?",
    "srp.documentation.bone_loss_required": "Do the radiographs need to show bone loss?",
    "srp.documentation.preauth": "Is pre-authorization required?",
    "srp.downgrade.to": "Does SRP ever downgrade, and to what?",
    "srp.downgrade.trigger": "When does that downgrade happen?",
    "srp.quadrants_per_dos": "How many quadrants per date of service?",
    "d4910.coverage_pct": "What's the coverage for D4910?",
    "d4910.frequency": "And how often is D4910 covered?",
    "d4910.shared_with_d1110": "Does D4910 share that frequency with regular prophy?",
    "d4910.wait_after_srp_days": "Any waiting period between the SRP and the first D4910?",
}
