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

# TODO: Replace these with the actual (x,y) pixel coordinates from your layout image!
ZONES = {
    "BILLING": np.array([[500, 200], [800, 200], [800, 400], [500, 400]], np.int32),
    "BEHIND_COUNTER": np.array([[550, 150], [750, 150], [750, 190], [550, 190]], np.int32)
}

def is_inside_polygon(point, polygon):
    """Checks if an (x,y) point is inside a polygon using OpenCV."""
    # pointPolygonTest returns > 0 if inside, 0 if on edge, < 0 if outside
    return cv2.pointPolygonTest(polygon, point, False) >= 0

def process_video(video_path: str, camera_id: str):
    """Processes a single video feed and POSTs events to the API."""
    logger.info(f"Loading YOLOv8 model for {video_path}...")
    # YOLOv8n (nano) is fastest. 
    model = YOLO("yolov8n.pt") 
    
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        logger.error(f"Failed to open video file: {video_path}")
        return

    fps = cap.get(cv2.CAP_PROP_FPS)
    frame_count = 0
    active_tracks = {}

    while cap.isOpened():
        success, frame = cap.read()
        if not success:
            break
            
        frame_count += 1
        
        # Performance Hack: Process every 3rd frame to simulate ~5-10 FPS
        if frame_count % 3 != 0:
            continue

        # Run detection and tracking (persist=True enables tracking between frames)
        # classes=[0] ensures we ONLY detect people
        results = model.track(frame, persist=True, classes=[0], verbose=False)
        
        batch_events = []
        current_time = datetime.now(timezone.utc).isoformat()

        if results[0].boxes is not None and results[0].boxes.id is not None:
            boxes = results[0].boxes.xyxy.cpu().numpy()
            track_ids = results[0].boxes.id.cpu().numpy()
            confidences = results[0].boxes.conf.cpu().numpy()

            for box, track_id, conf in zip(boxes, track_ids, confidences):
                x1, y1, x2, y2 = box
                
                # Use the bottom-center of the bounding box (where their feet are)
                foot_x = int((x1 + x2) / 2)
                foot_y = int(y2)
                point = (foot_x, foot_y)
                
                visitor_id = f"VIS_{int(track_id)}"
                
                # --- Staff Heuristic Check ---
                is_staff = is_inside_polygon(point, ZONES["BEHIND_COUNTER"])

                # --- Billing Zone Check ---
                in_billing = is_inside_polygon(point, ZONES["BILLING"])
                
                # State Machine: Did they just enter or exit the billing zone?
                was_in_billing = active_tracks.get(visitor_id, False)
                
                if in_billing and not was_in_billing:
                    # Trigger Entry Event
                    batch_events.append({
                        "event_id": str(uuid.uuid4()),
                        "store_id": STORE_ID,
                        "camera_id": camera_id,  # Dynamically assigned from filename
                        "visitor_id": visitor_id,
                        "timestamp": current_time,
                        "event_type": "BILLING_QUEUE_JOIN",
                        "zone_id": "BILLING",
                        "is_staff": is_staff,
                        "confidence": float(conf)
                    })
                elif not in_billing and was_in_billing:
                    # Trigger Exit Event
                    batch_events.append({
                        "event_id": str(uuid.uuid4()),
                        "store_id": STORE_ID,
                        "camera_id": camera_id,  # Dynamically assigned from filename
                        "visitor_id": visitor_id,
                        "timestamp": current_time,
                        "event_type": "BILLING_QUEUE_EXIT",
                        "zone_id": "BILLING",
                        "is_staff": is_staff,
                        "confidence": float(conf)
                    })

                # Update state
                active_tracks[visitor_id] = in_billing

        # If we found events in this frame, POST them to our API
        if batch_events:
            try:
                # We use http://store-api:8000 because Docker networks resolve the service name
                response = requests.post(API_URL, json={"events": batch_events})
                logger.info(f"[{camera_id}] Posted {len(batch_events)} events. API Response: {response.status_code}")
            except Exception as e:
                logger.error(f"[{camera_id}] Failed to post to API: {e}")

    cap.release()
    logger.info(f"Video processing complete for {camera_id}.")

def run_multi_camera_pipeline(data_directory: str):
    """
    Scans the data directory for video files and processes them sequentially
    to prevent memory crashes in Docker.
    """
    logger.info(f"Scanning {data_directory} for camera feeds...")
    
    # Look for all .mp4 files (update extension if your files are .avi or .mkv)
    video_files = glob.glob(os.path.join(data_directory, "*.mp4"))
    
    if not video_files:
        logger.warning("No video files found! Please place them in the data/ folder.")
        return

    logger.info(f"Found {len(video_files)} camera feeds. Starting batch processing.")

    for video_path in video_files:
        # Extract Camera ID from the filename (e.g., 'CAM_01.mp4' -> 'CAM_01')
        filename = os.path.basename(video_path)
        camera_id = os.path.splitext(filename)[0] 
        
        logger.info(f"========================================")
        logger.info(f"INITIALIZING PIPELINE FOR: {camera_id}")
        logger.info(f"========================================")
        
        # Process the video stream
        process_video(video_path, camera_id)

    logger.info("All camera feeds have been successfully processed!")

if __name__ == "__main__":
    # In Docker, the local ./data folder is mounted to /app/data
    run_multi_camera_pipeline("/app/data")