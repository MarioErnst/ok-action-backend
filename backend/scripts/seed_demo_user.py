"""Seed the demo user "Mario Jr" with 60 days of synthetic activity.

Idempotent: on a re-run the user row is preserved but every session of
this user is deleted (CASCADE wipes child metrics) before reinserting
fresh data. A fixed random seed makes the output reproducible across
runs.

Invoke from the backend directory:

    ./venv/bin/python -m scripts.seed_demo_user

Requires the same database environment as the app (Cloud SQL Connector
config in .env).
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from google.cloud.sql.connector import Connector
from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import Session as OrmSession

from app.domain.entities.enums import ModuleEnum, SessionStatusEnum
from app.domain.entities.role import Role
from app.domain.entities.session import Session
from app.domain.entities.user import User
from app.infrastructure.security.hashing import hash_password
from config import settings


# Demo identity for the recording. Read from settings so the credentials live
# in `.env` and not in source, but keep the previous baked-in values as a
# fallback so existing environments that haven't been updated still work.
DEMO_EMAIL = settings.demo_user_email or "mario@okaction.cl"
DEMO_PASSWORD = settings.demo_user_password or "Demo1234!"
DEMO_FULL_NAME = settings.demo_user_full_name or "Mario Jr"

# Span and shape of the activity we synthesize. 60 days back from "now"
# (UTC) gives the dashboard charts a meaningful sample once the demo runs.
NUM_DAYS = 60
AVG_DAILY_MINUTES = 26
DAILY_MINUTES_SIGMA = 9
SKIP_DAY_PROBABILITY = 0.12
MAX_SESSIONS_PER_DAY = 4

# Pick every module except `live`. Live is a composition wrapper that
# inherits its score from its children, so synthesizing standalone live
# sessions would distort the chart.
SEEDABLE_MODULES: list[ModuleEnum] = [m for m in ModuleEnum if m != ModuleEnum.live]

# "Talón de Aquiles" – linguistic_versatility ends noticeably lower than
# the other modules to show contrast on the per-module selector.
WEAK_MODULE = ModuleEnum.linguistic_versatility
WEAK_CURVE = (35, 65)

RANDOM_SEED = 42


def _get_sync_connection():
    """Match the connector setup used by app.infrastructure.db.seed."""
    connector = Connector()
    return connector.connect(
        settings.cloud_sql_instance_connection_name,
        "pg8000",
        user=settings.db_user,
        password=settings.db_password,
        db=settings.db_name,
    )


def _get_or_create_role(session: OrmSession) -> Role:
    role = session.execute(select(Role).where(Role.name == "user")).scalar_one_or_none()
    if role is not None:
        return role
    role = Role(name="user", description="Usuario estándar con acceso básico a la plataforma")
    session.add(role)
    session.flush()
    return role


def _get_or_create_mario(session: OrmSession, role: Role) -> User:
    user = session.execute(select(User).where(User.email == DEMO_EMAIL)).scalar_one_or_none()
    if user is not None:
        return user
    user = User(
        email=DEMO_EMAIL,
        password_hash=hash_password(DEMO_PASSWORD),
        full_name=DEMO_FULL_NAME,
        role_id=role.id,
    )
    session.add(user)
    session.flush()
    return user


def _wipe_existing_sessions(session: OrmSession, user_id) -> int:
    """Delete every session for this user. CASCADE drops metric rows."""
    result = session.execute(delete(Session).where(Session.user_id == user_id))
    return result.rowcount or 0


def _build_module_curves(rng: random.Random) -> dict[ModuleEnum, tuple[int, int]]:
    """Pick a (start_score, end_score) pair per module.

    Most modules end in the upper 70s/80s. The weak module ends visibly
    lower. The randomisation runs against a fixed-seed rng so the demo
    looks the same every run.
    """
    curves: dict[ModuleEnum, tuple[int, int]] = {}
    for module in SEEDABLE_MODULES:
        if module == WEAK_MODULE:
            curves[module] = WEAK_CURVE
            continue
        start = rng.randint(45, 60)
        end = rng.randint(78, 88)
        curves[module] = (start, end)
    return curves


def _split_minutes(rng: random.Random, total: int, n_sessions: int) -> list[int]:
    """Split `total` minutes into `n_sessions` chunks, each >= 2 minutes."""
    if n_sessions <= 0 or total < 2 * n_sessions:
        return [max(total, 2)]
    splits: list[int] = []
    remaining = total
    for i in range(n_sessions):
        slots_left = n_sessions - i
        if slots_left == 1:
            splits.append(max(2, remaining))
            break
        avg = remaining // slots_left
        chunk = int(rng.gauss(avg, 2))
        # Reserve >= 2 minutes for each remaining slot.
        chunk = max(2, min(chunk, remaining - 2 * (slots_left - 1)))
        splits.append(chunk)
        remaining -= chunk
    return splits


def _score_for(
    rng: random.Random,
    module: ModuleEnum,
    day_offset: int,
    curves: dict[ModuleEnum, tuple[int, int]],
) -> int:
    """Compute a noisy score on the per-module improvement curve.

    `day_offset` is 0 for today and grows backwards in time.
    """
    start_score, end_score = curves[module]
    progress = 1.0 - (day_offset / NUM_DAYS)
    base = start_score + (end_score - start_score) * progress
    noise = rng.gauss(0, 6)
    return max(0, min(100, int(round(base + noise))))


def _generate_sessions(user_id, rng: random.Random) -> list[Session]:
    """Build the list of Session rows for the demo window."""
    curves = _build_module_curves(rng)
    sessions: list[Session] = []
    now_utc = datetime.now(timezone.utc)

    # Iterate day_offset from oldest (NUM_DAYS - 1) to most recent (0).
    for day_offset in range(NUM_DAYS - 1, -1, -1):
        if rng.random() < SKIP_DAY_PROBABILITY:
            continue

        target_minutes = int(rng.gauss(AVG_DAILY_MINUTES, DAILY_MINUTES_SIGMA))
        if target_minutes < 2:
            continue

        n_sessions = rng.randint(1, MAX_SESSIONS_PER_DAY)
        if n_sessions > len(SEEDABLE_MODULES):
            n_sessions = len(SEEDABLE_MODULES)

        modules_today = rng.sample(SEEDABLE_MODULES, k=n_sessions)
        minute_splits = _split_minutes(rng, target_minutes, n_sessions)

        day_anchor = (now_utc - timedelta(days=day_offset)).replace(
            hour=rng.randint(8, 21),
            minute=rng.randint(0, 59),
            second=0,
            microsecond=0,
        )

        cursor = day_anchor
        for module, minutes in zip(modules_today, minute_splits):
            duration_ms = minutes * 60_000
            started_at = cursor
            ended_at = started_at + timedelta(milliseconds=duration_ms)

            sessions.append(
                Session(
                    user_id=user_id,
                    module=module,
                    parent_id=None,
                    started_at=started_at,
                    ended_at=ended_at,
                    duration_ms=duration_ms,
                    score=_score_for(rng, module, day_offset, curves),
                    status=SessionStatusEnum.completed,
                )
            )
            # Random gap before the next session of the day (0-90 min).
            cursor = ended_at + timedelta(minutes=rng.randint(0, 90))
    return sessions


def seed() -> None:
    rng = random.Random(RANDOM_SEED)
    engine = create_engine("postgresql+pg8000://", creator=_get_sync_connection)

    with OrmSession(engine) as session:
        role = _get_or_create_role(session)
        user = _get_or_create_mario(session, role)
        deleted = _wipe_existing_sessions(session, user.id)
        if deleted:
            print(f"Wiped {deleted} existing sessions for {DEMO_EMAIL}")

        new_sessions = _generate_sessions(user.id, rng)
        session.add_all(new_sessions)
        session.commit()
        print(
            f"Seeded {len(new_sessions)} sessions for {DEMO_EMAIL} "
            f"across {len(SEEDABLE_MODULES)} modules over {NUM_DAYS} days"
        )


if __name__ == "__main__":
    seed()
