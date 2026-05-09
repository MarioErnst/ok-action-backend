"""Idempotent seed for the OK Action database.

Inserts the baseline rows that the application needs to function in dev
or after a fresh schema reset:

- The "user" role.
- Three system-wide loudness presets (user_id NULL, is_default=True).
- A development user, only when DEV_USER_* env vars are configured.
"""

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session as OrmSession
from google.cloud.sql.connector import Connector

from app.domain.entities.role import Role
from app.domain.entities.loudness_preset import LoudnessPreset
from app.domain.entities.user import User
from app.infrastructure.security.hashing import hash_password
from config import settings


def _get_sync_connection():
    connector = Connector()
    return connector.connect(
        settings.cloud_sql_instance_connection_name,
        "pg8000",
        user=settings.db_user,
        password=settings.db_password,
        db=settings.db_name,
    )


def _seed_role(session: OrmSession) -> Role:
    role = session.execute(select(Role).where(Role.name == "user")).scalar_one_or_none()
    if role is None:
        role = Role(
            name="user",
            description="Usuario estándar con acceso básico a la plataforma",
        )
        session.add(role)
        session.flush()
        print("Role 'user' created")
    else:
        print("Role 'user' already exists")
    return role


def _seed_loudness_presets(session: OrmSession) -> None:
    presets = [
        {
            "label": "Conversación",
            "description": "Para hablar uno a uno o en grupos pequeños",
            "silence_offset_db": 6,
            "low_offset_db": -6,
            "optimal_offset_db": 6,
            "clip_threshold_db": -3,
        },
        {
            "label": "Presentación grupal",
            "description": "Para exponer ante un grupo mediano",
            "silence_offset_db": 6,
            "low_offset_db": -4,
            "optimal_offset_db": 8,
            "clip_threshold_db": -3,
        },
        {
            "label": "Auditorio grande",
            "description": "Para hablar en salas grandes o auditorios",
            "silence_offset_db": 6,
            "low_offset_db": -3,
            "optimal_offset_db": 10,
            "clip_threshold_db": -3,
        },
    ]

    for preset_data in presets:
        existing = session.execute(
            select(LoudnessPreset).where(
                LoudnessPreset.label == preset_data["label"],
                LoudnessPreset.user_id.is_(None),
            )
        ).scalar_one_or_none()

        if existing is None:
            session.add(LoudnessPreset(user_id=None, is_default=True, **preset_data))
            print(f"Preset '{preset_data['label']}' created")
        else:
            print(f"Preset '{preset_data['label']}' already exists")


def _seed_dev_user(session: OrmSession, role: Role) -> None:
    if not settings.dev_user_email:
        return

    existing = session.execute(
        select(User).where(User.email == settings.dev_user_email)
    ).scalar_one_or_none()

    if existing is not None:
        print(f"Dev user '{settings.dev_user_email}' already exists")
        return

    session.add(
        User(
            email=settings.dev_user_email,
            password_hash=hash_password(settings.dev_user_password),
            full_name=settings.dev_user_full_name,
            role_id=role.id,
        )
    )
    print(f"Dev user '{settings.dev_user_email}' created")


def seed() -> None:
    engine = create_engine("postgresql+pg8000://", creator=_get_sync_connection)

    with OrmSession(engine) as session:
        role = _seed_role(session)
        _seed_loudness_presets(session)
        _seed_dev_user(session, role)
        session.commit()
        print("Seed completed")


if __name__ == "__main__":
    seed()
