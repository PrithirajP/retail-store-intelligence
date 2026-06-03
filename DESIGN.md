# DESIGN.md

# Retail Store Intelligence Platform — System Design

## 1. Purpose

This project converts CCTV-style store video signals and POS transaction records into store-level retail intelligence.

The system is designed to estimate and expose:

* total visitors
* product-zone visits
* billing queue participation
* completed purchases
* conversion rate
* queue abandonment
* average queue wait time
* zone dwell summaries
* heatmap-style zone engagement
* operational anomalies
* API health and feed freshness

The implementation prioritizes:

* acceptance-gate reliability
* clear API behavior
* reviewer-friendly setup
* business-relevant metrics
* honest documentation of limitations
* incremental implementation under challenge constraints

---

## 2. Final Architecture

```text
CCTV clips / sample event payloads
        ↓
Edge CV pipeline or sample event replay
        ↓
Raw event payloads
        ↓
Event normalization layer
        ↓
Canonical Event Schema v1.2
        ↓
FastAPI ingestion API
        ↓
SQLite database
        ↓
Metrics / Funnel / Heatmap / Anomalies / Health endpoints
        ↓
Streamlit dashboard
```

The system has two runtime layers.

---

## 3. Cloud Layer

The cloud layer is containerized with Docker Compose.

Services:

```text
store-api
store-dashboard
```

### `store-api`

The API service is built with FastAPI.

Responsibilities:

* event ingestion
* event normalization
* event validation
* duplicate event idempotency
* partial-success ingestion
* SQLite persistence
* POS data seeding
* POS correlation
* visitor session materialization
* metrics calculation
* funnel calculation
* heatmap calculation
* anomaly detection
* health monitoring
* structured request logging

### `store-dashboard`

The dashboard service is built with Streamlit.

Responsibilities:

* system health panel
* store selector
* North Star KPI cards
* queue KPI cards
* four-stage funnel visualization
* anomaly panel
* heatmap table/chart
* dwell summary

---

## 4. Edge CV Layer

The CV pipeline currently runs on the host machine:

```bash
cd cv_pipeline
python orchestrator.py
```

This is an intentional edge-cloud split.

The API and dashboard run in Docker. The CV worker runs locally to avoid PyTorch/OpenCV/Ultralytics container compatibility problems on reviewer machines.

This is documented as a production-readiness limitation, but it protects the acceptance gate by ensuring the API and dashboard start reliably.

---

## 5. Detection Model

Implemented model:

```text
YOLOv8n
```

Reason for selection:

* lightweight
* CPU-friendly compared with larger detectors
* easy Ultralytics integration
* supports person detection
* compatible with ByteTrack tracking
* fast enough for challenge-scale processing

Known limitation:

YOLOv8n can miss partially occluded or distant shoppers, especially in crowded or low-light CCTV footage.

---

## 6. Tracking Model

Implemented tracker:

```text
ByteTrack
```

Reason for selection:

* strong local tracking performance
* better low-confidence detection handling than simple SORT
* lower complexity than DeepSORT / BoT-SORT / StrongSORT
* integrates easily through Ultralytics

Known limitation:

ByteTrack IDs are camera-local. A shopper moving across cameras may receive multiple identities.

---

## 7. Re-ID Strategy

Current implementation:

```text
Full cross-camera Re-ID is not implemented.
```

Current identity strategy:

```text
ByteTrack-local visitor IDs
```

Supported at API schema level:

```text
REENTRY
session_seq
visitor_id
store_id
camera_id
```

Not fully implemented in CV:

```text
global visitor identity
OSNet / TorchReID embeddings
cross-camera identity stitching
robust REENTRY emission
```

Future design:

```text
person crop → Re-ID embedding → vector similarity → global visitor ID → session stitching
```

Reason for deferral:

Full Re-ID requires additional model integration, embedding storage, threshold tuning, and cross-camera state management. Under the challenge timeline, the safer decision was to complete the full API/database/dashboard pipeline first.

---

## 8. Zone Detection Strategy

Implemented approach:

```text
manual polygon zones + bottom-center point of bounding box
```

Zone mapping files:

```text
cv_pipeline/zone_mapper.py
cv_pipeline/tracker_state.py
cv_pipeline/orchestrator.py
```

The zone engine checks whether the tracked bottom-center point lies inside a manually calibrated polygon.

Implemented logical zones include:

```text
ENTRY_DOOR
BILLING_QUEUE
BEHIND_COUNTER
MAKEUP
SKINCARE
```

Layout images are useful as store-planning references, but CCTV pixel polygons still require camera-space calibration. Floor-plan coordinates cannot be directly used as CCTV coordinates without homography calibration.

---

## 9. Staff Detection Strategy

Implemented staff exclusion:

```text
behind-counter spatial heuristic
```

Rule:

```text
If a person stays inside BEHIND_COUNTER for more than 30 consecutive frames,
mark the visitor as staff.
```

Strength:

* simple
* deterministic
* very low compute overhead
* removes cashier noise from queue analytics

Known limitation:

Roaming staff in aisles may still be counted as customers.

Future improvement:

* staff lanyard/uniform classifier
* lightweight MobileNet-style crop classifier
* staff identity registry
* Re-ID-assisted staff filtering

---

## 10. Event Schema

Internal canonical schema:

```text
Event Schema v1.2
```

Core fields:

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

Metadata fields:

```text
metadata.queue_depth
metadata.sku_zone
metadata.session_seq
```

Supported event types:

```text
ENTRY
EXIT
ZONE_ENTER
ZONE_EXIT
ZONE_DWELL
BILLING_QUEUE_JOIN
BILLING_QUEUE_EXIT
BILLING_QUEUE_ABANDON
REENTRY
```

---

## 11. Event Normalization Layer

The ingestion API now supports both:

```text
canonical Event Schema v1.2
```

and uploaded challenge-style sample events using fields such as:

```text
id_token
track_id
store_code
event_timestamp
event_time
queue_exit_ts
queue_served_ts
queue_join_ts
queue_completed
queue_abandoned
zone_entered
zone_exited
```

Normalization examples:

```text
id_token → visitor_id
track_id → visitor_id
store_code → store_id
event_timestamp/event_time → timestamp
zone_entered → ZONE_ENTER
zone_exited → ZONE_EXIT
queue_completed → BILLING_QUEUE_EXIT
queue_abandoned → BILLING_QUEUE_ABANDON
queue_position_at_join → metadata.queue_depth
zone_name → metadata.sku_zone
```

This keeps the internal schema stable while making the API tolerant to provided sample event formats.

---

## 12. API Design

Framework:

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

### `POST /events/ingest`

Features:

* batch ingestion
* max 500 events
* event normalization
* per-event validation
* duplicate event idempotency
* partial success
* structured response counters

Response counters:

```text
received_count
processed_count
duplicate_count
error_count
errors
```

### `GET /stores/{store_id}/metrics`

Returns:

* total visitors
* converted visitors
* conversion rate
* current queue depth
* average queue wait
* average dwell by zone
* total event count
* last event timestamp

### `GET /stores/{store_id}/funnel`

Challenge-aligned funnel:

```text
Entered Store → Visited Product Zone → Entered Billing Queue → Completed Purchase
```

Returned keys:

```text
1_entered_store
2_visited_zone
3_entered_billing_queue
4_completed_purchase
```

Backward-compatible keys are also preserved:

```text
2_entered_billing_queue
3_completed_purchase
```

### `GET /stores/{store_id}/heatmap`

Returns zone-level engagement:

```text
zone_id
visit_count
avg_dwell_ms
heat_score
data_confidence
```

### `GET /stores/{store_id}/anomalies`

Implemented rule-based anomaly types:

```text
BILLING_QUEUE_SPIKE
CONVERSION_DROP
DEAD_ZONE
STALE_FEED
```

### `GET /health`

Reports:

* API status
* database status
* latest event timestamp per store
* feed freshness
* warnings

---

## 13. Database Design

Database:

```text
SQLite
```

ORM:

```text
SQLAlchemy
```

Tables:

```text
events
sessions
pos_transactions
```

### `events`

Stores raw normalized event records:

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

Stores materialized visitor state:

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

Stores POS ground truth:

```text
transaction_id
store_id
timestamp
basket_value_inr
claimed_by_visitor_id
```

Known limitation:

SQLite is acceptable for challenge evaluation but should be replaced by PostgreSQL in production.

---

## 14. POS Seeding

The POS seeder supports both:

### Official-style schema

```text
transaction_id
store_id
timestamp
basket_value_inr
```

### Uploaded/current schema

```text
order_id
order_date
order_time
store_id
product_id
brand_name
total_amount
```

The parser skips malformed rows, deduplicates transaction IDs, and returns a seed summary.

---

## 15. POS Correlation

When a visitor exits billing, the API attempts to correlate that event with POS transactions.

Rule:

```text
Find an unclaimed POS transaction from the same store within the 5-minute window before billing exit.
```

If matched:

```text
pos_transactions.claimed_by_visitor_id = visitor_id
sessions.is_converted = True
```

Known limitation:

Without full cross-camera Re-ID, conversion attribution is strongest inside the billing camera but not globally perfect.

---

## 16. Funnel Logic

The funnel now follows:

```text
1. Entered Store
2. Visited Product Zone
3. Entered Billing Queue
4. Completed Purchase
```

Stage sources:

```text
Entered Store: sessions with entry_time
Visited Product Zone: distinct non-staff visitors with ZONE_ENTER or ZONE_DWELL
Entered Billing Queue: BILLING_QUEUE_JOIN
Completed Purchase: sessions marked is_converted
```

Queue insights are derived from:

```text
BILLING_QUEUE_JOIN
BILLING_QUEUE_EXIT
BILLING_QUEUE_ABANDON
```

---

## 17. Heatmap Logic

Heatmap is zone-level, not pixel-level.

Inputs:

```text
ZONE_ENTER
ZONE_DWELL
```

Outputs:

```text
visit_count
avg_dwell_ms
heat_score
```

Heat score:

```text
0.6 × normalized visit count + 0.4 × normalized dwell
```

Excluded non-product zones:

```text
ENTRY_DOOR
BILLING_QUEUE
BEHIND_COUNTER
```

---

## 18. Anomaly Detection

Implemented anomaly detection is rule-based.

Rules:

```text
BILLING_QUEUE_SPIKE:
WARN if current_queue_depth >= 5
CRITICAL if current_queue_depth >= 8

CONVERSION_DROP:
WARN / CRITICAL based on current conversion below a fixed baseline

DEAD_ZONE:
Expected product zone has zero visits after enough total events

STALE_FEED:
Latest event older than configured threshold
```

This design is explainable, deterministic, and suitable for challenge evaluation.

---

## 19. Dashboard Design

Framework:

```text
Streamlit
```

Dashboard panels:

```text
store selector
system health
North Star KPIs
queue/event KPIs
four-stage shopper funnel
queue insights
active anomalies
zone heatmap
average product-zone dwell
```

The dashboard supports:

```text
ST1008
STORE_BLR_002
ST1076
store_1076
```

This supports the current sample store, acceptance-gate store, and sample-event stores.

---

## 20. Structured Logging

Implemented in:

```text
api/main.py
```

Every API request logs:

```text
trace_id
method
endpoint
status_code
latency_ms
store_id
client_host
```

Ingestion additionally logs:

```text
received_count
processed_count
duplicate_count
error_count
status
```

Every response includes:

```text
X-Trace-Id
```

---

## 21. Testing Strategy

Implemented test strategy:

```text
pytest
FastAPI TestClient
in-memory SQLite test DB
```

Test coverage includes:

* health endpoint
* valid event ingestion
* duplicate event idempotency
* malformed event partial success
* sample-event normalization
* acceptance-gate store safety
* POS schema variants
* session-based funnel
* populated heatmap
* anomaly rules
* staff filtering

CV model tests are not automated because YOLO/ByteTrack behavior depends on video files, model versions, and local hardware. CV behavior is validated manually by running the orchestrator.

---

## 22. AI-Assisted Decisions

AI assistance was used as an engineering review and implementation-planning tool, not as an uncontrolled code generator.

### AI suggestion accepted: event normalization adapter

AI identified that the uploaded sample events used a different schema from the internal Event Schema v1.2. The accepted decision was to add a normalization layer before Pydantic validation instead of rewriting the entire schema.

Reason accepted:

* low implementation risk
* improves compatibility
* protects API scoring
* keeps internal schema stable

### AI suggestion accepted: event-derived queue analytics

AI recommended computing queue depth and wait time from raw queue events instead of relying only on session state.

Reason accepted:

* queue events are local to the billing camera
* avoids overdependence on missing global Re-ID
* improves queue metric reliability

### AI suggestion partially accepted: full session-based funnel

AI identified that the challenge expects a four-stage funnel. The accepted implementation adds `Visited Product Zone` while preserving backward-compatible response keys.

Reason partially accepted:

* improves challenge compliance
* avoids breaking existing dashboard/tests

### AI suggestion rejected: immediate full Re-ID implementation

AI suggested OSNet/TorchReID-style Re-ID as a production solution. This was rejected for the challenge implementation because it would increase dependency risk and implementation time.

Reason rejected:

* high complexity
* threshold tuning required
* additional model integration
* risk of destabilizing existing pipeline

### AI suggestion rejected: fully containerizing CV immediately

AI suggested full Dockerization of the CV worker for production. This was deferred because PyTorch/OpenCV/Ultralytics containers can create reviewer-machine compatibility problems.

Reason rejected for now:

* high Docker image complexity
* possible GPU/CPU dependency issues
* API/dashboard stability was higher priority

---

## 23. Implemented vs Planned

### Implemented

```text
YOLOv8n detection
ByteTrack local tracking
manual polygon zone detection
behind-counter staff heuristic
Event Schema v1.2
event normalization adapter
FastAPI ingestion
partial-success handling
event persistence
SQLite database
dual POS schema parser
POS correlation
metrics endpoint
four-stage funnel endpoint
heatmap endpoint
anomalies endpoint
health endpoint
structured logging
Streamlit dashboard
expanded pytest tests
```

### Planned / Future

```text
global cross-camera Re-ID
full REENTRY emission from CV
periodic ZONE_DWELL every 30 seconds from CV
fully Dockerized CV profile
PostgreSQL migration
Alembic migrations
persistent edge buffer / DLQ
WebSocket dashboard updates
CV state-machine tests
```

---

## 24. Known Limitations

1. Full cross-camera Re-ID is not implemented.
2. ByteTrack IDs are camera-local.
3. CV pipeline runs locally outside Docker.
4. Camera polygons are manually calibrated and hardcoded.
5. `REENTRY` is schema-supported but not robustly emitted by CV.
6. `ZONE_DWELL` cadence may not fully match every-30-second production behavior.
7. SQLite is used instead of PostgreSQL.
8. Dashboard uses polling, not WebSockets.
9. Roaming staff may still be counted as customers.
10. CV processing can be slow on CPU.

---

## 25. Final Design Summary

The implemented system is a pragmatic challenge-ready retail intelligence platform.

It prioritizes:

```text
working software
API robustness
schema compatibility
business metrics
dashboard visibility
testability
honest limitations
```

The largest remaining production gap is global cross-camera identity resolution.
