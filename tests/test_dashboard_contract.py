from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_APP = PROJECT_ROOT / "dashboard" / "app.py"


def test_dashboard_supports_final_store_selector():
    content = DASHBOARD_APP.read_text(encoding="utf-8")

    assert "ST1008" in content
    assert "STORE_2" in content
    assert "selectbox" in content


def test_dashboard_calls_required_api_endpoints():
    content = DASHBOARD_APP.read_text(encoding="utf-8")

    assert '"/health"' in content
    assert '"/stores/{selected_store}/metrics"' in content
    assert '"/stores/{selected_store}/funnel"' in content
    assert '"/stores/{selected_store}/heatmap"' in content
    assert '"/stores/{selected_store}/anomalies"' in content


def test_dashboard_uses_environment_api_base_url():
    content = DASHBOARD_APP.read_text(encoding="utf-8")

    assert 'os.getenv("API_BASE_URL"' in content
    assert "http://store-api:8000" in content