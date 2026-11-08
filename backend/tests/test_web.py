import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def web_client(tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>app</html>", encoding="utf-8")
    (dist / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    (dist / "favicon.svg").write_text("<svg/>", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("nope", encoding="utf-8")
    settings = Settings("pw", "s", tmp_path / "data", web_dist=dist)
    with TestClient(create_app(settings)) as c:
        yield c


def test_index_and_spa_routes(web_client):
    for path in ("/", "/admin", "/admin/runs/3", "/run"):
        r = web_client.get(path)
        assert r.status_code == 200, path
        assert r.text == "<html>app</html>"
        assert r.headers["cache-control"] == "no-cache"


def test_static_files(web_client):
    assert web_client.get("/assets/app.js").text == "console.log(1)"
    assert web_client.get("/favicon.svg").text == "<svg/>"
    assert web_client.get("/assets/missing.js").status_code == 404


def test_api_paths_are_not_swallowed(web_client):
    assert web_client.get("/api/health").json() == {"ok": True}
    assert web_client.get("/api/nope").status_code == 404
    assert web_client.get("/ws").status_code == 404


def test_path_traversal_blocked(web_client):
    r = web_client.get("/..%2Fsecret.txt")
    assert "nope" not in r.text


def test_no_web_dist_means_no_spa(client):
    assert client.get("/").status_code == 404
