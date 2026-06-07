"""
Rules engine — evaluates 5 detection rules in priority order.
Returns AlertPayload list for the current frame's zone detections.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import cv2
import numpy as np
import structlog

logger = structlog.get_logger(__name__)

_VEHICLE_CLASSES = {"car", "truck", "motorcycle", "bus", "bicycle"}
_PERSON_CLASS = "person"
_TAMPERING_CORREL_THRESHOLD = 0.4   # histogram correlation below this → tampering


@dataclass
class AlertPayload:
    camera_id: str
    detection_type: str
    zone_name: Optional[str]
    confidence: float
    severity: str
    rule_triggered: str
    bbox: Optional[list[float]]
    track_id: Optional[int]
    triggered_at: datetime
    frame: Optional[np.ndarray] = field(default=None, repr=False)


class RulesEngine:
    COOLDOWN_S: float = 60.0

    def __init__(
        self,
        camera_id: str,
        baseline_histogram: Optional[np.ndarray] = None,
    ) -> None:
        self._camera_id = camera_id
        self._baseline_hist = baseline_histogram
        # _cooldowns[(rule, zone_name, track_id)] = monotonic time of last alert
        self._cooldowns: dict[tuple, float] = {}

    def set_baseline(self, histogram: np.ndarray) -> None:
        self._baseline_hist = histogram

    def evaluate(
        self,
        zone_detections: list,
        frame: np.ndarray,
        current_time: Optional[datetime] = None,
    ) -> list[AlertPayload]:
        if current_time is None:
            current_time = datetime.now(timezone.utc)

        alerts: list[AlertPayload] = []

        # Rule 1 — TAMPERING (highest priority; short-circuits other rules)
        if self._baseline_hist is not None:
            t_alert = self._check_tampering(frame, current_time)
            if t_alert:
                return [t_alert]

        for det in zone_detections:
            zone = det.zone

            # Rule 2 — RESTRICTED_ZONE_ANY_TIME
            if zone.restricted:
                key = ("RESTRICTED_ZONE", det.zone_name, det.track_id)
                if not self._in_cooldown(key):
                    self._set_cooldown(key)
                    alerts.append(AlertPayload(
                        camera_id=self._camera_id,
                        detection_type=det.class_name,
                        zone_name=det.zone_name,
                        confidence=det.confidence,
                        severity="high",
                        rule_triggered="RESTRICTED_ZONE_ANY_TIME",
                        bbox=det.bbox,
                        track_id=det.track_id,
                        triggered_at=current_time,
                        frame=frame,
                    ))
                continue  # restricted zone rules take precedence

            # Rule 3 — AFTER_HOURS_PERSON
            if det.class_name == _PERSON_CLASS:
                if not self._within_working_hours(zone, current_time):
                    key = ("AFTER_HOURS_PERSON", det.zone_name, det.track_id)
                    if not self._in_cooldown(key):
                        self._set_cooldown(key)
                        alerts.append(AlertPayload(
                            camera_id=self._camera_id,
                            detection_type="person",
                            zone_name=det.zone_name,
                            confidence=det.confidence,
                            severity="high",
                            rule_triggered="AFTER_HOURS_PERSON",
                            bbox=det.bbox,
                            track_id=det.track_id,
                            triggered_at=current_time,
                            frame=frame,
                        ))
                continue

            # Rule 4 — AFTER_HOURS_VEHICLE
            if det.class_name in _VEHICLE_CLASSES:
                if not self._within_working_hours(zone, current_time):
                    key = ("AFTER_HOURS_VEHICLE", det.zone_name, det.track_id)
                    if not self._in_cooldown(key):
                        self._set_cooldown(key)
                        alerts.append(AlertPayload(
                            camera_id=self._camera_id,
                            detection_type=det.class_name,
                            zone_name=det.zone_name,
                            confidence=det.confidence,
                            severity="medium",
                            rule_triggered="AFTER_HOURS_VEHICLE",
                            bbox=det.bbox,
                            track_id=det.track_id,
                            triggered_at=current_time,
                            frame=frame,
                        ))

        return alerts

    def evaluate_dwell(
        self,
        det,
        dwell_time: float,
        current_time: Optional[datetime] = None,
    ) -> Optional[AlertPayload]:
        """Rule 5 — DWELL_TIME: called separately with the dwell duration."""
        if current_time is None:
            current_time = datetime.now(timezone.utc)
        zone = det.zone
        if det.track_id is None or zone.dwell_threshold_s <= 0:
            return None
        if dwell_time < zone.dwell_threshold_s:
            return None
        key = ("DWELL_TIME", det.zone_name, det.track_id)
        if self._in_cooldown(key):
            return None
        self._set_cooldown(key)
        return AlertPayload(
            camera_id=self._camera_id,
            detection_type=det.class_name,
            zone_name=det.zone_name,
            confidence=det.confidence,
            severity="medium",
            rule_triggered="DWELL_TIME",
            bbox=det.bbox,
            track_id=det.track_id,
            triggered_at=current_time,
        )

    # ── helpers ────────────────────────────────────────────────────────────────

    def _check_tampering(
        self,
        frame: np.ndarray,
        current_time: datetime,
    ) -> Optional[AlertPayload]:
        try:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            hist = cv2.calcHist([gray], [0], None, [256], [0, 256])
            cv2.normalize(hist, hist)
            correl = cv2.compareHist(
                self._baseline_hist, hist, cv2.HISTCMP_CORREL
            )
            if correl < _TAMPERING_CORREL_THRESHOLD:
                key = ("TAMPERING", None, None)
                if not self._in_cooldown(key):
                    self._set_cooldown(key)
                    return AlertPayload(
                        camera_id=self._camera_id,
                        detection_type="tampering",
                        zone_name=None,
                        confidence=float(max(0.0, 1.0 - correl)),
                        severity="critical",
                        rule_triggered="TAMPERING",
                        bbox=None,
                        track_id=None,
                        triggered_at=current_time,
                        frame=frame,
                    )
        except Exception:
            logger.warning("tampering_check_error", camera_id=self._camera_id)
        return None

    def _within_working_hours(self, zone, current_time: datetime) -> bool:
        if not zone.working_hours_start or not zone.working_hours_end:
            return False  # no schedule defined → always "after hours"
        from datetime import time as dt_time
        sh, sm = zone.working_hours_start.split(":")
        eh, em = zone.working_hours_end.split(":")
        start = dt_time(int(sh), int(sm))
        end = dt_time(int(eh), int(em))
        current = current_time.time()
        if start <= end:
            return start <= current <= end
        # Crosses midnight
        return current >= start or current <= end

    def _in_cooldown(self, key: tuple) -> bool:
        last = self._cooldowns.get(key)
        return last is not None and time.monotonic() - last < self.COOLDOWN_S

    def _set_cooldown(self, key: tuple) -> None:
        self._cooldowns[key] = time.monotonic()
