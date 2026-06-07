"""Ring buffer of raw frames for pre-event alert context (last 30 seconds)."""
from __future__ import annotations

import threading
from collections import deque
from datetime import datetime
from typing import NamedTuple

import cv2
import numpy as np


class FrameRecord(NamedTuple):
    timestamp: datetime
    frame: np.ndarray


class FrameBuffer:
    def __init__(self, sample_fps: int = 2, buffer_seconds: int = 30) -> None:
        maxlen = max(1, sample_fps * buffer_seconds)
        self._buffer: deque[FrameRecord] = deque(maxlen=maxlen)
        self._lock = threading.Lock()

    def append(self, timestamp: datetime, frame: np.ndarray) -> None:
        with self._lock:
            self._buffer.append(FrameRecord(timestamp=timestamp, frame=frame.copy()))

    def get_frames_since(self, dt: datetime) -> list[FrameRecord]:
        with self._lock:
            return [r for r in self._buffer if r.timestamp >= dt]

    def to_jpeg(self, frame: np.ndarray, quality: int = 85) -> bytes:
        """Encode a BGR numpy frame to JPEG bytes (lazy — not pre-stored)."""
        _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
        return buf.tobytes()

    def __len__(self) -> int:
        with self._lock:
            return len(self._buffer)
