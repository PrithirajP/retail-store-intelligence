import cv2
import uuid
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class StoreTrackerState:
    """
    In-memory state machine for one camera feed.

    Responsibilities:
    - Convert tracked foot-points into zone transition events.
    - Track active dwell state per visitor.
    - Mark likely staff using BEHIND_COUNTER dwell heuristic.
    - Emit billing queue join/exit events.
    - Attach Event Schema v1.2 metadata:
        - queue_depth
        - sku_zone
        - session_seq
    """

    def __init__(self, store_id: str, camera_id: str, zones: dict, entrance_line: list):
        self.store_id = store_id
        self.camera_id = camera_id
        self.zones = zones
        self.entrance_line = entrance_line

        # visitor_id -> {zone_name: entry_datetime}
        self.active_dwells = {}

        # visitor_ids permanently marked as staff
        self.staff_profiles = set()

        # visitor_id -> consecutive frames inside BEHIND_COUNTER
        self.staff_counter_frames = {}

        # visitor_id -> local event sequence number
        self.session_seq = {}

    def _is_inside(self, point, polygon) -> bool:
        """
        Returns True if point (x, y) is inside the OpenCV polygon.
        """
        return cv2.pointPolygonTest(polygon, point, False) >= 0

    def _next_session_seq(self, visitor_id: str) -> int:
        """
        Returns the next local sequence number for a visitor.

        Note:
        This is camera-local/session-state-local in the current implementation.
        A future global Re-ID layer can replace this with global session sequencing.
        """
        self.session_seq[visitor_id] = self.session_seq.get(visitor_id, 0) + 1
        return self.session_seq[visitor_id]

    def _current_queue_depth(self) -> int:
        """
        Calculates current billing queue depth from active dwell state.

        This is camera-local queue depth for the BILLING_QUEUE polygon.
        """
        depth = 0
        for zone_map in self.active_dwells.values():
            if "BILLING_QUEUE" in zone_map:
                depth += 1
        return depth

    def _build_event(
        self,
        visitor_id: str,
        event_type: str,
        zone_id: str,
        timestamp_iso: str,
        is_staff: bool,
        confidence: float,
        dwell_ms: int = None,
        queue_depth: int = None,
        sku_zone: str = None,
    ) -> dict:
        """
        Builds one JSON-ready event dictionary using Event Schema v1.2.
        """

        return {
            "event_id": str(uuid.uuid4()),
            "store_id": self.store_id,
            "camera_id": self.camera_id,
            "visitor_id": visitor_id,
            "timestamp": timestamp_iso,
            "event_type": event_type,
            "zone_id": zone_id,
            "dwell_ms": dwell_ms,
            "is_staff": is_staff,
            "confidence": confidence,
            "metadata": {
                "queue_depth": queue_depth,
                "sku_zone": sku_zone if sku_zone is not None else zone_id,
                "session_seq": self._next_session_seq(visitor_id),
            },
        }

    def process_frame_tracks(self, tracks):
        """
        Takes a list of tracks from YOLO/ByteTrack for a single frame.

        Expected track format:
        [
            {
                "visitor_id": "VIS_1",
                "point": (x, y),
                "conf": 0.88
            },
            ...
        ]

        Returns:
            List[dict]: JSON-ready event payloads.
        """

        batch_events = []
        current_time = datetime.now(timezone.utc)
        current_time_iso = current_time.isoformat()

        for track in tracks:
            vid = track["visitor_id"]
            point = track["point"]
            conf = float(track["conf"])

            if vid not in self.active_dwells:
                self.active_dwells[vid] = {}

            # ------------------------------------------------------------
            # 1. Staff exclusion heuristic
            # ------------------------------------------------------------
            behind_counter_poly = self.zones.get("BEHIND_COUNTER")

            if behind_counter_poly is not None and self._is_inside(point, behind_counter_poly):
                self.staff_counter_frames[vid] = self.staff_counter_frames.get(vid, 0) + 1

                # If visitor stays behind counter for more than 30 consecutive frames,
                # permanently mark them as staff for this camera-local tracker state.
                if self.staff_counter_frames[vid] > 30:
                    self.staff_profiles.add(vid)
            else:
                self.staff_counter_frames[vid] = 0

            is_staff = vid in self.staff_profiles

            # ------------------------------------------------------------
            # 2. Zone transition and dwell state machine
            # ------------------------------------------------------------
            for zone_name, polygon in self.zones.items():
                # BEHIND_COUNTER is used for staff detection, not customer journey events.
                if zone_name == "BEHIND_COUNTER":
                    continue

                in_zone = self._is_inside(point, polygon)
                was_in_zone = zone_name in self.active_dwells[vid]

                # --------------------------------------------------------
                # Transition: ENTERED ZONE
                # --------------------------------------------------------
                if in_zone and not was_in_zone:
                    self.active_dwells[vid][zone_name] = current_time

                    if zone_name == "BILLING_QUEUE":
                        event_type = "BILLING_QUEUE_JOIN"
                        queue_depth = self._current_queue_depth()
                    else:
                        event_type = "ZONE_ENTER"
                        queue_depth = None

                    batch_events.append(
                        self._build_event(
                            visitor_id=vid,
                            event_type=event_type,
                            zone_id=zone_name,
                            timestamp_iso=current_time_iso,
                            is_staff=is_staff,
                            confidence=conf,
                            dwell_ms=None,
                            queue_depth=queue_depth,
                            sku_zone=zone_name,
                        )
                    )

                # --------------------------------------------------------
                # Transition: EXITED ZONE
                # --------------------------------------------------------
                elif not in_zone and was_in_zone:
                    entry_time = self.active_dwells[vid].pop(zone_name)
                    dwell_ms = int((current_time - entry_time).total_seconds() * 1000)

                    if zone_name == "BILLING_QUEUE":
                        event_type = "BILLING_QUEUE_EXIT"
                        queue_depth = self._current_queue_depth()
                    else:
                        event_type = "ZONE_EXIT"
                        queue_depth = None

                    batch_events.append(
                        self._build_event(
                            visitor_id=vid,
                            event_type=event_type,
                            zone_id=zone_name,
                            timestamp_iso=current_time_iso,
                            is_staff=is_staff,
                            confidence=conf,
                            dwell_ms=None,
                            queue_depth=queue_depth,
                            sku_zone=zone_name,
                        )
                    )

                    # Emit dwell event for product zones.
                    # Billing queue timing will be handled by the API queue logic later.
                    if zone_name != "BILLING_QUEUE" and dwell_ms > 0:
                        batch_events.append(
                            self._build_event(
                                visitor_id=vid,
                                event_type="ZONE_DWELL",
                                zone_id=zone_name,
                                timestamp_iso=current_time_iso,
                                is_staff=is_staff,
                                confidence=conf,
                                dwell_ms=dwell_ms,
                                queue_depth=None,
                                sku_zone=zone_name,
                            )
                        )

        return batch_events