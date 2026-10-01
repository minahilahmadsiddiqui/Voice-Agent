"""Date math for SRP frequency limits. Done in code, never by the LLM."""

import calendar
from datetime import date


def add_months(d: date, months: int) -> date:
    """Same day-of-month `months` later; clamps to month end (2024-02-29 + 12 -> 2025-02-28)."""
    total = d.month - 1 + months
    year, month = d.year + total // 12, total % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def next_eligible(paid: date | None, frequency_months: int | None, today: date | None = None) -> str | None:
    """ISO date the quadrant is next eligible, "now" if it already is, None if we can't tell.

    No paid SRP on file -> "now". Counted date of service to date of service.
    """
    today = today or date.today()
    if paid is None:
        return "now"
    if not frequency_months:
        return None
    due = add_months(paid, frequency_months)
    return "now" if due <= today else due.isoformat()
