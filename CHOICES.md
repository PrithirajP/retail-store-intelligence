# CHOICES.md

# Engineering Choices and Rationale

This document records the major engineering decisions made during the Retail Store Intelligence Platform implementation.

The project was implemented under challenge-style constraints, so the choices prioritize:

* acceptance-gate reliability
* reviewer-friendly setup
* implementation simplicity
* business usefulness
* testability
* clear upgrade path for production

---

## Decision 1 — Detection Model

### Decision

Use `YOLOv8n` for person detection.

### Why

YOLOv8n gives a practical balance between speed, simplicity, and person-detection quality. It is lightweight enough for local execution, integrates well with Ultralytics, and supports tracking through ByteTrack. A larger detector may improve accuracy but would increase runtime, dependency size, and reviewer setup risk.

---

## Decision 2 — Tracking Model

### Decision

Use `ByteTrack` for local camera-level tracking.

### Why

ByteTrack handles low-confidence detections better than simple SORT and avoids the extra appearance-model dependency of DeepSORT or StrongSORT. It is suitable for tracking shoppers within a single camera view and supports zone, queue, and line-crossing logic. Full global cross-camera identity is treated separately through lightweight re-entry handling and documented future Re-ID upgrades.

---

## Decision 3 — Re-ID and REENTRY Strategy

### Decision

Implement lightweight distance-based `REENTRY` matching at configured entrance cameras.

### Why

Full appearance-based Re-ID using OSNet or TorchReID would require another deep model, embedding storage, similarity thresholds, and additional validation. For this challenge, a lighter approach is more reliable: when a visitor exits through an entrance line, the tracker stores a recent-exit candidate. If a new local track re-enters near that exit within a configured time and distance window, the system emits `REENTRY` and maps the new local track back to the earlier visitor ID.

This reduces re-entry double counting without adding a heavy Re-ID model.

---

## Decision 4 — Entry, Exit, and Zone Detection

### Decision

Use bottom-center foot points, manual zone polygons, and directional entrance-line crossing.

### Why

The bottom-center of a bounding box approximates the person’s floor position in CCTV footage. Manual polygons make zone logic simple, explainable, and easy to adjust. Directional entrance-line crossing improves visitor counting compared with entry-door polygon-only logic because the system can distinguish `IN` and `OUT` movement.

---

## Decision 5 — Staff Detection

### Decision

Use a behind-counter spatial heuristic for staff exclusion.

### Why

Cashiers are the most common source of staff noise in billing and queue analytics. If a person remains inside the `BEHIND_COUNTER` polygon for more than the configured frame threshold, the visitor is marked as staff and excluded from customer metrics. This is simple, fast, and avoids fragile uniform-color or face-recognition assumptions.

---

## Decision 6 — Event Schema

### Decision

Use canonical `Event Schema v1.2` with nested metadata.

### Why

The challenge requires structured fields such as `event_id`, `store_id`, `camera_id`, `visitor_id`, `event_type`, `timestamp`, `zone_id`, `dwell_ms`, `is_staff`, `confidence`, and `metadata`. The nested metadata object stores queue depth, SKU zone, and session sequence. This keeps the internal event format consistent while supporting analytics and API validation.

---

## Decision 7 — Event Ingestion

### Decision

Normalize incoming raw events before validation.

### Why

The provided sample-event format and the internal canonical schema may use different field names. The ingestion layer maps fields such as `id_token`, `track_id`, `store_code`, `event_timestamp`, `zone_entered`, `queue_completed`, and `queue_abandoned` into the internal schema. This allows the API to support both challenge-style sample events and canonical CV-generated events without changing downstream logic.

---

## Decision 8 — Event Log JSONL Generation

### Decision

Generate `event_log.jsonl` from the API database after events are ingested, validated, normalized, and persisted.

### Why

The event log is a mandatory deliverable. Exporting it from the persisted API database ensures that the submitted JSONL contains only accepted events and stays consistent with `/metrics`, `/funnel`, `/heatmap`, and `/anomalies`. The file is included in the repository because no separate event-log upload field was available, while videos, POS files, model weights, and database files remain excluded.

---

## Decision 9 — Database

### Decision

Use SQLite with SQLAlchemy.

### Why

SQLite minimizes setup friction for reviewers and avoids requiring a separate database service, credentials, or migrations. SQLAlchemy keeps the database layer structured and allows a future migration to PostgreSQL if the system is productionized.

---

## Decision 10 — POS Parser

### Decision

Support both official-style and uploaded/current POS CSV schemas.

### Why

The POS format may vary between challenge resources and exported files. The parser supports schemas such as `transaction_id, store_id, timestamp, basket_value_inr` and `order_id, order_date, order_time, store_id, total_amount`. This reduces evaluator-data risk and keeps conversion correlation functional across file variants.

---

## Decision 11 — Funnel Logic

### Decision

Use a four-stage shopper funnel:

```text
Entered Store → Visited Product Zone → Entered Billing Queue → Completed Purchase
```

### Why

This funnel better represents the retail customer journey than a simple entry-to-purchase pipeline. It separates browsing behavior from queue participation and purchase completion, giving more useful business insight into where shoppers drop off.

---

## Decision 12 — Queue Analytics

### Decision

Compute queue metrics from event-stream queue cycles.

### Why

Billing queue behavior is best inferred from queue-specific events: `BILLING_QUEUE_JOIN`, `BILLING_QUEUE_EXIT`, and `BILLING_QUEUE_ABANDON`. This is more reliable than depending only on global session state, especially because full appearance-based cross-camera Re-ID is not implemented.

---

## Decision 13 — Heatmap

### Decision

Use zone-level heatmap analytics instead of pixel-level heatmaps.

### Why

Retail managers usually need to know which product zones receive attention, not exact pixel-density maps. Zone-level heatmaps are easier to validate, explain, and connect to business actions. They also avoid requiring homography calibration from CCTV pixels to floor-plan coordinates.

---

## Decision 14 — Anomaly Detection

### Decision

Use rule-based anomaly detection.

### Why

The challenge data is limited, so learned anomaly models would be difficult to train and validate reliably. Rule-based anomalies such as `BILLING_QUEUE_SPIKE`, `CONVERSION_DROP`, `DEAD_ZONE`, and `STALE_FEED` are deterministic, explainable, and easy to test.

---

## Decision 15 — API Framework

### Decision

Use FastAPI.

### Why

FastAPI provides strong request validation, clean endpoint design, automatic OpenAPI documentation, and good testing support through `TestClient`. It fits well for a structured event-ingestion and analytics API.

---

## Decision 16 — Dashboard

### Decision

Use Streamlit for the dashboard.

### Why

Streamlit allows rapid development of a business-facing analytics dashboard with minimal frontend complexity. It supports KPI cards, tables, charts, store selection, refresh controls, and API-driven panels for metrics, funnel, heatmap, anomalies, and health.

---

## Decision 17 — Containerization

### Decision

Use Docker Compose for API and dashboard by default, with an optional `cv-worker` profile for the CV pipeline.

### Why

The API and dashboard must run reliably for reviewers using `docker compose up --build`. The CV stack is heavier because it depends on PyTorch, OpenCV, Ultralytics, and tracking libraries. Making CV optional gives two paths: a lightweight default path for API/dashboard and a full CV path using `docker compose --profile cv up --build`.

---

## Decision 18 — Structured Logging

### Decision

Use standard Python logging with JSON-style structured payloads.

### Why

This provides important observability fields without adding extra logging dependencies. The API logs trace ID, method, endpoint, status code, latency, store ID, client host, and ingestion counters. Each response also includes an `X-Trace-Id`.

---

## Decision 19 — Testing Strategy

### Decision

Use pytest with deterministic API, business-logic, dashboard-contract, and tracker-state tests.

### Why

API behavior, event validation, metrics, funnel logic, heatmap logic, anomaly rules, staff filtering, line crossing, and re-entry matching are deterministic and suitable for automated tests. Raw YOLO/ByteTrack model output is hardware- and video-dependent, so it is validated through runtime CV pipeline execution rather than unit tests.

---

## Final Baseline

```text
Detection Model: YOLOv8n
Tracking Model: ByteTrack
Re-ID Strategy: Lightweight same-entrance REENTRY matching; full appearance Re-ID planned
Entry/Exit Strategy: Directional entrance-line crossing
Zone Detection: Polygon + bottom-center point
Queue Detection: Event-derived queue cycles
Staff Detection: Behind-counter heuristic
Event Schema: v1.2 with normalization adapter
Database: SQLite + SQLAlchemy
API Framework: FastAPI
Dashboard: Streamlit
Logging: Standard logging with JSON-style records
Testing: Expanded pytest API/business/dashboard/tracker suite
Deployment: Docker Compose for API/dashboard, optional cv-worker profile, host-side CV supported
Event Log: event_log.jsonl generated from accepted API events and included as required deliverable
```
