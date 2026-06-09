"""Report generation and scheduling service (Task 12.1, Req 14).

Backs the report surface from design.md ("Telemetry & Reports"):

    POST /reports            {device_ids, from, to, format} -> {download_url}
    POST /reports/schedule   {query, schedule_cron, destination} -> {scheduled_report}

A report renders telemetry for one or more devices over a time range into either
a CSV file (Req 14.1) or a PDF file (Req 14.2). A scheduled report stores a cron
expression plus a delivery destination so a worker can regenerate and deliver it
on a recurring basis (Req 14.3).

Both one-off and scheduled reports are persisted as ``scheduled_reports`` rows:
a one-off report simply has ``schedule_cron = NULL``. The report's query (device
ids + time range + format) is stored in the JSONB ``query`` column so the file
can be regenerated on demand (one-off download) or on schedule (delivery).

Everything is tenant-scoped: telemetry is read through
:class:`~app.services.telemetry_service.TelemetryService`, which loads each
device via :class:`~app.core.security.tenant.TenantScope` (denying cross-org ids,
Req 3.3). Device_User callers are additionally restricted to devices explicitly
assigned to them (Req 2.4) via ``user_has_device_access``.

The CSV and PDF builders are pure functions over plain rows so they can be unit
tested without a DB (Task 12.2). The PDF builder emits a minimal but valid
PDF 1.4 document by hand, avoiding any third-party reporting dependency.
"""

from __future__ import annotations

import csv
import io
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from app.core.errors import ValidationError
from app.core.security.deps import user_has_device_access
from app.core.security.tenant import TenantScope
from app.models.ops import ScheduledReport
from app.services.telemetry_service import (
    MAX_LIMIT,
    RESOLUTION_RAW,
    TelemetryService,
    resolve_source,
)

# Supported output formats (design.md ``reports.format`` -> csv / pdf).
FORMAT_CSV = "csv"
FORMAT_PDF = "pdf"
VALID_FORMATS = (FORMAT_CSV, FORMAT_PDF)

# Content types per format, used by the download endpoint.
CONTENT_TYPES = {
    FORMAT_CSV: "text/csv",
    FORMAT_PDF: "application/pdf",
}


@dataclass(frozen=True)
class ReportRow:
    """A single rendered telemetry sample for one device."""

    device_id: str
    ts: datetime
    data: dict


# ---------------------------------------------------------------------------
# Pure rendering helpers (Task 12.2 unit-tests these directly)
# ---------------------------------------------------------------------------
def _sensor_keys(rows: list[ReportRow]) -> list[str]:
    """Return the sorted union of sensor keys across all rows.

    Telemetry payloads are schemaless per device, so the column set is the union
    of every ``data`` dict's keys, kept stable (sorted) for deterministic output.
    """
    keys: set[str] = set()
    for row in rows:
        keys.update(str(k) for k in row.data.keys())
    return sorted(keys)


def _format_ts(ts: datetime) -> str:
    """Render a timestamp as ISO-8601 (UTC-normalised when tz-aware)."""
    if isinstance(ts, datetime):
        return ts.isoformat()
    return str(ts)


def _cell(value: object) -> str:
    """Render a sensor value as a string, leaving missing values blank."""
    if value is None:
        return ""
    return str(value)


def generate_csv(rows: list[ReportRow]) -> bytes:
    """Render report rows as CSV bytes (Req 14.1).

    The header is ``device_id, ts`` followed by every sensor key seen across the
    rows; a row leaves a cell blank when that device's sample lacks the key.
    """
    keys = _sensor_keys(rows)
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["device_id", "ts", *keys])
    for row in rows:
        writer.writerow(
            [
                row.device_id,
                _format_ts(row.ts),
                *[_cell(row.data.get(k)) for k in keys],
            ]
        )
    return buffer.getvalue().encode("utf-8")


def _escape_pdf_text(text: str) -> str:
    """Escape characters that are special inside a PDF literal string."""
    return (
        text.replace("\\", r"\\")
        .replace("(", r"\(")
        .replace(")", r"\)")
        .replace("\r", " ")
        .replace("\n", " ")
    )


def _report_lines(rows: list[ReportRow]) -> list[str]:
    """Build the human-readable text lines rendered into the PDF."""
    keys = _sensor_keys(rows)
    lines = ["IoTAPS Telemetry Report", f"Generated: {datetime.now(timezone.utc).isoformat()}", ""]
    header = "device_id | ts | " + " | ".join(keys) if keys else "device_id | ts"
    lines.append(header)
    for row in rows:
        cells = " | ".join(_cell(row.data.get(k)) for k in keys)
        line = f"{row.device_id} | {_format_ts(row.ts)}"
        if cells:
            line += f" | {cells}"
        lines.append(line)
    if not rows:
        lines.append("(no telemetry for the requested range)")
    return lines


def generate_pdf(rows: list[ReportRow]) -> bytes:
    """Render report rows as a minimal, valid PDF 1.4 document (Req 14.2).

    Builds a single-page PDF with the report text using the built-in Helvetica
    font. This avoids a third-party reporting dependency while still producing a
    file any PDF reader can open (``%PDF`` header, object table, xref, trailer).
    """
    lines = _report_lines(rows)

    # ---- content stream: lay out text lines top-to-bottom ----
    leading = 14
    content_ops = ["BT", "/F1 10 Tf", f"{leading} TL", "50 760 Td"]
    for index, line in enumerate(lines):
        escaped = _escape_pdf_text(line)
        if index > 0:
            content_ops.append("T*")
        content_ops.append(f"({escaped}) Tj")
    content_ops.append("ET")
    content_stream = "\n".join(content_ops).encode("latin-1", "replace")

    # ---- PDF objects ----
    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>"
        ),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length %d >>\nstream\n%s\nendstream"
        % (len(content_stream), content_stream),
    ]

    pdf = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf += b"%d 0 obj\n" % number
        pdf += body
        pdf += b"\nendobj\n"

    xref_pos = len(pdf)
    count = len(objects) + 1  # +1 for the free object 0
    pdf += b"xref\n"
    pdf += b"0 %d\n" % count
    pdf += b"0000000000 65535 f \n"
    for offset in offsets:
        pdf += b"%010d 00000 n \n" % offset
    pdf += b"trailer\n"
    pdf += b"<< /Size %d /Root 1 0 R >>\n" % count
    pdf += b"startxref\n"
    pdf += b"%d\n" % xref_pos
    pdf += b"%%EOF"
    return bytes(pdf)


def render(rows: list[ReportRow], format: str) -> bytes:
    """Render rows into the requested format's bytes (Req 14.1, 14.2)."""
    if format == FORMAT_CSV:
        return generate_csv(rows)
    if format == FORMAT_PDF:
        return generate_pdf(rows)
    raise ValidationError(
        f"Unsupported report format: {format!r}; expected one of "
        f"{', '.join(VALID_FORMATS)}",
        error_code="invalid_report_format",
    )


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------
def _validate_format(format: str) -> str:
    if format not in VALID_FORMATS:
        raise ValidationError(
            f"Unsupported report format: {format!r}; expected one of "
            f"{', '.join(VALID_FORMATS)}",
            error_code="invalid_report_format",
        )
    return format


def _coerce_dt(value: object) -> datetime | None:
    """Parse an ISO-8601 string / datetime into a datetime, or None."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except (ValueError, TypeError) as exc:
        raise ValidationError(
            f"Invalid datetime value: {value!r}",
            error_code="invalid_report_query",
        ) from exc


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------
class ReportService:
    """Tenant-scoped report generation and scheduling (Req 14)."""

    def __init__(self, scope: TenantScope) -> None:
        self._scope = scope
        self._session = scope.session
        self._telemetry = TelemetryService(scope)

    @property
    def _org_uuid(self) -> uuid.UUID:
        return uuid.UUID(str(self._scope.org_id))

    def _owner_user_uuid(self) -> uuid.UUID | None:
        try:
            return uuid.UUID(str(self._scope.principal.user_id))
        except (ValueError, TypeError):
            return None

    async def _assert_device_access(self, device_id: uuid.UUID) -> None:
        """Deny a Device_User report over a device not assigned to them (Req 2.4)."""
        allowed = await user_has_device_access(
            self._session, self._scope.principal, str(device_id)
        )
        if not allowed:
            from app.core.errors import AuthorizationError

            raise AuthorizationError(
                "You do not have access to this device",
                error_code="authorization_error",
            )

    async def collect_rows(
        self,
        device_ids: list[uuid.UUID],
        *,
        start: datetime | None,
        end: datetime | None,
        resolution: str = RESOLUTION_RAW,
    ) -> list[ReportRow]:
        """Gather telemetry rows for the requested devices and range (Req 14.1, 14.2).

        Each device is read through the tenant-scoped telemetry service, so a
        cross-org id is denied (Req 3.3) and a Device_User only sees assigned
        devices (Req 2.4). Rows are ordered by (device_id, ts).
        """
        if not device_ids:
            raise ValidationError(
                "At least one device_id is required",
                error_code="invalid_report_query",
            )
        # Validate the resolution up front (raises on unknown values).
        resolve_source(resolution)

        rows: list[ReportRow] = []
        for device_id in device_ids:
            await self._assert_device_access(device_id)
            points = await self._telemetry.query(
                device_id,
                resolution=resolution,
                start=start,
                end=end,
                limit=MAX_LIMIT,
            )
            for point in points:
                rows.append(
                    ReportRow(
                        device_id=str(device_id),
                        ts=point.ts,
                        data=point.data,
                    )
                )
        return rows

    async def generate(
        self,
        *,
        device_ids: list[uuid.UUID],
        start: datetime | None,
        end: datetime | None,
        format: str,
        resolution: str = RESOLUTION_RAW,
    ) -> tuple[ScheduledReport, bytes]:
        """Generate a one-off report and persist its definition (Req 14.1, 14.2).

        Returns the stored ``ScheduledReport`` row (``schedule_cron = NULL``) and
        the rendered file bytes. The query is stored so the file can be
        regenerated by the download endpoint.
        """
        fmt = _validate_format(format)
        rows = await self.collect_rows(
            device_ids, start=start, end=end, resolution=resolution
        )
        content = render(rows, fmt)

        report = ScheduledReport(
            org_id=self._org_uuid,
            user_id=self._owner_user_uuid(),
            format=fmt,
            query={
                "device_ids": [str(d) for d in device_ids],
                "from": start.isoformat() if start else None,
                "to": end.isoformat() if end else None,
                "resolution": resolution,
                "format": fmt,
            },
            schedule_cron=None,
            destination=None,
            last_run_at=datetime.now(timezone.utc),
        )
        self._session.add(report)
        await self._session.commit()
        await self._session.refresh(report)
        return report, content

    async def regenerate(self, report: ScheduledReport) -> bytes:
        """Re-render a stored report from its persisted query (download/delivery)."""
        query = report.query or {}
        device_ids = [uuid.UUID(str(d)) for d in query.get("device_ids", [])]
        start = _coerce_dt(query.get("from"))
        end = _coerce_dt(query.get("to"))
        resolution = query.get("resolution") or RESOLUTION_RAW
        rows = await self.collect_rows(
            device_ids, start=start, end=end, resolution=resolution
        )
        return render(rows, report.format)

    async def get_report(self, report_id: uuid.UUID) -> ScheduledReport:
        """Fetch a report by id, enforcing tenant ownership (Req 3.3)."""
        return await self._scope.get(ScheduledReport, report_id)

    async def schedule(
        self,
        *,
        query: dict,
        schedule_cron: str,
        destination: str,
    ) -> ScheduledReport:
        """Persist a scheduled report definition (Req 14.3).

        ``query`` carries ``{device_ids, from?, to?, resolution?, format?}``; the
        cron expression and destination drive recurring generation + delivery by
        the report worker. The format defaults to CSV when omitted.
        """
        if not isinstance(query, dict):
            raise ValidationError(
                "query must be an object", error_code="invalid_report_query"
            )
        if not schedule_cron or not str(schedule_cron).strip():
            raise ValidationError(
                "schedule_cron is required", error_code="invalid_report_schedule"
            )
        if not destination or not str(destination).strip():
            raise ValidationError(
                "destination is required", error_code="invalid_report_schedule"
            )

        fmt = _validate_format(query.get("format", FORMAT_CSV))
        device_ids = query.get("device_ids") or []
        if not device_ids:
            raise ValidationError(
                "query.device_ids is required",
                error_code="invalid_report_query",
            )
        resolution = query.get("resolution") or RESOLUTION_RAW
        resolve_source(resolution)  # validate
        # Validate datetime fields eagerly so a bad schedule fails fast.
        _coerce_dt(query.get("from"))
        _coerce_dt(query.get("to"))

        report = ScheduledReport(
            org_id=self._org_uuid,
            user_id=self._owner_user_uuid(),
            format=fmt,
            query={
                "device_ids": [str(d) for d in device_ids],
                "from": query.get("from"),
                "to": query.get("to"),
                "resolution": resolution,
                "format": fmt,
            },
            schedule_cron=str(schedule_cron).strip(),
            destination=str(destination).strip(),
            last_run_at=None,
        )
        self._session.add(report)
        await self._session.commit()
        await self._session.refresh(report)
        return report
