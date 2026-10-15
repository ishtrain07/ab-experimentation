from decimal import Decimal
from pathlib import Path

from excuse_auditor.audit import run_audit
from excuse_auditor.extract import extract_document
from excuse_auditor.note import percent, verdict, write_note
from excuse_auditor.series import series_label

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
    assert result.unexplained == Decimal("0.057")


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
