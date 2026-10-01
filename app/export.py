"""CallState -> output JSON, in two shapes.

1. `export_sourced`: the full BenefitsVerification model. Every field carries its value,
   status, the rep's exact words and the transcript turn it came from.
2. `export_reference`: exactly the shape of Amplify's reference PDF, so reviewers can
   compare line by line. Unanswered fields are explicit nulls.
"""

from datetime import date
from typing import Any

from app.fields import QUADRANTS
from app.schema import BenefitsVerification, FieldStatus
from app.state import CallState


def _iso(v: Any) -> Any:
    return v.isoformat() if isinstance(v, date) else v


def _set(tree: dict, path: str, value: Any) -> None:
    *parents, leaf = path.split(".")
    node = tree
    for key in parents:
        node = node.setdefault(key, {})
    node[leaf] = value


def export_sourced(state: CallState) -> BenefitsVerification:
    tree: dict = {}
    for path, cap in state.values.items():
        _set(tree, path, {
            "value": _iso(cap.value), "status": cap.status.value, "quote": cap.quote, "turn": cap.turn,
            "previous_value": _iso(cap.previous_value), "source": cap.source,
        })
    pt = state.scenario.patient
    for key, value in (("name", pt.name), ("dob", pt.dob), ("member_id", pt.member_id)):
        tree.setdefault("member", {})[key] = {"value": value, "status": FieldStatus.PROVIDED.value, "source": "scenario"}
    history = {}
    for q, qc in state.quadrants.items():
        history[q] = {
            "status": qc.status.value, "on_file": qc.on_file, "code": qc.code, "paid": _iso(qc.paid),
            "next_eligible": state.next_eligible(q), "quote": qc.quote, "turn": qc.turn, "source": qc.source,
        }
    tree.setdefault("srp", {})["history"] = history
    call = tree.setdefault("call", {})
    call.update({"call_sid": state.call_sid, "hold_sec": state.hold_sec, "duration_sec": state.duration_sec})
    return BenefitsVerification.model_validate(tree)


def export_reference(state: CallState) -> dict:
    v = lambda p: _iso(state.value(p))  # noqa: E731
    pt = state.scenario.patient

    frequency = v("srp.frequency")
    if frequency and v("srp.frequency_counting") == "date_of_service":
        frequency += ", date-of-service to date-of-service"
    d4910_freq = v("d4910.frequency")
    if d4910_freq and v("d4910.shared_with_d1110"):
        d4910_freq += ", shared with D1110"

    subscriber = v("member.subscriber")
    if subscriber is None:
        subscriber = pt.relationship == "subscriber"

    on_file = [q for q in QUADRANTS if state.quadrants[q].on_file]
    rest = [q for q in QUADRANTS if q not in on_file]
    history = [{
        "quadrant": q,
        "code": state.quadrants[q].code,
        "paid": _iso(state.quadrants[q].paid),
        "next_eligible": state.next_eligible(q),
    } for q in on_file + rest]

    return {
        "member": {
            "name": pt.name, "dob": pt.dob, "member_id": pt.member_id, "subscriber": subscriber,
            "active": v("member.active"), "effective": v("member.effective"),
            "benefit_year": v("member.benefit_year"),
        },
        "srp": {
            "codes": {c: {"coverage_pct": v(f"srp.codes.{c}.coverage_pct")} for c in ("D4341", "D4342")},
            "class": v("srp.benefit_class"),
            "deductible": {"amount": v("srp.deductible.amount"), "met": v("srp.deductible.met")},
            "annual_max": v("srp.annual_max"),
            "remaining": v("srp.remaining"),
            "remaining_corrected_on_readback": state.values["srp.remaining"].status == FieldStatus.CORRECTED,
            "frequency": frequency,
            "quadrants_per_dos": v("srp.quadrants_per_dos"),
            "history": history,
            "documentation": {
                "perio_charting": v("srp.documentation.perio_charting"),
                "radiographs": v("srp.documentation.radiographs"),
                "min_pocket_depth_mm": v("srp.documentation.min_pocket_depth_mm"),
                "bone_loss_required": v("srp.documentation.bone_loss_required"),
                "preauth": v("srp.documentation.preauth"),
            },
            "downgrade": {"to": v("srp.downgrade.to"), "trigger": v("srp.downgrade.trigger")},
        },
        "d4910": {
            "coverage_pct": v("d4910.coverage_pct"),
            "frequency": d4910_freq,
            "wait_after_srp_days": v("d4910.wait_after_srp_days"),
        },
        "call": {
            "rep": v("call.rep"), "reference": v("call.reference"),
            "hold_sec": state.hold_sec, "duration_sec": state.duration_sec,
            "disclaimer": v("call.disclaimer"), "source": "payer_rep_verbal",
        },
    }
