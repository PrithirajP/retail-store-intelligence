# Retail Store Intelligence Platform

A computer-vision-powered Store Intelligence Platform that converts CCTV video streams into structured retail analytics.

The system detects and tracks people in store camera feeds, maps their movement to store zones, emits structured events, ingests those events through a FastAPI backend, stores them in SQLite, correlates billing-zone activity with POS transactions, and displays live metrics through a Streamlit dashboard.

---

## 1. Project Overview

This project is built for a retail analytics challenge where the goal is to estimate and expose store-level intelligence such as:

* Total unique visitors
* Conversion rate
* Billing queue participation
* Queue abandonment
* Average queue wait time
* Zone dwell analytics
* Zone heatmap scores
* Operational anomalies
* API health and stale-feed status

The system follows an edge-cloud architecture:

```text
CCTV Videos
   ↓
YOLOv8n + ByteTrack CV Pipeline
   ↓
Zone / Queue / Staff State Machine
   ↓
Structured Event Payloads
   ↓
FastAPI Ingestion API
   ↓
SQLite Database
   ↓
Metrics / Funnel / Heatmap / Anomalies APIs
   ↓
Streamlit Dashboard
```

---

## 2. Current Architecture

The project has two main runtime layers.

### 2.1 Cloud Layer

The cloud layer is containerized using Docker Compose.

It contains:

```text
store-api        FastAPI backend
store-dashboard  Streamlit dashboard
```

The FastAPI service handles:

* Event ingestion
* Event validation
* Idempotent event persistence
* Visitor session materialization
* POS transaction seeding
* POS correlation
* Metrics calculation
* Funnel calculation
* Heatmap calculation
* Rule-based anomaly detection
* Health and feed freshness reporting

The dashboard polls the API and displays live metrics.

### 2.2 Edge Layer

The CV pipeline currently runs on the host machine:

```bash
cd cv_pipeline
python orchestrator.py
```

This was a deliberate engineering trade-off to avoid PyTorch/OpenCV/Docker GPU compatibility failures during review. The API and dashboard are fully containerized; the CV worker is run locally as an edge process.

---

## 3. Repository Structure

```text
retail-store-intelligence/
├── api/
│   ├── Dockerfile
│   ├── database.py
│   ├── main.py
│   ├── models.py
│   ├── requirements.txt
│   └── seed_data.py
│
├── cv_pipeline/
│   ├── detector.py
│   ├── event_emitter.py
│   ├── orchestrator.py
│   ├── requirements.txt
│   ├── tracker_state.py
│   └── zone_mapper.py
│
├── dashboard/
│   ├── Dockerfile
│   ├── app.py
│   └── requirements.txt
│
├── tests/
│   ├── conftest.py
│   ├── test_anomalies.py
│   ├── test_funnel.py
│   ├── test_health.py
│   ├── test_heatmap.py
│   ├── test_ingest.py
│   └── test_metrics.py
│
├── data/
│   ├── Brigade_Bangalore_10_April_26.csv
│   ├── CAM_01.mp4
│   ├── CAM_02.mp4
│   ├── CAM_03.mp4
│   └── CAM_05.mp4
│
├── docker-compose.yml
├── pytest.ini
├── README.md
├── DESIGN.md
├── CHOICES.md
└── SUBMISSION_CHECKLIST.md
```

---

## 4. Required Data Placement

Before running the project, create a `data/` folder at the project root and place the required dataset files inside it.

Expected structure:

```text
retail-store-intelligence/
└── data/
    ├── Brigade_Bangalore_10_April_26.csv
    ├── CAM_01.mp4
    ├── CAM_02.mp4
    ├── CAM_03.mp4
    └── CAM_05.mp4
```

The POS transaction file must be named exactly:

```text
Brigade_Bangalore_10_April_26.csv
```

The API container mounts the local `data/` folder into:

```text
/app/data
```

and seeds POS transactions from:

```text
/app/data/Brigade_Bangalore_10_April_26.csv
```

---

## 5. Camera File Mapping

The CV orchestrator currently uses the following hardcoded video mapping:

```text
CAM_ENTRANCE  -> ../data/CAM_03.mp4
CAM_BILLING   -> ../data/CAM_05.mp4
CAM_MAKEUP    -> ../data/CAM_02.mp4
CAM_SKINCARE  -> ../data/CAM_01.mp4
```

This mapping is defined in:

```text
cv_pipeline/orchestrator.py
```

Important: because the paths use `../data/...`, run the CV pipeline from inside the `cv_pipeline/` folder:

```bash
cd cv_pipeline
python orchestrator.py
```

---

## 6. Quickstart

### Step 1: Start Docker Desktop

Make sure Docker Desktop is running and using Linux containers.

Check Docker with:

```bash
docker ps
```

If this command fails, start Docker Desktop first.

---

### Step 2: Start API and Dashboard

From the project root:

```bash
docker compose up --build
```

This starts:

```text
FastAPI API      http://localhost:8000
Streamlit UI     http://localhost:8501
```

The dashboard will start after the API healthcheck passes.

---

### Step 3: Verify API Health

Open:

```text
http://localhost:8000/health
```

Before CV events are ingested, expected response will be similar to:

```json
{
  "status": "healthy",
  "database": {
    "status": "connected"
  },
  "stores": {},
  "warnings": [
    "NO_EVENTS_RECEIVED"
  ]
}
```

---

### Step 4: Open Dashboard

Open:

```text
http://localhost:8501
```

Initially, the dashboard may show zero visitors and zero conversions. This is expected before the CV pipeline sends events.

---

### Step 5: Run CV Pipeline

Open a second terminal.

From the project root:

```bash
cd cv_pipeline
python orchestrator.py
```

Expected behavior:

```text
YOLOv8 model loads
camera videos are processed sequentially
zone events are generated
event batches are posted to FastAPI
dashboard metrics begin updating
```

---

## 7. Installing CV Dependencies Locally

The CV pipeline runs outside Docker.

Create and activate a virtual environment:

### Windows PowerShell

```powershell
python -m venv venv
.\venv\Scripts\activate
pip install -r cv_pipeline/requirements.txt
```

### macOS / Linux

```bash
python -m venv venv
source venv/bin/activate
pip install -r cv_pipeline/requirements.txt
```

Then run:

```bash
cd cv_pipeline
python orchestrator.py
```

---

## 8. Docker Services

The project uses Docker Compose for the API and dashboard.

### `store-api`

FastAPI backend.

Exposes:

```text
localhost:8000
```

Responsibilities:

* Receives CV events
* Validates event schema
* Stores event records
* Updates visitor sessions
* Seeds POS transaction data
* Correlates billing exits with POS transactions
* Provides analytics endpoints

### `store-dashboard`

Streamlit frontend.

Exposes:

```text
localhost:8501
```

Responsibilities:

* Polls API every few seconds
* Displays KPIs
* Displays conversion funnel
* Displays queue abandonment insights

---

## 9. API Endpoints

### 9.1 Health

```http
GET /health
```

Returns:

* API status
* Database connectivity
* Latest event timestamp per store
* Feed freshness status
* Stale-feed warnings

Example:

```json
{
  "status": "healthy",
  "database": {
    "status": "connected"
  },
  "stores": {
    "ST1008": {
      "last_event_timestamp": "2026-04-10T10:05:00+00:00",
      "feed_status": "OK",
      "warnings": []
    }
  },
  "warnings": []
}
```

---

### 9.2 Event Ingestion

```http
POST /events/ingest
```

Accepts a batch of up to 500 events.

Payload shape:

```json
{
  "events": [
    {
      "event_id": "11111111-1111-4111-8111-111111111111",
      "store_id": "ST1008",
      "camera_id": "CAM_ENTRANCE",
      "visitor_id": "VIS_1",
      "timestamp": "2026-04-10T10:00:00Z",
      "event_type": "ENTRY",
      "zone_id": null,
      "dwell_ms": null,
      "is_staff": false,
      "confidence": 0.92,
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

The endpoint validates events individually. If one event in a batch is malformed, valid events are still processed and the response becomes `partial_success`.

---

### 9.3 Store Metrics

```http
GET /stores/{store_id}/metrics
```

Example:

```text
GET /stores/ST1008/metrics
```

Returns:

```json
{
  "store_id": "ST1008",
  "total_visitors": 14,
  "converted_visitors": 3,
  "conversion_rate_percentage": 21.43,
  "current_queue_depth": 1,
  "avg_queue_wait_ms": 42000.0,
  "avg_dwell_ms_by_zone": {
    "MAKEUP": 7200.0,
    "SKINCARE": 6400.0
  },
  "total_events": 180,
  "last_event_timestamp": "2026-04-10T10:20:00+00:00"
}
```

---

### 9.4 Funnel

```http
GET /stores/{store_id}/funnel
```

Example:

```text
GET /stores/ST1008/funnel
```

Returns:

```json
{
  "store_id": "ST1008",
  "funnel_steps": {
    "1_entered_store": 14,
    "2_entered_billing_queue": 6,
    "3_completed_purchase": 3
  },
  "insights": {
    "queue_abandonment_count": 3,
    "queue_abandonment_rate": 50.0,
    "avg_queue_wait_ms": 38800.0,
    "completed_queue_cycles": 6,
    "current_queue_depth": 0,
    "queue_data_source": "event_stream"
  }
}
```

Queue analytics are derived from raw `BILLING_QUEUE_JOIN` and `BILLING_QUEUE_EXIT` events. This is intentional because full cross-camera Re-ID is not implemented yet.

---

### 9.5 Heatmap

```http
GET /stores/{store_id}/heatmap
```

Example:

```text
GET /stores/ST1008/heatmap
```

Returns:

```json
{
  "store_id": "ST1008",
  "heatmap_type": "zone_level",
  "data_confidence": "LOW",
  "zones": [
    {
      "zone_id": "MAKEUP",
      "visit_count": 4,
      "avg_dwell_ms": 6200.0,
      "heat_score": 85.0
    },
    {
      "zone_id": "SKINCARE",
      "visit_count": 2,
      "avg_dwell_ms": 4100.0,
      "heat_score": 45.3
    }
  ]
}
```

Heat score is normalized from 0 to 100 using visit count and average dwell time.

---

### 9.6 Anomalies

```http
GET /stores/{store_id}/anomalies
```

Example:

```text
GET /stores/ST1008/anomalies
```

Returns:

```json
{
  "store_id": "ST1008",
  "status": "WARN",
  "anomalies": [
    {
      "type": "BILLING_QUEUE_SPIKE",
      "severity": "WARN",
      "message": "Current billing queue depth is 5.",
      "suggested_action": "Open an additional billing counter or assign staff to checkout.",
      "evidence": {
        "current_queue_depth": 5,
        "warn_threshold": 5,
        "critical_threshold": 8
      }
    }
  ]
}
```

Implemented anomaly types:

```text
BILLING_QUEUE_SPIKE
CONVERSION_DROP
DEAD_ZONE
STALE_FEED
```

---

## 10. Event Schema Version

The project uses **Event Schema v1.2**.

It preserves the original flattened fields and adds nested metadata.

### Core Fields

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

### Metadata Fields

```text
metadata.queue_depth
metadata.sku_zone
metadata.session_seq
```

### Supported Event Types

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

Note: `REENTRY` and `BILLING_QUEUE_ABANDON` are supported by the API schema, but the current CV pipeline does not yet fully generate them.

---

## 11. Database Design

The backend uses SQLite through SQLAlchemy.

SQLite was chosen for challenge reliability because it requires:

```text
no external database container
no credentials
no network DB dependency
fast local startup
simple reviewer setup
```

### Tables

#### `events`

Raw event stream.

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

#### `sessions`

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

#### `pos_transactions`

Seeded from the POS CSV.

Stores:

```text
transaction_id
store_id
timestamp
basket_value_inr
claimed_by_visitor_id
```

---

## 12. POS Correlation Logic

When the API receives a `BILLING_QUEUE_EXIT` event, it tries to match that visitor with a POS transaction.

Rule:

```text
Find an unclaimed POS transaction from the same store where:
transaction timestamp is within 5 minutes before billing queue exit time
```

If found:

```text
pos_transactions.claimed_by_visitor_id = visitor_id
sessions.is_converted = True
```

This prevents the same receipt from being counted multiple times.

---

## 13. Staff Exclusion

The implemented staff exclusion strategy is spatial.

Rule:

```text
If a tracked person remains inside the BEHIND_COUNTER polygon for more than 30 consecutive frames,
mark that visitor as staff.
```

Staff events are excluded from customer analytics.

Known limitation:

```text
Roaming floor staff may still be counted as customers.
```

This is documented as a v1 limitation.

---

## 14. Zone Mapping

Zone mapping is based on manually calibrated polygons.

The helper utility:

```text
cv_pipeline/zone_mapper.py
```

allows a developer to click points on a video frame and generate OpenCV-compatible polygon arrays.

The final polygons are currently hardcoded into:

```text
cv_pipeline/orchestrator.py
```

Known limitation:

```text
If a camera moves, polygons must be recalibrated.
```

---

## 15. Dashboard

The dashboard is built with Streamlit.

Run through Docker Compose:

```text
http://localhost:8501
```

It displays:

```text
total visitors
converted visitors
conversion rate
shopper funnel
queue abandonment count
queue abandonment rate
```

The dashboard polls:

```text
GET /stores/ST1008/metrics
GET /stores/ST1008/funnel
```

The store ID is currently hardcoded as:

```text
ST1008
```

---

## 16. Structured Logging

The API includes structured JSON-style request logging.

Each request logs:

```text
trace_id
method
endpoint
status_code
latency_ms
store_id
client_host
```

For ingestion batches, the API also logs:

```text
received_count
processed_count
duplicate_count
error_count
status
```

Every API response includes:

```text
X-Trace-Id
```

---

## 17. Running Tests

The project includes a minimal API regression test suite using `pytest`.

From the project root, install the API test dependencies:

```bash
pip install -r api/requirements.txt
```

Then run:

```bash
pytest
```

Expected result:

```text
8 passed
```

The tests cover:

* API health endpoint
* valid event ingestion
* duplicate event idempotency
* partial-success behavior for malformed events
* empty-state metrics
* empty-state funnel
* empty-state heatmap
* empty-state anomalies

Each test file includes an AI prompt block and a human-change note, as expected by the challenge documentation.

### Test Scope and Limitations

The current test suite focuses on deterministic API and business-logic behavior. It does not test YOLOv8, ByteTrack, OpenCV video processing, or full multi-camera CV execution.

Those components are validated manually by running:

```bash
cd cv_pipeline
python orchestrator.py
```

This split is intentional: API regression tests provide fast, reliable validation, while CV model behavior depends on video files, local hardware, and non-deterministic tracking output.

---

## 18. Manual Validation Checklist

After setup, validate the system in this order.

### 18.1 Start cloud layer

```bash
docker compose up --build
```

Confirm:

```text
store-api starts
store-dashboard starts
API healthcheck passes
```

### 18.2 Check API endpoints

Open:

```text
http://localhost:8000/health
http://localhost:8000/stores/ST1008/metrics
http://localhost:8000/stores/ST1008/funnel
http://localhost:8000/stores/ST1008/heatmap
http://localhost:8000/stores/ST1008/anomalies
```

### 18.3 Open dashboard

Open:

```text
http://localhost:8501
```

### 18.4 Run CV pipeline

In another terminal:

```bash
cd cv_pipeline
python orchestrator.py
```

### 18.5 Watch dashboard update

Expected behavior:

```text
total events increase
visitor count increases
queue/funnel metrics update
dashboard refreshes automatically
```

---

## 19. Known Limitations

The current implementation is submission-focused and intentionally pragmatic.

Known limitations:

1. Full cross-camera Re-ID is not implemented.
2. OSNet/TorchReID is documented as a future improvement, not current code.
3. `REENTRY` is supported in the API schema but not fully emitted by the CV pipeline.
4. `BILLING_QUEUE_ABANDON` is computed as an aggregate, not emitted as a discrete CV event.
5. CV pipeline runs locally, outside default Docker Compose.
6. Camera polygons are manually calibrated and hardcoded.
7. Visitor IDs are ByteTrack-local, not globally stable across cameras.
8. SQLite is used for challenge simplicity; PostgreSQL is recommended for production.
9. Dashboard uses polling rather than WebSockets.
10. CV tests are manual rather than automated.

---

## 20. Production Improvements

For production deployment, the next improvements would be:

```text
Migrate SQLite to PostgreSQL
Add Alembic migrations
Add full Re-ID service using OSNet or similar embeddings
Add camera configuration API instead of hardcoded polygons
Add persistent edge event buffer / DLQ
Containerize CV worker with an optional CPU/GPU profile
Add WebSocket or SSE dashboard updates
Add structured log aggregation
Add OpenTelemetry tracing
Add full CV state-machine tests
Add load tests for event ingestion
```

---

## 21. Git Workflow Used

Recommended branch naming:

```text
docs/acceptance-gate-foundation
feature/event-schema-v1-2
feature/full-event-persistence
feature/robust-event-ingestion
feature/health-feed-status
feature/expanded-store-metrics
feature/zone-heatmap-endpoint
feature/event-derived-queue-funnel
feature/anomaly-detection-endpoint
feature/structured-api-logging
test/minimal-api-regression-suite
```

Recommended commit style:

```text
docs: add acceptance gate documentation and run checklist
feat: add event metadata schema and session sequence fields
feat: persist full event schema fields in database
feat: add partial success handling for event ingestion
feat: add feed freshness status to health endpoint
feat: add queue depth and dwell metrics
feat: add zone heatmap endpoint
feat: compute queue funnel metrics from event stream
feat: add rule-based anomaly detection endpoint
feat: add structured request logging middleware
test: add minimal API regression tests
```

---

## 22. Final Submission Status

Current implementation status:

```text
API containerized: yes
Dashboard containerized: yes
CV pipeline implemented: yes, host-side
Event ingestion: yes
Event schema metadata: yes
Full event persistence: yes
Metrics endpoint: yes
Funnel endpoint: yes
Heatmap endpoint: yes
Anomalies endpoint: yes
Health endpoint: yes
Structured logging: yes
Minimal tests: yes
README: yes
DESIGN.md: yes
CHOICES.md: yes
```

Current readiness:

```text
PARTIALLY READY TO READY FOR SUBMISSION
```

The remaining major weakness is the absence of full cross-camera Re-ID and fully containerized CV execution.
