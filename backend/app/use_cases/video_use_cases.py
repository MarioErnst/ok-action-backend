import uuid
from fastapi import UploadFile
from typing import List
from app.domain.entities.video import Video
from app.infrastructure.backblaze_setup import get_s3_client, get_presigned_url, S3_BUCKET

def list_videos() -> List[Video]:
    s3_client = get_s3_client()
    videos = []
    try:
        # List objects in the bucket (no prefix so it finds them if they are in the root)
        response = s3_client.list_objects_v2(Bucket=S3_BUCKET)
        if 'Contents' in response:
            for obj in response['Contents']:
                s3_key = obj['Key']
                # Skip if it's a directory
                if s3_key.endswith("/"):
                    continue
                
                # Extract filename and create a dummy ID/Title
                filename = s3_key.split("/")[-1]
                video_id = filename.split("_")[0] if "_" in filename else filename
                title = filename.split("_", 1)[1] if "_" in filename else filename
                
                url = get_presigned_url(s3_key)
                videos.append(Video(
                    id=video_id,
                    title=title,
                    url=url,
                    filename=filename
                ))
    except Exception as e:
        print(f"Error listing videos from S3: {e}")
        
    return videos

async def upload_video(file: UploadFile, title: str) -> Video:
    video_id = str(uuid.uuid4())
    # Clean filename or use original
    original_filename = file.filename if file.filename else "video.mp4"
    # To keep it readable in S3, we use video_id_title.ext or similar.
    # We will use video_id_original_filename to parse it later.
    saved_filename = f"{video_id}_{original_filename}"
    s3_key = f"videos/{saved_filename}"
    
    # Read the file content
    content = await file.read()
    
    # Upload to S3 without 'public-read' ACL (keeps it private)
    s3_client = get_s3_client()
    s3_client.put_object(
        Bucket=S3_BUCKET,
        Key=s3_key,
        Body=content,
        ContentType=file.content_type
    )
    
    url = get_presigned_url(s3_key)
    
    return Video(
        id=video_id,
        title=title, # the original title passed in the form
        url=url,
        filename=saved_filename
    )

def delete_video(video_id: str) -> bool:
    s3_client = get_s3_client()
    try:
        # Search the entire bucket to find the file that matches this ID
        response = s3_client.list_objects_v2(Bucket=S3_BUCKET)
        if 'Contents' in response:
            for obj in response['Contents']:
                # The object key could be "videos/123_video.mp4" or just "123_video.mp4"
                filename = obj['Key'].split("/")[-1]
                if filename.startswith(f"{video_id}_") or filename == video_id:
                    s3_client.delete_object(Bucket=S3_BUCKET, Key=obj['Key'])
                    return True
        return False
    except Exception as e:
        print(f"Failed to delete video {video_id} from S3: {e}")
        return False
