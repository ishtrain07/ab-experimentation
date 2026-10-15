import os
import time
from collections import defaultdict, deque
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field, field_validator
from starlette.middleware.base import BaseHTTPMiddleware

from .audit import run_audit
from .extract import extract_document
from .nemotron import extract_with_nano, token_factory_configured, write_with_super
from .note import money, percent, verdict, write_note

ROOT = Path(__file__).resolve().parents[2]
SAMPLES = ROOT / "samples"
SERIES_PATH = SAMPLES / "series.json"
STATIC = ROOT / "static" / "index.html"
MAX_DOCUMENT_CHARS = 50_000
MAX_QUESTION_CHARS = 4_000
MAX_BODY_BYTES = 120_000
RATE_LIMIT_WINDOW_SEC = 60
RATE_LIMIT_MAX_REQUESTS = 30
_PUBLIC_DOCS = os.environ.get("AUDITOR_ENABLE_DOCS", "").strip().lower() in {"1", "true", "yes"}

app = FastAPI(
    title="Market Excuse Auditor",
    docs_url="/docs" if _PUBLIC_DOCS else None,
    redoc_url="/redoc" if _PUBLIC_DOCS else None,
    openapi_url="/openapi.json" if _PUBLIC_DOCS else None,
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method == "POST" and request.url.path.startswith("/api/"):
            content_length = request.headers.get("content-length")
            if content_length is not None:
                try:
                    if int(content_length) > MAX_BODY_BYTES:
                        return JSONResponse(
                            status_code=413,
                            content={"detail": "Request body is too large."},
                        )
                except ValueError:
                    return JSONResponse(status_code=400, content={"detail": "Invalid Content-Length."})

        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data:; "
            "connect-src 'self'; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self'",
        )
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
            response.headers["Pragma"] = "no-cache"
        elif request.url.path == "/":
            response.headers.setdefault("Cache-Control", "no-cache")
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def _client_key(self, request: Request) -> str:
        forwarded = request.headers.get("cf-connecting-ip") or request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip() or "unknown"
        if request.client and request.client.host:
            return request.client.host
        return "unknown"

    async def dispatch(self, request: Request, call_next):
        if not request.url.path.startswith("/api/"):
            return await call_next(request)
        now = time.monotonic()
        key = self._client_key(request)
        bucket = self._hits[key]
        while bucket and now - bucket[0] > RATE_LIMIT_WINDOW_SEC:
            bucket.popleft()
        if len(bucket) >= RATE_LIMIT_MAX_REQUESTS:
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Wait a minute and try again."},
                headers={"Retry-After": str(RATE_LIMIT_WINDOW_SEC)},
            )
        bucket.append(now)
        return await call_next(request)


app.add_middleware(RateLimitMiddleware)
app.add_middleware(SecurityHeadersMiddleware)


class AuditRequest(BaseModel):
    invoice_text: str = Field(min_length=1, max_length=MAX_DOCUMENT_CHARS)
    quote_text: str = Field(min_length=1, max_length=MAX_DOCUMENT_CHARS)
    question: str = Field(default="", max_length=MAX_QUESTION_CHARS)

    @field_validator("invoice_text", "quote_text", "question")
    @classmethod
    def strip_nulls(cls, value: str) -> str:
        if "\x00" in value:
            raise ValueError("Null bytes are not allowed.")
        return value


class ComponentView(BaseModel):
    name: str
    key: str
    change: str | None
    start: str
    end: str
    unit: str
    source: str
    used: bool
    unused_reason: str


class TrustView(BaseModel):
    confidence: str
    confidence_reasons: list[str]
    limitations: list[str]
    material_scope: list[str]
    series_demo: bool
    live_feed: bool
    extraction_invoice: str
    extraction_quote: str


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
    trust: TrustView


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC)


@app.get("/api/samples")
def samples() -> dict[str, object]:
    from .series import load_series

    series = load_series(SERIES_PATH)
    return {
        "invoice": (SAMPLES / "invoice.txt").read_text(),
        "quote": (SAMPLES / "quote.txt").read_text(),
        "quote_mismatch": (SAMPLES / "quote_mismatch.txt").read_text(),
        "whatsapp": (SAMPLES / "whatsapp.txt").read_text(),
        "series_label": series.label,
        "material_scope": list(series.scope.materials),
        "series_demo": series.scope.demo,
        "live_feed": series.scope.live_feed,
        "limitations": list(series.scope.limitations),
    }


@app.post("/api/audits", response_model=AuditView)
def create_audit(body: AuditRequest) -> AuditView:
    invoice = _read(body.invoice_text, "invoice")
    quote = _read(body.quote_text, "quote")
    result = run_audit(invoice, quote, SERIES_PATH)
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
                key=item.key,
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
        trust=TrustView(
            confidence=result.trust.confidence,
            confidence_reasons=list(result.trust.confidence_reasons),
            limitations=list(result.trust.limitations),
            material_scope=list(result.trust.material_scope),
            series_demo=result.trust.series_demo,
            live_feed=result.trust.live_feed,
            extraction_invoice=result.trust.extraction_invoice,
            extraction_quote=result.trust.extraction_quote,
        ),
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
def health() -> dict[str, object]:
    from .series import load_series

    series = load_series(SERIES_PATH)
    return {
        "status": "ok",
        "model_mode": "token-factory" if token_factory_configured() else "local-calculation",
        "material_scope": list(series.scope.materials),
        "series_demo": series.scope.demo,
        "live_feed": series.scope.live_feed,
    }


@app.exception_handler(Exception)
async def unhandled_error(_request: Request, _exc: Exception) -> Response:
    return JSONResponse(status_code=500, content={"detail": "Internal server error."})
