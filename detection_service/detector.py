"""
DetectionWorker — one thread per camera.
Samples RTSP frames at SAMPLE_FPS, runs YOLO inference, applies zone filter
and rules engine, dispatches alert payloads via RedisPublisher.
"""
from __future__ import annotations

import base64
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
import structlog

logger = structlog.get_logger(__name__)

SAMPLE_FPS = 2
_MODEL_PATH = "/models/yolov8n.pt"
_DETECT_CLASSES = [0, 1, 2, 3, 5, 7]  # person, bicycle, car, motorcycle, bus, truck
_MAX_RETRIES = 20
_RETRY_WAIT_S = 10.0
_LONG_SLEEP_S = 300.0
_BASELINE_FRAMES = 10

# Module-level singleton — loaded once, thread-safe for concurrent predict() calls
_model = None
_model_lock = threading.Lock()


def _get_model():
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                from ultralytics import YOLO
                logger.info("loading_yolo_model", path=_MODEL_PATH)
                _model = YOLO(_MODEL_PATH)
    return _model


class DetectionWorker(threading.Thread):
    SAMPLE_INTERVAL = 1.0 / SAMPLE_FPS

    def __init__(
        self,
        camera_id: str,
        rtsp_url: str,
        zones_ref: dict,
        zones_lock: threading.RLock,
        publisher,
        stop_event: threading.Event,
        alert_clips_path: str = "/data/alerts",
        min_confidence: float = 0.5,
    ) -> None:
        super().__init__(daemon=True, name=f"worker-{camera_id}")
        self._camera_id = camera_id
        self._rtsp_url = rtsp_url
        self._zones_ref = zones_ref
        self._zones_lock = zones_lock
        self._publisher = publisher
        self._stop_event = stop_event
        self._clips_path = Path(alert_clips_path)
        self._min_conf = min_confidence
        self._running = False
        self._retries = 0

    def run(self) -> None:
        from frame_buffer import FrameBuffer
        from tracker import ObjectTracker
        from zone_filter import ZoneFilter, Zone
        from rules_engine import RulesEngine

        import supervision as sv

        self._running = True
        buf = FrameBuffer(sample_fps=SAMPLE_FPS, buffer_seconds=30)
        tracker = ObjectTracker()
        rules = RulesEngine(camera_id=self._camera_id)
        model = _get_model()
        baseline_frame_count = 0
        baseline_set = False

        while not self._stop_event.is_set():
            cap = self._open_capture()
            if cap is None:
                break

            logger.info("detector_started", camera_id=self._camera_id)
            self._retries = 0
            last_sample = 0.0

            try:
                while not self._stop_event.is_set():
                    ret, frame = cap.read()
                    if not ret or frame is None:
                        logger.warning("detector_frame_read_failed",
                                       camera_id=self._camera_id)
                        break

                    now = time.monotonic()
                    if now - last_sample < self.SAMPLE_INTERVAL:
                        continue
                    last_sample = now

                    ts = datetime.now(timezone.utc)
                    buf.append(ts, frame)

                    # Establish baseline from the first N frames (no alerts yet)
                    if not baseline_set:
                        baseline_frame_count += 1
                        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                        hist = cv2.calcHist([gray], [0], None, [256], [0, 256])
                        cv2.normalize(hist, hist)
                        rules.set_baseline(hist)
                        if baseline_frame_count >= _BASELINE_FRAMES:
                            baseline_set = True
                            logger.info("baseline_established",
                                        camera_id=self._camera_id)
                        continue

                    # Load current zones (hot-reloadable)
                    with self._zones_lock:
                        raw_zones = list(self._zones_ref.get(self._camera_id, []))
                    zones = [Zone(**z) for z in raw_zones if z.get("enabled", True)]

                    # YOLO inference
                    results = model.predict(
                        frame,
                        conf=self._min_conf,
                        classes=_DETECT_CLASSES,
                        verbose=False,
                        iou=0.45,
                    )
                    if not results or len(results[0].boxes) == 0:
                        continue

                    detections = sv.Detections.from_ultralytics(results[0])
                    tracked = tracker.update(detections)

                    zf = ZoneFilter(zones)
                    h, w = frame.shape[:2]
                    zone_dets = zf.filter(tracked, frame_shape=(h, w))

                    alerts = rules.evaluate(zone_dets, frame, current_time=ts)

                    # Rule 5 — DWELL_TIME (needs tracker state)
                    for det in zone_dets:
                        if det.track_id is not None:
                            tracker.record_zone_entry(det.track_id, det.zone_name)
                            dwell = tracker.get_dwell_time(det.track_id, det.zone_name)
                            dwell_alert = rules.evaluate_dwell(det, dwell,
                                                               current_time=ts)
                            if dwell_alert:
                                alerts.append(dwell_alert)

                    for alert in alerts:
                        self._dispatch_alert(alert, frame, buf)

            except Exception:
                logger.exception("detector_error", camera_id=self._camera_id)
            finally:
                cap.release()

        self._running = False
        logger.info("detector_stopped", camera_id=self._camera_id)

    def _open_capture(self) -> Optional[cv2.VideoCapture]:
        while not self._stop_event.is_set():
            if self._retries >= _MAX_RETRIES:
                logger.error("detector_max_retries_exceeded",
                             camera_id=self._camera_id)
                self._stop_event.wait(timeout=_LONG_SLEEP_S)
                self._retries = 0
                continue

            os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS",
                                  "rtsp_transport;tcp")
            cap = cv2.VideoCapture(self._rtsp_url, cv2.CAP_FFMPEG)
            if cap.isOpened():
                return cap

            cap.release()
            self._retries += 1
            logger.warning("detector_connect_failed",
                           camera_id=self._camera_id,
                           retry=self._retries,
                           max_retries=_MAX_RETRIES)
            self._stop_event.wait(timeout=_RETRY_WAIT_S)

        return None

    def _dispatch_alert(self, alert, frame: np.ndarray, buf) -> None:
        frame_path: Optional[str] = None
        try:
            frame_dir = self._clips_path / self._camera_id
            frame_dir.mkdir(parents=True, exist_ok=True)
            fname = f"{alert.triggered_at.strftime('%Y%m%d_%H%M%S%f')}.jpg"
            frame_file = frame_dir / fname
            _, jpg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
            frame_file.write_bytes(jpg.tobytes())
            frame_path = str(frame_file)
        except Exception:
            logger.warning("alert_frame_save_failed", camera_id=self._camera_id)

        # Collect pre-event frames for context logging
        pre_frames = buf.get_frames_since(
            alert.triggered_at - timedelta(seconds=30)
        )
        logger.info("alert_context_frames",
                    camera_id=self._camera_id,
                    count=len(pre_frames),
                    rule=alert.rule_triggered)

        frame_b64: Optional[str] = None
        if alert.frame is not None:
            try:
                _, jpg = cv2.imencode(".jpg", alert.frame,
                                      [cv2.IMWRITE_JPEG_QUALITY, 80])
                frame_b64 = base64.b64encode(jpg.tobytes()).decode()
            except Exception:
                pass

        self._publisher.publish({
            "camera_id": self._camera_id,
            "detection_type": alert.detection_type,
            "zone_name": alert.zone_name,
            "confidence": alert.confidence,
            "severity": alert.severity,
            "rule_triggered": alert.rule_triggered,
            "bbox": (
                {"x1": alert.bbox[0], "y1": alert.bbox[1],
                 "x2": alert.bbox[2], "y2": alert.bbox[3]}
                if alert.bbox else None
            ),
            "track_id": alert.track_id,
            "triggered_at": alert.triggered_at.isoformat(),
            "frame_path": frame_path,
            "frame_b64": frame_b64,
        })

    @property
    def is_running(self) -> bool:
        return self._running
