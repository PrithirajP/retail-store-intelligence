# PROMPT:
# Write pytest tests to verify that a FastAPI event ingestion endpoint can accept
# challenge sample_events.jsonl-style events and normalize them into the internal
# canonical Event Schema before validation and persistence.
#
# HUMAN CHANGES:
# Adapted event payloads to the newly observed challenge sample format using
# id_token, store_code, event_timestamp, zone_entered, queue_completed, and
# queue_abandoned. Assertions verify that normalization preserves partial-success
# behavior and does not break canonical ingestion.

def test_ingest_accepts_sample_entry_event(client):
    sample_event = {
        "event_type": "entry",
        "id_token": "VIS_SAMPLE_001",
        "store_code": "store_1076",
        "camera_id": "cam1",
        "event_timestamp": "2026-03-03T14:22:10Z",
        "is_staff": False,
        "gender_pred": "unknown",
        "age_bucket": "unknown",
        "group_id": "grp_1",
        "group_size": 1,
        "is_face_hidden": True,
    }

    response = client.post(
        "/events/ingest",
        json={"events": [sample_event]},
    )

    assert response.status_code == 202

    data = response.json()

    assert data["status"] == "success"
    assert data["received_count"] == 1
    assert data["processed_count"] == 1
    assert data["duplicate_count"] == 0
    assert data["error_count"] == 0


def test_ingest_accepts_sample_zone_event(client):
    sample_event = {
        "event_type": "zone_entered",
        "track_id": "TRK_123",
        "store_id": "ST1076",
        "camera_id": "CAM_MAIN_01",
        "zone_id": "ZONE_SKINCARE",
        "zone_name": "SKINCARE",
        "zone_type": "revenue",
        "is_revenue_zone": True,
        "event_time": "2026-03-03T14:23:10Z",
        "zone_hotspot_x": 120,
        "zone_hotspot_y": 340,
        "gender": "unknown",
        "age_bucket": "unknown",
    }

    response = client.post(
        "/events/ingest",
        json={"events": [sample_event]},
    )

    assert response.status_code == 202

    data = response.json()

    assert data["status"] == "success"
    assert data["received_count"] == 1
    assert data["processed_count"] == 1
    assert data["duplicate_count"] == 0
    assert data["error_count"] == 0


def test_ingest_accepts_sample_queue_completed_event(client):
    sample_event = {
        "queue_event_id": "QUEUE_SAMPLE_001",
        "event_type": "queue_completed",
        "track_id": "TRK_QUEUE_1",
        "store_id": "ST1076",
        "camera_id": "CAM_BILLING_01",
        "zone_id": "BILLING_COUNTER_QUEUE",
        "zone_name": "Billing Counter Queue",
        "zone_type": "billing",
        "is_revenue_zone": False,
        "queue_join_ts": "2026-03-03T14:24:00Z",
        "queue_served_ts": "2026-03-03T14:26:00Z",
        "queue_exit_ts": "2026-03-03T14:26:20Z",
        "wait_seconds": 120,
        "queue_position_at_join": 3,
        "abandoned": False,
        "zone_hotspot_x": 300,
        "zone_hotspot_y": 450,
        "gender": "unknown",
        "age_bucket": "unknown",
    }

    response = client.post(
        "/events/ingest",
        json={"events": [sample_event]},
    )

    assert response.status_code == 202

    data = response.json()

    assert data["status"] == "success"
    assert data["received_count"] == 1
    assert data["processed_count"] == 1
    assert data["duplicate_count"] == 0
    assert data["error_count"] == 0


def test_ingest_accepts_sample_queue_abandoned_event(client):
    sample_event = {
        "queue_event_id": "QUEUE_SAMPLE_002",
        "event_type": "queue_abandoned",
        "track_id": "TRK_QUEUE_2",
        "store_id": "ST1076",
        "camera_id": "CAM_BILLING_01",
        "zone_id": "BILLING_COUNTER_QUEUE",
        "zone_name": "Billing Counter Queue",
        "zone_type": "billing",
        "is_revenue_zone": False,
        "queue_join_ts": "2026-03-03T14:30:00Z",
        "queue_exit_ts": "2026-03-03T14:31:10Z",
        "wait_seconds": 70,
        "queue_position_at_join": 5,
        "abandoned": True,
        "zone_hotspot_x": 320,
        "zone_hotspot_y": 470,
        "gender": "unknown",
        "age_bucket": "unknown",
    }

    response = client.post(
        "/events/ingest",
        json={"events": [sample_event]},
    )

    assert response.status_code == 202

    data = response.json()

    assert data["status"] == "success"
    assert data["received_count"] == 1
    assert data["processed_count"] == 1
    assert data["duplicate_count"] == 0
    assert data["error_count"] == 0


def test_sample_event_normalization_preserves_partial_success(client):
    valid_sample_event = {
        "event_type": "entry",
        "id_token": "VIS_SAMPLE_002",
        "store_code": "store_1076",
        "camera_id": "cam1",
        "event_timestamp": "2026-03-03T14:22:10Z",
        "is_staff": False,
    }

    invalid_sample_event = {
        "event_type": "zone_entered",
        "store_id": "ST1076",
        "camera_id": "CAM_MAIN_01",
        # Missing track_id / id_token / visitor_id intentionally
        "zone_id": "ZONE_SKINCARE",
        "event_time": "2026-03-03T14:23:10Z",
    }

    response = client.post(
        "/events/ingest",
        json={"events": [valid_sample_event, invalid_sample_event]},
    )

    assert response.status_code == 202

    data = response.json()

    assert data["status"] == "partial_success"
    assert data["received_count"] == 2
    assert data["processed_count"] == 1
    assert data["duplicate_count"] == 0
    assert data["error_count"] == 1
    assert data["errors"] is not None