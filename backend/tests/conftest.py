import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def settings(tmp_path):
    return Settings(admin_password="pw", secret_key="test-secret", data_dir=tmp_path / "data")


@pytest.fixture
def app(settings):
    return create_app(settings)


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


@pytest.fixture
def admin_client(client):
    r = client.post("/api/admin/login", json={"password": "pw"})
    assert r.status_code == 200, r.text
    return client
