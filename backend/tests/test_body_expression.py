from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.presentation.schemas.body_expression import (
    BodyExpressionMetricsInput,
    BodyExpressionSessionCreate,
)
from app.use_cases.body_expression.sessions import derive_body_expression_score


def _metrics(**overrides) -> dict:
    data = {
        "posture_score": 80,
        "openness_score": 70,
        "gesture_score": 60,
        "stability_score": 90,
        "energy_score": 50,
        "framing_score": 100,
        "tracked_pct": 85,
        "hands_visible_pct": 75,
        "excessive_movement_pct": 10,
        "calibration_quality_pct": 88,
        "framing_mode": "upper_body",
    }
    data.update(overrides)
    return data


def test_body_expression_score_uses_canonical_weights():
    metrics = BodyExpressionMetricsInput.model_validate(_metrics())
    assert derive_body_expression_score(metrics) == 73


def test_rejects_low_tracking_pct():
    with pytest.raises(ValidationError):
        BodyExpressionMetricsInput.model_validate(_metrics(tracked_pct=39))


def test_rejects_short_session():
    now = datetime.now(timezone.utc)
    with pytest.raises(ValidationError):
        BodyExpressionSessionCreate.model_validate(
            {
                "started_at": now.isoformat(),
                "ended_at": (now + timedelta(seconds=19)).isoformat(),
                "metrics": _metrics(),
            }
        )


async def test_create_body_expression_session_endpoint(client, session_cleanup, monkeypatch):
    async def no_ai_feedback(prompt: str, metrics: dict[str, object]):
        return None

    monkeypatch.setattr(
        "app.use_cases.body_expression.sessions.generate_body_expression_feedback",
        no_ai_feedback,
    )

    now = datetime.now(timezone.utc)
    response = await client.post(
        "/body-expression/sessions",
        json={
            "started_at": now.isoformat(),
            "ended_at": (now + timedelta(seconds=30)).isoformat(),
            "prompt_text": "Presenta una idea breve.",
            "metrics": _metrics(),
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "completed"
    assert body["score"] == 73
    assert body["metrics"]["framing_mode"] == "upper_body"
    assert body["feedback"]["source"] == "rules"
