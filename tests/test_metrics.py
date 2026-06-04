# PROMPT:
# Write pytest tests for the store metrics endpoint verifying safe empty-state
# behavior and business metric completeness.
#
# HUMAN CHANGES:
# Added queue abandonment fields and product-zone dwell filtering tests.

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
    assert data["queue_abandonment_count"] == 0
    assert data["queue_abandonment_rate"] == 0.0
    assert data["completed_queue_cycles"] == 0
    assert data["abandoned_queue_cycles"] == 0
    assert data["avg_dwell_ms_by_zone"] == {}
    assert data["total_events"] == 0
    assert data["last_event_timestamp"] is None


def test_metrics_include_queue_abandonment_fields(client, sample_event):
    entry_event = sample_event(
        event_id="40000000-0000-4000-8000-000000000001",
        event_type="ENTRY",
        visitor_id="VIS_METRICS_ABANDON_1",
        timestamp="2026-04-10T10:00:00Z",
    )

    queue_join_event = sample_event(
        event_id="40000000-0000-4000-8000-000000000002",
        event_type="BILLING_QUEUE_JOIN",
        visitor_id="VIS_METRICS_ABANDON_1",
        zone_id="BILLING_QUEUE",
        queue_depth=1,
        timestamp="2026-04-10T10:05:00Z",
    )

    queue_abandon_event = sample_event(
        event_id="40000000-0000-4000-8000-000000000003",
        event_type="BILLING_QUEUE_ABANDON",
        visitor_id="VIS_METRICS_ABANDON_1",
        zone_id="BILLING_QUEUE",
        timestamp="2026-04-10T10:07:00Z",
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

    metrics_response = client.get("/stores/ST1008/metrics")

    assert metrics_response.status_code == 200

    data = metrics_response.json()

    assert data["total_visitors"] == 1
    assert data["current_queue_depth"] == 0
    assert data["avg_queue_wait_ms"] == 120000.0
    assert data["queue_abandonment_count"] == 1
    assert data["queue_abandonment_rate"] == 100.0
    assert data["completed_queue_cycles"] == 0
    assert data["abandoned_queue_cycles"] == 1


def test_metrics_exclude_non_product_zones_from_dwell(client, sample_event):
    events = [
        sample_event(
            event_id="40000000-0000-4000-8000-000000000011",
            event_type="ENTRY",
            visitor_id="VIS_METRICS_DWELL_1",
            timestamp="2026-04-10T11:00:00Z",
        ),
        sample_event(
            event_id="40000000-0000-4000-8000-000000000012",
            event_type="ZONE_DWELL",
            visitor_id="VIS_METRICS_DWELL_1",
            zone_id="ENTRY_DOOR",
            sku_zone="ENTRY_DOOR",
            dwell_ms=90000,
            timestamp="2026-04-10T11:01:30Z",
        ),
        sample_event(
            event_id="40000000-0000-4000-8000-000000000013",
            event_type="ZONE_DWELL",
            visitor_id="VIS_METRICS_DWELL_1",
            zone_id="BILLING_QUEUE",
            sku_zone="BILLING_QUEUE",
            dwell_ms=60000,
            timestamp="2026-04-10T11:02:00Z",
        ),
        sample_event(
            event_id="40000000-0000-4000-8000-000000000014",
            event_type="ZONE_DWELL",
            visitor_id="VIS_METRICS_DWELL_1",
            zone_id="MAKEUP",
            sku_zone="MAKEUP",
            dwell_ms=30000,
            timestamp="2026-04-10T11:02:30Z",
        ),
    ]

    response = client.post(
        "/events/ingest",
        json={"events": events},
    )

    assert response.status_code == 202
    assert response.json()["processed_count"] == 4

    metrics_response = client.get("/stores/ST1008/metrics")

    assert metrics_response.status_code == 200

    data = metrics_response.json()

    assert "ENTRY_DOOR" not in data["avg_dwell_ms_by_zone"]
    assert "BILLING_QUEUE" not in data["avg_dwell_ms_by_zone"]
    assert data["avg_dwell_ms_by_zone"]["MAKEUP"] == 30000.0