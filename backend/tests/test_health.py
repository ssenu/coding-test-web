from pathlib import Path

import pytest

from app.config import load_settings


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_load_settings_requires_env(monkeypatch):
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    monkeypatch.delenv("SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError):
        load_settings()


def test_load_settings_reads_env(monkeypatch, tmp_path):
    monkeypatch.setenv("ADMIN_PASSWORD", "a")
    monkeypatch.setenv("SECRET_KEY", "b")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("COOKIE_SECURE", "1")
    s = load_settings()
    assert (s.admin_password, s.secret_key, s.data_dir, s.cookie_secure) == ("a", "b", Path(tmp_path), True)


def test_load_settings_web_and_origins(monkeypatch, tmp_path):
    monkeypatch.setenv("ADMIN_PASSWORD", "a")
    monkeypatch.setenv("SECRET_KEY", "b")
    monkeypatch.setenv("WEB_DIST", str(tmp_path))
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://cotest.ssenu.cloud/, http://localhost:5173")
    s = load_settings()
    assert s.web_dist == Path(tmp_path)
    assert s.allowed_origins == ("https://cotest.ssenu.cloud", "http://localhost:5173")
    monkeypatch.delenv("WEB_DIST")
    monkeypatch.delenv("ALLOWED_ORIGINS")
    s = load_settings()
    assert (s.web_dist, s.allowed_origins) == (None, ())
