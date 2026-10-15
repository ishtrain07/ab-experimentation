import re
from datetime import date
from decimal import Decimal, InvalidOperation

from .documents import CommercialDocument

_FIELD = re.compile(r"^([A-Z_]+):\s*(.*)$")
_LABELED_KEYS = frozenset(
    {
        "SUPPLIER",
        "DATE",
        "GRADE",
        "SIZE",
        "QUANTITY",
        "UNIT",
        "UNIT_PRICE",
        "CURRENCY",
        "REASON",
    }
)
_MONTHS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}
_CURRENCY_UNIT = re.compile(
    r"(INR|USD|EUR|GBP)\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*per\s*(MT|tonne|ton|kg|lb)",
    re.I,
)
_SIZE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(mm|cm|in|inch|inches|gauge|ga)\b",
    re.I,
)
_QUANTITY = re.compile(r"(\d+(?:\.\d+)?)\s*(MT|tonne|ton|kg|lb)\b", re.I)
_DATE = re.compile(r"(\d{1,2})\s+([A-Za-z]{3,9})\s+(20\d{2})")
_GRADE_HINTS = (
    (re.compile(r"CR\s+sheet", re.I), "CR sheet"),
    (re.compile(r"HR\s+sheet", re.I), "HR sheet"),
    (re.compile(r"aluminum|aluminium", re.I), "Aluminum"),
    (re.compile(r"\bcopper\b", re.I), "Copper"),
    (re.compile(r"\bcement\b", re.I), "Cement"),
    (re.compile(r"\bpolymer\b|\bresin\b", re.I), "Polymer"),
)


def extract_document(text: str) -> CommercialDocument:
    labeled = _extract_labeled(text)
    if labeled is not None:
        return labeled
    free = _extract_free_text(text)
    if free is not None:
        return free
    raise ValueError(
        "Could not read a supplier, date, grade, size, unit, and unit price from this document."
    )


def _extract_labeled(text: str) -> CommercialDocument | None:
    fields: dict[str, str] = {}
    reason_lines: list[str] = []
    in_reason = False
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        match = _FIELD.match(line)
        if match and match.group(1) in _LABELED_KEYS:
            name, value = match.group(1), match.group(2).strip()
            in_reason = name == "REASON"
            fields[name] = value
            continue
        if in_reason:
            reason_lines.append(line)
    required = ("SUPPLIER", "DATE", "GRADE", "SIZE", "UNIT", "UNIT_PRICE", "CURRENCY")
    if not all(fields.get(name) for name in required):
        return None
    reason = " ".join([fields.get("REASON", ""), *reason_lines]).strip()
    try:
        unit_price = _positive_decimal(fields["UNIT_PRICE"])
        quantity = _non_negative_decimal(fields.get("QUANTITY") or "0")
        document_date = _parse_date(fields["DATE"])
    except ValueError:
        return None
    return CommercialDocument(
        supplier=fields["SUPPLIER"],
        document_date=document_date,
        grade=fields["GRADE"],
        size=fields["SIZE"],
        quantity=quantity,
        unit=fields["UNIT"],
        unit_price=unit_price,
        currency=fields["CURRENCY"],
        reason=reason,
        source_text=text.strip(),
        extraction_method="labeled",
    )


def _extract_free_text(text: str) -> CommercialDocument | None:
    compact = " ".join(text.split())
    price = _CURRENCY_UNIT.search(compact)
    size = _SIZE.search(compact)
    quantity = _QUANTITY.search(compact)
    dated = _DATE.search(compact)
    supplier = compact.split(",")[0].strip() if "," in compact else ""
    if not (price and size and quantity and dated and supplier):
        return None
    try:
        unit_price = _positive_decimal(price.group(2))
        qty = _non_negative_decimal(quantity.group(1))
        document_date = _parse_human_date(dated.group(1), dated.group(2), dated.group(3))
    except ValueError:
        return None
    reason_match = re.search(r"(up\s+\d+%.*)$", compact, re.I)
    size_unit = size.group(2).lower()
    if size_unit in {"inch", "inches"}:
        size_unit = "in"
    if size_unit == "ga":
        size_unit = "gauge"
    return CommercialDocument(
        supplier=supplier,
        document_date=document_date,
        grade=_guess_grade(compact),
        size=f"{size.group(1)} {size_unit}",
        quantity=qty,
        unit=quantity.group(2).upper() if quantity.group(2).lower() == "mt" else quantity.group(2).lower(),
        unit_price=unit_price,
        currency=price.group(1).upper(),
        reason=reason_match.group(1).strip() if reason_match else "",
        source_text=text.strip(),
        extraction_method="free_text",
    )


def _guess_grade(compact: str) -> str:
    for pattern, label in _GRADE_HINTS:
        if pattern.search(compact):
            return label
    return "unspecified"


def _positive_decimal(value: str) -> Decimal:
    try:
        number = Decimal(value.replace(",", "").strip())
    except InvalidOperation as error:
        raise ValueError("Unit price is not a number.") from error
    if number <= 0:
        raise ValueError("Unit price must be greater than zero.")
    return number


def _non_negative_decimal(value: str) -> Decimal:
    try:
        number = Decimal(value.replace(",", "").strip())
    except InvalidOperation as error:
        raise ValueError("Quantity is not a number.") from error
    if number < 0:
        raise ValueError("Quantity cannot be negative.")
    return number


def _parse_date(value: str) -> date:
    try:
        year, month, day = value.split("-")
        return date(int(year), int(month), int(day))
    except (TypeError, ValueError) as error:
        raise ValueError(f"Date must be YYYY-MM-DD, got {value!r}.") from error


def _parse_human_date(day: str, month: str, year: str) -> date:
    try:
        month_number = _MONTHS[month[:3].lower()]
    except KeyError as error:
        raise ValueError(f"Unrecognized month {month!r}.") from error
    return date(int(year), month_number, int(day))
