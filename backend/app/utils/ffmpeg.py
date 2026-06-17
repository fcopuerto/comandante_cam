import select
import signal
import subprocess
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import structlog

logger = structlog.get_logger(__name__)


class FFmpegEventType(str, Enum):
    stream_error = "stream_error"
    connection_refused = "connection_refused"
    reconnecting = "reconnecting"
    segment_created = "segment_created"
    clean_exit = "clean_exit"
    corrupt_stream = "corrupt_stream"


@dataclass
class FFmpegEvent:
    type: FFmpegEventType
    message: str = ""


class FFmpegProcess:
    def __init__(self, camera_id: str, command: list[str]) -> None:
        self.camera_id = camera_id
        self.command = command
        self._proc: Optional[subprocess.Popen] = None

    def start(self) -> subprocess.Popen:
        self._proc = subprocess.Popen(
            self.command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            bufsize=1,
        )
        logger.info("ffmpeg_started", camera_id=self.camera_id, pid=self._proc.pid)
        return self._proc

    def is_running(self) -> bool:
        if self._proc is None:
            return False
        return self._proc.poll() is None

    def stop(self, timeout: float = 5.0) -> None:
        if self._proc is None or not self.is_running():
            return
        try:
            self._proc.send_signal(signal.SIGTERM)
            self._proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self._proc.kill()
            self._proc.wait()
        except OSError:
            pass
        logger.info("ffmpeg_stopped", camera_id=self.camera_id)

    def read_stderr_line(self) -> Optional[str]:
        """Read one line from stderr without blocking. Returns None if nothing available."""
        if self._proc is None or self._proc.stderr is None:
            return None
        try:
            ready, _, _ = select.select([self._proc.stderr], [], [], 0)
            if ready:
                line = self._proc.stderr.readline()
                if line:
                    return line.decode("utf-8", errors="replace").rstrip()
        except (OSError, ValueError):
            pass
        return None

    def parse_stderr(self, line: str) -> Optional[FFmpegEvent]:
        lower = line.lower()
        if "connection refused" in lower:
            return FFmpegEvent(FFmpegEventType.connection_refused, line)
        if "invalid data found" in lower or "moov atom not found" in lower:
            return FFmpegEvent(FFmpegEventType.corrupt_stream, line)
        if "connection timed out" in lower or "no route to host" in lower:
            return FFmpegEvent(FFmpegEventType.stream_error, line)
        if "reconnecting" in lower or "trying to reconnect" in lower:
            return FFmpegEvent(FFmpegEventType.reconnecting, line)
        if "immediate exit requested" in lower or "signal 15" in lower:
            return FFmpegEvent(FFmpegEventType.clean_exit, line)
        # FFmpeg prints the new segment filename on segment rotation
        if "opening" in lower and ".mp4" in lower:
            return FFmpegEvent(FFmpegEventType.segment_created, line)
        return None


# ── Command builders ──────────────────────────────────────────────────────────

def build_continuous_command(
    rtsp_url: str,
    output_dir: str,
    camera_id: str,
    osd_camera_name: str | None = None,
    osd_clock: bool = False,
) -> list[str]:
    """10-minute segments. Copy stream when OSD is off; transcode with drawtext when on."""
    osd_filters = []
    if osd_camera_name:
        safe = osd_camera_name.replace("\\", "\\\\").replace("'", "\\'").replace(":", "\\:")
        osd_filters.append(
            f"drawtext=text='{safe}':fontcolor=white:fontsize=16"
            f":x=10:y=10:box=1:boxcolor=black@0.5:boxborderw=3"
        )
    if osd_clock:
        osd_filters.append(
            "drawtext=text='%{localtime}':fontcolor=white:fontsize=16"
            ":x=10:y=34:box=1:boxcolor=black@0.5:boxborderw=3"
        )

    cmd = [
        "ffmpeg",
        "-loglevel", "verbose",  # needs verbose to see "Opening '...' for writing" on segment rotation
        "-rtsp_transport", "tcp",
        "-i", rtsp_url,
    ]
    if osd_filters:
        cmd += ["-vf", ",".join(osd_filters), "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23"]
    else:
        cmd += ["-c:v", "copy"]
    cmd += [
        "-an",
        "-f", "segment",
        "-segment_time", "600",
        "-segment_format", "mp4",
        "-segment_atclocktime", "1",
        "-strftime", "1",
        "-reset_timestamps", "1",
        f"{output_dir}/%H-%M-%S_continuous.mp4",
    ]
    return cmd


def build_hls_command(rtsp_url: str, hls_dir: str, camera_id: str) -> list[str]:
    """Re-encode sub stream to HLS for live view."""
    return [
        "ffmpeg",
        "-loglevel", "warning",
        "-rtsp_transport", "tcp",
        "-i", rtsp_url,
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-tune", "zerolatency",
        "-crf", "28",
        "-c:a", "aac",
        "-b:a", "64k",
        "-f", "hls",
        "-hls_time", "2",
        "-hls_list_size", "10",
        "-hls_flags", "delete_segments",
        "-hls_segment_filename", f"{hls_dir}/%03d.ts",
        f"{hls_dir}/index.m3u8",
    ]


def build_export_command(
    input_files: list[str],
    output_path: str,
    watermark_text: str | None,
    crf: int = 18,
) -> list[str]:
    """Concat segments and optionally burn watermark."""
    # Build concat input
    concat_input = "|".join(input_files)

    vf_filters = []
    if watermark_text:
        safe_text = watermark_text.replace("'", "\\'").replace(":", "\\:")
        vf_filters.append(
            f"drawtext=text='{safe_text}':fontcolor=white:fontsize=18:"
            f"x=10:y=10:box=1:boxcolor=black@0.4"
        )

    cmd = [
        "ffmpeg",
        "-loglevel", "warning",
        "-i", f"concat:{concat_input}",
    ]
    if vf_filters:
        cmd += ["-vf", ",".join(vf_filters)]
    cmd += [
        "-c:v", "libx264",
        "-crf", str(crf),
        "-c:a", "copy",
        "-movflags", "+faststart",
        "-y",
        output_path,
    ]
    return cmd


def build_thumbnail_command(video_path: str, output_path: str) -> list[str]:
    """Extract the first keyframe as a JPEG thumbnail."""
    return [
        "ffmpeg",
        "-loglevel", "warning",
        "-ss", "1",
        "-i", video_path,
        "-vframes", "1",
        "-q:v", "2",
        "-y",
        output_path,
    ]
