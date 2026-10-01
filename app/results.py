"""End of a call: post-call reconciliation, both output shapes, files and database."""

import json
import time

from loguru import logger

from app.config import CALLS_DIR
from app.export import export_reference, export_sourced
from app.postcall import run_postcall, transcript_text
from app.state import CallState
from app.storage import save_call


async def finalize_call(state: CallState, *, kind: str, scenario: str, persona: str | None = None,
                        postcall: bool = True) -> dict:
    state.ended_at = state.ended_at or time.time()
    live_reference = export_reference(state)  # before reconciliation, for comparison
    discrepancies = await run_postcall(state) if postcall else []
    state.close_out_pending()
    reference = export_reference(state)
    sourced = export_sourced(state).model_dump(mode="json")

    out_dir = CALLS_DIR / state.call_sid
    out_dir.mkdir(parents=True, exist_ok=True)
    files = {
        "reference.json": reference,
        "reference_live_only.json": live_reference,
        "sourced.json": sourced,
        "discrepancies.json": discrepancies,
        "events.json": state.events,
    }
    for name, data in files.items():
        (out_dir / name).write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    (out_dir / "transcript.txt").write_text(transcript_text(state), encoding="utf-8")

    save_call(state, kind=kind, scenario=scenario, reference=reference, sourced=sourced,
              discrepancies=discrepancies, persona=persona)
    logger.info(f"Results for {state.call_sid} saved to {out_dir}")
    return {"reference": reference, "sourced": sourced, "discrepancies": discrepancies, "dir": str(out_dir)}
