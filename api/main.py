from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from fastapi import FastAPI, status, Depends
import logging
from contextlib import asynccontextmanager

from database import (
    get_db,
    EventRecord,
    VisitorSession,
    correlate_billing_exit,
)
from models import EventIngestRequest, EventIngestResponse
from seed_data import seed_pos_data


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application startup lifecycle.

    Seeds POS data from the mounted /app/data directory before normal use.
    If seeding fails, the API still starts so that health checks and basic
    API inspection do not crash.
    """

    logger.info("Initializing Store API...")

    try:
        seed_pos_data("/app/data/Brigade_Bangalore_10_April_26.csv")
    except Exception as e:
        logger.error("Failed to seed data on startup: %s", e)

    yield


app = FastAPI(
    title="Store Intelligence API",
    lifespan=lifespan,
)


@app.get("/health", tags=["System"])
async def health_check():
    """
    Basic health endpoint.

    Milestone 5 will upgrade this to include last event timestamp and
    stale feed status.
    """

    return {"status": "healthy"}


def _create_event_record(event_in) -> EventRecord:
    """
    Convert a validated Pydantic event into a SQLAlchemy EventRecord.

    Persists full Event Schema v1.2 fields including flattened metadata.
    """

    metadata = event_in.metadata

    return EventRecord(
        event_id=str(event_in.event_id),
        store_id=event_in.store_id,
        camera_id=event_in.camera_id,
        visitor_id=event_in.visitor_id,
        event_type=event_in.event_type.value,
        timestamp=event_in.timestamp,
        zone_id=event_in.zone_id,
        dwell_ms=event_in.dwell_ms,
        is_staff=event_in.is_staff,
        confidence=event_in.confidence,
        queue_depth=metadata.queue_depth,
        sku_zone=metadata.sku_zone,
        session_seq=metadata.session_seq,
    )


def _get_session(db: Session, visitor_id: str):
    return (
        db.query(VisitorSession)
        .filter(VisitorSession.visitor_id == visitor_id)
        .first()
    )


def _create_or_update_entry_session(db: Session, event_in) -> VisitorSession:
    """
    Create or update a visitor session from an ENTRY event.

    This keeps the session table as a materialized lifecycle view.
    """

    session = _get_session(db, event_in.visitor_id)

    if session is None:
        session = VisitorSession(
            visitor_id=event_in.visitor_id,
            store_id=event_in.store_id,
            entry_time=event_in.timestamp,
            last_seen_time=event_in.timestamp,
            is_staff=event_in.is_staff,
        )
        db.add(session)
        return session

    if session.entry_time is None:
        session.entry_time = event_in.timestamp

    session.last_seen_time = event_in.timestamp

    if event_in.is_staff:
        session.is_staff = True

    return session


def _update_existing_session_from_event(db: Session, event_in):
    """
    Update derived session state using non-ENTRY events.

    Important:
    This function does not create sessions for every random zone event.
    The top-of-funnel session still starts from ENTRY. This avoids inflating
    total visitors from cameras that do not observe the entrance.
    """

    session = _get_session(db, event_in.visitor_id)

    if session is None:
        return None

    session.last_seen_time = event_in.timestamp

    if event_in.is_staff:
        session.is_staff = True

    event_type = event_in.event_type.value

    if event_type == "BILLING_QUEUE_JOIN":
        session.billing_join_time = event_in.timestamp

    elif event_type == "BILLING_QUEUE_EXIT":
        session.billing_exit_time = event_in.timestamp

    return session


@app.post(
    "/events/ingest",
    response_model=EventIngestResponse,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["Ingestion"],
)
async def ingest_events(payload: EventIngestRequest, db: Session = Depends(get_db)):
    """
    Ingest a batch of CV-generated events.

    Current behavior:
    - Validates event payloads through Pydantic.
    - Inserts raw event records with event_id idempotency.
    - Updates the materialized VisitorSession table.
    - Triggers POS correlation on BILLING_QUEUE_EXIT.
    """

    processed_count = 0
    errors = []

    for event_in in payload.events:
        db_event = _create_event_record(event_in)

        db.add(db_event)

        try:
            db.commit()
            processed_count += 1
        except IntegrityError:
            # Duplicate event_id: idempotent skip.
            db.rollback()
            continue

        event_type = event_in.event_type.value

        try:
            if event_type == "ENTRY":
                _create_or_update_entry_session(db, event_in)
                db.commit()

            else:
                session = _update_existing_session_from_event(db, event_in)
                db.commit()

                if event_type == "BILLING_QUEUE_EXIT" and session is not None:
                    correlate_billing_exit(
                        db=db,
                        visitor_id=event_in.visitor_id,
                        store_id=event_in.store_id,
                        exit_time=event_in.timestamp,
                    )

        except Exception as e:
            db.rollback()
            logger.error(
                "Failed to update session state for event %s: %s",
                event_in.event_id,
                e,
            )
            errors.append(
                {
                    "event_id": str(event_in.event_id),
                    "error": str(e),
                }
            )

    return EventIngestResponse(
        status="success" if not errors else "partial_success",
        processed_count=processed_count,
        errors=errors if errors else None,
    )


@app.get("/stores/{store_id}/metrics", tags=["Analytics"])
async def get_store_metrics(store_id: str, db: Session = Depends(get_db)):
    """
    Returns the real-time North Star Metric: Conversion Rate.

    Staff sessions are excluded from customer metrics.
    """

    total_visitors = (
        db.query(VisitorSession)
        .filter(
            VisitorSession.store_id == store_id,
            VisitorSession.is_staff == False,
        )
        .count()
    )

    converted_visitors = (
        db.query(VisitorSession)
        .filter(
            VisitorSession.store_id == store_id,
            VisitorSession.is_staff == False,
            VisitorSession.is_converted == True,
        )
        .count()
    )

    conversion_rate = (
        converted_visitors / total_visitors * 100
        if total_visitors > 0
        else 0.0
    )

    return {
        "store_id": store_id,
        "total_visitors": total_visitors,
        "converted_visitors": converted_visitors,
        "conversion_rate_percentage": round(conversion_rate, 2),
    }


@app.get("/stores/{store_id}/funnel", tags=["Analytics"])
async def get_store_funnel(store_id: str, db: Session = Depends(get_db)):
    """
    Returns a basic shopper funnel.

    Current funnel:
    Entry -> Billing Queue -> Purchase
    """

    entered_store = (
        db.query(VisitorSession)
        .filter(
            VisitorSession.store_id == store_id,
            VisitorSession.is_staff == False,
        )
        .count()
    )

    entered_billing = (
        db.query(VisitorSession)
        .filter(
            VisitorSession.store_id == store_id,
            VisitorSession.is_staff == False,
            VisitorSession.billing_exit_time != None,
        )
        .count()
    )

    converted = (
        db.query(VisitorSession)
        .filter(
            VisitorSession.store_id == store_id,
            VisitorSession.is_staff == False,
            VisitorSession.is_converted == True,
        )
        .count()
    )

    abandoned_queue = max(entered_billing - converted, 0)

    return {
        "store_id": store_id,
        "funnel_steps": {
            "1_entered_store": entered_store,
            "2_entered_billing_queue": entered_billing,
            "3_completed_purchase": converted,
        },
        "insights": {
            "queue_abandonment_count": abandoned_queue,
            "queue_abandonment_rate": round(
                abandoned_queue / entered_billing * 100,
                2,
            )
            if entered_billing > 0
            else 0.0,
        },
    }