from app.speech_format import (
    money,
    number_to_words,
    phone_number,
    spell_digits,
    spell_id,
    spoken_date,
    year_words,
)


def test_tax_id():
    assert spell_digits("84-1552037") == "eight four, one five five, two zero three seven"


def test_npi():
    assert spell_digits("1477588213") == "one four seven, seven five eight, eight two one three"


def test_reference_number():
    assert spell_digits("771402988") == "seven seven one, four zero two, nine eight eight"


def test_member_id_plain():
    assert spell_id("MDB40719883") == "M, D, B, four zero seven, one nine eight, eight three"


def test_member_id_phonetic():
    assert spell_id("MDB4", phonetic=True) == "M as in Mary, D as in David, B as in Boy, four"


def test_phone():
    expected = "three zero three, five five five, zero one nine two"
    assert phone_number("303-555-0192") == expected
    assert phone_number("+13035550192") == expected


def test_dates():
    assert spoken_date("1983-07-09") == "July ninth, nineteen eighty-three"
    assert spoken_date("2027-02-04") == "February fourth, twenty twenty-seven"
    assert spoken_date("2024-03-01") == "March first, twenty twenty-four"
    assert spoken_date("2005-12-21") == "December twenty-first, two thousand five"


def test_years():
    assert year_words(1905) == "nineteen oh five"
    assert year_words(1900) == "nineteen hundred"


def test_money():
    assert money(1247) == "one thousand two hundred forty-seven dollars"
    assert money(50) == "fifty dollars"
    assert money(1) == "one dollar"
    assert money(12.5) == "twelve dollars and fifty cents"


def test_number_words():
    assert number_to_words(0) == "zero"
    assert number_to_words(90) == "ninety"
    assert number_to_words(1500) == "one thousand five hundred"
