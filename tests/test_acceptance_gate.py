# PROMPT:
# Write pytest tests for the challenge acceptance gate requirements.
# Verify that the required store metrics endpoint returns valid JSON for
# STORE_BLR_002 even when no events exist for that store.
#
# HUMAN CHANGES:
# Added checks for the updated multi-store baseline architecture. The tests
# verify that unknown or empty stores return safe zero-state responses instead
# of crashing or returning null values.

def test_acceptance_gate_store_blr_002_metrics_returns_valid_json(client):
    response = client.get("/stores/STORE_BLR_002/metrics")

    assert response.status_code == 200

    data = response.json()

    assert data["store_id"] == "STORE_BLR_002"
    assert data["total_visitors"] == 0
    assert data["converted_visitors"] == 0
    assert data["conversion_rate_percentage"] == 0.0
    assert data["current_queue_depth"] == 0
    assert data["avg_queue_wait_ms"] == 0.0
    assert data["avg_dwell_ms_by_zone"] == {}
    assert data["total_events"] == 0
    assert data["last_event_timestamp"] is None


def test_acceptance_gate_store_blr_002_funnel_returns_valid_json(client):
    response = client.get("/stores/STORE_BLR_002/funnel")

    assert response.status_code == 200

    data = response.json()

    assert data["store_id"] == "STORE_BLR_002"

    assert data["funnel_steps"]["1_entered_store"] == 0

    # New challenge-aligned funnel keys
    assert data["funnel_steps"]["2_visited_zone"] == 0
    assert data["funnel_steps"]["3_entered_billing_queue"] == 0
    assert data["funnel_steps"]["4_completed_purchase"] == 0

    # Backward-compatible keys
    assert data["funnel_steps"]["2_entered_billing_queue"] == 0
    assert data["funnel_steps"]["3_completed_purchase"] == 0

    assert data["insights"]["queue_abandonment_count"] == 0
    assert data["insights"]["queue_abandonment_rate"] == 0.0
    assert data["insights"]["avg_queue_wait_ms"] == 0.0
    assert data["insights"]["completed_queue_cycles"] == 0
    assert data["insights"]["current_queue_depth"] == 0
    assert data["insights"]["queue_data_source"] == "event_stream"


def test_acceptance_gate_store_blr_002_heatmap_returns_valid_json(client):
    response = client.get("/stores/STORE_BLR_002/heatmap")

    assert response.status_code == 200

    data = response.json()

    assert data["store_id"] == "STORE_BLR_002"
    assert data["heatmap_type"] == "zone_level"
    assert data["data_confidence"] == "NO_DATA"
    assert data["zones"] == []


def test_acceptance_gate_store_blr_002_anomalies_returns_valid_json(client):
    response = client.get("/stores/STORE_BLR_002/anomalies")

    assert response.status_code == 200

    data = response.json()

    assert data["store_id"] == "STORE_BLR_002"
    assert data["status"] == "OK"
    assert data["anomalies"] == []