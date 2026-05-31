import cv2
import uuid
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

class StoreTrackerState:
    def __init__(self, store_id: str, camera_id: str, zones: dict, entrance_line: list):
        self.store_id = store_id
        self.camera_id = camera_id
        self.zones = zones                # Dictionary of zone names to np.arrays
        self.entrance_line = entrance_line # [ (x1, y1), (x2, y2) ]
        
        # State memory: visitor_id -> { "zone_name": entry_datetime }
        self.active_dwells = {}
        # Memory of staff: set of visitor_ids permanently marked as staff
        self.staff_profiles = set()
        # Memory of consecutive frames a visitor is behind the counter
        self.staff_counter_frames = {}

    def _is_inside(self, point, polygon):
        """Returns True if point (x,y) is inside the OpenCV polygon."""
        return cv2.pointPolygonTest(polygon, point, False) >= 0

    def process_frame_tracks(self, tracks):
        """
        Takes a list of tracks from YOLO/ByteTrack for a single frame.
        tracks format: [ {"visitor_id": "VIS_1", "point": (x,y), "conf": 0.88}, ... ]
        """
        batch_events = []
        current_time = datetime.now(timezone.utc)
        current_time_iso = current_time.isoformat()

        for track in tracks:
            vid = track["visitor_id"]
            point = track["point"]
            conf = track["conf"]

            if vid not in self.active_dwells:
                self.active_dwells[vid] = {}

            # --- 1. STAFF EXCLUSION HEURISTIC ---
            behind_counter_poly = self.zones.get("BEHIND_COUNTER")
            
            # Only check if this specific camera actually has a counter zone mapped
            if behind_counter_poly is not None and self._is_inside(point, behind_counter_poly):
                self.staff_counter_frames[vid] = self.staff_counter_frames.get(vid, 0) + 1
                # If they spend > 30 frames behind the counter, mark as permanent staff
                if self.staff_counter_frames[vid] > 30:
                    self.staff_profiles.add(vid)
            else:
                self.staff_counter_frames[vid] = 0 # Reset if they step out (or if no counter exists)

            is_staff = vid in self.staff_profiles

            # --- 2. ZONE DWELL STATE MACHINE ---
            for zone_name, polygon in self.zones.items():
                if zone_name == "BEHIND_COUNTER":
                    continue # Handled above

                in_zone = self._is_inside(point, polygon)
                was_in_zone = zone_name in self.active_dwells[vid]

                event_base = {
                    "event_id": str(uuid.uuid4()),
                    "store_id": self.store_id,
                    "camera_id": self.camera_id,
                    "visitor_id": vid,
                    "timestamp": current_time_iso,
                    "is_staff": is_staff,
                    "confidence": conf
                }

                # Transition: ENTERED ZONE
                if in_zone and not was_in_zone:
                    self.active_dwells[vid][zone_name] = current_time
                    
                    event_type = "BILLING_QUEUE_JOIN" if zone_name == "BILLING_QUEUE" else "ZONE_ENTER"
                    batch_events.append({**event_base, "event_type": event_type, "zone_id": zone_name})

                # Transition: EXITED ZONE
                elif not in_zone and was_in_zone:
                    entry_time = self.active_dwells[vid].pop(zone_name)
                    dwell_ms = int((current_time - entry_time).total_seconds() * 1000)

                    event_type = "BILLING_QUEUE_EXIT" if zone_name == "BILLING_QUEUE" else "ZONE_EXIT"
                    batch_events.append({**event_base, "event_type": event_type, "zone_id": zone_name})

                    # Emit DWELL event for analytics (skip for billing queue)
                    if zone_name != "BILLING_QUEUE" and dwell_ms > 0:
                        batch_events.append({
                            **event_base, 
                            "event_type": "ZONE_DWELL", 
                            "zone_id": zone_name, 
                            "dwell_ms": dwell_ms
                        })

        return batch_events