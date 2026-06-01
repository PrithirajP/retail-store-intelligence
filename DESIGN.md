# DESIGN.md — Store Intelligence Platform

## 1. Architecture Overview

This project implements a store intelligence pipeline that converts CCTV footage into business metrics for retail operations. The current system has three main layers:

```text
Raw CCTV Videos
    ↓
CV Edge Pipeline
YOLOv8n + ByteTrack + polygon zone engine
    ↓
Structured Events
ENTRY, ZONE_ENTER, ZONE_EXIT, ZONE_DWELL, BILLING_QUEUE_JOIN, BILLING_QUEUE_EXIT
    ↓
FastAPI Backend
Validation, idempotent ingestion, session materialization, POS correlation
    ↓
SQLite Database
Raw events, visitor sessions, POS transactions
    ↓
Analytics API
/metrics and /funnel
    ↓
Streamlit Dashboard
Live conversion and funnel visualization
```

The North Star metric is offline store conversion rate:

```text
converted visitors / total unique visitors
```

## 2. Edge/Cloud Split

The current implementation separates the system into two operational layers:

| Layer | Runtime | Components |
|---|---|---|
| Cloud/backend layer | Docker Compose | FastAPI API and Streamlit dashboard |
| Edge CV layer | Host Python process | YOLOv8n, ByteTrack, polygon zone engine |

The API and dashboard are containerized to provide a reliable review path. The CV pipeline currently runs outside Docker because PyTorch, OpenCV, and Ultralytics introduce hardware-specific dependency risk inside containers, especially across macOS, Windows, and Linux machines.

## 3. Computer Vision Pipeline

Final CV entrypoint:

```text
cv_pipeline/orchestrator.py
```

Main modules:

| File | Responsibility |
|---|---|
| `detector.py` | Loads YOLOv8n and uses Ultralytics ByteTrack to return local person tracks |
| `tracker_state.py` | Maintains zone dwell state, staff state, and queue transitions |
| `event_emitter.py` | Buffers and posts event batches to FastAPI |
| `zone_mapper.py` | Manual OpenCV polygon calibration utility |
| `orchestrator.py` | Master loop for all configured cameras |

### Detection

The detector uses YOLOv8n because it is fast enough for CPU execution and has simple Ultralytics integration.

### Tracking

The implementation uses ByteTrack through Ultralytics tracking. This gives local frame-to-frame identity continuity within a single camera feed.

### Re-ID Status

Cross-camera Re-ID and OSNet are not implemented in the current code. Visitor IDs are currently local ByteTrack IDs formatted as `VIS_<track_id>`.

This means re-entry handling and cross-camera deduplication are known limitations.

## 4. Zone Mapping

The project uses manual polygon calibration instead of parsing the provided layout file. `zone_mapper.py` opens the first frame of a video and lets the developer click polygon points. The printed `np.array(..., np.int32)` values are copied into `CAMERA_CONFIGS` inside `orchestrator.py`.

Configured zones:

| Camera | Zones |
|---|---|
| `CAM_ENTRANCE` | `ENTRY_DOOR` |
| `CAM_BILLING` | `BEHIND_COUNTER`, `BILLING_QUEUE` |
| `CAM_MAKEUP` | `MAKEUP` |
| `CAM_SKINCARE` | `SKINCARE` |

The system uses the bottom-center point of the bounding box as the person’s floor position. This is more reliable than using the bounding-box center because CCTV perspective can make a person’s torso overlap a different zone from where they are actually standing.

## 5. Staff Exclusion

The current staff exclusion strategy is a behind-counter spatial heuristic.

If a local visitor ID remains inside the `BEHIND_COUNTER` polygon for more than 30 consecutive frames, that visitor is added to a `staff_profiles` set and future events for that ID use `is_staff=True`.

This handles cashier-like staff but does not fully handle roaming floor staff.

## 6. Queue Logic

The CV pipeline emits queue spatial facts:

```text
BILLING_QUEUE_JOIN
BILLING_QUEUE_EXIT
```

The backend derives conversion and abandonment from these events.

When a `BILLING_QUEUE_EXIT` event is ingested, the API looks for an unclaimed POS transaction in the same store within the previous 5 minutes. If a transaction is found, the transaction is claimed and the visitor session is marked as converted.

Queue abandonment is calculated in `/funnel` as:

```text
entered_billing_queue - completed_purchase
```

## 7. Backend API

Framework:

```text
FastAPI + Pydantic + SQLAlchemy
```

Implemented endpoints:

| Endpoint | Purpose |
|---|---|
| `GET /health` | Basic liveness check |
| `POST /events/ingest` | Batch ingest CV events |
| `GET /stores/{store_id}/metrics` | Total visitors, conversions, conversion rate |
| `GET /stores/{store_id}/funnel` | Entry → billing → purchase funnel |

Missing endpoints:

```text
GET /stores/{store_id}/heatmap
GET /stores/{store_id}/anomalies
```

## 8. Database Design

Database:

```text
SQLite using SQLAlchemy ORM
```

Tables:

| Table | Purpose |
|---|---|
| `events` | Raw event ledger and idempotency by `event_id` |
| `sessions` | Materialized visitor lifecycle state |
| `pos_transactions` | Seeded POS transaction data |

The `sessions` table allows the metrics and funnel endpoints to use fast count queries rather than reconstructing visitor journeys from raw events on every dashboard refresh.

## 9. Dashboard Design

The dashboard is implemented with Streamlit and Plotly.

It polls:

```text
GET /stores/ST1008/metrics
GET /stores/ST1008/funnel
```

every 5 seconds and displays:

- total unique visitors,
- converted visitors,
- conversion rate,
- funnel chart,
- queue abandonment count and rate.

## 10. AI-Assisted Decisions

AI assistance was used to reason about implementation trade-offs and challenge priorities.

### Decision 1: YOLOv8n over heavier detectors

AI suggested multiple detector options including YOLO, Faster R-CNN, and MediaPipe. The final choice was YOLOv8n because the challenge required a runnable end-to-end system under time constraints, and YOLOv8n offered the best balance between speed, ecosystem maturity, and ease of integration with ByteTrack.

### Decision 2: Edge/cloud split

AI initially suggested full Docker containerization. The final decision was to containerize API and dashboard while running the CV pipeline on the host. This deviates from an ideal one-command setup but reduces hardware-specific failure modes from PyTorch/OpenCV/Ultralytics inside Docker.

### Decision 3: Flattened event schema

AI suggested using the full nested challenge schema. The current implementation uses a flattened event schema to reduce integration risk and avoid Pydantic/SQLAlchemy serialization issues during the first working version. This is acknowledged as a compliance gap and planned for upgrade in the next milestone.

## 11. Known Limitations

- `README.md`, `DESIGN.md`, and `CHOICES.md` are added in this milestone, but tests are still missing.
- Cross-camera Re-ID is not implemented.
- `REENTRY` events are not generated.
- `EXIT` events are not generated by the CV pipeline.
- `/heatmap` is not implemented.
- `/anomalies` is not implemented.
- Event metadata is not fully challenge-compliant yet.
- CV pipeline is not part of default Docker Compose.
- Structured JSON logging is not implemented.
- SQLite database is not persisted through a mounted volume.

## 12. Production Evolution Path

The next engineering steps are:

1. Add challenge-compatible event metadata.
2. Persist full event payload fields in SQLite.
3. Implement `/heatmap`.
4. Implement `/anomalies`.
5. Upgrade `/health` with last event timestamp and stale-feed warnings.
6. Add minimal pytest coverage and prompt blocks.
7. Add optional Docker Compose profile for the CV worker.
8. Add lightweight re-entry heuristic.
