"""Filter YOLO detections by zone membership using Shapely point-in-polygon."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from shapely.geometry import Point, Polygon

# COCO classes of interest per SPEC 9.6
DETECT_CLASSES: dict[int, str] = {
    0: "person",
    1: "bicycle",
    2: "car",
    3: "motorcycle",
    5: "bus",
    7: "truck",
}


@dataclass
class Zone:
    name: str
    polygon: list[list[float]]   # [[x,y], ...] normalized 0.0-1.0
    restricted: bool = False
    enabled: bool = True
    working_hours_start: Optional[str] = None  # "HH:MM"
    working_hours_end: Optional[str] = None    # "HH:MM"
    dwell_threshold_s: int = 30
    is_privacy_mask: bool = False


@dataclass
class ZoneDetection:
    class_id: int
    class_name: str
    confidence: float
    bbox: list[float]            # [x1, y1, x2, y2] normalized
    track_id: Optional[int]
    zone_name: str
    zone: Zone


class ZoneFilter:
    def __init__(self, zones: list[Zone]) -> None:
        self.zones = zones
        self._polys: dict[str, Polygon] = {}
        for z in zones:
            if z.polygon and len(z.polygon) >= 3:
                self._polys[z.name] = Polygon(z.polygon)

    # Full-frame fallback zone used when no detection zones are configured
    _FULL_FRAME_ZONE = Zone(
        name="Full Frame",
        polygon=[[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]],
        restricted=False,
        enabled=True,
    )

    def filter(self, detections, frame_shape: tuple[int, int]) -> list[ZoneDetection]:
        """
        detections: sv.Detections with xyxy in pixel coordinates
        frame_shape: (height, width)
        Returns one ZoneDetection per (detection × matching zone) pair.
        When no detection zones are configured, the entire frame is used.
        """
        h, w = frame_shape
        results: list[ZoneDetection] = []

        if len(detections) == 0:
            return results

        privacy_polys = [
            Polygon(z.polygon)
            for z in self.zones
            if z.is_privacy_mask and len(z.polygon) >= 3
        ]

        active_zones = [z for z in self.zones if z.enabled and not z.is_privacy_mask]
        use_full_frame = len(active_zones) == 0
        if use_full_frame:
            active_zones = [self._FULL_FRAME_ZONE]
            full_frame_poly = Polygon(self._FULL_FRAME_ZONE.polygon)
            polys = {"Full Frame": full_frame_poly}
        else:
            polys = self._polys

        for i in range(len(detections)):
            class_id = int(detections.class_id[i]) if detections.class_id is not None else -1
            if class_id not in DETECT_CLASSES:
                continue

            x1, y1, x2, y2 = detections.xyxy[i]
            bx1, by1 = x1 / w, y1 / h
            bx2, by2 = x2 / w, y2 / h
            cx, cy = (bx1 + bx2) / 2, (by1 + by2) / 2
            centroid = Point(cx, cy)

            # Skip if centroid falls inside any privacy mask
            if any(p.contains(centroid) for p in privacy_polys):
                continue

            conf = float(detections.confidence[i]) if detections.confidence is not None else 0.0
            tid = None
            if detections.tracker_id is not None and i < len(detections.tracker_id):
                raw_tid = detections.tracker_id[i]
                if raw_tid is not None:
                    tid = int(raw_tid)

            for zone in active_zones:
                poly = polys.get(zone.name)
                if poly is None:
                    continue
                if poly.contains(centroid):
                    results.append(ZoneDetection(
                        class_id=class_id,
                        class_name=DETECT_CLASSES[class_id],
                        confidence=conf,
                        bbox=[bx1, by1, bx2, by2],
                        track_id=tid,
                        zone_name=zone.name,
                        zone=zone,
                    ))

        return results
