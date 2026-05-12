"""Backfill the videos table with the objects already in Backblaze B2.

Useful right after introducing the videos metadata table: every
pre-existing object becomes a proper row with a stable UUID and a
display title, so the frontend stops parsing the filename for metadata.

Idempotent: if a row already exists with the same s3_key it is left
alone. Re-running the script never duplicates capsules.

Invoke from the backend directory:

    ./venv/bin/python -m scripts.seed_existing_videos
"""

from __future__ import annotations

import re

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session as OrmSession
from google.cloud.sql.connector import Connector

from app.domain.entities.video import Video
from app.infrastructure.backblaze_setup import get_s3_client
from config import settings


# Matches keys like `video (1).mp4` to recover the original capsule
# number; anything that does not match falls back to enumeration order.
_NUMBERED_VIDEO_RE = re.compile(r"video\s*\((\d+)\)\..+", re.IGNORECASE)


def _get_sync_connection():
    connector = Connector()
    return connector.connect(
        settings.cloud_sql_instance_connection_name,
        "pg8000",
        user=settings.db_user,
        password=settings.db_password,
        db=settings.db_name,
    )


def _list_bucket_keys() -> list[str]:
    s3 = get_s3_client()
    response = s3.list_objects_v2(Bucket=settings.s3_bucket)
    contents = response.get("Contents", [])
    # Skip directory placeholders and order alphabetically for deterministic
    # numbering when filenames do not match the numbered pattern.
    return sorted(obj["Key"] for obj in contents if not obj["Key"].endswith("/"))


def _title_for(key: str, fallback_index: int) -> str:
    match = _NUMBERED_VIDEO_RE.match(key.rsplit("/", 1)[-1])
    if match:
        return f"Cápsula {int(match.group(1))}"
    return f"Cápsula {fallback_index}"


def seed() -> None:
    keys = _list_bucket_keys()
    if not keys:
        print("No objects found in bucket; nothing to seed.")
        return

    engine = create_engine("postgresql+pg8000://", creator=_get_sync_connection)
    with OrmSession(engine) as session:
        existing_keys = set(
            session.execute(select(Video.s3_key)).scalars().all()
        )

        inserted = 0
        for index, key in enumerate(keys, start=1):
            if key in existing_keys:
                continue
            title = _title_for(key, fallback_index=index)
            session.add(Video(title=title, s3_key=key))
            inserted += 1
            print(f"  + {title!r}  ->  {key}")

        session.commit()

    print(f"Seeded {inserted} new video row(s); skipped {len(keys) - inserted} already-tracked object(s).")


if __name__ == "__main__":
    seed()
