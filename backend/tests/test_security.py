import logging

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.config import Settings
from app.main import create_app
from app.security import MAX_BODY_BYTES, RedactTokenFilter

SITE = "https://cotest.ssenu.cloud"


@pytest.fixture
def strict_client(tmp_path):
    settings = Settings("pw", "s", tmp_path / "data", allowed_origins=(SITE,))
    with TestClient(create_app(settings)) as c:
        yield c


def test_security_headers(client):
    r = client.get("/api/health")
    assert "default-src 'self'" in r.headers["content-security-policy"]
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["referrer-policy"] == "same-origin"
    assert r.headers["x-frame-options"] == "DENY"


def test_foreign_origin_rejected_on_writes(strict_client):
    r = strict_client.post("/api/admin/login", json={"password": "pw"}, headers={"origin": "https://evil.example"})
    assert r.status_code == 403
    assert r.json()["detail"] == "허용되지 않은 출처입니다."
    ok = strict_client.post("/api/admin/login", json={"password": "pw"}, headers={"origin": SITE})
    assert ok.status_code == 200
    # Origin이 없는 요청(같은 출처 GET, 서버 간 호출)은 통과
    assert strict_client.get("/api/admin/me").status_code == 200


def test_no_allowed_origins_means_no_check(client):
    r = client.post("/api/admin/login", json={"password": "pw"}, headers={"origin": "http://localhost:5173"})
    assert r.status_code == 200


def test_foreign_origin_websocket_closed(strict_client):
    # 출처 검사는 회차·인증 확인보다 먼저 한다
    strict_client.post("/api/admin/login", json={"password": "pw"}, headers={"origin": SITE})
    cookie = strict_client.cookies.get("admin_session")
    with strict_client.websocket_connect(
        "/ws/runs/1", headers={"cookie": f"admin_session={cookie}", "origin": "https://evil.example"}
    ) as ws:
        with pytest.raises(WebSocketDisconnect) as closed:
            ws.receive_json()
    assert closed.value.code == 4403


def test_too_large_body_rejected(client):
    r = client.post(
        "/api/admin/login",
        content=b"x",
        headers={"content-length": str(MAX_BODY_BYTES + 1), "content-type": "application/json"},
    )
    assert r.status_code == 413


def test_token_redacted_from_logs():
    record = logging.LogRecord(
        "uvicorn.access", logging.INFO, __file__, 1,
        '%s - "%s %s HTTP/%s" %d', ("1.2.3.4:5", "GET", "/ws/runs/1?token=SECRET", "1.1", 101), None,
    )
    assert RedactTokenFilter().filter(record) is True
    assert "SECRET" not in record.getMessage()
    assert "/ws/runs/1" in record.getMessage()
    plain = logging.LogRecord("uvicorn.access", logging.INFO, __file__, 1, "%s", ("/api/x?page=2",), None)
    RedactTokenFilter().filter(plain)
    assert plain.getMessage() == "/api/x?page=2"
