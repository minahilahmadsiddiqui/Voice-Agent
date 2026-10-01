"""Drives the text-mode agent with a scripted fake LLM (no API key needed) through the
reference call, then checks the tool loop, hold gating, keypad tones, stage transitions,
output files, database rows and scorecard."""

import asyncio
import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

import app.results as results
import app.storage as storage
from app.config import load_scenario
from app.llm_client import Reply, ToolUse
from app.state import CallState
from sim.scorecard import score
from sim.text_agent import TextAgent

GT = json.loads((Path(__file__).parent.parent / "sim" / "ground_truth" / "reference_call.json").read_text())


def text(t):
    return NS(type="text", text=t)


def tool(name, **inp):
    tool.n = getattr(tool, "n", 0) + 1
    return NS(type="tool_use", id=f"tu_{tool.n}", name=name, input=inp)


def f(path, value):
    return {"path": path, "value": value, "quote": "q"}


class FakeClient:
    """Returns scripted responses in order; records what it was sent."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        blocks = self.script.pop(0)
        return Reply(
            text=" ".join(b.text for b in blocks if b.type == "text"),
            tool_uses=[ToolUse(b.id, b.name, b.input) for b in blocks if b.type == "tool_use"],
        )


# One entry per LLM call, in order.
SCRIPT = [
    [text("Benefits.")],                                                     # IVR menu
    [tool("press_digits", digits="841552037#")],                             # tax ID
    [tool("on_hold")],                                                       # please hold
    [text("Still waiting.")],                                                # hold music -> must be gated
    [tool("human_detected", rep_first_name="Denise")],                       # rep greets
    [text("Hi Denise, this is an automated assistant calling on behalf of Cedar Park Dental.")],
    [tool("record_fields", fields=[f("member.active", True), f("member.effective", "2024-03-01"),
                                   f("member.benefit_year", "calendar")])],
    # from here on the CODE asks the next question (scripted from the checklist): no LLM call
    [tool("record_fields", fields=[f("srp.codes.D4341.coverage_pct", 80), f("srp.codes.D4342.coverage_pct", 80),
                                   f("srp.benefit_class", "basic"), f("srp.deductible.amount", 50),
                                   f("srp.deductible.met", True), f("srp.annual_max", 1500),
                                   f("srp.remaining", 1340), f("srp.frequency", "1 per quadrant / 24 months"),
                                   f("srp.frequency_months", 24)])],
    [text("Sure, take your time.")],                                         # rep: "let me look"
    [tool("record_quadrant", quadrants=[
        {"quadrant": "UR", "on_file": True, "code": "D4341", "paid_date": "2025-02-04", "quote": "q"},
        {"quadrant": "LR", "on_file": True, "code": "D4341", "paid_date": "2025-02-04", "quote": "q"},
        {"quadrant": "UL", "on_file": False, "quote": "q"}, {"quadrant": "LL", "on_file": False, "quote": "q"},
    ]), tool("record_fields", fields=[f("srp.frequency_counting", "date_of_service")])],
    [tool("record_fields", fields=[
        f("srp.documentation.perio_charting", True), f("srp.documentation.radiographs", True),
        f("srp.documentation.min_pocket_depth_mm", 4), f("srp.documentation.bone_loss_required", True),
        f("srp.documentation.preauth", "recommended_not_required"), f("srp.downgrade.to", "D1110"),
        f("srp.downgrade.trigger", "documentation_does_not_support_diagnosis"), f("srp.quadrants_per_dos", 2)])],
    [tool("record_fields", fields=[f("d4910.coverage_pct", 80), f("d4910.frequency", "2 per calendar year"),
                                   f("d4910.shared_with_d1110", True), f("d4910.wait_after_srp_days", 90)])],
    # (read-back script spoken by code)
    [text("Correcting the remaining to twelve forty-seven."), tool("readback_done", corrections=[f("srp.remaining", 1247)])],
    # (code asks for the reference number and full name)
    [tool("record_fields", fields=[f("call.reference", "771402988"), f("call.rep", "Denise Okafor")])],
    # the reference must be read back (confirm_with_rep), so the LLM speaks:
    [text("That's seven seven one, four zero two, nine eight eight. And this quote is not a guarantee of payment?")],
    [tool("record_fields", fields=[f("call.disclaimer", "Correct. Benefits are subject to eligibility "
                                                         "and plan limitations at the time of service.")])],
    [text("Thanks, Denise. Goodbye.")],
]

REP_LINES = [
    "Thanks for holding, this is Denise. Can I get your name and the practice?",
    "I have her. Active, effective 03/01/2024, calendar year.",
    "80% basic, $50 met, $1,500 max with $1,340 remaining, once per quadrant every 24 months.",
    "Let me look...",
    "D4341 upper right and lower right on 02/04/2025, nothing else. 24 months date of service.",
    "Charting, radiographs, 4mm with bone loss, estimate recommended. Downgrades to prophy. Two quadrants.",
    "80%, twice a year shared with prophy, 90 days after SRP.",
    "Remaining is $1,247.",
    "Reference 771402988. Denise Okafor.",
    "Correct. Benefits are subject to eligibility and plan limitations at the time of service.",
]


@pytest.fixture
def tmp_calls(tmp_path, monkeypatch):
    monkeypatch.setattr(results, "CALLS_DIR", tmp_path)
    monkeypatch.setattr(storage, "CALLS_DIR", tmp_path)
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "calls.db")
    return tmp_path


def test_scripted_call_through_text_agent(tmp_calls):
    async def run():
        state = CallState(load_scenario("lana_kane"), call_sid="sim-test", today=date(2026, 9, 21))
        client = FakeClient(SCRIPT)
        agent = TextAgent(state, client)

        t = await agent.hear("For eligibility and benefits, say benefits or press one.")
        assert t.spoken == "Benefits."
        t = await agent.hear("Please enter the provider tax ID, followed by the pound key.")
        assert t.digits == "841552037#" and t.spoken == ""
        await agent.hear("Please hold.")
        assert state.stage == "hold"
        t = await agent.hear("(hold music)")
        assert t.spoken == "" and t.suppressed == "Still waiting."  # gated on hold

        spoken = []
        for line in REP_LINES:
            state.add_turn("rep" if state.stage not in ("ivr", "hold") else "ivr", line)
            turn = await agent.hear(line)
            spoken.append(turn.spoken)
        assert state.stage == "end" and state.ended_reason == "completed"
        assert spoken[0].startswith("Hi Denise")          # human_detected -> verify speaks immediately
        assert spoken[3] == "Sure, take your time."        # no new question mid-lookup
        assert state.transcript[[t.text for t in state.transcript].index(REP_LINES[0])].speaker == "rep"

        # Every call after on_hold sees only the current stage's tools.
        tool_sets = [[t["name"] for t in c["tools"]] for c in client.calls]
        assert tool_sets[0] == ["press_digits", "on_hold", "human_detected"]
        assert "record_quadrant" in tool_sets[9]
        assert spoken[1].startswith("Benefits for scaling and root planing")  # scripted by code
        assert spoken[2].startswith("Does claim history show SRP paid")
        assert spoken[6].startswith("Let me read this back")
        assert "reference number" in spoken[7]
        assert client.calls[-1]["tool_choice"] == "none"  # goodbye stage: talk only
        assert not client.script  # every scripted response used

        state.ended_at = state.connected_at + 60
        return await results.finalize_call(state, kind="sim", scenario="lana_kane", persona="cooperative",
                                           postcall=False)

    out = asyncio.run(run())
    sc = score(out["reference"], GT)
    assert sc["accuracy"] == 1.0, sc["wrong"]
    for name in ("reference.json", "sourced.json", "transcript.txt", "events.json"):
        assert (tmp_calls / "sim-test" / name).exists()
    row = storage.get_call("sim-test")
    assert row["ended_reason"] == "completed" and len(row["turns"]) > 10


def test_scorecard_flags_wrong_and_missing():
    actual = json.loads(json.dumps(GT))
    actual["srp"]["remaining"] = 1340
    actual["srp"]["history"][2]["next_eligible"] = None
    sc = score(actual, GT)
    wrong = {r["path"] for r in sc["wrong"]}
    assert wrong == {"srp.remaining", "srp.history.UL.next_eligible"}
