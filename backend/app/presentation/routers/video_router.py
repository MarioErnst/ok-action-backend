from fastapi import APIRouter, UploadFile, File, Form, HTTPException, status
from typing import List
from app.use_cases import video_use_cases
from app.domain.entities.video import Video
from pydantic import BaseModel

router = APIRouter(prefix="/videos", tags=["Videos"])

class VideoResponse(BaseModel):
    id: str
    title: str
    url: str
    filename: str

@router.get("", response_model=List[VideoResponse])
def get_videos():
    videos = video_use_cases.list_videos()
    return videos

@router.post("/upload", response_model=VideoResponse)
async def upload_video(file: UploadFile = File(...), title: str = Form(...)):
    if not file:
        raise HTTPException(status_code=400, detail="No file uploaded")
    try:
        video = await video_use_cases.upload_video(file, title)
        return video
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{video_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_video(video_id: str):
    success = video_use_cases.delete_video(video_id)
    if not success:
        raise HTTPException(status_code=404, detail="Video not found")
