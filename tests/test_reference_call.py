"""Replays Amplify's reference call through the real tools (no LLM) and checks that
the stage flow is right and the output matches the PDF's structured JSON exactly."""

from datetime import date

from app.callflow.tools import run_tool
from app.config import load_scenario
from app.export import export_reference, export_sourced
from app.state import CallState

# The structured output printed in the reference PDF.
PDF_JSON = {
    "member": {"name": "Lana Kane", "dob": "1983-07-09", "member_id": "MDB40719883",
               "subscriber": True, "active": True, "effective": "2024-03-01", "benefit_year": "calendar"},
    "srp": {"codes": {"D4341": {"coverage_pct": 80}, "D4342": {"coverage_pct": 80}},
            "class": "basic", "deductible": {"amount": 50, "met": True},
            "annual_max": 1500, "remaining": 1247, "remaining_corrected_on_readback": True,
            "frequency": "1 per quadrant / 24 months, date-of-service to date-of-service",
            "quadrants_per_dos": 2,
            "history": [{"quadrant": "UR", "code": "D4341", "paid": "2025-02-04", "next_eligible": "2027-02-04"},
                        {"quadrant": "LR", "code": "D4341", "paid": "2025-02-04", "next_eligible": "2027-02-04"},
                        {"quadrant": "UL", "code": None, "paid": None, "next_eligible": "now"},
                        {"quadrant": "LL", "code": None, "paid": None, "next_eligible": "now"}],
            "documentation": {"perio_charting": True, "radiographs": True, "min_pocket_depth_mm": 4,
                              "bone_loss_required": True, "preauth": "recommended_not_required"},
            "downgrade": {"to": "D1110", "trigger": "documentation_does_not_support_diagnosis"}},
    "d4910": {"coverage_pct": 80, "frequency": "2 per calendar year, shared with D1110",
              "wait_after_srp_days": 90},
    "call": {"rep": "Denise Okafor", "reference": "771402988", "hold_sec": 521, "duration_sec": 862,
             "disclaimer": "Not a guarantee of payment. Benefits subject to eligibility and plan "
                           "limitations at time of service.", "source": "payer_rep_verbal"},
}


def rep(state, text):
    state.add_turn("rep", text)


def f(path, value, quote="(quote)"):
    return {"path": path, "value": value, "quote": quote}


def test_reference_call_end_to_end():
    s = CallState(load_scenario("lana_kane"), today=date(2026, 9, 21))
    s.connected_at = 1000.0

    # Phone menu -> hold -> human
    s.add_turn("ivr", "For eligibility and benefits, say benefits or press one.")
    s.add_turn("ivr", "Please enter the provider tax ID, followed by the pound key.")
    o = run_tool(s, "press_digits", {"digits": "841552037#"})
    assert o.dtmf == "841552037#" and not o.respond
    run_tool(s, "on_hold", {})
    assert s.stage == "hold" and s.muted
    s.human_at = 1521.0
    rep(s, "Thanks for holding, Meridian provider services, this is Denise.")
    o = run_tool(s, "human_detected", {"rep_first_name": "Denise"})
    assert s.stage == "verify" and not s.muted

    rep(s, "I have her. Coverage is active, effective 03/01/2024, calendar year plan.")
    o = run_tool(s, "record_fields", {"fields": [
        f("member.active", True), f("member.effective", "03/01/2024"), f("member.benefit_year", "calendar year")]})
    assert o.next_stage == "benefits"

    rep(s, "Periodontics is basic. Both 80% after deductible, in network.")
    run_tool(s, "record_fields", {"fields": [
        f("srp.codes.D4341.coverage_pct", "80%"), f("srp.codes.D4342.coverage_pct", 80),
        f("srp.benefit_class", "basic")]})
    rep(s, "Fifty dollars individual, and it's met.")
    run_tool(s, "record_fields", {"fields": [f("srp.deductible.amount", "$50"), f("srp.deductible.met", "yes")]})
    rep(s, "Fifteen hundred, with $1,340 remaining.")
    run_tool(s, "record_fields", {"fields": [f("srp.annual_max", 1500), f("srp.remaining", "$1,340")]})
    rep(s, "Once per quadrant every 24 months.")
    o = run_tool(s, "record_fields", {"fields": [
        f("srp.frequency", "1 per quadrant / 24 months"), f("srp.frequency_months", 24)]})
    assert o.next_stage == "history"

    rep(s, "I show D4341 paid twice on 02/04/2025, upper right and lower right.")
    o = run_tool(s, "record_quadrant", {"quadrants": [
        {"quadrant": "UR", "on_file": True, "code": "D4341", "paid_date": "2025-02-04", "quote": "x"},
        {"quadrant": "LR", "on_file": True, "code": "D4341", "paid_date": "02/04/2025", "quote": "x"}]})
    assert "2027-02-04" in o.result["next_eligible"]["UR"]
    assert s.stage == "history"  # UL / LL and counting method still open
    rep(s, "Correct, nothing for those.")
    run_tool(s, "record_quadrant", {"quadrants": [
        {"quadrant": "UL", "on_file": False, "quote": "nothing"}, {"quadrant": "LL", "on_file": False, "quote": "nothing"}]})
    rep(s, "Yes, 24 months from date of service.")
    o = run_tool(s, "record_fields", {"fields": [f("srp.frequency_counting", "date of service")]})
    assert o.next_stage == "rules"

    rep(s, "Perio charting with pocket depths and radiographs. Four millimeters or greater, with bone loss. "
           "Pre-treatment estimate is recommended, not required.")
    run_tool(s, "record_fields", {"fields": [
        f("srp.documentation.perio_charting", True), f("srp.documentation.radiographs", True),
        f("srp.documentation.min_pocket_depth_mm", 4), f("srp.documentation.bone_loss_required", True),
        f("srp.documentation.preauth", "recommended_not_required")]})
    rep(s, "If documentation doesn't support the diagnosis it processes as a prophy.")
    run_tool(s, "record_fields", {"fields": [
        f("srp.downgrade.to", "D1110"), f("srp.downgrade.trigger", "documentation_does_not_support_diagnosis")]})
    rep(s, "Two.")
    o = run_tool(s, "record_fields", {"fields": [f("srp.quadrants_per_dos", 2)]})
    assert o.next_stage == "maintenance"

    rep(s, "80%, twice per calendar year, shared with regular prophy.")
    run_tool(s, "record_fields", {"fields": [
        f("d4910.coverage_pct", 80), f("d4910.frequency", "2 per calendar year"), f("d4910.shared_with_d1110", True)]})
    rep(s, "Ninety days.")
    o = run_tool(s, "record_fields", {"fields": [f("d4910.wait_after_srp_days", 90)]})
    assert o.next_stage == "readback"

    script = s.readback_script()
    assert "one thousand three hundred forty dollars remaining" in script
    assert "upper right and lower right paid February fourth, twenty twenty-five" in script
    assert "upper left and lower left have nothing on file" in script

    rep(s, "One thing, the $1,340 was before a claim finalized last week. Remaining is $1,247.")
    o = run_tool(s, "readback_done", {"corrections": [f("srp.remaining", 1247, "Remaining is $1,247.")]})
    assert o.next_stage == "close"

    rep(s, "Reference 771402988. Denise Okafor.")
    run_tool(s, "record_fields", {"fields": [f("call.reference", "771402988"), f("call.rep", "Denise Okafor")]})
    rep(s, "Correct. Benefits are subject to eligibility and plan limitations at the time of service.")
    o = run_tool(s, "record_fields", {"fields": [f("call.disclaimer", PDF_JSON["call"]["disclaimer"])]})
    assert o.next_stage == "end" and s.ended_reason == "completed"
    s.ended_at = 1862.0

    assert export_reference(s) == PDF_JSON

    sourced = export_sourced(s)
    assert sourced.srp.remaining.value == 1247
    assert sourced.srp.remaining.previous_value == 1340
    assert sourced.srp.remaining.status.value == "corrected_on_readback"
    assert sourced.srp.remaining.quote == "Remaining is $1,247."
    assert sourced.srp.history["UL"].on_file is False
    assert sourced.member.name.status.value == "provided"


def test_unanswered_fields_are_null_never_guessed():
    s = CallState(load_scenario("lana_kane"), today=date(2026, 9, 21))
    out = export_reference(s)
    assert out["srp"]["annual_max"] is None
    assert out["srp"]["codes"]["D4341"]["coverage_pct"] is None
    assert all(h["next_eligible"] is None for h in out["srp"]["history"])


def test_stage_skips_what_was_volunteered_early():
    s = CallState(load_scenario("lana_kane"), today=date(2026, 9, 21))
    s.stage = "verify"
    # Rep volunteers all D4910 answers during verification.
    run_tool(s, "record_fields", {"fields": [
        f("d4910.coverage_pct", 80), f("d4910.frequency", "2 per year"),
        f("d4910.shared_with_d1110", True), f("d4910.wait_after_srp_days", 90)]})
    # Finish verify; flow should later jump from rules straight to readback.
    run_tool(s, "record_fields", {"fields": [f("member.active", True), f("member.effective", "2024-03-01"),
                                              f("member.benefit_year", "calendar")]})
    assert s.stage == "benefits"
    s.stage = "rules"
    o = run_tool(s, "record_fields", {"fields": [
        f("srp.documentation.perio_charting", True), f("srp.documentation.radiographs", True),
        f("srp.documentation.min_pocket_depth_mm", 4), f("srp.documentation.bone_loss_required", True),
        f("srp.documentation.preauth", "required"), f("srp.downgrade.to", "D1110"),
        f("srp.downgrade.trigger", "x"), f("srp.quadrants_per_dos", 2)]})
    assert o.next_stage == "readback"  # maintenance skipped: already answered


def test_bad_values_are_rejected_not_stored():
    s = CallState(load_scenario("lana_kane"))
    s.stage = "benefits"
    o = run_tool(s, "record_fields", {"fields": [f("srp.annual_max", "a lot"), f("srp.codes.D4341.coverage_pct", 180)]})
    assert len(o.result["errors"]) == 2
    assert s.value("srp.annual_max") is None


def test_tools_are_scoped_to_their_stage():
    s = CallState(load_scenario("lana_kane"))
    o = run_tool(s, "record_fields", {"fields": [f("srp.annual_max", 1500)]})  # still in ivr
    assert "not available" in o.result["error"]


def test_member_not_found_retries_once_then_closes():
    s = CallState(load_scenario("lana_kane"))
    s.stage = "verify"
    o = run_tool(s, "member_not_found", {})
    assert "M as in Mary" in o.result["member_id_phonetic"]
    assert s.stage == "verify"
    o = run_tool(s, "member_not_found", {})
    assert s.stage == "close" and s.ended_reason == "member_not_found"
