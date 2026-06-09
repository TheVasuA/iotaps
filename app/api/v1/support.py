"""Support chat API endpoints (Task 19.4, Req 21).

Implements the support-chat surface between a Device_User and the
Project_Center that owns the Device_User's assigned device:

    GET    /support/messages            ?device_id -> [message]
    POST   /support/messages            {device_id, message} -> {message}
                                        (Device_User -> assigned Project_Center)
    POST   /support/messages/{id}/reply {message} -> {message}
                                        (Project_Center -> originating Device_User)

A Device_User sends a message about one of their assigned devices; it is
delivered to the Project_Center to which the device is assigned, carrying the
device identity (Req 21.1, 21.2). A Project_Center replies to a message and the
reply is routed back to the originating Device_User (Req 21.3). All queries go
through :class:`TenantScope` so they are auto-filtered to the caller's
organization (Req 3.2, 3.3).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.core.security.deps import require_role, tenant_scope
from app.core.security.principal import (
    ROLE_DEVICE_USER,
    ROLE_PROJECT_CENTER,
    ROLE_SUPER_ADMIN,
    Principal,
)
from app.core.security.tenant import TenantScope
from app.models.ops import SupportChat
from app.services.support_service import SupportService

router = APIRouter(prefix="/support", tags=["support"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class SupportMessageOut(BaseModel):
    id: str
    org_id: str
    device_id: str | None
    device_user_id: str | None
    project_center_id: str | None
    message: str
    sender_role: str | None
    created_at: str | None


class SendMessageRequest(BaseModel):
    device_id: uuid.UUID
    message: str = Field(min_length=1, max_length=4000)

    model_config = {"extra": "forbid"}


class ReplyMessageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)

    model_config = {"extra": "forbid"}


class SupportMessageResponse(BaseModel):
    message: SupportMessageOut


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------
def _message_out(chat: SupportChat) -> SupportMessageOut:
    return SupportMessageOut(
        id=str(chat.id),
        org_id=str(chat.org_id),
        device_id=str(chat.device_id) if chat.device_id else None,
        device_user_id=str(chat.device_user_id) if chat.device_user_id else None,
        project_center_id=(
            str(chat.project_center_id) if chat.project_center_id else None
        ),
        message=chat.message,
        sender_role=chat.sender_role,
        created_at=chat.created_at.isoformat() if chat.created_at else None,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.get("/messages", response_model=list[SupportMessageOut])
async def list_messages(
    device_id: uuid.UUID | None = Query(default=None),
    scope: TenantScope = Depends(tenant_scope),
    _: Principal = Depends(
        require_role(ROLE_DEVICE_USER, ROLE_PROJECT_CENTER, ROLE_SUPER_ADMIN)
    ),
) -> list[SupportMessageOut]:
    """List support messages visible to the caller (Req 21.1, 21.3)."""
    service = SupportService(scope)
    messages = await service.list_messages(device_id=device_id)
    return [_message_out(m) for m in messages]


@router.post("/messages", response_model=SupportMessageResponse, status_code=201)
async def send_message(
    payload: SendMessageRequest,
    scope: TenantScope = Depends(tenant_scope),
    _: Principal = Depends(require_role(ROLE_DEVICE_USER)),
) -> SupportMessageResponse:
    """Send a Device_User support message to the device's Project_Center (Req 21.1, 21.2)."""
    service = SupportService(scope)
    chat = await service.send_user_message(
        device_id=payload.device_id, message=payload.message
    )
    return SupportMessageResponse(message=_message_out(chat))


@router.post(
    "/messages/{message_id}/reply",
    response_model=SupportMessageResponse,
    status_code=201,
)
async def reply_message(
    message_id: uuid.UUID,
    payload: ReplyMessageRequest,
    scope: TenantScope = Depends(tenant_scope),
    _: Principal = Depends(require_role(ROLE_PROJECT_CENTER)),
) -> SupportMessageResponse:
    """Reply to a support message; routed to the originating Device_User (Req 21.3)."""
    service = SupportService(scope)
    chat = await service.reply(message_id=message_id, message=payload.message)
    return SupportMessageResponse(message=_message_out(chat))
