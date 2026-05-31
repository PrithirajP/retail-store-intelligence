import cv2
import numpy as np
import logging
from detector import PersonDetector
from tracker_state import StoreTrackerState
from event_emitter import EventEmitter
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- YOUR CUSTOM CALIBRATION DATA ---
STORE_ID = "ST1008"

# Map the video files to the zones visible in them
CAMERA_CONFIGS = {
    "CAM_ENTRANCE": {
        "video": "../data/CAM_03.mp4", 
        "zones": {
            # We treat the entry door as a zone. Entering it = Store Entry.
            "ENTRY_DOOR": np.array([[279, 488], [993, 0], [1434, 6], [1702, 21], [1508, 438], [1316, 693], [1173, 892], [1018, 1071], [472, 1072], [278, 494]], np.int32)
        }
    },
    "CAM_BILLING": {
        "video": "../data/CAM_05.mp4", #
        "zones": {
            "BEHIND_COUNTER": np.array([[408, 1077], [246, 774], [567, 258], [1215, 333], [1362, 1062], [423, 1077]], np.int32),
            "BILLING_QUEUE": np.array([[204, 732], [520, 238], [170, 234], [3, 514], [200, 730]], np.int32)
        }
    },
    "CAM_MAKEUP": {
        "video": "../data/CAM_02.mp4",
        "zones": {
            "MAKEUP": np.array([[4, 182], [519, 90], [1917, 190], [1917, 1066], [6, 1070], [3, 176]], np.int32)
        }
    },
    "CAM_SKINCARE": {
        "video": "../data/CAM_01.mp4",
        "zones": {
            "SKINCARE": np.array([[0, 56], [1905, 56], [1914, 1078], [6, 1072], [2, 60]], np.int32)
        }
    }
}

def process_camera(camera_id, config, detector, emitter):
    video_path = config["video"]
    if not os.path.exists(video_path):
        logger.warning(f"Video {video_path} not found. Skipping {camera_id}.")
        return

    logger.info(f"--- Processing {camera_id} ---")
    cap = cv2.VideoCapture(video_path)
    
    # Initialize the brain for this specific camera
    state_machine = StoreTrackerState(
        store_id=STORE_ID,
        camera_id=camera_id,
        zones=config["zones"],
        entrance_line=[] 
    )

    frame_count = 0
    while cap.isOpened():
        success, frame = cap.read()
        if not success:
            break
            
        frame_count += 1
        
        # 1. Detect & Track (The Eyes)
        tracks = detector.get_tracks(frame)
        
        # 2. Evaluate State & Generate Events (The Brain)
        events = state_machine.process_frame_tracks(tracks)
        
        # 3. Handle Special ENTRY logic for the door camera
        for e in events:
            if e["zone_id"] == "ENTRY_DOOR" and e["event_type"] == "ZONE_ENTER":
                e["event_type"] = "ENTRY" # Transform it to trigger top-of-funnel!
        
        # 4. Push to API (The Network)
        emitter.emit(events)

        if frame_count % 100 == 0:
            logger.info(f"{camera_id}: Processed {frame_count} frames...")

    # Flush any remaining events
    emitter.flush()
    cap.release()
    logger.info(f"Finished {camera_id}.")

if __name__ == "__main__":
    detector = PersonDetector()
    emitter = EventEmitter()

    # Process sequentially to avoid blowing up memory limits
    for cam_id, conf in CAMERA_CONFIGS.items():
        process_camera(cam_id, conf, detector, emitter)
        
    logger.info("🎉 All cameras processed successfully!")