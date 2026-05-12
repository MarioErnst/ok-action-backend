import logging
import uuid

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.video import Video
from app.infrastructure.backblaze_setup import get_presigned_url, get_s3_client
from app.infrastructure.repositories import video_repository as video_repo
from app.presentation.schemas.videos import VideoResponse
from config import settings

logger = logging.getLogger(__name__)


def _to_response(video: Video) -> VideoResponse:
    """Build the wire-format from the persisted row + a fresh presigned URL.

    The URL is generated on the fly so it always has a useful TTL, even
    when the row was inserted hours ago.
    """
    filename = video.s3_key.rsplit("/", 1)[-1]
    return VideoResponse(
        id=str(video.id),
        title=video.title,
        url=get_presigned_url(video.s3_key),
        filename=filename,
    )


async def list_videos(db: AsyncSession) -> list[VideoResponse]:
    rows = await video_repo.list_all(db)
    return [_to_response(v) for v in rows]


async def upload_video(db: AsyncSession, file: UploadFile, title: str) -> VideoResponse:
    """Upload the binary to Backblaze, then persist its metadata.

    The bucket write happens first so that a DB failure leaves only an
    orphan object (recoverable by a manual sweep of the bucket) rather
    than a phantom DB row pointing at a missing file.
    """
    new_id = uuid.uuid4()
    original = file.filename or "video.mp4"
    ext = original.rsplit(".", 1)[-1].lower() if "." in original else "mp4"
    s3_key = f"videos/{new_id}.{ext}"

    content = await file.read()
    s3 = get_s3_client()
    s3.put_object(
        Bucket=settings.s3_bucket,
        Key=s3_key,
        Body=content,
        ContentType=file.content_type or "video/mp4",
    )

    video = await video_repo.create(db, title=title, s3_key=s3_key)
    await db.commit()
    return _to_response(video)


async def delete_video(db: AsyncSession, video_id: uuid.UUID) -> bool:
    """Delete the bucket object first, then the DB row.

    Doing it in this order means that if Backblaze fails we keep the
    metadata and the user can retry. The reverse would leave an
    inaccessible orphan object.
    """
    video = await video_repo.get_by_id(db, video_id)
    if video is None:
        return False

    s3 = get_s3_client()
    try:
        s3.delete_object(Bucket=settings.s3_bucket, Key=video.s3_key)
    except Exception:
        logger.exception("Failed to delete S3 object %s", video.s3_key)
        raise

    await video_repo.delete_row(db, video_id)
    await db.commit()
    return True
