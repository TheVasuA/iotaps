"""Support chat service (Task 19.4, Req 21).

Implements the support-chat surface between a Device_User and the
Project_Center that owns the Device_User's assigned device:

- **Device_User sends a message (Req 21.1).** :meth:`SupportService.send_user_message`
  records a ``support_chats`` row addressed to the Project_Center to which the
  referenced device is assigned. Because a Device_User is provisioned inside the
  owning Project_Center's organization (see
  ``DeviceService.assign_device_to_user``), the device's ``org_id`` *is* that
  Project_Center org, so the message is delivered to it via the tenant key.
- **Device identity in every conversation (Req 21.2).** Each row carries the
  ``device_id`` it concerns, so the Project_Center always sees which device a
  conversation is about.
- **Project_Center reply routed to the originating user (Req 21.3).**
  :meth:`SupportService.reply` derives the originating ``device_user_id`` (and
  the device) from the message being replied to and stamps the reply with that
  user, so it surfaces in exactly that Device_User's conversation.

The service is transport-agnostic: it takes a :class:`TenantScope` (request
principal + tenant-bound session) and raw values, returns ORM objects, and lets
the HTTP router map them to schemas. Tenant isolation (Req 3) is enforced by the
scope: every ``support_chats`` row is keyed by the Project_Center ``org_id``, so
a caller can only ever read/write conversations inside their own organization.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AuthorizationError, NotFoundError, ValidationError
from app.core.security.tenant import TenantScope
from app.models.device import Device, DeviceUserAssignment
from app.models.ops import SupportChat

# Stable sender-role identifiers stored on each message so the conversation can
# be rendered as a two-party thread (Req 21.1, 21.3).
SENDER_DEVICE_USER = "device_user"
SENDER_PROJECT_CENTER = "project_center"


class SupportService:
    """Tenant-scoped support-chat operations (send, reply, list)."""

    def __init__(self, scope: TenantScope) -> None:
        self._scope = scope
        self._session: AsyncSession = scope.session

    @property
    def _caller_uuid(self) -> uuid.UUID:
        return uuid.UUID(str(self._scope.principal.user_id))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _clean_message(message: str) -> str:
        text = (message or "").strip()
        if not text:
            raise ValidationError(
                "Message must not be empty", error_code="empty_message"
            )
        return text

    async def _assert_user_assigned(self, device_id: uuid.UUID) -> None:
        """Ensure the calling Device_User is assigned to ``device_id`` (Req 2.4).

        Super_Admin bypasses the assignment check (acts across orgs, Req 2.5).
        """
        if self._scope.bypass:
            return
        result = await self._session.execute(
            select(DeviceUserAssignment.id).where(
                DeviceUserAssignment.device_id == device_id,
                DeviceUserAssignment.user_id == self._caller_uuid,
            )
        )
        if result.first() is None:
            raise AuthorizationError(
                "You do not have access to this device",
                error_code="authorization_error",
            )

    # ------------------------------------------------------------------
    # Device_User -> Project_Center (Req 21.1, 21.2)
    # ------------------------------------------------------------------
    async def send_user_message(
        self, *, device_id: uuid.UUID, message: str
    ) -> SupportChat:
        """Record a Device_User's support message for the device's Project_Center.

        The device must belong to the caller's organization (tenant check,
        Req 3.3) and be assigned to the calling Device_User (Req 2.4). The
        message is stamped with the device identity (Req 21.2) and delivered to
        the Project_Center via the device's ``org_id`` (Req 21.1).
        """
        text = self._clean_message(message)
        # Tenant-scoped fetch: raises 403 if the device is missing or in another
        # organization (Req 3.3). For a Device_User this is the Project_Center org.
        device = await self._scope.get(Device, device_id)
        await self._assert_user_assigned(device.id)

        chat = SupportChat(
            org_id=device.org_id,
            device_id=device.id,
            device_user_id=self._caller_uuid,
            project_center_id=device.org_id,
            message=text,
            sender_role=SENDER_DEVICE_USER,
        )
        self._session.add(chat)
        await self._session.commit()
        await self._session.refresh(chat)
        return chat

    # ------------------------------------------------------------------
    # Project_Center -> originating Device_User (Req 21.3)
    # ------------------------------------------------------------------
    async def reply(self, *, message_id: uuid.UUID, message: str) -> SupportChat:
        """Record a Project_Center reply routed to the originating Device_User.

        The message being replied to identifies both the device and the
        originating ``device_user_id``; the reply is stamped with that same user
        so it is delivered into exactly that Device_User's conversation
        (Req 21.3). The tenant scope guarantees the Project_Center can only reply
        to messages within its own organization (Req 3.3).
        """
        text = self._clean_message(message)
        # Tenant-scoped fetch enforces the message belongs to the caller's org.
        original = await self._scope.get(SupportChat, message_id)
        if original.device_user_id is None:
            raise NotFoundError(
                "Originating user not found for this conversation"
            )

        reply = SupportChat(
            org_id=original.org_id,
            device_id=original.device_id,
            device_user_id=original.device_user_id,
            project_center_id=original.org_id,
            message=text,
            sender_role=SENDER_PROJECT_CENTER,
        )
        self._session.add(reply)
        await self._session.commit()
        await self._session.refresh(reply)
        return reply

    # ------------------------------------------------------------------
    # Read conversations
    # ------------------------------------------------------------------
    async def list_messages(
        self, *, device_id: uuid.UUID | None = None
    ) -> list[SupportChat]:
        """List support messages visible to the caller, oldest first.

        - A Device_User sees only their own conversations (messages stamped with
          their ``device_user_id``), so one customer cannot read another's
          support thread (Req 21.3 routing/privacy).
        - A Project_Center sees every support message in its organization
          (tenant filter), i.e. messages from all the Device_Users it serves
          (Req 21.1).
        - Super_Admin sees across organizations (Req 2.5).
        """
        stmt = self._scope.select(SupportChat)
        if self._scope.principal.is_device_user:
            stmt = stmt.where(SupportChat.device_user_id == self._caller_uuid)
        if device_id is not None:
            stmt = stmt.where(SupportChat.device_id == device_id)
        stmt = stmt.order_by(SupportChat.created_at.asc())
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
