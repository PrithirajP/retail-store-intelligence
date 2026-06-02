# PROMPT:
# Write a pytest test for the store metrics endpoint verifying safe empty-state
# behavior before any CV events have been ingested.
#
# HUMAN CHANGES:
# Included assertions for the expanded Milestone 6 metrics fields such as
# current_queue_depth, avg_queue_wait_ms, avg_dwell_ms_by_zone, and total_events.

def test_metrics_empty_store_returns_zero_values(client):
    response = client.get("/stores/ST1008/metrics")

    assert response.status_code == 200

    data = response.json()

    assert data["store_id"] == "ST1008"
    assert data["total_visitors"] == 0
    assert data["converted_visitors"] == 0
    assert data["conversion_rate_percentage"] == 0.0
    assert data["current_queue_depth"] == 0
    assert data["avg_queue_wait_ms"] == 0.0
    assert data["avg_dwell_ms_by_zone"] == {}
    assert data["total_events"] == 0
    assert data["last_event_timestamp"] is None