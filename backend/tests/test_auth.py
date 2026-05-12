from __future__ import annotations

from config import settings


async def test_login_returns_token_and_user(anon_client):
    """Happy path: dev creds yield 200 with token + user dto."""

    response = await anon_client.post(
        "/auth/login",
        json={
            "email": settings.dev_user_email,
            "password": settings.dev_user_password,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["user"]["email"] == settings.dev_user_email
    assert body["user"]["is_active"] is True


async def test_login_with_wrong_password_returns_401(anon_client):
    response = await anon_client.post(
        "/auth/login",
        json={
            "email": settings.dev_user_email,
            "password": "this-is-wrong",
        },
    )
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "invalid_credentials"


async def test_protected_endpoint_without_token_returns_403(anon_client):
    """FastAPI's HTTPBearer raises 403 (not 401) when the header is absent.
    Documenting the actual behavior so a future change is intentional."""

    response = await anon_client.get("/phonation/sessions")
    assert response.status_code == 403
