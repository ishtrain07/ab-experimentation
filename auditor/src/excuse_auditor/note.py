from decimal import Decimal, ROUND_HALF_UP

from .audit import AuditResult
from .documents import CommercialDocument

_ONE_DECIMAL = Decimal("0.1")
_MONEY = Decimal("1")


def percent(value: Decimal) -> str:
    return f"{(value * Decimal('100')).quantize(_ONE_DECIMAL, rounding=ROUND_HALF_UP)}%"


def money(value: Decimal) -> str:
    return f"{value.quantize(_MONEY, rounding=ROUND_HALF_UP)}"


def write_note(invoice: CommercialDocument, quote: CommercialDocument, result: AuditResult) -> str:
    if not result.comparable:
        return result.comparison_note
    assert result.quote_change is not None
    assert result.explained is not None
    assert result.unexplained is not None
    assert result.fair_unit_price is not None
    lines = [
        (
            f"The quote is {percent(result.quote_change)} above the {invoice.document_date.isoformat()} "
            f"invoice of {invoice.currency} {money(invoice.unit_price)} per {invoice.unit}."
        )
    ]
    cited = [component for component in result.components if component.used]
    if cited:
        parts = [
            f"{component.name} {percent(component.change)} ({component.start} to {component.end} {component.unit}, {component.source})"
            for component in cited
        ]
        lines.append(f"Cited series explain {percent(result.explained)}: " + "; ".join(parts) + ".")
    else:
        lines.append("No cited series applies to the supplier's stated reason.")
    lines.append(f"Unexplained gap: {percent(result.unexplained)}.")
    lines.append(result.series_label)
    lines.append(
        f"Reply: we can accept {invoice.currency} {money(result.fair_unit_price)} per {invoice.unit}, "
        f"which is the last price plus the explained {percent(result.explained)}. "
        f"The remaining {percent(result.unexplained)} is not supported by the cited series."
    )
    return " ".join(lines)
