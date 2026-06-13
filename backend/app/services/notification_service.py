"""
Notification service — dispatches alert notifications to configured channels.
All sending functions are synchronous (called from Celery workers).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import smtplib
import time
from datetime import timezone
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from app.models.alert_event import AlertEvent
    from app.models.camera import Camera
    from app.models.notification_channel import NotificationChannel

logger = structlog.get_logger(__name__)

_SEVERITY_TO_PUSHOVER = {"low": -1, "medium": 0, "high": 1, "critical": 2}


def _retry(fn, max_attempts: int = 3, base_delay: float = 1.0):
    last_exc: Exception | None = None
    for attempt in range(max_attempts):
        try:
            fn()
            return
        except Exception as exc:
            last_exc = exc
            if attempt < max_attempts - 1:
                time.sleep(base_delay * (2 ** attempt))
    raise last_exc  # type: ignore[misc]


def send_alert_notifications(
    alert: AlertEvent,
    camera: Camera,
    channels: list[NotificationChannel],
) -> None:
    for ch in channels:
        if not ch.enabled:
            continue
        config = ch.config or {}
        try:
            if ch.channel_type == "email":
                _retry(lambda: send_email(config, alert, camera))
            elif ch.channel_type == "webhook":
                _retry(lambda: send_webhook(config, alert, camera))
            elif ch.channel_type == "telegram":
                _retry(lambda: send_telegram(config, alert, camera))
            elif ch.channel_type == "slack":
                _retry(lambda: send_slack(config, alert, camera))
            elif ch.channel_type == "pushover":
                _retry(lambda: send_pushover(config, alert, camera))
            else:
                logger.warning("unknown_channel_type", channel_type=ch.channel_type, channel_id=ch.id)
        except Exception:
            logger.exception("notification_send_failed", channel_id=ch.id, channel_type=ch.channel_type)


def send_email(config: dict, alert: AlertEvent, camera: Camera) -> None:
    from app.config import get_settings
    settings = get_settings()

    to_addresses = config.get("to", [])
    if isinstance(to_addresses, str):
        to_addresses = [to_addresses]
    if not to_addresses:
        return

    subject = f"[NVR Alert] {alert.severity.upper()} — {alert.detection_type or 'Unknown'} on {camera.name}"
    body_text = (
        f"Alert: {alert.detection_type or 'Unknown'}\n"
        f"Camera: {camera.name}\n"
        f"Severity: {alert.severity}\n"
        f"Zone: {alert.zone_name or 'N/A'}\n"
        f"Time: {alert.triggered_at.strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
        f"Confidence: {alert.confidence:.1%}\n" if alert.confidence else ""
    )

    msg = MIMEMultipart("alternative") if not alert.frame_path else MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["From"] = settings.SMTP_FROM
    msg["To"] = ", ".join(to_addresses)
    msg.attach(MIMEText(body_text, "plain"))

    if alert.frame_path:
        frame_file = Path(alert.frame_path)
        if frame_file.exists():
            img_data = frame_file.read_bytes()
            img = MIMEImage(img_data, name="alert_frame.jpg")
            img.add_header("Content-Disposition", "attachment", filename="alert_frame.jpg")
            msg.attach(img)

    smtp_host = config.get("smtp_host") or settings.SMTP_HOST
    smtp_port = int(config.get("smtp_port") or settings.SMTP_PORT)
    use_tls = config.get("smtp_starttls", settings.SMTP_STARTTLS)
    username = config.get("smtp_user") or settings.SMTP_USER
    password = config.get("smtp_password") or settings.SMTP_PASSWORD

    if not smtp_host:
        logger.warning("smtp_not_configured")
        return

    with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as server:
        if use_tls:
            server.starttls()
        if username and password:
            server.login(username, password)
        server.sendmail(settings.SMTP_FROM, to_addresses, msg.as_string())

    logger.info("notification_email_sent", alert_id=alert.id, to=to_addresses)


def send_invite_email(to_address: str, full_name: str, temp_password: str, app_url: str = "") -> None:
    from app.config import get_settings
    settings = get_settings()

    if not settings.SMTP_HOST:
        logger.warning("smtp_not_configured_invite")
        return

    subject = "You've been invited to NVR Pro"
    body = (
        f"Hello {full_name},\n\n"
        f"An account has been created for you on NVR Pro.\n\n"
        f"Login: {to_address}\n"
        f"Temporary password: {temp_password}\n\n"
        f"You will be asked to change your password on first login.\n"
        + (f"\nAccess the system at: {app_url}\n" if app_url else "")
        + "\nThis is an automated message — do not reply.\n"
    )

    msg = MIMEText(body, "plain")
    msg["Subject"] = subject
    msg["From"] = settings.SMTP_FROM
    msg["To"] = to_address

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as server:
        if settings.SMTP_STARTTLS:
            server.starttls()
        if settings.SMTP_USER and settings.SMTP_PASSWORD:
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        server.sendmail(settings.SMTP_FROM, [to_address], msg.as_string())

    logger.info("invite_email_sent", to=to_address)


def send_webhook(config: dict, alert: AlertEvent, camera: Camera) -> None:
    import httpx

    url = config.get("url")
    if not url:
        return
    secret = config.get("secret", "")
    custom_headers = config.get("headers") or {}

    payload = {
        "alert_id": alert.id,
        "camera_id": alert.camera_id,
        "camera_name": camera.name,
        "severity": alert.severity.value if hasattr(alert.severity, "value") else str(alert.severity),
        "detection_type": alert.detection_type,
        "zone_name": alert.zone_name,
        "triggered_at": alert.triggered_at.isoformat(),
        "confidence": alert.confidence,
        "bbox": alert.bbox,
    }
    body = json.dumps(payload)

    sig = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
    headers = {
        "Content-Type": "application/json",
        "X-NVR-Signature": f"sha256={sig}",
        **custom_headers,
    }

    with httpx.Client(timeout=10) as client:
        resp = client.post(url, content=body.encode(), headers=headers)
        resp.raise_for_status()

    logger.info("notification_webhook_sent", alert_id=alert.id, url=url)


def send_telegram(config: dict, alert: AlertEvent, camera: Camera) -> None:
    import httpx

    token = config.get("bot_token")
    chat_id = config.get("chat_id")
    if not token or not chat_id:
        return

    text = (
        f"🚨 *{alert.severity.upper()} Alert*\n"
        f"Camera: {camera.name}\n"
        f"Type: {alert.detection_type or 'Unknown'}\n"
        f"Zone: {alert.zone_name or 'N/A'}\n"
        f"Time: {alert.triggered_at.strftime('%H:%M:%S UTC')}"
    )

    base = f"https://api.telegram.org/bot{token}"
    with httpx.Client(timeout=15) as client:
        if alert.frame_path and Path(alert.frame_path).exists():
            with open(alert.frame_path, "rb") as f:
                client.post(
                    f"{base}/sendPhoto",
                    data={"chat_id": chat_id, "caption": text, "parse_mode": "Markdown"},
                    files={"photo": ("frame.jpg", f, "image/jpeg")},
                ).raise_for_status()
        else:
            client.post(
                f"{base}/sendMessage",
                json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
            ).raise_for_status()

    logger.info("notification_telegram_sent", alert_id=alert.id, chat_id=chat_id)


def send_slack(config: dict, alert: AlertEvent, camera: Camera) -> None:
    import httpx

    webhook_url = config.get("webhook_url")
    if not webhook_url:
        return

    color = {"low": "#36a64f", "medium": "#ffcc00", "high": "#ff6600", "critical": "#ff0000"}.get(
        str(alert.severity), "#cccccc"
    )

    payload = {
        "attachments": [
            {
                "color": color,
                "title": f"{str(alert.severity).upper()} Alert — {camera.name}",
                "fields": [
                    {"title": "Type", "value": alert.detection_type or "Unknown", "short": True},
                    {"title": "Zone", "value": alert.zone_name or "N/A", "short": True},
                    {"title": "Time", "value": alert.triggered_at.strftime("%Y-%m-%d %H:%M:%S UTC"), "short": False},
                ],
                "footer": "NVR Pro",
            }
        ]
    }

    with httpx.Client(timeout=10) as client:
        client.post(webhook_url, json=payload).raise_for_status()

    logger.info("notification_slack_sent", alert_id=alert.id)


def send_pushover(config: dict, alert: AlertEvent, camera: Camera) -> None:
    import httpx

    user_key = config.get("user_key")
    api_token = config.get("api_token")
    if not user_key or not api_token:
        return

    priority = _SEVERITY_TO_PUSHOVER.get(str(alert.severity), 0)
    message = (
        f"Camera: {camera.name}\n"
        f"Type: {alert.detection_type or 'Unknown'}\n"
        f"Zone: {alert.zone_name or 'N/A'}\n"
        f"Time: {alert.triggered_at.strftime('%H:%M:%S UTC')}"
    )

    data: dict = {
        "token": api_token,
        "user": user_key,
        "title": f"{str(alert.severity).upper()} Alert",
        "message": message,
        "priority": priority,
    }
    if priority == 2:
        data["retry"] = 60
        data["expire"] = 3600

    with httpx.Client(timeout=10) as client:
        client.post("https://api.pushover.net/1/messages.json", data=data).raise_for_status()

    logger.info("notification_pushover_sent", alert_id=alert.id)
