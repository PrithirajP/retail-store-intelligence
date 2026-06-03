# PROMPT:
# Write pytest tests for a store analytics funnel that must follow
# Entry -> Zone Visit -> Billing Queue -> Completed Purchase while remaining
# safe for empty stores and backward-compatible with older response keys.
#
# HUMAN CHANGES:
# Added regression tests for the updated multi-store baseline architecture.
# Tests verify zone-visit funnel stage, queue abandonment event handling, and
# store isolation across multiple stores.

def test_funnel_counts_entry_zone_queue_and_purchase_stages(client, sample_event):
    entry_event = sample_event(
        event_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1",
        event_type="ENTRY",
        visitor_id="VIS_FUNNEL_1",
        timestamp="2026-04-10T10:00:00Z",
    )

    zone_event = sample_event(
        event_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa2",
        event_type="ZONE_ENTER",
        visitor_id="VIS_FUNNEL_1",
        zone_id="MAKEUP",
        sku_zone="MAKEUP",
        timestamp="2026-04-10T10:01:00Z",
    )

    queue_join_event = sample_event(
        event_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa3",
        event_type="BILLING_QUEUE_JOIN",
        visitor_id="VIS_FUNNEL_1",
        zone_id="BILLING_QUEUE",
        queue_depth=1,
        timestamp="2026-04-10T10:05:00Z",
    )

    queue_exit_event = sample_event(
        event_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa4",
        event_type="BILLING_QUEUE_EXIT",
        visitor_id="VIS_FUNNEL_1",
        zone_id="BILLING_QUEUE",
        timestamp="2026-04-10T10:06:00Z",
    )

    response = client.post(
        "/events/ingest",
        json={
            "events": [
                entry_event,
                zone_event,
                queue_join_event,
                queue_exit_event,
            ]
        },
    )

    assert response.status_code == 202
    assert response.json()["processed_count"] == 4

    funnel_response = client.get("/stores/ST1008/funnel")

    assert funnel_response.status_code == 200

    data = funnel_response.json()

    assert data["funnel_steps"]["1_entered_store"] == 1
    assert data["funnel_steps"]["2_visited_zone"] == 1
    assert data["funnel_steps"]["3_entered_billing_queue"] == 1

    # No POS transaction is seeded in the test DB, so purchase remains zero.
    assert data["funnel_steps"]["4_completed_purchase"] == 0

    # Backward-compatible keys should still exist.
    assert data["funnel_steps"]["2_entered_billing_queue"] == 1
    assert data["funnel_steps"]["3_completed_purchase"] == 0

    assert data["insights"]["completed_queue_cycles"] == 1
    assert data["insights"]["current_queue_depth"] == 0
    assert data["insights"]["avg_queue_wait_ms"] == 60000.0


def test_funnel_counts_billing_queue_abandon_event(client, sample_event):
    entry_event = sample_event(
        event_id="bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb1",
        event_type="ENTRY",
        visitor_id="VIS_ABANDON_1",
        timestamp="2026-04-10T11:00:00Z",
    )

    queue_join_event = sample_event(
        event_id="bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb2",
        event_type="BILLING_QUEUE_JOIN",
        visitor_id="VIS_ABANDON_1",
        zone_id="BILLING_QUEUE",
        queue_depth=3,
        timestamp="2026-04-10T11:05:00Z",
    )

    queue_abandon_event = sample_event(
        event_id="bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb3",
        event_type="BILLING_QUEUE_ABANDON",
        visitor_id="VIS_ABANDON_1",
        zone_id="BILLING_QUEUE",
        timestamp="2026-04-10T11:07:00Z",
    )

    response = client.post(
        "/events/ingest",
        json={
            "events": [
                entry_event,
                queue_join_event,
                queue_abandon_event,
            ]
        },
    )

    assert response.status_code == 202
    assert response.json()["processed_count"] == 3

    funnel_response = client.get("/stores/ST1008/funnel")

    assert funnel_response.status_code == 200

    data = funnel_response.json()

    assert data["funnel_steps"]["1_entered_store"] == 1
    assert data["funnel_steps"]["3_entered_billing_queue"] == 1
    assert data["funnel_steps"]["4_completed_purchase"] == 0

    assert data["insights"]["abandoned_queue_cycles"] == 1
    assert data["insights"]["completed_queue_cycles"] == 0
    assert data["insights"]["queue_abandonment_count"] == 1
    assert data["insights"]["queue_abandonment_rate"] == 100.0
    assert data["insights"]["current_queue_depth"] == 0
    assert data["insights"]["avg_queue_wait_ms"] == 120000.0


def test_funnel_is_store_scoped(client, sample_event):
    st1008_entry = sample_event(
        event_id="cccccccc-cccc-4ccc-8ccc-ccccccccccc1",
        event_type="ENTRY",
        visitor_id="VIS_STORE_SCOPE_1",
        timestamp="2026-04-10T12:00:00Z",
    )

    other_store_entry = sample_event(
        event_id="cccccccc-cccc-4ccc-8ccc-ccccccccccc2",
        event_type="ENTRY",
        visitor_id="VIS_STORE_SCOPE_2",
        timestamp="2026-04-10T12:00:00Z",
    )
    other_store_entry["store_id"] = "STORE_BLR_002"

    response = client.post(
        "/events/ingest",
        json={"events": [st1008_entry, other_store_entry]},
    )

    assert response.status_code == 202
    assert response.json()["processed_count"] == 2

    st1008_funnel = client.get("/stores/ST1008/funnel").json()
    other_store_funnel = client.get("/stores/STORE_BLR_002/funnel").json()

    assert st1008_funnel["funnel_steps"]["1_entered_store"] == 1
    assert other_store_funnel["funnel_steps"]["1_entered_store"] == 1