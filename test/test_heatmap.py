# PROMPT:
# Write a pytest test for a zone heatmap endpoint verifying safe no-data output
# before any ZONE_ENTER or ZONE_DWELL events are ingested.
#
# HUMAN CHANGES:
# Adjusted expected response to match the implemented zone-level heatmap schema.

def test_heatmap_empty_store_returns_no_data(client):
    response = client.get("/stores/ST1008/heatmap")

    assert response.status_code == 200

    data = response.json()

    assert data["store_id"] == "ST1008"
    assert data["heatmap_type"] == "zone_level"
    assert data["data_confidence"] == "NO_DATA"
    assert data["zones"] == []