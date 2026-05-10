from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.domain.entities.session import Session as SessionEntity


def _phonation_payload(score: int, parent_id: str) -> dict:
    now = datetime.now(timezone.utc)
    return {
        "started_at": now.isoformat(),
        "ended_at": (now + timedelta(minutes=1)).isoformat(),
        "score": score,
        "metrics": {
            "avg_hz": 145.0,
            "stability_score": 80,
            "breaks_count": 0,
            "exercises_count": 1,
        },
        "exercises": [
            {
                "exercise_type": "holding",
                "avg_hz": 145.0,
                "stability_score": 80,
                "breaks_count": 0,
                "in_range_pct": 90,
            }
        ],
        "parent_id": parent_id,
    }


async def test_full_live_composition(client, session_cleanup, db):
    """Start a live, attach two phonation children, finalize, verify score."""

    start = await client.post("/live/sessions")
    assert start.status_code == 201
    live_id = start.json()["session_id"]

    c1 = await client.post("/phonation/sessions", json=_phonation_payload(80, live_id))
    c2 = await client.post("/phonation/sessions", json=_phonation_payload(60, live_id))
    assert c1.status_code == 201
    assert c2.status_code == 201

    finalize = await client.post(f"/live/sessions/{live_id}/finalize")
    assert finalize.status_code == 200
    body = finalize.json()
    assert body["status"] == "completed"
    assert body["children_count"] == 2
    # Avg of the two completed children: (80 + 60) / 2 = 70
    assert body["score"] == 70

    detail = await client.get(f"/live/sessions/{live_id}")
    assert detail.status_code == 200
    detail_body = detail.json()
    assert detail_body["status"] == "completed"
    assert detail_body["score"] == 70
    assert detail_body["metrics"]["stop_reason"] == "completed"
    assert len(detail_body["children"]) == 2
    assert {child["module"] for child in detail_body["children"]} == {"phonation"}


async def test_finalize_on_completed_returns_409(client, session_cleanup):
    start = await client.post("/live/sessions")
    live_id = start.json()["session_id"]

    first = await client.post(f"/live/sessions/{live_id}/finalize")
    assert first.status_code == 200

    second = await client.post(f"/live/sessions/{live_id}/finalize")
    assert second.status_code == 409


async def test_abandon_with_user_stop(client, session_cleanup, db):
    start = await client.post("/live/sessions")
    live_id = start.json()["session_id"]

    abandon = await client.patch(
        f"/live/sessions/{live_id}/abandon",
        json={"stop_reason": "user_stop"},
    )
    assert abandon.status_code == 204

    detail = await client.get(f"/live/sessions/{live_id}")
    assert detail.json()["status"] == "aborted"
    assert detail.json()["metrics"]["stop_reason"] == "user_stop"


async def test_abandon_rejects_completed_stop_reason(client, session_cleanup):
    """The schema layer must block 'completed' on the abandon endpoint;
    that value is reserved for finalize."""

    start = await client.post("/live/sessions")
    live_id = start.json()["session_id"]

    response = await client.patch(
        f"/live/sessions/{live_id}/abandon",
        json={"stop_reason": "completed"},
    )
    assert response.status_code == 422


async def test_finalize_with_no_children_yields_null_score(client, session_cleanup):
    start = await client.post("/live/sessions")
    live_id = start.json()["session_id"]

    finalize = await client.post(f"/live/sessions/{live_id}/finalize")
    assert finalize.status_code == 200
    assert finalize.json()["score"] is None
    assert finalize.json()["children_count"] == 0
