"""Turn IDs, dates, phone numbers and money into text a TTS engine reads correctly.

TTS engines guess at "84-1552037" (eighty-four million...?). On a phone call every
identifier must be read digit by digit, in short groups, with pauses between groups.
Commas give the TTS a natural pause; groups of 3-4 digits are what people can hold.
"""

from datetime import date

DIGITS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"]
ONES = DIGITS + [
    "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
    "sixteen", "seventeen", "eighteen", "nineteen",
]
TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]
MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]
ORDINALS = {
    1: "first", 2: "second", 3: "third", 4: "fourth", 5: "fifth", 6: "sixth", 7: "seventh",
    8: "eighth", 9: "ninth", 10: "tenth", 11: "eleventh", 12: "twelfth", 13: "thirteenth",
    14: "fourteenth", 15: "fifteenth", 16: "sixteenth", 17: "seventeenth", 18: "eighteenth",
    19: "nineteenth", 20: "twentieth", 30: "thirtieth",
}
PHONETIC = {
    "A": "Adam", "B": "Boy", "C": "Charlie", "D": "David", "E": "Edward", "F": "Frank",
    "G": "George", "H": "Henry", "I": "Ida", "J": "John", "K": "King", "L": "Lincoln",
    "M": "Mary", "N": "Nora", "O": "Ocean", "P": "Peter", "Q": "Queen", "R": "Robert",
    "S": "Sam", "T": "Tom", "U": "Union", "V": "Victor", "W": "William", "X": "X-ray",
    "Y": "Young", "Z": "Zebra",
}

GROUP_SEP = ", "


def number_to_words(n: int) -> str:
    """Cardinal words for 0 <= n < 1,000,000 ("one thousand two hundred forty-seven")."""
    if n < 0 or n >= 1_000_000:
        raise ValueError(f"out of range: {n}")
    if n < 20:
        return ONES[n]
    if n < 100:
        tens, ones = divmod(n, 10)
        return TENS[tens] + (f"-{ONES[ones]}" if ones else "")
    if n < 1000:
        hundreds, rest = divmod(n, 100)
        return f"{ONES[hundreds]} hundred" + (f" {number_to_words(rest)}" if rest else "")
    thousands, rest = divmod(n, 1000)
    return f"{number_to_words(thousands)} thousand" + (f" {number_to_words(rest)}" if rest else "")


def ordinal_words(n: int) -> str:
    """Ordinal words for 1..31 ("ninth", "twenty-first")."""
    if n in ORDINALS:
        return ORDINALS[n]
    tens, ones = divmod(n, 10)
    return f"{TENS[tens]}-{ORDINALS[ones]}"


def year_words(y: int) -> str:
    """How people say years: 1983 -> nineteen eighty-three, 2005 -> two thousand five."""
    if 2000 <= y <= 2009:
        return number_to_words(y)
    hi, lo = divmod(y, 100)
    if lo == 0:
        return f"{number_to_words(hi)} hundred"
    if lo < 10:
        return f"{number_to_words(hi)} oh {ONES[lo]}"
    return f"{number_to_words(hi)} {number_to_words(lo)}"


def _chunk(digits: str) -> list[str]:
    """Split a digit run into groups of 3, never leaving a lone trailing digit."""
    if len(digits) <= 4:
        return [digits]
    groups = [digits[i : i + 3] for i in range(0, len(digits), 3)]
    if len(groups[-1]) == 1:
        lone = groups.pop()
        groups[-1] += lone
    return groups


def _say_digits(digits: str) -> str:
    return " ".join(DIGITS[int(d)] for d in digits)


def spell_digits(value: str) -> str:
    """Any number-like ID (tax ID, NPI, reference number) read digit by digit in groups.

    Existing separators (dashes, spaces) are kept as group boundaries.
    "84-1552037" -> "eight four, one five five, two zero three seven"
    """
    parts = [p for p in value.replace("-", " ").replace(".", " ").split() if p]
    groups: list[str] = []
    for part in parts:
        digits = "".join(c for c in part if c.isdigit())
        groups.extend(_chunk(digits))
    return GROUP_SEP.join(_say_digits(g) for g in groups if g)


def spell_id(value: str, phonetic: bool = False) -> str:
    """Alphanumeric ID: letters one by one, digit runs in groups.

    "MDB40719883" -> "M, D, B, four zero seven, one nine eight, eight three"
    phonetic=True  -> "M as in Mary, D as in David, B as in Boy, ..." (use when asked to repeat)
    """
    out: list[str] = []
    run = ""
    for c in value.upper():
        if c.isdigit():
            run += c
            continue
        if run:
            out.extend(_say_digits(g) for g in _chunk(run))
            run = ""
        if c.isalpha():
            out.append(f"{c} as in {PHONETIC[c]}" if phonetic else c)
    if run:
        out.extend(_say_digits(g) for g in _chunk(run))
    return GROUP_SEP.join(out)


def phone_number(value: str) -> str:
    """US phone: "303-555-0192" or "+13035550192" -> "three zero three, five five five, zero one nine two"."""
    digits = "".join(c for c in value if c.isdigit())
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) != 10:
        return spell_digits(digits)
    return GROUP_SEP.join(_say_digits(g) for g in (digits[:3], digits[3:6], digits[6:]))


def spoken_date(value: str | date) -> str:
    """ISO date -> "July ninth, nineteen eighty-three"."""
    d = value if isinstance(value, date) else date.fromisoformat(value)
    return f"{MONTHS[d.month - 1]} {ordinal_words(d.day)}, {year_words(d.year)}"


def money(amount: float) -> str:
    """1247 -> "one thousand two hundred forty-seven dollars"; 12.5 -> "... and fifty cents"."""
    cents_total = round(amount * 100)
    dollars, cents = divmod(cents_total, 100)
    text = f"{number_to_words(dollars)} dollar{'s' if dollars != 1 else ''}"
    if cents:
        text += f" and {number_to_words(cents)} cent{'s' if cents != 1 else ''}"
    return text
