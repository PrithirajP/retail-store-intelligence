# PROMPT:
# Write a pytest test for a rule-based anomaly endpoint verifying that an empty
# store returns OK and does not trigger false anomalies.
#
# HUMAN CHANGES:
# Matched assertions to the Milestone 9 anomaly response with status and
# anomalies list.

def test_anomalies_empty_store_returns_ok(client):
    response = client.get("/stores/ST1008/anomalies")

    assert response.status_code == 200

    data = response.json()

    assert data["store_id"] == "ST1008"
    assert data["status"] == "OK"
    assert data["anomalies"] == []