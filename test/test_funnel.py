# PROMPT:
# Write a pytest test for a retail funnel endpoint verifying that an empty store
# returns safe zero values and no divide-by-zero errors.
#
# HUMAN CHANGES:
# Updated assertions to match the event-derived queue funnel response from
# Milestone 8.

def test_funnel_empty_store_returns_zero_safe_response(client):
    response = client.get("/stores/ST1008/funnel")

    assert response.status_code == 200

    data = response.json()

    assert data["store_id"] == "ST1008"

    assert data["funnel_steps"]["1_entered_store"] == 0
    assert data["funnel_steps"]["2_entered_billing_queue"] == 0
    assert data["funnel_steps"]["3_completed_purchase"] == 0

    assert data["insights"]["queue_abandonment_count"] == 0
    assert data["insights"]["queue_abandonment_rate"] == 0.0
    assert data["insights"]["avg_queue_wait_ms"] == 0.0
    assert data["insights"]["completed_queue_cycles"] == 0
    assert data["insights"]["current_queue_depth"] == 0
    assert data["insights"]["queue_data_source"] == "event_stream"