from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .audit import run_audit
from .extract import extract_document
from .nemotron import extract_with_nano, token_factory_configured, write_with_super
from .note import money, percent, verdict, write_note
from .series import series_label

ROOT = Path(__file__).resolve().parents[2]
SAMPLES = ROOT / "samples"
SERIES_PATH = SAMPLES / "series.json"
STATIC = ROOT / "static" / "index.html"

app = FastAPI(title="Market Excuse Auditor")


class AuditRequest(BaseModel):
    invoice_text: str = Field(min_length=1)
    quote_text: str = Field(min_length=1)
    question: str = ""


class ComponentView(BaseModel):
    name: str
    change: str | None
    start: str
    end: str
    unit: str
    source: str
    used: bool
    unused_reason: str


class AuditView(BaseModel):
    comparable: bool
    comparison_note: str
    quote_change: str | None
    explained: str | None
    unexplained: str | None
    fair_unit_price: str | None
    currency: str
    unit: str
    reason: str
    series_label: str
    verdict: str
    note: str
    follow_up: str | None
    model_mode: str
    components: list[ComponentView]


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC)


@app.get("/api/samples")
def samples() -> dict[str, str]:
    return {
        "invoice": (SAMPLES / "invoice.txt").read_text(),
        "quote": (SAMPLES / "quote.txt").read_text(),
        "quote_mismatch": (SAMPLES / "quote_mismatch.txt").read_text(),
        "whatsapp": (SAMPLES / "whatsapp.txt").read_text(),
        "series_label": series_label(SERIES_PATH),
    }


@app.post("/api/audits", response_model=AuditView)
def create_audit(body: AuditRequest) -> AuditView:
    invoice = _read(body.invoice_text, "invoice")
    quote = _read(body.quote_text, "quote")
    result = run_audit(invoice, quote, SERIES_PATH, series_label(SERIES_PATH))
    note = write_note(invoice, quote, result)
    follow_up = None
    if body.question.strip() and result.comparable:
        follow_up = write_with_super(note, body.question.strip())
        if follow_up is None:
            follow_up = _local_follow_up(body.question, note)
    return AuditView(
        comparable=result.comparable,
        comparison_note=result.comparison_note,
        quote_change=None if result.quote_change is None else percent(result.quote_change),
        explained=None if result.explained is None else percent(result.explained),
        unexplained=None if result.unexplained is None else percent(result.unexplained),
        fair_unit_price=None if result.fair_unit_price is None else money(result.fair_unit_price),
        currency=invoice.currency,
        unit=invoice.unit,
        reason=result.reason,
        series_label=result.series_label,
        verdict=verdict(result),
        note=note,
        follow_up=follow_up,
        model_mode="token-factory" if token_factory_configured() else "local-calculation",
        components=[
            ComponentView(
                name=item.name,
                change=percent(item.change) if item.used else None,
                start=str(item.start),
                end=str(item.end),
                unit=item.unit,
                source=item.source,
                used=item.used,
                unused_reason=item.unused_reason,
            )
            for item in result.components
        ],
    )


def _read(text: str, label: str):
    nano = extract_with_nano(text)
    if nano is not None:
        labeled = _nano_to_labeled(nano)
        if labeled is not None:
            text = labeled
    try:
        return extract_document(text)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=f"Could not read the {label}. {error}") from error


def _nano_to_labeled(fields: dict[str, str]) -> str | None:
    required = ("supplier", "date", "grade", "size", "unit", "unit_price", "currency")
    if not all(fields.get(key) for key in required):
        return None
    quantity = fields.get("quantity") or "0"
    reason = fields.get("reason") or ""
    return "\n".join(
        [
            f"SUPPLIER: {fields['supplier']}",
            f"DATE: {fields['date']}",
            f"GRADE: {fields['grade']}",
            f"SIZE: {fields['size']}",
            f"QUANTITY: {quantity}",
            f"UNIT: {fields['unit']}",
            f"UNIT_PRICE: {fields['unit_price']}",
            f"CURRENCY: {fields['currency']}",
            f"REASON: {reason}",
        ]
    )


def _local_follow_up(question: str, note: str) -> str:
    asked = question.lower()
    if "bid" in asked or "90" in asked:
        return (
            "Use the accepted unit price in the audit note for a 90-day bid, and state that it includes "
            "only the explained market move. " + note
        )
    return "Send this reply: " + note


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "model_mode": "token-factory" if token_factory_configured() else "local-calculation"}
