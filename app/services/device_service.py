"""Device provisioning and management service (Task 4.1, Req 5).

Encapsulates the business logic behind the Devices API (design.md "Devices"):

    - provision (create) a device with unique MQTT credentials + node assignment
    - list / get / rename + reconfigure (label, group, maintenance_mode) / delete
    - create device groups
    - assign a device to a Device_User (Req 5.6)
    - generate a QR code encoding the device identity (Req 5.2)

The service is deliberately transport-agnostic: it takes a :class:`TenantScope`
(which carries the request principal + DB session and enforces tenant
isolation) and raw values, and returns ORM objects / bytes. The HTTP router
(``app.api.v1.devices``) maps these to request/response schemas.

Key invariants:
  - Every device is created under the caller's ``org_id`` (Req 5.1) and gets a
    unique MQTT credential whose ACL is ``iotaps/{org_id}/#`` (Req 3.5, 5.1).
  - Deleting a device revokes (does not hard-delete) its MQTT credentials by
    setting ``revoked = true`` before the device row is removed (Req 5.9), so
    the Mosquitto auth backend immediately denies the old credentials.
  - Provisioning, assignment, rename, command, and config changes each write an
    ``activity_logs`` entry (Req 5.8).
  - Provisioning binds the device to an MQTT node with spare capacity via
    ``assign_node`` (Req 24.4).
"""

from __future__ import annotations

import secrets
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError, ValidationError
from app.core.mqtt_topics import org_acl_pattern
from app.core.security import password as password_service
from app.core.security.tenant import TenantScope
from app.models.device import (
    Device,
    DeviceGroup,
    DeviceUserAssignment,
    MqttCredential,
)
from app.models.ops import ActivityLog
from app.models.organization import Organization
from app.models.user import User
from app.services.node_assignment import assign_node
from app.services.plan_limits import PlanLimitError, limits_for_plan

# Activity log action identifiers (Req 5.8). Centralised so the worker/admin
# views and tests refer to the same stable strings.
ACTION_PROVISION = "device.provision"
ACTION_ASSIGN = "device.assign"
ACTION_RENAME = "device.rename"
ACTION_COMMAND = "device.command"
ACTION_CONFIG_CHANGE = "device.config_change"
ACTION_DELETE = "device.delete"


def _new_mqtt_username(device_uid: str) -> str:
    """Build a unique MQTT username for a device.

    Combines the device's stable uid with random entropy so usernames are
    unique even if a uid is reused after deletion, and never collide across
    devices (``mqtt_credentials.username`` is UNIQUE).
    """
    return f"dev-{device_uid}-{secrets.token_hex(4)}"


def _generate_mqtt_secret() -> str:
    """Generate a high-entropy MQTT password (returned once to the caller)."""
    return secrets.token_urlsafe(24)


class DeviceService:
    """Tenant-scoped operations over devices, groups, credentials, assignments."""

    def __init__(self, scope: TenantScope) -> None:
        self._scope = scope
        self._session: AsyncSession = scope.session

    @property
    def _org_uuid(self) -> uuid.UUID:
        return uuid.UUID(str(self._scope.org_id))

    # ------------------------------------------------------------------
    # Plan limit helpers (Req 15.1, 15.2, 15.7)
    # ------------------------------------------------------------------
    async def _org_plan(self) -> str | None:
        """Fetch the caller's organization plan value (may be ambiguous)."""
        org = await self._session.get(Organization, self._org_uuid)
        return org.plan if org is not None else None

    async def _count_devices(self) -> int:
        """Count provisioned devices in the caller's org."""
        result = await self._session.execute(
            select(func.count())
            .select_from(Device)
            .where(Device.org_id == self._org_uuid)
        )
        return int(result.scalar_one())

    async def _enforce_device_limit(self) -> None:
        """Raise :class:`PlanLimitError` if provisioning exceeds the plan cap.

        Pro orgs (``max_devices`` is ``None``) are always permitted. For
        Free/ambiguous orgs the current device count must be below the cap before
        one more device is created (Req 15.1, 15.7).
        """
        limits = limits_for_plan(await self._org_plan())
        if limits.max_devices is None:
            return
        if await self._count_devices() >= limits.max_devices:
            raise PlanLimitError(
                f"Your plan allows at most {limits.max_devices} devices. "
                "Delete a device or upgrade to Pro.",
            )

    def _log(
        self,
        action: str,
        *,
        device_id: uuid.UUID | None = None,
        detail: dict | None = None,
    ) -> None:
        """Queue an activity-log entry on the session (Req 5.8).

        Uses the principal's org_id; Super_Admin acting cross-org logs under the
        device's org via ``detail`` rather than the principal org when needed.
        """
        try:
            user_uuid = uuid.UUID(str(self._scope.principal.user_id))
        except (ValueError, TypeError):
            user_uuid = None
        self._session.add(
            ActivityLog(
                org_id=self._org_uuid,
                user_id=user_uuid,
                device_id=device_id,
                action=action,
                detail=detail,
            )
        )

    # ------------------------------------------------------------------
    # Provisioning (Req 5.1, 5.2, 5.8, 24.4)
    # ------------------------------------------------------------------
    async def provision_device(
        self,
        *,
        label: str | None = None,
        group_id: uuid.UUID | None = None,
        template_id: uuid.UUID | None = None,
        device_uid: str | None = None,
    ) -> tuple[Device, MqttCredential, str]:
        """Create a device, its unique MQTT credentials, and bind it to a node.

        Returns ``(device, credential, plaintext_secret)``. The plaintext MQTT
        secret is returned once here (only its hash is stored) so the caller can
        surface it to the operator/device exactly once (Req 5.1).
        """
        if group_id is not None:
            # Ensure the referenced group belongs to the tenant (Req 3.3).
            await self._scope.get(DeviceGroup, group_id)

        # Enforce the per-plan device cap before creating anything (Req 15.1).
        await self._enforce_device_limit()

        device_uid = device_uid or uuid.uuid4().hex

        device = Device(
            org_id=self._org_uuid,
            device_uid=device_uid,
            label=label,
            group_id=group_id,
            template_id=template_id,
            status="offline",
        )
        self._session.add(device)
        await self._session.flush()  # assign device.id

        # Bind to an MQTT node with spare capacity (Req 24.4). If the fleet is
        # full this raises NoCapacityError (503) and the whole provision aborts.
        node = await assign_node(self._session)
        device.node_id = node.id

        # Unique per-device MQTT credentials, ACL scoped to the org (Req 3.5, 5.1).
        plaintext_secret = _generate_mqtt_secret()
        credential = MqttCredential(
            org_id=self._org_uuid,
            device_id=device.id,
            username=_new_mqtt_username(device_uid),
            password_hash=password_service.hash_password(plaintext_secret),
            acl_pattern=org_acl_pattern(str(self._scope.org_id)),
            revoked=False,
        )
        self._session.add(credential)

        self._log(
            ACTION_PROVISION,
            device_id=device.id,
            detail={"device_uid": device_uid, "node_id": str(node.id)},
        )

        await self._session.commit()
        await self._session.refresh(device)
        await self._session.refresh(credential)
        return device, credential, plaintext_secret

    # ------------------------------------------------------------------
    # Read (Req 5.x list/get) - tenant filtered
    # ------------------------------------------------------------------
    async def list_devices(
        self,
        *,
        group_id: uuid.UUID | None = None,
        status: str | None = None,
    ) -> list[Device]:
        """List devices in the caller's org, optionally filtered."""
        stmt = self._scope.select(Device)
        if group_id is not None:
            stmt = stmt.where(Device.group_id == group_id)
        if status is not None:
            stmt = stmt.where(Device.status == status)
        stmt = stmt.order_by(Device.created_at.desc())
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_device(self, device_id: uuid.UUID) -> Device:
        """Fetch a device by id, enforcing tenant ownership (Req 3.3)."""
        return await self._scope.get(Device, device_id)

    # ------------------------------------------------------------------
    # Update: rename / group / maintenance_mode (Req 5.3, 5.4, 5.5, 5.7, 5.8)
    # ------------------------------------------------------------------
    async def update_device(
        self,
        device_id: uuid.UUID,
        *,
        label: str | None = None,
        group_id: uuid.UUID | None = None,
        maintenance_mode: bool | None = None,
        label_set: bool = False,
        group_set: bool = False,
    ) -> Device:
        """Apply a partial update to a device.

        ``label_set`` / ``group_set`` distinguish "field omitted" from
        "explicitly set to null" for the nullable label/group columns. A rename
        (label change) and any other config change are logged separately so the
        activity feed reflects the precise nature of the change (Req 5.8).
        """
        device = await self._scope.get(Device, device_id)

        config_changes: dict[str, object] = {}

        if label_set and label != device.label:
            old_label = device.label
            device.label = label  # rename / custom label (Req 5.3, 5.4)
            self._log(
                ACTION_RENAME,
                device_id=device.id,
                detail={"old_label": old_label, "new_label": label},
            )

        if group_set and group_id != device.group_id:
            if group_id is not None:
                await self._scope.get(DeviceGroup, group_id)  # tenant check
            device.group_id = group_id  # group association (Req 5.5)
            config_changes["group_id"] = str(group_id) if group_id else None

        if maintenance_mode is not None and maintenance_mode != device.maintenance_mode:
            device.maintenance_mode = maintenance_mode  # (Req 5.7)
            config_changes["maintenance_mode"] = maintenance_mode

        if config_changes:
            self._log(
                ACTION_CONFIG_CHANGE, device_id=device.id, detail=config_changes
            )

        await self._session.commit()
        await self._session.refresh(device)
        return device

    # ------------------------------------------------------------------
    # Delete: remove device + revoke MQTT credentials (Req 5.9)
    # ------------------------------------------------------------------
    async def delete_device(self, device_id: uuid.UUID) -> None:
        """Delete a device and revoke its MQTT credentials (Req 5.9).

        Credentials are revoked (``revoked = true``) before the device row is
        removed so the Mosquitto auth backend denies them immediately, even if
        the cascade delete of the credential row is deferred or audited.
        """
        device = await self._scope.get(Device, device_id)

        # Revoke all credentials for this device (Req 5.9).
        creds = await self._session.execute(
            select(MqttCredential).where(MqttCredential.device_id == device.id)
        )
        for cred in creds.scalars():
            cred.revoked = True

        self._log(
            ACTION_DELETE,
            device_id=device.id,
            detail={"device_uid": device.device_uid},
        )
        # Flush the revocation + log before deleting the device so they persist
        # and the activity log keeps a (now historical) device reference.
        await self._session.flush()

        await self._session.delete(device)
        await self._session.commit()

    # ------------------------------------------------------------------
    # Groups (Req 5.5)
    # ------------------------------------------------------------------
    async def create_group(self, name: str) -> DeviceGroup:
        """Create a device group in the caller's org."""
        if not name or not name.strip():
            raise ValidationError("Group name is required", error_code="invalid_group_name")
        group = DeviceGroup(org_id=self._org_uuid, name=name.strip())
        self._session.add(group)
        await self._session.commit()
        await self._session.refresh(group)
        return group

    # ------------------------------------------------------------------
    # Assignment to a Device_User (Req 5.6, 5.8)
    # ------------------------------------------------------------------
    async def assign_device_to_user(
        self, device_id: uuid.UUID, user_id: uuid.UUID
    ) -> DeviceUserAssignment:
        """Grant a Device_User access to a single device (Req 5.6).

        Validates that both the device and the target user belong to the
        caller's organization, then records the assignment (idempotent on the
        unique (device_id, user_id) pair) and writes an activity log (Req 5.8).
        """
        device = await self._scope.get(Device, device_id)

        # The target user must exist in the same org (tenant boundary, Req 3.3).
        user = await self._session.get(User, user_id)
        if user is None or (
            not self._scope.bypass and str(user.org_id) != str(self._scope.org_id)
        ):
            raise NotFoundError("User not found in your organization")

        existing = await self._session.execute(
            select(DeviceUserAssignment).where(
                DeviceUserAssignment.device_id == device.id,
                DeviceUserAssignment.user_id == user_id,
            )
        )
        assignment = existing.scalar_one_or_none()
        if assignment is None:
            assignment = DeviceUserAssignment(
                org_id=device.org_id,
                device_id=device.id,
                user_id=user_id,
            )
            self._session.add(assignment)
            self._log(
                ACTION_ASSIGN,
                device_id=device.id,
                detail={"user_id": str(user_id)},
            )
            await self._session.commit()
            await self._session.refresh(assignment)
        return assignment

    # ------------------------------------------------------------------
    # Device Simulator start/stop (Req 13.1-13.4)
    # ------------------------------------------------------------------
    async def start_simulator(
        self, device_id: uuid.UUID, *, interval_sec: int
    ) -> Device:
        """Enable the Device_Simulator and set its publish interval (Req 13.1, 13.2).

        Marks the device as a simulator and records ``sim_interval_sec``. A
        positive interval makes the backend simulator worker publish simulated
        telemetry at that cadence (Req 13.2); an interval of ``0`` is accepted
        but suppresses publishing (Req 13.3). The configuration change is
        recorded in the activity log (Req 5.8).
        """
        if interval_sec < 0:
            raise ValidationError(
                "Simulator interval must be zero or positive",
                error_code="invalid_sim_interval",
            )
        device = await self._scope.get(Device, device_id)
        device.is_simulator = True
        device.sim_interval_sec = interval_sec
        self._log(
            ACTION_CONFIG_CHANGE,
            device_id=device.id,
            detail={"is_simulator": True, "sim_interval_sec": interval_sec},
        )
        await self._session.commit()
        await self._session.refresh(device)
        return device

    async def stop_simulator(self, device_id: uuid.UUID) -> Device:
        """Stop a running Device_Simulator so it ceases publishing (Req 13.4).

        Sets ``sim_interval_sec`` to ``0`` which the simulator worker treats as
        "do not publish" (Req 13.3), so the device stops emitting simulated
        telemetry on the next worker tick. The device remains flagged as a
        simulator so it can be restarted. The change is logged (Req 5.8).
        """
        device = await self._scope.get(Device, device_id)
        device.sim_interval_sec = 0
        self._log(
            ACTION_CONFIG_CHANGE,
            device_id=device.id,
            detail={"simulator_stopped": True, "sim_interval_sec": 0},
        )
        await self._session.commit()
        await self._session.refresh(device)
        return device

    # ------------------------------------------------------------------
    # QR code encoding device identity (Req 5.2)
    # ------------------------------------------------------------------
    async def generate_qr_png(self, device_id: uuid.UUID) -> bytes:
        """Return a PNG QR code encoding the device identity (Req 5.2)."""
        device = await self._scope.get(Device, device_id)
        payload = build_qr_payload(device)
        return render_qr_png(payload)


def device_display_name(device: Device) -> str:
    """Return the name to display for a device (Req 5.4).

    A custom label, when set, is displayed in place of the device's default
    identifier (its hardware ``device_uid``). When no label has been assigned
    the default identifier is shown so a device is never anonymous. Kept pure
    so the precedence rule can be unit-tested without an HTTP request.
    """
    if device.label is not None and device.label.strip():
        return device.label
    return device.device_uid or str(device.id)


def build_qr_payload(device: Device) -> str:
    """Build the string encoded in a device's QR code (Req 5.2).

    Encodes the stable device identity (org + device id + hardware uid) so a
    scanning app can resolve the exact device. Kept pure for unit testing.
    """
    return (
        f"iotaps:device?org={device.org_id}"
        f"&id={device.id}"
        f"&uid={device.device_uid or ''}"
    )


def render_qr_png(payload: str) -> bytes:
    """Render ``payload`` into PNG bytes using the ``qrcode`` library.

    Isolated so the QR encoding can be unit-tested without an HTTP request and
    so the (optional) dependency import is localised.
    """
    import qrcode

    img = qrcode.make(payload)
    import io

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()
