from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from .documents import CommercialDocument, same_specification
from .series import SeriesComponent, lookup_component

SERIES_KEYS = ("steel", "freight", "fx")


@dataclass(frozen=True)
class UsedComponent:
    name: str
    source: str
    unit: str
    start: Decimal
    end: Decimal
    change: Decimal
    used: bool
    unused_reason: str


@dataclass(frozen=True)
class AuditResult:
    comparable: bool
    comparison_note: str
    quote_change: Decimal | None
    explained: Decimal | None
    unexplained: Decimal | None
    fair_unit_price: Decimal | None
    components: tuple[UsedComponent, ...]
    reason: str
    series_label: str


def run_audit(
    invoice: CommercialDocument,
    quote: CommercialDocument,
    series_path: Path,
    series_label: str,
) -> AuditResult:
    if not same_specification(invoice, quote):
        return AuditResult(
            comparable=False,
            comparison_note=(
                f"The invoice is {invoice.size} {invoice.grade} in {invoice.currency} per {invoice.unit}. "
                f"The quote is {quote.size} {quote.grade} in {quote.currency} per {quote.unit}. "
                "The percentage claim needs the same grade, size, unit, and currency."
            ),
            quote_change=None,
            explained=None,
            unexplained=None,
            fair_unit_price=None,
            components=(),
            reason=quote.reason,
            series_label=series_label,
        )

    quote_change = (quote.unit_price - invoice.unit_price) / invoice.unit_price
    used: list[UsedComponent] = []
    explained = Decimal("0")
    reason_text = quote.reason.lower()
    for key in SERIES_KEYS:
        component = lookup_component(series_path, key, invoice.document_date, quote.document_date)
        if component is None:
            used.append(
                UsedComponent(
                    name=key,
                    source="No point on both document dates",
                    unit="",
                    start=Decimal("0"),
                    end=Decimal("0"),
                    change=Decimal("0"),
                    used=False,
                    unused_reason="No series point on both the invoice date and the quote date.",
                )
            )
            continue
        claim_ok = _claim_matches(component, reason_text)
        if claim_ok:
            explained += component.change
        used.append(_used(component, claim_ok))

    fair = invoice.unit_price * (Decimal("1") + explained)
    return AuditResult(
        comparable=True,
        comparison_note="Grade, size, unit, and currency match.",
        quote_change=quote_change,
        explained=explained,
        unexplained=quote_change - explained,
        fair_unit_price=fair,
        components=tuple(used),
        reason=quote.reason,
        series_label=series_label,
    )


def _claim_matches(component: SeriesComponent, reason_text: str) -> bool:
    if not component.requires_claim:
        return True
    return any(token in reason_text for token in component.requires_claim)


def _used(component: SeriesComponent, claim_ok: bool) -> UsedComponent:
    if claim_ok:
        unused = ""
    else:
        quoted = ", ".join(component.requires_claim)
        unused = f"Left out. The supplier reason does not mention {quoted}."
    return UsedComponent(
        name=component.name,
        source=component.source,
        unit=component.unit,
        start=component.start,
        end=component.end,
        change=component.change,
        used=claim_ok,
        unused_reason=unused,
    )
