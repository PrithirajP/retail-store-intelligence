# DESIGN.md

# Retail Store Intelligence Platform — System Design

## 1. Purpose

This project converts CCTV footage and POS transaction data into store-level retail intelligence.

The system is designed to answer business questions such as:

- How many customers entered the store?
- How many customers reached the billing queue?
- How many converted into purchases?
- What is the conversion rate?
- Which product zones received attention?
- How long did customers dwell in zones?
- Is the billing queue becoming too long?
- Are there operational anomalies?

The implementation prioritizes:

- Acceptance-gate reliability
- Simple reviewer setup
- Explainable engineering decisions
- Business-relevant metrics
- Clear separation between edge CV and cloud analytics

---

## 2. Final Implemented Architecture

```text
CCTV video files
   ↓
cv_pipeline/orchestrator.py
   ↓
YOLOv8n person detection
   ↓
ByteTrack local tracking
   ↓
Polygon-based zone state machine
   ↓
Structured Event Schema v1.2
   ↓
FastAPI /events/ingest
   ↓
SQLite database
   ↓
Metrics / Funnel / Heatmap / Anomalies APIs
   ↓
Streamlit dashboard
```

The system is split into two runtime layers:

## 2.1 Cloud Layer

The cloud layer is containerized with Docker Compose.

Services:

```text
store-api
store-dashboard
```

### `store-api`

FastAPI backend responsible for:

- API health
- Event ingestion
- Event validation
- Idempotent persistence
- POS CSV seeding
- Visitor session materialization
- POS correlation
- Metrics endpoint
- Funnel endpoint
- Heatmap endpoint
- Anomaly endpoint
- Structured request logging

### `store-dashboard`

Streamlit dashboard responsible for:

- North Star KPIs
- Queue KPIs
- Funnel chart
- Health status
- Heatmap table/chart
- Active anomaly panel

## 2.2 Edge Layer

The edge CV worker currently runs outside Docker:

```bash
cd cv_pipeline
python orchestrator.py
```

This is deliberate. PyTorch, OpenCV, Ultralytics, and hardware acceleration can create Docker compatibility issues on reviewer machines. Running the CV worker locally improves the chance that the API and dashboard remain stable during evaluation.

---

## 3. Computer Vision Pipeline

## 3.1 Detection Model

Implemented detector:

```text
YOLOv8n
```

File:

```text
cv_pipeline/detector.py
```

Why YOLOv8n:

- Lightweight
- Fast on CPU compared with larger models
- Easy integration through Ultralytics
- Supports person-only detection
- Works well enough for challenge-scale analytics

The detector filters for the `person` class.

## 3.2 Tracking Model

Implemented tracker:

```text
ByteTrack
```

ByteTrack is used through the Ultralytics tracking interface.

Purpose:

- Maintain local identity within one camera
- Reduce ID fragmentation during short occlusion
- Avoid heavier Re-ID processing during every frame

## 3.3 Identity Model

Implemented:

```text
ByteTrack-local visitor IDs
```

Not implemented:

```text
Global cross-camera Re-ID
OSNet / TorchReID
REENTRY event generation
```

Current visitor IDs are local to the tracker. A person appearing in different cameras may receive different IDs.

This limitation is documented and accepted for the current challenge version.

Future design:

```text
YOLO crop → OSNet embedding → cosine similarity → global visitor ID
```

---

## 4. Zone Detection Strategy

Zone detection is polygon-based.

Implemented files:

```text
cv_pipeline/zone_mapper.py
cv_pipeline/tracker_state.py
cv_pipeline/orchestrator.py
```

The zone mapper allows manual clicking of polygon points on a video frame. The generated arrays are pasted into `CAMERA_CONFIGS` inside `orchestrator.py`.

Tracked point:

```text
bottom-center of bounding box
```

Reason:

The bottom-center point better represents the person’s physical floor location than the bounding-box center.

Zone logic uses:

```python
cv2.pointPolygonTest(...)
```

Implemented zone types:

```text
ENTRY_DOOR
BILLING_QUEUE
BEHIND_COUNTER
MAKEUP
SKINCARE
```

---

## 5. Staff Detection Strategy

Implemented staff detection:

```text
Behind-counter spatial heuristic
```

Rule:

```text
If a visitor stays inside BEHIND_COUNTER for more than 30 consecutive frames,
mark that visitor as staff.
```

Staff events are excluded from customer-facing analytics.

Strength:

- Very low compute overhead
- Deterministic
- Works well for cashiers

Known limitation:

- Roaming staff in aisles may still be counted as customers.

Future improvement:

- Lightweight staff classifier for aisle staff
- Uniform/lanyard classifier on cropped person images
- Staff registry using appearance embeddings

---

## 6. Event Schema

Implemented schema:

```text
Event Schema v1.2
```

The event payload preserves flattened fields and adds nested metadata.

## 6.1 Core Event Fields

```text
event_id
store_id
camera_id
visitor_id
timestamp
event_type
zone_id
dwell_ms
is_staff
confidence
metadata
```

## 6.2 Metadata Fields

```text
metadata.queue_depth
metadata.sku_zone
metadata.session_seq
```

## 6.3 Supported Event Types

```text
ENTRY
EXIT
ZONE_ENTER
ZONE_EXIT
ZONE_DWELL
BILLING_QUEUE_JOIN
BILLING_QUEUE_EXIT
REENTRY
BILLING_QUEUE_ABANDON
```

Important distinction:

- `REENTRY` is schema-supported but not currently emitted.
- `BILLING_QUEUE_ABANDON` is schema-supported but not currently emitted as a raw CV event.
- Queue abandonment is calculated in the API as an aggregate metric.

---

## 7. Event Generation

Implemented in:

```text
cv_pipeline/tracker_state.py
cv_pipeline/orchestrator.py
```

Generated event types:

```text
ENTRY
ZONE_ENTER
ZONE_EXIT
ZONE_DWELL
BILLING_QUEUE_JOIN
BILLING_QUEUE_EXIT
```

`orchestrator.py` rewrites:

```text
ZONE_ENTER at ENTRY_DOOR → ENTRY
```

Event batching is handled by:

```text
cv_pipeline/event_emitter.py
```

The emitter sends batches to:

```text
POST http://127.0.0.1:8000/events/ingest
```

---

## 8. API Design

Implemented API framework:

```text
FastAPI
```

Implemented endpoints:

```text
GET  /health
POST /events/ingest
GET  /stores/{store_id}/metrics
GET  /stores/{store_id}/funnel
GET  /stores/{store_id}/heatmap
GET  /stores/{store_id}/anomalies
```

## 8.1 Health Endpoint

```text
GET /health
```

Reports:

- API status
- Database status
- Last event timestamp per store
- Feed freshness
- Stale-feed warnings

## 8.2 Event Ingestion

```text
POST /events/ingest
```

Features:

- Batch ingestion
- Maximum 500 events per request
- Per-event validation
- Partial success handling
- Duplicate event idempotency
- Structured response counters

Response includes:

```text
received_count
processed_count
duplicate_count
error_count
errors
```

## 8.3 Metrics Endpoint

```text
GET /stores/{store_id}/metrics
```

Returns:

- Total visitors
- Converted visitors
- Conversion rate
- Current queue depth
- Average queue wait
- Average dwell by zone
- Total events
- Last event timestamp

## 8.4 Funnel Endpoint

```text
GET /stores/{store_id}/funnel
```

Returns:

- Entered store
- Entered billing queue
- Completed purchase
- Queue abandonment count
- Queue abandonment rate
- Average queue wait
- Completed queue cycles
- Current queue depth

Queue metrics are computed from raw billing queue events rather than relying only on sessions.

## 8.5 Heatmap Endpoint

```text
GET /stores/{store_id}/heatmap
```

Returns:

- Zone visit counts
- Average dwell per zone
- Heat score
- Data confidence

Excluded zones:

```text
ENTRY_DOOR
BILLING_QUEUE
BEHIND_COUNTER
```

## 8.6 Anomalies Endpoint

```text
GET /stores/{store_id}/anomalies
```

Implemented anomaly types:

```text
BILLING_QUEUE_SPIKE
CONVERSION_DROP
DEAD_ZONE
STALE_FEED
```

Each anomaly includes:

```text
type
severity
message
suggested_action
evidence
```

---

## 9. Database Design

Database:

```text
SQLite
```

ORM:

```text
SQLAlchemy
```

SQLite is used for simple challenge deployment.

## 9.1 Tables

### `events`

Raw event ledger.

Stores:

```text
event_id
store_id
camera_id
visitor_id
event_type
timestamp
zone_id
dwell_ms
is_staff
confidence
queue_depth
sku_zone
session_seq
```

### `sessions`

Materialized visitor lifecycle table.

Stores:

```text
visitor_id
store_id
entry_time
last_seen_time
billing_join_time
billing_exit_time
is_converted
is_staff
```

### `pos_transactions`

Seeded POS transaction table.

Stores:

```text
transaction_id
store_id
timestamp
basket_value_inr
claimed_by_visitor_id
```

---

## 10. POS Correlation

Implemented in:

```text
api/database.py
```

When a visitor exits the billing queue, the API attempts to match that exit with a POS transaction.

Rule:

```text
Find an unclaimed transaction from the same store within the 5-minute window before billing exit.
```

If matched:

```text
pos_transactions.claimed_by_visitor_id = visitor_id
sessions.is_converted = True
```

This prevents double-counting the same transaction.

Known limitation:

Because full cross-camera Re-ID is not implemented, POS correlation is only as reliable as the visitor ID observed in the billing camera.

---

## 11. Queue Analytics

Queue analytics are derived mainly from the raw event stream.

Implemented queue events:

```text
BILLING_QUEUE_JOIN
BILLING_QUEUE_EXIT
```

Queue cycle logic:

```text
JOIN starts queue cycle
EXIT closes queue cycle
JOIN without EXIT contributes to current_queue_depth
```

Computed metrics:

```text
entered_billing_queue
completed_queue_cycles
current_queue_depth
avg_queue_wait_ms
queue_abandonment_count
queue_abandonment_rate
```

Reason for event-derived queue logic:

Since global cross-camera Re-ID is not implemented, raw billing queue events are more reliable for queue analytics than relying only on `VisitorSession`.

---

## 12. Heatmap Analytics

Heatmap is zone-level, not pixel-level.

Inputs:

```text
ZONE_ENTER
ZONE_DWELL
```

Metrics:

```text
visit_count
avg_dwell_ms
heat_score
```

Heat score formula:

```text
heat_score = 0.6 * normalized_visit_count + 0.4 * normalized_avg_dwell
```

Returned score range:

```text
0 to 100
```

Data confidence:

```text
NO_DATA
LOW
MEDIUM
HIGH
```

---

## 13. Anomaly Detection

Implemented anomaly detection is rule-based.

No ML anomaly model is used.

Reasons:

- Faster to implement
- Explainable
- Deterministic
- Easy to validate
- Appropriate for challenge timeline

Implemented rules:

## 13.1 Billing Queue Spike

```text
WARN     if current_queue_depth >= 5
CRITICAL if current_queue_depth >= 8
```

## 13.2 Conversion Drop

Uses fallback baseline:

```text
BASELINE_CONVERSION_RATE_PERCENTAGE = 25.0
```

Rules:

```text
WARN     if current conversion < 70% of baseline
CRITICAL if current conversion < 50% of baseline
```

Guard:

```text
Do not trigger if total visitors < 5
```

## 13.3 Dead Zone

Expected zones:

```text
MAKEUP
SKINCARE
```

Rule:

```text
If total event count > 20 and expected zone has 0 visits → WARN
```

## 13.4 Stale Feed

Rule:

```text
If latest event is older than 10 minutes → WARN
```

---

## 14. Dashboard Design

Framework:

```text
Streamlit
```

Implemented dashboard panels:

```text
System Health
North Star KPIs
Queue and Event KPIs
Shopper Funnel
Queue Insights
Active Anomalies
Zone Heatmap
Average Product-Zone Dwell
```

Dashboard calls:

```text
GET /health
GET /stores/ST1008/metrics
GET /stores/ST1008/funnel
GET /stores/ST1008/heatmap
GET /stores/ST1008/anomalies
```

Refresh method:

```text
time.sleep(5)
st.rerun()
```

Known limitation:

Polling causes some UI flicker. A production system should use WebSockets or server-sent events.

---

## 15. Structured Logging

Implemented in:

```text
api/main.py
```

Every request logs a JSON-style structured record.

Fields:

```text
trace_id
method
endpoint
status_code
latency_ms
store_id
client_host
```

Every response includes:

```text
X-Trace-Id
```

Ingestion additionally logs:

```text
received_count
processed_count
duplicate_count
error_count
status
```

No external logging dependency is used.

---

## 16. Testing Strategy

Implemented tests:

```text
pytest
FastAPI TestClient
in-memory SQLite database
```

Test folder:

```text
tests/
```

Test coverage focus:

- Health endpoint
- Valid event ingestion
- Duplicate event idempotency
- Partial success for malformed events
- Empty-state metrics
- Empty-state funnel
- Empty-state heatmap
- Empty-state anomalies

Current validation:

```text
8 passed
```

CV model tests are not implemented because YOLO/ByteTrack behavior depends on video files, model state, and local hardware.

---

## 17. Deployment Strategy

Implemented Docker Compose services:

```text
store-api
store-dashboard
```

Run:

```bash
docker compose up --build
```

Then run CV edge worker separately:

```bash
cd cv_pipeline
python orchestrator.py
```

This split simulates an edge-cloud architecture.

Known deployment limitation:

The full system is not started by a single `docker compose up` command because the CV worker is outside Docker.

---

## 18. Implemented vs Planned

## Implemented

```text
YOLOv8n detection
ByteTrack local tracking
Polygon zone detection
Staff behind-counter heuristic
Event Schema v1.2
FastAPI ingestion
Full event persistence
SQLite database
POS seeding
POS correlation
Metrics endpoint
Funnel endpoint
Heatmap endpoint
Anomaly endpoint
Health endpoint
Structured logging
Streamlit dashboard
Minimal pytest suite
```

## Planned / Future

```text
OSNet / TorchReID global Re-ID
REENTRY event generation
Dedicated queue engine module
PostgreSQL migration
Alembic migrations
Persistent edge buffer / DLQ
Containerized CV worker
Concurrent multi-camera processing
WebSocket dashboard updates
CV state-machine tests
```

---

## 19. Known Limitations

1. Full cross-camera Re-ID is not implemented.
2. ByteTrack IDs are camera-local.
3. `REENTRY` is schema-supported but not emitted.
4. `BILLING_QUEUE_ABANDON` is aggregate-derived, not emitted by CV.
5. CV pipeline runs locally outside Docker.
6. Camera polygons are hardcoded.
7. SQLite is used instead of PostgreSQL.
8. CV processing can be slow on CPU.
9. Dashboard uses polling instead of WebSockets.
10. Roaming staff may be counted as customers.

---

## 20. Final Design Summary

The implemented system is a pragmatic, challenge-ready retail intelligence platform.

It prioritizes:

```text
working software
clear API behavior
reviewer-friendly deployment
business metrics
structured documentation
honest limitations
```

The main missing production feature is full global identity resolution across cameras.