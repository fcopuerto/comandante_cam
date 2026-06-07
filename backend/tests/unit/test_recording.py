"""Unit tests for recording engine (FFmpegProcess, command builders, purge logic)."""
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.utils.ffmpeg import (
    FFmpegEvent,
    FFmpegEventType,
    FFmpegProcess,
    build_continuous_command,
    build_export_command,
    build_hls_command,
    build_thumbnail_command,
)


# ── FFmpegProcess ─────────────────────────────────────────────────────────────

def test_ffmpeg_process_is_running_false_when_not_started():
    proc = FFmpegProcess("cam-1", ["ffmpeg", "-version"])
    assert proc.is_running() is False


def test_ffmpeg_process_start_sets_proc():
    mock_popen = MagicMock()
    mock_popen.pid = 12345
    mock_popen.poll.return_value = None  # still running

    with patch("subprocess.Popen", return_value=mock_popen):
        proc = FFmpegProcess("cam-1", ["ffmpeg", "-version"])
        proc.start()
        assert proc.is_running() is True


def test_ffmpeg_process_stop_sends_sigterm():
    mock_popen = MagicMock()
    mock_popen.pid = 12345
    mock_popen.poll.side_effect = [None, None, 0]  # running → running → exited
    mock_popen.wait.return_value = 0

    with patch("subprocess.Popen", return_value=mock_popen):
        proc = FFmpegProcess("cam-1", ["ffmpeg", "-version"])
        proc.start()
        proc.stop()

    import signal
    mock_popen.send_signal.assert_called_once_with(signal.SIGTERM)


def test_ffmpeg_process_stop_kills_on_timeout():
    mock_popen = MagicMock()
    mock_popen.pid = 12345
    mock_popen.poll.return_value = None
    mock_popen.wait.side_effect = [subprocess.TimeoutExpired(cmd=[], timeout=5), None]

    with patch("subprocess.Popen", return_value=mock_popen):
        proc = FFmpegProcess("cam-1", ["ffmpeg"])
        proc.start()
        proc.stop(timeout=0.01)

    mock_popen.kill.assert_called_once()


# ── parse_stderr ──────────────────────────────────────────────────────────────

def test_parse_stderr_connection_refused():
    proc = FFmpegProcess("cam-1", [])
    evt = proc.parse_stderr("tcp://192.168.1.10:554: Connection refused")
    assert evt is not None
    assert evt.type == FFmpegEventType.connection_refused


def test_parse_stderr_invalid_data():
    proc = FFmpegProcess("cam-1", [])
    evt = proc.parse_stderr("Invalid data found when processing input")
    assert evt is not None
    assert evt.type == FFmpegEventType.corrupt_stream


def test_parse_stderr_reconnecting():
    proc = FFmpegProcess("cam-1", [])
    evt = proc.parse_stderr("Reconnecting at offset 0")
    assert evt is not None
    assert evt.type == FFmpegEventType.reconnecting


def test_parse_stderr_segment_created():
    proc = FFmpegProcess("cam-1", [])
    evt = proc.parse_stderr("Opening '/data/recordings/cam-1/2024-06-15/10-00-00_continuous.mp4' for writing")
    assert evt is not None
    assert evt.type == FFmpegEventType.segment_created


def test_parse_stderr_clean_exit():
    proc = FFmpegProcess("cam-1", [])
    evt = proc.parse_stderr("Immediate exit requested")
    assert evt is not None
    assert evt.type == FFmpegEventType.clean_exit


def test_parse_stderr_unrelated_line_returns_none():
    proc = FFmpegProcess("cam-1", [])
    assert proc.parse_stderr("frame=  100 fps= 25 q=-1.0 size=    512kB time=00:00:04.00") is None


# ── Command builders ──────────────────────────────────────────────────────────

def test_build_continuous_command_contains_segment_format():
    cmd = build_continuous_command("rtsp://192.168.1.10:554/stream", "/data/recordings/cam-1/2024-06-15", "cam-1")
    assert "ffmpeg" in cmd
    assert "-f" in cmd
    assert "segment" in cmd
    assert "-segment_time" in cmd
    assert "600" in cmd
    assert "-c:v" in cmd
    assert "copy" in cmd
    assert "-an" in cmd


def test_build_continuous_command_rtsp_transport_tcp():
    cmd = build_continuous_command("rtsp://192.168.1.10:554/stream", "/tmp", "cam-1")
    assert "-rtsp_transport" in cmd
    assert "tcp" in cmd


def test_build_hls_command_contains_hls_format():
    cmd = build_hls_command("rtsp://192.168.1.10:554/sub", "/data/hls/cam-1", "cam-1")
    assert "-f" in cmd
    assert "hls" in cmd
    assert "-hls_time" in cmd
    assert "-hls_list_size" in cmd
    assert "10" in cmd
    assert "index.m3u8" in cmd[-1]


def test_build_export_command_with_watermark():
    cmd = build_export_command(
        ["/data/recordings/cam-1/seg1.mp4", "/data/recordings/cam-1/seg2.mp4"],
        "/data/exports/job-1/export.mp4",
        watermark_text="Exported by Admin",
    )
    assert "ffmpeg" in cmd
    assert "-vf" in cmd
    # watermark text present somewhere in the command
    full = " ".join(cmd)
    assert "drawtext" in full
    assert "Exported by Admin" in full


def test_build_export_command_without_watermark():
    cmd = build_export_command(
        ["/data/recordings/cam-1/seg1.mp4"],
        "/data/exports/job-1/export.mp4",
        watermark_text=None,
    )
    assert "-vf" not in cmd


def test_build_export_command_concat_input():
    cmd = build_export_command(
        ["/seg1.mp4", "/seg2.mp4"],
        "/out.mp4",
        watermark_text=None,
    )
    # Verify concat input is passed
    idx = cmd.index("-i")
    concat_arg = cmd[idx + 1]
    assert "concat:" in concat_arg
    assert "/seg1.mp4" in concat_arg
    assert "/seg2.mp4" in concat_arg


def test_build_thumbnail_command():
    cmd = build_thumbnail_command("/data/seg.mp4", "/data/seg.jpg")
    assert "ffmpeg" in cmd
    assert "-ss" in cmd
    assert "-vframes" in cmd
    assert "1" in cmd
    assert "/data/seg.jpg" in cmd


# ── Purge logic ───────────────────────────────────────────────────────────────

def test_purge_deletes_file_on_disk(tmp_path):
    """Purge should delete the video file from disk."""
    video = tmp_path / "seg.mp4"
    video.write_bytes(b"fake video data")
    thumb = tmp_path / "seg.jpg"
    thumb.write_bytes(b"fake jpeg")

    from app.workers.purge import _delete_segment

    seg = MagicMock()
    seg.file_path = str(video)
    seg.thumbnail_path = str(thumb)

    mock_db = MagicMock()
    _delete_segment(mock_db, seg)

    assert not video.exists()
    assert not thumb.exists()
    mock_db.delete.assert_called_once_with(seg)


def test_purge_handles_missing_file_gracefully(tmp_path):
    """Purge should not raise if the file is already gone."""
    from app.workers.purge import _delete_segment

    seg = MagicMock()
    seg.file_path = str(tmp_path / "nonexistent.mp4")
    seg.thumbnail_path = None

    mock_db = MagicMock()
    _delete_segment(mock_db, seg)  # should not raise

    mock_db.delete.assert_called_once_with(seg)


def test_export_command_no_colon_in_watermark():
    """Colons in watermark text must be escaped for FFmpeg drawtext."""
    cmd = build_export_command(
        ["/seg.mp4"],
        "/out.mp4",
        watermark_text="Camera: North Entrance",
    )
    full = " ".join(cmd)
    # Colon should be escaped as \: in the drawtext filter
    assert "\\:" in full


def test_stop_recording_task_removes_from_running(tmp_path):
    """stop_recording should remove camera from RUNNING_PROCESSES."""
    from app.workers import recording as rec_module

    mock_proc = MagicMock()
    mock_proc.is_running.return_value = True
    rec_module.RUNNING_PROCESSES["test-cam"] = mock_proc

    with patch("app.workers.recording._get_sync_session") as mock_session_fn:
        mock_session = MagicMock()
        mock_session_fn.return_value = mock_session
        mock_session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_session.return_value.__exit__ = MagicMock(return_value=False)
        mock_session.get.return_value = None  # Camera not found is fine

        # Call the underlying function directly (bypass Celery)
        from unittest.mock import patch as p
        with p("app.workers.recording._db") as mock_db_ctx:
            mock_db_obj = MagicMock()
            mock_db_ctx.return_value.__enter__ = MagicMock(return_value=mock_db_obj)
            mock_db_ctx.return_value.__exit__ = MagicMock(return_value=False)
            mock_db_obj.get.return_value = None

            from app.workers.recording import stop_recording
            stop_recording.run("test-cam")

    assert "test-cam" not in rec_module.RUNNING_PROCESSES
    mock_proc.stop.assert_called_once()
