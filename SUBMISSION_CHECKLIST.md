# SUBMISSION_CHECKLIST.md

# Retail Store Intelligence Platform — Submission Checklist

This checklist summarizes the final implementation status and reviewer run instructions.

---

## 1. Acceptance Gate

## Docker Compose

Status:

```text
PASS
```

Command:

```bash
docker compose up --build
```

Expected services:

```text
store-api
store-dashboard
```

Expected URLs:

```text
http://localhost:8000/health
http://localhost:8501
```

Notes:

The API and dashboard are containerized. The CV pipeline is run locally as a host-side edge process.

---

## 2. Required Data Placement

Before running the full system, create:

```text
data/
```

Expected files:

```text
data/Brigade_Bangalore_10_April_26.csv
data/CAM_01.mp4
data/CAM_02.mp4
data/CAM_03.mp4
data/CAM_05.mp4
```

The POS CSV is mounted into the API container at:

```text
/app/data/Brigade_Bangalore_10_April_26.csv
```

---

## 3. Reviewer Run Commands

## Step 1: Start API and Dashboard

From project root:

```bash
docker compose up --build
```

Open:

```text
http://localhost:8000/health
http://localhost:8501
```

## Step 2: Run CV Pipeline

In a second terminal:

```bash
cd cv_pipeline
python orchestrator.py
```

## Step 3: Run Tests

From project root:

```bash
pytest
```

Expected result:

```text
8 passed
```

---

## 4. API Endpoints

## Health

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
latest event timestamp
feed freshness
warnings
```

---

## Event Ingestion

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
max 500 events
per-event validation
partial success handling
duplicate event idempotency
structured response counters
```

---

## Metrics

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

## Funnel

```text
GET /stores/{store_id}/funnel
```

Status:

```text
IMPLEMENTED
```

Returns:

```text
entered store
entered billing queue
completed purchase
queue abandonment count
queue abandonment rate
average queue wait
completed queue cycles
current queue depth
```

---

## Heatmap

```text
GET /stores/{store_id}/heatmap
```

Status:

```text
IMPLEMENTED
```

Returns:

```text
zone visit counts
average dwell by zone
heat score
data confidence
```

---

## Anomalies

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

## 5. Dashboard

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

---

## 6. Computer Vision Pipeline

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
IMPLEMENTED
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
batched API emission
```

Known issue:

```text
Processing may be slow on CPU because YOLO inference runs frame by frame.
```

Current decision:

```text
Keep as-is for submission stability.
```

---

## 7. Event Schema

Schema version:

```text
Event Schema v1.2
```

Status:

```text
IMPLEMENTED
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
REENTRY
BILLING_QUEUE_ABANDON
```

Important limitation:

```text
REENTRY is schema-supported but not emitted.
BILLING_QUEUE_ABANDON is calculated as an aggregate, not emitted as a CV event.
```

---

## 8. Database

Database:

```text
SQLite
```

ORM:

```text
SQLAlchemy
```

Status:

```text
IMPLEMENTED
```

Tables:

```text
events
sessions
pos_transactions
```

Implemented persistence:

```text
full Event Schema v1.2 fields
visitor session state
POS transactions
POS claim status
```

Known limitation:

```text
SQLite is not ideal for production multi-camera write-heavy workloads.
```

Production recommendation:

```text
PostgreSQL + Alembic migrations
```

---

## 9. POS Correlation

Status:

```text
IMPLEMENTED
```

Rule:

```text
When BILLING_QUEUE_EXIT arrives, find an unclaimed POS transaction from the same store within the previous 5 minutes.
```

If matched:

```text
mark transaction as claimed
mark visitor session as converted
```

Known limitation:

```text
Reliability depends on visitor identity stability in the billing camera.
```

---

## 10. Queue Logic

Status:

```text
IMPLEMENTED
```

Queue events:

```text
BILLING_QUEUE_JOIN
BILLING_QUEUE_EXIT
```

Queue analytics source:

```text
event stream
```

Reason:

Raw billing queue events are more reliable for queue metrics than cross-camera session state because full Re-ID is not implemented.

---

## 11. Staff Exclusion

Status:

```text
IMPLEMENTED
```

Method:

```text
Behind-counter spatial heuristic
```

Rule:

```text
More than 30 consecutive frames inside BEHIND_COUNTER → is_staff=True
```

Known limitation:

```text
Roaming floor staff may not be excluded.
```

---

## 12. Re-ID and Re-entry

Global Re-ID:

```text
NOT IMPLEMENTED
```

REENTRY events:

```text
NOT EMITTED
```

Planned future design:

```text
OSNet / TorchReID embeddings
cosine similarity
global visitor ID pool
cross-camera identity stitching
```

Reason deferred:

```text
High dependency and implementation risk within challenge timeline.
```

---

## 13. Logging

Status:

```text
IMPLEMENTED
```

Structured request logging fields:

```text
trace_id
method
endpoint
status_code
latency_ms
store_id
client_host
```

Ingestion batch logging fields:

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

## 14. Automated Tests

Status:

```text
IMPLEMENTED
```

Test framework:

```text
pytest
```

Run:

```bash
pytest
```

Current result:

```text
8 passed
```

Test files:

```text
tests/test_health.py
tests/test_ingest.py
tests/test_metrics.py
tests/test_funnel.py
tests/test_heatmap.py
tests/test_anomalies.py
```

Coverage focus:

```text
API health
valid event ingestion
duplicate idempotency
malformed event partial success
empty metrics
empty funnel
empty heatmap
empty anomalies
```

Known limitation:

```text
No automated YOLO/ByteTrack video tests.
```

Reason:

CV output depends on video data, model behavior, and local hardware.

---

## 15. Documentation

Status:

```text
IMPLEMENTED
```

Docs included:

```text
README.md
DESIGN.md
CHOICES.md
SUBMISSION_CHECKLIST.md
```

Docs honestly describe:

```text
implemented features
known limitations
reviewer commands
architecture decisions
testing status
deployment trade-offs
```

---

## 16. Final Feature Status

| Feature | Status |
|---|---|
| Dockerized API | Implemented |
| Dockerized dashboard | Implemented |
| Host-side CV worker | Implemented |
| YOLOv8n detection | Implemented |
| ByteTrack tracking | Implemented |
| Polygon zones | Implemented |
| Staff exclusion | Implemented |
| Event Schema v1.2 | Implemented |
| Full event persistence | Implemented |
| Robust ingestion | Implemented |
| POS correlation | Implemented |
| Metrics endpoint | Implemented |
| Funnel endpoint | Implemented |
| Heatmap endpoint | Implemented |
| Anomalies endpoint | Implemented |
| Health endpoint | Implemented |
| Structured logging | Implemented |
| Dashboard upgrade | Implemented |
| Pytest suite | Implemented |
| Cross-camera Re-ID | Not implemented |
| REENTRY emission | Not implemented |
| Fully Dockerized CV | Not implemented |

---

## 17. Known Limitations

1. CV pipeline runs locally outside Docker.
2. Cross-camera Re-ID is not implemented.
3. ByteTrack IDs are camera-local.
4. `REENTRY` events are not emitted.
5. `BILLING_QUEUE_ABANDON` is aggregate-derived, not emitted.
6. Camera polygons are manually calibrated and hardcoded.
7. SQLite is used instead of PostgreSQL.
8. CV processing may be slow on CPU.
9. Dashboard uses polling.
10. Roaming staff may be counted as customers.

---

## 18. Final Submission Confidence

Current readiness:

```text
READY FOR SUBMISSION WITH DOCUMENTED LIMITATIONS
```

Strong points:

```text
API works
Docker works
Dashboard works
Tests pass
Endpoints are complete
Structured logging exists
Documentation is honest
```

Main weakness:

```text
No global cross-camera Re-ID
CV worker outside Docker
```

These limitations are explicitly documented and defensible as challenge-time trade-offs.