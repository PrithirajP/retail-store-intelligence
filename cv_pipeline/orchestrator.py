import os
from typing import Dict, Any

import cv2
import numpy as np

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

# Keep default as 1 for correctness.
# If processing is too slow, run with FRAME_SKIP=5 later.
FRAME_SKIP = int(os.getenv("FRAME_SKIP", "1"))

# Flush remaining events after each camera.
FLUSH_AFTER_CAMERA = True


# ---------------------------------------------------------------------
# Store + camera configuration
# ---------------------------------------------------------------------
#
# IMPORTANT:
# These video paths assume this structure:
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
# Run this script from inside cv_pipeline/:
#
# cd cv_pipeline
# python orchestrator.py
#

STORE_CONFIGS: Dict[str, Dict[str, Dict[str, Any]]] = {
    "ST1008": {
        "CAM_1_ZONE": {
            "video": "../data/ST1008/CAM_1_ZONE.mp4",
            "zones": {
                # Earlier project mapping treated CAM_01 as SKINCARE.
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
            "video": "../data/ST1008/CAM_2_ZONE.mp4",
            "zones": {
                # Earlier project mapping treated CAM_02 as MAKEUP.
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
            "video": "../data/ST1008/CAM_3_ENTRY.mp4",
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
            "video": "../data/ST1008/CAM_5_BILLING.mp4",
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
            "video": "../data/STORE_2/ENTRY_1.mp4",
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
            "video": "../data/STORE_2/ENTRY_2.mp4",
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
            "video": "../data/STORE_2/BILLING_AREA.mp4",
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
            "video": "../data/STORE_2/ZONE.mp4",
            "zones": {
                # Store 2 product zone is not confirmed as MAKEUP/SKINCARE,
                # so keep it generic.
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
    Build the detector in a backwards-compatible way.

    Some detector.py versions may define PersonDetector() without args,
    while others may accept a model path.
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
) -> StoreTrackerState:
    """
    Build StoreTrackerState in a backwards-compatible way.

    This protects us if tracker_state.py uses positional arguments instead
    of keyword arguments.
    """

    try:
        return StoreTrackerState(
            store_id=store_id,
            camera_id=camera_id,
            zones=zones,
        )
    except TypeError:
        return StoreTrackerState(store_id, camera_id, zones)


# ---------------------------------------------------------------------
# Event transformation
# ---------------------------------------------------------------------

def build_tracker(
    store_id: str,
    camera_id: str,
    zones: Dict[str, np.ndarray],
    entrance_line=None,
) -> StoreTrackerState:
    """
    Build StoreTrackerState in a backwards-compatible way.

    Your current tracker_state.py requires:
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

    print("\n" + "=" * 80)
    print(f"Processing store={store_id}, camera={camera_id}")
    print(f"Video: {video_path}")
    print(f"Zones: {list(zones.keys())}")
    print("=" * 80)

    cap = cv2.VideoCapture(video_path)

    if not cap.isOpened():
        print(f"WARNING: Could not open {video_path}. Skipping {store_id}/{camera_id}.")
        return

    entrance_line = camera_config.get("entrance_line")

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

        tracks = detector.get_tracks(frame)
        events = tracker.process_frame_tracks(tracks)

        for event in events:
            normalized_event = normalize_business_event(
                event=event,
                store_id=store_id,
                camera_id=camera_id,
            )

            emitter.add_event(normalized_event)
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
        emitter.flush()

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

    emitter.flush()

    print("\n" + "#" * 80)
    print(f"FINISHED STORE: {store_id}")
    print("#" * 80)


def main():
    print("Starting CV pipeline...")
    print(f"API_URL={API_URL}")
    print(f"YOLO_MODEL={YOLO_MODEL}")
    print(f"FRAME_SKIP={FRAME_SKIP}")

    detector = build_detector()
    emitter = EventEmitter(API_URL)

    for store_id, camera_configs in STORE_CONFIGS.items():
        process_store(
            detector=detector,
            emitter=emitter,
            store_id=store_id,
            camera_configs=camera_configs,
        )

    emitter.flush()

    print("\nCV pipeline finished.")


if __name__ == "__main__":
    main()