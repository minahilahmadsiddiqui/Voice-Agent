"""Reconciliation rules between live capture and the post-call extraction."""

from app.config import load_scenario
from app.postcall import reconcile
from app.schema import FieldStatus
from app.state import CallState


def _state():
    s = CallState(load_scenario("lana_kane"))
    for i in range(10):
        s.add_turn("rep", f"line {i}")
    return s


def test_fills_what_live_missed():
    s = _state()
    notes = reconcile(s, {"fields": [
        {"path": "srp.annual_max", "value": "1500", "status": "answered", "quote": "Fifteen hundred", "turn": 4}],
        "quadrants": []})
    cap = s.values["srp.annual_max"]
    assert cap.value == 1500 and cap.source == "postcall" and cap.turn == 4
    assert notes[0]["kind"] == "missed_live"


def test_agreement_changes_nothing():
    s = _state()
    s.record("srp.annual_max", 1500, "Fifteen hundred")
    notes = reconcile(s, {"fields": [
        {"path": "srp.annual_max", "value": 1500, "status": "answered", "quote": "x", "turn": 4}], "quadrants": []})
    assert notes == [] and s.values["srp.annual_max"].status == FieldStatus.ANSWERED


def test_conflict_later_turn_wins_and_is_flagged():
    s = _state()
    s.record("srp.remaining", 1340, "1340")
    s.values["srp.remaining"].turn = 3
    notes = reconcile(s, {"fields": [
        {"path": "srp.remaining", "value": 1247, "status": "answered", "quote": "Remaining is $1,247", "turn": 8}],
        "quadrants": []})
    cap = s.values["srp.remaining"]
    assert cap.value == 1247 and cap.previous_value == 1340 and cap.status == FieldStatus.NEEDS_REVIEW
    assert notes[0]["kind"] == "conflict"


def test_readback_correction_always_wins():
    s = _state()
    s.record("srp.remaining", 1340)
    s.correct("srp.remaining", 1247, "Remaining is $1,247")
    reconcile(s, {"fields": [
        {"path": "srp.remaining", "value": 1340, "status": "answered", "quote": "x", "turn": 9}], "quadrants": []})
    assert s.value("srp.remaining") == 1247 and s.values["srp.remaining"].status == FieldStatus.CORRECTED


def test_quadrant_missed_live_is_filled_but_absence_needs_explicit_answer():
    s = _state()
    reconcile(s, {"fields": [], "quadrants": [
        {"quadrant": "UR", "on_file": True, "code": "D4341", "paid_date": "2025-02-04", "quote": "q", "turn": 5},
        {"quadrant": "UL", "on_file": None, "quote": "", "turn": 5}]})
    assert s.quadrants["UR"].on_file is True and s.quadrants["UR"].source == "postcall"
    assert s.quadrants["UL"].status == FieldStatus.PENDING  # not guessed
