from dataclasses import dataclass
from datetime import date
from decimal import Decimal

# Grade phrases that map a document into a series material bucket.
_MATERIAL_ALIASES: dict[str, tuple[str, ...]] = {
    "steel": (
        "steel",
        "cr sheet",
        "hr sheet",
        "crc",
        "hrc",
        "cold-rolled",
        "hot-rolled",
        "cold rolled",
        "hot rolled",
    ),
    "aluminum": ("aluminum", "aluminium", "al sheet"),
    "copper": ("copper", "cu sheet"),
    "polymer": ("polymer", "resin", "plastic", "pvc"),
    "cement": ("cement", "clinker"),
}


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
    extraction_method: str = "labeled"


def _norm(value: str) -> str:
    return "".join(value.lower().split())


def same_specification(old: CommercialDocument, new: CommercialDocument) -> bool:
    return (
        _norm(old.grade) == _norm(new.grade)
        and _norm(old.size) == _norm(new.size)
        and _norm(old.unit) == _norm(new.unit)
        and old.currency.upper() == new.currency.upper()
    )


def grade_matches_materials(grade: str, materials: tuple[str, ...]) -> bool:
    """Return True when the grade looks compatible with at least one scoped material."""
    if not materials or materials == ("unspecified",):
        return True
    grade_l = grade.lower().strip()
    if not grade_l or grade_l == "unspecified":
        return False
    for material in materials:
        key = material.lower().strip()
        aliases = _MATERIAL_ALIASES.get(key, ())
        tokens = (key, *aliases)
        if any(token in grade_l or grade_l in token for token in tokens if token.strip()):
            return True
    return False
