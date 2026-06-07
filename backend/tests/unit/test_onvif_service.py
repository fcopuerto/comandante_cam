"""Unit tests for ONVIF service and helpers. No real camera required."""
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from freezegun import freeze_time

from app.core.exceptions import CameraConnectionError
from app.utils.onvif_helpers import fix_rtsp_url, parse_datetime_from_onvif, safe_get


# ── onvif_helpers ─────────────────────────────────────────────────────────────

def test_fix_rtsp_url_replaces_000():
    assert fix_rtsp_url("rtsp://0.0.0.0:554/stream", "192.168.1.10") == "rtsp://192.168.1.10:554/stream"


def test_fix_rtsp_url_replaces_localhost():
    assert fix_rtsp_url("rtsp://localhost:554/stream", "10.0.0.1") == "rtsp://10.0.0.1:554/stream"


def test_fix_rtsp_url_keeps_real_ip():
    url = "rtsp://192.168.1.5:554/stream1"
    assert fix_rtsp_url(url, "192.168.1.10") == url


def test_fix_rtsp_url_no_port():
    assert fix_rtsp_url("rtsp://0.0.0.0/live", "10.0.0.2") == "rtsp://10.0.0.2/live"


def test_safe_get_attribute():
    obj = MagicMock()
    obj.DeviceInfo = MagicMock()
    obj.DeviceInfo.Manufacturer = "Hikvision"
    assert safe_get(obj, "DeviceInfo", "Manufacturer") == "Hikvision"


def test_safe_get_missing_returns_default():
    obj = MagicMock(spec=[])
    assert safe_get(obj, "Nonexistent") is None
    assert safe_get(obj, "Nonexistent", default="fallback") == "fallback"


def test_safe_get_none_input():
    assert safe_get(None, "anything") is None


def test_safe_get_dict():
    d = {"a": {"b": 42}}
    assert safe_get(d, "a", "b") == 42
    assert safe_get(d, "a", "c") is None


def test_parse_datetime_from_onvif_with_struct():
    struct = MagicMock()
    struct.Year = 2024
    struct.Month = 6
    struct.Day = 15
    struct.Hour = 10
    struct.Minute = 30
    struct.Second = 0
    result = parse_datetime_from_onvif(struct)
    assert result == datetime(2024, 6, 15, 10, 30, 0, tzinfo=timezone.utc)


def test_parse_datetime_from_onvif_with_python_datetime():
    dt = datetime(2024, 6, 15, 10, 30, tzinfo=timezone.utc)
    assert parse_datetime_from_onvif(dt) == dt


def test_parse_datetime_from_onvif_with_none():
    result = parse_datetime_from_onvif(None)
    assert result.tzinfo == timezone.utc


# ── discover_cameras ──────────────────────────────────────────────────────────

def _make_wsd_service(ip: str, port: int = 80):
    svc = MagicMock()
    svc.getXAddrs.return_value = [f"http://{ip}:{port}/onvif/device_service"]
    return svc


@pytest.mark.asyncio
async def test_discover_cameras_parses_response():
    mock_service1 = _make_wsd_service("192.168.1.10", 80)
    mock_service2 = _make_wsd_service("192.168.1.11", 8080)

    mock_wsd = MagicMock()
    mock_wsd.searchServices.return_value = [mock_service1, mock_service2]

    with patch("app.services.onvif_service._sync_discover") as mock_sync:
        from app.schemas.camera import DiscoveredCamera
        mock_sync.return_value = [
            DiscoveredCamera(ip="192.168.1.10", port=80),
            DiscoveredCamera(ip="192.168.1.11", port=8080),
        ]
        from app.services import onvif_service
        result = await onvif_service.discover_cameras("192.168.1.0/24", timeout=2.0)

    assert len(result) == 2
    assert result[0].ip == "192.168.1.10"
    assert result[1].ip == "192.168.1.11"


@pytest.mark.asyncio
async def test_discover_cameras_returns_empty_on_error():
    with patch("app.services.onvif_service._sync_discover") as mock_sync:
        mock_sync.return_value = []
        from app.services import onvif_service
        result = await onvif_service.discover_cameras("10.0.0.0/24")
    assert result == []


# ── probe_camera ──────────────────────────────────────────────────────────────

def _build_mock_onvif_cam():
    """Build a fully-mocked ONVIFCamera that returns reasonable probe data."""
    mock_cam = MagicMock()

    dev_svc = MagicMock()
    dev_info = MagicMock()
    dev_info.Manufacturer = "Hikvision"
    dev_info.Model = "DS-2CD2143G2-I"
    dev_info.FirmwareVersion = "V5.7.15"
    dev_info.SerialNumber = "DS-2CD2143G2-I20221101BBRR123456789"
    dev_info.HardwareId = "AB:CD:EF:01:23:45"
    dev_svc.GetDeviceInformation.return_value = dev_info
    mock_cam.create_devicemgmt_service.return_value = dev_svc

    profile = MagicMock()
    profile._token = "Profile_1"
    sub_profile = MagicMock()
    sub_profile._token = "Profile_2"

    media_svc = MagicMock()
    media_svc.GetProfiles.return_value = [profile, sub_profile]

    uri_resp = MagicMock()
    uri_resp.Uri = "rtsp://0.0.0.0:554/Streaming/Channels/101"
    media_svc.GetStreamUri.return_value = uri_resp

    enc_cfg = MagicMock()
    enc_cfg.Resolution = MagicMock(Width=1920, Height=1080)
    enc_cfg.RateControl = MagicMock(FrameRateLimit=25, BitrateLimit=2048)
    enc_cfg.Encoding = "H264"
    media_svc.GetVideoEncoderConfigurations.return_value = [enc_cfg]
    mock_cam.create_media_service.return_value = media_svc

    ptz_svc = MagicMock()
    ptz_svc.GetConfigurations.return_value = [MagicMock()]
    mock_cam.create_ptz_service.return_value = ptz_svc

    return mock_cam


@pytest.mark.asyncio
async def test_probe_camera_success():
    mock_cam = _build_mock_onvif_cam()

    with (
        patch("app.services.onvif_service._sync_probe") as mock_probe,
    ):
        from app.schemas.camera import CameraProbeResult
        mock_probe.return_value = CameraProbeResult(
            manufacturer="Hikvision",
            model="DS-2CD2143G2-I",
            firmware_version="V5.7.15",
            serial_number="DS-2CD2143G2-I20221101BBRR123456789",
            rtsp_main_url="rtsp://192.168.1.10:554/Streaming/Channels/101",
            rtsp_sub_url="rtsp://192.168.1.10:554/Streaming/Channels/102",
            onvif_profile_main="Profile_1",
            onvif_profile_sub="Profile_2",
            resolution_main="1920x1080",
            fps=25,
            bitrate_kbps=2048,
            codec="h264",
            ptz_enabled=True,
            rtsp_reachable=False,
        )
        from app.services import onvif_service
        result = await onvif_service.probe_camera("192.168.1.10", 80, "admin", "password")

    assert result.manufacturer == "Hikvision"
    assert result.model == "DS-2CD2143G2-I"
    assert result.rtsp_main_url == "rtsp://192.168.1.10:554/Streaming/Channels/101"
    assert result.onvif_profile_main == "Profile_1"
    assert result.resolution_main == "1920x1080"
    assert result.fps == 25
    assert result.ptz_enabled is True


@pytest.mark.asyncio
async def test_probe_camera_auth_failure():
    with patch("app.services.onvif_service._sync_probe") as mock_probe:
        mock_probe.side_effect = CameraConnectionError("192.168.1.10", "Authentication failed")
        from app.services import onvif_service
        with pytest.raises(CameraConnectionError) as exc_info:
            await onvif_service.probe_camera("192.168.1.10", 80, "admin", "wrongpassword")
    assert exc_info.value.ip == "192.168.1.10"
    assert "Authentication" in exc_info.value.reason


@pytest.mark.asyncio
async def test_probe_camera_connection_refused():
    with patch("app.services.onvif_service._sync_probe") as mock_probe:
        mock_probe.side_effect = CameraConnectionError("10.0.0.99", "Connection refused")
        from app.services import onvif_service
        with pytest.raises(CameraConnectionError) as exc_info:
            await onvif_service.probe_camera("10.0.0.99", 80, "admin", "pass")
    assert "refused" in exc_info.value.reason


# ── sync_time ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
@freeze_time("2024-06-15 12:00:00")
async def test_sync_time_sends_utc():
    camera = MagicMock()
    camera.id = "test-camera-id"
    camera.ip_address = "192.168.1.10"
    camera.onvif_port = 80
    camera.username = "admin"
    camera.password_encrypted = None

    with patch("app.services.onvif_service._sync_time_op") as mock_sync:
        mock_sync.return_value = True
        from app.services import onvif_service
        result = await onvif_service.sync_time(camera)

    assert result is True
    mock_sync.assert_called_once_with(camera)


@pytest.mark.asyncio
async def test_sync_time_returns_false_on_error():
    camera = MagicMock()
    camera.id = "cam-1"
    camera.ip_address = "192.168.1.10"
    camera.onvif_port = 80
    camera.username = "admin"
    camera.password_encrypted = None

    with patch("app.services.onvif_service._sync_time_op") as mock_sync:
        mock_sync.return_value = False
        from app.services import onvif_service
        result = await onvif_service.sync_time(camera)

    assert result is False
