"""
Seed script for the precision_questions table.
Run once before first use: python -m app.infrastructure.db.seeds.precision_questions_seed
Must be run from backend/ directory with venv activated.
"""
import asyncio
import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app.infrastructure.db.session import async_session_factory

QUESTIONS = [
    {"text": "¿Qué es lo más importante que aprendiste esta semana?", "category": "reflexión", "difficulty_level": "basic"},
    {"text": "Explica en pocas palabras qué hace tu trabajo.", "category": "profesional", "difficulty_level": "basic"},
    {"text": "¿Cuál es tu principal objetivo este mes?", "category": "metas", "difficulty_level": "basic"},
    {"text": "Describe en una o dos oraciones cuál fue el mayor desafío de tu día.", "category": "reflexión", "difficulty_level": "basic"},
    {"text": "¿Qué harías diferente si pudieras repetir la última semana?", "category": "reflexión", "difficulty_level": "basic"},
    {"text": "¿Cuál es la decisión más importante que tomaste esta semana y por qué?", "category": "reflexión", "difficulty_level": "intermediate"},
    {"text": "Explica brevemente cómo resolviste un problema reciente.", "category": "profesional", "difficulty_level": "intermediate"},
    {"text": "¿Qué cambio específico harías en tu rutina diaria para ser más productivo?", "category": "metas", "difficulty_level": "intermediate"},
    {"text": "¿Cómo describirías tu mayor fortaleza profesional en pocas palabras?", "category": "profesional", "difficulty_level": "intermediate"},
    {"text": "¿Cuál es la idea principal de un proyecto en el que estás trabajando?", "category": "profesional", "difficulty_level": "intermediate"},
    {"text": "Describe en pocas palabras cuál es tu propuesta de valor como profesional.", "category": "profesional", "difficulty_level": "advanced"},
    {"text": "¿Cuál es la lección más importante que has aprendido de un fracaso reciente?", "category": "reflexión", "difficulty_level": "advanced"},
    {"text": "Explica en qué área necesitas mejorar más y qué pasos concretos tomarías.", "category": "metas", "difficulty_level": "advanced"},
    {"text": "¿Qué impacto tiene tu trabajo en las personas que te rodean?", "category": "metas", "difficulty_level": "advanced"},
    {"text": "Describe cuál es tu visión a largo plazo en una sola idea central.", "category": "metas", "difficulty_level": "advanced"},
]


async def seed() -> None:
    # Deferred to avoid resolving the ORM mapper before the async engine is initialized.
    from app.domain.entities.precision_question import PrecisionQuestion

    async with async_session_factory() as session:
        async with session.begin():
            existing = await session.execute(select(PrecisionQuestion).limit(1))
            if existing.scalar():
                print("precision_questions already seeded — skipping.")
                return

            for q in QUESTIONS:
                session.add(PrecisionQuestion(
                    id=uuid.uuid4(),
                    text=q["text"],
                    category=q["category"],
                    difficulty_level=q["difficulty_level"],
                    is_active=True,
                    created_at=datetime.now(timezone.utc),
                ))

    print(f"Seeded {len(QUESTIONS)} precision questions.")


if __name__ == "__main__":
    asyncio.run(seed())
