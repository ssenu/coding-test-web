from tests.graphs import parking_graph_dict
from tests.helpers import create_template


def test_requires_admin(client):
    assert client.get("/api/templates").status_code == 401


def test_create_valid_template(admin_client):
    t = create_template(admin_client)
    assert t["valid"] is True
    assert t["issues"] == []
    assert [x["name"] for x in admin_client.get("/api/templates").json()] == ["주차장"]


def test_empty_template_is_saved_but_invalid(admin_client):
    r = admin_client.post("/api/templates", json={"name": "빈 시험장"})
    assert r.status_code == 201
    body = r.json()
    assert body["valid"] is False
    assert body["issues"] == [{"message": "박스가 하나도 없습니다.", "box_ids": []}]


def test_update_reports_issues_with_box_ids(admin_client):
    t = create_template(admin_client)
    graph = parking_graph_dict()
    graph["boxes"].append({"id": "x", "type": "common", "title": "x", "config": {}})
    r = admin_client.put(f"/api/templates/{t['id']}", json={"name": "주차장 v2", "graph": graph})
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "주차장 v2"
    assert body["valid"] is False
    assert body["issues"] == [{"message": "결과 박스까지 이어지지 않는 박스가 있습니다.", "box_ids": ["x"]}]


def test_malformed_graph_is_an_issue_not_a_crash(admin_client):
    r = admin_client.post("/api/templates", json={"name": "깨짐", "graph": {"boxes": [{"id": "x"}]}})
    assert r.status_code == 201
    assert r.json()["issues"] == [{"message": "박스에 id와 type이 필요합니다.", "box_ids": []}]


def test_duplicate_and_delete(admin_client):
    t = create_template(admin_client)
    admin_client.post(f"/api/templates/{t['id']}/files", data={"box_id": "story"}, files={"file": ("안내.txt", b"hello")})
    clone = admin_client.post(f"/api/templates/{t['id']}/duplicate").json()
    assert clone["name"] == "주차장 사본"
    assert clone["valid"] is True
    clone_files = admin_client.get(f"/api/templates/{clone['id']}/files").json()
    assert [f["filename"] for f in clone_files] == ["안내.txt"]
    assert admin_client.delete(f"/api/templates/{t['id']}").status_code == 204
    assert admin_client.get(f"/api/templates/{t['id']}").status_code == 404
    r = admin_client.get(f"/api/templates/{clone['id']}/files/{clone_files[0]['id']}")
    assert r.content == b"hello"


def test_upload_download_delete_file(admin_client):
    t = create_template(admin_client)
    r = admin_client.post(
        f"/api/templates/{t['id']}/files", data={"box_id": "a"}, files={"file": ("../../evil name.py", b"x = 1\n")}
    )
    assert r.status_code == 201
    f = r.json()
    assert f["filename"] == "evil name.py"
    assert f["size"] == 6
    got = admin_client.get(f"/api/templates/{t['id']}/files/{f['id']}")
    assert got.content == b"x = 1\n"
    assert admin_client.delete(f"/api/templates/{t['id']}/files/{f['id']}").status_code == 204
    assert admin_client.get(f"/api/templates/{t['id']}/files").json() == []


def test_upload_too_large(admin_client):
    t = create_template(admin_client)
    big = b"0" * (10 * 1024 * 1024 + 1)
    r = admin_client.post(f"/api/templates/{t['id']}/files", data={"box_id": "a"}, files={"file": ("big.bin", big)})
    assert r.status_code == 413
    assert admin_client.get(f"/api/templates/{t['id']}/files").json() == []
