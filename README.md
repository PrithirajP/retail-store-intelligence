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
YOLOv8n person detection
        ↓
ByteTrack local tracking
        ↓
Directional line-crossing + zone-state logic
        ↓
Lightweight REENTRY matching
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

The project uses an edge-cloud style architecture:

```text
Default cloud layer: API + Dashboard inside Docker
Edge layer: CV pipeline running locally or through optional Docker profile
```

The default Docker path is lightweight and starts the API and dashboard. The CV worker can be run locally or through the optional Docker Compose `cv` profile.

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
│   ├── Dockerfile
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
│   ├── test_compose_cv_profile.py
│   ├── test_dashboard_contract.py
│   ├── test_database_failure.py
│   ├── test_funnel.py
│   ├── test_funnel_session_logic.py
│   ├── test_health.py
│   ├── test_heatmap.py
│   ├── test_heatmap_populated.py
│   ├── test_ingest.py
│   ├── test_metrics.py
│   ├── test_reentry_funnel.py
│   ├── test_reentry_tracking.py
│   ├── test_sample_events_ingest.py
│   ├── test_seed_data.py
│   ├── test_staff_filtering.py
│   └── test_tracker_line_crossing.py
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

### Step 2 — Run the CV Pipeline Locally

In a second terminal:

```bash
cd cv_pipeline
python orchestrator.py
```

To run only one store:

#### Windows PowerShell

```powershell
$env:ONLY_STORE="STORE_2"
python orchestrator.py
```

To clear the single-store setting:

```powershell
Remove-Item Env:\ONLY_STORE
```

#### macOS / Linux

```bash
ONLY_STORE=STORE_2 python orchestrator.py
```

### Step 3 — Run Tests

From the project root:

```bash
pytest
```

Expected result after the final milestones:

```text
all tests passed
```

The current test suite covers ingestion, idempotency, sample-event normalization, metrics, funnel, heatmap, anomalies, staff filtering, dashboard contract, database failure handling, line crossing, and re-entry logic.

---

## 6. Local CV Environment Setup

The CV pipeline can run outside Docker.

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

## 7. Optional CV Docker Profile

By default, Docker Compose starts only the API and dashboard:

```bash
docker compose up --build
```

The CV pipeline can also be run through an optional Docker Compose profile:

```bash
docker compose --profile cv up --build
```

The optional CV worker service runs:

```bash
python orchestrator.py
```

inside the `cv_pipeline` container and sends events to:

```text
http://store-api:8000/events/ingest
```

The local `data/` folder is mounted into the container at:

```text
/app/data
```

Useful environment variables:

```bash
FRAME_SKIP=5
ONLY_STORE=STORE_2
DEBUG_EVENTS=1
EVENT_BATCH_SIZE=50
```

Example:

```bash
ONLY_STORE=STORE_2 FRAME_SKIP=5 docker compose --profile cv up --build
```

The host-side CV run remains fully supported and is still the recommended lightweight path for local validation:

```bash
cd cv_pipeline
python orchestrator.py
```

The Docker CV profile is optional because PyTorch, OpenCV, and Ultralytics can be heavier than the API/dashboard services.

---

## 8. Docker Services

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
* graceful database failure responses

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

### `cv-worker`

Optional Docker Compose profile service.

Run with:

```bash
docker compose --profile cv up --build
```

Responsibilities:

* run YOLOv8n person detection
* run ByteTrack local tracking
* perform zone and line-crossing logic
* emit structured events
* stream events to the API

---

## 9. API Endpoints

### Health

```http
GET /health
```

Returns API status, database status, latest event timestamp by store, feed freshness, and warnings.

If the database is unavailable, the endpoint returns a structured degraded response with HTTP 503.

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
queue_abandonment_count
queue_abandonment_rate
completed_queue_cycles
abandoned_queue_cycles
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

The heatmap excludes operational zones such as:

```text
ENTRY_DOOR
BILLING_QUEUE
BEHIND_COUNTER
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

## 10. Event Schema v1.2

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

The CV tracker may emit intermediate `LINE_CROSS` events. The orchestrator normalizes:

```text
LINE_CROSS + IN  → ENTRY
LINE_CROSS + OUT → EXIT
```

---

## 11. Sample Event Compatibility

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

## 12. POS Data Compatibility

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

## 13. Camera Mapping

Current CV camera mapping is defined in:

```text
cv_pipeline/orchestrator.py
```

### ST1008

```text
CAM_1_ZONE      → data/ST1008/CAM_1_ZONE.mp4      → SKINCARE
CAM_2_ZONE      → data/ST1008/CAM_2_ZONE.mp4      → MAKEUP
CAM_3_ENTRY     → data/ST1008/CAM_3_ENTRY.mp4     → ENTRY_DOOR / entrance line
CAM_5_BILLING   → data/ST1008/CAM_5_BILLING.mp4   → BILLING_QUEUE / BEHIND_COUNTER
```

### STORE_2

```text
ENTRY_1         → data/STORE_2/ENTRY_1.mp4        → ENTRY_DOOR / entrance line
BILLING_AREA    → data/STORE_2/BILLING_AREA.mp4   → BILLING_QUEUE / BEHIND_COUNTER
ZONE            → data/STORE_2/ZONE.mp4           → PRODUCT_ZONE
```

`STORE_2/ENTRY_2.mp4` is intentionally not used in the final baseline to reduce double-counting. It can be re-enabled only if it is confirmed to cover a different non-overlapping door.

---

## 14. Entry, Exit, and Re-entry Logic

The CV tracker stores the previous and current bottom-center foot point for each local track.

For configured entrance cameras, the tracker checks whether the motion crosses the entrance line.

It emits:

```text
LINE_CROSS + direction=IN
LINE_CROSS + direction=OUT
```

The orchestrator normalizes these into:

```text
ENTRY
EXIT
```

For re-entry support, the tracker stores recent exits for a short time window. If a new local track crosses inward near a recent exit location, the tracker emits:

```text
REENTRY
```

and maps the new local track back to the earlier visitor ID.

This reduces double-counting for shoppers who leave and re-enter through the same configured entrance.

---

## 15. Zone Mapping

Zone mapping is polygon-based.

Helper tool:

```text
cv_pipeline/zone_mapper.py
```

It allows manual clicking of polygon points on the first frame of a video and prints OpenCV-compatible `np.array(...)` coordinates.

Known limitation:

```text
If a camera angle changes, polygons and entrance lines must be recalibrated.
```

---

## 16. Staff Exclusion

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

## 17. Queue Logic

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

Queue analytics are derived from the raw event stream, which is more reliable than depending entirely on global cross-camera identity.

---

## 18. Testing

Run:

```bash
pytest
```

Test coverage includes:

```text
health endpoint
database failure degradation
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
dashboard contract
directional line crossing
lightweight REENTRY matching
CV Docker profile contract
```

The CV model output itself is not fully unit-tested because YOLO/ByteTrack behavior depends on local video files, model versions, and hardware.

---

## 19. Event Log JSONL Deliverable

The repository includes the required challenge event log file:

```text
event_log.jsonl
```

This file is generated after running the CV pipeline and exporting the events accepted by the API. It follows JSONL format, where each line is one valid JSON object and there is no surrounding list.

The event log contains structured events such as:

```text
ENTRY
EXIT
REENTRY
ZONE_ENTER
ZONE_EXIT
ZONE_DWELL
BILLING_QUEUE_JOIN
BILLING_QUEUE_EXIT
BILLING_QUEUE_ABANDON
```

Each event contains:

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
metadata
```

The `metadata` object contains:

```text
queue_depth
sku_zone
session_seq
```

### Generate the event log

After starting the API and running the CV pipeline, copy the Docker API database to the host:

```powershell
docker cp store-api:/app/store_intelligence.db .\store_intelligence_from_docker.db
```

Then run:

```powershell
python export_event_log.py
```

This generates:

```text
event_log.jsonl
```

### Validate the event log

Run:

```powershell
python validate_event_log.py
```

Expected output:

```text
Valid JSONL file. Total events: <number greater than 0>
```

The submitted `event_log.jsonl` must be non-empty.

### Repository rule

The required `event_log.jsonl` file is included in the repository because the organizer identified it as a mandatory deliverable and no separate upload field was provided.

The following generated or challenge data files are still excluded from GitHub:

```text
CCTV videos
POS CSV files
SQLite database files
model weights
layout images
```


## 20. Structured Logging

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

## 21. AI-Assisted Engineering

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
directional line crossing accepted
lightweight REENTRY matching accepted
optional CV Docker profile accepted
full appearance-based cross-camera Re-ID deferred
```

---

## 22. Known Limitations

1. Full appearance-based cross-camera Re-ID is not implemented. The system now includes lightweight distance-based REENTRY matching at configured entrance cameras, but it does not compare person appearance embeddings across all cameras.

2. Directional entry/exit detection depends on correctly calibrated entrance lines, camera angle, detection quality, and crowding near the doorway.

3. The optional CV Docker profile may require more Docker disk, memory, and build time than the default API/dashboard services because of PyTorch, OpenCV, and Ultralytics dependencies.

4. Camera polygons are manually calibrated and must be updated if camera angles change.

5. SQLite is used for challenge deployment. Production should use PostgreSQL with migrations.

6. Dashboard refresh uses polling rather than WebSockets.

7. Roaming staff outside the behind-counter zone may still be counted as customers.

8. Store 2 conversion remains zero unless POS transactions for `STORE_2` are provided.

---

## 23. Production Improvements

Recommended next steps for production:

```text
full appearance-based cross-camera Re-ID
OSNet/TorchReID-style embedding service
global identity stitching across cameras
PostgreSQL migration
Alembic migrations
camera configuration API
persistent edge event buffer
concurrent multi-camera processing
WebSocket/SSE dashboard updates
OpenTelemetry tracing
CV model regression tests
```

---

## 24. Final Submission Status

Current status:

```text
READY FOR SUBMISSION WITH DOCUMENTED PRODUCTION LIMITATIONS
```

Strong points:

```text
Dockerized API and dashboard
optional Docker CV worker profile
host-side CV edge pipeline
YOLOv8n + ByteTrack detection/tracking
directional entry/exit line crossing
lightweight REENTRY matching
robust event ingestion
sample event compatibility
dual POS parser
session-based funnel
queue abandonment metrics
heatmap endpoint
anomaly endpoint
structured logging
expanded pytest suite
reviewer-friendly documentation
```

Main production limitations:

```text
no full appearance-based cross-camera Re-ID
manual polygon and entrance-line calibration
SQLite used for challenge deployment
polling dashboard instead of WebSockets
```
