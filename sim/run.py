"""Run the agent against a simulated rep, in text mode, and score the result.

  python -m sim.run --persona cooperative
  python -m sim.run --persona cooperative --runs 3 --agent-model claude-haiku-4-5-20251001
  python -m sim.run --persona cooperative --no-postcall --quiet
"""

import argparse
import asyncio
import json
import statistics
import sys
import time
from datetime import date, datetime
from pathlib import Path

from app.config import load_scenario, settings
from app.llm_client import AnthropicChat, GeminiChat, OpenAICompatChat
from app.results import finalize_call
from app.state import CallState
from app.storage import connect
from sim.rep import HANGUP, PAUSE, RepSim, load_persona
from sim.scorecard import format_report, score
from sim.text_agent import TextAgent

GROUND_TRUTH_DIR = Path(__file__).parent / "ground_truth"
MAX_REP_TURNS = 60


class Printer:
    def __init__(self, quiet: bool):
        self.quiet = quiet

    def __call__(self, who: str, text: str) -> None:
        if not self.quiet and text:
            print(f"{who:>6} | {text}")


def chat(model: str, provider: str | None = None):
    provider = provider or settings.llm_provider
    if provider == "anthropic":
        return AnthropicChat(model)
    if provider == "groq":
        return OpenAICompatChat(model)
    return GeminiChat(model)


async def run_once(persona_name: str, scenario: str, agent_model: str, rep_model: str,
                   postcall: bool, quiet: bool) -> dict:
    persona = load_persona(persona_name)
    call_sid = f"sim-{persona_name}-{datetime.now():%Y%m%d-%H%M%S}"
    state = CallState(load_scenario(scenario), call_sid=call_sid, today=date.fromisoformat(persona.today))
    agent = TextAgent(state, chat(agent_model))
    rep = RepSim(persona, chat(rep_model, settings.provider_for("rep")))
    say = Printer(quiet)
    behavior = {"ivr_steps_passed": 0, "ivr_steps_total": len(persona.ivr), "spoke_on_hold": 0,
                "pause_violations": 0, "agent_turns": 0}
    llm_ms: list[int] = []

    def track(turn):
        llm_ms.extend(turn.llm_ms)
        if turn.spoken:
            behavior["agent_turns"] += 1
        say("AGENT", turn.spoken + (f"  [keys {turn.digits}]" if turn.digits else ""))

    # 1. Phone menu (scripted), checking what the agent says / presses.
    for step in persona.ivr:
        state.add_turn("ivr", step.say)
        say("IVR", step.say)
        turn = await agent.hear(step.say)
        track(turn)
        speech_ok = bool(step.expect_speech) and step.expect_speech.lower() in turn.spoken.lower()
        digits_ok = bool(step.expect_digits) and turn.digits == step.expect_digits
        if (not step.expect_speech and not step.expect_digits) or speech_ok or digits_ok:
            behavior["ivr_steps_passed"] += 1

    # 2. Hold queue: the agent must stay silent.
    for msg in persona.hold_messages:
        state.add_turn("ivr", msg)
        say("HOLD", msg)
        turn = await agent.hear(msg)
        track(turn)
        if turn.spoken or turn.suppressed:
            behavior["spoke_on_hold"] += 1

    # 3. The live rep.
    rep_text = await rep.say()
    for _ in range(MAX_REP_TURNS):
        hung_up = HANGUP in rep_text
        if hung_up and state.stage not in ("end", "close"):
            say("SIM", f"(the simulated rep hung up early during stage {state.stage})")
        parts = [p.strip() for p in rep_text.replace(HANGUP, "").split(PAUSE)]
        agent_said = []
        for i, part in enumerate(parts):
            if not part:
                continue
            speaker = "rep" if state.stage not in ("ivr", "hold") else "ivr"
            state.add_turn(speaker, part)
            say("REP", part)
            if hung_up and i == len(parts) - 1:
                break
            turn = await agent.hear(part)
            track(turn)
            if i < len(parts) - 1 and "?" in turn.spoken:  # asked something new mid-lookup
                behavior["pause_violations"] += 1
            if turn.spoken:
                agent_said.append(turn.spoken)
        if hung_up or state.stage == "end" and agent_said:
            break
        rep_text = await rep.reply(" ".join(agent_said))

    state.ended_at = time.time()
    behavior["completed"] = state.ended_reason == "completed"
    behavior["ended_reason"] = state.ended_reason
    behavior["final_stage"] = state.stage
    behavior["readback_done"] = state.readback_done
    behavior["llm_calls"] = len(llm_ms)
    behavior["llm_ms_median"] = int(statistics.median(llm_ms)) if llm_ms else None

    result = await finalize_call(state, kind="sim", scenario=scenario, persona=persona_name, postcall=postcall)
    expected = json.loads((GROUND_TRUTH_DIR / persona.ground_truth).read_text(encoding="utf-8"))
    sc = score(result["reference"], expected)
    live_sc = score(json.loads((Path(result["dir"]) / "reference_live_only.json").read_text()), expected)
    behavior["live_only_accuracy"] = f"{live_sc['accuracy']:.0%}"
    report = {"score": sc, "behavior": behavior, "agent_model": agent_model, "rep_model": rep_model}
    (Path(result["dir"]) / "score.json").write_text(json.dumps(report, indent=2, default=str))
    with connect() as conn:
        conn.execute("UPDATE calls SET score_json = ? WHERE call_sid = ?", (json.dumps(report, default=str), call_sid))
    print(f"\n=== {call_sid} ({agent_model}) ===\n{format_report(sc, behavior)}\nSaved: {result['dir']}")
    return report


async def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--persona", default="cooperative")
    p.add_argument("--scenario", default="lana_kane")
    p.add_argument("--runs", type=int, default=1)
    p.add_argument("--agent-model", default=settings.model_for("agent"))
    p.add_argument("--rep-model", default=settings.model_for("rep"))
    p.add_argument("--no-postcall", action="store_true", help="skip the post-call extraction pass")
    p.add_argument("--quiet", action="store_true", help="don't print the conversation")
    args = p.parse_args()
    if not getattr(settings, settings.llm_key_name):
        sys.exit(f"Set {settings.llm_key_name.upper()} in .env first (LLM_PROVIDER={settings.llm_provider}).")

    print(f"Agent: {settings.llm_provider} {args.agent_model} | rep: {settings.provider_for('rep')} {args.rep_model}")
    reports = [await run_once(args.persona, args.scenario, args.agent_model, args.rep_model,
                              not args.no_postcall, args.quiet) for _ in range(args.runs)]
    if len(reports) > 1:
        accs = [r["score"]["accuracy"] for r in reports]
        print(f"\n{len(reports)} runs: mean accuracy {statistics.mean(accs):.0%}, min {min(accs):.0%}")


if __name__ == "__main__":
    asyncio.run(main())
