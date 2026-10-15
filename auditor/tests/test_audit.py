import json
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient

from excuse_auditor.api import app
from excuse_auditor.audit import run_audit
from excuse_auditor.documents import grade_matches_materials
from excuse_auditor.extract import extract_document
from excuse_auditor.note import percent, verdict, write_note
from excuse_auditor.series import load_series, series_label

SAMPLES = Path(__file__).resolve().parents[1] / "samples"
SERIES = SAMPLES / "series.json"


def test_matching_quote_splits_market_from_supplier():
    invoice = extract_document((SAMPLES / "invoice.txt").read_text())
    quote = extract_document((SAMPLES / "quote.txt").read_text())
    result = run_audit(invoice, quote, SERIES, series_label(SERIES))

    assert result.comparable is True
    assert result.quote_change == Decimal("0.14")
    assert result.explained == Decimal("0.083")
    assert result.unexplained == Decimal("0.057")
    assert percent(result.quote_change) == "14.0%"
    assert percent(result.explained) == "8.3%"
    assert percent(result.unexplained) == "5.7%"
    assert result.fair_unit_price == Decimal("67146")
    assert result.trust.confidence == "medium"
    assert result.trust.series_demo is True
    assert result.trust.live_feed is False
    assert result.trust.material_scope == ("steel",)
    assert result.trust.extraction_invoice == "labeled"
    assert any("demonstration" in reason.lower() or "non-live" in reason.lower()
               for reason in result.trust.confidence_reasons)

    note = write_note(invoice, quote, result)
    assert "14.0%" in note
    assert "8.3%" in note
    assert "5.7%" in note
    assert "67146" in note
    assert "Demonstration series" in note
    assert verdict(result) == "The supplier's reason does not cover the full increase."


def test_mismatched_size_stops_before_a_percentage():
    invoice = extract_document((SAMPLES / "invoice.txt").read_text())
    quote = extract_document((SAMPLES / "quote_mismatch.txt").read_text())
    result = run_audit(invoice, quote, SERIES, series_label(SERIES))

    assert result.comparable is False
    assert result.quote_change is None
    assert "3 mm" in result.comparison_note
    assert "%" not in write_note(invoice, quote, result)


def test_whatsapp_quote_reads_the_same_commercial_terms():
    invoice = extract_document((SAMPLES / "invoice.txt").read_text())
    quote = extract_document((SAMPLES / "whatsapp.txt").read_text())
    result = run_audit(invoice, quote, SERIES, series_label(SERIES))

    assert quote.unit_price == Decimal("70680")
    assert quote.document_date.isoformat() == "2026-10-01"
    assert quote.extraction_method == "free_text"
    assert result.unexplained == Decimal("0.057")
    assert result.trust.extraction_quote == "free_text"


def test_freight_is_left_out_when_the_supplier_does_not_cite_it():
    invoice = extract_document((SAMPLES / "invoice.txt").read_text())
    quote = extract_document(
        (SAMPLES / "quote.txt").read_text().replace(
            "Sheet is up 14% because of imports and freight.",
            "Sheet is up 14% because of imports.",
        )
    )
    result = run_audit(invoice, quote, SERIES, series_label(SERIES))
    freight = next(item for item in result.components if item.name == "Sample freight index")

    assert freight.used is False
    assert result.explained == Decimal("0.067")


def test_series_discovers_components_without_hardcoded_steel_keys(tmp_path: Path):
    path = tmp_path / "aluminum.json"
    path.write_text(
        json.dumps(
            {
                "label": "Demo aluminum series",
                "scope": {
                    "demo": True,
                    "live_feed": False,
                    "materials": ["aluminum"],
                    "limitations": ["Demo aluminum only."],
                },
                "aluminum": {
                    "name": "Sample aluminum index",
                    "source": "test",
                    "unit": "index",
                    "requires_claim": [],
                    "points": [
                        {"date": "2026-06-01", "value": "100"},
                        {"date": "2026-10-01", "value": "110"},
                    ],
                },
                "freight": {
                    "name": "Sample freight",
                    "source": "test",
                    "unit": "index",
                    "requires_claim": ["freight"],
                    "points": [
                        {"date": "2026-06-01", "value": "100"},
                        {"date": "2026-10-01", "value": "102"},
                    ],
                },
            }
        )
    )
    series = load_series(path)
    assert series.component_keys == ("aluminum", "freight")

    invoice = extract_document(
        "\n".join(
            [
                "SUPPLIER: Alco",
                "DATE: 2026-06-01",
                "GRADE: Aluminum sheet",
                "SIZE: 2 mm",
                "QUANTITY: 5",
                "UNIT: MT",
                "UNIT_PRICE: 200000",
                "CURRENCY: INR",
            ]
        )
    )
    quote = extract_document(
        "\n".join(
            [
                "SUPPLIER: Alco",
                "DATE: 2026-10-01",
                "GRADE: Aluminum sheet",
                "SIZE: 2 mm",
                "QUANTITY: 5",
                "UNIT: MT",
                "UNIT_PRICE: 230000",
                "CURRENCY: INR",
                "REASON: Up because of aluminum market and freight.",
            ]
        )
    )
    result = run_audit(invoice, quote, path)

    assert result.comparable is True
    assert result.explained == Decimal("0.12")
    assert result.quote_change == Decimal("0.15")
    assert result.unexplained == Decimal("0.03")
    assert result.trust.material_scope == ("aluminum",)
    assert result.trust.confidence == "medium"
    assert {item.key for item in result.components} == {"aluminum", "freight"}


def test_out_of_scope_grade_lowers_confidence():
    invoice = extract_document(
        (SAMPLES / "invoice.txt").read_text().replace("CR sheet", "Aluminum sheet")
    )
    quote = extract_document(
        (SAMPLES / "quote.txt").read_text().replace("CR sheet", "Aluminum sheet")
    )
    result = run_audit(invoice, quote, SERIES)

    assert result.comparable is True
    assert result.trust.confidence == "low"
    assert any("outside loaded material scope" in reason for reason in result.trust.confidence_reasons)


def test_zero_unit_price_is_rejected():
    text = (SAMPLES / "invoice.txt").read_text().replace("UNIT_PRICE: 62000", "UNIT_PRICE: 0")
    try:
        extract_document(text)
        assert False, "expected extract failure for zero price"
    except ValueError as error:
        assert "could not read" in str(error).lower() or "unit price" in str(error).lower()


def test_grade_material_matching():
    assert grade_matches_materials("CR sheet", ("steel",))
    assert grade_matches_materials("Aluminum sheet", ("aluminum",))
    assert not grade_matches_materials("Aluminum sheet", ("steel",))
    assert grade_matches_materials("anything", ("unspecified",))


def test_api_audit_exposes_trust_and_preserves_math():
    client = TestClient(app)
    payload = {
        "invoice_text": (SAMPLES / "invoice.txt").read_text(),
        "quote_text": (SAMPLES / "quote.txt").read_text(),
    }
    response = client.post("/api/audits", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["quote_change"] == "14.0%"
    assert body["explained"] == "8.3%"
    assert body["unexplained"] == "5.7%"
    assert body["fair_unit_price"] == "67146"
    assert body["trust"]["confidence"] == "medium"
    assert body["trust"]["material_scope"] == ["steel"]
    assert body["trust"]["series_demo"] is True
    assert body["trust"]["live_feed"] is False
    assert any(item["key"] == "steel" for item in body["components"])


def test_api_samples_and_health_declare_scope():
    client = TestClient(app)
    samples = client.get("/api/samples").json()
    health = client.get("/api/health").json()
    assert samples["material_scope"] == ["steel"]
    assert samples["series_demo"] is True
    assert samples["live_feed"] is False
    assert health["material_scope"] == ["steel"]
    assert health["status"] == "ok"


def test_api_rejects_unreadable_document():
    client = TestClient(app)
    response = client.post(
        "/api/audits",
        json={"invoice_text": "hello", "quote_text": (SAMPLES / "quote.txt").read_text()},
    )
    assert response.status_code == 422


def test_api_rejects_oversized_fields():
    client = TestClient(app)
    huge = "x" * 50_001
    response = client.post(
        "/api/audits",
        json={"invoice_text": huge, "quote_text": (SAMPLES / "quote.txt").read_text()},
    )
    assert response.status_code == 422


def test_api_rejects_null_bytes():
    client = TestClient(app)
    response = client.post(
        "/api/audits",
        json={
            "invoice_text": "SUPPLIER: X\x00Y",
            "quote_text": (SAMPLES / "quote.txt").read_text(),
        },
    )
    assert response.status_code == 422


def test_security_headers_and_docs_disabled():
    client = TestClient(app)
    home = client.get("/")
    assert home.status_code == 200
    assert home.headers.get("x-frame-options") == "DENY"
    assert home.headers.get("x-content-type-options") == "nosniff"
    assert home.headers.get("referrer-policy") == "no-referrer"
    assert "frame-ancestors 'none'" in home.headers.get("content-security-policy", "")

    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.headers.get("cache-control") == "no-store"

    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404


def test_rate_limit_on_api(monkeypatch):
    from excuse_auditor import api as api_module

    monkeypatch.setattr(api_module, "RATE_LIMIT_MAX_REQUESTS", 3)

    def clear_rate_buckets(node):
        if node.__class__.__name__ == "RateLimitMiddleware":
            node._hits.clear()
            return True
        nested = getattr(node, "app", None)
        return clear_rate_buckets(nested) if nested is not None else False

    assert clear_rate_buckets(app.middleware_stack)

    client = TestClient(app)
    statuses = [client.get("/api/health").status_code for _ in range(4)]
    assert statuses[:3] == [200, 200, 200]
    assert statuses[3] == 429
