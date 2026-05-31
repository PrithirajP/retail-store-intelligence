from sqlalchemy.orm import Session
from database import get_db, EventRecord, VisitorSession, correlate_billing_exit
from sqlalchemy.exc import IntegrityError
from fastapi import FastAPI, HTTPException, status, Depends, Query
from fastapi.responses import JSONResponse
import logging
from models import EventIngestRequest, EventIngestResponse
from sqlalchemy import func
from contextlib import asynccontextmanager
from seed_data import seed_pos_data

# Configure basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # This runs exactly once when the container starts up
    logger.info("Initializing Store API...")
    try:
        # Hardcode the path assuming it's mounted in docker-compose
        seed_pos_data("/app/data/Brigade_Bangalore_10_April_26.csv")
    except Exception as e:
        logger.error(f"Failed to seed data on startup: {e}")
    yield
    

app = FastAPI(
    title="Store Intelligence API",
    lifespan=lifespan
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

@app.get("/stores/{store_id}/metrics", tags=["Analytics"])
async def get_store_metrics(store_id: str, db: Session = Depends(get_db)):
    """
    Returns the real-time North Star Metric: Conversion Rate.
    Excludes staff from all calculations.
    """
    # 1. Top of Funnel: Total Unique Visitors
    total_visitors = db.query(VisitorSession).filter(
        VisitorSession.store_id == store_id,
        VisitorSession.is_staff == False
    ).count()

    # 2. Bottom of Funnel: Converted Visitors
    converted_visitors = db.query(VisitorSession).filter(
        VisitorSession.store_id == store_id,
        VisitorSession.is_staff == False,
        VisitorSession.is_converted == True
    ).count()

    # 3. Calculate North Star Metric safely (avoid Divide by Zero)
    conversion_rate = (converted_visitors / total_visitors * 100) if total_visitors > 0 else 0.0

    return {
        "store_id": store_id,
        "total_visitors": total_visitors,
        "converted_visitors": converted_visitors,
        "conversion_rate_percentage": round(conversion_rate, 2)
    }

@app.get("/stores/{store_id}/funnel", tags=["Analytics"])
async def get_store_funnel(store_id: str, db: Session = Depends(get_db)):
    """
    Returns a step-by-step drop-off funnel for the store.
    """
    # Total valid visitors
    entered_store = db.query(VisitorSession).filter(
        VisitorSession.store_id == store_id,
        VisitorSession.is_staff == False
    ).count()

    # Visitors who made it to the billing queue
    entered_billing = db.query(VisitorSession).filter(
        VisitorSession.store_id == store_id,
        VisitorSession.is_staff == False,
        VisitorSession.billing_exit_time != None
    ).count()

    # Visitors who actually bought something
    converted = db.query(VisitorSession).filter(
        VisitorSession.store_id == store_id,
        VisitorSession.is_staff == False,
        VisitorSession.is_converted == True
    ).count()

    # Calculate queue abandonment
    abandoned_queue = entered_billing - converted

    return {
        "store_id": store_id,
        "funnel_steps": {
            "1_entered_store": entered_store,
            "2_entered_billing_queue": entered_billing,
            "3_completed_purchase": converted
        },
        "insights": {
            "queue_abandonment_count": abandoned_queue,
            "queue_abandonment_rate": round((abandoned_queue / entered_billing * 100), 2) if entered_billing > 0 else 0.0
        }
    }