"""
Recordings routes — timeline, calendar, and segment retrieval.
"""
import uuid
from datetime import date, datetime, timezone
from math import ceil

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_user, require_permission
from app.models.user import User
from app.schemas.camera import Page
from app.schemas.recording import CalendarResponse, SegmentResponse, TimelineResponse
import app.services.recording_service as rec_svc

router = APIRouter(prefix="/recordings", tags=["recordings"])


def _validate_camera_id(camera_id: str) -> str:
    try:
        uuid.UUID(camera_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Camera {camera_id} not found")
    return camera_id


@router.get("/timeline", response_model=TimelineResponse)
async def get_timeline(
    camera_id: str = Query(...),
    date: date = Query(...),
    tz: str = Query(default="UTC"),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_permission("recordings:view")),
) -> TimelineResponse:
    _validate_camera_id(camera_id)
    return await rec_svc.get_timeline(db, camera_id, date, tz)


@router.get("/calendar", response_model=CalendarResponse)
async def get_calendar(
    camera_id: str = Query(...),
    year: int = Query(..., ge=2000, le=2100),
    month: int = Query(..., ge=1, le=12),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_permission("recordings:view")),
) -> CalendarResponse:
    _validate_camera_id(camera_id)
    return await rec_svc.get_calendar(db, camera_id, year, month)


@router.get("/segments", response_model=Page[SegmentResponse])
async def list_segments(
    camera_id: str | None = Query(default=None),
    from_dt: datetime | None = Query(default=None),
    to_dt: datetime | None = Query(default=None),
    segment_type: str | None = Query(default=None),
    has_alert: bool | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_permission("recordings:view")),
) -> Page[SegmentResponse]:
    if camera_id:
        _validate_camera_id(camera_id)
    segments, total = await rec_svc.get_segments(
        db, camera_id=camera_id, from_dt=from_dt, to_dt=to_dt,
        segment_type=segment_type, has_alert=has_alert,
        page=page, page_size=page_size,
    )
    from app.services.recording_service import _segment_response
    return Page(
        items=[_segment_response(s) for s in segments],
        total=total,
        page=page,
        page_size=page_size,
        pages=ceil(total / page_size) if total else 0,
    )


@router.get("/segments/{segment_id}", response_model=SegmentResponse)
async def get_segment(
    segment_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_permission("recordings:view")),
) -> SegmentResponse:
    from sqlalchemy import select
    from app.models.recording_segment import RecordingSegment
    from app.services.recording_service import _segment_response

    try:
        uuid.UUID(segment_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Segment {segment_id} not found")

    result = await db.execute(select(RecordingSegment).where(RecordingSegment.id == segment_id))
    seg = result.scalar_one_or_none()
    if not seg:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Segment {segment_id} not found")
    return _segment_response(seg)


@router.delete("/segments/{segment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_segment(
    segment_id: str,
    db: AsyncSession = Depends(get_db),
    acting_user: User = Depends(require_permission("recordings:delete")),
) -> None:
    import pathlib
    from sqlalchemy import select
    from app.models.recording_segment import RecordingSegment
    import app.services.audit_service as audit_svc

    try:
        uuid.UUID(segment_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Segment {segment_id} not found")

    result = await db.execute(select(RecordingSegment).where(RecordingSegment.id == segment_id))
    seg = result.scalar_one_or_none()
    if not seg:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Segment {segment_id} not found")
    if seg.is_on_legal_hold:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Segment is on legal hold and cannot be deleted")

    # Delete files
    for path_str in [seg.file_path, seg.thumbnail_path]:
        if path_str:
            p = pathlib.Path(path_str)
            if p.exists():
                p.unlink(missing_ok=True)

    await db.delete(seg)
    audit_svc.log(db, "segment_deleted", acting_user, "recording_segment", segment_id)


@router.get("/segments/{segment_id}/thumbnail")
async def get_segment_thumbnail(
    segment_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_permission("recordings:view")),
) -> Response:
    import pathlib
    from sqlalchemy import select
    from app.models.recording_segment import RecordingSegment

    try:
        uuid.UUID(segment_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Segment not found")

    result = await db.execute(select(RecordingSegment).where(RecordingSegment.id == segment_id))
    seg = result.scalar_one_or_none()
    if not seg or not seg.thumbnail_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thumbnail not available")

    thumb_path = pathlib.Path(seg.thumbnail_path)
    if not thumb_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thumbnail file not found")

    return Response(content=thumb_path.read_bytes(), media_type="image/jpeg")
