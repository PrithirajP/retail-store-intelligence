import cv2
import uuid
import logging
from datetime import datetime, timezone
from math import sqrt
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


class StoreTrackerState:
    """
    In-memory state machine for one camera feed.

    Responsibilities:
    - Convert tracked foot-points into zone transition events.
    - Track active dwell state per visitor.
    - Emit directional entrance-line crossing events.
    - Emit lightweight distance-based REENTRY events.
    - Mark likely staff using BEHIND_COUNTER dwell heuristic.
    - Emit billing queue join/exit events.
    - Attach Event Schema v1.2 metadata:
        - queue_depth
        - sku_zone
        - session_seq
    """

    def __init__(
        self,
        store_id: str,
        camera_id: str,
        zones: dict,
        entrance_line: Optional[Tuple[Tuple[int, int], Tuple[int, int]]] = None,
        reentry_window_seconds: int = 600,
        reentry_distance_px: int = 250,
    ):
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

        # raw tracker visitor_id -> previous foot point
        self.last_points = {}

        # raw tracker visitor_id -> global/lightweight visitor_id
        self.track_to_global_id = {}

        # recent exits used for lightweight re-entry matching
        self.recent_exits = []

        self.reentry_window_seconds = reentry_window_seconds
        self.reentry_distance_px = reentry_distance_px

    # ------------------------------------------------------------------
    # Geometry helpers
    # ------------------------------------------------------------------

    def _is_inside(self, point, polygon) -> bool:
        """
        Returns True if point (x, y) is inside the OpenCV polygon.
        """
        return cv2.pointPolygonTest(polygon, point, False) >= 0

    def _line_side(self, point, line) -> float:
        """
        Signed side of a point relative to a directed line.
        """

        (x1, y1), (x2, y2) = line
        px, py = point

        return (x2 - x1) * (py - y1) - (y2 - y1) * (px - x1)

    def _point_between_line_bounds(self, point, line, tolerance: int = 20) -> bool:
        """
        Checks whether the point lies within the bounding box of the entrance line.

        This prevents the infinite mathematical line from triggering crossings far
        away from the actual doorway segment.
        """

        (x1, y1), (x2, y2) = line
        px, py = point

        min_x = min(x1, x2) - tolerance
        max_x = max(x1, x2) + tolerance
        min_y = min(y1, y2) - tolerance
        max_y = max(y1, y2) + tolerance

        return min_x <= px <= max_x and min_y <= py <= max_y

    def _crosses_entrance_line(self, previous_point, current_point) -> bool:
        """
        Detects whether movement from previous_point to current_point crossed
        the configured entrance line.
        """

        if self.entrance_line is None:
            return False

        prev_side = self._line_side(previous_point, self.entrance_line)
        curr_side = self._line_side(current_point, self.entrance_line)

        if prev_side == 0 and curr_side == 0:
            return False

        crossed_sides = (prev_side <= 0 < curr_side) or (prev_side >= 0 > curr_side)

        if not crossed_sides:
            return False

        mid_point = (
            int((previous_point[0] + current_point[0]) / 2),
            int((previous_point[1] + current_point[1]) / 2),
        )

        return self._point_between_line_bounds(mid_point, self.entrance_line)

    def _infer_crossing_direction(self, previous_point, current_point, entry_polygon) -> str:
        """
        Infers IN/OUT direction for an entrance-line crossing.

        Preferred rule:
        - outside ENTRY_DOOR -> inside ENTRY_DOOR = IN
        - inside ENTRY_DOOR -> outside ENTRY_DOOR = OUT

        Fallback rule:
        - use signed line side change.
        """

        prev_inside = self._is_inside(previous_point, entry_polygon)
        curr_inside = self._is_inside(current_point, entry_polygon)

        if not prev_inside and curr_inside:
            return "IN"

        if prev_inside and not curr_inside:
            return "OUT"

        prev_side = self._line_side(previous_point, self.entrance_line)
        curr_side = self._line_side(current_point, self.entrance_line)

        if prev_side > 0 and curr_side <= 0:
            return "IN"

        return "OUT"

    def _distance(self, point_a, point_b) -> float:
        return sqrt(
            (point_a[0] - point_b[0]) ** 2
            + (point_a[1] - point_b[1]) ** 2
        )

    # ------------------------------------------------------------------
    # Lightweight Re-ID helpers
    # ------------------------------------------------------------------

    def _prune_recent_exits(self, current_time: datetime):
        """
        Removes old exit candidates outside the re-entry window.
        """

        self.recent_exits = [
            item
            for item in self.recent_exits
            if (current_time - item["exit_time"]).total_seconds()
            <= self.reentry_window_seconds
        ]

    def _remember_exit(self, visitor_id: str, point, current_time: datetime):
        """
        Store a short-lived exit candidate for later REENTRY matching.
        """

        self._prune_recent_exits(current_time)

        self.recent_exits.append(
            {
                "visitor_id": visitor_id,
                "exit_point": point,
                "exit_time": current_time,
            }
        )

    def _match_reentry_candidate(self, point, current_time: datetime) -> Optional[str]:
        """
        Matches an inward crossing against recent exits.

        This is a lightweight distance-based Re-ID baseline. It does not use
        appearance embeddings. It is intended to reduce re-entry double counting
        at the same configured entrance camera.
        """

        self._prune_recent_exits(current_time)

        if not self.recent_exits:
            return None

        best_index = None
        best_distance = None

        for index, candidate in enumerate(self.recent_exits):
            distance = self._distance(point, candidate["exit_point"])

            if distance > self.reentry_distance_px:
                continue

            if best_distance is None or distance < best_distance:
                best_index = index
                best_distance = distance

        if best_index is None:
            return None

        matched = self.recent_exits.pop(best_index)
        return matched["visitor_id"]

    # ------------------------------------------------------------------
    # Event helpers
    # ------------------------------------------------------------------

    def _next_session_seq(self, visitor_id: str) -> int:
        self.session_seq[visitor_id] = self.session_seq.get(visitor_id, 0) + 1
        return self.session_seq[visitor_id]

    def _current_queue_depth(self) -> int:
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
        direction: str = None,
    ) -> dict:
        """
        Builds one JSON-ready event dictionary using Event Schema v1.2.
        """

        event = {
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

        if direction is not None:
            event["direction"] = direction

        return event

    # ------------------------------------------------------------------
    # Main tracking state machine
    # ------------------------------------------------------------------

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

        if tracks is None:
            tracks = []

        batch_events = []
        current_time = datetime.now(timezone.utc)
        current_time_iso = current_time.isoformat()

        for track in tracks:
            raw_vid = track["visitor_id"]
            point = track["point"]
            conf = float(track["conf"])

            previous_point = self.last_points.get(raw_vid)

            # If a raw tracker ID was already matched to an earlier global ID,
            # use that global ID for all downstream events.
            vid = self.track_to_global_id.get(raw_vid, raw_vid)

            if vid not in self.active_dwells:
                self.active_dwells[vid] = {}

            # ------------------------------------------------------------
            # 1. Staff exclusion heuristic
            # ------------------------------------------------------------
            behind_counter_poly = self.zones.get("BEHIND_COUNTER")

            if behind_counter_poly is not None and self._is_inside(point, behind_counter_poly):
                self.staff_counter_frames[vid] = self.staff_counter_frames.get(vid, 0) + 1

                if self.staff_counter_frames[vid] > 30:
                    self.staff_profiles.add(vid)
            else:
                self.staff_counter_frames[vid] = 0

            is_staff = vid in self.staff_profiles

            # ------------------------------------------------------------
            # 2. Zone transition and dwell state machine
            # ------------------------------------------------------------
            for zone_name, polygon in self.zones.items():
                if zone_name == "BEHIND_COUNTER":
                    continue

                in_zone = self._is_inside(point, polygon)
                was_in_zone = zone_name in self.active_dwells[vid]

                # --------------------------------------------------------
                # Special handling: directional entrance-line crossing
                # --------------------------------------------------------
                if zone_name == "ENTRY_DOOR" and self.entrance_line is not None:
                    if previous_point is not None and self._crosses_entrance_line(
                        previous_point,
                        point,
                    ):
                        direction = self._infer_crossing_direction(
                            previous_point,
                            point,
                            polygon,
                        )

                        if direction == "OUT":
                            self._remember_exit(
                                visitor_id=vid,
                                point=point,
                                current_time=current_time,
                            )

                            batch_events.append(
                                self._build_event(
                                    visitor_id=vid,
                                    event_type="LINE_CROSS",
                                    zone_id="ENTRY_DOOR",
                                    timestamp_iso=current_time_iso,
                                    is_staff=is_staff,
                                    confidence=conf,
                                    dwell_ms=None,
                                    queue_depth=None,
                                    sku_zone="ENTRY_DOOR",
                                    direction="OUT",
                                )
                            )

                        else:
                            matched_visitor_id = self._match_reentry_candidate(
                                point=point,
                                current_time=current_time,
                            )

                            if matched_visitor_id is not None:
                                self.track_to_global_id[raw_vid] = matched_visitor_id
                                vid = matched_visitor_id

                                if vid not in self.active_dwells:
                                    self.active_dwells[vid] = {}

                                batch_events.append(
                                    self._build_event(
                                        visitor_id=vid,
                                        event_type="REENTRY",
                                        zone_id=None,
                                        timestamp_iso=current_time_iso,
                                        is_staff=is_staff,
                                        confidence=conf,
                                        dwell_ms=None,
                                        queue_depth=None,
                                        sku_zone=None,
                                        direction=None,
                                    )
                                )

                            else:
                                batch_events.append(
                                    self._build_event(
                                        visitor_id=vid,
                                        event_type="LINE_CROSS",
                                        zone_id="ENTRY_DOOR",
                                        timestamp_iso=current_time_iso,
                                        is_staff=is_staff,
                                        confidence=conf,
                                        dwell_ms=None,
                                        queue_depth=None,
                                        sku_zone="ENTRY_DOOR",
                                        direction="IN",
                                    )
                                )

                    # Maintain ENTRY_DOOR dwell state internally, but do not
                    # emit ENTRY_DOOR dwell events.
                    if in_zone and not was_in_zone:
                        self.active_dwells[vid][zone_name] = current_time

                    elif not in_zone and was_in_zone:
                        self.active_dwells[vid].pop(zone_name, None)

                    continue

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

            self.last_points[raw_vid] = point

        return batch_events