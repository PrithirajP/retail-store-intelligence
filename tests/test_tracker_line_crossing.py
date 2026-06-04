import sys
from pathlib import Path

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CV_DIR = PROJECT_ROOT / "cv_pipeline"

if str(CV_DIR) not in sys.path:
    sys.path.insert(0, str(CV_DIR))

from tracker_state import StoreTrackerState  # noqa: E402


def test_tracker_emits_line_cross_in_event():
    zones = {
        "ENTRY_DOOR": np.array(
            [
                [0, 0],
                [100, 0],
                [100, 100],
                [0, 100],
            ],
            np.int32,
        )
    }

    tracker = StoreTrackerState(
        store_id="STORE_TEST",
        camera_id="CAM_ENTRY",
        zones=zones,
        entrance_line=((50, 0), (50, 100)),
    )

    first_frame_events = tracker.process_frame_tracks(
        [
            {
                "visitor_id": "VIS_1",
                "point": (25, 50),
                "conf": 0.95,
            }
        ]
    )

    assert first_frame_events == []

    second_frame_events = tracker.process_frame_tracks(
        [
            {
                "visitor_id": "VIS_1",
                "point": (75, 50),
                "conf": 0.95,
            }
        ]
    )

    assert len(second_frame_events) == 1

    event = second_frame_events[0]

    assert event["event_type"] == "LINE_CROSS"
    assert event["zone_id"] == "ENTRY_DOOR"
    assert event["direction"] == "IN"
    assert event["store_id"] == "STORE_TEST"
    assert event["camera_id"] == "CAM_ENTRY"
    assert event["visitor_id"] == "VIS_1"


def test_tracker_emits_line_cross_out_event():
    zones = {
        "ENTRY_DOOR": np.array(
            [
                [0, 0],
                [100, 0],
                [100, 100],
                [0, 100],
            ],
            np.int32,
        )
    }

    tracker = StoreTrackerState(
        store_id="STORE_TEST",
        camera_id="CAM_ENTRY",
        zones=zones,
        entrance_line=((50, 0), (50, 100)),
    )

    tracker.process_frame_tracks(
        [
            {
                "visitor_id": "VIS_1",
                "point": (75, 50),
                "conf": 0.95,
            }
        ]
    )

    events = tracker.process_frame_tracks(
        [
            {
                "visitor_id": "VIS_1",
                "point": (25, 50),
                "conf": 0.95,
            }
        ]
    )

    assert len(events) == 1

    event = events[0]

    assert event["event_type"] == "LINE_CROSS"
    assert event["zone_id"] == "ENTRY_DOOR"
    assert event["direction"] == "OUT"


def test_tracker_without_entrance_line_keeps_zone_enter_fallback():
    zones = {
        "ENTRY_DOOR": np.array(
            [
                [0, 0],
                [100, 0],
                [100, 100],
                [0, 100],
            ],
            np.int32,
        )
    }

    tracker = StoreTrackerState(
        store_id="STORE_TEST",
        camera_id="CAM_ENTRY",
        zones=zones,
        entrance_line=None,
    )

    events = tracker.process_frame_tracks(
        [
            {
                "visitor_id": "VIS_1",
                "point": (50, 50),
                "conf": 0.95,
            }
        ]
    )

    assert len(events) == 1

    event = events[0]

    assert event["event_type"] == "ZONE_ENTER"
    assert event["zone_id"] == "ENTRY_DOOR"