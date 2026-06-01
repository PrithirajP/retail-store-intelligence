# CHOICES.md — Engineering Decisions

This document records the major engineering decisions made in the current Store Intelligence Platform implementation. It intentionally separates implemented behavior from future roadmap items.

## Decision 1: Detection Model

### Options Considered

| Option | Pros | Cons |
|---|---|---|
| MediaPipe object detection | Lightweight, CPU-friendly | Less suitable for robust retail tracking pipeline |
| Faster R-CNN | Higher accuracy | Too slow and heavy for quick CPU-based challenge deployment |
| YOLOv10/YOLOv11 | Newer models | More integration risk under time constraints |
| YOLOv8n | Fast, mature, easy Ultralytics integration | Lower accuracy than larger models |

### Final Choice

```text
YOLOv8n using Ultralytics
```

### Rationale

The project needed a detector that could run on ordinary hardware and integrate quickly with a tracker. YOLOv8n was chosen because it is lightweight, widely used, easy to install, and integrates directly with ByteTrack in the Ultralytics API.

The goal of the challenge is not perfect detection accuracy. The goal is a complete system that converts raw video into useful store metrics. YOLOv8n supports that goal better than heavier models because it keeps the system runnable.

### Trade-offs

- May miss people under occlusion.
- Less accurate for small/distant people than larger YOLO variants.
- May produce false positives in retail-like scenes with mannequins or posters.

### Interview Defense

I prioritized deployment viability over theoretical detection accuracy. A slightly weaker detector that runs reliably across machines is better for this challenge than a heavier detector that risks failing the reviewer’s environment.

---

## Decision 2: Tracking Model

### Options Considered

| Option | Pros | Cons |
|---|---|---|
| SORT | Simple and fast | Loses IDs when detections drop |
| DeepSORT | Adds appearance information | More dependencies and complexity |
| BoT-SORT/StrongSORT | More robust | Heavier and more complex |
| ByteTrack | Good local tracking with low-confidence detections | No cross-camera identity by itself |

### Final Choice

```text
ByteTrack through Ultralytics model.track(..., tracker="bytetrack.yaml")
```

### Rationale

ByteTrack handles local track continuity well and keeps low-confidence detections in the association process. This is useful in retail scenes where shoppers may be partially occluded by shelves or other people.

### Trade-offs

- Identity is local to a camera/track sequence.
- No cross-camera deduplication.
- No true re-entry recognition.

### Interview Defense

ByteTrack was the right v1 choice because it enabled stable local zone transitions without introducing a second model or embedding pipeline. Re-ID is a planned extension, not part of the current implementation.

---

## Decision 3: Re-ID Strategy

### Final Current Status

```text
Not implemented in current code.
```

OSNet/TorchReID and global identity matching were considered but not implemented due to time and dependency risk.

### Rationale

Re-ID requires crop extraction, embedding inference, identity gallery storage, similarity thresholds, and local-to-global ID mapping. Implementing it properly would have taken significant time away from the API, database, POS correlation, and dashboard.

### Current Impact

- `REENTRY` events are not generated.
- Cross-camera deduplication is missing.
- Visitor counts may be inflated.
- Funnel sessions may fragment.

### Future Decision

The approved baseline is to add a lightweight re-entry heuristic first, possibly using color histogram matching, before attempting full OSNet.

---

## Decision 4: Event Schema

### Options Considered

| Option | Pros | Cons |
|---|---|---|
| Full nested challenge schema | Most compliant | More implementation complexity |
| Flattened schema | Easy to generate, validate, and ingest | Missing challenge metadata |
| Raw detector schema | Quick but not business-friendly | Weak API contract |

### Final Current Choice

```text
Flattened event schema
```

Current fields:

```text
event_id, store_id, camera_id, visitor_id, timestamp, event_type,
zone_id, dwell_ms, is_staff, confidence
```

### Rationale

The flattened schema was chosen to reduce integration risk during the first working version. It made it easier for the CV pipeline to generate JSON and for FastAPI/Pydantic to validate incoming events.

### Trade-offs

The current schema does not fully match the challenge-required schema. It lacks:

```text
metadata.queue_depth
metadata.sku_zone
metadata.session_seq
```

### Future Decision

Upgrade to event schema `v1.2`: keep flattened core fields but add nested `metadata` for challenge compatibility.

---

## Decision 5: API Architecture

### Options Considered

| Option | Pros | Cons |
|---|---|---|
| Flask | Simple | Weaker built-in validation |
| Django REST Framework | Full-featured | Too heavy for the challenge |
| Node/Express | Flexible | Less natural for Python CV stack |
| FastAPI | Typed validation, fast implementation, OpenAPI | Needs discipline to avoid bloated route files |

### Final Choice

```text
FastAPI + Pydantic + SQLAlchemy
```

### Rationale

FastAPI provides a clean JSON API, automatic validation with Pydantic, good Docker compatibility, and a fast development path. This was important for building a working end-to-end system within the timebox.

### Trade-offs

Currently, metrics and funnel logic live directly inside `api/main.py`. This made implementation fast but reduces modularity and testability.

### Future Decision

Refactor into service modules only after required endpoints and acceptance-gate items are complete.

---

## Decision 6: Database

### Options Considered

| Option | Pros | Cons |
|---|---|---|
| SQLite | Zero setup, reliable for local demo | Weak concurrency, no row-level locks |
| PostgreSQL | Production-grade concurrency | Extra container, credentials, setup complexity |
| In-memory state | Very simple | Loses data and weak for API queries |
| JSONL files | Easy event logging | Poor queryability |

### Final Choice

```text
SQLite with SQLAlchemy ORM
```

### Rationale

SQLite minimized setup risk and allowed the API to run without a separate database container. This was the safest choice for a time-boxed challenge where `docker compose up` reliability mattered.

### Materialized Sessions Decision

The system uses a `sessions` table instead of computing metrics from raw events on every request. This makes `/metrics` and `/funnel` fast and easy to reason about.

### Trade-offs

- SQLite can lock under concurrent writes.
- The DB file is not currently mounted as persistent storage.
- Raw event persistence is currently too minimal for heatmap/dwell analytics.

### Future Decision

Keep SQLite for the challenge submission but persist richer event fields. PostgreSQL is the production migration path.

---

## Decision 7: Queue and POS Correlation

### Final Choice

The edge CV pipeline emits spatial queue facts:

```text
BILLING_QUEUE_JOIN
BILLING_QUEUE_EXIT
```

The API derives conversion by matching queue exits to POS transactions within a 5-minute lookback window.

### Rationale

The CV pipeline does not have access to POS data, so it should not decide whether a shopper purchased or abandoned. The backend is the correct place to perform business correlation.

### Trade-offs

- No explicit `BILLING_QUEUE_ABANDON` event is emitted.
- Queue wait time is not currently available because `billing_join_time` is not stored.
- Queue depth is not currently exposed.

### Future Decision

Add `billing_join_time`, live queue depth, and API-derived abandonment details in later milestones.

---

## Decision 8: Staff Detection

### Options Considered

| Option | Pros | Cons |
|---|---|---|
| Uniform color mask | Simple | Brittle under lighting and customer clothing overlap |
| Face blur/face cues | Tempting if visible | Not reliable and conflicts with anonymized footage assumption |
| Custom classifier | Better generalization | Requires data/training time |
| Behind-counter heuristic | Fast and deterministic | Misses roaming staff |

### Final Choice

```text
Behind-counter spatial heuristic
```

### Rationale

Cashier-like staff are a major source of noise in queue analytics. The behind-counter polygon removes this noise with almost no compute overhead.

### Trade-offs

- Roaming staff are not excluded.
- Customers leaning behind the counter may be falsely marked staff.

### Future Decision

Add a no-entry/multi-camera heuristic or lightweight crop classifier if time permits.

---

## Decision 9: Dashboard

### Options Considered

| Option | Pros | Cons |
|---|---|---|
| Terminal dashboard | Lightweight | Less visually compelling |
| React/Vue | Full control | Too much setup for challenge timeline |
| Streamlit | Very fast to build | Polling/rerun UX is less polished |

### Final Choice

```text
Streamlit + Plotly
```

### Rationale

Streamlit gives a browser-based dashboard quickly and is easy to run in Docker. It demonstrates that API metrics update as events are ingested.

### Trade-offs

- Store ID is hardcoded to `ST1008`.
- UI reruns every 5 seconds.
- No heatmap/anomaly panels yet.

---

## Decision 10: Containerization

### Final Current Choice

```text
Docker Compose for API + dashboard; host-side CV pipeline
```

### Rationale

The API and dashboard need to boot reliably for the acceptance gate. CV dependencies introduce higher Docker risk due to PyTorch/OpenCV/Ultralytics.

### Trade-offs

- Full system is not currently one-command.
- Reviewer must run the CV pipeline in a host Python environment.

### Future Decision

Add an optional Docker Compose `vision-worker` profile after the acceptance-gate documentation and core API upgrades are complete.
