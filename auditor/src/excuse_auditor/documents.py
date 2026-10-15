from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class CommercialDocument:
    supplier: str
    document_date: date
    grade: str
    size: str
    quantity: Decimal
    unit: str
    unit_price: Decimal
    currency: str
    reason: str
    source_text: str


def _norm(value: str) -> str:
    return "".join(value.lower().split())


def same_specification(old: CommercialDocument, new: CommercialDocument) -> bool:
    return (
        _norm(old.grade) == _norm(new.grade)
        and _norm(old.size) == _norm(new.size)
        and _norm(old.unit) == _norm(new.unit)
        and old.currency.upper() == new.currency.upper()
    )
