"""Russian number formatting and plural forms for user-facing text."""

from __future__ import annotations

MINUS = "−"


def plural(n: int, forms: tuple[str, str, str]) -> str:
    """Pick the form for 1 / 2-4 / 5+: plural(3, ("квадрат", "квадрата", "квадратов"))."""
    n = abs(n)
    if n % 10 == 1 and n % 100 != 11:
        return forms[0]
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return forms[1]
    return forms[2]


def count(n: int, forms: tuple[str, str, str]) -> str:
    return f"{n} {plural(n, forms)}"


def number(value: float, decimals: int = 1, signed: bool = False) -> str:
    """Decimal comma and a real minus sign: -1.25 -> "−1,3"; whole numbers lose ",0"."""
    text = f"{abs(value):.{decimals}f}".replace(".", ",")
    if "," in text:
        text = text.rstrip("0").rstrip(",")
    if value < 0 and text != "0":
        return MINUS + text
    if signed and text != "0":
        return "+" + text
    return text


CELLS = ("квадрат", "квадрата", "квадратов")
CELLS_IN = ("квадрате", "квадратах", "квадратах")  # "в 177 квадратах"
WEAK_CELLS_OF = ("слабого квадрата", "слабых квадратов", "слабых квадратов")  # "из 174 слабых квадратов"
ROWS = ("строка", "строки", "строк")
MEASUREMENTS = ("замер", "замера", "замеров")
