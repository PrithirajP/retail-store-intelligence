from pydantic import BaseModel, Field
from enum import Enum
from typing import Optional, List
from datetime import datetime
import uuid

# Define the exact event types from the challenge catalog
class EventType(str, Enum):
    ENTRY = "ENTRY"
    EXIT = "EXIT"
    ZONE_ENTER = "ZONE_ENTER"
    ZONE_EXIT = "ZONE_EXIT"
    ZONE_DWELL = "ZONE_DWELL"
    BILLING_QUEUE_JOIN = "BILLING_QUEUE_JOIN"
    BILLING_QUEUE_EXIT = "BILLING_QUEUE_EXIT"

# The core Event schema based on the challenge requirements
class Event(BaseModel):
    event_id: uuid.UUID = Field(default_factory=uuid.uuid4, description="Unique identifier for the event")
    store_id: str = Field(..., description="Unique store identifier")
    camera_id: str = Field(..., description="Camera identifier generating the event")
    visitor_id: str = Field(..., description="Persistent track ID assigned to a person")
    timestamp: datetime = Field(..., description="ISO-8601 UTC timestamp")
    event_type: EventType = Field(..., description="Type of the event from the catalog")
    zone_id: Optional[str] = Field(default=None, description="Required for ZONE_* events")
    
    dwell_ms: Optional[int] = Field(default=None, ge=0, description="Dwell time in milliseconds")
    is_staff: bool = Field(default=False, description="True if the person is identified as staff")
    confidence: float = Field(..., ge=0.0, le=1.0, description="AI confidence score for the detection/tracking")

# Request/Response schemas for batch ingestion
class EventIngestRequest(BaseModel):
    events: List[Event] = Field(..., max_length=500, description="Batch of events (max 500)")

class EventIngestResponse(BaseModel):
    status: str
    processed_count: int
    errors: Optional[List[dict]] = None