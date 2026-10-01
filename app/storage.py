"""SQLite storage: one row per call, one per captured field, one per transcript turn."""

import json
import sqlite3
from datetime import datetime

from app.config import CALLS_DIR
from app.state import CallState

DB_PATH = CALLS_DIR / "calls.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS calls (
    call_sid TEXT PRIMARY KEY,
    kind TEXT,                -- live | sim
    scenario TEXT,
    persona TEXT,
    created_at TEXT,
    ended_reason TEXT,
    hold_sec INTEGER,
    duration_sec INTEGER,
    recording_url TEXT,
    reference_json TEXT,      -- output in the reference PDF's shape
    sourced_json TEXT,        -- full output: every field with status / quote / turn
    discrepancies_json TEXT,  -- live vs post-call differences
    events_json TEXT,
    score_json TEXT
);
CREATE TABLE IF NOT EXISTS fields (
    call_sid TEXT, path TEXT, value TEXT, status TEXT, quote TEXT, turn INTEGER,
    previous_value TEXT, source TEXT,
    PRIMARY KEY (call_sid, path)
);
CREATE TABLE IF NOT EXISTS turns (
    call_sid TEXT, idx INTEGER, speaker TEXT, text TEXT, t REAL,
    PRIMARY KEY (call_sid, idx)
);
"""


def connect() -> sqlite3.Connection:
    CALLS_DIR.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def save_call(state: CallState, *, kind: str, scenario: str, reference: dict, sourced: dict,
              discrepancies: list, persona: str | None = None, score: dict | None = None) -> None:
    with connect() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO calls (call_sid, kind, scenario, persona, created_at, ended_reason,
               hold_sec, duration_sec, recording_url, reference_json, sourced_json, discrepancies_json,
               events_json, score_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?,
                       (SELECT recording_url FROM calls WHERE call_sid = ?), ?, ?, ?, ?, ?)""",
            (state.call_sid, kind, scenario, persona, datetime.now().isoformat(timespec="seconds"),
             state.ended_reason, state.hold_sec, state.duration_sec, state.call_sid,
             json.dumps(reference), json.dumps(sourced, default=str), json.dumps(discrepancies),
             json.dumps(state.events, default=str), json.dumps(score) if score else None),
        )
        conn.execute("DELETE FROM fields WHERE call_sid = ?", (state.call_sid,))
        conn.executemany(
            "INSERT INTO fields VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [(state.call_sid, p, json.dumps(c.value, default=str), c.status.value, c.quote, c.turn,
              json.dumps(c.previous_value, default=str), c.source) for p, c in state.values.items()],
        )
        conn.execute("DELETE FROM turns WHERE call_sid = ?", (state.call_sid,))
        conn.executemany(
            "INSERT INTO turns VALUES (?, ?, ?, ?, ?)",
            [(state.call_sid, t.idx, t.speaker, t.text, t.t) for t in state.transcript],
        )


def set_recording(call_sid: str, url: str) -> None:
    with connect() as conn:
        conn.execute("INSERT OR IGNORE INTO calls (call_sid) VALUES (?)", (call_sid,))
        conn.execute("UPDATE calls SET recording_url = ? WHERE call_sid = ?", (url, call_sid))


def list_calls(limit: int = 50) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT call_sid, kind, persona, created_at, ended_reason, duration_sec, hold_sec, score_json "
            "FROM calls ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]


def get_call(call_sid: str) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM calls WHERE call_sid = ?", (call_sid,)).fetchone()
        if not row:
            return None
        turns = conn.execute("SELECT idx, speaker, text FROM turns WHERE call_sid = ? ORDER BY idx",
                             (call_sid,)).fetchall()
    out = dict(row)
    out["turns"] = [dict(t) for t in turns]
    return out
