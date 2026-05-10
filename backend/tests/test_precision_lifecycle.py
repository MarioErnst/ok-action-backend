from __future__ import annotations

import uuid

from sqlalchemy import select

from app.domain.entities.session import Session as SessionEntity
from app.domain.entities.enums import SessionStatusEnum
from app.use_cases.precision.sessions import (
    RoundAlreadyEvaluatedError,
    RoundIndexOutOfRangeError,
    evaluate_round,
    finalize_precision_session,
    start_precision_session,
)


def _good_eval(score: int) -> dict:
    return {
        "audio_intelligible": True,
        "relevance_score": score,
        "directness_score": score,
        "conciseness_score": score,
        "transcript": "",
        "feedback": "",
        "strengths": [],
        "improvement_areas": [],
    }


async def test_full_lifecycle_score_aggregation(db, dev_user, session_cleanup):
    """start -> 3 evaluate (one inintelligible) -> finalize -> verify score."""

    s, _, prompts = await start_precision_session(db, dev_user, rounds_total=3)
    pids = [p.id for p in prompts]

    r0 = await evaluate_round(db, dev_user, s.id, 0, pids[0], _good_eval(80))
    assert r0.score == 80

    bad = {**_good_eval(0), "audio_intelligible": False}
    r1 = await evaluate_round(db, dev_user, s.id, 1, pids[1], bad)
    assert r1.score is None

    r2 = await evaluate_round(db, dev_user, s.id, 2, pids[2], _good_eval(70))
    assert r2.score == 70

    fs, fm = await finalize_precision_session(db, dev_user, s.id)
    assert fs.status == SessionStatusEnum.completed
    # Avg of intelligible scores: (80 + 70) / 2 = 75
    assert fs.score == 75
    assert fm.rounds_completed == 3


async def test_round_index_out_of_range_rejected(db, dev_user, session_cleanup):
    import pytest

    s, _, prompts = await start_precision_session(db, dev_user, rounds_total=2)
    with pytest.raises(RoundIndexOutOfRangeError):
        await evaluate_round(db, dev_user, s.id, 999, prompts[0].id, _good_eval(70))


async def test_duplicate_round_index_rejected(dev_user, session_cleanup):
    """Open fresh sessions for each step instead of using the shared db
    fixture: evaluate_round's rollback on IntegrityError leaves the
    fixture session in a state that breaks pytest teardown
    (MissingGreenlet on pool pre-ping)."""

    import pytest

    from app.domain.entities.precision_metrics import PrecisionMetrics
    from app.infrastructure.db.session import async_session_factory

    async with async_session_factory() as setup_db:
        s, _, prompts = await start_precision_session(setup_db, dev_user, rounds_total=2)

    async with async_session_factory() as first_db:
        await evaluate_round(first_db, dev_user, s.id, 0, prompts[0].id, _good_eval(70))

    async with async_session_factory() as dup_db:
        with pytest.raises(RoundAlreadyEvaluatedError):
            await evaluate_round(dup_db, dev_user, s.id, 0, prompts[1].id, _good_eval(80))

    async with async_session_factory() as verify_db:
        metrics = (
            await verify_db.execute(
                select(PrecisionMetrics).where(PrecisionMetrics.session_id == s.id)
            )
        ).scalar_one()
        assert metrics.rounds_completed == 1
