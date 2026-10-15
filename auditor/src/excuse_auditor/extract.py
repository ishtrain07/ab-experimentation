import re
from datetime import date
from decimal import Decimal

from .documents import CommercialDocument

_FIELD = re.compile(r"^([A-Z_]+):\s*(.*)$")
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
        if match and match.group(1) in {
            "SUPPLIER",
            "DATE",
            "GRADE",
            "SIZE",
            "QUANTITY",
            "UNIT",
            "UNIT_PRICE",
            "CURRENCY",
            "REASON",
        }:
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
    return CommercialDocument(
        supplier=fields["SUPPLIER"],
        document_date=_parse_date(fields["DATE"]),
        grade=fields["GRADE"],
        size=fields["SIZE"],
        quantity=Decimal(fields.get("QUANTITY") or "0"),
        unit=fields["UNIT"],
        unit_price=Decimal(fields["UNIT_PRICE"].replace(",", "")),
        currency=fields["CURRENCY"],
        reason=reason,
        source_text=text.strip(),
    )


def _extract_free_text(text: str) -> CommercialDocument | None:
    compact = " ".join(text.split())
    price = re.search(r"INR\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*per\s*MT", compact, re.I)
    size = re.search(r"(\d+(?:\.\d+)?)\s*mm", compact, re.I)
    quantity = re.search(r"(\d+(?:\.\d+)?)\s*MT", compact, re.I)
    dated = re.search(r"(\d{1,2})\s+([A-Za-z]{3,9})\s+(20\d{2})", compact)
    supplier = compact.split(",")[0].strip() if "," in compact else ""
    if not (price and size and quantity and dated and supplier):
        return None
    reason_match = re.search(r"(up\s+\d+%.*)$", compact, re.I)
    return CommercialDocument(
        supplier=supplier,
        document_date=_parse_human_date(dated.group(1), dated.group(2), dated.group(3)),
        grade="CR sheet" if re.search(r"CR\s+sheet", compact, re.I) else "unspecified",
        size=f"{size.group(1)} mm",
        quantity=Decimal(quantity.group(1)),
        unit="MT",
        unit_price=Decimal(price.group(1).replace(",", "")),
        currency="INR",
        reason=reason_match.group(1).strip() if reason_match else "",
        source_text=text.strip(),
    )


def _parse_date(value: str) -> date:
    year, month, day = value.split("-")
    return date(int(year), int(month), int(day))


def _parse_human_date(day: str, month: str, year: str) -> date:
    month_number = _MONTHS[month[:3].lower()]
    return date(int(year), month_number, int(day))
