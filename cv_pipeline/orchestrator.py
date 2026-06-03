import os
from pathlib import Path
from typing import Any, Dict, Optional, List

import cv2
import numpy as np
import requests

from detector import PersonDetector
from tracker_state import StoreTrackerState
from event_emitter import EventEmitter


# ---------------------------------------------------------------------
# Runtime configuration
# ---------------------------------------------------------------------

API_URL = os.getenv(
    "API_URL",
    "http://127.0.0.1:8000/events/ingest",
)

YOLO_MODEL = os.getenv("YOLO_MODEL", "yolov8n.pt")

# Keep FRAME_SKIP=1 for maximum correctness.
# If it is very slow, run:
# $env:FRAME_SKIP="5"
# python orchestrator.py
FRAME_SKIP = int(os.getenv("FRAME_SKIP", "1"))

FLUSH_AFTER_CAMERA = True

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent


def data_path(relative_path: str) -> str:
    """
    Build stable paths from project root.
    This works whether you run the script from project root or cv_pipeline/.
    """
    return str(PROJECT_ROOT / relative_path)


# ---------------------------------------------------------------------
# Store + camera configuration
# ---------------------------------------------------------------------
#
# Confirmed:
# Store 1 = ST1008
# Store 2 = STORE_2
#
# Expected local data structure:
#
# data/
# ├── ST1008/
# │   ├── CAM_1_ZONE.mp4
# │   ├── CAM_2_ZONE.mp4
# │   ├── CAM_3_ENTRY.mp4
# │   └── CAM_5_BILLING.mp4
# │
# └── STORE_2/
#     ├── ENTRY_1.mp4
#     ├── ENTRY_2.mp4
#     ├── BILLING_AREA.mp4
#     └── ZONE.mp4
#

STORE_CONFIGS: Dict[str, Dict[str, Dict[str, Any]]] = {
    "ST1008": {
        "CAM_1_ZONE": {
            "video": data_path("data/ST1008/CAM_1_ZONE.mp4"),
            "entrance_line": None,
            "zones": {
                "SKINCARE": np.array(
                    [
                        [0, 250],
                        [1485, 196],
                        [1581, 435],
                        [1779, 584],
                        [1887, 711],
                        [1911, 752],
                        [1884, 1076],
                        [6, 1072],
                        [6, 252],
                    ],
                    np.int32,
                )
            },
        },
        "CAM_2_ZONE": {
            "video": data_path("data/ST1008/CAM_2_ZONE.mp4"),
            "entrance_line": None,
            "zones": {
                "MAKEUP": np.array(
                    [
                        [6, 86],
                        [1914, 86],
                        [1902, 1059],
                        [3, 1050],
                        [6, 92],
                    ],
                    np.int32,
                )
            },
        },
        "CAM_3_ENTRY": {
            "video": data_path("data/ST1008/CAM_3_ENTRY.mp4"),
            "entrance_line": ((98, 196), (1455, 30)),
            "zones": {
                "ENTRY_DOOR": np.array(
                    [
                        [98, 196],
                        [1455, 30],
                        [1484, 370],
                        [1023, 1072],
                        [476, 1071],
                        [108, 198],
                    ],
                    np.int32,
                )
            },
        },
        "CAM_5_BILLING": {
            "video": data_path("data/ST1008/CAM_5_BILLING.mp4"),
            "entrance_line": None,
            "zones": {
                "BEHIND_COUNTER": np.array(
                    [
                        [424, 1068],
                        [297, 778],
                        [562, 252],
                        [752, 267],
                        [1200, 322],
                        [1246, 1052],
                        [432, 1070],
                    ],
                    np.int32,
                ),
                "BILLING_QUEUE": np.array(
                    [
                        [214, 750],
                        [506, 237],
                        [210, 202],
                        [10, 698],
                        [204, 750],
                    ],
                    np.int32,
                ),
            },
        },
    },
    "STORE_2": {
        "ENTRY_1": {
            "video": data_path("data/STORE_2/ENTRY_1.mp4"),
            "entrance_line": ((144, 15), (870, 6)),
            "zones": {
                "ENTRY_DOOR": np.array(
                    [
                        [144, 15],
                        [217, 669],
                        [198, 906],
                        [743, 892],
                        [870, 6],
                        [142, 12],
                    ],
                    np.int32,
                )
            },
        },
        "ENTRY_2": {
            "video": data_path("data/STORE_2/ENTRY_2.mp4"),
            "entrance_line": ((172, 21), (840, 30)),
            "zones": {
                "ENTRY_DOOR": np.array(
                    [
                        [172, 21],
                        [840, 30],
                        [734, 892],
                        [249, 948],
                        [169, 16],
                    ],
                    np.int32,
                )
            },
        },
        "BILLING_AREA": {
            "video": data_path("data/STORE_2/BILLING_AREA.mp4"),
            "entrance_line": None,
            "zones": {
                "BEHIND_COUNTER": np.array(
                    [
                        [350, 642],
                        [676, 650],
                        [694, 1057],
                        [382, 1054],
                        [345, 658],
                    ],
                    np.int32,
                ),
                "BILLING_QUEUE": np.array(
                    [
                        [352, 526],
                        [664, 528],
                        [658, 330],
                        [361, 300],
                        [350, 526],
                    ],
                    np.int32,
                ),
            },
        },
        "ZONE": {
            "video": data_path("data/STORE_2/ZONE.mp4"),
            "entrance_line": None,
            "zones": {
                "PRODUCT_ZONE": np.array(
                    [
                        [12, 210],
                        [365, 48],
                        [482, 56],
                        [944, 284],
                        [892, 1029],
                        [652, 1053],
                        [37, 1050],
                        [12, 213],
                    ],
                    np.int32,
                )
            },
        },
    },
}


# ---------------------------------------------------------------------
# Construction helpers
# ---------------------------------------------------------------------

def build_detector() -> PersonDetector:
    """
    Build detector with compatibility for different detector.py constructors.
    """

    try:
        return PersonDetector(model_path=YOLO_MODEL)
    except TypeError:
        try:
            return PersonDetector(YOLO_MODEL)
        except TypeError:
            return PersonDetector()


def build_tracker(
    store_id: str,
    camera_id: str,
    zones: Dict[str, np.ndarray],
    entrance_line: Optional[tuple] = None,
) -> StoreTrackerState:
    """
    Build tracker with compatibility for tracker_state.py.

    Your current tracker requires:
    StoreTrackerState(store_id, camera_id, zones, entrance_line)
    """

    try:
        return StoreTrackerState(
            store_id=store_id,
            camera_id=camera_id,
            zones=zones,
            entrance_line=entrance_line,
        )
    except TypeError:
        return StoreTrackerState(
            store_id,
            camera_id,
            zones,
            entrance_line,
        )


def build_emitter() -> EventEmitter:
    """
    Build EventEmitter with compatibility for different constructors.
    """

    try:
        return EventEmitter(api_url=API_URL)
    except TypeError:
        try:
            return EventEmitter(API_URL)
        except TypeError:
            return EventEmitter()


# ---------------------------------------------------------------------
# Event helpers
# ---------------------------------------------------------------------

def normalize_business_event(
    event: dict,
    store_id: str,
    camera_id: str,
) -> dict:
    """
    Convert tracker zone events into business-level events expected by the API.

    Examples:
    - ZONE_ENTER at ENTRY_DOOR      -> ENTRY
    - ZONE_ENTER at BILLING_QUEUE   -> BILLING_QUEUE_JOIN
    - ZONE_EXIT at BILLING_QUEUE    -> BILLING_QUEUE_EXIT
    """

    if event is None:
        return {}

    event["store_id"] = event.get("store_id") or store_id
    event["camera_id"] = event.get("camera_id") or camera_id

    event_type = event.get("event_type")
    zone_id = event.get("zone_id")

    if event_type == "ZONE_ENTER" and zone_id == "ENTRY_DOOR":
        event["event_type"] = "ENTRY"
        event["zone_id"] = None

    elif event_type == "ZONE_ENTER" and zone_id == "BILLING_QUEUE":
        event["event_type"] = "BILLING_QUEUE_JOIN"

    elif event_type == "ZONE_EXIT" and zone_id == "BILLING_QUEUE":
        event["event_type"] = "BILLING_QUEUE_EXIT"

    if "metadata" not in event or not isinstance(event["metadata"], dict):
        event["metadata"] = {
            "queue_depth": event.get("queue_depth"),
            "sku_zone": event.get("sku_zone") or event.get("zone_id"),
            "session_seq": event.get("session_seq"),
        }

    return event


def post_events_direct(events: List[dict]):
    """
    Fallback sender.

    Used only if EventEmitter does not expose a known method.
    """

    if not events:
        return None

    try:
        response = requests.post(
            API_URL,
            json={"events": events},
            timeout=10,
        )
        print(
            f"Direct POST: status={response.status_code}, "
            f"events={len(events)}"
        )
        return response

    except requests.RequestException as exc:
        print(f"WARNING: Failed direct POST to API: {exc}")
        return None


def emit_or_buffer_event(emitter: EventEmitter, event: dict):
    """
    Send or buffer one event using whichever method exists in event_emitter.py.

    This protects orchestrator.py from method-name differences such as:
    add_event, emit_event, send_event, emit, send_events, etc.
    """

    if event is None:
        return None

    single_event_methods = [
        "add_event",
        "emit_event",
        "send_event",
        "publish_event",
        "emit",
        "send",
        "push",
    ]

    for method_name in single_event_methods:
        method = getattr(emitter, method_name, None)

        if callable(method):
            return method(event)

    batch_event_methods = [
        "send_events",
        "emit_events",
        "post_events",
        "publish_events",
        "send_batch",
        "emit_batch",
        "post_batch",
        "publish_batch",
    ]

    for method_name in batch_event_methods:
        method = getattr(emitter, method_name, None)

        if callable(method):
            return method([event])

    buffer_names = [
        "buffer",
        "events",
        "event_buffer",
        "pending_events",
    ]

    for buffer_name in buffer_names:
        buffer = getattr(emitter, buffer_name, None)

        if isinstance(buffer, list):
            buffer.append(event)
            return None

    # Last safe fallback: send directly to API.
    return post_events_direct([event])


def flush_emitter(emitter: EventEmitter):
    """
    Flush pending events if EventEmitter supports flushing.
    If it sends immediately, this is a no-op.
    """

    flush_methods = [
        "flush",
        "flush_events",
        "send_batch",
        "emit_batch",
        "post_batch",
        "publish_batch",
    ]

    for method_name in flush_methods:
        method = getattr(emitter, method_name, None)

        if callable(method):
            try:
                return method()
            except TypeError:
                # Some batch methods require a list. Try to pass a known buffer.
                for buffer_name in [
                    "buffer",
                    "events",
                    "event_buffer",
                    "pending_events",
                ]:
                    buffer = getattr(emitter, buffer_name, None)

                    if isinstance(buffer, list) and buffer:
                        result = method(buffer)
                        buffer.clear()
                        return result

    # If no flush method exists but there is a known buffer, post it directly.
    for buffer_name in [
        "buffer",
        "events",
        "event_buffer",
        "pending_events",
    ]:
        buffer = getattr(emitter, buffer_name, None)

        if isinstance(buffer, list) and buffer:
            events_to_send = list(buffer)
            buffer.clear()
            return post_events_direct(events_to_send)

    return None


def get_tracks_from_detector(
    detector: PersonDetector,
    frame,
):
    """
    Compatibility wrapper for detector.py.
    Expected method is get_tracks(frame).
    """

    if hasattr(detector, "get_tracks"):
        return detector.get_tracks(frame)

    if hasattr(detector, "detect"):
        return detector.detect(frame)

    raise AttributeError(
        "PersonDetector must define either get_tracks(frame) or detect(frame)."
    )


def get_events_from_tracker(
    tracker: StoreTrackerState,
    tracks,
):
    """
    Compatibility wrapper for tracker_state.py.
    Expected method is process_frame_tracks(tracks).
    """

    if hasattr(tracker, "process_frame_tracks"):
        return tracker.process_frame_tracks(tracks)

    if hasattr(tracker, "update"):
        return tracker.update(tracks)

    raise AttributeError(
        "StoreTrackerState must define process_frame_tracks(tracks) or update(tracks)."
    )


# ---------------------------------------------------------------------
# Processing
# ---------------------------------------------------------------------

def process_camera(
    detector: PersonDetector,
    emitter: EventEmitter,
    store_id: str,
    camera_id: str,
    camera_config: Dict[str, Any],
):
    video_path = camera_config["video"]
    zones = camera_config["zones"]
    entrance_line = camera_config.get("entrance_line")

    print("\n" + "=" * 80)
    print(f"Processing store={store_id}, camera={camera_id}")
    print(f"Video: {video_path}")
    print(f"Zones: {list(zones.keys())}")
    print(f"Entrance line: {entrance_line}")
    print("=" * 80)

    if not Path(video_path).exists():
        print(f"WARNING: Video file not found: {video_path}")
        print(f"Skipping {store_id}/{camera_id}.")
        return

    cap = cv2.VideoCapture(video_path)

    if not cap.isOpened():
        print(f"WARNING: Could not open {video_path}. Skipping {store_id}/{camera_id}.")
        return

    tracker = build_tracker(
        store_id=store_id,
        camera_id=camera_id,
        zones=zones,
        entrance_line=entrance_line,
    )

    frame_index = 0
    processed_frames = 0
    emitted_events = 0

    while True:
        ret, frame = cap.read()

        if not ret:
            break

        frame_index += 1

        if FRAME_SKIP > 1 and frame_index % FRAME_SKIP != 0:
            continue

        processed_frames += 1

        tracks = get_tracks_from_detector(detector, frame)
        events = get_events_from_tracker(tracker, tracks)

        if events is None:
            events = []

        for event in events:
            if not isinstance(event, dict):
                continue

            normalized_event = normalize_business_event(
                event=event,
                store_id=store_id,
                camera_id=camera_id,
            )

            if not normalized_event:
                continue

            emit_or_buffer_event(emitter, normalized_event)
            emitted_events += 1

        if processed_frames % 500 == 0:
            print(
                f"[{store_id}/{camera_id}] "
                f"frames_read={frame_index}, "
                f"frames_processed={processed_frames}, "
                f"events_emitted={emitted_events}"
            )

    cap.release()

    if FLUSH_AFTER_CAMERA:
        flush_emitter(emitter)

    print(
        f"Finished {store_id}/{camera_id}: "
        f"frames_read={frame_index}, "
        f"frames_processed={processed_frames}, "
        f"events_emitted={emitted_events}"
    )


def process_store(
    detector: PersonDetector,
    emitter: EventEmitter,
    store_id: str,
    camera_configs: Dict[str, Dict[str, Any]],
):
    print("\n" + "#" * 80)
    print(f"STARTING STORE: {store_id}")
    print("#" * 80)

    for camera_id, camera_config in camera_configs.items():
        process_camera(
            detector=detector,
            emitter=emitter,
            store_id=store_id,
            camera_id=camera_id,
            camera_config=camera_config,
        )

    flush_emitter(emitter)

    print("\n" + "#" * 80)
    print(f"FINISHED STORE: {store_id}")
    print("#" * 80)


def main():
    print("Starting CV pipeline...")
    print(f"API_URL={API_URL}")
    print(f"YOLO_MODEL={YOLO_MODEL}")
    print(f"FRAME_SKIP={FRAME_SKIP}")

    detector = build_detector()
    emitter = build_emitter()

    for store_id, camera_configs in STORE_CONFIGS.items():
        process_store(
            detector=detector,
            emitter=emitter,
            store_id=store_id,
            camera_configs=camera_configs,
        )

    flush_emitter(emitter)

    print("\nCV pipeline finished.")


if __name__ == "__main__":
    main()