# Store Intelligence Platform

A lightweight Store Intelligence Platform for the Purplle/Apex Retail challenge. The system processes CCTV clips into structured visitor events, ingests those events through a FastAPI backend, stores analytical state in SQLite, and shows live conversion/funnel metrics in a Streamlit dashboard.

## Current Implementation Status

Implemented:

- FastAPI backend with event ingestion, health, metrics, and funnel endpoints.
- SQLite persistence using SQLAlchemy.
- POS transaction seeding from the provided CSV.
- YOLOv8n + ByteTrack computer vision pipeline for person detection/tracking.
- Manual polygon-based zone mapping.
- Billing queue join/exit event generation.
- POS correlation for conversion-rate calculation.
- Streamlit dashboard for visitors, conversions, conversion rate, funnel, and queue abandonment.

Known limitations are documented below. This README intentionally describes the actual current implementation, not the future roadmap.

## Repository Structure

```text
store-intelligence/
├── api/
│   ├── Dockerfile
│   ├── database.py
│   ├── main.py
│   ├── models.py
│   ├── requirements.txt
│   └── seed_data.py
├── cv_pipeline/
│   ├── detector.py
│   ├── event_emitter.py
│   ├── orchestrator.py
│   ├── requirements.txt
│   ├── tracker_state.py
│   ├── worker.py              # Deprecated; not used by final pipeline
│   └── zone_mapper.py
├── dashboard/
│   ├── Dockerfile
│   ├── app.py
│   └── requirements.txt
├── data/                      # Created locally by reviewer; not committed
├── docker-compose.yml
├── README.md
├── DESIGN.md
├── CHOICES.md
└── SUBMISSION_CHECKLIST.md
```

## Required Data Placement

Create a `data/` folder at the repository root and place the challenge files there.

The API expects this POS CSV filename:

```text
Brigade_Bangalore_10_April_26.csv
```

The CV pipeline currently expects the videos to be renamed as follows because `cv_pipeline/orchestrator.py` uses hardcoded paths:

| Logical Camera | Expected File Path | Purpose |
|---|---|---|
| `CAM_ENTRANCE` | `data/CAM_03.mp4` | Entry-door detection |
| `CAM_BILLING` | `data/CAM_05.mp4` | Billing queue and behind-counter staff zone |
| `CAM_MAKEUP` | `data/CAM_02.mp4` | Makeup zone tracking |
| `CAM_SKINCARE` | `data/CAM_01.mp4` | Skincare zone tracking |

Expected local layout:

```text
store-intelligence/
└── data/
    ├── Brigade_Bangalore_10_April_26.csv
    ├── CAM_01.mp4
    ├── CAM_02.mp4
    ├── CAM_03.mp4
    └── CAM_05.mp4
```

## Quickstart: API + Dashboard

From the repository root:

```bash
docker compose up --build
```

This starts:

| Service | URL |
|---|---|
| FastAPI API | http://localhost:8000 |
| Streamlit Dashboard | http://localhost:8501 |

The API container mounts `./data` to `/app/data` and attempts to seed POS transactions from:

```text
/app/data/Brigade_Bangalore_10_April_26.csv
```

## Verify API Health

Open:

```text
http://localhost:8000/health
```

Expected response:

```json
{
  "status": "healthy"
}
```

## Verify Metrics Endpoint

Open:

```text
http://localhost:8000/stores/ST1008/metrics
```

Before the CV pipeline sends events, the response may show zero visitors and zero conversions.

## Run the CV Pipeline

The CV pipeline is intentionally run on the host machine in the current implementation. This avoids Docker GPU/OpenCV/PyTorch instability and keeps the API/dashboard Docker startup reliable.

Open a second terminal.

From the repository root:

```bash
python -m venv venv
source venv/bin/activate        # Windows: .\venv\Scripts\activate
pip install -r cv_pipeline/requirements.txt
cd cv_pipeline
python orchestrator.py
```

Important: run `python orchestrator.py` from inside the `cv_pipeline/` directory. The video paths in `orchestrator.py` are relative paths such as `../data/CAM_03.mp4`.

As the CV pipeline runs, it posts event batches to:

```text
http://127.0.0.1:8000/events/ingest
```

The dashboard at `http://localhost:8501` refreshes every 5 seconds and should show visitor/funnel counts increasing as events are ingested.

## Implemented API Endpoints

| Method | Endpoint | Status | Purpose |
|---|---|---|---|
| GET | `/health` | Implemented | Basic liveness check |
| POST | `/events/ingest` | Implemented | Batch event ingestion, max 500 events |
| GET | `/stores/{store_id}/metrics` | Implemented | Visitors, conversions, conversion rate |
| GET | `/stores/{store_id}/funnel` | Implemented | Entry → billing → purchase funnel and queue abandonment |

## Not Yet Implemented

| Requirement | Status |
|---|---|
| `/stores/{store_id}/heatmap` | Not implemented |
| `/stores/{store_id}/anomalies` | Not implemented |
| Full challenge metadata schema | Partially implemented only |
| `REENTRY` event generation | Not implemented |
| Cross-camera Re-ID | Not implemented |
| `BILLING_QUEUE_ABANDON` event emission | Not emitted; abandonment is calculated in `/funnel` |
| Automated tests | Not implemented |
| Structured JSON logging | Not implemented |
| Full one-command CV containerization | Not implemented; CV runs on host |

## Current Event Schema

The current event schema is a flattened schema:

```json
{
  "event_id": "uuid-string",
  "store_id": "ST1008",
  "camera_id": "CAM_ENTRANCE",
  "visitor_id": "VIS_1",
  "timestamp": "2026-04-10T12:00:00Z",
  "event_type": "ENTRY",
  "zone_id": null,
  "dwell_ms": null,
  "is_staff": false,
  "confidence": 0.91
}
```

The challenge-required nested `metadata` object is planned for the next milestone but is not part of the current code.

## Notes for Reviewers

- `cv_pipeline/orchestrator.py` is the final CV entrypoint.
- `cv_pipeline/worker.py` is deprecated draft code and should be ignored.
- SQLite is used for simplicity and reliable local execution.
- The dashboard is hardcoded to store `ST1008`.
- The current implementation prioritizes end-to-end execution and conversion-rate visibility over full Re-ID and advanced anomaly logic.
