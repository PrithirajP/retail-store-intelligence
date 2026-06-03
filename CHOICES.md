# CHOICES.md

# Engineering Choices and Trade-offs

This document records the major engineering decisions made during the Retail Store Intelligence Platform implementation.

The project was implemented under challenge-style constraints, so decisions prioritize:

* acceptance-gate reliability
* reviewer confidence
* implementation simplicity
* production-oriented reasoning
* business usefulness

---

## Decision 1 — Detection Model

### Alternatives considered

```text
MediaPipe Object Detection
Faster R-CNN
YOLOv10 / YOLOv11
YOLOv8n
```

### Decision

Use:

```text
YOLOv8n
```

### Rationale

YOLOv8n gives a strong balance of speed, simplicity, and adequate person-detection quality for challenge-scale retail analytics.

It also integrates easily with Ultralytics tracking.

### Trade-off

The nano model is less accurate than heavier models in:

* occlusion
* distant shoppers
* poor lighting
* crowded frames

### Interview defense

The challenge required a working end-to-end system, not only a high-accuracy detector. YOLOv8n makes the edge pipeline feasible on CPU-class machines and allows more effort to be spent on event processing, API correctness, and analytics.

---

## Decision 2 — Tracking Model

### Alternatives considered

```text
SORT
DeepSORT
BoT-SORT
StrongSORT
ByteTrack
```

### Decision

Use:

```text
ByteTrack
```

### Rationale

ByteTrack handles low-confidence detections better than SORT and avoids the extra model/dependency overhead of DeepSORT or StrongSORT.

### Trade-off

ByteTrack gives local camera tracking only. It does not solve global cross-camera identity.

### Interview defense

ByteTrack is a strong local tracker for a time-limited implementation. It gives stable enough IDs for zone and queue analytics while leaving a clean upgrade path to Re-ID.

---

## Decision 3 — Re-ID Strategy

### Previous ideal

Implement full OSNet/TorchReID-based global identity.

### Issue

Full Re-ID would require:

* crop extraction
* second model inference
* embedding storage
* similarity thresholding
* cross-camera state management
* tuning and validation

### Decision

Defer full Re-ID.

Current implementation:

```text
ByteTrack-local visitor IDs
```

### Rationale

Completing API ingestion, database persistence, POS correlation, dashboard, and tests was higher priority than adding a partially reliable Re-ID layer.

### Trade-off

A shopper crossing cameras may be counted more than once.

### Interview defense

A weak Re-ID system can damage funnel accuracy more than no Re-ID. The implementation documents this limitation honestly and keeps the architecture ready for a future Re-ID module.

---

## Decision 4 — Zone Detection

### Alternatives considered

```text
center point of bounding box
bottom-center point of bounding box
semantic segmentation
homography-based floor projection
```

### Decision

Use:

```text
bottom-center point + polygon hit test
```

### Rationale

The bottom-center point better represents the person’s physical floor position in CCTV footage.

### Trade-off

Manual polygons are sensitive to camera drift and must be recalibrated if cameras move.

### Interview defense

Manual polygon zones are simple, explainable, fast, and appropriate for a challenge implementation.

---

## Decision 5 — Staff Detection

### Alternatives considered

```text
uniform color masking
custom staff classifier
face-based recognition
behind-counter heuristic
```

### Decision

Use:

```text
behind-counter spatial heuristic
```

### Rationale

Cashiers are the biggest source of staff noise in queue analytics. The behind-counter heuristic removes that noise with almost no compute cost.

### Trade-off

Roaming floor staff may still be counted as shoppers.

### Interview defense

This is a practical 80/20 solution. It removes the most damaging staff noise while avoiding fragile color or face-based logic.

---

## Decision 6 — Event Schema

### Previous approach

Use a flattened internal event schema.

### Issue

The challenge requires metadata such as:

```text
queue_depth
sku_zone
session_seq
```

The uploaded sample events also use non-canonical field names.

### Decision

Use canonical internal:

```text
Event Schema v1.2
```

with nested metadata, plus an event normalization adapter.

### Rationale

This preserves a clean internal schema while accepting multiple external payload styles.

### Trade-off

The API ingestion layer is slightly more complex.

### Interview defense

Production systems often normalize data from heterogeneous producers before validation. This adapter makes the ingestion path more robust.

---

## Decision 7 — Event Ingestion

### Previous approach

Strictly validate one schema.

### Issue

Uploaded challenge-style events use fields like:

```text
id_token
store_code
event_timestamp
zone_entered
queue_completed
queue_abandoned
```

### Decision

Normalize raw events before Pydantic validation.

### Rationale

This allows the API to accept:

```text
canonical schema
sample_events.jsonl-style schema
```

without changing downstream database or analytics logic.

### Trade-off

If a raw payload is very malformed, it may still fail validation after normalization. This is acceptable because failures are returned through partial-success response logic.

### Interview defense

This is a robust production pattern: normalize at the boundary, validate internally, and keep the core application stable.

---

## Decision 8 — Database

### Alternatives considered

```text
PostgreSQL
SQLite
```

### Decision

Use:

```text
SQLite + SQLAlchemy
```

### Rationale

SQLite minimizes reviewer setup risk and avoids extra Docker services, credentials, and migrations during challenge evaluation.

### Trade-off

SQLite is not ideal for high-throughput multi-camera production workloads.

### Interview defense

SQLite is suitable for local challenge evaluation. Production deployment should migrate to PostgreSQL with Alembic migrations.

---

## Decision 9 — POS Parser

### Problem

The official POS schema and uploaded POS CSV schema differ.

Official style:

```text
transaction_id, store_id, timestamp, basket_value_inr
```

Uploaded style:

```text
order_id, order_date, order_time, store_id, total_amount
```

### Decision

Support both POS schemas.

### Rationale

This reduces evaluator-data risk and keeps POS correlation functional across file variants.

### Trade-off

The parser has more normalization logic.

### Interview defense

POS integrations often vary by vendor/export. Supporting multiple schemas makes ingestion more production-like.

---

## Decision 10 — Funnel Logic

### Previous funnel

```text
Entered Store → Billing Queue → Purchase
```

### Required funnel

```text
Entered Store → Visited Product Zone → Entered Billing Queue → Completed Purchase
```

### Decision

Upgrade funnel to include `Visited Product Zone`.

### Rationale

The new funnel better matches the challenge requirement and gives managers more useful shopper-journey visibility.

### Trade-off

The response shape changed, so backward-compatible keys were preserved.

### Interview defense

The implementation improves compliance while maintaining compatibility with earlier tests and dashboard behavior.

---

## Decision 11 — Queue Analytics

### Alternatives considered

```text
session-only queue logic
event-stream-derived queue logic
```

### Decision

Use event-stream-derived queue analytics.

Inputs:

```text
BILLING_QUEUE_JOIN
BILLING_QUEUE_EXIT
BILLING_QUEUE_ABANDON
```

### Rationale

Queue behavior is best inferred from billing-camera events. This is more reliable than depending entirely on global identity, which is not implemented.

### Trade-off

Conversion attribution still depends on POS correlation.

### Interview defense

This uses the strongest available signal for queue metrics and avoids overclaiming Re-ID capabilities.

---

## Decision 12 — Heatmap

### Alternatives considered

```text
pixel heatmap
zone-level heatmap
```

### Decision

Use:

```text
zone-level heatmap
```

### Rationale

Retail managers care about zone engagement, not raw pixel density. Zone-level heatmaps are easier to validate and explain.

### Trade-off

Less spatial detail than a true pixel-level heatmap.

### Interview defense

Zone-level analytics are more actionable for store operations and are appropriate without homography calibration.

---

## Decision 13 — Anomaly Detection

### Alternatives considered

```text
ML anomaly detection
rule-based anomaly detection
```

### Decision

Use:

```text
rule-based anomaly detection
```

Implemented rules:

```text
BILLING_QUEUE_SPIKE
CONVERSION_DROP
DEAD_ZONE
STALE_FEED
```

### Rationale

Rule-based anomalies are deterministic, explainable, testable, and suitable for limited challenge data.

### Trade-off

Thresholds are manually chosen rather than learned from long-term historical data.

### Interview defense

Most production alerting starts with explainable threshold rules before moving to learned anomaly models.

---

## Decision 14 — API Framework

### Alternatives considered

```text
Flask
Django REST Framework
FastAPI
```

### Decision

Use:

```text
FastAPI
```

### Rationale

FastAPI provides:

* Pydantic validation
* automatic OpenAPI docs
* clean route structure
* good test support
* strong typing

### Trade-off

None significant for this challenge.

### Interview defense

FastAPI is the best fit for a typed event-ingestion API with structured payloads and fast implementation.

---

## Decision 15 — Dashboard

### Alternatives considered

```text
React/Vue
terminal dashboard
Streamlit
```

### Decision

Use:

```text
Streamlit
```

### Rationale

Streamlit gives a fast, data-oriented dashboard with minimal frontend overhead.

### Trade-off

Polling refresh can cause UI flicker.

### Interview defense

The dashboard demonstrates business value quickly and keeps frontend complexity low.

---

## Decision 16 — Containerization

### Ideal

Containerize:

```text
API
Dashboard
CV worker
```

### Issue

Containerizing CV introduces risk from:

* PyTorch image size
* OpenCV system dependencies
* CPU/GPU differences
* reviewer-machine compatibility

### Decision

Containerize:

```text
API
Dashboard
```

Run locally:

```text
CV worker
```

### Rationale

This protects API/dashboard startup reliability.

### Trade-off

The entire pipeline is not single-command Docker.

### Interview defense

This mirrors real edge-cloud architecture: video processing runs on an edge node and streams JSON events to a cloud API.

---

## Decision 17 — Structured Logging

### Alternatives considered

```text
structlog
python-json-logger
standard logging + json.dumps
```

### Decision

Use:

```text
standard logging + JSON-style payloads
```

### Rationale

This adds useful observability without adding dependencies.

### Logged fields

```text
trace_id
method
endpoint
status_code
latency_ms
store_id
client_host
received_count
processed_count
duplicate_count
error_count
```

### Interview defense

The implementation captures the essential production debugging fields with minimal complexity.

---

## Decision 18 — Testing Strategy

### Previous state

Minimal tests only.

### Decision

Expand deterministic API and business-logic tests.

### Implemented test areas

```text
health
ingestion
idempotency
partial success
sample-event normalization
acceptance-gate store
POS schemas
funnel stages
heatmap
anomaly rules
staff filtering
```

### Rationale

API and business logic are deterministic and suitable for automated testing. CV model output is hardware/model dependent and is validated manually.

### Trade-off

No automated YOLO/ByteTrack regression tests yet.

### Interview defense

The test suite focuses on stable acceptance-gate and scoring-critical behavior first.

---

## Final Baseline

```text
Detection Model: YOLOv8n
Tracking Model: ByteTrack
Re-ID Strategy: Planned, not implemented
Zone Detection: Polygon + bottom-center point
Queue Detection: Event-derived queue cycles
Staff Detection: Behind-counter heuristic
Event Schema: v1.2 with normalization adapter
Database: SQLite + SQLAlchemy
API Framework: FastAPI
Dashboard: Streamlit
Logging: Standard logging with JSON-style records
Testing: Expanded pytest API/business-logic suite
Deployment: Docker Compose for API/dashboard, host-side CV
```
