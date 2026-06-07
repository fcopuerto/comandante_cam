import re
from datetime import datetime, timezone
from typing import Any


def fix_rtsp_url(url: str, camera_ip: str) -> str:
    """Replace 0.0.0.0 or localhost in an RTSP URL host with the actual camera IP."""
    return re.sub(
        r"^(rtsp://)(?:0\.0\.0\.0|localhost)(.*)",
        lambda m: f"{m.group(1)}{camera_ip}{m.group(2)}",
        url,
    )


def parse_datetime_from_onvif(dt_struct: Any) -> datetime:
    """Convert a zeep datetime struct or Python datetime to a UTC-aware datetime."""
    if dt_struct is None:
        return datetime.now(timezone.utc)
    if isinstance(dt_struct, datetime):
        if dt_struct.tzinfo is None:
            return dt_struct.replace(tzinfo=timezone.utc)
        return dt_struct.astimezone(timezone.utc)
    # zeep wraps datetime in objects with year/month/day/hour/minute/second attributes
    try:
        return datetime(
            year=int(dt_struct.Year),
            month=int(dt_struct.Month),
            day=int(dt_struct.Day),
            hour=int(dt_struct.Hour),
            minute=int(dt_struct.Minute),
            second=int(dt_struct.Second),
            tzinfo=timezone.utc,
        )
    except (AttributeError, TypeError, ValueError):
        return datetime.now(timezone.utc)


def safe_get(obj: Any, *attrs: str, default: Any = None) -> Any:
    """Safely navigate a chain of attributes or dict keys on nested ONVIF response objects."""
    for attr in attrs:
        if obj is None:
            return default
        try:
            if isinstance(obj, dict):
                obj = obj[attr]
            else:
                obj = getattr(obj, attr)
        except (AttributeError, KeyError, TypeError, IndexError):
            return default
    return obj if obj is not None else default
