"""
Tests for tracker.ObjectTracker — dwell time, zone entry, track expiry.
We test ObjectTracker's own state management without exercising ByteTrack
itself (that's tested by the supervision library).
"""
import time

import numpy as np
import pytest
import supervision as sv

from tracker import ObjectTracker, _EXPIRE_S


def test_dwell_time_zero_for_unknown_track():
    t = ObjectTracker()
    assert t.get_dwell_time(999, "zone_a") == 0.0


def test_dwell_time_is_positive_after_entry():
    t = ObjectTracker()
    t.record_zone_entry(1, "zone_a")
    time.sleep(0.02)
    dwell = t.get_dwell_time(1, "zone_a")
    assert dwell >= 0.01, f"expected dwell > 10ms, got {dwell:.4f}s"


def test_dwell_time_increases_over_time():
    t = ObjectTracker()
    t.record_zone_entry(2, "zone_b")
    dwell1 = t.get_dwell_time(2, "zone_b")
    time.sleep(0.03)
    dwell2 = t.get_dwell_time(2, "zone_b")
    assert dwell2 > dwell1


def test_first_entry_is_idempotent():
    """Calling record_zone_entry multiple times should not reset the entry time."""
    t = ObjectTracker()
    t.record_zone_entry(3, "zone_c")
    time.sleep(0.05)
    dwell_before = t.get_dwell_time(3, "zone_c")
    t.record_zone_entry(3, "zone_c")  # second call
    dwell_after = t.get_dwell_time(3, "zone_c")
    # dwell_after should be >= dwell_before (entry time unchanged)
    assert dwell_after >= dwell_before - 0.005  # allow 5ms floating-point margin


def test_separate_zones_tracked_independently():
    t = ObjectTracker()
    t.record_zone_entry(4, "zone_x")
    time.sleep(0.03)
    t.record_zone_entry(4, "zone_y")
    time.sleep(0.02)
    dwell_x = t.get_dwell_time(4, "zone_x")
    dwell_y = t.get_dwell_time(4, "zone_y")
    assert dwell_x > dwell_y, "zone_x entry came first — should have longer dwell"


def test_different_tracks_same_zone_independent():
    t = ObjectTracker()
    t.record_zone_entry(10, "zone_a")
    time.sleep(0.03)
    t.record_zone_entry(11, "zone_a")
    dwell10 = t.get_dwell_time(10, "zone_a")
    dwell11 = t.get_dwell_time(11, "zone_a")
    assert dwell10 > dwell11


def test_track_expiry_after_5_seconds():
    """Tracks older than _EXPIRE_S are purged by _expire_stale."""
    t = ObjectTracker()
    track_id = 42
    # Simulate a track that was last seen > _EXPIRE_S ago
    t._last_seen[track_id] = time.monotonic() - (_EXPIRE_S + 1.0)
    t._zone_entry[track_id] = {"zone_a": time.monotonic() - (_EXPIRE_S + 1.0)}

    # Trigger expiry
    t._expire_stale()

    assert t.get_dwell_time(track_id, "zone_a") == 0.0
    assert track_id not in t._last_seen
    assert track_id not in t._zone_entry


def test_recent_track_not_expired():
    t = ObjectTracker()
    t.record_zone_entry(7, "zone_a")
    t._expire_stale()
    # Still within _EXPIRE_S — should not be purged
    assert t.get_dwell_time(7, "zone_a") >= 0.0
    assert 7 in t._last_seen


def test_update_with_empty_detections_triggers_expiry():
    """Calling update() with empty Detections runs _expire_stale."""
    t = ObjectTracker()
    track_id = 99
    t._last_seen[track_id] = time.monotonic() - (_EXPIRE_S + 1.0)
    t._zone_entry[track_id] = {"zone_a": time.monotonic() - (_EXPIRE_S + 1.0)}

    empty_dets = sv.Detections.empty()
    t.update(empty_dets)

    assert t.get_dwell_time(track_id, "zone_a") == 0.0


def test_update_returns_detections_unchanged_when_empty():
    t = ObjectTracker()
    empty = sv.Detections.empty()
    result = t.update(empty)
    assert len(result) == 0


def test_update_with_single_detection():
    """update() with one detection should record it in last_seen."""
    t = ObjectTracker()
    dets = sv.Detections(
        xyxy=np.array([[0.1, 0.1, 0.5, 0.5]], dtype=np.float32),
        confidence=np.array([0.9], dtype=np.float32),
        class_id=np.array([0], dtype=int),
    )
    result = t.update(dets)
    # ByteTracker may or may not assign tracker_id on first frame (needs 2 frames)
    # Just verify no crash and returns Detections
    assert isinstance(result, sv.Detections)
