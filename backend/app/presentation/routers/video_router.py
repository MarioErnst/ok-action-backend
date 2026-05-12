from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.session import get_session
from app.presentation.schemas.videos import VideoResponse
from app.use_cases import video_use_cases

router = APIRouter(prefix="/videos", tags=["Videos"])


@router.get("", response_model=list[VideoResponse])
async def get_videos(db: AsyncSession = Depends(get_session)) -> list[VideoResponse]:
    return await video_use_cases.list_videos(db)


@router.post("/upload", response_model=VideoResponse)
async def upload_video(
    file: UploadFile = File(...),
    title: str = Form(...),
    db: AsyncSession = Depends(get_session),
) -> VideoResponse:
    if not file:
        raise HTTPException(status_code=400, detail="No file uploaded")
    return await video_use_cases.upload_video(db, file, title)


@router.delete("/{video_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_video(
    video_id: UUID,
    db: AsyncSession = Depends(get_session),
) -> None:
    deleted = await video_use_cases.delete_video(db, video_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Video not found")
