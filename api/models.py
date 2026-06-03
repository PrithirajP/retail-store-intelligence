from enum import Enum
from typing import Optional, List
from uuid import UUID
from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class EventType(str, Enum):
    ENTRY = "ENTRY"
    EXIT = "EXIT"
    ZONE_ENTER = "ZONE_ENTER"
    ZONE_EXIT = "ZONE_EXIT"
    ZONE_DWELL = "ZONE_DWELL"
    BILLING_QUEUE_JOIN = "BILLING_QUEUE_JOIN"
    BILLING_QUEUE_EXIT = "BILLING_QUEUE_EXIT"
    BILLING_QUEUE_ABANDON = "BILLING_QUEUE_ABANDON"
    REENTRY = "REENTRY"


class EventMetadata(BaseModel):
    queue_depth: Optional[int] = None
    sku_zone: Optional[str] = None
    session_seq: Optional[int] = None


class Event(BaseModel):
    event_id: UUID
    store_id: str
    camera_id: str
    visitor_id: str
    timestamp: datetime
    event_type: EventType
    zone_id: Optional[str] = None
    dwell_ms: Optional[int] = None
    is_staff: bool = False
    confidence: float = 0.0
    metadata: EventMetadata = Field(default_factory=EventMetadata)

    @model_validator(mode="after")
    def validate_event_fields(self):
        if self.event_type in {
            EventType.ZONE_ENTER,
            EventType.ZONE_EXIT,
            EventType.ZONE_DWELL,
        } and not self.zone_id:
            raise ValueError("zone_id is required for zone events")

        if self.event_type == EventType.ZONE_DWELL and self.dwell_ms is None:
            raise ValueError("dwell_ms is required for ZONE_DWELL events")

        if self.dwell_ms is not None and self.dwell_ms < 0:
            raise ValueError("dwell_ms cannot be negative")

        if self.confidence < 0 or self.confidence > 1:
            raise ValueError("confidence must be between 0 and 1")

        return self


class EventIngestResponse(BaseModel):
    status: str
    received_count: int
    processed_count: int
    duplicate_count: int
    error_count: int
    errors: Optional[List[dict]] = None