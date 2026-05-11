import os
import uuid
import aiofiles
from fastapi import UploadFile
from typing import List
from app.domain.entities.video import Video
from app.infrastructure.video_repository import VideoRepository

repo = VideoRepository()

UPLOADS_DIR = "uploads"
BASE_URL = "http://localhost:8000/uploads"

def list_videos() -> List[Video]:
    return repo.get_all()

async def upload_video(file: UploadFile, title: str) -> Video:
    video_id = str(uuid.uuid4())
    # Clean filename or use original
    original_filename = file.filename if file.filename else "video.mp4"
    saved_filename = f"{video_id}_{original_filename}"
    
    file_path = os.path.join(UPLOADS_DIR, saved_filename)
    
    # Ensure directory exists
    os.makedirs(UPLOADS_DIR, exist_ok=True)
    
    async with aiofiles.open(file_path, 'wb') as out_file:
        content = await file.read()
        await out_file.write(content)
        
    url = f"{BASE_URL}/{saved_filename}"
    
    video = Video(
        id=video_id,
        title=title,
        url=url,
        filename=saved_filename
    )
    
    return repo.add(video)

def delete_video(video_id: str) -> bool:
    video = repo.get_by_id(video_id)
    if not video:
        return False
        
    file_path = os.path.join(UPLOADS_DIR, video.filename)
    if os.path.exists(file_path):
        os.remove(file_path)
        
    return repo.delete(video_id)
