"""Data-access layer for the videos table.

Kept separate from `app/use_cases/video_use_cases.py` so the use case
stays focused on orchestrating the bucket + the DB without owning SQL
construction. This is the only true repository in the project today;
the rest of the codebase tends to inline its queries inside use cases.
The split is justified here because the videos flow touches two stores
(Postgres + Backblaze) and the SQL surface is small but reused across
three operations.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.video import Video


async def list_all(db: AsyncSession) -> list[Video]:
    """Return every video ordered by most recent first."""
    result = await db.execute(select(Video).order_by(Video.created_at.desc()))
    return list(result.scalars().all())


async def get_by_id(db: AsyncSession, video_id: UUID) -> Video | None:
    result = await db.execute(select(Video).where(Video.id == video_id))
    return result.scalar_one_or_none()


async def create(db: AsyncSession, title: str, s3_key: str) -> Video:
    """Persist a new video row. Caller is responsible for committing."""
    video = Video(title=title, s3_key=s3_key)
    db.add(video)
    await db.flush()
    return video


async def delete_row(db: AsyncSession, video_id: UUID) -> bool:
    """Delete the row by id. Returns True if a row was actually deleted."""
    result = await db.execute(delete(Video).where(Video.id == video_id))
    return (result.rowcount or 0) > 0
