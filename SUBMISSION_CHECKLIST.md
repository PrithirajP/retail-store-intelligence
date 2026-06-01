# SUBMISSION_CHECKLIST.md

This checklist tracks the current project state against the challenge acceptance gate and scoring areas.

## 1. Acceptance Gate

| Gate Item | Current Status | Notes |
|---|---:|---|
| `docker compose up` starts API | Yes | `store-api` service exists |
| `docker compose up` starts dashboard | Yes | `store-dashboard` service exists |
| API health endpoint responds | Yes | `GET /health` returns `{"status":"healthy"}` |
| Metrics endpoint responds | Yes | `GET /stores/ST1008/metrics` implemented |
| Event ingestion endpoint exists | Yes | `POST /events/ingest` implemented |
| Detection pipeline produces events | Yes, host-side | Run `cd cv_pipeline && python orchestrator.py` |
| README exists | Yes, added in Milestone 1 | Must remain accurate |
| DESIGN.md exists | Yes, added in Milestone 1 | Includes AI-Assisted Decisions |
| CHOICES.md exists | Yes, added in Milestone 1 | Includes major trade-offs |

## 2. Required Data Files

Before review, ensure this local structure exists:

```text
data/
├── Brigade_Bangalore_10_April_26.csv
├── CAM_01.mp4
├── CAM_02.mp4
├── CAM_03.mp4
└── CAM_05.mp4
```

## 3. Run Commands

### Start API and dashboard

```bash
docker compose up --build
```

### Start CV pipeline

```bash
python -m venv venv
source venv/bin/activate
pip install -r cv_pipeline/requirements.txt
cd cv_pipeline
python orchestrator.py
```

## 4. URLs to Verify

| URL | Expected |
|---|---|
| http://localhost:8000/health | JSON health response |
| http://localhost:8000/stores/ST1008/metrics | Metrics JSON |
| http://localhost:8000/stores/ST1008/funnel | Funnel JSON |
| http://localhost:8501 | Streamlit dashboard |

## 5. Implemented Features

| Feature | Status |
|---|---:|
| YOLOv8n person detection | Implemented |
| ByteTrack local tracking | Implemented |
| Manual polygon zone mapping | Implemented |
| Entry detection through `ENTRY_DOOR` polygon | Partially implemented |
| Billing queue join/exit | Implemented |
| Behind-counter staff heuristic | Implemented |
| Event ingestion | Implemented |
| Event idempotency by `event_id` | Implemented |
| POS seeding from CSV | Implemented |
| POS correlation within 5-minute window | Implemented |
| Metrics endpoint | Implemented |
| Funnel endpoint | Implemented |
| Streamlit dashboard | Implemented |

## 6. Known Missing Features

| Feature | Current Status | Planned Milestone |
|---|---:|---|
| Full event metadata schema | Missing | Milestone 2 |
| Persist full event fields | Missing | Milestone 3 |
| `/heatmap` endpoint | Missing | Milestone 7 |
| `/anomalies` endpoint | Missing | Milestone 9 |
| Detailed `/health` stale-feed data | Missing | Milestone 5 |
| Tests and prompt blocks | Missing | Milestone 11 |
| Structured JSON logging | Missing | Milestone 10 |
| Re-entry detection | Missing | Milestone 14 |
| Cross-camera Re-ID | Missing | Future work |
| Full CV Docker worker | Missing | Milestone 13 optional profile |

## 7. Pre-Submission Manual Validation

Run this sequence before submission:

```bash
docker compose down -v
docker compose up --build
```

In another terminal:

```bash
cd cv_pipeline
python orchestrator.py
```

Check:

- API does not crash.
- POS data seeds successfully or logs a clear warning.
- CV logs show frame processing.
- Event emitter logs successful batches.
- `/metrics` returns non-error JSON.
- Dashboard loads at port 8501.
- Dashboard values update after CV events are sent.

## 8. Reviewer Communication Notes

Be prepared to explain:

1. Why YOLOv8n was chosen over heavier detectors.
2. Why ByteTrack is local-only and Re-ID is missing.
3. Why CV runs outside Docker in the current milestone.
4. Why event schema is flattened in the current version.
5. Why SQLite was chosen for challenge reliability.
6. Why tests are still missing and what the first tests would cover.
