import requests
import logging

logger = logging.getLogger(__name__)

class EventEmitter:
    def __init__(self, api_url="http://127.0.0.1:8000/events/ingest", batch_size=20):
        self.api_url = api_url
        self.batch_size = batch_size
        self.buffer = []

    def emit(self, events: list):
        if not events:
            return
            
        self.buffer.extend(events)
        if len(self.buffer) >= self.batch_size:
            self.flush()

    def flush(self):
        if not self.buffer:
            return
        try:
            # We match the EventIngestRequest schema exactly
            response = requests.post(self.api_url, json={"events": self.buffer}, timeout=2)
            if response.status_code == 202:
                logger.info(f"Successfully pushed {len(self.buffer)} events to API.")
            else:
                logger.error(f"API rejected batch: {response.text}")
            self.buffer = []
        except requests.exceptions.RequestException as e:
            logger.error(f"Connection error to API: {e}")