# Retail Store Intelligence Platform

A computer-vision-powered retail analytics system that converts CCTV-style store activity and POS transaction data into structured retail intelligence.

The system detects shopper activity, maps movement into store zones, emits structured events, ingests them through a FastAPI backend, stores them in SQLite, correlates billing activity with POS transactions, and displays business metrics through a Streamlit dashboard.

---

## 1. What This Project Does

The platform estimates and exposes:

* total visitors
* product-zone visits
* billing queue participation
* completed purchases
* conversion rate
* queue abandonment
* current queue depth
* average queue wait time
* average dwell time by product zone
* zone-level heatmap scores
* operational anomalies
* API health and stale-feed status

---

## 2. Architecture Summary

```text
CCTV videos / sample event payloads
        ↓
CV edge pipeline or event replay
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

The project uses an edge-cloud split:

```text
Cloud layer: API + Dashboard inside Docker
Edge layer: CV pipeline runs locally on the host machine
```

This split avoids PyTorch/OpenCV/Ultralytics Docker compatibility issues while keeping the API and dashboard easy to run.

---

## 3. Repository Structure

```text
retail-store-intelligence/
├── api/
│   ├── Dockerfile
│   ├── database.py
│   ├── main.py
│   ├── models.py
│   ├── seed_data.py
│   └── requirements.txt
│
├── cv_pipeline/
│   ├── detector.py
│   ├── event_emitter.py
│   ├── orchestrator.py
│   ├── tracker_state.py
│   ├── zone_mapper.py
│   └── requirements.txt
│
├── dashboard/
│   ├── Dockerfile
│   ├── app.py
│   └── requirements.txt
│
├── tests/
│   ├── conftest.py
│   ├── test_acceptance_gate.py
│   ├── test_anomalies.py
│   ├── test_anomaly_rules.py
│   ├── test_funnel.py
│   ├── test_funnel_session_logic.py
│   ├── test_health.py
│   ├── test_heatmap.py
│   ├── test_heatmap_populated.py
│   ├── test_ingest.py
│   ├── test_metrics.py
│   ├── test_sample_events_ingest.py
│   ├── test_seed_data.py
│   └── test_staff_filtering.py
│
├── data/
│   ├── README.md
│   ├── .gitkeep
│   ├── Brigade_Bangalore_10_April_26.csv
│   │
│   ├── ST1008/
│   │   ├── Store_1_layout.png
│   │   ├── CAM_1_ZONE.mp4
│   │   ├── CAM_2_ZONE.mp4
│   │   ├── CAM_3_ENTRY.mp4
│   │   └── CAM_5_BILLING.mp4
│   │
│   └── STORE_2/
│       ├── Store_2_layout.png
│       ├── ENTRY_1.mp4
│       ├── ENTRY_2.mp4
│       ├── BILLING_AREA.mp4
│       └── ZONE.mp4
│
├── docker-compose.yml
├── pytest.ini
├── README.md
├── DESIGN.md
├── CHOICES.md
└── SUBMISSION_CHECKLIST.md
```

Important:

Challenge datasets, CCTV videos, POS CSV files, layout images, generated databases, and model weights are not committed to GitHub.

Only placeholders such as `data/.gitkeep` and `data/README.md` should be committed.

---

## 4. Required Local Data Placement

Create a `data/` folder at the project root and place the challenge-provided files locally.

Final expected local structure:

```text
data/
├── Brigade_Bangalore_10_April_26.csv
│
├── ST1008/
│   ├── Store_1_layout.png
│   ├── CAM_1_ZONE.mp4
│   ├── CAM_2_ZONE.mp4
│   ├── CAM_3_ENTRY.mp4
│   └── CAM_5_BILLING.mp4
│
└── STORE_2/
    ├── Store_2_layout.png
    ├── ENTRY_1.mp4
    ├── ENTRY_2.mp4
    ├── BILLING_AREA.mp4
    └── ZONE.mp4
```

Confirmed store mapping:

```text
Store 1 = ST1008
Store 2 = STORE_2
```

Reason:

The POS sample transaction file confirms Store 1 as `ST1008`. Store 2 has no confirmed POS store ID, so it is handled internally as `STORE_2`.

Important POS rule:

```text
CV event store_id must match POS CSV store_id.
```

For Store 1:

```text
CV store_id = ST1008
POS store_id = ST1008
```

For Store 2:

```text
CV store_id = STORE_2
```

If no POS file exists for `STORE_2`, Store 2 conversion rate will remain `0.0%`. This is expected and documented.

---

## 5. Quick Start

### Step 1 — Start API and Dashboard

From the project root:

```bash
docker compose up --build
```

Open:

```text
http://localhost:8000/health
http://localhost:8501
```

### Step 2 — Run the CV Pipeline

In a second terminal:

```bash
cd cv_pipeline
python orchestrator.py
```

To run only one store:

### Windows PowerShell

```powershell
$env:ONLY_STORE="STORE_2"
python orchestrator.py
```

To clear the single-store setting:

```powershell
Remove-Item Env:\ONLY_STORE
```

### macOS / Linux

```bash
ONLY_STORE=STORE_2 python orchestrator.py
```

### Step 3 — Run Tests

From the project root:

```bash
pytest
```

Expected result:

```text
32 passed
```

If dashboard contract tests are added, the expected count may increase.

---

## 6. Local CV Environment Setup

The CV pipeline runs outside Docker.

### Windows PowerShell

```powershell
python -m venv venv
.\venv\Scripts\activate
pip install -r cv_pipeline/requirements.txt
cd cv_pipeline
python orchestrator.py
```

### macOS / Linux

```bash
python -m venv venv
source venv/bin/activate
pip install -r cv_pipeline/requirements.txt
cd cv_pipeline
python orchestrator.py
```

Optional speed setting:

```powershell
$env:FRAME_SKIP="5"
python orchestrator.py
```

This processes fewer frames and is useful for quicker local validation.

---

## 7. Docker Services

### `store-api`

FastAPI backend.

URL:

```text
http://localhost:8000
```

Responsibilities:

* event ingestion
* event normalization
* event validation
* duplicate idempotency
* partial-success handling
* event persistence
* POS seeding
* POS correlation
* metrics
* funnel
* heatmap
* anomalies
* health monitoring
* structured logging

### `store-dashboard`

Streamlit dashboard.

URL:

```text
http://localhost:8501
```

Dashboard panels:

* store selector
* system health
* North Star KPIs
* queue/event KPIs
* four-stage shopper funnel
* queue insights
* active anomalies
* zone heatmap
* average product-zone dwell

---

## 8. API Endpoints

### Health

```http
GET /health
```

Returns API status, database status, latest event timestamp by store, and stale-feed warnings.

---

### Event Ingestion

```http
POST /events/ingest
```

Accepts up to 500 events per request.

Supports:

```text
canonical Event Schema v1.2
sample_events.jsonl-style challenge payloads
```

Example canonical payload:

```json
{
  "events": [
    {
      "event_id": "11111111-1111-4111-8111-111111111111",
      "store_id": "ST1008",
      "camera_id": "CAM_ENTRANCE",
      "visitor_id": "VIS_001",
      "timestamp": "2026-04-10T10:00:00Z",
      "event_type": "ENTRY",
      "zone_id": null,
      "dwell_ms": null,
      "is_staff": false,
      "confidence": 0.95,
      "metadata": {
        "queue_depth": null,
        "sku_zone": null,
        "session_seq": 1
      }
    }
  ]
}
```

Response:

```json
{
  "status": "success",
  "received_count": 1,
  "processed_count": 1,
  "duplicate_count": 0,
  "error_count": 0,
  "errors": null
}
```

---

### Metrics

```http
GET /stores/{store_id}/metrics
```

Example:

```text
GET /stores/ST1008/metrics
GET /stores/STORE_2/metrics
GET /stores/STORE_BLR_002/metrics
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

Unknown or empty stores return safe zero-state JSON.

---

### Funnel

```http
GET /stores/{store_id}/funnel
```

Challenge-aligned funnel:

```text
Entered Store
Visited Product Zone
Entered Billing Queue
Completed Purchase
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

Queue insight fields include:

```text
queue_abandonment_count
queue_abandonment_rate
avg_queue_wait_ms
completed_queue_cycles
abandoned_queue_cycles
current_queue_depth
queue_data_source
```

---

### Heatmap

```http
GET /stores/{store_id}/heatmap
```

Returns zone-level engagement:

```text
zone_id
visit_count
avg_dwell_ms
heat_score
data_confidence
```

---

### Anomalies

```http
GET /stores/{store_id}/anomalies
```

Implemented anomaly types:

```text
BILLING_QUEUE_SPIKE
CONVERSION_DROP
DEAD_ZONE
STALE_FEED
```

---

## 9. Event Schema v1.2

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

## 10. Sample Event Compatibility

The ingestion API includes a normalization adapter.

It maps challenge-style sample fields into the internal schema:

```text
id_token → visitor_id
track_id → visitor_id
store_code → store_id
event_timestamp → timestamp
event_time → timestamp
queue_exit_ts → timestamp
queue_served_ts → timestamp
queue_join_ts → timestamp
zone_entered → ZONE_ENTER
zone_exited → ZONE_EXIT
queue_completed → BILLING_QUEUE_EXIT
queue_abandoned → BILLING_QUEUE_ABANDON
queue_position_at_join → metadata.queue_depth
zone_name → metadata.sku_zone
```

This allows the API to accept both canonical internal events and uploaded sample-event style payloads.

---

## 11. POS Data Compatibility

The POS seeder supports two schemas.

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
total_amount
```

The parser:

```text
skips malformed rows
deduplicates transaction IDs
allows zero-value transactions
returns a safe summary if the file is missing
```

---

## 12. Camera Mapping

Current CV camera mapping is defined in:

```text
cv_pipeline/orchestrator.py
```

### ST1008

```text
CAM_1_ZONE      → data/ST1008/CAM_1_ZONE.mp4      → SKINCARE
CAM_2_ZONE      → data/ST1008/CAM_2_ZONE.mp4      → MAKEUP
CAM_3_ENTRY     → data/ST1008/CAM_3_ENTRY.mp4     → ENTRY_DOOR
CAM_5_BILLING   → data/ST1008/CAM_5_BILLING.mp4   → BILLING_QUEUE / BEHIND_COUNTER
```

### STORE_2

```text
ENTRY_1         → data/STORE_2/ENTRY_1.mp4        → ENTRY_DOOR
BILLING_AREA    → data/STORE_2/BILLING_AREA.mp4   → BILLING_QUEUE / BEHIND_COUNTER
ZONE            → data/STORE_2/ZONE.mp4           → PRODUCT_ZONE
```

`STORE_2/ENTRY_2.mp4` is intentionally not used in the final baseline to reduce double-counting. It can be re-enabled only if it is confirmed to cover a different non-overlapping door.

---

## 13. Zone Mapping

Zone mapping is polygon-based.

Helper tool:

```text
cv_pipeline/zone_mapper.py
```

It allows manual clicking of polygon points on the first frame of a video and prints OpenCV-compatible `np.array(...)` coordinates.

Known limitation:

```text
If a camera angle changes, polygons must be recalibrated.
```

---

## 14. Staff Exclusion

Implemented strategy:

```text
behind-counter spatial heuristic
```

Rule:

```text
If a person stays inside the BEHIND_COUNTER polygon for more than 30 consecutive frames,
mark that visitor as staff.
```

Staff is excluded from:

```text
metrics
funnel
queue analytics
heatmap
```

Known limitation:

```text
Roaming floor staff may still be counted as customers.
```

---

## 15. Queue Logic

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

Queue analytics are derived from the raw event stream, which is more reliable than global session state because full cross-camera Re-ID is not implemented.

---

## 16. Testing

Run:

```bash
pytest
```

Expected result:

```text
32 passed
```

Test coverage includes:

```text
health endpoint
valid event ingestion
duplicate idempotency
partial-success ingestion
sample-event normalization
acceptance-gate store safety
POS schema variants
session-based funnel
populated heatmap
anomaly rules
staff filtering
```

The CV model pipeline is not unit-tested because YOLO/ByteTrack output depends on local video files, model behavior, and hardware.

---

## 17. Structured Logging

Every API request logs JSON-style structured fields:

```text
trace_id
method
endpoint
status_code
latency_ms
store_id
client_host
```

Every ingestion batch additionally logs:

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

## 18. AI-Assisted Engineering

AI assistance was used for:

```text
architecture review
risk prioritization
event schema compatibility planning
test expansion planning
documentation review
```

Important decisions documented in `DESIGN.md` and `CHOICES.md`:

```text
event normalization adapter accepted
event-derived queue analytics accepted
four-stage funnel accepted
full Re-ID deferred
full CV Dockerization deferred
```

---

## 19. Known Limitations

1. Full cross-camera Re-ID is not implemented.
2. ByteTrack IDs are camera-local.
3. CV pipeline runs locally outside Docker.
4. Camera polygons are manually calibrated and hardcoded.
5. `REENTRY` is schema-supported but not robustly emitted by CV.
6. `ZONE_DWELL` cadence may not fully satisfy every-30-second production behavior.
7. SQLite is used instead of PostgreSQL.
8. Dashboard uses polling, not WebSockets.
9. Roaming staff may still be counted as customers.
10. CV processing may be slow on CPU.
11. Store 2 conversion remains zero unless POS data for `STORE_2` is provided.

---

## 20. Production Improvements

Recommended next steps for production:

```text
PostgreSQL migration
Alembic migrations
global Re-ID service
camera configuration API
persistent edge event buffer
optional CV Docker profile
concurrent multi-camera processing
WebSocket/SSE dashboard updates
OpenTelemetry tracing
CV state-machine tests
```

---

## 21. Final Submission Status

Current status:

```text
READY FOR SUBMISSION WITH DOCUMENTED LIMITATIONS
```

Strong points:

```text
Dockerized API and dashboard
robust event ingestion
sample event compatibility
dual POS parser
session-based funnel
heatmap endpoint
anomaly endpoint
structured logging
expanded pytest suite
reviewer-friendly documentation
```

Main limitations:

```text
no full cross-camera Re-ID
CV worker outside Docker
manual polygon calibration
SQLite used for challenge deployment
```
