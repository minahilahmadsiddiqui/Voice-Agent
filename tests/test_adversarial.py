"""Tricky rep behaviour: mid-call holds, early hang-ups, volunteered info, corrections."""

from app.callflow.tools import looks_like_person, run_tool
from app.config import load_scenario
from app.schema import FieldStatus
from app.state import CallState


def _state(stage="ivr"):
    s = CallState(load_scenario("lana_kane"))
    s.stage = stage
    return s


def test_mid_call_hold_returns_to_same_stage():
    s = _state("benefits")
    out = run_tool(s, "on_hold", {})
    assert s.stage == "hold" and s.muted and not out.respond
    out = run_tool(s, "human_detected", {})
    assert s.stage == "benefits" and not s.muted and s.resume_stage is None


def test_first_hold_still_goes_to_verify():
    s = _state("ivr")
    run_tool(s, "on_hold", {})
    run_tool(s, "human_detected", {"rep_first_name": "Haider"})
    assert s.stage == "verify"


def test_end_call_asks_for_reference_first():
    s = _state("benefits")
    run_tool(s, "end_call", {"reason": "rep has to go"})
    assert s.stage == "close"
    run_tool(s, "end_call", {"reason": "rep has to go"})
    assert s.stage == "end"


def test_quadrant_volunteered_during_benefits_is_kept():
    s = _state("benefits")
    out = run_tool(s, "record_quadrant", {"quadrants": [
        {"quadrant": "UR", "on_file": True, "code": "D4341", "paid_date": "2025-02-04", "quote": "UR paid 2/4/25"}]})
    assert "UR" in out.result["recorded"] and s.quadrants["UR"].on_file


def test_on_file_without_date_is_kept_with_unknown_eligibility():
    s = _state("history")
    out = run_tool(s, "record_quadrant", {"quadrants": [
        {"quadrant": "UL", "on_file": True, "quote": "shows paid, I can't see the date"}]})
    assert "UL" in out.result["recorded"]
    assert s.quadrants["UL"].on_file and s.next_eligible("UL") is None


def test_change_during_readback_counts_as_correction():
    s = _state("benefits")
    s.record("srp.remaining", "1340", "1340 remaining")
    s.stage = "readback"
    run_tool(s, "record_fields", {"fields": [{"path": "srp.remaining", "value": "1247", "quote": "it's 1247"}]})
    cap = s.values["srp.remaining"]
    assert cap.value == 1247 and cap.previous_value == 1340 and cap.status == FieldStatus.CORRECTED


def test_close_skipped_when_rep_gave_everything_early():
    s = _state("readback")
    for path, v in [("call.reference", "771402988"), ("call.rep", "Denise Okafor"),
                    ("call.disclaimer", "Not a guarantee of payment.")]:
        s.record(path, v, v)
    run_tool(s, "readback_done", {"corrections": []})
    assert s.stage == "end"


def test_empty_enum_is_rejected():
    s = _state("verify")
    assert s.record("member.benefit_year", "", "") is not None


def test_readback_never_says_slash():
    s = _state("benefits")
    s.record("srp.frequency", "1 per quadrant / 24 months", "once per quadrant every 24 months")
    assert "/" not in s.readback_script()


def test_person_vs_recording():
    assert looks_like_person("Thanks for holding, Meridian provider services, this is Denise.")
    assert looks_like_person("Hello?")
    assert looks_like_person("Who am I speaking with?")
    assert not looks_like_person("Thank you for holding. A representative will be with you shortly.")
    assert not looks_like_person("For eligibility and benefits, say benefits or press one.")
    assert not looks_like_person("Your call is important to us. Please continue to hold.")
    # Coming back from a mid-call hold with an answer
    assert looks_like_person("Okay so I show D4341 paid on February fourth", mid_call=True)
    assert not looks_like_person("Okay so I show D4341 paid on February fourth", mid_call=False)


def test_rep_who_insists_on_leaving_is_let_go_with_nulls():
    s = _state("rules")
    run_tool(s, "end_call", {"reason": "rep has to go"})
    assert s.stage == "close"  # asked once, politely
    run_tool(s, "end_call", {"reason": "rep insists"})
    assert s.stage == "end"  # never trapped
    s.close_out_pending()
    assert s.values["call.reference"].value is None
    assert s.values["call.reference"].status == FieldStatus.NOT_ASKED


def test_second_leave_request_from_another_stage_is_not_asked_again():
    s = _state("benefits")
    run_tool(s, "end_call", {"reason": "rep has to go"})
    s.stage = "maintenance"  # rep stayed a bit, then has to go again
    run_tool(s, "end_call", {"reason": "rep has to go now"})
    assert s.stage == "end"


def test_full_name_on_pickup_is_not_asked_again():
    s = _state("hold")
    run_tool(s, "human_detected", {"rep_full_name": "Haider Ali"})
    assert s.rep_first_name == "Haider" and s.value("call.rep") == "Haider Ali"
    assert "call.rep" not in s.missing("close")


def test_first_name_only_still_asks_for_full_name():
    s = _state("hold")
    run_tool(s, "human_detected", {"rep_first_name": "Haider"})
    s.stage = "verify"
    s.record("call.rep", "Haider", "this is Haider")
    assert "call.rep" in s.missing("close")
    s.stage = "close"
    s.record("call.rep", "Haider", "just Haider")  # rep won't give a last name: accept, don't loop
    assert "call.rep" not in s.missing("close")
