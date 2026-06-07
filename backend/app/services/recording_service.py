from datetime import date, datetime, timedelta, timezone

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert_event import AlertEvent
from app.models.recording_segment import RecordingSegment
from app.schemas.recording import (
    CalendarDay,
    CalendarResponse,
    SegmentResponse,
    TimelineGap,
    TimelineResponse,
    TimelineSegment,
)


def _segment_response(seg: RecordingSegment) -> SegmentResponse:
    return SegmentResponse(
        id=seg.id,
        camera_id=seg.camera_id,
        started_at=seg.started_at,
        ended_at=seg.ended_at,
        duration_seconds=seg.duration_seconds,
        file_path=seg.file_path,
        file_name=seg.file_name,
        file_size_bytes=seg.file_size_bytes,
        segment_type=seg.segment_type,
        has_motion=seg.has_motion,
        has_alert=seg.has_alert,
        is_corrupt=seg.is_corrupt,
        is_on_legal_hold=seg.is_on_legal_hold,
        thumbnail_path=seg.thumbnail_path,
        width=seg.width,
        height=seg.height,
        fps=seg.fps,
        codec=seg.codec,
        created_at=seg.created_at,
    )


async def get_timeline(
    db: AsyncSession,
    camera_id: str,
    target_date: date,
    tz: str = "UTC",
) -> TimelineResponse:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
    try:
        tzinfo = ZoneInfo(tz)
    except (ZoneInfoNotFoundError, Exception):
        tzinfo = timezone.utc

    # Convert local date to UTC range
    day_start_local = datetime(target_date.year, target_date.month, target_date.day, tzinfo=tzinfo)
    day_end_local = day_start_local + timedelta(days=1)
    day_start_utc = day_start_local.astimezone(timezone.utc)
    day_end_utc = day_end_local.astimezone(timezone.utc)

    result = await db.execute(
        select(RecordingSegment)
        .where(
            RecordingSegment.camera_id == camera_id,
            RecordingSegment.started_at < day_end_utc,
            and_(
                RecordingSegment.ended_at.isnot(None),
                RecordingSegment.ended_at > day_start_utc,
            ),
        )
        .order_by(RecordingSegment.started_at)
    )
    segments = list(result.scalars().all())

    timeline_segs = [_make_timeline_segment(s) for s in segments]
    gaps = _find_gaps(timeline_segs, day_start_utc, day_end_utc)
    covered_seconds = sum(
        (min(s.ended_at or day_end_utc, day_end_utc) - max(s.started_at, day_start_utc)).total_seconds()
        for s in segments
        if s.ended_at
    )
    coverage_pct = min(100.0, round(covered_seconds / 86400 * 100, 1))

    return TimelineResponse(
        camera_id=camera_id,
        date=target_date,
        segments=timeline_segs,
        gaps=gaps,
        coverage_pct=coverage_pct,
    )


def _make_timeline_segment(seg: RecordingSegment) -> TimelineSegment:
    return TimelineSegment(
        segment_id=seg.id,
        started_at=seg.started_at,
        ended_at=seg.ended_at,
        duration_seconds=seg.duration_seconds,
        segment_type=seg.segment_type,
        has_alert=seg.has_alert,
        has_motion=seg.has_motion,
        file_size_bytes=seg.file_size_bytes,
        thumbnail_path=seg.thumbnail_path,
    )


def _find_gaps(
    segments: list[TimelineSegment],
    day_start: datetime,
    day_end: datetime,
) -> list[TimelineGap]:
    if not segments:
        return [TimelineGap(
            started_at=day_start,
            ended_at=day_end,
            duration_seconds=int((day_end - day_start).total_seconds()),
        )]
    gaps: list[TimelineGap] = []
    cursor = day_start
    for seg in segments:
        seg_start = max(seg.started_at, day_start)
        if seg_start > cursor:
            gaps.append(TimelineGap(
                started_at=cursor,
                ended_at=seg_start,
                duration_seconds=int((seg_start - cursor).total_seconds()),
            ))
        if seg.ended_at:
            cursor = max(cursor, min(seg.ended_at, day_end))
    if cursor < day_end:
        gaps.append(TimelineGap(
            started_at=cursor,
            ended_at=day_end,
            duration_seconds=int((day_end - cursor).total_seconds()),
        ))
    return gaps


async def get_calendar(
    db: AsyncSession,
    camera_id: str,
    year: int,
    month: int,
) -> CalendarResponse:
    import calendar as cal_mod
    _, days_in_month = cal_mod.monthrange(year, month)
    month_start = datetime(year, month, 1, tzinfo=timezone.utc)
    month_end = datetime(year, month, days_in_month, 23, 59, 59, tzinfo=timezone.utc)

    result = await db.execute(
        select(RecordingSegment)
        .where(
            RecordingSegment.camera_id == camera_id,
            RecordingSegment.started_at >= month_start,
            RecordingSegment.started_at <= month_end,
        )
        .order_by(RecordingSegment.started_at)
    )
    segments = list(result.scalars().all())

    alert_result = await db.execute(
        select(AlertEvent.triggered_at).where(
            AlertEvent.camera_id == camera_id,
            AlertEvent.triggered_at >= month_start,
            AlertEvent.triggered_at <= month_end,
        )
    )
    alert_dates = {row[0].date() for row in alert_result.all()}

    # Group by day
    day_data: dict[date, dict] = {}
    for seg in segments:
        d = seg.started_at.date()
        if d not in day_data:
            day_data[d] = {"seconds": 0, "bytes": 0}
        day_data[d]["seconds"] += seg.duration_seconds or 0
        day_data[d]["bytes"] += seg.file_size_bytes or 0

    days = []
    for day_num in range(1, days_in_month + 1):
        d = date(year, month, day_num)
        info = day_data.get(d, {})
        days.append(CalendarDay(
            date=d,
            has_recordings=d in day_data,
            has_alerts=d in alert_dates,
            recording_hours=round(info.get("seconds", 0) / 3600, 2),
            storage_mb=round(info.get("bytes", 0) / (1024 * 1024), 2),
        ))

    return CalendarResponse(camera_id=camera_id, year=year, month=month, days=days)


async def get_segments(
    db: AsyncSession,
    camera_id: str | None = None,
    from_dt: datetime | None = None,
    to_dt: datetime | None = None,
    segment_type: str | None = None,
    has_alert: bool | None = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[RecordingSegment], int]:
    stmt = select(RecordingSegment)
    if camera_id:
        stmt = stmt.where(RecordingSegment.camera_id == camera_id)
    if from_dt:
        stmt = stmt.where(RecordingSegment.started_at >= from_dt)
    if to_dt:
        stmt = stmt.where(RecordingSegment.started_at <= to_dt)
    if segment_type:
        stmt = stmt.where(RecordingSegment.segment_type == segment_type)
    if has_alert is not None:
        stmt = stmt.where(RecordingSegment.has_alert.is_(has_alert))

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_result = await db.execute(count_stmt)
    total = total_result.scalar_one()

    offset = (page - 1) * page_size
    stmt = stmt.order_by(RecordingSegment.started_at.desc()).offset(offset).limit(page_size)
    result = await db.execute(stmt)
    return list(result.scalars().all()), total


async def find_segment_at(
    db: AsyncSession,
    camera_id: str,
    timestamp: datetime,
) -> RecordingSegment | None:
    result = await db.execute(
        select(RecordingSegment)
        .where(
            RecordingSegment.camera_id == camera_id,
            RecordingSegment.started_at <= timestamp,
            RecordingSegment.ended_at >= timestamp,
        )
        .order_by(RecordingSegment.started_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def find_segments_in_range(
    db: AsyncSession,
    camera_ids: list[str],
    from_dt: datetime,
    to_dt: datetime,
) -> list[RecordingSegment]:
    result = await db.execute(
        select(RecordingSegment)
        .where(
            RecordingSegment.camera_id.in_(camera_ids),
            RecordingSegment.started_at < to_dt,
            RecordingSegment.ended_at > from_dt,
        )
        .order_by(RecordingSegment.camera_id, RecordingSegment.started_at)
    )
    return list(result.scalars().all())
