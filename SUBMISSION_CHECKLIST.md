# SUBMISSION_CHECKLIST.md

# Retail Store Intelligence Platform — Submission Checklist

This file summarizes the current implementation status and reviewer commands.

---

## 1. Quick Run Commands

### Start API and Dashboard

```bash
docker compose up --build
```

Open:

```text
http://localhost:8000/health
http://localhost:8501
```

### Run CV Pipeline

In another terminal:

```bash
cd cv_pipeline
python orchestrator.py
```

### Run Tests

From project root:

```bash
pytest
```

---

## 2. Data Placement

Expected project structure:

```text
retail-store-intelligence/
└── data/
    ├── Brigade_Bangalore_10_April_26.csv
    ├── CAM_01.mp4
    ├── CAM_02.mp4
    ├── CAM_03.mp4
    └── CAM_05.mp4
```

The API seeds POS data from:

```text
/app/data/Brigade_Bangalore_10_April_26.csv
```

inside the Docker container.

---

## 3. Acceptance Gate Status

| Requirement                                                   | Status                |
| ------------------------------------------------------------- | --------------------- |
| Docker Compose starts API                                     | Implemented           |
| Docker Compose starts dashboard                               | Implemented           |
| `/health` returns valid JSON                                  | Implemented           |
| `/stores/ST1008/metrics` returns valid JSON                   | Implemented           |
| `/stores/STORE_BLR_002/metrics` returns valid zero-state JSON | Implemented / tested  |
| Event ingestion works                                         | Implemented           |
| Duplicate event idempotency                                   | Implemented / tested  |
| Partial-success ingestion                                     | Implemented / tested  |
| Dashboard available at port 8501                              | Implemented           |
| CV pipeline runnable                                          | Implemented host-side |
| Full CV containerization                                      | Not implemented       |

---

## 4. API Endpoints

### Health

```text
GET /health
```

Status:

```text
IMPLEMENTED
```

Reports:

```text
API status
database status
latest event timestamp by store
feed freshness
warnings
```

---

### Event Ingestion

```text
POST /events/ingest
```

Status:

```text
IMPLEMENTED
```

Features:

```text
batch ingestion
maximum 500 events
event normalization
Pydantic validation
duplicate idempotency
partial success
structured response counters
```

Supports both:

```text
canonical Event Schema v1.2
sample_events.jsonl-style payloads
```

---

### Metrics

```text
GET /stores/{store_id}/metrics
```

Status:

```text
IMPLEMENTED
```

Returns:

```text
total_visitors
converted_visitors
conversion_rate_percentage
current_queue_depth
avg_queue_wait_ms
avg_dwell_ms_by_zone
total_events
last_event_timestamp
```

---

### Funnel

```text
GET /stores/{store_id}/funnel
```

Status:

```text
IMPLEMENTED
```

Challenge-aligned stages:

```text
1_entered_store
2_visited_zone
3_entered_billing_queue
4_completed_purchase
```

Backward-compatible keys preserved:

```text
2_entered_billing_queue
3_completed_purchase
```

---

### Heatmap

```text
GET /stores/{store_id}/heatmap
```

Status:

```text
IMPLEMENTED
```

Returns:

```text
zone_id
visit_count
avg_dwell_ms
heat_score
data_confidence
```

---

### Anomalies

```text
GET /stores/{store_id}/anomalies
```

Status:

```text
IMPLEMENTED
```

Implemented anomaly types:

```text
BILLING_QUEUE_SPIKE
CONVERSION_DROP
DEAD_ZONE
STALE_FEED
```

---

## 5. Event Schema

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

Metadata:

```text
queue_depth
sku_zone
session_seq
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

## 6. Sample Event Compatibility

Status:

```text
IMPLEMENTED
```

The API normalizes fields such as:

```text
id_token → visitor_id
track_id → visitor_id
store_code → store_id
event_timestamp/event_time → timestamp
zone_entered → ZONE_ENTER
zone_exited → ZONE_EXIT
queue_completed → BILLING_QUEUE_EXIT
queue_abandoned → BILLING_QUEUE_ABANDON
```

This protects ingestion against uploaded challenge sample-event formats.

---

## 7. POS Compatibility

Status:

```text
IMPLEMENTED
```

Supported POS formats:

### Official-style format

```text
transaction_id
store_id
timestamp
basket_value_inr
```

### Uploaded/current format

```text
order_id
order_date
order_time
store_id
total_amount
```

The parser:

```text
skips malformed rows
deduplicates transaction IDs
supports zero-value transactions
returns safe summary for missing files
```

---

## 8. Dashboard

URL:

```text
http://localhost:8501
```

Status:

```text
IMPLEMENTED
```

Dashboard panels:

```text
store selector
system health
North Star KPIs
queue and event KPIs
four-stage funnel
queue insights
active anomalies
zone heatmap
average product-zone dwell
```

Supported store selector options:

```text
ST1008
STORE_BLR_002
ST1076
store_1076
```

---

## 9. Computer Vision Pipeline

Entrypoint:

```text
cv_pipeline/orchestrator.py
```

Run:

```bash
cd cv_pipeline
python orchestrator.py
```

Status:

```text
IMPLEMENTED HOST-SIDE
```

Implemented CV components:

```text
YOLOv8n person detection
ByteTrack local tracking
bottom-center point extraction
polygon zone detection
behind-counter staff heuristic
billing queue join/exit events
zone dwell events
batched API event emission
```

Known limitation:

```text
CV runs outside Docker.
Processing can be slow on CPU.
Full cross-camera Re-ID is not implemented.
```

---

## 10. Staff Exclusion

Status:

```text
IMPLEMENTED
```

Method:

```text
Behind-counter spatial heuristic
```

Staff events are excluded from:

```text
metrics
funnel
heatmap
queue analytics
```

Known limitation:

```text
Roaming staff may still be counted as customers.
```

---

## 11. Queue Logic

Status:

```text
IMPLEMENTED
```

Queue events:

```text
BILLING_QUEUE_JOIN
BILLING_QUEUE_EXIT
BILLING_QUEUE_ABANDON
```

Computed metrics:

```text
current_queue_depth
avg_queue_wait_ms
completed_queue_cycles
abandoned_queue_cycles
queue_abandonment_count
queue_abandonment_rate
```

---

## 12. Testing Status

Test framework:

```text
pytest
```

Test areas:

```text
health
event ingestion
duplicate idempotency
partial success
sample-event normalization
acceptance-gate store safety
POS schema variants
session-based funnel
populated heatmap
average dwell
anomaly rules
staff filtering
```

After Phase 5, expected test count:

```text
32 passed
```

If some optional phases were skipped, the count may be lower, but all included tests should pass.

---

## 13. Logging

Status:

```text
IMPLEMENTED
```

Structured request log fields:

```text
trace_id
method
endpoint
status_code
latency_ms
store_id
client_host
```

Ingest batch log fields:

```text
received_count
processed_count
duplicate_count
error_count
status
```

Response header:

```text
X-Trace-Id
```

---

## 14. AI-Assisted Decisions

Status:

```text
DOCUMENTED
```

See:

```text
DESIGN.md
CHOICES.md
```

Important AI-assisted decisions documented:

```text
event normalization adapter accepted
event-derived queue analytics accepted
session-based funnel accepted
full Re-ID deferred
full CV Dockerization deferred
```

---

## 15. Final Feature Status

| Feature                    | Status          |
| -------------------------- | --------------- |
| Dockerized API             | Implemented     |
| Dockerized dashboard       | Implemented     |
| Host-side CV worker        | Implemented     |
| YOLOv8n detection          | Implemented     |
| ByteTrack tracking         | Implemented     |
| Polygon zones              | Implemented     |
| Staff exclusion            | Implemented     |
| Event Schema v1.2          | Implemented     |
| Sample event normalization | Implemented     |
| Full event persistence     | Implemented     |
| POS dual schema parser     | Implemented     |
| POS correlation            | Implemented     |
| Metrics endpoint           | Implemented     |
| Four-stage funnel endpoint | Implemented     |
| Heatmap endpoint           | Implemented     |
| Anomaly endpoint           | Implemented     |
| Health endpoint            | Implemented     |
| Structured logging         | Implemented     |
| Dashboard upgrade          | Implemented     |
| Pytest suite               | Implemented     |
| Cross-camera Re-ID         | Not implemented |
| Fully Dockerized CV        | Not implemented |

---

## 16. Known Limitations

1. CV pipeline runs locally outside Docker.
2. Cross-camera Re-ID is not implemented.
3. ByteTrack IDs are camera-local.
4. Camera polygons are manually calibrated and hardcoded.
5. `REENTRY` is schema-supported but not robustly emitted by CV.
6. `ZONE_DWELL` cadence may not fully satisfy every-30-second production behavior.
7. SQLite is used instead of PostgreSQL.
8. Dashboard uses polling, not WebSockets.
9. Roaming staff may still be counted as customers.
10. CV processing may be slow on CPU.

---

## 17. Final Submission Confidence

Current status:

```text
READY FOR SUBMISSION WITH DOCUMENTED LIMITATIONS
```

Strong points:

```text
API works
Docker works for API/dashboard
Dashboard works
Event ingestion is robust
Sample events are normalized
POS schema variants are supported
Metrics/funnel/heatmap/anomalies are implemented
Tests cover key edge cases
Documentation is honest
```

Main limitations:

```text
No global cross-camera Re-ID
CV worker outside Docker
Manual polygon calibration
```
