import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import cv2
import numpy as np
import requests

from detector import PersonDetector
from tracker_state import StoreTrackerState


# ---------------------------------------------------------------------
# Runtime configuration
# ---------------------------------------------------------------------

API_URL = os.getenv(
    "API_URL",
    "http://127.0.0.1:8000/events/ingest",
)

YOLO_MODEL = os.getenv("YOLO_MODEL", "yolov8n.pt")

# Keep FRAME_SKIP=1 for maximum correctness.
# If processing is slow:
# PowerShell:
#   $env:FRAME_SKIP="5"
#   python orchestrator.py
FRAME_SKIP = int(os.getenv("FRAME_SKIP", "1"))

# Debug raw tracker events:
# PowerShell:
#   $env:DEBUG_EVENTS="1"
#   python orchestrator.py
DEBUG_EVENTS = os.getenv("DEBUG_EVENTS", "0") == "1"

# Run only one store:
# PowerShell:
#   $env:ONLY_STORE="STORE_2"
#   python orchestrator.py
ONLY_STORE = os.getenv("ONLY_STORE")

BATCH_SIZE = int(os.getenv("EVENT_BATCH_SIZE", "50"))

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent


def data_path(relative_path: str) -> str:
    """
    Build a stable absolute path from the project root.

    This works whether the script is run from:
    - project root
    - cv_pipeline/
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
# Expected local structure:
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
# NOTE:
# STORE_2 / ENTRY_2 is intentionally disabled for the final baseline
# because both Store 2 entry cameras may observe overlapping visitor traffic.
# Without full Re-ID, using both entry cameras can double-count visitors.
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

        # -----------------------------------------------------------------
        # Disabled for final baseline to reduce Store 2 visitor overcounting.
        # Re-enable only if ENTRY_1 and ENTRY_2 are confirmed to cover
        # different doors/non-overlapping traffic.
        # -----------------------------------------------------------------
        #
        # "ENTRY_2": {
        #     "video": data_path("data/STORE_2/ENTRY_2.mp4"),
        #     "entrance_line": ((172, 21), (840, 30)),
        #     "zones": {
        #         "ENTRY_DOOR": np.array(
        #             [
        #                 [172, 21],
        #                 [840, 30],
        #                 [734, 892],
        #                 [249, 948],
        #                 [169, 16],
        #             ],
        #             np.int32,
        #         )
        #     },
        # },

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
# API event poster
# ---------------------------------------------------------------------

class EventPoster:
    """
    Direct API event poster.

    Important safety behavior:
    - Events are removed from the buffer only after a confirmed HTTP 202.
    - Failed batches remain in memory for retry.
    - This avoids silent data loss when the API is temporarily unavailable.
    """

    def __init__(self, api_url: str, batch_size: int = 50):
        self.api_url = api_url
        self.batch_size = batch_size
        self.buffer: List[dict] = []
        self.total_posted = 0
        self.total_failed_batches = 0

    def add_event(self, event: dict):
        if not event:
            return

        self.buffer.append(event)

        if len(self.buffer) >= self.batch_size:
            self.flush()

    def flush(self):
        if not self.buffer:
            return

        events_to_send = list(self.buffer[: self.batch_size])

        try:
            response = requests.post(
                self.api_url,
                json={"events": events_to_send},
                timeout=15,
            )

            print(
                f"POST /events/ingest: status={response.status_code}, "
                f"events={len(events_to_send)}, response={response.text[:500]}"
            )

            if response.status_code == 202:
                del self.buffer[: len(events_to_send)]
                self.total_posted += len(events_to_send)
            else:
                self.total_failed_batches += 1
                print(
                    "WARNING: API did not accept event batch. "
                    "Events retained in buffer for retry."
                )

        except requests.RequestException as exc:
            self.total_failed_batches += 1
            print(
                f"WARNING: Failed to post events to API: {exc}. "
                "Events retained in buffer for retry."
            )

    def flush_all(self):
        """
        Attempt to flush all buffered events.

        If the API is down, stop after one failed retry to avoid an infinite loop.
        """

        while self.buffer:
            before_count = len(self.buffer)
            self.flush()

            if len(self.buffer) == before_count:
                break


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
    Build tracker with safe per-camera polygon copies.

    This prevents accidental in-place mutation of module-level np.array polygons.
    """

    safe_zones = {
        zone_name: polygon.copy() if hasattr(polygon, "copy") else polygon
        for zone_name, polygon in zones.items()
    }

    try:
        return StoreTrackerState(
            store_id=store_id,
            camera_id=camera_id,
            zones=safe_zones,
            entrance_line=entrance_line,
        )
    except TypeError:
        return StoreTrackerState(
            store_id,
            camera_id,
            safe_zones,
            entrance_line,
        )


# ---------------------------------------------------------------------
# Detector / tracker compatibility wrappers
# ---------------------------------------------------------------------

def get_tracks_from_detector(
    detector: PersonDetector,
    frame,
):
    """
    Compatibility wrapper for detector.py.
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
    """

    if hasattr(tracker, "process_frame_tracks"):
        return tracker.process_frame_tracks(tracks)

    if hasattr(tracker, "update"):
        return tracker.update(tracks)

    raise AttributeError(
        "StoreTrackerState must define process_frame_tracks(tracks) or update(tracks)."
    )


# ---------------------------------------------------------------------
# Event normalization
# ---------------------------------------------------------------------

def _build_metadata(event: dict) -> dict:
    """
    Build metadata without accidentally overwriting meaningful existing values.
    """

    raw_metadata = event.get("metadata")

    if isinstance(raw_metadata, dict):
        metadata = dict(raw_metadata)
    else:
        metadata = {}

    queue_depth = metadata.get("queue_depth")
    sku_zone = metadata.get("sku_zone")
    session_seq = metadata.get("session_seq")

    if queue_depth is None and "queue_depth" in event:
        queue_depth = event.get("queue_depth")

    if sku_zone is None:
        sku_zone = event.get("sku_zone") or event.get("zone_id")

    if session_seq is None and "session_seq" in event:
        session_seq = event.get("session_seq")

    return {
        "queue_depth": queue_depth,
        "sku_zone": sku_zone,
        "session_seq": session_seq,
    }


def normalize_business_event(
    event: dict,
    store_id: str,
    camera_id: str,
    has_entrance_line: bool = False,
) -> dict:
    """
    Convert tracker events into business-level events expected by the API.

    Behavior:
    - Preserve canonical tracker events:
      ZONE_ENTER, ZONE_EXIT, ZONE_DWELL,
      BILLING_QUEUE_JOIN, BILLING_QUEUE_EXIT, etc.
    - Convert ENTRY_DOOR ZONE_ENTER to ENTRY.
    - Convert ENTRY_DOOR ZONE_EXIT to EXIT.
    - Drop ENTRY_DOOR ZONE_DWELL to avoid dwell pollution.
    - Support future directional entrance-line events.
    """

    if event is None:
        return {}

    event["store_id"] = event.get("store_id") or store_id
    event["camera_id"] = event.get("camera_id") or camera_id

    event_type = event.get("event_type")
    zone_id = event.get("zone_id")

    event_type_upper = str(event_type).upper() if event_type is not None else ""

    direction = (
        event.get("direction")
        or event.get("crossing_direction")
        or event.get("movement_direction")
        or event.get("line_direction")
    )
    direction_upper = str(direction).upper() if direction is not None else ""

    line_cross_event_types = {
        "LINE_CROSS",
        "LINE_CROSSED",
        "CROSS_LINE",
        "ENTRANCE_LINE_CROSS",
        "ENTRANCE_CROSS",
        "DIRECTIONAL_ENTRY",
        "DIRECTIONAL_EXIT",
    }

    inward_directions = {
        "IN",
        "ENTRY",
        "ENTER",
        "INSIDE",
        "INWARD",
    }

    outward_directions = {
        "OUT",
        "EXIT",
        "LEAVE",
        "OUTSIDE",
        "OUTWARD",
    }

    canonical_passthrough_events = {
        "ENTRY",
        "EXIT",
        "ZONE_ENTER",
        "ZONE_EXIT",
        "ZONE_DWELL",
        "BILLING_QUEUE_JOIN",
        "BILLING_QUEUE_EXIT",
        "BILLING_QUEUE_ABANDON",
        "REENTRY",
    }

    # 1. Future-proof directional entrance-line support.
    if event_type_upper in line_cross_event_types:
        if direction_upper in inward_directions:
            event["event_type"] = "ENTRY"
            event["zone_id"] = None

        elif direction_upper in outward_directions:
            event["event_type"] = "EXIT"
            event["zone_id"] = None

        else:
            if DEBUG_EVENTS:
                print(
                    "[WARN] Dropping line-cross event with unknown direction: "
                    f"store={store_id}, camera={camera_id}, event={event}"
                )
            return {}

    # 2. Current fallback entry logic.
    elif event_type_upper == "ZONE_ENTER" and zone_id == "ENTRY_DOOR":
        event["event_type"] = "ENTRY"
        event["zone_id"] = None

    elif event_type_upper == "ZONE_EXIT" and zone_id == "ENTRY_DOOR":
        event["event_type"] = "EXIT"
        event["zone_id"] = None

    # 3. Drop entry dwell. Entry door should not appear in dwell metrics.
    elif event_type_upper == "ZONE_DWELL" and zone_id == "ENTRY_DOOR":
        return {}

    # 4. Legacy billing mapping, if tracker emits billing as zone events.
    elif event_type_upper == "ZONE_ENTER" and zone_id == "BILLING_QUEUE":
        event["event_type"] = "BILLING_QUEUE_JOIN"

    elif event_type_upper == "ZONE_EXIT" and zone_id == "BILLING_QUEUE":
        event["event_type"] = "BILLING_QUEUE_EXIT"

    # 5. Already-canonical events pass through.
    elif event_type_upper in canonical_passthrough_events:
        event["event_type"] = event_type_upper

        if event_type_upper in {"ENTRY", "EXIT", "REENTRY"}:
            event["zone_id"] = None

    else:
        if DEBUG_EVENTS:
            print(
                "[WARN] Dropping unsupported tracker event: "
                f"store={store_id}, camera={camera_id}, event={event}"
            )
        return {}

    event["metadata"] = _build_metadata(event)

    return event


# ---------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------

def validate_store_configs():
    """
    Validate configured video paths before loading the model.
    Missing videos are warned early instead of being discovered mid-run.
    """

    missing_files = []

    for store_id, camera_configs in STORE_CONFIGS.items():
        for camera_id, camera_config in camera_configs.items():
            video_path = Path(camera_config["video"])

            if not video_path.exists():
                missing_files.append(
                    {
                        "store_id": store_id,
                        "camera_id": camera_id,
                        "video": str(video_path),
                    }
                )

    if missing_files:
        print("\nWARNING: Some configured video files are missing:")

        for item in missing_files:
            print(
                f"- store={item['store_id']}, "
                f"camera={item['camera_id']}, "
                f"path={item['video']}"
            )

        print()


# ---------------------------------------------------------------------
# Processing
# ---------------------------------------------------------------------

def process_camera(
    detector: PersonDetector,
    poster: EventPoster,
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

        # FRAME_SKIP=5 now processes frames 1, 6, 11, ...
        if FRAME_SKIP > 1 and (frame_index - 1) % FRAME_SKIP != 0:
            continue

        processed_frames += 1

        tracks = get_tracks_from_detector(detector, frame)

        if tracks is None:
            tracks = []

        events = get_events_from_tracker(tracker, tracks)

        if events is None:
            events = []

        if DEBUG_EVENTS and processed_frames % 100 == 0:
            print(
                f"[DEBUG] {store_id}/{camera_id}: "
                f"tracks={len(tracks)}, raw_events={len(events)}"
            )

        for event in events:
            if not isinstance(event, dict):
                continue

            if DEBUG_EVENTS and emitted_events < 20:
                print(f"[RAW EVENT DEBUG] {store_id}/{camera_id}: {event}")

            normalized_event = normalize_business_event(
                event=event,
                store_id=store_id,
                camera_id=camera_id,
                has_entrance_line=entrance_line is not None,
            )

            if not normalized_event:
                continue

            poster.add_event(normalized_event)
            emitted_events += 1

        if processed_frames % 500 == 0:
            print(
                f"[{store_id}/{camera_id}] "
                f"frames_read={frame_index}, "
                f"frames_processed={processed_frames}, "
                f"events_emitted={emitted_events}"
            )

    cap.release()
    poster.flush_all()

    print(
        f"Finished {store_id}/{camera_id}: "
        f"frames_read={frame_index}, "
        f"frames_processed={processed_frames}, "
        f"events_emitted={emitted_events}"
    )


def process_store(
    detector: PersonDetector,
    poster: EventPoster,
    store_id: str,
    camera_configs: Dict[str, Dict[str, Any]],
):
    print("\n" + "#" * 80)
    print(f"STARTING STORE: {store_id}")
    print("#" * 80)

    for camera_id, camera_config in camera_configs.items():
        process_camera(
            detector=detector,
            poster=poster,
            store_id=store_id,
            camera_id=camera_id,
            camera_config=camera_config,
        )

    poster.flush_all()

    print("\n" + "#" * 80)
    print(f"FINISHED STORE: {store_id}")
    print("#" * 80)


def main():
    print("Starting CV pipeline...")
    print(f"API_URL={API_URL}")
    print(f"YOLO_MODEL={YOLO_MODEL}")
    print(f"FRAME_SKIP={FRAME_SKIP}")
    print(f"BATCH_SIZE={BATCH_SIZE}")
    print(f"DEBUG_EVENTS={DEBUG_EVENTS}")
    print(f"ONLY_STORE={ONLY_STORE}")

    validate_store_configs()

    detector = build_detector()
    poster = EventPoster(API_URL, batch_size=BATCH_SIZE)

    for store_id, camera_configs in STORE_CONFIGS.items():
        if ONLY_STORE and store_id != ONLY_STORE:
            continue

        process_store(
            detector=detector,
            poster=poster,
            store_id=store_id,
            camera_configs=camera_configs,
        )

    poster.flush_all()

    print("\nCV pipeline finished.")
    print(f"Total posted events accepted: {poster.total_posted}")
    print(f"Failed batches: {poster.total_failed_batches}")

    if poster.buffer:
        print(f"WARNING: Unsent events remaining in buffer: {len(poster.buffer)}")


if __name__ == "__main__":
    main()