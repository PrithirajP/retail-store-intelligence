from typing import Any, List, Optional
from datetime import datetime, timezone, timedelta
import json
import logging
import time
import uuid

from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func, text
from fastapi import FastAPI, status, Depends, Body, Request
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

EXPECTED_PRODUCT_ZONES = {
    "MAKEUP",
    "SKINCARE",
}

QUEUE_SPIKE_WARN_THRESHOLD = 5
QUEUE_SPIKE_CRITICAL_THRESHOLD = 8

BASELINE_CONVERSION_RATE_PERCENTAGE = 25.0
CONVERSION_DROP_WARN_FACTOR = 0.70
CONVERSION_DROP_CRITICAL_FACTOR = 0.50
MIN_VISITORS_FOR_CONVERSION_ANOMALY = 5

DEAD_ZONE_MIN_TOTAL_EVENTS = 20


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
# Structured logging helpers
# ---------------------------------------------------------------------

def _extract_store_id_from_path(path: str) -> Optional[str]:
    parts = [part for part in path.split("/") if part]

    if len(parts) >= 2 and parts[0] == "stores":
        return parts[1]

    return None


def _get_or_create_trace_id(request: Request) -> str:
    return request.headers.get("X-Trace-Id") or str(uuid.uuid4())


def _log_json(payload: dict):
    logger.info(json.dumps(payload, sort_keys=True, default=str))


@app.middleware("http")
async def structured_logging_middleware(request: Request, call_next):
    start_time = time.perf_counter()
    trace_id = _get_or_create_trace_id(request)
    request.state.trace_id = trace_id

    status_code = 500
    error = None

    try:
        response = await call_next(request)
        status_code = response.status_code
        response.headers["X-Trace-Id"] = trace_id
        return response

    except Exception as exc:
        error = {
            "type": exc.__class__.__name__,
            "message": str(exc),
        }
        raise

    finally:
        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)

        client_host = None
        if request.client is not None:
            client_host = request.client.host

        log_payload = {
            "event": "api_request",
            "trace_id": trace_id,
            "method": request.method,
            "endpoint": request.url.path,
            "status_code": status_code,
            "latency_ms": latency_ms,
            "store_id": _extract_store_id_from_path(request.url.path),
            "client_host": client_host,
        }

        if error is not None:
            log_payload["error"] = error

        _log_json(log_payload)


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


def _milliseconds_between(start_time, end_time) -> Optional[int]:
    start_dt = _normalize_datetime_to_utc(start_time)
    end_dt = _normalize_datetime_to_utc(end_time)

    if start_dt is None or end_dt is None:
        return None

    delta_ms = int((end_dt - start_dt).total_seconds() * 1000)

    if delta_ms < 0:
        return None

    return delta_ms


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
# Event normalization helpers
# ---------------------------------------------------------------------

def _is_valid_uuid(value: Any) -> bool:
    try:
        uuid.UUID(str(value))
        return True
    except (TypeError, ValueError):
        return False


def _get_or_generate_event_id(raw_event: dict) -> str:
    candidate = raw_event.get("event_id") or raw_event.get("queue_event_id")

    if candidate is not None and _is_valid_uuid(candidate):
        return str(candidate)

    return str(uuid.uuid4())


def _normalize_event_type(raw_event_type: Any) -> Optional[str]:
    if raw_event_type is None:
        return None

    event_type = str(raw_event_type).strip()

    if not event_type:
        return None

    canonical = event_type.upper()

    direct_supported = {
        "ENTRY",
        "EXIT",
        "ZONE_ENTER",
        "ZONE_EXIT",
        "ZONE_DWELL",
        "BILLING_QUEUE_JOIN",
        "BILLING_QUEUE_EXIT",
        "BILLING_QUEUE_ABANDON",
        "REENTRY",
    }

    if canonical in direct_supported:
        return canonical

    event_type_map = {
        "entry": "ENTRY",
        "exit": "EXIT",
        "zone_entered": "ZONE_ENTER",
        "zone_exited": "ZONE_EXIT",
        "zone_enter": "ZONE_ENTER",
        "zone_exit": "ZONE_EXIT",
        "zone_dwell": "ZONE_DWELL",
        "queue_joined": "BILLING_QUEUE_JOIN",
        "queue_entered": "BILLING_QUEUE_JOIN",
        "billing_queue_join": "BILLING_QUEUE_JOIN",
        "queue_completed": "BILLING_QUEUE_EXIT",
        "queue_served": "BILLING_QUEUE_EXIT",
        "billing_queue_exit": "BILLING_QUEUE_EXIT",
        "queue_abandoned": "BILLING_QUEUE_ABANDON",
        "billing_queue_abandon": "BILLING_QUEUE_ABANDON",
        "reentry": "REENTRY",
        "re_entry": "REENTRY",
    }

    return event_type_map.get(event_type.lower())


def _extract_normalized_timestamp(raw_event: dict) -> Optional[str]:
    for key in [
        "timestamp",
        "event_timestamp",
        "event_time",
        "queue_exit_ts",
        "queue_served_ts",
        "queue_join_ts",
    ]:
        value = raw_event.get(key)
        if value:
            return value

    return None


def _extract_normalized_store_id(raw_event: dict) -> Optional[str]:
    return (
        raw_event.get("store_id")
        or raw_event.get("store_code")
        or raw_event.get("store")
    )


def _extract_normalized_visitor_id(raw_event: dict) -> Optional[str]:
    value = (
        raw_event.get("visitor_id")
        or raw_event.get("id_token")
        or raw_event.get("track_id")
        or raw_event.get("person_id")
    )

    if value is None:
        return None

    return str(value)


def _extract_normalized_zone_id(raw_event: dict) -> Optional[str]:
    return raw_event.get("zone_id") or raw_event.get("zone_name")


def _extract_normalized_dwell_ms(
    raw_event: dict,
    normalized_event_type: Optional[str],
) -> Optional[int]:
    if raw_event.get("dwell_ms") is not None:
        try:
            return int(raw_event.get("dwell_ms"))
        except (TypeError, ValueError):
            return None

    if raw_event.get("wait_seconds") is not None:
        try:
            return int(float(raw_event.get("wait_seconds")) * 1000)
        except (TypeError, ValueError):
            return None

    if normalized_event_type in {
        "ENTRY",
        "EXIT",
        "ZONE_ENTER",
        "ZONE_EXIT",
        "BILLING_QUEUE_JOIN",
        "BILLING_QUEUE_EXIT",
        "BILLING_QUEUE_ABANDON",
        "REENTRY",
    }:
        return None

    return None


def _build_normalized_metadata(raw_event: dict) -> dict:
    existing_metadata = raw_event.get("metadata")

    if isinstance(existing_metadata, dict):
        metadata = dict(existing_metadata)
    else:
        metadata = {}

    if metadata.get("queue_depth") is None:
        queue_depth = raw_event.get("queue_depth")

        if queue_depth is None:
            queue_depth = raw_event.get("queue_position_at_join")

        if queue_depth is not None:
            try:
                metadata["queue_depth"] = int(queue_depth)
            except (TypeError, ValueError):
                metadata["queue_depth"] = None

    if metadata.get("sku_zone") is None:
        metadata["sku_zone"] = (
            raw_event.get("sku_zone")
            or raw_event.get("zone_name")
            or raw_event.get("brand_name")
        )

    if metadata.get("session_seq") is None:
        session_seq = raw_event.get("session_seq")

        if session_seq is not None:
            try:
                metadata["session_seq"] = int(session_seq)
            except (TypeError, ValueError):
                metadata["session_seq"] = None
        else:
            metadata["session_seq"] = None

    return {
        "queue_depth": metadata.get("queue_depth"),
        "sku_zone": metadata.get("sku_zone"),
        "session_seq": metadata.get("session_seq"),
    }


def _extract_normalized_confidence(raw_event: dict) -> float:
    confidence = raw_event.get("confidence")

    if confidence is None:
        confidence = raw_event.get("score")

    if confidence is None:
        return 0.50

    try:
        confidence_float = float(confidence)
    except (TypeError, ValueError):
        return 0.50

    return min(max(confidence_float, 0.0), 1.0)


def _extract_normalized_is_staff(raw_event: dict) -> bool:
    value = raw_event.get("is_staff", False)

    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "y"}

    return bool(value)


def _normalize_incoming_event(raw_event: dict) -> dict:
    normalized_event_type = _normalize_event_type(raw_event.get("event_type"))

    normalized = {
        "event_id": _get_or_generate_event_id(raw_event),
        "store_id": _extract_normalized_store_id(raw_event),
        "camera_id": raw_event.get("camera_id"),
        "visitor_id": _extract_normalized_visitor_id(raw_event),
        "timestamp": _extract_normalized_timestamp(raw_event),
        "event_type": normalized_event_type,
        "zone_id": _extract_normalized_zone_id(raw_event),
        "dwell_ms": _extract_normalized_dwell_ms(
            raw_event,
            normalized_event_type,
        ),
        "is_staff": _extract_normalized_is_staff(raw_event),
        "confidence": _extract_normalized_confidence(raw_event),
        "metadata": _build_normalized_metadata(raw_event),
    }

    return normalized


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


def _get_session(
    db: Session,
    store_id: str,
    visitor_id: str,
) -> Optional[VisitorSession]:
    return (
        db.query(VisitorSession)
        .filter(
            VisitorSession.store_id == store_id,
            VisitorSession.visitor_id == visitor_id,
        )
        .first()
    )


def _create_session_if_missing(
    db: Session,
    event_in: Event,
) -> VisitorSession:
    session = _get_session(
        db=db,
        store_id=event_in.store_id,
        visitor_id=event_in.visitor_id,
    )

    if session is None:
        session = VisitorSession(
            visitor_id=event_in.visitor_id,
            store_id=event_in.store_id,
            entry_time=None,
            last_seen_time=event_in.timestamp,
            is_staff=event_in.is_staff,
        )
        db.add(session)
        db.flush()

    return session


def _create_or_update_entry_session(db: Session, event_in: Event) -> VisitorSession:
    session = _create_session_if_missing(db, event_in)

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
    session = _get_session(
        db=db,
        store_id=event_in.store_id,
        visitor_id=event_in.visitor_id,
    )

    if session is None:
        session = _create_session_if_missing(db, event_in)

    session.last_seen_time = event_in.timestamp

    if event_in.is_staff:
        session.is_staff = True

    event_type = event_in.event_type.value

    if event_type == "ZONE_ENTER":
        # No schema migration in this phase.
        # Zone-visit funnel is derived from raw events.

        if session.entry_time is None:
            session.entry_time = event_in.timestamp

    elif event_type == "BILLING_QUEUE_JOIN":
        session.billing_join_time = event_in.timestamp

        if session.entry_time is None:
            session.entry_time = event_in.timestamp

    elif event_type in {
        "BILLING_QUEUE_EXIT",
        "BILLING_QUEUE_ABANDON",
    }:
        session.billing_exit_time = event_in.timestamp

        if session.entry_time is None:
            session.entry_time = event_in.timestamp

    elif event_type == "EXIT":
        session.last_seen_time = event_in.timestamp

    elif event_type == "REENTRY":
        session.last_seen_time = event_in.timestamp

        if session.entry_time is None:
            session.entry_time = event_in.timestamp

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


def _validate_raw_event(
    raw_event: Any,
    index: int,
) -> tuple[Optional[Event], Optional[dict]]:
    if not isinstance(raw_event, dict):
        return None, {
            "index": index,
            "event_id": None,
            "error": "Event must be a JSON object.",
        }

    normalized_event = _normalize_incoming_event(raw_event)

    try:
        return Event.model_validate(normalized_event), None

    except ValidationError as e:
        return None, {
            "index": index,
            "event_id": (
                raw_event.get("event_id")
                or raw_event.get("queue_event_id")
                or normalized_event.get("event_id")
            ),
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
    request: Request,
    payload: Any = Body(...),
    db: Session = Depends(get_db),
):
    raw_events, envelope_errors = _validate_payload_shape(payload)

    if raw_events is None:
        response = EventIngestResponse(
            status="failed",
            received_count=0,
            processed_count=0,
            duplicate_count=0,
            error_count=len(envelope_errors),
            errors=envelope_errors,
        )

        _log_json(
            {
                "event": "event_ingest_batch",
                "trace_id": getattr(request.state, "trace_id", None),
                "status": response.status,
                "received_count": response.received_count,
                "processed_count": response.processed_count,
                "duplicate_count": response.duplicate_count,
                "error_count": response.error_count,
            }
        )

        return response

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

    _log_json(
        {
            "event": "event_ingest_batch",
            "trace_id": getattr(request.state, "trace_id", None),
            "status": response_status,
            "received_count": received_count,
            "processed_count": processed_count,
            "duplicate_count": duplicate_count,
            "error_count": error_count,
        }
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
                [
                    "BILLING_QUEUE_JOIN",
                    "BILLING_QUEUE_EXIT",
                    "BILLING_QUEUE_ABANDON",
                ]
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


def _count_entered_store(db: Session, store_id: str) -> int:
    return (
        db.query(VisitorSession)
        .filter(
            VisitorSession.store_id == store_id,
            VisitorSession.is_staff == False,
            VisitorSession.entry_time.isnot(None),
        )
        .count()
    )


def _count_zone_visitors(db: Session, store_id: str) -> int:
    return (
        db.query(EventRecord.visitor_id)
        .filter(
            EventRecord.store_id == store_id,
            EventRecord.is_staff == False,
            EventRecord.event_type.in_(["ZONE_ENTER", "ZONE_DWELL"]),
        )
        .distinct()
        .count()
    )


def _count_converted_visitors(db: Session, store_id: str) -> int:
    return (
        db.query(VisitorSession)
        .filter(
            VisitorSession.store_id == store_id,
            VisitorSession.is_staff == False,
            VisitorSession.is_converted == True,
        )
        .count()
    )


# ---------------------------------------------------------------------
# Queue / Funnel helpers
# ---------------------------------------------------------------------

def _get_queue_events(db: Session, store_id: str) -> list:
    return (
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
                [
                    "BILLING_QUEUE_JOIN",
                    "BILLING_QUEUE_EXIT",
                    "BILLING_QUEUE_ABANDON",
                ]
            ),
        )
        .order_by(
            EventRecord.timestamp.asc(),
            EventRecord.session_seq.asc().nullsfirst(),
        )
        .all()
    )


def _get_queue_cycles(db: Session, store_id: str) -> dict:
    queue_events = _get_queue_events(db, store_id)

    open_join_by_visitor = {}
    completed_cycles = []
    abandoned_cycles = []
    joined_visitors = set()

    for event in queue_events:
        visitor_id = event.visitor_id
        event_type = event.event_type

        if event_type == "BILLING_QUEUE_JOIN":
            joined_visitors.add(visitor_id)

            if visitor_id not in open_join_by_visitor:
                open_join_by_visitor[visitor_id] = event.timestamp

        elif event_type in {"BILLING_QUEUE_EXIT", "BILLING_QUEUE_ABANDON"}:
            join_time = open_join_by_visitor.pop(visitor_id, None)

            if join_time is None:
                continue

            wait_ms = _milliseconds_between(join_time, event.timestamp)

            if wait_ms is None:
                continue

            cycle = {
                "visitor_id": visitor_id,
                "join_time": _datetime_to_iso(join_time),
                "exit_time": _datetime_to_iso(event.timestamp),
                "wait_ms": wait_ms,
            }

            if event_type == "BILLING_QUEUE_ABANDON":
                abandoned_cycles.append(cycle)
            else:
                completed_cycles.append(cycle)

    return {
        "joined_visitors": joined_visitors,
        "completed_cycles": completed_cycles,
        "abandoned_cycles": abandoned_cycles,
        "open_queue_visitors": set(open_join_by_visitor.keys()),
    }


def _compute_queue_summary(db: Session, store_id: str) -> dict:
    queue_state = _get_queue_cycles(db, store_id)

    joined_count = len(queue_state["joined_visitors"])
    completed_cycles = queue_state["completed_cycles"]
    abandoned_cycles = queue_state["abandoned_cycles"]
    completed_queue_cycles = len(completed_cycles)
    abandoned_queue_cycles = len(abandoned_cycles)
    current_queue_depth = len(queue_state["open_queue_visitors"])

    all_closed_cycles = completed_cycles + abandoned_cycles

    if all_closed_cycles:
        avg_queue_wait_ms = round(
            sum(cycle["wait_ms"] for cycle in all_closed_cycles)
            / len(all_closed_cycles),
            2,
        )
    else:
        avg_queue_wait_ms = 0.0

    return {
        "entered_billing_queue": joined_count,
        "completed_queue_cycles": completed_queue_cycles,
        "abandoned_queue_cycles": abandoned_queue_cycles,
        "current_queue_depth": current_queue_depth,
        "avg_queue_wait_ms": avg_queue_wait_ms,
        "queue_data_source": "event_stream",
    }


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
# Anomaly helpers
# ---------------------------------------------------------------------

def _build_anomaly(
    anomaly_type: str,
    severity: str,
    message: str,
    suggested_action: str,
    evidence: dict,
) -> dict:
    return {
        "type": anomaly_type,
        "severity": severity,
        "message": message,
        "suggested_action": suggested_action,
        "evidence": evidence,
    }


def _rollup_anomaly_status(anomalies: list) -> str:
    severities = {anomaly["severity"] for anomaly in anomalies}

    if "CRITICAL" in severities:
        return "CRITICAL"

    if "WARN" in severities:
        return "WARN"

    if "INFO" in severities:
        return "INFO"

    return "OK"


def _get_conversion_stats(db: Session, store_id: str) -> dict:
    total_visitors = _count_entered_store(db, store_id)
    converted_visitors = _count_converted_visitors(db, store_id)

    conversion_rate = (
        converted_visitors / total_visitors * 100
        if total_visitors > 0
        else 0.0
    )

    return {
        "total_visitors": total_visitors,
        "converted_visitors": converted_visitors,
        "conversion_rate_percentage": round(conversion_rate, 2),
    }


def _detect_queue_spike(db: Session, store_id: str) -> Optional[dict]:
    queue_summary = _compute_queue_summary(db, store_id)
    current_depth = queue_summary["current_queue_depth"]

    if current_depth >= QUEUE_SPIKE_CRITICAL_THRESHOLD:
        return _build_anomaly(
            anomaly_type="BILLING_QUEUE_SPIKE",
            severity="CRITICAL",
            message=f"Current billing queue depth is {current_depth}, above the critical threshold.",
            suggested_action="Immediately open additional billing counters and assign staff support.",
            evidence={
                "current_queue_depth": current_depth,
                "warn_threshold": QUEUE_SPIKE_WARN_THRESHOLD,
                "critical_threshold": QUEUE_SPIKE_CRITICAL_THRESHOLD,
            },
        )

    if current_depth >= QUEUE_SPIKE_WARN_THRESHOLD:
        return _build_anomaly(
            anomaly_type="BILLING_QUEUE_SPIKE",
            severity="WARN",
            message=f"Current billing queue depth is {current_depth}.",
            suggested_action="Open an additional billing counter or assign staff to checkout.",
            evidence={
                "current_queue_depth": current_depth,
                "warn_threshold": QUEUE_SPIKE_WARN_THRESHOLD,
                "critical_threshold": QUEUE_SPIKE_CRITICAL_THRESHOLD,
            },
        )

    return None


def _detect_conversion_drop(db: Session, store_id: str) -> Optional[dict]:
    stats = _get_conversion_stats(db, store_id)

    total_visitors = stats["total_visitors"]
    current_rate = stats["conversion_rate_percentage"]

    if total_visitors < MIN_VISITORS_FOR_CONVERSION_ANOMALY:
        return None

    critical_threshold = (
        BASELINE_CONVERSION_RATE_PERCENTAGE * CONVERSION_DROP_CRITICAL_FACTOR
    )
    warn_threshold = (
        BASELINE_CONVERSION_RATE_PERCENTAGE * CONVERSION_DROP_WARN_FACTOR
    )

    if current_rate < critical_threshold:
        return _build_anomaly(
            anomaly_type="CONVERSION_DROP",
            severity="CRITICAL",
            message=(
                f"Conversion rate is {current_rate}%, significantly below "
                f"the baseline of {BASELINE_CONVERSION_RATE_PERCENTAGE}%."
            ),
            suggested_action="Investigate billing flow, queue abandonment, and staff availability immediately.",
            evidence={
                "current_conversion_rate_percentage": current_rate,
                "baseline_conversion_rate_percentage": BASELINE_CONVERSION_RATE_PERCENTAGE,
                "critical_threshold_percentage": round(critical_threshold, 2),
                "warn_threshold_percentage": round(warn_threshold, 2),
                "total_visitors": total_visitors,
            },
        )

    if current_rate < warn_threshold:
        return _build_anomaly(
            anomaly_type="CONVERSION_DROP",
            severity="WARN",
            message=(
                f"Conversion rate is {current_rate}%, below "
                f"the expected baseline of {BASELINE_CONVERSION_RATE_PERCENTAGE}%."
            ),
            suggested_action="Review queue wait time, checkout staffing, and shopper assistance coverage.",
            evidence={
                "current_conversion_rate_percentage": current_rate,
                "baseline_conversion_rate_percentage": BASELINE_CONVERSION_RATE_PERCENTAGE,
                "critical_threshold_percentage": round(critical_threshold, 2),
                "warn_threshold_percentage": round(warn_threshold, 2),
                "total_visitors": total_visitors,
            },
        )

    return None


def _detect_dead_zones(db: Session, store_id: str) -> list:
    total_events = _get_total_event_count(db, store_id)

    if total_events < DEAD_ZONE_MIN_TOTAL_EVENTS:
        return []

    visit_counts = _get_zone_visit_counts(db, store_id)
    anomalies = []

    for zone_id in sorted(EXPECTED_PRODUCT_ZONES):
        if visit_counts.get(zone_id, 0) == 0:
            anomalies.append(
                _build_anomaly(
                    anomaly_type="DEAD_ZONE",
                    severity="WARN",
                    message=f"No customer visits detected in {zone_id}.",
                    suggested_action=(
                        "Check camera calibration, product-zone placement, "
                        "or whether the zone is being physically blocked."
                    ),
                    evidence={
                        "zone_id": zone_id,
                        "visit_count": 0,
                        "total_events": total_events,
                        "minimum_events_required": DEAD_ZONE_MIN_TOTAL_EVENTS,
                    },
                )
            )

    return anomalies


def _detect_stale_feed(db: Session, store_id: str) -> Optional[dict]:
    latest_timestamp = (
        db.query(func.max(EventRecord.timestamp))
        .filter(EventRecord.store_id == store_id)
        .scalar()
    )

    latest_dt = _normalize_datetime_to_utc(latest_timestamp)

    if latest_dt is None:
        return None

    feed_status, warnings = _get_feed_status(latest_dt)

    if feed_status != "STALE":
        return None

    return _build_anomaly(
        anomaly_type="STALE_FEED",
        severity="WARN",
        message="No recent CV events have been received for this store.",
        suggested_action="Check camera stream, edge worker process, and network connectivity.",
        evidence={
            "last_event_timestamp": latest_dt.isoformat(),
            "stale_threshold_minutes": STALE_FEED_THRESHOLD_MINUTES,
            "warnings": warnings,
        },
    )


# ---------------------------------------------------------------------
# Analytics endpoints
# ---------------------------------------------------------------------

@app.get("/stores/{store_id}/metrics", tags=["Analytics"])
async def get_store_metrics(store_id: str, db: Session = Depends(get_db)):
    stats = _get_conversion_stats(db, store_id)
    queue_summary = _compute_queue_summary(db, store_id)

    avg_dwell_ms_by_zone = _compute_avg_dwell_by_zone(db, store_id)
    total_events = _get_total_event_count(db, store_id)
    last_event_timestamp = _get_latest_event_timestamp(db, store_id)

    return {
        "store_id": store_id,
        "total_visitors": stats["total_visitors"],
        "converted_visitors": stats["converted_visitors"],
        "conversion_rate_percentage": stats["conversion_rate_percentage"],
        "current_queue_depth": queue_summary["current_queue_depth"],
        "avg_queue_wait_ms": queue_summary["avg_queue_wait_ms"],
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
    entered_store = _count_entered_store(db, store_id)
    zone_visit = _count_zone_visitors(db, store_id)
    converted = _count_converted_visitors(db, store_id)

    queue_summary = _compute_queue_summary(db, store_id)

    entered_billing = queue_summary["entered_billing_queue"]
    completed_queue_cycles = queue_summary["completed_queue_cycles"]
    abandoned_queue_cycles = queue_summary["abandoned_queue_cycles"]

    queue_abandonment_count = max(
        abandoned_queue_cycles,
        completed_queue_cycles - converted,
        0,
    )

    closed_queue_cycles = completed_queue_cycles + abandoned_queue_cycles

    queue_abandonment_rate = (
        round(queue_abandonment_count / closed_queue_cycles * 100, 2)
        if closed_queue_cycles > 0
        else 0.0
    )

    return {
        "store_id": store_id,
        "funnel_steps": {
            # Challenge-aligned funnel
            "1_entered_store": entered_store,
            "2_visited_zone": zone_visit,
            "3_entered_billing_queue": entered_billing,
            "4_completed_purchase": converted,

            # Backward-compatible keys used by earlier tests/dashboard
            "2_entered_billing_queue": entered_billing,
            "3_completed_purchase": converted,
        },
        "insights": {
            "queue_abandonment_count": queue_abandonment_count,
            "queue_abandonment_rate": queue_abandonment_rate,
            "avg_queue_wait_ms": queue_summary["avg_queue_wait_ms"],
            "completed_queue_cycles": completed_queue_cycles,
            "abandoned_queue_cycles": abandoned_queue_cycles,
            "current_queue_depth": queue_summary["current_queue_depth"],
            "queue_data_source": queue_summary["queue_data_source"],
        },
    }


@app.get("/stores/{store_id}/anomalies", tags=["Analytics"])
async def get_store_anomalies(store_id: str, db: Session = Depends(get_db)):
    anomalies = []

    queue_spike = _detect_queue_spike(db, store_id)
    if queue_spike is not None:
        anomalies.append(queue_spike)

    conversion_drop = _detect_conversion_drop(db, store_id)
    if conversion_drop is not None:
        anomalies.append(conversion_drop)

    anomalies.extend(_detect_dead_zones(db, store_id))

    stale_feed = _detect_stale_feed(db, store_id)
    if stale_feed is not None:
        anomalies.append(stale_feed)

    return {
        "store_id": store_id,
        "status": _rollup_anomaly_status(anomalies),
        "anomalies": anomalies,
    }