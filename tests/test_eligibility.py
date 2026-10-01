from datetime import date

from app.eligibility import add_months, next_eligible

TODAY = date(2026, 9, 21)


def test_24_months_date_of_service():
    assert next_eligible(date(2025, 2, 4), 24, TODAY) == "2027-02-04"


def test_nothing_on_file_is_open_now():
    assert next_eligible(None, 24, TODAY) == "now"


def test_window_already_passed_is_now():
    assert next_eligible(date(2023, 1, 10), 24, TODAY) == "now"


def test_unknown_frequency_is_unknown():
    assert next_eligible(date(2025, 2, 4), None, TODAY) is None


def test_month_end_clamping():
    assert add_months(date(2024, 2, 29), 12) == date(2025, 2, 28)
    assert add_months(date(2025, 1, 31), 1) == date(2025, 2, 28)
    assert add_months(date(2025, 11, 15), 3) == date(2026, 2, 15)
