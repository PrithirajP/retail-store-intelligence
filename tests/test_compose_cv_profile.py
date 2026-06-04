from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
COMPOSE_FILE = PROJECT_ROOT / "docker-compose.yml"
CV_DOCKERFILE = PROJECT_ROOT / "cv_pipeline" / "Dockerfile"


def test_compose_has_optional_cv_worker_profile():
    content = COMPOSE_FILE.read_text(encoding="utf-8")

    assert "cv-worker:" in content
    assert "profiles:" in content
    assert "- cv" in content
    assert 'API_URL: "http://store-api:8000/events/ingest"' in content
    assert "condition: service_healthy" in content


def test_cv_worker_mounts_data_directory():
    content = COMPOSE_FILE.read_text(encoding="utf-8")

    assert "./data:/app/data" in content


def test_cv_pipeline_has_dockerfile():
    assert CV_DOCKERFILE.exists()

    content = CV_DOCKERFILE.read_text(encoding="utf-8")

    assert "FROM python:3.12-slim" in content
    assert "pip install" in content
    assert 'CMD ["python", "orchestrator.py"]' in content