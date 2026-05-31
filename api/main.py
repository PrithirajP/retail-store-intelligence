from sqlalchemy.orm import Session
from database import get_db, EventRecord, VisitorSession, correlate_billing_exit
from sqlalchemy.exc import IntegrityError
from fastapi import FastAPI, HTTPException, status, Depends
from fastapi.responses import JSONResponse
import logging
from models import EventIngestRequest, EventIngestResponse

# Configure basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Store Intelligence API",
    description="Real-time retail analytics backend",
    version="1.0.0"
)

@app.get("/health", tags=["System"])
async def health_check():
    """Endpoint for Docker to verify the API is ready to accept traffic."""
    return {"status": "healthy"}

@app.post(
    "/events/ingest", 
    response_model=EventIngestResponse, 
    status_code=status.HTTP_202_ACCEPTED,
    tags=["Ingestion"]
)
async def ingest_events(payload: EventIngestRequest, db: Session = Depends(get_db)):
    processed_count = 0
    errors = []

    for event_in in payload.events:
        # 1. Idempotency Check: Try to insert the raw event
        db_event = EventRecord(
            event_id=str(event_in.event_id),
            store_id=event_in.store_id,
            visitor_id=event_in.visitor_id,
            event_type=event_in.event_type.value,
            timestamp=event_in.timestamp
        )
        db.add(db_event)
        
        try:
            db.commit()
            processed_count += 1
        except IntegrityError:
            # Event already exists, ignore it safely (Idempotent)
            db.rollback()
            continue

        # 2. Update Materialized Session
        session = db.query(VisitorSession).filter(VisitorSession.visitor_id == event_in.visitor_id).first()
        if not session and event_in.event_type.value == "ENTRY":
            session = VisitorSession(
                visitor_id=event_in.visitor_id,
                store_id=event_in.store_id,
                entry_time=event_in.timestamp,
                is_staff=event_in.is_staff
            )
            db.add(session)
            db.commit()

        # 3. Trigger POS Correlation on Billing Exit
        if event_in.event_type.value == "BILLING_QUEUE_EXIT":
            if session:
                session.billing_exit_time = event_in.timestamp
                db.commit()
                # Run the correlation engine
                correlate_billing_exit(db, event_in.visitor_id, event_in.store_id, event_in.timestamp)

    return EventIngestResponse(
        status="success",
        processed_count=processed_count,
        errors=errors if errors else None
    )