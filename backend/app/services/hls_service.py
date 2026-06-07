"""
HLS stream manager — manages FFmpeg HLS processes for live view.
Singleton attached to app.state.hls_manager during lifespan.
"""
import asyncio
import shutil
from typing import TYPE_CHECKING

import structlog

from app.config import get_settings
from app.utils.ffmpeg import FFmpegProcess, build_hls_command

if TYPE_CHECKING:
    from app.models.camera import Camera

logger = structlog.get_logger(__name__)


class HLSStreamManager:
    def __init__(self) -> None:
        self._streams: dict[str, FFmpegProcess] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        # camera_id → set of websocket connection IDs viewing this stream
        self._viewers: dict[str, set[str]] = {}
        self._watchdog_task: asyncio.Task | None = None

    async def start(self) -> None:
        self._watchdog_task = asyncio.create_task(self._watchdog())
        logger.info("hls_manager_started")

    async def stop_all(self) -> None:
        if self._watchdog_task:
            self._watchdog_task.cancel()
            try:
                await self._watchdog_task
            except asyncio.CancelledError:
                pass
        for camera_id in list(self._streams.keys()):
            await self.stop_stream(camera_id)
        logger.info("hls_manager_stopped")

    async def start_stream(self, camera: "Camera") -> str:
        """Start HLS stream for camera (idempotent). Returns HLS URL path."""
        lock = self._get_lock(camera.id)
        async with lock:
            proc = self._streams.get(camera.id)
            if proc and proc.is_running():
                logger.debug("hls_stream_already_running", camera_id=camera.id)
                return f"/hls/{camera.id}/index.m3u8"

            rtsp_url = camera.rtsp_sub_url or camera.rtsp_main_url
            if not rtsp_url:
                raise ValueError(f"Camera {camera.id} has no RTSP URL configured")

            settings = get_settings()
            hls_dir = settings.HLS_PATH / camera.id
            hls_dir.mkdir(parents=True, exist_ok=True)

            cmd = build_hls_command(rtsp_url, str(hls_dir), camera.id)
            new_proc = FFmpegProcess(camera.id, cmd)
            await asyncio.to_thread(new_proc.start)
            self._streams[camera.id] = new_proc
            if camera.id not in self._viewers:
                self._viewers[camera.id] = set()
            logger.info("hls_stream_started", camera_id=camera.id)

        return f"/hls/{camera.id}/index.m3u8"

    async def stop_stream(self, camera_id: str) -> None:
        lock = self._get_lock(camera_id)
        async with lock:
            proc = self._streams.pop(camera_id, None)
            if proc:
                await asyncio.to_thread(proc.stop)
            self._viewers.pop(camera_id, None)
            self._locks.pop(camera_id, None)

            settings = get_settings()
            hls_dir = settings.HLS_PATH / camera_id
            if hls_dir.exists():
                await asyncio.to_thread(shutil.rmtree, str(hls_dir), True)
            logger.info("hls_stream_stopped", camera_id=camera_id)

    def add_viewer(self, camera_id: str, viewer_id: str) -> None:
        if camera_id not in self._viewers:
            self._viewers[camera_id] = set()
        self._viewers[camera_id].add(viewer_id)

    def remove_viewer(self, camera_id: str, viewer_id: str) -> None:
        if camera_id in self._viewers:
            self._viewers[camera_id].discard(viewer_id)

    def viewer_count(self, camera_id: str) -> int:
        return len(self._viewers.get(camera_id, set()))

    def is_running(self, camera_id: str) -> bool:
        proc = self._streams.get(camera_id)
        return proc is not None and proc.is_running()

    async def get_status(self) -> dict[str, dict]:
        return {
            camera_id: {
                "status": "running" if proc.is_running() else "stopped",
                "viewers": self.viewer_count(camera_id),
            }
            for camera_id, proc in self._streams.items()
        }

    def _get_lock(self, camera_id: str) -> asyncio.Lock:
        if camera_id not in self._locks:
            self._locks[camera_id] = asyncio.Lock()
        return self._locks[camera_id]

    async def _watchdog(self) -> None:
        """Every 60 s: check all HLS processes are alive; restart if viewers waiting."""
        while True:
            try:
                await asyncio.sleep(60)
                for camera_id, proc in list(self._streams.items()):
                    if not proc.is_running():
                        logger.warning("hls_process_died", camera_id=camera_id)
                        # Remove dead process — stream-url endpoint restarts on next request
                        self._streams.pop(camera_id, None)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("hls_watchdog_error")
