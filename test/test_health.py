# PROMPT:
# Write a pytest test for a FastAPI health endpoint that reports API status,
# database connectivity, and safe no-events startup behavior.
#
# HUMAN CHANGES:
# Adjusted assertions to match the implemented /health response shape,
# including database.status and NO_EVENTS_RECEIVED warning.

def test_health_returns_connected_database(client):
    response = client.get("/health")

    assert response.status_code == 200

    data = response.json()

    assert data["status"] == "healthy"
    assert data["database"]["status"] == "connected"
    assert "stores" in data
    assert "warnings" in data
    assert "NO_EVENTS_RECEIVED" in data["warnings"]