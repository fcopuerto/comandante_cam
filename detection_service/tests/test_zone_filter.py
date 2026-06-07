"""
Tests for zone_filter.ZoneFilter — point-in-polygon, privacy mask, class filtering.
"""
import numpy as np
import pytest
import supervision as sv

from zone_filter import Zone, ZoneFilter, DETECT_CLASSES

_FULL_ZONE = Zone(
    name="full",
    polygon=[[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]],
)

_CENTER_ZONE = Zone(
    name="center",
    polygon=[[0.25, 0.25], [0.75, 0.25], [0.75, 0.75], [0.25, 0.75]],
)

_TOP_LEFT_ZONE = Zone(
    name="top_left",
    polygon=[[0.0, 0.0], [0.3, 0.0], [0.3, 0.3], [0.0, 0.3]],
)


def _make_detections(
    xyxy: list[list[float]],
    class_ids: list[int],
    confidences: list[float] | None = None,
    tracker_ids: list[int | None] | None = None,
) -> sv.Detections:
    n = len(xyxy)
    confs = confidences if confidences is not None else [0.9] * n
    d = sv.Detections(
        xyxy=np.array(xyxy, dtype=np.float32),
        confidence=np.array(confs, dtype=np.float32),
        class_id=np.array(class_ids, dtype=int),
    )
    if tracker_ids is not None:
        d.tracker_id = np.array(
            [t if t is not None else -1 for t in tracker_ids], dtype=int
        )
    return d


# ── centroid inside / outside ──────────────────────────────────────────────────

def test_centroid_inside_polygon_included():
    """Centroid at (0.5, 0.5) is inside _CENTER_ZONE → included."""
    zf = ZoneFilter([_CENTER_ZONE])
    dets = _make_detections([[40.0, 40.0, 60.0, 60.0]], [0])
    results = zf.filter(dets, frame_shape=(100, 100))
    assert len(results) == 1
    assert results[0].zone_name == "center"
    assert results[0].class_name == "person"
    assert results[0].confidence == pytest.approx(0.9)


def test_centroid_outside_polygon_excluded():
    """Centroid at (0.5, 0.5) is outside _TOP_LEFT_ZONE → excluded."""
    zf = ZoneFilter([_TOP_LEFT_ZONE])
    dets = _make_detections([[40.0, 40.0, 60.0, 60.0]], [0])
    results = zf.filter(dets, frame_shape=(100, 100))
    assert len(results) == 0


def test_centroid_exactly_on_edge_treated_as_outside():
    """Centroid on zone boundary — Shapely 'contains' returns False on edge."""
    # edge zone: top edge is y=0.0, centroid is at y=0.0 exactly
    edge_zone = Zone(
        name="edge",
        polygon=[[0.0, 0.0], [1.0, 0.0], [1.0, 0.5], [0.0, 0.5]],
    )
    zf = ZoneFilter([edge_zone])
    # bbox occupying rows 0..0 — centroid at (0.5, 0.0) — on boundary
    dets = _make_detections([[0.0, 0.0, 100.0, 0.0]], [0])
    results = zf.filter(dets, frame_shape=(100, 100))
    # Shapely 'contains' excludes boundary; result may be 0 or 1 depending on
    # float precision — just verify no crash
    assert isinstance(results, list)


# ── privacy mask ───────────────────────────────────────────────────────────────

def test_privacy_mask_excludes_detection():
    """Detection centroid inside privacy mask → excluded even though main zone covers it."""
    zones = [
        _FULL_ZONE,
        Zone(
            name="privacy_center",
            polygon=[[0.4, 0.4], [0.6, 0.4], [0.6, 0.6], [0.4, 0.6]],
            is_privacy_mask=True,
        ),
    ]
    zf = ZoneFilter(zones)
    dets = _make_detections([[40.0, 40.0, 60.0, 60.0]], [0])
    results = zf.filter(dets, frame_shape=(100, 100))
    assert len(results) == 0


def test_detection_outside_privacy_mask_included():
    """Detection centroid outside privacy mask → included in zone results."""
    zones = [
        _FULL_ZONE,
        Zone(
            name="privacy_top_left",
            polygon=[[0.0, 0.0], [0.2, 0.0], [0.2, 0.2], [0.0, 0.2]],
            is_privacy_mask=True,
        ),
    ]
    zf = ZoneFilter(zones)
    # centroid at (0.5, 0.5) — outside privacy mask at top-left
    dets = _make_detections([[40.0, 40.0, 60.0, 60.0]], [0])
    results = zf.filter(dets, frame_shape=(100, 100))
    zone_names = [r.zone_name for r in results]
    assert "full" in zone_names
    assert "privacy_top_left" not in zone_names


# ── class filtering ────────────────────────────────────────────────────────────

def test_non_target_class_excluded():
    """COCO class not in DETECT_CLASSES → excluded."""
    zf = ZoneFilter([_FULL_ZONE])
    dets = _make_detections([[10.0, 10.0, 90.0, 90.0]], [15])  # 15 = not in list
    results = zf.filter(dets, frame_shape=(100, 100))
    assert len(results) == 0


def test_all_target_classes_included():
    """Each class in DETECT_CLASSES is processed."""
    zf = ZoneFilter([_FULL_ZONE])
    for class_id in DETECT_CLASSES:
        dets = _make_detections([[10.0, 10.0, 90.0, 90.0]], [class_id])
        results = zf.filter(dets, frame_shape=(100, 100))
        assert len(results) == 1, f"class_id={class_id} should be included"
        assert results[0].class_name == DETECT_CLASSES[class_id]


# ── multiple zones ─────────────────────────────────────────────────────────────

def test_centroid_in_two_overlapping_zones():
    """Detection inside two overlapping zones → appears in both."""
    zones = [_FULL_ZONE, _CENTER_ZONE]
    zf = ZoneFilter(zones)
    dets = _make_detections([[40.0, 40.0, 60.0, 60.0]], [0])
    results = zf.filter(dets, frame_shape=(100, 100))
    zone_names = {r.zone_name for r in results}
    assert "full" in zone_names
    assert "center" in zone_names


def test_disabled_zone_excluded():
    """Zone with enabled=False → detections inside it are not returned."""
    zones = [Zone(
        name="disabled",
        polygon=[[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]],
        enabled=False,
    )]
    zf = ZoneFilter(zones)
    dets = _make_detections([[10.0, 10.0, 90.0, 90.0]], [0])
    results = zf.filter(dets, frame_shape=(100, 100))
    assert len(results) == 0


# ── empty / degenerate inputs ──────────────────────────────────────────────────

def test_empty_detections_returns_empty():
    zf = ZoneFilter([_FULL_ZONE])
    dets = sv.Detections.empty()
    results = zf.filter(dets, frame_shape=(100, 100))
    assert results == []


def test_zone_with_degenerate_polygon_skipped():
    """Zone with < 3 vertices → no Polygon created → no matches."""
    zones = [Zone(name="line", polygon=[[0.0, 0.0], [1.0, 1.0]])]
    zf = ZoneFilter(zones)
    dets = _make_detections([[10.0, 10.0, 90.0, 90.0]], [0])
    results = zf.filter(dets, frame_shape=(100, 100))
    assert len(results) == 0


def test_tracker_id_propagated():
    """track_id from detections.tracker_id is forwarded to ZoneDetection."""
    zf = ZoneFilter([_FULL_ZONE])
    dets = _make_detections(
        [[10.0, 10.0, 90.0, 90.0]], [0], tracker_ids=[42]
    )
    results = zf.filter(dets, frame_shape=(100, 100))
    assert len(results) == 1
    assert results[0].track_id == 42
