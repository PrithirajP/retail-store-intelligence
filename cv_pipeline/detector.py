import cv2
from ultralytics import YOLO
import logging

logger = logging.getLogger(__name__)

class PersonDetector:
    def __init__(self, model_path="yolov8n.pt"):
        # YOLOv8 nano is extremely fast on CPU. 
        # We enforce ByteTrack for stable ID persistence across frames.
        logger.info(f"Loading YOLOv8 model from {model_path}...")
        self.model = YOLO(model_path)

    def get_tracks(self, frame):
        """Runs inference and returns a list of active tracks."""
        # classes=[0] ensures we ONLY track people, ignoring chairs, bags, etc.
        results = self.model.track(frame, persist=True, classes=[0], tracker="bytetrack.yaml", verbose=False)
        
        tracks = []
        if results[0].boxes is not None and results[0].boxes.id is not None:
            boxes = results[0].boxes.xyxy.cpu().numpy()
            track_ids = results[0].boxes.id.int().cpu().tolist()
            confs = results[0].boxes.conf.cpu().tolist()

            for box, track_id, conf in zip(boxes, track_ids, confs):
                x1, y1, x2, y2 = box
                # Heuristic: Track the feet (bottom-center of bounding box) for accurate floor zone mapping
                foot_x = int((x1 + x2) / 2)
                foot_y = int(y2)
                
                tracks.append({
                    "visitor_id": f"VIS_{track_id}",
                    "point": (foot_x, foot_y),
                    "conf": float(conf)
                })
                
        return tracks