"""Aggregate router for API v1.

All v1 resource routers are included here and mounted under the `/api/v1`
prefix by the application factory. Later tasks add auth, devices, telemetry,
dashboards, billing, admin, etc. as separate router modules included below.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import (
    admin,
    admin_content,
    admin_nodes,
    admin_ops,
    admin_revenue,
    auth,
    billing,
    changelog,
    commands,
    dashboards,
    devices,
    health,
    partner,
    referrals,
    reports,
    rules,
    support,
    telemetry,
    templates,
)

api_v1_router = APIRouter()

api_v1_router.include_router(health.router)
api_v1_router.include_router(auth.router)
api_v1_router.include_router(devices.router)
api_v1_router.include_router(telemetry.router)
api_v1_router.include_router(rules.router)
api_v1_router.include_router(templates.router)
api_v1_router.include_router(commands.router)
api_v1_router.include_router(dashboards.router)
api_v1_router.include_router(dashboards.public_router)
api_v1_router.include_router(billing.router)
api_v1_router.include_router(referrals.router)
api_v1_router.include_router(reports.router)
api_v1_router.include_router(partner.router)
api_v1_router.include_router(partner.admin_router)
api_v1_router.include_router(support.router)
api_v1_router.include_router(changelog.router)
api_v1_router.include_router(admin.router)
api_v1_router.include_router(admin_content.router)
api_v1_router.include_router(admin_nodes.router)
api_v1_router.include_router(admin_ops.router)
api_v1_router.include_router(admin_revenue.router)
