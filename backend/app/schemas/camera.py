from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from app.core.constants import CameraStatus, Codec, RecordingMode

T = TypeVar("T")


# ── Generic pagination ────────────────────────────────────────────────────────

class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
    pages: int


# ── Discovery / probe ─────────────────────────────────────────────────────────

class DiscoveredCamera(BaseModel):
    ip: str
    port: int = 80
    xaddrs: list[str] = []
    manufacturer: str | None = None
    model: str | None = None


class CameraProbeResult(BaseModel):
    manufacturer: str | None = None
    model: str | None = None
    firmware_version: str | None = None
    serial_number: str | None = None
    mac_address: str | None = None
    rtsp_main_url: str | None = None
    rtsp_sub_url: str | None = None
    onvif_profile_main: str | None = None
    onvif_profile_sub: str | None = None
    resolution_main: str | None = None
    resolution_sub: str | None = None
    fps: int | None = None
    bitrate_kbps: int | None = None
    codec: str | None = None
    ptz_enabled: bool = False
    rtsp_reachable: bool = False


class CameraTestResult(BaseModel):
    onvif_reachable: bool
    rtsp_reachable: bool
    probe_result: CameraProbeResult | None = None
    error: str | None = None


# ── Request bodies ─────────────────────────────────────────────────────────────

class DiscoverRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    subnet: str
    timeout: float = Field(default=5.0, ge=1.0, le=30.0)


class ProbeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ip: str
    port: int = 80
    username: str
    password: str


class CameraCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(..., max_length=100)
    ip_address: str
    onvif_port: int = 80
    username: str | None = None
    password: str | None = None
    description: str | None = None
    group_id: str | None = None
    zone_location: str | None = None
    building: str | None = None
    floor: str | None = None
    map_x: float | None = None
    map_y: float | None = None
    is_vpn: bool = False
    vpn_host: str | None = None
    tags: list[str] = []
    notes: str | None = None
    recording_mode: RecordingMode = RecordingMode.continuous
    retention_days: int = Field(default=30, ge=1, le=365)


class CameraUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, max_length=100)
    ip_address: str | None = None
    onvif_port: int | None = None
    username: str | None = None
    password: str | None = None
    description: str | None = None
    group_id: str | None = None
    zone_location: str | None = None
    building: str | None = None
    floor: str | None = None
    map_x: float | None = None
    map_y: float | None = None
    is_vpn: bool | None = None
    vpn_host: str | None = None
    tags: list[str] | None = None
    notes: str | None = None
    recording_mode: RecordingMode | None = None
    retention_days: int | None = Field(default=None, ge=1, le=365)
    fps: int | None = None
    bitrate_kbps: int | None = None
    codec: Codec | None = None
    pre_event_seconds: int | None = None
    post_event_seconds: int | None = None
    detection_enabled: bool | None = None
    ptz_enabled: bool | None = None


class RecordingModeUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: RecordingMode


class PTZMoveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pan: float = Field(..., ge=-1.0, le=1.0)
    tilt: float = Field(..., ge=-1.0, le=1.0)
    zoom: float = Field(default=0.0, ge=-1.0, le=1.0)
    speed: float = Field(default=0.5, ge=0.0, le=1.0)


class PTZPresetCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(..., max_length=100)


# ── Schedules ──────────────────────────────────────────────────────────────────

class ScheduleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(..., max_length=100)
    days_of_week: list[int] = Field(..., description="0=Mon … 6=Sun")
    time_start: str = Field(..., description="HH:MM")
    time_end: str = Field(..., description="HH:MM")
    recording_mode: RecordingMode = RecordingMode.continuous
    enabled: bool = True


class ScheduleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = None
    days_of_week: list[int] | None = None
    time_start: str | None = None
    time_end: str | None = None
    recording_mode: RecordingMode | None = None
    enabled: bool | None = None


class ScheduleResponse(BaseModel):
    id: str
    camera_id: str
    name: str | None
    days_of_week: list[int]
    time_start: str
    time_end: str
    recording_mode: RecordingMode
    enabled: bool
    created_at: datetime


# ── Zones ──────────────────────────────────────────────────────────────────────

class ZoneCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(..., max_length=100)
    polygon: list[list[float]]
    restricted: bool = False
    enabled: bool = True
    working_hours_start: str | None = None
    working_hours_end: str | None = None
    timezone: str = "UTC"
    dwell_threshold_s: int = 30
    color: str | None = None


class ZoneUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = None
    polygon: list[list[float]] | None = None
    restricted: bool | None = None
    enabled: bool | None = None
    working_hours_start: str | None = None
    working_hours_end: str | None = None
    timezone: str | None = None
    dwell_threshold_s: int | None = None
    color: str | None = None


class ZoneBulkItem(BaseModel):
    """One zone in a bulk-replace request; id is ignored (treated as new)."""
    name: str = Field(..., max_length=100)
    polygon: list[list[float]]
    restricted: bool = False
    enabled: bool = True
    working_hours_start: str | None = None
    working_hours_end: str | None = None
    timezone: str = "UTC"
    dwell_threshold_s: int = 30
    color: str | None = None
    is_privacy_mask: bool = False


class ZoneBulkUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    zones: list[ZoneBulkItem]


class ZoneResponse(BaseModel):
    id: str
    camera_id: str
    name: str
    polygon: list[list[float]]
    restricted: bool
    enabled: bool
    working_hours_start: str | None
    working_hours_end: str | None
    timezone: str
    dwell_threshold_s: int
    color: str | None
    created_at: datetime
    updated_at: datetime


# ── Permissions ────────────────────────────────────────────────────────────────

class CameraPermissionResponse(BaseModel):
    user_id: str
    camera_id: str
    can_view_live: bool
    can_view_recordings: bool
    can_export_clips: bool
    can_configure: bool
    can_ptz: bool
    granted_at: datetime


class CameraPermissionSet(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: str
    can_view_live: bool = False
    can_view_recordings: bool = False
    can_export_clips: bool = False
    can_configure: bool = False
    can_ptz: bool = False


# ── PTZ ────────────────────────────────────────────────────────────────────────

class PTZPreset(BaseModel):
    token: str
    name: str


# ── Stats ─────────────────────────────────────────────────────────────────────

class CameraStats(BaseModel):
    camera_id: str
    recording_hours_30d: float
    storage_used_bytes: int
    alert_count_30d: int


# ── Response ──────────────────────────────────────────────────────────────────

class CameraResponse(BaseModel):
    id: str
    name: str
    description: str | None
    ip_address: str
    onvif_port: int
    onvif_profile_main: str | None
    onvif_profile_sub: str | None
    manufacturer: str | None
    model: str | None
    firmware_version: str | None
    serial_number: str | None
    mac_address: str | None
    is_vpn: bool
    vpn_host: str | None
    group_id: str | None
    zone_location: str | None
    building: str | None
    floor: str | None
    map_x: float | None
    map_y: float | None
    status: CameraStatus
    recording_mode: RecordingMode
    resolution_main: str | None
    resolution_sub: str | None
    fps: int
    bitrate_kbps: int
    codec: Codec
    retention_days: int
    pre_event_seconds: int
    post_event_seconds: int
    ptz_enabled: bool
    tags: list[str]
    notes: str | None
    detection_enabled: bool
    created_at: datetime
    updated_at: datetime
    created_by: str | None


class StreamUrlResponse(BaseModel):
    hls_url: str
    sub_hls_url: str
    camera: CameraResponse
