from datetime import datetime
from datetime import date as DateType

from pydantic import BaseModel, ConfigDict, Field

from app.core.constants import ExportStatus, SegmentType


class TimelineSegment(BaseModel):
    segment_id: str
    started_at: datetime
    ended_at: datetime | None
    duration_seconds: int | None
    segment_type: SegmentType | None
    has_alert: bool
    has_motion: bool
    file_size_bytes: int | None
    thumbnail_path: str | None


class TimelineGap(BaseModel):
    started_at: datetime
    ended_at: datetime
    duration_seconds: int


class TimelineResponse(BaseModel):
    camera_id: str
    date: DateType
    segments: list[TimelineSegment]
    gaps: list[TimelineGap]
    coverage_pct: float


class CalendarDay(BaseModel):
    date: DateType
    has_recordings: bool
    has_alerts: bool
    recording_hours: float
    storage_mb: float


class CalendarResponse(BaseModel):
    camera_id: str
    year: int
    month: int
    days: list[CalendarDay]


class SegmentResponse(BaseModel):
    id: str
    camera_id: str
    started_at: datetime
    ended_at: datetime | None
    duration_seconds: int | None
    file_path: str
    file_name: str
    file_size_bytes: int | None
    segment_type: SegmentType | None
    has_motion: bool
    has_alert: bool
    is_corrupt: bool
    is_on_legal_hold: bool
    thumbnail_path: str | None
    width: int | None
    height: int | None
    fps: int | None
    codec: str | None
    created_at: datetime


# ── Export schemas ─────────────────────────────────────────────────────────────

class ExportCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    camera_ids: list[str] = Field(..., min_length=1)
    from_dt: datetime
    to_dt: datetime
    watermark: bool = True
    watermark_text: str | None = Field(default=None, max_length=200)
    password_protected: bool = False


class ExportJobResponse(BaseModel):
    id: str
    camera_ids: list[str]
    from_dt: datetime
    to_dt: datetime
    status: ExportStatus
    progress_pct: int
    file_size_bytes: int | None
    checksum_sha256: str | None
    password_protected: bool
    watermark: bool
    watermark_text: str | None
    error_message: str | None
    requested_by: str | None
    created_at: datetime
    completed_at: datetime | None
    expires_at: datetime | None
    download_url: str | None = None
    estimated_size_bytes: int | None = None
