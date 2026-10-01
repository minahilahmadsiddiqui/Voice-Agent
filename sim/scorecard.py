"""Field-by-field comparison of a call's output against a persona's ground truth."""

from typing import Any

IGNORE = {"call.hold_sec", "call.duration_sec"}


def _contains_all(*needles: str):
    return lambda got, _want: isinstance(got, str) and all(n in got.lower() for n in needles)


def _same_text(got: Any, want: Any) -> bool:
    return isinstance(got, str) and got.strip().lower() == str(want).strip().lower()


# Free-text fields: the meaning must match, not the exact wording.
FUZZY = {
    "srp.frequency": _contains_all("24", "quadrant"),
    "d4910.frequency": _contains_all("2", "d1110"),
    "srp.downgrade.trigger": _contains_all("document"),
    "call.disclaimer": _contains_all("eligibility"),
    "call.rep": _same_text,
}


def flatten(data: Any, prefix: str = "") -> dict[str, Any]:
    if isinstance(data, dict):
        out = {}
        for k, v in data.items():
            out.update(flatten(v, f"{prefix}.{k}" if prefix else k))
        return out
    if isinstance(data, list) and data and isinstance(data[0], dict) and "quadrant" in data[0]:
        return flatten({row["quadrant"]: {k: v for k, v in row.items() if k != "quadrant"} for row in data}, prefix)
    return {prefix: data}


def score(actual: dict, expected: dict) -> dict:
    exp, act = flatten(expected), flatten(actual)
    rows = []
    for path, want in exp.items():
        if path in IGNORE:
            continue
        got = act.get(path)
        check = FUZZY.get(path)
        ok = check(got, want) if check and want is not None else got == want
        rows.append({"path": path, "expected": want, "actual": got, "ok": ok})
    correct = sum(r["ok"] for r in rows)
    return {
        "fields_total": len(rows),
        "fields_correct": correct,
        "accuracy": round(correct / len(rows), 3) if rows else 0.0,
        "wrong": [r for r in rows if not r["ok"]],
    }


def format_report(result: dict, behavior: dict) -> str:
    lines = [f"Field accuracy: {result['fields_correct']}/{result['fields_total']} ({result['accuracy']:.0%})"]
    for r in result["wrong"]:
        lines.append(f"  x {r['path']}: expected {r['expected']!r}, got {r['actual']!r}")
    lines.append("Behavior:")
    for k, v in behavior.items():
        lines.append(f"  {k}: {v}")
    return "\n".join(lines)
