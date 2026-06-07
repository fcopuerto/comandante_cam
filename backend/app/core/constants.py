import enum


class CameraStatus(str, enum.Enum):
    online = "online"
    offline = "offline"
    error = "error"
    recording = "recording"
    unauthorized = "unauthorized"
    unknown = "unknown"


class RecordingMode(str, enum.Enum):
    continuous = "continuous"
    motion = "motion"
    scheduled = "scheduled"
    off = "off"


class SegmentType(str, enum.Enum):
    continuous = "continuous"
    motion = "motion"
    scheduled = "scheduled"
    event = "event"
    manual = "manual"


class Codec(str, enum.Enum):
    h264 = "h264"
    h265 = "h265"
    mjpeg = "mjpeg"


class Severity(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class ExportStatus(str, enum.Enum):
    queued = "queued"
    processing = "processing"
    completed = "completed"
    failed = "failed"
    expired = "expired"


class NotificationChannelType(str, enum.Enum):
    email = "email"
    webhook = "webhook"
    telegram = "telegram"
    slack = "slack"
    pushover = "pushover"
