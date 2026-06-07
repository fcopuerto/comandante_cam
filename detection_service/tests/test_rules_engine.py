"""
Tests for rules_engine.RulesEngine — all 5 rules, cooldown suppression.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import cv2
import numpy as np
import pytest

from rules_engine import RulesEngine
from zone_filter import Zone, ZoneDetection


# ── test fixtures / helpers ───────────────────────────────────────────────────

_ALWAYS_AFTER_HOURS_ZONE = Zone(
    name="zone_a",
    polygon=[[0, 0], [1, 0], [1, 1], [0, 1]],
    restricted=False,
    # No working_hours → always "after hours"
)

_RESTRICTED_ZONE = Zone(
    name="restricted",
    polygon=[[0, 0], [1, 0], [1, 1], [0, 1]],
    restricted=True,
)

_WORKING_HOURS_ZONE = Zone(
    name="work_zone",
    polygon=[[0, 0], [1, 0], [1, 1], [0, 1]],
    restricted=False,
    working_hours_start="08:00",
    working_hours_end="18:00",
)

_DWELL_ZONE = Zone(
    name="dwell_zone",
    polygon=[[0, 0], [1, 0], [1, 1], [0, 1]],
    dwell_threshold_s=10,
)

_BLANK_FRAME = np.zeros((100, 100, 3), dtype=np.uint8)
_WHITE_FRAME = np.full((100, 100, 3), 255, dtype=np.uint8)


def _det(class_name: str = "person", track_id: int = 1, zone: Zone = _ALWAYS_AFTER_HOURS_ZONE) -> ZoneDetection:
    return ZoneDetection(
        class_id=0,
        class_name=class_name,
        confidence=0.9,
        bbox=[0.1, 0.1, 0.5, 0.5],
        track_id=track_id,
        zone_name=zone.name,
        zone=zone,
    )


def _ts(hour: int = 3) -> datetime:
    """Return a datetime at the given UTC hour (default 03:00 = after hours)."""
    return datetime(2025, 6, 1, hour, 0, 0, tzinfo=timezone.utc)


def _baseline_hist(frame: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    hist = cv2.calcHist([gray], [0], None, [256], [0, 256])
    cv2.normalize(hist, hist)
    return hist


# ── Rule 1: TAMPERING ─────────────────────────────────────────────────────────

def test_tampering_fires_when_histogram_differs_greatly():
    """Baseline=white frame, current=black frame → correlation ≈ 0 → alert."""
    engine = RulesEngine("cam-1", baseline_histogram=_baseline_hist(_WHITE_FRAME))
    alerts = engine.evaluate([], _BLANK_FRAME, current_time=_ts())
    assert len(alerts) == 1
    assert alerts[0].rule_triggered == "TAMPERING"
    assert alerts[0].severity == "critical"


def test_tampering_silent_when_histogram_matches():
    """Baseline and current are same frame → high correlation → no alert."""
    engine = RulesEngine("cam-1", baseline_histogram=_baseline_hist(_BLANK_FRAME))
    alerts = engine.evaluate([], _BLANK_FRAME, current_time=_ts())
    assert len(alerts) == 0


def test_tampering_preempts_other_rules():
    """When tampering fires, other rules are not evaluated (returns early)."""
    engine = RulesEngine("cam-1", baseline_histogram=_baseline_hist(_WHITE_FRAME))
    det = _det(zone=_RESTRICTED_ZONE)
    alerts = engine.evaluate([det], _BLANK_FRAME, current_time=_ts())
    assert len(alerts) == 1
    assert alerts[0].rule_triggered == "TAMPERING"


# ── Rule 2: RESTRICTED_ZONE_ANY_TIME ─────────────────────────────────────────

def test_restricted_zone_fires_for_person():
    engine = RulesEngine("cam-1")
    det = _det(class_name="person", zone=_RESTRICTED_ZONE)
    alerts = engine.evaluate([det], _BLANK_FRAME, current_time=_ts(hour=14))
    assert any(a.rule_triggered == "RESTRICTED_ZONE_ANY_TIME" for a in alerts)


def test_restricted_zone_fires_for_vehicle():
    engine = RulesEngine("cam-1")
    det = _det(class_name="car", zone=_RESTRICTED_ZONE)
    alerts = engine.evaluate([det], _BLANK_FRAME, current_time=_ts(hour=14))
    assert any(a.rule_triggered == "RESTRICTED_ZONE_ANY_TIME" for a in alerts)


def test_restricted_zone_fires_during_working_hours():
    """Restricted zone fires at any time — even during 'working hours'."""
    engine = RulesEngine("cam-1")
    det = _det(zone=_RESTRICTED_ZONE)
    alerts = engine.evaluate([det], _BLANK_FRAME, current_time=_ts(hour=10))
    assert any(a.rule_triggered == "RESTRICTED_ZONE_ANY_TIME" for a in alerts)


# ── Rule 3: AFTER_HOURS_PERSON ────────────────────────────────────────────────

def test_after_hours_person_fires_outside_schedule():
    engine = RulesEngine("cam-1")
    det = _det(class_name="person", zone=_WORKING_HOURS_ZONE)
    # 03:00 UTC — before 08:00 → after hours
    alerts = engine.evaluate([det], _BLANK_FRAME, current_time=_ts(hour=3))
    assert any(a.rule_triggered == "AFTER_HOURS_PERSON" for a in alerts)
    assert any(a.severity == "high" for a in alerts)


def test_after_hours_person_silent_during_working_hours():
    engine = RulesEngine("cam-1")
    det = _det(class_name="person", zone=_WORKING_HOURS_ZONE)
    # 12:00 UTC — inside 08:00-18:00
    alerts = engine.evaluate([det], _BLANK_FRAME, current_time=_ts(hour=12))
    assert not any(a.rule_triggered == "AFTER_HOURS_PERSON" for a in alerts)


def test_after_hours_person_silent_in_zone_without_schedule():
    """Zone without schedule → returns False from _within_working_hours → fires."""
    engine = RulesEngine("cam-1")
    det = _det(class_name="person", zone=_ALWAYS_AFTER_HOURS_ZONE)
    alerts = engine.evaluate([det], _BLANK_FRAME, current_time=_ts(hour=12))
    # No working_hours set → always fires AFTER_HOURS_PERSON
    assert any(a.rule_triggered == "AFTER_HOURS_PERSON" for a in alerts)


# ── Rule 4: AFTER_HOURS_VEHICLE ───────────────────────────────────────────────

def test_after_hours_vehicle_fires_for_car():
    engine = RulesEngine("cam-1")
    det = _det(class_name="car", zone=_WORKING_HOURS_ZONE)
    alerts = engine.evaluate([det], _BLANK_FRAME, current_time=_ts(hour=3))
    assert any(a.rule_triggered == "AFTER_HOURS_VEHICLE" for a in alerts)
    assert any(a.severity == "medium" for a in alerts)


def test_after_hours_vehicle_silent_during_working_hours():
    engine = RulesEngine("cam-1")
    det = _det(class_name="truck", zone=_WORKING_HOURS_ZONE)
    alerts = engine.evaluate([det], _BLANK_FRAME, current_time=_ts(hour=10))
    assert not any(a.rule_triggered == "AFTER_HOURS_VEHICLE" for a in alerts)


# ── Rule 5: DWELL_TIME ────────────────────────────────────────────────────────

def test_dwell_fires_when_threshold_reached():
    engine = RulesEngine("cam-1")
    det = _det(track_id=7, zone=_DWELL_ZONE)
    alert = engine.evaluate_dwell(det, dwell_time=15.0, current_time=_ts())
    assert alert is not None
    assert alert.rule_triggered == "DWELL_TIME"
    assert alert.severity == "medium"


def test_dwell_silent_when_below_threshold():
    engine = RulesEngine("cam-1")
    det = _det(track_id=7, zone=_DWELL_ZONE)
    alert = engine.evaluate_dwell(det, dwell_time=5.0, current_time=_ts())
    assert alert is None


def test_dwell_silent_without_track_id():
    engine = RulesEngine("cam-1")
    det = _det(track_id=None, zone=_DWELL_ZONE)
    alert = engine.evaluate_dwell(det, dwell_time=100.0, current_time=_ts())
    assert alert is None


# ── Cooldown suppression ──────────────────────────────────────────────────────

def test_cooldown_suppresses_same_rule_zone_track():
    """Second call with same (rule, zone, track_id) within 60s → suppressed."""
    engine = RulesEngine("cam-1")
    det = _det(class_name="person", track_id=1, zone=_ALWAYS_AFTER_HOURS_ZONE)
    alerts1 = engine.evaluate([det], _BLANK_FRAME, current_time=_ts())
    alerts2 = engine.evaluate([det], _BLANK_FRAME, current_time=_ts())
    assert len(alerts1) == 1
    assert len(alerts2) == 0  # suppressed by cooldown


def test_cooldown_does_not_suppress_different_track_id():
    """Different track_id in same zone → not suppressed by cooldown."""
    engine = RulesEngine("cam-1")
    det1 = _det(class_name="person", track_id=1, zone=_ALWAYS_AFTER_HOURS_ZONE)
    det2 = _det(class_name="person", track_id=2, zone=_ALWAYS_AFTER_HOURS_ZONE)
    alerts1 = engine.evaluate([det1], _BLANK_FRAME, current_time=_ts())
    alerts2 = engine.evaluate([det2], _BLANK_FRAME, current_time=_ts())
    assert len(alerts1) == 1
    assert len(alerts2) == 1


def test_cooldown_does_not_suppress_different_zone():
    """Same track_id in different zone → not suppressed."""
    zone_b = Zone(name="zone_b", polygon=[[0, 0], [1, 0], [1, 1], [0, 1]])
    engine = RulesEngine("cam-1")
    det_a = ZoneDetection(0, "person", 0.9, [0.1, 0.1, 0.5, 0.5], 1, "zone_a", _ALWAYS_AFTER_HOURS_ZONE)
    det_b = ZoneDetection(0, "person", 0.9, [0.1, 0.1, 0.5, 0.5], 1, "zone_b", zone_b)
    alerts_a = engine.evaluate([det_a], _BLANK_FRAME, current_time=_ts())
    alerts_b = engine.evaluate([det_b], _BLANK_FRAME, current_time=_ts())
    assert len(alerts_a) == 1
    assert len(alerts_b) == 1


def test_dwell_cooldown_suppresses_repeat():
    engine = RulesEngine("cam-1")
    det = _det(track_id=5, zone=_DWELL_ZONE)
    a1 = engine.evaluate_dwell(det, dwell_time=20.0, current_time=_ts())
    a2 = engine.evaluate_dwell(det, dwell_time=20.0, current_time=_ts())
    assert a1 is not None
    assert a2 is None


def test_tampering_cooldown_suppresses_repeat():
    engine = RulesEngine("cam-1", baseline_histogram=_baseline_hist(_WHITE_FRAME))
    alerts1 = engine.evaluate([], _BLANK_FRAME, current_time=_ts())
    alerts2 = engine.evaluate([], _BLANK_FRAME, current_time=_ts())
    assert len(alerts1) == 1
    assert len(alerts2) == 0
