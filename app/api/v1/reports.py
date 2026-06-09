"""Reports API endpoints (Task 12.1, Req 14).

Implements the report surface from design.md ("Telemetry & Reports"):

    POST   /reports            {device_ids, from, to, format} -> {download_url}
    POST   /reports/schedule   {query, schedule_cron, destination} -> {scheduled_report}
    GET    /reports/{id}/download                              -> file (csv/pdf)

``POST /reports`` generates a one-off CSV or PDF report from a telemetry query
(Req 14.1, 14.2), persists its definition, and returns a ``download_url`` the
client follows to fetch the file. ``POST /reports/schedule`` stores a cron-driven
report plus a delivery destination for the report worker to regenerate and
deliver on schedule (Req 14.3).

All routes require an authenticated principal and are tenant-scoped: telemetry is
read through the tenant scope so cross-org device ids are denied (Req 3.3) and a
Device_User is restricted to devices assigned to them (Req 2.4). Any role may
generate reports over devices they can access.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.security.deps import get_principal, tenant_scope
from app.core.security.principal import Principal
from app.core.security.tenant import TenantScope
from app.models.ops import ScheduledReport
from app.services.report_service import (
    CONTENT_TYPES,
    ReportService,
)

router = APIRouter(prefix="/reports", tags=["reports"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class GenerateReportRequest(BaseModel):
    device_ids: list[uuid.UUID] = Field(min_length=1)
    from_: datetime | None = Field(default=None, alias="from")
    to: datetime | None = Field(default=None)
    format: str = Field(default="csv", description="'csv' or 'pdf'")
    resolution: str = Field(default="raw", description="raw|5m|1h|1d")

    model_config = {"populate_by_name": True}


class GenerateReportResponse(BaseModel):
    report_id: str
    format: str
    download_url: str


class ScheduledReportOut(BaseModel):
    id: str
    org_id: str
    user_id: str | None
    format: str
    query: dict | None
    schedule_cron: str | None
    destination: str | None


class ScheduleReportRequest(BaseModel):
    query: dict
    schedule_cron: str = Field(min_length=1)
    destination: str = Field(min_length=1)


class ScheduleReportResponse(BaseModel):
    scheduled_report: ScheduledReportOut


def _scheduled_report_out(report: ScheduledReport) -> ScheduledReportOut:
    return ScheduledReportOut(
        id=str(report.id),
        org_id=str(report.org_id),
        user_id=str(report.user_id) if report.user_id else None,
        format=report.format,
        query=report.query,
        schedule_cron=report.schedule_cron,
        destination=report.destination,
    )


def _download_url(report_id: uuid.UUID) -> str:
    base = get_settings().public_base_url.rstrip("/")
    return f"{base}/api/v1/reports/{report_id}/download"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.post("", response_model=GenerateReportResponse, status_code=201)
async def generate_report(
    payload: GenerateReportRequest,
    scope: TenantScope = Depends(tenant_scope),
    _: Principal = Depends(get_principal),
) -> GenerateReportResponse:
    """Generate a one-off CSV/PDF report and return its download URL (Req 14.1, 14.2)."""
    service = ReportService(scope)
    report, _content = await service.generate(
        device_ids=payload.device_ids,
        start=payload.from_,
        end=payload.to,
        format=payload.format,
        resolution=payload.resolution,
    )
    return GenerateReportResponse(
        report_id=str(report.id),
        format=report.format,
        download_url=_download_url(report.id),
    )


@router.post("/schedule", response_model=ScheduleReportResponse, status_code=201)
async def schedule_report(
    payload: ScheduleReportRequest,
    scope: TenantScope = Depends(tenant_scope),
    _: Principal = Depends(get_principal),
) -> ScheduleReportResponse:
    """Schedule a cron-driven report delivered to a destination (Req 14.3)."""
    service = ReportService(scope)
    report = await service.schedule(
        query=payload.query,
        schedule_cron=payload.schedule_cron,
        destination=payload.destination,
    )
    return ScheduleReportResponse(scheduled_report=_scheduled_report_out(report))


@router.get("/{report_id}/download")
async def download_report(
    report_id: uuid.UUID,
    scope: TenantScope = Depends(tenant_scope),
    _: Principal = Depends(get_principal),
) -> Response:
    """Render and stream a previously generated report's file (Req 14.1, 14.2).

    The report is re-rendered from its persisted query so the latest telemetry in
    range is included. Tenant ownership is enforced when loading the report
    (Req 3.3).
    """
    service = ReportService(scope)
    report = await service.get_report(report_id)
    content = await service.regenerate(report)
    media_type = CONTENT_TYPES.get(report.format, "application/octet-stream")
    filename = f"report-{report.id}.{report.format}"
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
