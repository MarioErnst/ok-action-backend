from __future__ import annotations

from pydantic import BaseModel


class VideoResponse(BaseModel):
    """Wire format for video capsules served by /api/videos.

    `id` is the database PK (UUID serialized as string), `title` is the
    human-readable name, `url` is a freshly generated presigned URL valid
    for 1 hour and `filename` is the bucket key's basename (kept for
    backwards compatibility with the existing frontend).
    """

    id: str
    title: str
    url: str
    filename: str
