from pydantic import BaseModel, Field
from enum import Enum
from typing import Optional, List
from datetime import datetime
import uuid


class EventType(str, Enum):
    ENTRY = "ENTRY"
    EXIT = "EXIT"
    ZONE_ENTER = "ZONE_ENTER"
    ZONE_EXIT = "ZONE_EXIT"
    ZONE_DWELL = "ZONE_DWELL"
    BILLING_QUEUE_JOIN = "BILLING_QUEUE_JOIN"
    BILLING_QUEUE_EXIT = "BILLING_QUEUE_EXIT"

    # Added for Event Schema v1.2 compatibility.
    REENTRY = "REENTRY"
    BILLING_QUEUE_ABANDON = "BILLING_QUEUE_ABANDON"


class EventMetadata(BaseModel):
    """
    Optional nested metadata object for Event Schema v1.2.

    queue_depth:
        Current billing queue depth, mainly for queue events.

    sku_zone:
        Business-friendly zone name. Currently mirrors zone_id.

    session_seq:
        Local event sequence number for this visitor.
    """

    queue_depth: Optional[int] = Field(default=None, ge=0)
    sku_zone: Optional[str] = None
    session_seq: Optional[int] = Field(default=None, ge=1)


class Event(BaseModel):
    """
    Core event schema accepted by POST /events/ingest.

    This schema keeps the earlier flattened event fields and adds
    challenge-compatible nested metadata.
    """

    event_id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        description="Unique identifier for the event",
    )
    store_id: str = Field(..., description="Unique store identifier")
    camera_id: str = Field(..., description="Camera identifier generating the event")
    visitor_id: str = Field(..., description="Persistent track ID assigned to a person")
    timestamp: datetime = Field(..., description="ISO-8601 UTC timestamp")
    event_type: EventType = Field(..., description="Type of event")
    zone_id: Optional[str] = Field(default=None, description="Zone identifier")

    dwell_ms: Optional[int] = Field(
        default=None,
        ge=0,
        description="Dwell time in milliseconds",
    )
    is_staff: bool = Field(
        default=False,
        description="True if the person is identified as staff",
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Detection/tracking confidence score",
    )

    metadata: EventMetadata = Field(
        default_factory=EventMetadata,
        description="Nested event metadata",
    )


class EventIngestRequest(BaseModel):
    """
    Kept for OpenAPI documentation and compatibility.

    Milestone 4 manually validates events inside /events/ingest so that
    one malformed event does not reject the entire batch.
    """

    events: List[Event] = Field(
        ...,
        max_length=500,
        description="Batch of events, maximum 500",
    )


class EventIngestResponse(BaseModel):
    status: str
    received_count: int = 0
    processed_count: int = 0
    duplicate_count: int = 0
    error_count: int = 0
    errors: Optional[List[dict]] = None