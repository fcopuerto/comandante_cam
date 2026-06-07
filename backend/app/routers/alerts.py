"""
Alert event and alert rule routes.
"""
import uuid
from datetime import datetime
from math import ceil

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError, NotFoundError, ValidationError
from app.database import get_db
from app.middleware.auth import require_permission
from app.models.alert_event import AlertEvent
from app.models.alert_rule import AlertRule
from app.models.user import User
from app.schemas.alert import (
    AlertAcknowledgeRequest,
    AlertEventResponse,
    AlertFalsePositiveRequest,
    AlertLegalHoldRequest,
    AlertRuleCreate,
    AlertRuleResponse,
    AlertRuleUpdate,
    AlertStatsResponse,
)
from app.schemas.camera import Page
import app.services.alert_service as alert_svc
import app.services.audit_service as audit_svc

router = APIRouter(tags=["alerts"])


def _validate_uuid(value: str, label: str) -> str:
    try:
        uuid.UUID(value)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{label} not found")
    return value


# ── Alert events ───────────────────────────────────────────────────────────────

@router.get("/alerts", response_model=Page[AlertEventResponse])
async def list_alerts(
    camera_id: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    from_dt: datetime | None = Query(default=None),
    to_dt: datetime | None = Query(default=None),
    acknowledged: bool | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_permission("alerts:view")),
) -> Page[AlertEventResponse]:
    if camera_id:
        _validate_uuid(camera_id, "Camera")
    alerts, total = await alert_svc.list_alerts(
        db, camera_id=camera_id, severity=severity,
        from_dt=from_dt, to_dt=to_dt, acknowledged=acknowledged,
        page=page, page_size=page_size,
    )
    return Page(
        items=alerts,
        total=total,
        page=page,
        page_size=page_size,
        pages=ceil(total / page_size) if total else 0,
    )


@router.get("/alerts/stats", response_model=AlertStatsResponse)
async def get_alert_stats(
    hours: int = Query(default=24, ge=1, le=168),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("alerts:view")),
) -> AlertStatsResponse:
    return await alert_svc.get_alert_stats(db, hours, user)


@router.get("/alerts/{alert_id}", response_model=AlertEventResponse)
async def get_alert(
    alert_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_permission("alerts:view")),
) -> AlertEventResponse:
    _validate_uuid(alert_id, "Alert")
    try:
        return await alert_svc.get_alert(db, alert_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.patch("/alerts/{alert_id}/acknowledge", response_model=AlertEventResponse)
async def acknowledge_alert(
    alert_id: str,
    body: AlertAcknowledgeRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("alerts:acknowledge")),
) -> AlertEventResponse:
    _validate_uuid(alert_id, "Alert")
    try:
        return await alert_svc.acknowledge_alert(db, alert_id, user, body.notes)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.patch("/alerts/{alert_id}/false-positive", response_model=AlertEventResponse)
async def mark_false_positive(
    alert_id: str,
    body: AlertFalsePositiveRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("alerts:manage")),
) -> AlertEventResponse:
    _validate_uuid(alert_id, "Alert")
    try:
        return await alert_svc.mark_false_positive(db, alert_id, user, body.notes)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.patch("/alerts/{alert_id}/legal-hold", response_model=AlertEventResponse)
async def set_legal_hold(
    alert_id: str,
    body: AlertLegalHoldRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("alerts:manage")),
) -> AlertEventResponse:
    _validate_uuid(alert_id, "Alert")
    try:
        return await alert_svc.set_legal_hold(db, alert_id, body.hold, user)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/alerts/{alert_id}/clip")
async def get_alert_clip(
    alert_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_permission("alerts:view")),
) -> StreamingResponse:
    import pathlib
    _validate_uuid(alert_id, "Alert")
    result = await db.execute(select(AlertEvent).where(AlertEvent.id == alert_id))
    alert = result.scalar_one_or_none()
    if not alert or not alert.clip_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clip not available")

    clip = pathlib.Path(alert.clip_path)
    if not clip.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clip file not found")

    def _iter():
        with open(clip, "rb") as f:
            while chunk := f.read(65536):
                yield chunk

    return StreamingResponse(
        _iter(),
        media_type="video/mp4",
        headers={
            "Content-Disposition": f'attachment; filename="alert_{alert_id}.mp4"',
            "Content-Length": str(clip.stat().st_size),
        },
    )


@router.get("/alerts/{alert_id}/frame")
async def get_alert_frame(
    alert_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_permission("alerts:view")),
) -> Response:
    import pathlib
    _validate_uuid(alert_id, "Alert")
    result = await db.execute(select(AlertEvent).where(AlertEvent.id == alert_id))
    alert = result.scalar_one_or_none()
    if not alert or not alert.frame_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Frame not available")

    frame = pathlib.Path(alert.frame_path)
    if not frame.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Frame file not found")

    return Response(content=frame.read_bytes(), media_type="image/jpeg")


# ── Alert rules ────────────────────────────────────────────────────────────────

@router.get("/alert-rules", response_model=Page[AlertRuleResponse])
async def list_alert_rules(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_permission("alerts:manage")),
) -> Page[AlertRuleResponse]:
    from sqlalchemy import func
    count_result = await db.execute(select(func.count(AlertRule.id)))
    total = count_result.scalar_one()
    offset = (page - 1) * page_size
    result = await db.execute(
        select(AlertRule).order_by(AlertRule.created_at.desc()).offset(offset).limit(page_size)
    )
    rules = result.scalars().all()
    items = [_rule_response(r) for r in rules]
    return Page(items=items, total=total, page=page, page_size=page_size,
                pages=ceil(total / page_size) if total else 0)


@router.post("/alert-rules", response_model=AlertRuleResponse, status_code=status.HTTP_201_CREATED)
async def create_alert_rule(
    body: AlertRuleCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("alerts:manage")),
) -> AlertRuleResponse:
    if body.camera_id:
        _validate_uuid(body.camera_id, "Camera")
    rule = AlertRule(
        name=body.name,
        camera_id=body.camera_id,
        detection_types=body.detection_types,
        severity=body.severity,
        schedule=body.schedule,
        enabled=body.enabled,
        notification_channels=body.notification_channels,
    )
    db.add(rule)
    await db.flush()
    audit_svc.log(db, "alert_rule_created", user, "alert_rule", rule.id,
                  detail={"name": rule.name})
    return _rule_response(rule)


@router.get("/alert-rules/{rule_id}", response_model=AlertRuleResponse)
async def get_alert_rule(
    rule_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_permission("alerts:manage")),
) -> AlertRuleResponse:
    rule = await _load_rule(db, rule_id)
    return _rule_response(rule)


@router.patch("/alert-rules/{rule_id}", response_model=AlertRuleResponse)
async def update_alert_rule(
    rule_id: str,
    body: AlertRuleUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("alerts:manage")),
) -> AlertRuleResponse:
    rule = await _load_rule(db, rule_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(rule, field, value)
    audit_svc.log(db, "alert_rule_updated", user, "alert_rule", rule_id)
    return _rule_response(rule)


@router.delete("/alert-rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_alert_rule(
    rule_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("alerts:manage")),
) -> None:
    rule = await _load_rule(db, rule_id)
    await db.delete(rule)
    audit_svc.log(db, "alert_rule_deleted", user, "alert_rule", rule_id)


async def _load_rule(db: AsyncSession, rule_id: str) -> AlertRule:
    _validate_uuid(rule_id, "AlertRule")
    result = await db.execute(select(AlertRule).where(AlertRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Alert rule {rule_id} not found")
    return rule


def _rule_response(rule: AlertRule) -> AlertRuleResponse:
    return AlertRuleResponse(
        id=rule.id,
        name=rule.name,
        camera_id=rule.camera_id,
        detection_types=list(rule.detection_types or []),
        severity=rule.severity,
        schedule=rule.schedule,
        enabled=rule.enabled,
        notification_channels=[str(c) for c in (rule.notification_channels or [])],
        created_at=rule.created_at,
    )
