# PROMPT:
# Write pytest tests for rule-based anomaly detection in a retail analytics API.
# Cover queue spike, conversion drop, and dead zone anomaly conditions.
#
# HUMAN CHANGES:
# Adapted tests to the current anomaly endpoint and event-derived queue logic.
# Tests check for presence of anomaly types rather than relying on only one
# overall status, because multiple rules can trigger at the same time.

def _get_anomaly_by_type(anomalies, anomaly_type):
    for anomaly in anomalies:
        if anomaly.get("type") == anomaly_type:
            return anomaly

    return None


def test_anomalies_detect_queue_spike(client, sample_event):
    events = []

    for i in range(5):
        visitor_id = f"VIS_QUEUE_SPIKE_{i}"

        events.append(
            sample_event(
                event_id=f"20000000-0000-4000-8000-00000000000{i}",
                event_type="BILLING_QUEUE_JOIN",
                visitor_id=visitor_id,
                zone_id="BILLING_QUEUE",
                queue_depth=i + 1,
                timestamp=f"2026-04-10T12:0{i}:00Z",
            )
        )

    ingest_response = client.post(
        "/events/ingest",
        json={"events": events},
    )

    assert ingest_response.status_code == 202
    assert ingest_response.json()["processed_count"] == 5

    response = client.get("/stores/ST1008/anomalies")

    assert response.status_code == 200

    data = response.json()
    anomaly = _get_anomaly_by_type(
        data["anomalies"],
        "BILLING_QUEUE_SPIKE",
    )

    assert anomaly is not None
    assert anomaly["severity"] in {"WARN", "CRITICAL"}
    assert anomaly["evidence"]["current_queue_depth"] == 5


def test_anomalies_detect_conversion_drop(client, sample_event):
    events = []

    for i in range(5):
        events.append(
            sample_event(
                event_id=f"21000000-0000-4000-8000-00000000000{i}",
                event_type="ENTRY",
                visitor_id=f"VIS_CONV_DROP_{i}",
                timestamp=f"2026-04-10T13:0{i}:00Z",
            )
        )

    ingest_response = client.post(
        "/events/ingest",
        json={"events": events},
    )

    assert ingest_response.status_code == 202
    assert ingest_response.json()["processed_count"] == 5

    response = client.get("/stores/ST1008/anomalies")

    assert response.status_code == 200

    data = response.json()
    anomaly = _get_anomaly_by_type(
        data["anomalies"],
        "CONVERSION_DROP",
    )

    assert anomaly is not None
    assert anomaly["severity"] == "CRITICAL"
    assert anomaly["evidence"]["total_visitors"] == 5
    assert anomaly["evidence"]["current_conversion_rate_percentage"] == 0.0


def test_anomalies_detect_dead_zones_after_enough_events(client, sample_event):
    events = []

    for i in range(20):
        events.append(
            sample_event(
                event_id=f"22000000-0000-4000-8000-0000000000{i:02d}",
                event_type="ENTRY",
                visitor_id=f"VIS_DEAD_ZONE_{i}",
                timestamp=f"2026-04-10T14:{i:02d}:00Z",
            )
        )

    ingest_response = client.post(
        "/events/ingest",
        json={"events": events},
    )

    assert ingest_response.status_code == 202
    assert ingest_response.json()["processed_count"] == 20

    response = client.get("/stores/ST1008/anomalies")

    assert response.status_code == 200

    data = response.json()

    dead_zone_anomalies = [
        anomaly
        for anomaly in data["anomalies"]
        if anomaly.get("type") == "DEAD_ZONE"
    ]

    dead_zone_ids = {
        anomaly["evidence"]["zone_id"]
        for anomaly in dead_zone_anomalies
    }

    assert "MAKEUP" in dead_zone_ids
    assert "SKINCARE" in dead_zone_ids