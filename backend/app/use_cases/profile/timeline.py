from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import Date, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.enums import ModuleEnum
from app.domain.entities.session import Session
from app.presentation.schemas.profile import TimelinePoint, TimelineResponse, TimeRange


# Maps the public range token to a lower bound delta. "all" means no bound.
_RANGE_DAYS: dict[TimeRange, int | None] = {
    "7d": 7,
    "30d": 30,
    "90d": 90,
    "all": None,
}


async def get_user_timeline(
    db: AsyncSession,
    user_id: UUID,
    range_: TimeRange = "30d",
    module: str = "all",
) -> TimelineResponse:
    """Aggregate the user's sessions per UTC day for the timeline charts.

    The aggregation uses Postgres `DATE(started_at)` which reads the
    timestamp in the server timezone; Cloud SQL defaults to UTC so all
    bucketing here is UTC-relative. That is enough for the dashboard demo
    and matches how the seed script writes timestamps.
    """

    date_col = cast(Session.started_at, Date).label("date")

    stmt = (
        select(
            date_col,
            func.avg(Session.score).label("avg_score"),
            func.coalesce(func.sum(Session.duration_ms), 0).label("total_duration_ms"),
            func.count(Session.id).label("session_count"),
        )
        .where(Session.user_id == user_id)
        .group_by(date_col)
        .order_by(date_col)
    )

    days = _RANGE_DAYS[range_]
    if days is not None:
        # Inclusive lower bound: now() - N days. Sessions older than that are filtered.
        lower_bound = datetime.now(timezone.utc) - timedelta(days=days)
        stmt = stmt.where(Session.started_at >= lower_bound)

    if module != "all":
        # Validate against the enum so unknown slugs return an empty series
        # instead of a 500 from the DB layer.
        try:
            module_enum = ModuleEnum(module)
        except ValueError:
            return TimelineResponse(range=range_, module=module, daily=[])
        stmt = stmt.where(Session.module == module_enum)

    result = await db.execute(stmt)
    rows = result.all()

    daily = [
        TimelinePoint(
            date=row.date,
            avg_score=int(row.avg_score) if row.avg_score is not None else None,
            total_duration_ms=int(row.total_duration_ms or 0),
            session_count=int(row.session_count),
        )
        for row in rows
    ]

    return TimelineResponse(range=range_, module=module, daily=daily)
