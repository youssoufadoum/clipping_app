from __future__ import annotations

import uuid

from fastapi.testclient import TestClient


def test_project_crud_search_and_pagination(client: TestClient, auth: dict[str, str]) -> None:
    for title in ["Podcast episode 12", "Webinar recap", "Podcast episode 13"]:
        resp = client.post("/api/v1/projects", json={"title": title}, headers=auth)
        assert resp.status_code == 201
        assert resp.json()["status"] == "draft"

    page = client.get("/api/v1/projects?page_size=2", headers=auth).json()
    assert page["total"] == 3 and len(page["items"]) == 2

    found = client.get("/api/v1/projects?q=podcast", headers=auth).json()
    assert {p["title"] for p in found["items"]} == {"Podcast episode 12", "Podcast episode 13"}
    # LIKE wildcards in search terms are escaped
    assert client.get("/api/v1/projects?q=%25", headers=auth).json()["total"] == 0

    pid = found["items"][0]["id"]
    renamed = client.patch(f"/api/v1/projects/{pid}", json={"title": "  Renamed  "}, headers=auth)
    assert renamed.json()["title"] == "Renamed"

    archived = client.patch(f"/api/v1/projects/{pid}", json={"archived": True}, headers=auth)
    assert archived.json()["status"] == "archived"
    assert client.get("/api/v1/projects", headers=auth).json()["total"] == 2
    assert client.get("/api/v1/projects?status=archived", headers=auth).json()["total"] == 1
    restored = client.patch(f"/api/v1/projects/{pid}", json={"archived": False}, headers=auth)
    assert restored.json()["status"] == "draft"

    assert client.delete(f"/api/v1/projects/{pid}", headers=auth).status_code == 204
    assert client.get(f"/api/v1/projects/{pid}", headers=auth).status_code == 404


def test_blank_title_rejected(client: TestClient, auth: dict[str, str]) -> None:
    assert client.post("/api/v1/projects", json={"title": "   "}, headers=auth).status_code == 422


def test_users_cannot_access_each_others_projects(
    client: TestClient, auth: dict[str, str], other_auth: dict[str, str]
) -> None:
    pid = client.post("/api/v1/projects", json={"title": "Private"}, headers=auth).json()["id"]
    for method, path, body in [
        ("get", f"/api/v1/projects/{pid}", None),
        ("patch", f"/api/v1/projects/{pid}", {"title": "pwned"}),
        ("delete", f"/api/v1/projects/{pid}", None),
        ("get", f"/api/v1/projects/{pid}/clips", None),
        ("get", f"/api/v1/projects/{pid}/media", None),
        ("get", f"/api/v1/projects/{pid}/jobs", None),
        (
            "post",
            f"/api/v1/projects/{pid}/uploads/initiate",
            {"filename": "a.mp4", "content_type": "video/mp4", "size_bytes": 10},
        ),
    ]:
        resp = client.request(method, path, json=body, headers=other_auth)
        assert resp.status_code == 404, (method, path, resp.status_code)
    assert client.get("/api/v1/projects", headers=other_auth).json()["total"] == 0
    assert client.get(f"/api/v1/projects/{pid}", headers=auth).json()["title"] == "Private"


def test_unknown_ids_are_404(client: TestClient, auth: dict[str, str]) -> None:
    rid = uuid.uuid4()
    for path in [f"/api/v1/projects/{rid}", f"/api/v1/clips/{rid}", f"/api/v1/jobs/{rid}"]:
        assert client.get(path, headers=auth).status_code == 404


def test_project_quota(client: TestClient, auth: dict[str, str], monkeypatch) -> None:
    from dataclasses import replace

    from app.core import plans

    monkeypatch.setitem(plans.PLANS, "free", replace(plans.PLANS["free"], max_projects=1))
    assert client.post("/api/v1/projects", json={"title": "a"}, headers=auth).status_code == 201
    resp = client.post("/api/v1/projects", json={"title": "b"}, headers=auth)
    assert resp.status_code == 402 and resp.json()["error"]["code"] == "QUOTA_EXCEEDED"
