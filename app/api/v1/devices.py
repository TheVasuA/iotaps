"""Devices API endpoints (Task 4.1, Req 5).

Implements the device surface from design.md ("Devices"):

    GET    /devices                       ?group_id&status -> [device]
    POST   /devices                       {label, group_id?, template_id?}
                                          -> {device, mqtt_credentials, qr}
    GET    /devices/{id}                  -> {device}
    PATCH  /devices/{id}                  {label?, group_id?, maintenance_mode?}
                                          -> {device}
    DELETE /devices/{id}                  -> 204   (revokes MQTT credentials)
    POST   /devices/{id}/assign           {user_id} -> 204
    POST   /devices/groups                {name} -> {group}
    GET    /devices/{id}/qr               -> image/png

Device provisioning/management is restricted to Project_Center (and Super_Admin,
who is always permitted) via ``require_role`` (Req 2.2). All queries go through
``TenantScope`` so they are auto-filtered to the caller's organization (Req 3.2,
3.3). Telemetry, commands, and the simulator live in their own tasks/routers.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Response, status
from fastapi.responses import Response as RawResponse
from pydantic import BaseModel, Field

from app.core.security.deps import require_role, tenant_scope
from app.core.security.principal import (
    ROLE_PROJECT_CENTER,
    ROLE_SUPER_ADMIN,
    Principal,
)
from app.core.security.tenant import TenantScope
from app.models.device import Device, DeviceGroup, MqttCredential
from app.services.device_service import DeviceService
from app.services.template_service import TemplateService

router = APIRouter(prefix="/devices", tags=["devices"])

# Roles permitted to manage devices (Super_Admin is always allowed by
# require_role, but listing it documents intent).
_MANAGE_ROLES = (ROLE_PROJECT_CENTER, ROLE_SUPER_ADMIN)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class DeviceOut(BaseModel):
    id: str
    org_id: str
    device_uid: str | None
    label: str | None
    group_id: str | None
    node_id: str | None
    status: str
    maintenance_mode: bool
    is_simulator: bool
    sim_interval_sec: int
    firmware_version: str | None
    template_id: str | None
    device_token: str | None = None


class MqttCredentialOut(BaseModel):
    id: str
    device_token: str
    acl_pattern: str | None
    revoked: bool


class CreateDeviceRequest(BaseModel):
    label: str | None = Field(default=None, max_length=256)
    group_id: uuid.UUID | None = None
    template_id: uuid.UUID | None = None
    device_uid: str | None = Field(default=None, max_length=128)


class ProvisionDeviceResponse(BaseModel):
    device: DeviceOut
    mqtt_credentials: MqttCredentialOut
    qr: str


class UpdateDeviceRequest(BaseModel):
    label: str | None = Field(default=None, max_length=256)
    group_id: uuid.UUID | None = None
    maintenance_mode: bool | None = None

    # Track which optional fields were explicitly provided so we can tell
    # "omitted" from "set to null" for nullable columns.
    model_config = {"extra": "forbid"}


class DeviceResponse(BaseModel):
    device: DeviceOut


class CreateGroupRequest(BaseModel):
    name: str = Field(min_length=1, max_length=256)


class GroupOut(BaseModel):
    id: str
    name: str


class GroupResponse(BaseModel):
    group: GroupOut


class AssignDeviceRequest(BaseModel):
    user_id: uuid.UUID


class ApplyTemplateRequest(BaseModel):
    template_id: uuid.UUID


class StartSimulatorRequest(BaseModel):
    # interval_sec >= 0; 0 means "configured but do not publish" (Req 13.3).
    interval_sec: int = Field(ge=0)

    model_config = {"extra": "forbid"}


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------
def _device_out(device: Device, device_token: str | None = None) -> DeviceOut:
    return DeviceOut(
        id=str(device.id),
        org_id=str(device.org_id),
        device_uid=device.device_uid,
        label=device.label,
        group_id=str(device.group_id) if device.group_id else None,
        node_id=str(device.node_id) if device.node_id else None,
        status=device.status,
        maintenance_mode=bool(device.maintenance_mode),
        is_simulator=bool(device.is_simulator),
        sim_interval_sec=device.sim_interval_sec,
        firmware_version=device.firmware_version,
        template_id=str(device.template_id) if device.template_id else None,
        device_token=device_token,
    )


def _credential_out(credential: MqttCredential, secret: str | None = None) -> MqttCredentialOut:
    return MqttCredentialOut(
        id=str(credential.id),
        device_token=credential.token,
        acl_pattern=credential.acl_pattern,
        revoked=bool(credential.revoked),
    )


def _group_out(group: DeviceGroup) -> GroupOut:
    return GroupOut(id=str(group.id), name=group.name)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.get("", response_model=list[DeviceOut])
async def list_devices(
    group_id: uuid.UUID | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    scope: TenantScope = Depends(tenant_scope),
    _: Principal = Depends(require_role(*_MANAGE_ROLES)),
) -> list[DeviceOut]:
    """List devices in the caller's organization with MQTT credentials (Req 3.2)."""
    service = DeviceService(scope)
    devices = await service.list_devices(group_id=group_id, status=status_filter)

    # Fetch device tokens for each device
    from sqlalchemy import select
    from app.models.device import MqttCredential
    result_list = []
    for d in devices:
        cred_result = await scope.session.execute(
            select(MqttCredential).where(
                MqttCredential.device_id == d.id,
                MqttCredential.revoked == False,
            ).limit(1)
        )
        cred = cred_result.scalar_one_or_none()
        result_list.append(_device_out(
            d,
            device_token=cred.token if cred else None,
        ))
    return result_list


@router.post("", response_model=ProvisionDeviceResponse, status_code=201)
async def create_device(
    payload: CreateDeviceRequest,
    scope: TenantScope = Depends(tenant_scope),
    _: Principal = Depends(require_role(*_MANAGE_ROLES)),
) -> ProvisionDeviceResponse:
    """Provision a device with unique MQTT credentials and a QR code (Req 5.1, 5.2)."""
    service = DeviceService(scope)
    device, credential, secret = await service.provision_device(
        label=payload.label,
        group_id=payload.group_id,
        template_id=payload.template_id,
        device_uid=payload.device_uid,
    )
    from app.services.device_service import build_qr_payload

    return ProvisionDeviceResponse(
        device=_device_out(device, device_token=credential.token),
        mqtt_credentials=_credential_out(credential),
        qr=build_qr_payload(device),
    )


@router.post("/groups", response_model=GroupResponse, status_code=201)
async def create_group(
    payload: CreateGroupRequest,
    scope: TenantScope = Depends(tenant_scope),
    _: Principal = Depends(require_role(*_MANAGE_ROLES)),
) -> GroupResponse:
    """Create a device group (Req 5.5)."""
    service = DeviceService(scope)
    group = await service.create_group(payload.name)
    return GroupResponse(group=_group_out(group))


@router.get("/{device_id}", response_model=DeviceResponse)
async def get_device(
    device_id: uuid.UUID,
    scope: TenantScope = Depends(tenant_scope),
    _: Principal = Depends(require_role(*_MANAGE_ROLES)),
) -> DeviceResponse:
    """Fetch a single device (tenant-scoped, Req 3.3)."""
    service = DeviceService(scope)
    device = await service.get_device(device_id)
    return DeviceResponse(device=_device_out(device))


@router.patch("/{device_id}", response_model=DeviceResponse)
async def update_device(
    device_id: uuid.UUID,
    payload: UpdateDeviceRequest,
    scope: TenantScope = Depends(tenant_scope),
    _: Principal = Depends(require_role(*_MANAGE_ROLES)),
) -> DeviceResponse:
    """Rename / regroup / toggle maintenance for a device (Req 5.3-5.5, 5.7)."""
    fields_set = payload.model_fields_set
    service = DeviceService(scope)
    device = await service.update_device(
        device_id,
        label=payload.label,
        group_id=payload.group_id,
        maintenance_mode=payload.maintenance_mode,
        label_set="label" in fields_set,
        group_set="group_id" in fields_set,
    )
    return DeviceResponse(device=_device_out(device))


@router.delete("/{device_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_device(
    device_id: uuid.UUID,
    scope: TenantScope = Depends(tenant_scope),
    _: Principal = Depends(require_role(*_MANAGE_ROLES)),
) -> Response:
    """Delete a device and revoke its MQTT credentials (Req 5.9)."""
    service = DeviceService(scope)
    await service.delete_device(device_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{device_id}/assign", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def assign_device(
    device_id: uuid.UUID,
    payload: AssignDeviceRequest,
    scope: TenantScope = Depends(tenant_scope),
    _: Principal = Depends(require_role(*_MANAGE_ROLES)),
) -> Response:
    """Assign a device to a Device_User, granting access to it only (Req 5.6)."""
    service = DeviceService(scope)
    await service.assign_device_to_user(device_id, payload.user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{device_id}/apply-template", response_model=DeviceResponse)
async def apply_template(
    device_id: uuid.UUID,
    payload: ApplyTemplateRequest,
    scope: TenantScope = Depends(tenant_scope),
    _: Principal = Depends(require_role(*_MANAGE_ROLES)),
) -> DeviceResponse:
    """Configure a device's Dashboard and Rules from a template (Req 11.4).

    Records the applied template on the device and creates the dashboard,
    widgets, and rules defined by the template (rules are subject to the plan's
    active-rule limit, Req 10.6-10.8).
    """
    service = TemplateService(scope)
    device = await service.apply_template_to_device(device_id, payload.template_id)
    return DeviceResponse(device=_device_out(device))


@router.post("/{device_id}/simulator", response_model=DeviceResponse)
async def start_simulator(
    device_id: uuid.UUID,
    payload: StartSimulatorRequest,
    scope: TenantScope = Depends(tenant_scope),
    _: Principal = Depends(require_role(*_MANAGE_ROLES)),
) -> DeviceResponse:
    """Start/configure the Device_Simulator at a publish interval (Req 13.1-13.3).

    Sets the device's ``sim_interval_sec``; the backend simulator worker
    publishes simulated telemetry via the org's MQTT credentials at this
    interval. An interval of ``0`` configures the simulator without publishing
    (Req 13.3).
    """
    service = DeviceService(scope)
    device = await service.start_simulator(device_id, interval_sec=payload.interval_sec)
    return DeviceResponse(device=_device_out(device))


@router.post(
    "/{device_id}/simulator/stop",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def stop_simulator(
    device_id: uuid.UUID,
    scope: TenantScope = Depends(tenant_scope),
    _: Principal = Depends(require_role(*_MANAGE_ROLES)),
) -> Response:
    """Stop a running Device_Simulator so it ceases publishing (Req 13.4)."""
    service = DeviceService(scope)
    await service.stop_simulator(device_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{device_id}/qr")
async def device_qr(
    device_id: uuid.UUID,
    scope: TenantScope = Depends(tenant_scope),
    _: Principal = Depends(require_role(*_MANAGE_ROLES)),
) -> RawResponse:
    """Return a PNG QR code encoding the device identity (Req 5.2)."""
    service = DeviceService(scope)
    png = await service.generate_qr_png(device_id)
    return RawResponse(content=png, media_type="image/png")
