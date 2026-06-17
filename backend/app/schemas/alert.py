"""
Alert, AlertRule, NotificationChannel, and DetectionEvent schemas.
"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.core.constants import NotificationChannelType, Severity


# ── Detection event (inbound from detection service via Redis) ─────────────────

class DetectionEvent(BaseModel):
    model_config = ConfigDict(extra="ignore")
    camera_id: str
    detection_type: str
    zone_name: str | None = None
    confidence: float | None = None
    severity: Severity = Severity.medium
    rule_triggered: str | None = None
    bbox: dict | None = None
    track_id: int | None = None
    triggered_at: datetime
    frame_path: str | None = None
    frame_b64: str | None = None


# ── Alert event responses ──────────────────────────────────────────────────────

class AlertEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    camera_id: str
    alert_rule_id: str | None
    triggered_at: datetime
    detection_type: str | None
    zone_name: str | None
    confidence: float | None
    severity: Severity
    rule_triggered: str | None
    bbox: dict | None
    track_id: int | None
    frame_path: str | None
    clip_path: str | None
    clip_checksum: str | None
    is_false_positive: bool
    is_on_legal_hold: bool
    acknowledged: bool
    acknowledged_by: str | None
    acknowledged_at: datetime | None
    notes: str | None
    created_at: datetime


class AlertAcknowledgeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    notes: str | None = None


class AlertFalsePositiveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    notes: str | None = None


class AlertLegalHoldRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    hold: bool


class AlertStatsResponse(BaseModel):
    total: int = 0
    unacknowledged: int = 0
    by_severity: dict[str, int]
    by_camera: dict[str, int]
    by_rule: dict[str, int]
    by_hour: list[dict]


# ── Alert rules ────────────────────────────────────────────────────────────────

class AlertRuleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(..., max_length=200)
    camera_id: str | None = None
    detection_types: list[str] = Field(default_factory=list)
    severity: Severity
    schedule: dict | None = None
    enabled: bool = True
    notification_channels: list[str] = Field(default_factory=list)


class AlertRuleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, max_length=200)
    camera_id: str | None = None
    detection_types: list[str] | None = None
    severity: Severity | None = None
    schedule: dict | None = None
    enabled: bool | None = None
    notification_channels: list[str] | None = None


class AlertRuleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    camera_id: str | None
    detection_types: list[str]
    severity: Severity
    schedule: dict | None
    enabled: bool
    notification_channels: list[str]
    created_at: datetime


# ── Notification channels ──────────────────────────────────────────────────────

class NotificationChannelCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, max_length=200)
    channel_type: NotificationChannelType
    config: dict
    enabled: bool = True


class NotificationChannelUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, max_length=200)
    channel_type: NotificationChannelType | None = None
    config: dict | None = None
    enabled: bool | None = None


class NotificationChannelResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str | None
    channel_type: str
    enabled: bool
    created_at: datetime
