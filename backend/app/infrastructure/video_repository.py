import json
import os
from typing import List, Optional
from app.domain.entities.video import Video

DATA_FILE = "videos.json"

class VideoRepository:
    def _read_data(self) -> List[dict]:
        if not os.path.exists(DATA_FILE):
            return []
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            return []

    def _write_data(self, data: List[dict]):
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

    def get_all(self) -> List[Video]:
        data = self._read_data()
        return [Video(**item) for item in data]

    def add(self, video: Video) -> Video:
        data = self._read_data()
        data.append({
            "id": video.id,
            "title": video.title,
            "url": video.url,
            "filename": video.filename
        })
        self._write_data(data)
        return video

    def delete(self, video_id: str) -> bool:
        data = self._read_data()
        new_data = [item for item in data if item["id"] != video_id]
        if len(data) == len(new_data):
            return False
        self._write_data(new_data)
        return True

    def get_by_id(self, video_id: str) -> Optional[Video]:
        data = self._read_data()
        for item in data:
            if item["id"] == video_id:
                return Video(**item)
        return None
