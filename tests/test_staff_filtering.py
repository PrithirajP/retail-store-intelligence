# PROMPT:
# Write pytest tests to verify that staff events are excluded from customer
# analytics in a retail store intelligence API.
#
# HUMAN CHANGES:
# Adapted tests to the implemented is_staff flag and existing analytics
# endpoints. Tests verify that staff are excluded from metrics, funnel, and
# heatmap outputs while events themselves can still be ingested.

def test_staff_entries_are_excluded_from_metrics_and_funnel(client, sample_event):
    staff_entry = sample_event(
        event_id="30000000-0000-4000-8000-000000000001",
        event_type="ENTRY",
        visitor_id="VIS_STAFF_1",
        is_staff=True,
        timestamp="2026-04-10T15:00:00Z",
    )

    staff_queue_join = sample_event(
        event_id="30000000-0000-4000-8000-000000000002",
        event_type="BILLING_QUEUE_JOIN",
        visitor_id="VIS_STAFF_1",
        zone_id="BILLING_QUEUE",
        is_staff=True,
        timestamp="2026-04-10T15:01:00Z",
    )

    response = client.post(
        "/events/ingest",
        json={"events": [staff_entry, staff_queue_join]},
    )

    assert response.status_code == 202
    assert response.json()["processed_count"] == 2

    metrics_response = client.get("/stores/ST1008/metrics")
    assert metrics_response.status_code == 200

    metrics = metrics_response.json()

    assert metrics["total_visitors"] == 0
    assert metrics["converted_visitors"] == 0
    assert metrics["conversion_rate_percentage"] == 0.0
    assert metrics["current_queue_depth"] == 0

    funnel_response = client.get("/stores/ST1008/funnel")
    assert funnel_response.status_code == 200

    funnel = funnel_response.json()

    assert funnel["funnel_steps"]["1_entered_store"] == 0
    assert funnel["funnel_steps"]["2_visited_zone"] == 0
    assert funnel["funnel_steps"]["3_entered_billing_queue"] == 0
    assert funnel["funnel_steps"]["4_completed_purchase"] == 0


def test_staff_zone_events_are_excluded_from_heatmap(client, sample_event):
    staff_zone_enter = sample_event(
        event_id="30000000-0000-4000-8000-000000000011",
        event_type="ZONE_ENTER",
        visitor_id="VIS_STAFF_ZONE_1",
        zone_id="MAKEUP",
        sku_zone="MAKEUP",
        is_staff=True,
        timestamp="2026-04-10T16:00:00Z",
    )

    staff_zone_dwell = sample_event(
        event_id="30000000-0000-4000-8000-000000000012",
        event_type="ZONE_DWELL",
        visitor_id="VIS_STAFF_ZONE_1",
        zone_id="MAKEUP",
        sku_zone="MAKEUP",
        dwell_ms=60000,
        is_staff=True,
        timestamp="2026-04-10T16:01:00Z",
    )

    response = client.post(
        "/events/ingest",
        json={"events": [staff_zone_enter, staff_zone_dwell]},
    )

    assert response.status_code == 202
    assert response.json()["processed_count"] == 2

    heatmap_response = client.get("/stores/ST1008/heatmap")
    assert heatmap_response.status_code == 200

    heatmap = heatmap_response.json()

    assert heatmap["store_id"] == "ST1008"
    assert heatmap["data_confidence"] == "NO_DATA"
    assert heatmap["zones"] == []

    metrics_response = client.get("/stores/ST1008/metrics")
    assert metrics_response.status_code == 200

    metrics = metrics_response.json()

    assert metrics["avg_dwell_ms_by_zone"] == {}