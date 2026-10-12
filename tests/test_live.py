"""The live view (/live): reads CallState while a call runs, then shows the final result."""

import asyncio

from fastapi.testclient import TestClient

from app import live
from app.config import load_scenario
from app.main import app
from app.results import finalize_call
from app.schema import FieldStatus
from app.state import CallState


def _field(snap, path):
    return next(f for f in snap["fields"] if f["path"] == path)


def test_live_view_follows_a_call(tmp_path, monkeypatch):
    monkeypatch.setattr("app.results.CALLS_DIR", tmp_path)
    monkeypatch.setattr("app.results.save_call", lambda *a, **k: None)
    c = TestClient(app)
    live._current = None
    assert c.get("/live/state").json() == {"status": "idle"}
    assert "SRP Benefits Verification" in c.get("/live").text

    s = CallState(load_scenario("lana_kane"), call_sid="web-test")
    live.track(s)
    s.stage = "benefits"
    s.add_turn("agent", "What's the coverage for D4341?")
    s.add_turn("rep", "D4341 is covered at eighty percent, annual max is fifteen hundred.")
    s.record("srp.codes.D4341.coverage_pct", 80, "covered at eighty percent")
    s.record("srp.annual_max", 1500, "annual max is fifteen hundred")
    s.record_quadrant("UR", True, "D4341", "2025-02-04", "D4341 paid on February 4, 2025")

    snap = c.get("/live/state").json()
    assert snap["status"] == "live" and snap["stage"] == "benefits"
    assert [t["speaker"] for t in snap["transcript"]] == ["agent", "rep"]
    pct = _field(snap, "srp.codes.D4341.coverage_pct")
    assert pct["value"] == "80%" and pct["status"] == "answered" and pct["turn"] == 1
    assert pct["quote"] == "covered at eighty percent"
    assert _field(snap, "srp.annual_max")["value"] == "$1,500"
    assert _field(snap, "srp.history.UR")["value"].startswith("Paid 2025-02-04 (D4341)")
    assert _field(snap, "srp.frequency")["label"] == "SRP frequency limitation"
    missing = [m["path"] for m in snap["missing"]]
    assert "srp.codes.D4341.coverage_pct" not in missing and "srp.remaining" in missing
    assert snap["missing"][0]["group"] == "benefits"  # the current stage comes first
    assert snap["captured"] == 3 and "result" not in snap

    s.mark("srp.deductible.met", FieldStatus.REFUSED, "I can't give that out")
    s.stage = "end"
    assert c.get("/live/state").json()["status"] == "finalizing"
    live.finish(s, asyncio.run(finalize_call(s, kind="browser", scenario="lana_kane", postcall=False)))

    snap = c.get("/live/state").json()
    assert snap["status"] == "done" and snap["missing"] == []
    assert snap["result"]["reference"]
    nulls = {n["path"]: n for n in snap["result"]["nulls"]}
    assert nulls["srp.deductible.met"]["reason"] == "The rep declined to give it."
    assert nulls["srp.remaining"]["status"] == "not_asked"
    assert "srp.annual_max" not in nulls
    live._current = None
