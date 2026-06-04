# PROMPT:
# Write pytest tests for lightweight distance-based re-entry detection.
#
# HUMAN CHANGES:
# Tests verify that the tracker emits REENTRY instead of a second ENTRY when
# a new local track crosses inward near a recent exit.

import sys
from pathlib import Path

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CV_DIR = PROJECT_ROOT / "cv_pipeline"

if str(CV_DIR) not in sys.path:
    sys.path.insert(0, str(CV_DIR))

from tracker_state import StoreTrackerState  # noqa: E402


def _make_entry_tracker():
    zones = {
        "ENTRY_DOOR": np.array(
            [
                [50, 0],
                [100, 0],
                [100, 100],
                [50, 100],
            ],
            np.int32,
        )
    }

    return StoreTrackerState(
        store_id="STORE_TEST",
        camera_id="CAM_ENTRY",
        zones=zones,
        entrance_line=((50, 0), (50, 100)),
        reentry_window_seconds=600,
        reentry_distance_px=250,
    )


def test_tracker_emits_reentry_for_new_track_near_recent_exit():
    tracker = _make_entry_tracker()

    # Existing visitor starts inside the store.
    tracker.process_frame_tracks(
        [
            {
                "visitor_id": "VIS_OLD",
                "point": (75, 50),
                "conf": 0.95,
            }
        ]
    )

    # Existing visitor exits.
    exit_events = tracker.process_frame_tracks(
        [
            {
                "visitor_id": "VIS_OLD",
                "point": (25, 50),
                "conf": 0.95,
            }
        ]
    )

    assert len(exit_events) == 1
    assert exit_events[0]["event_type"] == "LINE_CROSS"
    assert exit_events[0]["direction"] == "OUT"
    assert exit_events[0]["visitor_id"] == "VIS_OLD"

    # New local tracker ID appears outside.
    tracker.process_frame_tracks(
        [
            {
                "visitor_id": "VIS_NEW_LOCAL",
                "point": (25, 55),
                "conf": 0.92,
            }
        ]
    )

    # New local tracker ID crosses inward near the old exit.
    reentry_events = tracker.process_frame_tracks(
        [
            {
                "visitor_id": "VIS_NEW_LOCAL",
                "point": (75, 55),
                "conf": 0.92,
            }
        ]
    )

    assert len(reentry_events) == 1

    event = reentry_events[0]

    assert event["event_type"] == "REENTRY"
    assert event["visitor_id"] == "VIS_OLD"
    assert event["zone_id"] is None


def test_tracker_emits_normal_entry_when_no_recent_exit_match():
    tracker = _make_entry_tracker()

    tracker.process_frame_tracks(
        [
            {
                "visitor_id": "VIS_NEW",
                "point": (25, 50),
                "conf": 0.95,
            }
        ]
    )

    events = tracker.process_frame_tracks(
        [
            {
                "visitor_id": "VIS_NEW",
                "point": (75, 50),
                "conf": 0.95,
            }
        ]
    )

    assert len(events) == 1
    assert events[0]["event_type"] == "LINE_CROSS"
    assert events[0]["direction"] == "IN"
    assert events[0]["visitor_id"] == "VIS_NEW"


def test_reentry_mapping_is_reused_for_future_zone_events():
    zones = {
        "ENTRY_DOOR": np.array(
            [
                [50, 0],
                [100, 0],
                [100, 100],
                [50, 100],
            ],
            np.int32,
        ),
        "MAKEUP": np.array(
            [
                [100, 0],
                [200, 0],
                [200, 100],
                [100, 100],
            ],
            np.int32,
        ),
    }

    tracker = StoreTrackerState(
        store_id="STORE_TEST",
        camera_id="CAM_ENTRY",
        zones=zones,
        entrance_line=((50, 0), (50, 100)),
        reentry_window_seconds=600,
        reentry_distance_px=250,
    )

    tracker.process_frame_tracks(
        [
            {
                "visitor_id": "VIS_OLD",
                "point": (75, 50),
                "conf": 0.95,
            }
        ]
    )

    tracker.process_frame_tracks(
        [
            {
                "visitor_id": "VIS_OLD",
                "point": (25, 50),
                "conf": 0.95,
            }
        ]
    )

    tracker.process_frame_tracks(
        [
            {
                "visitor_id": "VIS_NEW_LOCAL",
                "point": (25, 50),
                "conf": 0.95,
            }
        ]
    )

    reentry_events = tracker.process_frame_tracks(
        [
            {
                "visitor_id": "VIS_NEW_LOCAL",
                "point": (75, 50),
                "conf": 0.95,
            }
        ]
    )

    assert reentry_events[0]["event_type"] == "REENTRY"
    assert reentry_events[0]["visitor_id"] == "VIS_OLD"

    zone_events = tracker.process_frame_tracks(
        [
            {
                "visitor_id": "VIS_NEW_LOCAL",
                "point": (150, 50),
                "conf": 0.95,
            }
        ]
    )

    zone_event_types = {event["event_type"] for event in zone_events}
    visitor_ids = {event["visitor_id"] for event in zone_events}

    assert "ZONE_ENTER" in zone_event_types
    assert visitor_ids == {"VIS_OLD"}