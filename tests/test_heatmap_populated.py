# PROMPT:
# Write pytest tests for populated heatmap behavior in a retail analytics API.
# Verify that ZONE_ENTER and ZONE_DWELL events produce zone visit counts,
# average dwell values, heat scores, and metrics-level dwell summaries.
#
# HUMAN CHANGES:
# Adapted tests to the implemented Event Schema v1.2 and the current
# zone-level heatmap endpoint. Tests use deterministic event IDs and validate
# business-facing analytics rather than raw model output.

def test_heatmap_returns_populated_zone_scores(client, sample_event):
    events = [
        sample_event(
            event_id="10000000-0000-4000-8000-000000000001",
            event_type="ENTRY",
            visitor_id="VIS_HEAT_1",
            timestamp="2026-04-10T10:00:00Z",
        ),
        sample_event(
            event_id="10000000-0000-4000-8000-000000000002",
            event_type="ZONE_ENTER",
            visitor_id="VIS_HEAT_1",
            zone_id="MAKEUP",
            sku_zone="MAKEUP",
            timestamp="2026-04-10T10:01:00Z",
        ),
        sample_event(
            event_id="10000000-0000-4000-8000-000000000003",
            event_type="ZONE_DWELL",
            visitor_id="VIS_HEAT_1",
            zone_id="MAKEUP",
            sku_zone="MAKEUP",
            dwell_ms=30000,
            timestamp="2026-04-10T10:01:30Z",
        ),
        sample_event(
            event_id="10000000-0000-4000-8000-000000000004",
            event_type="ENTRY",
            visitor_id="VIS_HEAT_2",
            timestamp="2026-04-10T10:02:00Z",
        ),
        sample_event(
            event_id="10000000-0000-4000-8000-000000000005",
            event_type="ZONE_ENTER",
            visitor_id="VIS_HEAT_2",
            zone_id="SKINCARE",
            sku_zone="SKINCARE",
            timestamp="2026-04-10T10:03:00Z",
        ),
        sample_event(
            event_id="10000000-0000-4000-8000-000000000006",
            event_type="ZONE_DWELL",
            visitor_id="VIS_HEAT_2",
            zone_id="SKINCARE",
            sku_zone="SKINCARE",
            dwell_ms=15000,
            timestamp="2026-04-10T10:03:15Z",
        ),
    ]

    ingest_response = client.post(
        "/events/ingest",
        json={"events": events},
    )

    assert ingest_response.status_code == 202
    assert ingest_response.json()["processed_count"] == 6

    response = client.get("/stores/ST1008/heatmap")

    assert response.status_code == 200

    data = response.json()

    assert data["store_id"] == "ST1008"
    assert data["heatmap_type"] == "zone_level"
    assert data["data_confidence"] in {"LOW", "MEDIUM", "HIGH"}

    zones = data["zones"]

    assert len(zones) == 2

    zone_by_id = {zone["zone_id"]: zone for zone in zones}

    assert "MAKEUP" in zone_by_id
    assert "SKINCARE" in zone_by_id

    assert zone_by_id["MAKEUP"]["visit_count"] == 1
    assert zone_by_id["MAKEUP"]["avg_dwell_ms"] == 30000.0
    assert zone_by_id["MAKEUP"]["heat_score"] > 0

    assert zone_by_id["SKINCARE"]["visit_count"] == 1
    assert zone_by_id["SKINCARE"]["avg_dwell_ms"] == 15000.0
    assert zone_by_id["SKINCARE"]["heat_score"] > 0


def test_metrics_include_average_dwell_by_zone(client, sample_event):
    events = [
        sample_event(
            event_id="10000000-0000-4000-8000-000000000011",
            event_type="ENTRY",
            visitor_id="VIS_DWELL_1",
            timestamp="2026-04-10T11:00:00Z",
        ),
        sample_event(
            event_id="10000000-0000-4000-8000-000000000012",
            event_type="ZONE_ENTER",
            visitor_id="VIS_DWELL_1",
            zone_id="MAKEUP",
            sku_zone="MAKEUP",
            timestamp="2026-04-10T11:01:00Z",
        ),
        sample_event(
            event_id="10000000-0000-4000-8000-000000000013",
            event_type="ZONE_DWELL",
            visitor_id="VIS_DWELL_1",
            zone_id="MAKEUP",
            sku_zone="MAKEUP",
            dwell_ms=20000,
            timestamp="2026-04-10T11:01:20Z",
        ),
        sample_event(
            event_id="10000000-0000-4000-8000-000000000014",
            event_type="ZONE_DWELL",
            visitor_id="VIS_DWELL_1",
            zone_id="MAKEUP",
            sku_zone="MAKEUP",
            dwell_ms=40000,
            timestamp="2026-04-10T11:01:40Z",
        ),
    ]

    ingest_response = client.post(
        "/events/ingest",
        json={"events": events},
    )

    assert ingest_response.status_code == 202
    assert ingest_response.json()["processed_count"] == 4

    response = client.get("/stores/ST1008/metrics")

    assert response.status_code == 200

    data = response.json()

    assert data["avg_dwell_ms_by_zone"]["MAKEUP"] == 30000.0