# PROMPT:
# Write pytest tests verifying graceful database degradation behavior.
#
# HUMAN CHANGES:
# Added tests for /health and analytics endpoint database failure handling.
# The API should return structured HTTP 503 responses and must not expose
# raw stack traces.

from sqlalchemy.exc import SQLAlchemyError


def test_health_database_failure_returns_structured_503(client, monkeypatch):
    def fake_database_health(_db):
        return {
            "status": "error",
            "error": "simulated database outage",
        }

    monkeypatch.setattr(
        "main._check_database_health",
        fake_database_health,
    )

    response = client.get("/health")

    assert response.status_code == 503

    data = response.json()

    assert data["status"] == "degraded"
    assert data["database"]["status"] == "error"
    assert "DATABASE_UNAVAILABLE" in data["warnings"]

    assert "Traceback" not in response.text
    assert "sqlalchemy" not in response.text.lower()


def test_metrics_database_failure_returns_structured_503(client, monkeypatch):
    def fake_conversion_stats(_db, _store_id):
        raise SQLAlchemyError("simulated database outage")

    monkeypatch.setattr(
        "main._get_conversion_stats",
        fake_conversion_stats,
    )

    response = client.get("/stores/ST1008/metrics")

    assert response.status_code == 503

    data = response.json()

    assert data["status"] == "degraded"
    assert data["error"] == "DATABASE_UNAVAILABLE"
    assert data["message"] == "Database operation failed. Please retry later."
    assert "trace_id" in data

    assert "Traceback" not in response.text
    assert "simulated database outage" not in response.text