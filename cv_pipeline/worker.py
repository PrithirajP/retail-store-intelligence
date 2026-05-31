import cv2
import numpy as np
import requests
import uuid
import logging
import os
import glob
from datetime import datetime, timezone
from ultralytics import YOLO

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- CONFIGURATION ---
API_URL = "http://store-api:8000/events/ingest"
STORE_ID = "ST1008" # From your Brigade_Bangalore CSV

# TODO: Replace these placeholder arrays using the output from your zone_mapper.py!
ZONES = {
    # Core Zones
    "BEHIND_COUNTER": np.array([[399, 1068], [220, 759], [222, 608], [300, 472], [375, 482], [402, 547], [568, 252], [740, 263], [844, 291], [966, 291], [1114, 308], [1188, 312], [1275, 1069], [396, 1065]], np.int32),
    "BILLING": np.array([[0, 622], [76, 508], [200, 492], [396, 432], [234, 840], [405, 1078], [2, 1076], [0, 624]], np.int32),
    
    # Browsing Zones (Add as many as you need)
    "SKINCARE": np.array([[100, 100], [300, 100], [300, 300], [100, 300]], np.int32),
    "MAKEUP": np.array([[850, 100], [1050, 100], [1050, 300], [850, 300]], np.int32)
}

def is_inside_polygon(point, polygon):
    """Checks if an (x,y) point is inside a polygon using OpenCV."""
    return cv2.pointPolygonTest(polygon, point, False) >= 0

def process_video(video_path: str, camera_id: str):
    """Processes a single video feed and POSTs events to the API."""
    logger.info(f"Loading YOLOv8 model for {video_path}...")
    model = YOLO("yolov8n.pt") 
    
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        logger.error(f"Failed to open video file: {video_path}")
        return

    frame_count = 0
    active_tracks = {}

    while cap.isOpened():
        success, frame = cap.read()
        if not success:
            break
            
        frame_count += 1
        
        # Performance Hack: Process every 3rd frame to simulate ~5 FPS
        if frame_count % 3 != 0:
            continue

        results = model.track(frame, persist=True, classes=[0], verbose=False)
        
        batch_events = []
        current_time = datetime.now(timezone.utc).isoformat()

        if results[0].boxes is not None and results[0].boxes.id is not None:
            boxes = results[0].boxes.xyxy.cpu().numpy()
            track_ids = results[0].boxes.id.cpu().numpy()
            confidences = results[0].boxes.conf.cpu().numpy()

            for box, track_id, conf in zip(boxes, track_ids, confidences):
                x1, y1, x2, y2 = box
                
                # Bottom-center of bounding box (feet)
                foot_x = int((x1 + x2) / 2)
                foot_y = int(y2)
                point = (foot_x, foot_y)
                
                visitor_id = f"VIS_{int(track_id)}"
                
                # 1. Staff Heuristic Check
                is_staff = is_inside_polygon(point, ZONES["BEHIND_COUNTER"])

                # 2. Dynamic Zone Checks
                for zone_name, polygon in ZONES.items():
                    if zone_name == "BEHIND_COUNTER":
                        continue # Already handled above
                        
                    in_current_zone = is_inside_polygon(point, polygon)
                    
                    # Create a unique state key per visitor per zone (e.g., "VIS_5_SKINCARE")
                    state_key = f"{visitor_id}_{zone_name}"
                    was_in_zone = active_tracks.get(state_key, False)
                    
                    # Determine event type based on the zone
                    if zone_name == "BILLING":
                        entry_event = "BILLING_QUEUE_JOIN"
                        exit_event = "BILLING_QUEUE_EXIT"
                    else:
                        entry_event = "ZONE_ENTER"
                        exit_event = "ZONE_EXIT"

                    # State Machine: Trigger Entry
                    if in_current_zone and not was_in_zone:
                        batch_events.append({
                            "event_id": str(uuid.uuid4()),
                            "store_id": STORE_ID,
                            "camera_id": camera_id,
                            "visitor_id": visitor_id,
                            "timestamp": current_time,
                            "event_type": entry_event,
                            "zone_id": zone_name,
                            "is_staff": is_staff,
                            "confidence": float(conf)
                        })
                        active_tracks[state_key] = True

                    # State Machine: Trigger Exit
                    elif not in_current_zone and was_in_zone:
                        batch_events.append({
                            "event_id": str(uuid.uuid4()),
                            "store_id": STORE_ID,
                            "camera_id": camera_id,
                            "visitor_id": visitor_id,
                            "timestamp": current_time,
                            "event_type": exit_event,
                            "zone_id": zone_name,
                            "is_staff": is_staff,
                            "confidence": float(conf)
                        })
                        active_tracks[state_key] = False

        # POST batch to API
        if batch_events:
            try:
                response = requests.post(API_URL, json={"events": batch_events})
                logger.info(f"[{camera_id}] Posted {len(batch_events)} events. API Response: {response.status_code}")
            except Exception as e:
                logger.error(f"[{camera_id}] Failed to post to API: {e}")

    cap.release()
    logger.info(f"Video processing complete for {camera_id}.")


def run_multi_camera_pipeline(data_directory: str):
    """Scans the data directory and processes all .mp4 files sequentially."""
    logger.info(f"Scanning {data_directory} for camera feeds...")
    video_files = glob.glob(os.path.join(data_directory, "*.mp4"))
    
    if not video_files:
        logger.warning("No video files found! Please place them in the data/ folder.")
        return

    logger.info(f"Found {len(video_files)} camera feeds. Starting batch processing.")

    for video_path in video_files:
        filename = os.path.basename(video_path)
        camera_id = os.path.splitext(filename)[0] 
        
        logger.info(f"========================================")
        logger.info(f"INITIALIZING PIPELINE FOR: {camera_id}")
        logger.info(f"========================================")
        
        process_video(video_path, camera_id)

    logger.info("All camera feeds have been successfully processed!")

if __name__ == "__main__":
    # In Docker, the local ./data folder is mounted to /app/data
    run_multi_camera_pipeline("/app/data")