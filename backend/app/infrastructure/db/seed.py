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

from app.domain.entities.enums import ModuleEnum
from app.domain.entities.loudness_preset import LoudnessPreset
from app.domain.entities.prompt import Prompt
from app.domain.entities.role import Role
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


def _seed_precision_prompts(session: OrmSession) -> None:
    """Seed open-ended questions for the precision module.

    Each prompt asks the user to answer a question directly so Gemini can
    score relevance, directness and conciseness. Idempotent on (module, text).
    """

    prompts = [
        "Cuéntame brevemente sobre tu mayor logro profesional.",
        "¿Cuál ha sido el mayor desafío que has enfrentado en tu trabajo y cómo lo resolviste?",
        "Describe una situación en la que tuviste que tomar una decisión difícil bajo presión.",
        "¿Por qué deberíamos elegirte para este proyecto en lugar de otra persona?",
        "Explica en una oración qué haces y a quién ayudas.",
        "¿Cómo manejas el feedback negativo o las críticas constructivas?",
        "Cuéntame un error reciente del que aprendiste algo importante.",
        "¿Cuál es tu opinión sobre el trabajo remoto y por qué?",
        "Describe el proyecto más complejo en el que hayas trabajado.",
        "¿Qué habilidad te gustaría desarrollar en los próximos seis meses?",
    ]
    for text in prompts:
        existing = session.execute(
            select(Prompt).where(
                Prompt.module == ModuleEnum.precision,
                Prompt.text == text,
            )
        ).scalar_one_or_none()
        if existing is None:
            session.add(
                Prompt(
                    module=ModuleEnum.precision,
                    text=text,
                    category="general",
                    difficulty="basic",
                    language="es",
                    is_active=True,
                )
            )
            print(f"Precision prompt seeded: '{text[:50]}...'")
        else:
            print(f"Precision prompt already exists: '{text[:50]}...'")


def _seed_accentuation_phrases(session: OrmSession) -> None:
    """Seed accentuation phrases in the unified prompts catalog.

    `category` (declarative / interrogative / exclamative) drives UI grouping
    and Gemini's prompt template — it's the same field used in precision and
    linguistic_versatility but with module-specific semantics. Idempotent on
    (module, text).
    """

    phrases = [
        ("El pájaro cantaba sobre el árbol más alto del jardín.", "declarative"),
        ("La música clásica transmite emociones profundas.", "declarative"),
        ("¿Dónde compraste esa lámpara tan bonita?", "interrogative"),
        ("¡Qué espectáculo tan magnífico!", "exclamative"),
        ("El médico le recomendó tomar la medicina después del almuerzo.", "declarative"),
        ("Los exámenes de matemáticas fueron difíciles pero necesarios.", "declarative"),
    ]
    for text, category in phrases:
        existing = session.execute(
            select(Prompt).where(
                Prompt.module == ModuleEnum.accentuation,
                Prompt.text == text,
            )
        ).scalar_one_or_none()
        if existing is None:
            session.add(
                Prompt(
                    module=ModuleEnum.accentuation,
                    text=text,
                    category=category,
                    difficulty="basic",
                    language="es",
                    is_active=True,
                )
            )
            print(f"Accentuation phrase seeded: '{text[:50]}...'")
        else:
            print(f"Accentuation phrase already exists: '{text[:50]}...'")


def _seed_pronunciation_phrases(session: OrmSession) -> None:
    """Seed pronunciation phrases in the unified prompts catalog.

    `difficulty` (basico / intermedio / avanzado) matches the level selector
    in the frontend. The phonetic complexity grows with difficulty:
    basic CV words, intermediate complex syllables, advanced clusters and
    tongue-twister-like density. Idempotent on (module, text).
    """

    phrases = [
        # basic
        ("La luna brilla sobre el mar.", "basico"),
        ("Mi mamá come una naranja.", "basico"),
        ("El niño juega en el parque.", "basico"),
        ("La flor roja es muy bonita.", "basico"),
        ("Veo pájaros en el jardín.", "basico"),
        ("El perro corre por el campo.", "basico"),
        # intermediate
        ("El ferrocarril recorre la sierra.", "intermedio"),
        ("La lluvia cae sobre la calle mojada.", "intermedio"),
        ("Jorge trabaja en la ciudad grande.", "intermedio"),
        ("El reloj de la torre marca las tres.", "intermedio"),
        ("Guillermo bebe jugo de naranja fresca.", "intermedio"),
        ("La jirafa come hojas verdes del árbol.", "intermedio"),
        # advanced
        ("El extraordinario guerrero cruzó la pradera.", "avanzado"),
        ("La proyección refleja brillantes colores rojizos.", "avanzado"),
        ("El ferroviario corrigió rápidamente el horario.", "avanzado"),
        ("Glorioso amanecer sobre las verdes praderas rurales.", "avanzado"),
        ("Jorge rechazó la oferta extraordinaria del generoso jefe.", "avanzado"),
        ("El joven relojero reparó el viejo ferrocarril.", "avanzado"),
    ]
    for text, difficulty in phrases:
        existing = session.execute(
            select(Prompt).where(
                Prompt.module == ModuleEnum.pronunciation,
                Prompt.text == text,
            )
        ).scalar_one_or_none()
        if existing is None:
            session.add(
                Prompt(
                    module=ModuleEnum.pronunciation,
                    text=text,
                    category="general",
                    difficulty=difficulty,
                    language="es",
                    is_active=True,
                )
            )
            print(f"Pronunciation phrase seeded: '{text[:50]}...'")
        else:
            print(f"Pronunciation phrase already exists: '{text[:50]}...'")


def _seed_pause_prompts(session: OrmSession) -> None:
    """Seed open-ended prompts for the pauses module.

    Each prompt invites a short improvised speech so the frontend's audio
    pipeline can score the user's pause patterns (natural / rhetorical /
    break). Idempotent on (module, text). Replaces the hardcoded
    PAUSE_QUESTIONS list that lived in the frontend.
    """

    prompts = [
        "Describe brevemente una experiencia presentando frente a otras personas.",
        "Explica cómo resolverías un problema importante con tu equipo.",
        "Cuenta qué habilidad comunicacional te gustaría mejorar y por qué.",
        "Describe un proyecto que te emocione y explica por qué.",
        "Cuéntame una anécdota reciente que te haya hecho reír.",
        "Habla de un lugar donde te sientas cómodo hablando en público.",
        "Explica una idea compleja de tu trabajo o estudio en palabras simples.",
        "Describe el último libro o curso que te dejó algo importante.",
    ]
    for text in prompts:
        existing = session.execute(
            select(Prompt).where(
                Prompt.module == ModuleEnum.pauses,
                Prompt.text == text,
            )
        ).scalar_one_or_none()
        if existing is None:
            session.add(
                Prompt(
                    module=ModuleEnum.pauses,
                    text=text,
                    category="general",
                    difficulty="basic",
                    language="es",
                    is_active=True,
                )
            )
            print(f"Pauses prompt seeded: '{text[:50]}...'")
        else:
            print(f"Pauses prompt already exists: '{text[:50]}...'")


def _seed_muletillas_prompts(session: OrmSession) -> None:
    """Seed open-ended questions for the muletillas module.

    The questions invite the user to answer freely so Gemini can detect
    filler words. Idempotent on (module, text). Replaces the previous
    hardcoded EVALUATION_QUESTIONS list inside the use_case.
    """

    prompts = [
        "Cuéntame sobre tu día de hoy.",
        "Describe tu lugar de trabajo o estudio.",
        "Explica en qué consiste tu pasatiempo favorito.",
        "Habla sobre una película o libro que hayas disfrutado recientemente.",
        "Describe un momento importante en tu vida.",
        "¿Qué te motiva a mejorar tu comunicación oral?",
        "Habla sobre alguien que admiras y por qué.",
        "Describe el lugar donde creciste.",
    ]
    for text in prompts:
        existing = session.execute(
            select(Prompt).where(
                Prompt.module == ModuleEnum.muletillas,
                Prompt.text == text,
            )
        ).scalar_one_or_none()
        if existing is None:
            session.add(
                Prompt(
                    module=ModuleEnum.muletillas,
                    text=text,
                    category="general",
                    difficulty="basic",
                    language="es",
                    is_active=True,
                )
            )
            print(f"Muletillas prompt seeded: '{text[:50]}...'")
        else:
            print(f"Muletillas prompt already exists: '{text[:50]}...'")


def _seed_linguistic_versatility_prompts(session: OrmSession) -> None:
    """Seed open-ended questions for linguistic_versatility (guided mode).

    Each prompt invites the user to talk for ~30s about a topic that exposes
    vocabulary range. Free mode does not use these prompts. Idempotent on
    (module, text).
    """

    prompts = [
        "Describe tu lugar favorito de la ciudad y por qué te gusta.",
        "Cuéntame sobre una película o libro que te haya marcado, sin contar el final.",
        "Explica con tus palabras cómo funciona algo que te apasione.",
        "Describe un sabor o un aroma que te traiga recuerdos vívidos.",
        "Habla de una persona que admires y de qué cualidades tiene.",
        "Imagina que tenés que vender un producto cualquiera. Convénceme.",
        "Cuéntame qué hiciste el último fin de semana, con el mayor detalle posible.",
        "Describe un paisaje que conozcas, como si la persona que escucha nunca lo hubiera visto.",
        "Explica un proceso cotidiano (cocinar algo, llegar a un lugar) paso a paso.",
        "Cuéntame qué te gustaría aprender en los próximos meses y por qué.",
    ]
    for text in prompts:
        existing = session.execute(
            select(Prompt).where(
                Prompt.module == ModuleEnum.linguistic_versatility,
                Prompt.text == text,
            )
        ).scalar_one_or_none()
        if existing is None:
            session.add(
                Prompt(
                    module=ModuleEnum.linguistic_versatility,
                    text=text,
                    category="general",
                    difficulty="basic",
                    language="es",
                    is_active=True,
                )
            )
            print(f"Linguistic versatility prompt seeded: '{text[:50]}...'")
        else:
            print(f"Linguistic versatility prompt already exists: '{text[:50]}...'")


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
        _seed_precision_prompts(session)
        _seed_linguistic_versatility_prompts(session)
        _seed_muletillas_prompts(session)
        _seed_pause_prompts(session)
        _seed_accentuation_phrases(session)
        _seed_pronunciation_phrases(session)
        _seed_dev_user(session, role)
        session.commit()
        print("Seed completed")


if __name__ == "__main__":
    seed()
