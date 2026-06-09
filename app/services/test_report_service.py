"""Unit tests for report rendering helpers (Task 12.1, Req 14.1, 14.2).

Covers the pure CSV/PDF builders in :mod:`app.services.report_service` that do
not need a DB: column union, blank cells for missing keys, CSV structure, and a
valid PDF byte stream.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.core.errors import ValidationError
from app.services import report_service as rs
from app.services.report_service import ReportRow

_BASE = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)


def _rows() -> list[ReportRow]:
    return [
        ReportRow(device_id="dev-a", ts=_BASE, data={"temp": 10.0, "hum": 60}),
        ReportRow(device_id="dev-a", ts=_BASE, data={"temp": 11.0}),
    ]


def test_sensor_keys_union_sorted():
    assert rs._sensor_keys(_rows()) == ["hum", "temp"]


def test_generate_csv_header_and_rows():
    out = rs.generate_csv(_rows()).decode("utf-8")
    lines = out.strip().split("\n")
    assert lines[0] == "device_id,ts,hum,temp"
    # First row has both keys.
    assert lines[1] == f"dev-a,{_BASE.isoformat()},60,10.0"
    # Second row is missing hum -> blank cell.
    assert lines[2] == f"dev-a,{_BASE.isoformat()},,11.0"


def test_generate_csv_empty_rows_has_header_only():
    out = rs.generate_csv([]).decode("utf-8")
    assert out.strip() == "device_id,ts"


def test_generate_pdf_is_valid_pdf_stream():
    pdf = rs.generate_pdf(_rows())
    assert pdf.startswith(b"%PDF-1.4")
    assert pdf.rstrip().endswith(b"%%EOF")
    assert b"/Type /Catalog" in pdf
    assert b"xref" in pdf
    assert b"trailer" in pdf
    # The report content should reference the device id.
    assert b"dev-a" in pdf


def test_generate_pdf_handles_empty_rows():
    pdf = rs.generate_pdf([])
    assert pdf.startswith(b"%PDF-1.4")
    assert b"no telemetry" in pdf


def test_pdf_escapes_special_characters():
    rows = [ReportRow(device_id="a(b)c\\", ts=_BASE, data={"k": "v)("})]
    pdf = rs.generate_pdf(rows)
    # Parentheses/backslashes in content must be escaped, never raw-unbalanced.
    assert b"\\(" in pdf and b"\\)" in pdf


def test_render_dispatches_by_format():
    assert rs.render(_rows(), "csv").startswith(b"device_id")
    assert rs.render(_rows(), "pdf").startswith(b"%PDF")


def test_render_rejects_unknown_format():
    with pytest.raises(ValidationError) as exc:
        rs.render(_rows(), "xlsx")
    assert exc.value.error_code == "invalid_report_format"


# ---------------------------------------------------------------------------
# Known multi-device telemetry set (Task 12.2, Req 14.1, 14.2)
# ---------------------------------------------------------------------------
_T0 = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
_T1 = datetime(2025, 1, 1, 0, 5, 0, tzinfo=timezone.utc)


def _known_set() -> list[ReportRow]:
    """A fixed two-device telemetry set with overlapping/disjoint sensor keys."""
    return [
        ReportRow(device_id="dev-a", ts=_T0, data={"temp": 20.5, "hum": 55}),
        ReportRow(device_id="dev-a", ts=_T1, data={"temp": 21.0, "hum": 54}),
        ReportRow(device_id="dev-b", ts=_T0, data={"temp": 18.0, "co2": 410}),
    ]


def test_generate_csv_content_for_known_set():
    """CSV content matches the expected file exactly for a known set (Req 14.1)."""
    out = rs.generate_csv(_known_set()).decode("utf-8")
    expected = (
        "device_id,ts,co2,hum,temp\n"
        f"dev-a,{_T0.isoformat()},,55,20.5\n"
        f"dev-a,{_T1.isoformat()},,54,21.0\n"
        f"dev-b,{_T0.isoformat()},410,,18.0\n"
    )
    assert out == expected


def test_generate_pdf_content_for_known_set():
    """PDF content includes every device id and sensor value of a known set (Req 14.2)."""
    pdf = rs.generate_pdf(_known_set())
    assert pdf.startswith(b"%PDF-1.4")
    assert pdf.rstrip().endswith(b"%%EOF")
    # Report title and the union header line are rendered.
    assert b"IoTAPS Telemetry Report" in pdf
    assert b"device_id | ts | co2 | hum | temp" in pdf
    # Both devices and a representative value from each appear in the content.
    assert b"dev-a" in pdf and b"dev-b" in pdf
    assert b"410" in pdf and b"20.5" in pdf and b"18.0" in pdf
