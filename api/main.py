from typing import Any, List, Optional
from datetime import datetime, timezone, timedelta

from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func, text
from fastapi import FastAPI, status, Depends, Body
import logging
from contextlib import asynccontextmanager
from pydantic import ValidationError

from database import (
    get_db,
    EventRecord,
    VisitorSession,
    correlate_billing_exit,
)
from models import Event, EventIngestResponse
from seed_data import seed_pos_data


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


STALE_FEED_THRESHOLD_MINUTES = 10

EXCLUDED_HEATMAP_ZONES = {
    "ENTRY_DOOR",
    "BILLING_QUEUE",
    "BEHIND_COUNTER",
}


@asynccontextmanager
async def lifespan(app: FastAPI):
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


# ---------------------------------------------------------------------
# Shared time helpers
# ---------------------------------------------------------------------

def _normalize_datetime_to_utc(value) -> Optional[datetime]:
    if value is None:
        return None

    if isinstance(value, str):
        try:
            value = value.replace("Z", "+00:00")
            value = datetime.fromisoformat(value)
        except ValueError:
            return None

    if not isinstance(value, datetime):
        return None

    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)

    return value.astimezone(timezone.utc)


def _datetime_to_iso(value) -> Optional[str]:
    normalized = _normalize_datetime_to_utc(value)
    return normalized.isoformat() if normalized is not None else None


# ---------------------------------------------------------------------
# Health helpers
# ---------------------------------------------------------------------

def _check_database_health(db: Session) -> dict:
    try:
        db.execute(text("SELECT 1"))
        return {"status": "connected"}
    except Exception as e:
        logger.error("Database health check failed: %s", e)
        return {
            "status": "error",
            "error": str(e),
        }


def _get_latest_event_by_store(db: Session) -> list:
    return (
        db.query(
            EventRecord.store_id,
            func.max(EventRecord.timestamp).label("last_event_timestamp"),
        )
        .filter(EventRecord.store_id.isnot(None))
        .group_by(EventRecord.store_id)
        .all()
    )


def _get_feed_status(last_event_time: Optional[datetime]) -> tuple[str, list]:
    if last_event_time is None:
        return "NO_EVENTS", ["NO_EVENTS_RECEIVED"]

    now_utc = datetime.now(timezone.utc)
    age = now_utc - last_event_time

    if age > timedelta(minutes=STALE_FEED_THRESHOLD_MINUTES):
        return "STALE", ["STALE_FEED"]

    return "OK", []


@app.get("/health", tags=["System"])
async def health_check(db: Session = Depends(get_db)):
    database_status = _check_database_health(db)

    if database_status.get("status") != "connected":
        return {
            "status": "degraded",
            "database": database_status,
            "stores": {},
            "warnings": ["DATABASE_UNAVAILABLE"],
        }

    try:
        latest_events = _get_latest_event_by_store(db)
    except Exception as e:
        logger.error("Failed to query latest events: %s", e)
        return {
            "status": "degraded",
            "database": database_status,
            "stores": {},
            "warnings": ["EVENT_QUERY_FAILED"],
        }

    stores = {}
    global_warnings = []

    if not latest_events:
        global_warnings.append("NO_EVENTS_RECEIVED")

    for row in latest_events:
        store_id = row.store_id
        last_event_time = _normalize_datetime_to_utc(row.last_event_timestamp)

        feed_status, warnings = _get_feed_status(last_event_time)

        stores[store_id] = {
            "last_event_timestamp": last_event_time.isoformat()
            if last_event_time is not None
            else None,
            "feed_status": feed_status,
            "warnings": warnings,
        }

    overall_status = "healthy"

    if any(store["feed_status"] == "STALE" for store in stores.values()):
        overall_status = "degraded"

    return {
        "status": overall_status,
        "database": database_status,
        "stores": stores,
        "warnings": global_warnings,
    }


# ---------------------------------------------------------------------
# Ingestion helpers
# ---------------------------------------------------------------------

def _create_event_record(event_in: Event) -> EventRecord:
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


def _get_session(db: Session, visitor_id: str) -> Optional[VisitorSession]:
    return (
        db.query(VisitorSession)
        .filter(VisitorSession.visitor_id == visitor_id)
        .first()
    )


def _create_or_update_entry_session(db: Session, event_in: Event) -> VisitorSession:
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


def _update_existing_session_from_event(
    db: Session,
    event_in: Event,
) -> Optional[VisitorSession]:
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


def _validate_payload_shape(payload: Any) -> tuple[Optional[List[dict]], List[dict]]:
    if not isinstance(payload, dict):
        return None, [
            {
                "index": None,
                "event_id": None,
                "error": "Request body must be a JSON object containing an 'events' list.",
            }
        ]

    if "events" not in payload:
        return None, [
            {
                "index": None,
                "event_id": None,
                "error": "Missing required top-level key: events",
            }
        ]

    raw_events = payload.get("events")

    if not isinstance(raw_events, list):
        return None, [
            {
                "index": None,
                "event_id": None,
                "error": "The 'events' field must be a list.",
            }
        ]

    if len(raw_events) > 500:
        return None, [
            {
                "index": None,
                "event_id": None,
                "error": "Batch size exceeds maximum allowed length of 500 events.",
            }
        ]

    return raw_events, []


def _validate_raw_event(raw_event: Any, index: int) -> tuple[Optional[Event], Optional[dict]]:
    if not isinstance(raw_event, dict):
        return None, {
            "index": index,
            "event_id": None,
            "error": "Event must be a JSON object.",
        }

    try:
        return Event.model_validate(raw_event), None
    except ValidationError as e:
        return None, {
            "index": index,
            "event_id": raw_event.get("event_id"),
            "error": e.errors(),
        }


def _determine_ingest_status(
    received_count: int,
    processed_count: int,
    duplicate_count: int,
    error_count: int,
) -> str:
    if received_count == 0:
        return "failed"

    if processed_count == received_count and duplicate_count == 0 and error_count == 0:
        return "success"

    if processed_count == 0 and duplicate_count == received_count and error_count == 0:
        return "duplicate_only"

    if processed_count == 0 and duplicate_count == 0 and error_count > 0:
        return "failed"

    return "partial_success"


@app.post(
    "/events/ingest",
    response_model=EventIngestResponse,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["Ingestion"],
)
async def ingest_events(
    payload: Any = Body(...),
    db: Session = Depends(get_db),
):
    raw_events, envelope_errors = _validate_payload_shape(payload)

    if raw_events is None:
        return EventIngestResponse(
            status="failed",
            received_count=0,
            processed_count=0,
            duplicate_count=0,
            error_count=len(envelope_errors),
            errors=envelope_errors,
        )

    received_count = len(raw_events)
    processed_count = 0
    duplicate_count = 0
    errors: List[dict] = []

    for index, raw_event in enumerate(raw_events):
        event_in, validation_error = _validate_raw_event(raw_event, index)

        if validation_error is not None:
            errors.append(validation_error)
            continue

        db_event = _create_event_record(event_in)
        db.add(db_event)

        try:
            db.commit()
            processed_count += 1
        except IntegrityError:
            db.rollback()
            duplicate_count += 1
            continue
        except Exception as e:
            db.rollback()
            logger.error("Failed to persist event at index %s: %s", index, e)
            errors.append(
                {
                    "index": index,
                    "event_id": str(event_in.event_id),
                    "error": str(e),
                }
            )
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
                    "index": index,
                    "event_id": str(event_in.event_id),
                    "error": str(e),
                }
            )

    error_count = len(errors)

    response_status = _determine_ingest_status(
        received_count=received_count,
        processed_count=processed_count,
        duplicate_count=duplicate_count,
        error_count=error_count,
    )

    return EventIngestResponse(
        status=response_status,
        received_count=received_count,
        processed_count=processed_count,
        duplicate_count=duplicate_count,
        error_count=error_count,
        errors=errors if errors else None,
    )


# ---------------------------------------------------------------------
# Metrics helpers
# ---------------------------------------------------------------------

def _compute_current_queue_depth(db: Session, store_id: str) -> int:
    queue_events = (
        db.query(
            EventRecord.visitor_id,
            EventRecord.event_type,
            EventRecord.timestamp,
            EventRecord.session_seq,
        )
        .filter(
            EventRecord.store_id == store_id,
            EventRecord.is_staff == False,
            EventRecord.event_type.in_(
                ["BILLING_QUEUE_JOIN", "BILLING_QUEUE_EXIT"]
            ),
        )
        .order_by(
            EventRecord.timestamp.asc(),
            EventRecord.session_seq.asc().nullsfirst(),
        )
        .all()
    )

    latest_status_by_visitor = {}

    for event in queue_events:
        latest_status_by_visitor[event.visitor_id] = event.event_type

    return sum(
        1
        for latest_status in latest_status_by_visitor.values()
        if latest_status == "BILLING_QUEUE_JOIN"
    )


def _compute_avg_dwell_by_zone(db: Session, store_id: str) -> dict:
    rows = (
        db.query(
            EventRecord.zone_id,
            EventRecord.sku_zone,
            func.avg(EventRecord.dwell_ms).label("avg_dwell_ms"),
        )
        .filter(
            EventRecord.store_id == store_id,
            EventRecord.event_type == "ZONE_DWELL",
            EventRecord.dwell_ms.isnot(None),
            EventRecord.is_staff == False,
        )
        .group_by(EventRecord.zone_id, EventRecord.sku_zone)
        .all()
    )

    result = {}

    for row in rows:
        zone_key = row.zone_id or row.sku_zone or "UNKNOWN"
        result[zone_key] = round(float(row.avg_dwell_ms or 0.0), 2)

    return result


def _get_total_event_count(db: Session, store_id: str) -> int:
    return (
        db.query(EventRecord)
        .filter(EventRecord.store_id == store_id)
        .count()
    )


def _get_latest_event_timestamp(db: Session, store_id: str) -> Optional[str]:
    latest_timestamp = (
        db.query(func.max(EventRecord.timestamp))
        .filter(EventRecord.store_id == store_id)
        .scalar()
    )

    return _datetime_to_iso(latest_timestamp)


# ---------------------------------------------------------------------
# Heatmap helpers
# ---------------------------------------------------------------------

def _is_heatmap_zone(zone_name: Optional[str]) -> bool:
    if zone_name is None:
        return False

    return zone_name not in EXCLUDED_HEATMAP_ZONES


def _get_zone_visit_counts(db: Session, store_id: str) -> dict:
    rows = (
        db.query(
            EventRecord.zone_id,
            EventRecord.sku_zone,
            func.count(EventRecord.event_id).label("visit_count"),
        )
        .filter(
            EventRecord.store_id == store_id,
            EventRecord.event_type == "ZONE_ENTER",
            EventRecord.is_staff == False,
        )
        .group_by(EventRecord.zone_id, EventRecord.sku_zone)
        .all()
    )

    visit_counts = {}

    for row in rows:
        zone_key = row.zone_id or row.sku_zone

        if not _is_heatmap_zone(zone_key):
            continue

        visit_counts[zone_key] = int(row.visit_count or 0)

    return visit_counts


def _get_zone_avg_dwell(db: Session, store_id: str) -> dict:
    rows = (
        db.query(
            EventRecord.zone_id,
            EventRecord.sku_zone,
            func.avg(EventRecord.dwell_ms).label("avg_dwell_ms"),
        )
        .filter(
            EventRecord.store_id == store_id,
            EventRecord.event_type == "ZONE_DWELL",
            EventRecord.dwell_ms.isnot(None),
            EventRecord.is_staff == False,
        )
        .group_by(EventRecord.zone_id, EventRecord.sku_zone)
        .all()
    )

    avg_dwell = {}

    for row in rows:
        zone_key = row.zone_id or row.sku_zone

        if not _is_heatmap_zone(zone_key):
            continue

        avg_dwell[zone_key] = round(float(row.avg_dwell_ms or 0.0), 2)

    return avg_dwell


def _compute_heat_score(
    visit_count: int,
    avg_dwell_ms: float,
    max_visit_count: int,
    max_avg_dwell_ms: float,
) -> float:
    if max_visit_count <= 0 and max_avg_dwell_ms <= 0:
        return 0.0

    visit_component = (
        visit_count / max_visit_count
        if max_visit_count > 0
        else 0.0
    )

    dwell_component = (
        avg_dwell_ms / max_avg_dwell_ms
        if max_avg_dwell_ms > 0
        else 0.0
    )

    heat_score = (0.6 * visit_component + 0.4 * dwell_component) * 100

    return round(min(max(heat_score, 0.0), 100.0), 2)


def _get_heatmap_data_confidence(total_zone_visits: int) -> str:
    if total_zone_visits == 0:
        return "NO_DATA"

    if total_zone_visits < 10:
        return "LOW"

    if total_zone_visits <= 50:
        return "MEDIUM"

    return "HIGH"


# ---------------------------------------------------------------------
# Analytics endpoints
# ---------------------------------------------------------------------

@app.get("/stores/{store_id}/metrics", tags=["Analytics"])
async def get_store_metrics(store_id: str, db: Session = Depends(get_db)):
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

    current_queue_depth = _compute_current_queue_depth(db, store_id)
    avg_dwell_ms_by_zone = _compute_avg_dwell_by_zone(db, store_id)
    total_events = _get_total_event_count(db, store_id)
    last_event_timestamp = _get_latest_event_timestamp(db, store_id)

    return {
        "store_id": store_id,
        "total_visitors": total_visitors,
        "converted_visitors": converted_visitors,
        "conversion_rate_percentage": round(conversion_rate, 2),
        "current_queue_depth": current_queue_depth,
        "avg_dwell_ms_by_zone": avg_dwell_ms_by_zone,
        "total_events": total_events,
        "last_event_timestamp": last_event_timestamp,
    }


@app.get("/stores/{store_id}/heatmap", tags=["Analytics"])
async def get_store_heatmap(store_id: str, db: Session = Depends(get_db)):
    visit_counts = _get_zone_visit_counts(db, store_id)
    avg_dwell = _get_zone_avg_dwell(db, store_id)

    all_zones = sorted(set(visit_counts.keys()) | set(avg_dwell.keys()))

    total_zone_visits = sum(visit_counts.values())
    data_confidence = _get_heatmap_data_confidence(total_zone_visits)

    max_visit_count = max(visit_counts.values()) if visit_counts else 0
    max_avg_dwell_ms = max(avg_dwell.values()) if avg_dwell else 0.0

    zones = []

    for zone_id in all_zones:
        visit_count = visit_counts.get(zone_id, 0)
        avg_dwell_ms = avg_dwell.get(zone_id, 0.0)

        heat_score = _compute_heat_score(
            visit_count=visit_count,
            avg_dwell_ms=avg_dwell_ms,
            max_visit_count=max_visit_count,
            max_avg_dwell_ms=max_avg_dwell_ms,
        )

        zones.append(
            {
                "zone_id": zone_id,
                "visit_count": visit_count,
                "avg_dwell_ms": avg_dwell_ms,
                "heat_score": heat_score,
            }
        )

    zones.sort(key=lambda item: item["heat_score"], reverse=True)

    return {
        "store_id": store_id,
        "heatmap_type": "zone_level",
        "data_confidence": data_confidence,
        "zones": zones,
    }


@app.get("/stores/{store_id}/funnel", tags=["Analytics"])
async def get_store_funnel(store_id: str, db: Session = Depends(get_db)):
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