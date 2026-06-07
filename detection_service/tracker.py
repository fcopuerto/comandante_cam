"""ByteTrack wrapper with dwell-time tracking and stale-track expiry."""
from __future__ import annotations

import threading
import time
from typing import Optional

import numpy as np
import supervision as sv

SAMPLE_FPS = 2
_EXPIRE_S = 5.0


class ObjectTracker:
    def __init__(self) -> None:
        self._tracker = sv.ByteTrack(
            track_activation_threshold=0.25,
            lost_track_buffer=max(1, int(_EXPIRE_S * SAMPLE_FPS)),
            minimum_matching_threshold=0.8,
            frame_rate=SAMPLE_FPS,
        )
        self._lock = threading.Lock()
        # zone_entry[track_id][zone_name] = monotonic timestamp of first entry
        self._zone_entry: dict[int, dict[str, float]] = {}
        # last_seen[track_id] = monotonic timestamp of most recent detection
        self._last_seen: dict[int, float] = {}

    def update(self, detections: sv.Detections) -> sv.Detections:
        with self._lock:
            self._expire_stale()
            if len(detections) == 0:
                return detections
            tracked = self._tracker.update_with_detections(detections)
            now = time.monotonic()
            if tracked.tracker_id is not None:
                for tid in tracked.tracker_id:
                    if tid is not None:
                        self._last_seen[int(tid)] = now
            return tracked

    def record_zone_entry(self, track_id: int, zone_name: str) -> None:
        """Record when a track_id first enters a zone (idempotent)."""
        with self._lock:
            if track_id not in self._zone_entry:
                self._zone_entry[track_id] = {}
            if zone_name not in self._zone_entry[track_id]:
                self._zone_entry[track_id][zone_name] = time.monotonic()
            # Always update last_seen on zone entry
            self._last_seen[track_id] = time.monotonic()

    def get_dwell_time(self, track_id: int, zone_name: str) -> float:
        """Return seconds since track_id first entered zone_name, or 0.0."""
        with self._lock:
            entry = self._zone_entry.get(track_id, {}).get(zone_name)
            if entry is None:
                return 0.0
            return time.monotonic() - entry

    def _expire_stale(self) -> None:
        now = time.monotonic()
        expired = [
            tid for tid, ts in self._last_seen.items()
            if now - ts > _EXPIRE_S
        ]
        for tid in expired:
            del self._last_seen[tid]
            self._zone_entry.pop(tid, None)
