from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone


def _payload(parent_id: str | None = None) -> dict:
    now = datetime.now(timezone.utc)
    body = {
        "started_at": now.isoformat(),
        "ended_at": (now + timedelta(minutes=2)).isoformat(),
        "score": 85,
        "metrics": {
            "avg_hz": 145.0,
            "stability_score": 88,
            "breaks_count": 1,
            "exercises_count": 2,
        },
        "exercises": [
            {
                "exercise_type": "holding",
                "avg_hz": 142.0,
                "stability_score": 90,
                "breaks_count": 0,
                "in_range_pct": 95,
            },
            {
                "exercise_type": "gliding",
                "avg_hz": 148.0,
                "stability_score": 86,
                "breaks_count": 1,
                "in_range_pct": 80,
            },
        ],
    }
    if parent_id is not None:
        body["parent_id"] = parent_id
    return body


async def test_create_standalone_phonation_session(client, session_cleanup):
    response = await client.post("/phonation/sessions", json=_payload())
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "completed"
    assert body["score"] == 85
    assert body["duration_ms"] == 120000
    assert len(body["exercises"]) == 2
    # Exercises come back in enum-definition order (holding, gliding)
    assert [e["exercise_type"] for e in body["exercises"]] == ["holding", "gliding"]


async def test_list_sessions_excludes_live_children(client, session_cleanup):
    """A phonation session created with parent_id must NOT appear in the
    standalone list endpoint, only in the live's children. The list is
    explicitly filtered by parent_id IS NULL."""

    live = await client.post("/live/sessions")
    live_id = live.json()["session_id"]

    standalone = await client.post("/phonation/sessions", json=_payload())
    nested = await client.post("/phonation/sessions", json=_payload(parent_id=live_id))
    assert standalone.status_code == 201
    assert nested.status_code == 201

    listed = await client.get("/phonation/sessions")
    assert listed.status_code == 200
    ids = [item["id"] for item in listed.json()]
    assert standalone.json()["id"] in ids
    assert nested.json()["id"] not in ids


async def test_get_unknown_session_returns_404(client, session_cleanup):
    response = await client.get(f"/phonation/sessions/{uuid.uuid4()}")
    assert response.status_code == 404


async def test_create_with_invalid_parent_id_returns_422(client, session_cleanup):
    response = await client.post(
        "/phonation/sessions",
        json=_payload(parent_id=str(uuid.uuid4())),
    )
    assert response.status_code == 422


async def test_pydantic_invariants_reject_payload(client, session_cleanup):
    """exercises_count must equal len(exercises). Pydantic catches it before
    the use_case runs, so the response is 422 with the validator message."""

    payload = _payload()
    payload["metrics"]["exercises_count"] = 99
    response = await client.post("/phonation/sessions", json=payload)
    assert response.status_code == 422
