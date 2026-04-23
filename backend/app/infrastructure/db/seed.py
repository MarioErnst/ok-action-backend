import uuid

from google.cloud.sql.connector import Connector
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.domain.entities.role import Role
from app.domain.entities.loudness_preset import LoudnessPreset
from config import settings


def get_sync_connection():
    connector = Connector()
    return connector.connect(
        settings.cloud_sql_instance_connection_name,
        "pg8000",
        user=settings.db_user,
        password=settings.db_password,
        db=settings.db_name,
    )


def seed():
    engine = create_engine("postgresql+pg8000://", creator=get_sync_connection)

    with Session(engine) as session:
        # Seed role
        existing_role = session.execute(
            select(Role).where(Role.name == "user")
        ).scalar_one_or_none()

        if not existing_role:
            session.add(Role(
                name="user",
                description="Usuario estándar con acceso básico a la plataforma",
            ))
            print("Role 'user' created")
        else:
            print("Role 'user' already exists")

        # Seed loudness presets
        presets = [
            {
                "label": "Conversación",
                "description": "Para hablar uno a uno o en grupos pequeños",
                "silence_offset_db": 6,
                "too_low_offset_db": -6,
                "optimal_offset_db": 6,
                "clip_threshold_dbfs": -3,
            },
            {
                "label": "Presentación grupal",
                "description": "Para exponer ante un grupo mediano",
                "silence_offset_db": 6,
                "too_low_offset_db": -4,
                "optimal_offset_db": 8,
                "clip_threshold_dbfs": -3,
            },
            {
                "label": "Auditorio grande",
                "description": "Para hablar en salas grandes o auditorios",
                "silence_offset_db": 6,
                "too_low_offset_db": -3,
                "optimal_offset_db": 10,
                "clip_threshold_dbfs": -3,
            },
        ]

        for preset_data in presets:
            existing = session.execute(
                select(LoudnessPreset).where(
                    LoudnessPreset.label == preset_data["label"],
                    LoudnessPreset.user_id.is_(None),
                )
            ).scalar_one_or_none()

            if not existing:
                session.add(LoudnessPreset(
                    user_id=None,
                    is_default=True,
                    **preset_data,
                ))
                print(f"Preset '{preset_data['label']}' created")
            else:
                print(f"Preset '{preset_data['label']}' already exists")

        session.commit()
        print("Seed completed")


if __name__ == "__main__":
    seed()
