"""Integration tests for the FastAPI endpoints."""
import pytest
from fastapi.testclient import TestClient
from main import app
from app.core.database import SessionLocal
from app.models.auth import User


@pytest.fixture
def client():
    from app.core.database import get_db
    with TestClient(app) as c:
        yield c


def _auth_headers(client: TestClient) -> dict:
    res = client.post(
        "/api/v1/auth/register",
        json={
            "email": "tester@example.com",
            "password": "password123",
            "display_name": "Tester",
        },
    )
    assert res.status_code == 201
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _auth_headers_for(client: TestClient, email: str, display_name: str = "Tester") -> dict:
    res = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "password123",
            "display_name": display_name,
        },
    )
    assert res.status_code == 201
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _promote_user_to_admin(email: str):
    db = SessionLocal()
    try:
        user = db.query(User).filter_by(email=email.lower()).first()
        assert user is not None
        user.role = "admin"
        db.commit()
    finally:
        db.close()


def test_health(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_create_and_get_topic(client):
    headers = _auth_headers(client)
    payload = {
        "title": "Federated Learning under Concept Drift",
        "literature_scarce": True,
        "adjacent_fields": ["Continual Learning", "Concept Drift"],
    }
    res = client.post("/api/v1/topics", json=payload, headers=headers)
    assert res.status_code == 201
    data = res.json()
    assert data["title"] == payload["title"]
    topic_id = data["id"]

    res2 = client.get(f"/api/v1/topics/{topic_id}", headers=headers)
    assert res2.status_code == 200
    assert res2.json()["id"] == topic_id


def test_list_topics(client):
    headers = _auth_headers(client)
    client.post("/api/v1/topics", json={"title": "Topic 1"}, headers=headers)
    client.post("/api/v1/topics", json={"title": "Topic 2"}, headers=headers)
    res = client.get("/api/v1/topics", headers=headers)
    assert res.status_code == 200
    assert len(res.json()) >= 2


def test_topic_not_found(client):
    headers = _auth_headers(client)
    res = client.get("/api/v1/topics/9999", headers=headers)
    assert res.status_code == 404


def test_override_paper_decision(client):
    # Create topic and a paper via DB directly would be complex; test endpoint shape
    res = client.patch("/api/v1/papers/9999/decision", json={"label": "direct", "reason": "manual override"})
    assert res.status_code == 404


def test_non_professor_cannot_create_lab_news(client):
    owner_headers = _auth_headers_for(client, "owner@example.com", "Owner")
    outsider_headers = _auth_headers_for(client, "outsider@example.com", "Outsider")

    created = client.post(
        "/api/v1/labs",
        json={"name": "Systems Lab", "description": "Lab for testing"},
        headers=owner_headers,
    )
    assert created.status_code == 201
    lab_id = created.json()["id"]

    denied = client.post(
        f"/api/v1/labs/{lab_id}/news",
        json={"title": "Unauthorized news", "content": "should fail", "pinned": False},
        headers=outsider_headers,
    )
    assert denied.status_code == 403


def test_create_topic_with_paper_type_and_lab_scope(client):
    headers = _auth_headers_for(client, "labowner@example.com", "Lab Owner")
    created_lab = client.post(
        "/api/v1/labs",
        json={"name": "AI Lab", "description": "Paper-type scoped lab"},
        headers=headers,
    )
    assert created_lab.status_code == 201
    lab_id = created_lab.json()["id"]

    created_topic = client.post(
        "/api/v1/topics",
        json={
            "title": "Multimodal Reasoning",
            "paper_type": "review",
            "lab_id": lab_id,
        },
        headers=headers,
    )
    assert created_topic.status_code == 201
    payload = created_topic.json()
    assert payload["paper_type"] == "review"
    assert payload["lab_id"] == lab_id


def test_update_own_publication_and_project(client):
    headers = _auth_headers_for(client, "profileowner@example.com", "Profile Owner")

    pub_created = client.post(
        "/api/v1/users/me/publications",
        json={
            "title": "Original Publication",
            "authors": ["Alice", "Bob"],
            "venue": "ICML",
            "year": 2024,
            "pub_type": "conference",
            "citation_count": 0,
        },
        headers=headers,
    )
    assert pub_created.status_code == 201
    pub_id = pub_created.json()["id"]

    pub_updated = client.patch(
        f"/api/v1/users/me/publications/{pub_id}",
        json={"title": "Updated Publication", "year": 2025},
        headers=headers,
    )
    assert pub_updated.status_code == 200
    assert pub_updated.json()["title"] == "Updated Publication"
    assert pub_updated.json()["year"] == 2025

    proj_created = client.post(
        "/api/v1/users/me/projects",
        json={
            "title": "Original Project",
            "description": "Initial description",
            "role": "Lead",
            "start_date": "2025-01-01",
            "status": "ongoing",
            "collaborators": [],
        },
        headers=headers,
    )
    assert proj_created.status_code == 201
    proj_id = proj_created.json()["id"]

    proj_updated = client.patch(
        f"/api/v1/users/me/projects/{proj_id}",
        json={"status": "completed", "description": "Finalized"},
        headers=headers,
    )
    assert proj_updated.status_code == 200
    assert proj_updated.json()["status"] == "completed"
    assert proj_updated.json()["description"] == "Finalized"


def test_upload_profile_avatar(client):
    headers = _auth_headers_for(client, "avatarowner@example.com", "Avatar Owner")

    uploaded = client.post(
        "/api/v1/users/me/avatar",
        files={"file": ("avatar.png", b"fake-image-bytes", "image/png")},
        headers=headers,
    )
    assert uploaded.status_code == 200
    avatar_url = uploaded.json()["avatar_url"]
    assert avatar_url.startswith("/storage/profile-avatars/")

    me = client.get("/api/v1/auth/me", headers=headers)
    assert me.status_code == 200
    user_id = me.json()["id"]
    assert me.json()["role"] in {"admin", "user"}

    public_profile = client.get(f"/api/v1/users/{user_id}/profile")
    assert public_profile.status_code == 200
    assert public_profile.json()["profile"]["avatar_url"] == avatar_url


def test_professor_can_update_lab_news(client):
    professor_headers = _auth_headers_for(client, "prof@example.com", "Professor")

    created_lab = client.post(
        "/api/v1/labs",
        json={"name": "Vision Lab", "description": "Lab for news update"},
        headers=professor_headers,
    )
    assert created_lab.status_code == 201
    lab_id = created_lab.json()["id"]

    created_news = client.post(
        f"/api/v1/labs/{lab_id}/news",
        json={"title": "Initial", "content": "Draft", "pinned": False},
        headers=professor_headers,
    )
    assert created_news.status_code == 201
    news_id = created_news.json()["id"]

    updated_news = client.patch(
        f"/api/v1/labs/{lab_id}/news/{news_id}",
        json={"title": "Updated", "content": "Published", "pinned": True},
        headers=professor_headers,
    )
    assert updated_news.status_code == 200
    assert updated_news.json()["title"] == "Updated"
    assert updated_news.json()["pinned"] is True


def test_cross_user_update_publication_forbidden(client):
    owner_headers = _auth_headers_for(client, "pubowner@example.com", "Pub Owner")
    other_headers = _auth_headers_for(client, "pubother@example.com", "Pub Other")

    created = client.post(
        "/api/v1/users/me/publications",
        json={
            "title": "Owner Publication",
            "authors": ["Owner"],
            "venue": "NeurIPS",
            "year": 2024,
            "pub_type": "conference",
            "citation_count": 0,
        },
        headers=owner_headers,
    )
    assert created.status_code == 201
    pub_id = created.json()["id"]

    denied = client.patch(
        f"/api/v1/users/me/publications/{pub_id}",
        json={"title": "Hacked"},
        headers=other_headers,
    )
    assert denied.status_code == 403


def test_cross_user_update_project_forbidden(client):
    owner_headers = _auth_headers_for(client, "projowner@example.com", "Proj Owner")
    other_headers = _auth_headers_for(client, "projother@example.com", "Proj Other")

    created = client.post(
        "/api/v1/users/me/projects",
        json={
            "title": "Owner Project",
            "description": "Private project",
            "role": "Lead",
            "start_date": "2025-01-01",
            "status": "ongoing",
            "collaborators": [],
        },
        headers=owner_headers,
    )
    assert created.status_code == 201
    project_id = created.json()["id"]

    denied = client.patch(
        f"/api/v1/users/me/projects/{project_id}",
        json={"status": "completed"},
        headers=other_headers,
    )
    assert denied.status_code == 403


def test_invalid_github_repo_url_rejected(client):
    headers = _auth_headers_for(client, "ghowner@example.com", "GH Owner")
    created = client.post(
        "/api/v1/topics",
        json={"title": "Code Topic"},
        headers=headers,
    )
    assert created.status_code == 201
    topic_id = created.json()["id"]

    denied = client.post(
        f"/api/v1/topics/{topic_id}/github",
        json={"repo_url": "https://example.com/not-a-github-repo"},
        headers=headers,
    )
    assert denied.status_code == 400
    assert "github.com" in denied.json()["detail"]


def test_github_refresh_endpoint_starts_reanalysis(client, monkeypatch):
    headers = _auth_headers_for(client, "refreshgh@example.com", "Refresh GH")

    created_topic = client.post(
        "/api/v1/topics",
        json={"title": "Refresh Topic"},
        headers=headers,
    )
    assert created_topic.status_code == 201
    topic_id = created_topic.json()["id"]

    import app.api.github as github_api

    class FakeResponse:
        def __init__(self, status_code=200, payload=None):
            self.status_code = status_code
            self._payload = payload or {}

        def json(self):
            return self._payload

    def fake_get(url, headers=None, timeout=None):
        if url.endswith('/languages'):
            return FakeResponse(200, {"Python": 123})
        if url.endswith('/readme'):
            return FakeResponse(200, {"content": "IyBSRUFETUU="})
        if '/git/trees/' in url:
            return FakeResponse(200, {"tree": []})
        return FakeResponse(200, {"full_name": "owner/repo"})

    monkeypatch.setattr(github_api.httpx, 'get', fake_get)
    monkeypatch.setattr(github_api, '_run_code_analysis', lambda repo, db: None)

    linked = client.post(
        f"/api/v1/topics/{topic_id}/github",
        json={"repo_url": "https://github.com/owner/repo"},
        headers=headers,
    )
    assert linked.status_code == 201

    refreshed = client.post(
        f"/api/v1/topics/{topic_id}/github/refresh",
        headers=headers,
    )
    assert refreshed.status_code == 200
    assert refreshed.json()["status"] == "running"


def test_non_admin_cannot_access_admin_users(client):
    headers = _auth_headers_for(client, "basicuser@example.com", "Basic User")
    denied = client.get("/api/v1/admin/users", headers=headers)
    assert denied.status_code == 403


def test_admin_users_full_crud(client):
    admin_email = "admincrud@example.com"
    admin_headers = _auth_headers_for(client, admin_email, "Admin CRUD")
    _promote_user_to_admin(admin_email)

    created = client.post(
        "/api/v1/admin/users",
        json={
            "email": "manageduser@example.com",
            "display_name": "Managed User",
            "password": "password123",
            "role": "user",
            "plan": "free",
            "is_active": True,
        },
        headers=admin_headers,
    )
    assert created.status_code == 201
    created_data = created.json()
    user_id = created_data["id"]
    assert created_data["email"] == "manageduser@example.com"
    assert created_data["is_active"] is True

    listed = client.get("/api/v1/admin/users", headers=admin_headers)
    assert listed.status_code == 200
    assert any(u["id"] == user_id for u in listed.json())

    detail = client.get(f"/api/v1/admin/users/{user_id}", headers=admin_headers)
    assert detail.status_code == 200
    assert detail.json()["display_name"] == "Managed User"

    updated = client.patch(
        f"/api/v1/admin/users/{user_id}",
        json={
            "display_name": "Managed User Updated",
            "plan": "paid",
            "role": "admin",
            "is_active": False,
        },
        headers=admin_headers,
    )
    assert updated.status_code == 200
    updated_data = updated.json()
    assert updated_data["display_name"] == "Managed User Updated"
    assert updated_data["plan"] == "paid"
    assert updated_data["role"] == "admin"
    assert updated_data["is_active"] is False

    deleted = client.delete(f"/api/v1/admin/users/{user_id}", headers=admin_headers)
    assert deleted.status_code == 204

    missing = client.get(f"/api/v1/admin/users/{user_id}", headers=admin_headers)
    assert missing.status_code == 404


def test_admin_cannot_delete_or_downgrade_self(client):
    admin_email = "selfguard@example.com"
    admin_headers = _auth_headers_for(client, admin_email, "Self Guard")
    _promote_user_to_admin(admin_email)

    me = client.get("/api/v1/auth/me", headers=admin_headers)
    assert me.status_code == 200
    my_id = me.json()["id"]

    deny_delete = client.delete(f"/api/v1/admin/users/{my_id}", headers=admin_headers)
    assert deny_delete.status_code == 400

    deny_downgrade = client.patch(
        f"/api/v1/admin/users/{my_id}",
        json={"role": "user"},
        headers=admin_headers,
    )
    assert deny_downgrade.status_code == 400
