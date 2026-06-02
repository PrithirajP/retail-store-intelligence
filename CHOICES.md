# CHOICES.md

# Engineering Choices and Trade-offs

This document explains the major engineering decisions made during the implementation of the Retail Store Intelligence Platform.

The project was built under challenge-style constraints, so decisions prioritize:

```text
acceptance-gate reliability
implementation speed
reviewer confidence
business usefulness
interview defensibility
```

---

# Decision 1: Detection Model

## Alternatives Considered

### MediaPipe Object Detection

Pros:

- Lightweight
- CPU friendly
- Easy to run locally

Cons:

- Less mature for multi-person CCTV retail scenes
- Tracking integration less direct
- Less flexible for challenge-style CV pipelines

### Faster R-CNN

Pros:

- Strong accuracy
- Good for complex object detection

Cons:

- Too slow for CPU-first edge processing
- Heavy dependency footprint
- Overkill for person-only detection

### YOLOv10 / YOLOv11

Pros:

- Newer model families
- Strong detection performance

Cons:

- More uncertainty around ecosystem maturity
- More risk under time constraints

## Decision

Use:

```text
YOLOv8n
```

## Rationale

YOLOv8n provides the best balance between:

- Detection quality
- Speed
- Simplicity
- Ultralytics ecosystem support
- ByteTrack integration

## Trade-off

Choosing the nano model sacrifices some accuracy, especially in:

- Occlusion
- Low light
- Distant shoppers
- Crowded scenes

## Interview Defense

I chose YOLOv8n because the challenge needed a working end-to-end system, not a benchmark-winning detector. In retail analytics, stable approximate trends are often more useful than perfect frame-level detection if the system is reliable and cheap to deploy.

---

# Decision 2: Tracking Model

## Alternatives Considered

### SORT

Pros:

- Simple
- Fast

Cons:

- Drops identities easily when detections are weak
- Poor occlusion handling

### DeepSORT

Pros:

- Adds appearance features
- Better identity retention than SORT

Cons:

- More compute
- More complexity
- Extra model dependency

### BoT-SORT / StrongSORT

Pros:

- Stronger tracking performance
- Better ID consistency

Cons:

- Heavier implementation
- More compute overhead
- More risk in short challenge timeline

## Decision

Use:

```text
ByteTrack
```

## Rationale

ByteTrack was selected because it handles low-confidence detections better than simpler trackers. This is useful in retail stores where customers are partially occluded by shelves, counters, or other shoppers.

## Trade-off

ByteTrack only provides local camera tracking. It does not solve cross-camera identity.

## Interview Defense

ByteTrack gives strong local tracking for low implementation cost. I used it to make zone and queue events stable enough for analytics, while leaving a clear future path for Re-ID.

---

# Decision 3: Re-ID Strategy

## Alternatives Considered

### Full OSNet / TorchReID Implementation

Pros:

- Cross-camera identity
- Enables REENTRY detection
- Improves true visitor uniqueness

Cons:

- Extra model integration
- Additional inference cost
- Dependency risk
- Threshold tuning required
- Hard to validate quickly

### Simple Color Histogram Re-ID

Pros:

- Easy to implement
- Low compute

Cons:

- Weak accuracy
- Sensitive to lighting
- Poor robustness

## Previous Decision

Implement OSNet/TorchReID for global identity.

## Issue

This created too much implementation and dependency risk for the challenge timeline.

## Recommended Decision

Defer full Re-ID.

Implemented identity strategy:

```text
ByteTrack-local visitor IDs
```

## Rationale

The project needed a working API, event pipeline, database, dashboard, and metrics. Re-ID would have consumed too much implementation time and increased the risk of an unstable submission.

## Implementation Impact

Affected files:

```text
cv_pipeline/detector.py
cv_pipeline/orchestrator.py
cv_pipeline/tracker_state.py
```

No `reid.py` module is currently implemented.

## Score Impact

This loses points for cross-camera identity and REENTRY handling, but preserves acceptance-gate reliability and overall system completeness.

## Interview Defense

I made a deliberate trade-off: implement the full analytics pipeline first, and leave Re-ID as a clean future extension. A half-built Re-ID system would be worse than a stable system with clearly documented identity limitations.

---

# Decision 4: Zone Detection Strategy

## Alternatives Considered

### Object-center zone detection

Pros:

- Easy

Cons:

- Inaccurate for CCTV perspective
- Person’s upper body may overlap shelves while feet are elsewhere

### Segmentation-based floor mapping

Pros:

- More sophisticated

Cons:

- Requires more data
- Harder to calibrate
- Too complex for challenge timeline

## Decision

Use:

```text
bottom-center point of bounding box + polygon hit test
```

## Rationale

The bottom-center of the bounding box better approximates where the person is standing on the floor.

## Trade-off

Polygon boundaries can flicker if the detected foot point jitters near the edge.

## Future Improvement

Add hysteresis/debounce:

```text
must remain inside/outside for N frames before firing enter/exit
```

## Interview Defense

Polygon-based zone detection is simple, fast, explainable, and appropriate for manually calibrated CCTV analytics.

---

# Decision 5: Staff Detection

## Alternatives Considered

### Uniform color masking

Pros:

- Easy to implement

Cons:

- Brittle under lighting changes
- False positives for customers wearing similar colors

### Custom staff classifier

Pros:

- More accurate if trained well

Cons:

- Requires labeled data
- Additional model complexity
- Extra inference cost

### Face blur / face detection artifact

Pros:

- Might work on sample data if staff/customer anonymization differs

Cons:

- Dataset leak
- Not robust
- Ethically and technically weak

## Decision

Use:

```text
behind-counter spatial heuristic
```

## Rule

```text
If a person stays inside BEHIND_COUNTER for more than 30 consecutive frames,
mark as staff.
```

## Rationale

Cashiers create the largest staff-noise problem in queue analytics. The behind-counter heuristic removes that noise with almost zero compute overhead.

## Trade-off

Roaming staff may still be counted as customers.

## Interview Defense

This is an 80/20 production choice: remove the highest-impact staff noise deterministically before adding heavier ML classification.

---

# Decision 6: Event Schema

## Previous Decision

Use a flattened event schema only.

## Issue

The challenge expected metadata fields such as:

```text
queue_depth
sku_zone
session_seq
```

A purely flattened schema created scoring risk.

## Recommended Decision

Use:

```text
Event Schema v1.2
```

with both flattened fields and nested metadata.

## Implemented Fields

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
metadata.queue_depth
metadata.sku_zone
metadata.session_seq
```

## Rationale

This preserves backward compatibility while improving challenge compliance.

## Implementation Impact

Affected files:

```text
api/models.py
cv_pipeline/tracker_state.py
api/database.py
api/main.py
```

## Score Impact

Improves schema compliance and enables heatmap, queue, and anomaly analytics.

---

# Decision 7: Database

## Alternatives Considered

### PostgreSQL

Pros:

- Production-grade
- Better concurrency
- Stronger querying
- Better for multi-service deployment

Cons:

- Requires extra Docker service
- Credentials/configuration
- More setup risk

### SQLite

Pros:

- Zero configuration
- Simple
- Fast startup
- Easy reviewer setup

Cons:

- Limited concurrency
- Not ideal for production write-heavy workloads

## Decision

Use:

```text
SQLite + SQLAlchemy
```

## Rationale

SQLite minimizes acceptance-gate risk. The project is challenge-focused, and SQLite is sufficient for single-reviewer local evaluation.

## Trade-off

SQLite is not the recommended production database for high-throughput multi-camera ingestion.

## Interview Defense

I used SQLite for submission reliability. In production I would migrate to PostgreSQL with Alembic migrations.

---

# Decision 8: API Framework

## Alternatives Considered

### Flask

Pros:

- Simple
- Familiar

Cons:

- Weaker typing by default
- Less automatic schema support

### Django REST Framework

Pros:

- Full-featured

Cons:

- Heavy
- Too much boilerplate for challenge timeline

## Decision

Use:

```text
FastAPI
```

## Rationale

FastAPI provides:

- Pydantic validation
- Automatic OpenAPI docs
- Simple dependency injection
- Good async support
- Clean route structure

## Interview Defense

FastAPI was the best fit for a typed event-ingestion API with structured responses and quick development.

---

# Decision 9: Event Ingestion

## Previous Approach

Validate the full batch with Pydantic before entering the route handler.

## Issue

One malformed event could cause the entire batch to fail with HTTP 422.

## Decision

Validate events individually inside `/events/ingest`.

## Implemented Behavior

```text
valid events are persisted
duplicates are skipped
bad events are reported
response can be partial_success
```

## Rationale

This is more robust for edge devices, where occasional malformed or duplicate events should not block the whole stream.

## Trade-off

OpenAPI schema is slightly less strict because the route accepts raw body data.

## Interview Defense

For streaming edge systems, partial success is preferable to dropping the whole batch.

---

# Decision 10: Queue Analytics

## Previous Approach

Use `VisitorSession.billing_exit_time`.

## Issue

Without full cross-camera Re-ID, billing-camera visitor IDs may not match entrance-camera visitor IDs.

## Decision

Compute queue analytics from raw event stream.

## Implemented Inputs

```text
BILLING_QUEUE_JOIN
BILLING_QUEUE_EXIT
```

## Computed Metrics

```text
entered_billing_queue
completed_queue_cycles
current_queue_depth
avg_queue_wait_ms
queue_abandonment_count
queue_abandonment_rate
```

## Rationale

Queue events from the billing camera are more reliable for queue-specific analytics than session state alone.

## Trade-off

Conversion attribution still depends on POS correlation and visitor identity.

## Interview Defense

This is a pragmatic correction: use the most reliable signal for each metric. Entry metrics use sessions; queue metrics use billing queue events.

---

# Decision 11: Heatmap Analytics

## Alternatives Considered

### Pixel-level heatmap

Pros:

- More visual
- More detailed

Cons:

- Requires homography or floor projection
- More complex
- Harder to validate

### Zone-level heatmap

Pros:

- Simple
- Business-readable
- Directly tied to store layout

Cons:

- Less spatially granular

## Decision

Use:

```text
zone-level heatmap
```

## Rationale

Retail managers care about zone performance. Zone-level counts and dwell times are easier to explain than raw pixel heatmaps.

## Interview Defense

The challenge needed actionable store analytics; zone heatmap is sufficient and robust.

---

# Decision 12: Anomaly Detection

## Alternatives Considered

### ML anomaly detection

Pros:

- More sophisticated

Cons:

- Needs historical data
- Hard to validate
- Overkill for small clips

### Rule-based anomaly detection

Pros:

- Explainable
- Easy to test
- Fast to implement

Cons:

- Thresholds are manually chosen

## Decision

Use:

```text
rule-based anomaly detection
```

## Implemented Rules

```text
BILLING_QUEUE_SPIKE
CONVERSION_DROP
DEAD_ZONE
STALE_FEED
```

## Rationale

Rule-based anomalies are reliable, explainable, and suitable for challenge evaluation.

## Trade-off

Thresholds are not learned from real long-term history.

## Interview Defense

In production, rule-based alerts are often the first version. They are transparent and actionable.

---

# Decision 13: Dashboard

## Alternatives Considered

### React/Vue frontend

Pros:

- Professional frontend
- Flexible UI

Cons:

- Much slower to build
- More boilerplate
- More deployment complexity

### Terminal dashboard

Pros:

- Lightweight
- Fast

Cons:

- Less accessible for non-technical reviewers

### Streamlit

Pros:

- Fast development
- Data-native
- Easy charts
- Simple Docker container

Cons:

- Polling refresh can flicker
- Less customizable than React

## Decision

Use:

```text
Streamlit
```

## Rationale

Streamlit gave the fastest route to a reviewer-friendly dashboard.

## Implemented Panels

```text
System Health
North Star KPIs
Queue KPIs
Funnel
Queue Insights
Heatmap
Anomalies
Dwell Summary
```

## Interview Defense

The dashboard proves API connectivity and business value without adding frontend complexity.

---

# Decision 14: Containerization

## Previous Ideal

Containerize API, dashboard, and CV worker.

## Issue

Containerizing PyTorch/OpenCV/Ultralytics can create heavy images and GPU/driver issues, especially on Windows and macOS.

## Decision

Containerize:

```text
API
Dashboard
```

Run locally:

```text
CV pipeline
```

## Rationale

This protects the acceptance gate. The reviewer can always start the API and dashboard with Docker Compose.

## Trade-off

The full system is not a single-command Docker deployment.

## Interview Defense

This mirrors real edge-cloud architecture: the edge node processes video locally and streams JSON events to the cloud API.

---

# Decision 15: Structured Logging

## Alternatives Considered

### structlog / python-json-logger

Pros:

- Better structured logging support

Cons:

- Extra dependency
- More setup

### Standard logging + json.dumps

Pros:

- No new dependency
- Easy to implement
- Good enough for challenge

Cons:

- Less feature-rich

## Decision

Use:

```text
standard logging + JSON-style log payloads
```

## Logged Fields

```text
trace_id
method
endpoint
status_code
latency_ms
store_id
client_host
```

Ingest-specific fields:

```text
received_count
processed_count
duplicate_count
error_count
```

## Interview Defense

This adds practical observability without adding dependency risk.

---

# Decision 16: Testing Strategy

## Previous State

No automated tests.

## Issue

This weakened production readiness and reviewer confidence.

## Decision

Add minimal API regression tests.

## Implemented Tests

```text
health
valid ingest
duplicate ingest
partial-success ingest
metrics empty state
funnel empty state
heatmap empty state
anomalies empty state
```

## Result

```text
8 passed
```

## Rationale

Testing deterministic API and business logic provides the highest return. CV tests are deferred because video processing is hardware/model dependent.

## Interview Defense

I prioritized tests around stable business logic and acceptance-gate behavior rather than non-deterministic model inference.

---

# Final Baseline

```text
Detection Model: YOLOv8n
Tracking Model: ByteTrack
Re-ID Strategy: Planned, not implemented
Zone Detection: Polygon + bottom-center point
Queue Detection: Event-derived from queue join/exit
Staff Detection: Behind-counter heuristic
Event Schema: v1.2
Database: SQLite + SQLAlchemy
API Framework: FastAPI
Dashboard: Streamlit
Logging: Standard logging with JSON-style records
Testing: Minimal pytest API regression suite
Deployment: Docker Compose for API/dashboard, host-side CV
```