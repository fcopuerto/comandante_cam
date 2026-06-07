import asyncio
import subprocess
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx
import structlog

from app.core.exceptions import CameraConnectionError
from app.models.camera import Camera
from app.schemas.camera import CameraProbeResult, DiscoveredCamera, PTZPreset
from app.utils.encryption import get_encryption
from app.utils.onvif_helpers import fix_rtsp_url, parse_datetime_from_onvif, safe_get

logger = structlog.get_logger(__name__)


# ── WS-Discovery ─────────────────────────────────────────────────────────────

def _sync_discover(timeout: float) -> list[DiscoveredCamera]:
    try:
        from wsdiscovery.discovery import ThreadedWSDiscovery as WSDiscovery
    except ImportError:
        logger.warning("wsdiscovery_unavailable")
        return []

    results: list[DiscoveredCamera] = []
    seen_ips: set[str] = set()
    wsd = WSDiscovery()
    try:
        wsd.start()
        services = wsd.searchServices(timeout=timeout)
        for svc in services:
            xaddrs = list(svc.getXAddrs() or [])
            ip = None
            port = 80
            for xaddr in xaddrs:
                try:
                    parsed = urlparse(xaddr)
                    ip = parsed.hostname
                    port = parsed.port or 80
                    break
                except Exception:
                    continue
            if not ip or ip in seen_ips:
                continue
            seen_ips.add(ip)
            results.append(DiscoveredCamera(ip=ip, port=port, xaddrs=xaddrs))
    except Exception:
        logger.exception("wsdiscovery_error")
    finally:
        try:
            wsd.stop()
        except Exception:
            pass
    return results


async def discover_cameras(subnet: str, timeout: float = 5.0) -> list[DiscoveredCamera]:
    loop = asyncio.get_event_loop()
    cameras = await loop.run_in_executor(None, _sync_discover, timeout)
    logger.info("wsdiscovery_complete", found=len(cameras), subnet=subnet)
    return cameras


# ── Camera probe ──────────────────────────────────────────────────────────────

def _sync_probe(ip: str, port: int, username: str, password: str) -> CameraProbeResult:
    from onvif import ONVIFCamera

    try:
        try:
            from zeep.settings import Settings as ZeepSettings
            cam = ONVIFCamera(ip, port, username, password,
                              zeep_settings=ZeepSettings(strict=False))
        except TypeError:
            cam = ONVIFCamera(ip, port, username, password)

        device_svc = cam.create_devicemgmt_service()

        # Device info
        try:
            dev_info = device_svc.GetDeviceInformation()
        except Exception:
            dev_info = None

        manufacturer = safe_get(dev_info, "Manufacturer", default=None)
        model = safe_get(dev_info, "Model", default=None)
        firmware = safe_get(dev_info, "FirmwareVersion", default=None)
        serial = safe_get(dev_info, "SerialNumber", default=None)
        hw_id = safe_get(dev_info, "HardwareId", default=None)
        mac_address = hw_id  # HardwareId often contains MAC on some cameras

        # Profiles
        media_svc = cam.create_media_service()
        try:
            profiles = media_svc.GetProfiles()
        except Exception:
            profiles = []

        profile_main_token = None
        profile_sub_token = None
        if profiles:
            profile_main_token = safe_get(profiles[0], "_token") or safe_get(profiles[0], "token")
            if len(profiles) > 1:
                profile_sub_token = safe_get(profiles[1], "_token") or safe_get(profiles[1], "token")

        # Stream URIs
        rtsp_main_url = None
        rtsp_sub_url = None

        def _get_stream_uri(profile_token: str) -> str | None:
            try:
                uri_resp = media_svc.GetStreamUri({
                    "StreamSetup": {
                        "Stream": "RTP-Unicast",
                        "Transport": {"Protocol": "RTSP"},
                    },
                    "ProfileToken": profile_token,
                })
                uri = safe_get(uri_resp, "Uri")
                if uri:
                    return fix_rtsp_url(str(uri), ip)
            except Exception:
                pass
            return None

        if profile_main_token:
            rtsp_main_url = _get_stream_uri(profile_main_token)
        if profile_sub_token:
            rtsp_sub_url = _get_stream_uri(profile_sub_token)

        # Video encoder config
        resolution_main = None
        resolution_sub = None
        fps = None
        bitrate_kbps = None
        codec = None
        try:
            enc_cfgs = media_svc.GetVideoEncoderConfigurations()
            if enc_cfgs:
                cfg = enc_cfgs[0]
                w = safe_get(cfg, "Resolution", "Width")
                h = safe_get(cfg, "Resolution", "Height")
                if w and h:
                    resolution_main = f"{w}x{h}"
                fps = safe_get(cfg, "RateControl", "FrameRateLimit")
                bitrate_kbps = safe_get(cfg, "RateControl", "BitrateLimit")
                enc_name = safe_get(cfg, "Encoding")
                if enc_name:
                    codec = str(enc_name).lower()
            if len(enc_cfgs) > 1:
                cfg2 = enc_cfgs[1]
                w2 = safe_get(cfg2, "Resolution", "Width")
                h2 = safe_get(cfg2, "Resolution", "Height")
                if w2 and h2:
                    resolution_sub = f"{w2}x{h2}"
        except Exception:
            pass

        # PTZ
        ptz_enabled = False
        try:
            ptz_svc = cam.create_ptz_service()
            ptz_cfgs = ptz_svc.GetConfigurations()
            ptz_enabled = bool(ptz_cfgs)
        except Exception:
            pass

        # Test RTSP reachability via ffprobe
        rtsp_reachable = False
        if rtsp_main_url:
            try:
                proc = subprocess.run(
                    ["ffprobe", "-v", "quiet", "-rtsp_transport", "tcp",
                     "-i", rtsp_main_url],
                    timeout=5,
                    capture_output=True,
                )
                rtsp_reachable = proc.returncode == 0
            except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
                pass

        return CameraProbeResult(
            manufacturer=manufacturer,
            model=model,
            firmware_version=firmware,
            serial_number=serial,
            mac_address=mac_address,
            rtsp_main_url=rtsp_main_url,
            rtsp_sub_url=rtsp_sub_url,
            onvif_profile_main=profile_main_token,
            onvif_profile_sub=profile_sub_token,
            resolution_main=resolution_main,
            resolution_sub=resolution_sub,
            fps=int(fps) if fps is not None else None,
            bitrate_kbps=int(bitrate_kbps) if bitrate_kbps is not None else None,
            codec=codec,
            ptz_enabled=ptz_enabled,
            rtsp_reachable=rtsp_reachable,
        )

    except Exception as exc:
        reason = str(exc)
        err_lower = reason.lower()
        if any(k in err_lower for k in ("401", "unauthorized", "auth", "forbidden")):
            raise CameraConnectionError(ip, "Authentication failed") from exc
        if any(k in err_lower for k in ("timeout", "timed out")):
            raise CameraConnectionError(ip, "Connection timed out") from exc
        if any(k in err_lower for k in ("connection refused", "connect call failed")):
            raise CameraConnectionError(ip, "Connection refused") from exc
        raise CameraConnectionError(ip, f"ONVIF error: {reason}") from exc


async def probe_camera(ip: str, port: int, username: str, password: str) -> CameraProbeResult:
    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(None, _sync_probe, ip, port, username, password)
        logger.info("camera_probe_success", ip=ip, manufacturer=result.manufacturer, model=result.model)
        return result
    except CameraConnectionError:
        raise
    except Exception as exc:
        raise CameraConnectionError(ip, str(exc)) from exc


# ── Time sync ─────────────────────────────────────────────────────────────────

def _sync_time_op(camera: Camera) -> bool:
    try:
        from onvif import ONVIFCamera
        password = get_encryption().decrypt(camera.password_encrypted) if camera.password_encrypted else ""
        try:
            from zeep.settings import Settings as ZeepSettings
            cam = ONVIFCamera(camera.ip_address, camera.onvif_port,
                              camera.username or "", password,
                              zeep_settings=ZeepSettings(strict=False))
        except TypeError:
            cam = ONVIFCamera(camera.ip_address, camera.onvif_port,
                              camera.username or "", password)

        device_svc = cam.create_devicemgmt_service()
        camera_dt_resp = device_svc.GetSystemDateAndTime()
        camera_utc = parse_datetime_from_onvif(
            safe_get(camera_dt_resp, "UTCDateTime")
        )
        drift_s = (datetime.now(timezone.utc) - camera_utc).total_seconds()
        logger.info("camera_time_drift", camera_id=camera.id, drift_seconds=drift_s)

        now = datetime.now(timezone.utc)
        device_svc.SetSystemDateAndTime({
            "DateTimeType": "Manual",
            "DaylightSavings": False,
            "TimeZone": {"TZ": "UTC"},
            "UTCDateTime": {
                "Date": {"Year": now.year, "Month": now.month, "Day": now.day},
                "Time": {"Hour": now.hour, "Minute": now.minute, "Second": now.second},
            },
        })
        logger.info("camera_time_synced", camera_id=camera.id)
        return True
    except Exception as exc:
        logger.warning("camera_time_sync_failed", camera_id=camera.id, error=str(exc))
        return False


async def sync_time(camera: Camera) -> bool:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _sync_time_op, camera)


# ── Snapshot ──────────────────────────────────────────────────────────────────

def _sync_snapshot(camera: Camera) -> bytes:
    from onvif import ONVIFCamera
    password = get_encryption().decrypt(camera.password_encrypted) if camera.password_encrypted else ""
    try:
        from zeep.settings import Settings as ZeepSettings
        cam = ONVIFCamera(camera.ip_address, camera.onvif_port,
                          camera.username or "", password,
                          zeep_settings=ZeepSettings(strict=False))
    except TypeError:
        cam = ONVIFCamera(camera.ip_address, camera.onvif_port,
                          camera.username or "", password)

    media_svc = cam.create_media_service()
    profile_token = camera.onvif_profile_main
    if not profile_token:
        profiles = media_svc.GetProfiles()
        if not profiles:
            raise CameraConnectionError(camera.ip_address, "No ONVIF profiles available")
        profile_token = safe_get(profiles[0], "_token") or safe_get(profiles[0], "token")

    snap_uri_resp = media_svc.GetSnapshotUri({"ProfileToken": profile_token})
    snap_url = safe_get(snap_uri_resp, "Uri")
    if not snap_url:
        raise CameraConnectionError(camera.ip_address, "No snapshot URI returned")

    import httpx as _httpx
    with _httpx.Client(auth=(camera.username or "", password), timeout=10.0) as client:
        resp = client.get(str(snap_url))
        resp.raise_for_status()
        return resp.content


async def get_snapshot(camera: Camera) -> bytes:
    loop = asyncio.get_event_loop()
    try:
        return await loop.run_in_executor(None, _sync_snapshot, camera)
    except Exception:
        pass  # fall through to RTSP fallback

    # Fallback: grab one frame from RTSP via FFmpeg
    rtsp_url = camera.rtsp_main_url or camera.rtsp_sub_url
    if not rtsp_url:
        raise CameraConnectionError(camera.ip_address, "No snapshot URI and no RTSP URL available")
    return await _ffmpeg_snapshot(rtsp_url)


async def _ffmpeg_snapshot(rtsp_url: str) -> bytes:
    import asyncio as _asyncio
    cmd = [
        "ffmpeg", "-y",
        "-rtsp_transport", "tcp",
        "-i", rtsp_url,
        "-vframes", "1",
        "-f", "image2pipe",
        "-vcodec", "mjpeg",
        "pipe:1",
    ]
    try:
        proc = await _asyncio.create_subprocess_exec(
            *cmd,
            stdout=_asyncio.subprocess.PIPE,
            stderr=_asyncio.subprocess.PIPE,
        )
        stdout, _ = await _asyncio.wait_for(proc.communicate(), timeout=15.0)
        if proc.returncode != 0 or not stdout:
            raise CameraConnectionError(rtsp_url, "FFmpeg snapshot failed")
        return stdout
    except _asyncio.TimeoutError as exc:
        raise CameraConnectionError(rtsp_url, "FFmpeg snapshot timed out") from exc


# ── PTZ ───────────────────────────────────────────────────────────────────────

def _build_ptz_cam(camera: Camera):
    from onvif import ONVIFCamera
    password = get_encryption().decrypt(camera.password_encrypted) if camera.password_encrypted else ""
    try:
        from zeep.settings import Settings as ZeepSettings
        cam = ONVIFCamera(camera.ip_address, camera.onvif_port,
                          camera.username or "", password,
                          zeep_settings=ZeepSettings(strict=False))
    except TypeError:
        cam = ONVIFCamera(camera.ip_address, camera.onvif_port,
                          camera.username or "", password)
    ptz_svc = cam.create_ptz_service()
    return ptz_svc, camera.onvif_profile_main


def _sync_get_ptz_presets(camera: Camera) -> list[PTZPreset]:
    try:
        ptz_svc, profile_token = _build_ptz_cam(camera)
        presets = ptz_svc.GetPresets({"ProfileToken": profile_token or ""})
        return [
            PTZPreset(
                token=safe_get(p, "_token") or safe_get(p, "token") or "",
                name=safe_get(p, "Name") or "",
            )
            for p in (presets or [])
        ]
    except Exception as exc:
        logger.warning("ptz_get_presets_failed", camera_id=camera.id, error=str(exc))
        return []


async def get_ptz_presets(camera: Camera) -> list[PTZPreset]:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _sync_get_ptz_presets, camera)


def _sync_goto_preset(camera: Camera, preset_token: str) -> bool:
    try:
        ptz_svc, profile_token = _build_ptz_cam(camera)
        ptz_svc.GotoPreset({
            "ProfileToken": profile_token or "",
            "PresetToken": preset_token,
            "Speed": {},
        })
        return True
    except Exception as exc:
        logger.warning("ptz_goto_preset_failed", camera_id=camera.id, error=str(exc))
        return False


async def goto_preset(camera: Camera, preset_token: str) -> bool:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _sync_goto_preset, camera, preset_token)


def _sync_save_preset(camera: Camera, preset_name: str) -> str:
    ptz_svc, profile_token = _build_ptz_cam(camera)
    resp = ptz_svc.SetPreset({"ProfileToken": profile_token or "", "PresetName": preset_name})
    token = safe_get(resp, "PresetToken") or ""
    return str(token)


async def save_preset(camera: Camera, preset_name: str) -> str:
    loop = asyncio.get_event_loop()
    try:
        return await loop.run_in_executor(None, _sync_save_preset, camera, preset_name)
    except Exception as exc:
        raise CameraConnectionError(camera.ip_address, f"Save preset failed: {exc}") from exc


def _sync_continuous_move(camera: Camera, pan: float, tilt: float, zoom: float) -> bool:
    try:
        ptz_svc, profile_token = _build_ptz_cam(camera)
        ptz_svc.ContinuousMove({
            "ProfileToken": profile_token or "",
            "Velocity": {
                "PanTilt": {"x": pan, "y": tilt},
                "Zoom": {"x": zoom},
            },
        })
        return True
    except Exception as exc:
        logger.warning("ptz_move_failed", camera_id=camera.id, error=str(exc))
        return False


async def continuous_move(camera: Camera, pan: float, tilt: float, zoom: float) -> bool:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _sync_continuous_move, camera, pan, tilt, zoom)


def _sync_stop_ptz(camera: Camera) -> bool:
    try:
        ptz_svc, profile_token = _build_ptz_cam(camera)
        ptz_svc.Stop({"ProfileToken": profile_token or "", "PanTilt": True, "Zoom": True})
        return True
    except Exception as exc:
        logger.warning("ptz_stop_failed", camera_id=camera.id, error=str(exc))
        return False


async def stop_ptz(camera: Camera) -> bool:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _sync_stop_ptz, camera)
