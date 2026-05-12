from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base


class Video(Base):
    """Metadata of a learning capsule. The binary lives in Backblaze B2.

    Splitting metadata (id, title) from storage (s3_key → bucket object)
    means a video can be renamed, listed and filtered without touching
    the bucket, and the bucket key can follow a strict UUID convention
    without polluting filenames with display titles.
    """

    __tablename__ = "videos"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    # Bucket key (e.g. `videos/3f8c2d11-…mp4`). Unique to prevent two
    # rows from pointing at the same physical object.
    s3_key: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
