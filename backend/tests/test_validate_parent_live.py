from __future__ import annotations

import uuid

import pytest

from app.domain.entities.enums import ModuleEnum, SessionStatusEnum
from app.domain.entities.session import Session as SessionEntity
from app.use_cases.live.sessions import (
    InvalidParentLiveError,
    start_live_session,
    validate_parent_live_session,
)


async def test_accepts_active_live_owned_by_user(db, dev_user, session_cleanup):
    live = await start_live_session(db, dev_user)
    await validate_parent_live_session(db, dev_user, live.id)


async def test_rejects_unknown_parent_id(db, dev_user, session_cleanup):
    with pytest.raises(InvalidParentLiveError):
        await validate_parent_live_session(db, dev_user, uuid.uuid4())


async def test_rejects_non_live_module(db, dev_user, session_cleanup):
    """A row that exists but has module != 'live' must not pass."""

    from datetime import datetime, timezone

    fake_phonation = SessionEntity(
        user_id=dev_user.id,
        module=ModuleEnum.phonation,
        parent_id=None,
        started_at=datetime.now(timezone.utc),
        ended_at=datetime.now(timezone.utc),
        duration_ms=1000,
        score=80,
        status=SessionStatusEnum.completed,
    )
    db.add(fake_phonation)
    await db.commit()
    await db.refresh(fake_phonation)

    with pytest.raises(InvalidParentLiveError):
        await validate_parent_live_session(db, dev_user, fake_phonation.id)


async def test_rejects_completed_live(db, dev_user, session_cleanup):
    """An already-completed live session cannot accept new children."""

    from datetime import datetime, timezone

    closed_live = SessionEntity(
        user_id=dev_user.id,
        module=ModuleEnum.live,
        parent_id=None,
        started_at=datetime.now(timezone.utc),
        ended_at=datetime.now(timezone.utc),
        duration_ms=1000,
        score=70,
        status=SessionStatusEnum.completed,
    )
    db.add(closed_live)
    await db.commit()
    await db.refresh(closed_live)

    with pytest.raises(InvalidParentLiveError):
        await validate_parent_live_session(db, dev_user, closed_live.id)
