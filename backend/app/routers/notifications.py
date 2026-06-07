"""
Notification channel CRUD routes.
"""
import uuid
from math import ceil

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import require_permission
from app.models.notification_channel import NotificationChannel
from app.models.user import User
from app.schemas.alert import (
    NotificationChannelCreate,
    NotificationChannelResponse,
    NotificationChannelUpdate,
)
from app.schemas.camera import Page
import app.services.audit_service as audit_svc

router = APIRouter(prefix="/notifications", tags=["notifications"])


def _validate_uuid(value: str, label: str) -> str:
    try:
        uuid.UUID(value)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{label} not found")
    return value


def _channel_response(ch: NotificationChannel) -> NotificationChannelResponse:
    return NotificationChannelResponse(
        id=ch.id,
        name=ch.name,
        channel_type=ch.channel_type,
        enabled=ch.enabled,
        created_at=ch.created_at,
    )


@router.get("/channels", response_model=Page[NotificationChannelResponse])
async def list_channels(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_permission("notifications:manage")),
) -> Page[NotificationChannelResponse]:
    count_result = await db.execute(select(func.count(NotificationChannel.id)))
    total = count_result.scalar_one()
    offset = (page - 1) * page_size
    result = await db.execute(
        select(NotificationChannel)
        .order_by(NotificationChannel.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    channels = result.scalars().all()
    return Page(
        items=[_channel_response(c) for c in channels],
        total=total,
        page=page,
        page_size=page_size,
        pages=ceil(total / page_size) if total else 0,
    )


@router.post("/channels", response_model=NotificationChannelResponse, status_code=status.HTTP_201_CREATED)
async def create_channel(
    body: NotificationChannelCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("notifications:manage")),
) -> NotificationChannelResponse:
    ch = NotificationChannel(
        name=body.name,
        channel_type=body.channel_type.value,
        config=body.config,
        enabled=body.enabled,
    )
    db.add(ch)
    await db.flush()
    audit_svc.log(db, "notification_channel_created", user, "notification_channel", ch.id,
                  detail={"name": ch.name, "type": ch.channel_type})
    return _channel_response(ch)


@router.patch("/channels/{channel_id}", response_model=NotificationChannelResponse)
async def update_channel(
    channel_id: str,
    body: NotificationChannelUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("notifications:manage")),
) -> NotificationChannelResponse:
    ch = await _load_channel(db, channel_id)
    update_data = body.model_dump(exclude_unset=True)
    if "channel_type" in update_data and update_data["channel_type"] is not None:
        update_data["channel_type"] = update_data["channel_type"].value
    for field, value in update_data.items():
        setattr(ch, field, value)
    audit_svc.log(db, "notification_channel_updated", user, "notification_channel", channel_id)
    return _channel_response(ch)


@router.delete("/channels/{channel_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_channel(
    channel_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("notifications:manage")),
) -> None:
    ch = await _load_channel(db, channel_id)
    await db.delete(ch)
    audit_svc.log(db, "notification_channel_deleted", user, "notification_channel", channel_id)


@router.post("/channels/{channel_id}/test", status_code=status.HTTP_200_OK)
async def test_channel(
    channel_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("notifications:manage")),
) -> dict:
    import asyncio
    from app.models.alert_event import AlertEvent
    from app.models.camera import Camera
    from app.core.constants import Severity
    from app.services.notification_service import send_alert_notifications

    ch = await _load_channel(db, channel_id)

    # Build a synthetic alert and camera for the test send
    class _FakeAlert:
        id = "test-alert-000"
        camera_id = "test-camera-000"
        alert_rule_id = None
        triggered_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
        detection_type = "test"
        zone_name = "Test Zone"
        confidence = 0.99
        severity = Severity.low
        rule_triggered = "test"
        frame_path = None
        bbox = None
        track_id = None

    class _FakeCamera:
        id = "test-camera-000"
        name = "Test Camera"

    try:
        await asyncio.to_thread(
            send_alert_notifications, _FakeAlert(), _FakeCamera(), [ch]
        )
        return {"status": "sent"}
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Test notification failed: {exc}",
        ) from exc


async def _load_channel(db: AsyncSession, channel_id: str) -> NotificationChannel:
    _validate_uuid(channel_id, "NotificationChannel")
    result = await db.execute(
        select(NotificationChannel).where(NotificationChannel.id == channel_id)
    )
    ch = result.scalar_one_or_none()
    if not ch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Notification channel {channel_id} not found")
    return ch
