# PROMPT:
# Write pytest tests for FastAPI event ingestion covering valid events,
# duplicate event idempotency, and partial success for malformed events.
#
# HUMAN CHANGES:
# Adapted payloads to Event Schema v1.2 with nested metadata. Assertions follow
# the implemented partial-success response fields.

def test_ingest_accepts_valid_event(client, sample_event):
    event = sample_event()

    response = client.post(
        "/events/ingest",
        json={"events": [event]},
    )

    assert response.status_code == 202

    data = response.json()

    assert data["status"] == "success"
    assert data["received_count"] == 1
    assert data["processed_count"] == 1
    assert data["duplicate_count"] == 0
    assert data["error_count"] == 0
    assert data["errors"] is None


def test_ingest_is_idempotent_for_duplicate_event_id(client, sample_event):
    event = sample_event(event_id="11111111-1111-4111-8111-111111111111")

    first_response = client.post(
        "/events/ingest",
        json={"events": [event]},
    )

    assert first_response.status_code == 202
    assert first_response.json()["processed_count"] == 1

    second_response = client.post(
        "/events/ingest",
        json={"events": [event]},
    )

    assert second_response.status_code == 202

    data = second_response.json()

    assert data["status"] == "duplicate_only"
    assert data["received_count"] == 1
    assert data["processed_count"] == 0
    assert data["duplicate_count"] == 1
    assert data["error_count"] == 0


def test_ingest_partial_success_for_malformed_event(client, sample_event):
    valid_event = sample_event(event_id="22222222-2222-4222-8222-222222222222")

    malformed_event = {
        "event_id": "33333333-3333-4333-8333-333333333333",
        "store_id": "ST1008",
        "camera_id": "CAM_TEST",
        # Missing visitor_id intentionally
        "timestamp": "2026-04-10T10:00:00Z",
        "event_type": "ENTRY",
        "is_staff": False,
        "confidence": 0.90,
    }

    response = client.post(
        "/events/ingest",
        json={"events": [valid_event, malformed_event]},
    )

    assert response.status_code == 202

    data = response.json()

    assert data["status"] == "partial_success"
    assert data["received_count"] == 2
    assert data["processed_count"] == 1
    assert data["duplicate_count"] == 0
    assert data["error_count"] == 1
    assert data["errors"] is not None
    assert data["errors"][0]["index"] == 1