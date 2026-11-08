from app.auth import check_admin_cookie, hash_token, make_admin_cookie, new_token
from app.config import Settings


def test_cookie_signed_with_secret(tmp_path):
    a = Settings("pw", "secret-a", tmp_path)
    b = Settings("pw", "secret-b", tmp_path)
    cookie = make_admin_cookie(a)
    assert check_admin_cookie(a, cookie)
    assert not check_admin_cookie(b, cookie)
    assert not check_admin_cookie(a, None)
    assert not check_admin_cookie(a, "garbage")


def test_token_hash_is_stable_and_tokens_unique():
    t1, t2 = new_token(), new_token()
    assert t1 != t2
    assert hash_token(t1) == hash_token(t1)
    assert len(hash_token(t1)) == 64


def test_login_wrong_password(client):
    r = client.post("/api/admin/login", json={"password": "nope"})
    assert r.status_code == 401
    assert client.get("/api/admin/me").status_code == 401


def test_login_logout(client):
    assert client.post("/api/admin/login", json={"password": "pw"}).status_code == 200
    assert client.get("/api/admin/me").json() == {"admin": True}
    client.post("/api/admin/logout")
    assert client.get("/api/admin/me").status_code == 401
