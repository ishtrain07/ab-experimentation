from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from .documents import CommercialDocument, grade_matches_materials, same_specification
from .series import MarketSeries, SeriesComponent, load_series

_ALWAYS_LIMITATIONS = (
    "Deterministic percentages come from invoice/quote prices and the loaded series only.",
    "Models may help read messy text or phrase a follow-up; they must not invent the audit percentages.",
)


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
    key: str = ""


@dataclass(frozen=True)
class AuditTrust:
    confidence: str
    confidence_reasons: tuple[str, ...]
    limitations: tuple[str, ...]
    material_scope: tuple[str, ...]
    series_demo: bool
    live_feed: bool
    extraction_invoice: str
    extraction_quote: str


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
    trust: AuditTrust


def run_audit(
    invoice: CommercialDocument,
    quote: CommercialDocument,
    series_path: Path,
    series_label: str | None = None,
) -> AuditResult:
    series = load_series(series_path)
    label = series_label or series.label
    trust = _trust_for(invoice, quote, series, comparable=False, missing_points=False)

    if invoice.unit_price <= 0:
        return AuditResult(
            comparable=False,
            comparison_note="Invoice unit price must be greater than zero.",
            quote_change=None,
            explained=None,
            unexplained=None,
            fair_unit_price=None,
            components=(),
            reason=quote.reason,
            series_label=label,
            trust=trust,
        )

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
            series_label=label,
            trust=trust,
        )

    quote_change = (quote.unit_price - invoice.unit_price) / invoice.unit_price
    used: list[UsedComponent] = []
    explained = Decimal("0")
    reason_text = quote.reason.lower()
    missing_points = False

    for key in series.component_keys:
        component = series.lookup(key, invoice.document_date, quote.document_date)
        if component is None:
            missing_points = True
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
                    key=key,
                )
            )
            continue
        claim_ok = _claim_matches(component, reason_text)
        if claim_ok:
            explained += component.change
        used.append(_used(component, claim_ok))

    fair = invoice.unit_price * (Decimal("1") + explained)
    trust = _trust_for(invoice, quote, series, comparable=True, missing_points=missing_points)
    return AuditResult(
        comparable=True,
        comparison_note="Grade, size, unit, and currency match.",
        quote_change=quote_change,
        explained=explained,
        unexplained=quote_change - explained,
        fair_unit_price=fair,
        components=tuple(used),
        reason=quote.reason,
        series_label=label,
        trust=trust,
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
        key=component.key,
    )


def _trust_for(
    invoice: CommercialDocument,
    quote: CommercialDocument,
    series: MarketSeries,
    *,
    comparable: bool,
    missing_points: bool,
) -> AuditTrust:
    reasons: list[str] = []
    limitations = list(series.scope.limitations) + list(_ALWAYS_LIMITATIONS)
    confidence = "high"

    if series.scope.demo or not series.scope.live_feed:
        confidence = "medium"
        reasons.append("Loaded series is a demonstration or non-live feed.")

    if invoice.extraction_method != "labeled" or quote.extraction_method != "labeled":
        if confidence == "high":
            confidence = "medium"
        reasons.append("At least one document used free-text heuristics rather than labeled fields.")
        if invoice.grade.lower() == "unspecified" or quote.grade.lower() == "unspecified":
            confidence = "low"
            reasons.append("Free-text extraction could not identify a specific material grade.")

    in_scope = grade_matches_materials(invoice.grade, series.scope.materials)
    if comparable and not in_scope:
        confidence = "low"
        materials = ", ".join(series.scope.materials)
        reasons.append(f"Document grade {invoice.grade!r} is outside loaded material scope ({materials}).")
        limitations.append(
            f"Live calculation support is limited to materials declared in the series scope: {materials}."
        )

    if missing_points:
        confidence = "low"
        reasons.append("One or more series components lack points on both document dates.")

    if not reasons:
        reasons.append("Labeled documents and series points aligned for this comparison.")

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique_reasons = []
    for item in reasons:
        if item not in seen:
            seen.add(item)
            unique_reasons.append(item)
    seen_lim: set[str] = set()
    unique_limits = []
    for item in limitations:
        if item not in seen_lim:
            seen_lim.add(item)
            unique_limits.append(item)

    return AuditTrust(
        confidence=confidence,
        confidence_reasons=tuple(unique_reasons),
        limitations=tuple(unique_limits),
        material_scope=series.scope.materials,
        series_demo=series.scope.demo,
        live_feed=series.scope.live_feed,
        extraction_invoice=invoice.extraction_method,
        extraction_quote=quote.extraction_method,
    )
