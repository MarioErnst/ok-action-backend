"""Uniform DB schema reset.

Drops every legacy table and recreates the unified design: a single sessions
table as the root for all modules, with per-module <module>_metrics tables
linked 1:1 by session_id. Live sessions compose other module sessions via
parent_id.

Revision ID: 0001_uniform_schema
Revises:
Create Date: 2026-05-09
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_uniform_schema"
down_revision = None
branch_labels = None
depends_on = None


# ---------- ENUM definitions ----------

MODULE_VALUES = (
    "phonation",
    "loudness",
    "accentuation",
    "pronunciation",
    "muletillas",
    "pauses",
    "precision",
    "linguistic_versatility",
    "facial_expression",
    "fluency",
    "consistency",
    "live",
)
SESSION_STATUS_VALUES = ("active", "completed", "aborted")
STOP_REASON_VALUES = ("user_stop", "time_limit", "error", "completed")
EXERCISE_TYPE_VALUES = ("holding", "gliding")
TOP_EMOTION_VALUES = (
    "happy",
    "sad",
    "angry",
    "surprised",
    "fearful",
    "disgusted",
    "neutral",
)
PRECISION_MODE_VALUES = ("standalone", "live")
LEX_MODE_VALUES = ("guided", "free")
MULETILLA_SEVERITY_VALUES = ("low", "medium", "high")


def _enum(name: str, values: tuple[str, ...]) -> postgresql.ENUM:
    return postgresql.ENUM(*values, name=name, create_type=False)


def upgrade() -> None:
    # 1. Create ENUM types up front so they can be reused across tables.
    op.execute(
        f"CREATE TYPE module_enum AS ENUM ({', '.join(repr(v) for v in MODULE_VALUES)})"
    )
    op.execute(
        f"CREATE TYPE session_status_enum AS ENUM ({', '.join(repr(v) for v in SESSION_STATUS_VALUES)})"
    )
    op.execute(
        f"CREATE TYPE stop_reason_enum AS ENUM ({', '.join(repr(v) for v in STOP_REASON_VALUES)})"
    )
    op.execute(
        f"CREATE TYPE exercise_type_enum AS ENUM ({', '.join(repr(v) for v in EXERCISE_TYPE_VALUES)})"
    )
    op.execute(
        f"CREATE TYPE top_emotion_enum AS ENUM ({', '.join(repr(v) for v in TOP_EMOTION_VALUES)})"
    )
    op.execute(
        f"CREATE TYPE precision_mode_enum AS ENUM ({', '.join(repr(v) for v in PRECISION_MODE_VALUES)})"
    )
    op.execute(
        f"CREATE TYPE linguistic_versatility_mode_enum AS ENUM ({', '.join(repr(v) for v in LEX_MODE_VALUES)})"
    )
    op.execute(
        f"CREATE TYPE muletilla_severity_enum AS ENUM ({', '.join(repr(v) for v in MULETILLA_SEVERITY_VALUES)})"
    )

    # 2. Identity tables.
    op.create_table(
        "roles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(50), nullable=False, unique=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(150), nullable=False),
        sa.Column(
            "role_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("roles.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_users_active", "users", ["is_active", "deleted_at"])

    # 3. Catalogs.
    op.create_table(
        "prompts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("module", _enum("module_enum", MODULE_VALUES), nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("difficulty", sa.String(20), nullable=False, server_default="basic"),
        sa.Column("language", sa.CHAR(2), nullable=False, server_default="es"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("module", "text", name="uq_prompts_module_text"),
    )
    op.create_index(
        "ix_prompts_module_active_difficulty",
        "prompts",
        ["module", "is_active", "difficulty"],
    )

    op.create_table(
        "loudness_presets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("label", sa.String(100), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("silence_offset_db", sa.Numeric(6, 2), nullable=False),
        sa.Column("low_offset_db", sa.Numeric(6, 2), nullable=False),
        sa.Column("optimal_offset_db", sa.Numeric(6, 2), nullable=False),
        sa.Column("clip_threshold_db", sa.Numeric(6, 2), nullable=False),
        sa.Column("is_default", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_loudness_presets_user", "loudness_presets", ["user_id"])
    op.create_index("ix_loudness_presets_default", "loudness_presets", ["is_default"])

    # 4. Root sessions table.
    op.create_table(
        "sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("module", _enum("module_enum", MODULE_VALUES), nullable=False),
        sa.Column(
            "parent_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer, nullable=True),
        sa.Column("score", sa.SmallInteger, nullable=True),
        sa.Column(
            "status",
            _enum("session_status_enum", SESSION_STATUS_VALUES),
            nullable=False,
            server_default="active",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "score IS NULL OR (score BETWEEN 0 AND 100)", name="ck_sessions_score_range"
        ),
        sa.CheckConstraint(
            "(status = 'active') = (ended_at IS NULL)", name="ck_sessions_active_ended"
        ),
    )
    op.create_index("ix_sessions_user_started", "sessions", ["user_id", "started_at"])
    op.create_index(
        "ix_sessions_user_module_started", "sessions", ["user_id", "module", "started_at"]
    )
    op.create_index("ix_sessions_parent", "sessions", ["parent_id"])
    op.create_index("ix_sessions_module_status", "sessions", ["module", "status"])

    # 5. Per-module metrics tables.
    op.create_table(
        "phonation_metrics",
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("avg_hz", sa.Numeric(8, 2), nullable=False),
        sa.Column("stability_score", sa.SmallInteger, nullable=False),
        sa.Column("breaks_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("exercises_count", sa.Integer, nullable=False, server_default="0"),
        sa.CheckConstraint(
            "stability_score BETWEEN 0 AND 100",
            name="ck_phonation_metrics_stability_range",
        ),
    )

    op.create_table(
        "phonation_session_exercises",
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "exercise_type",
            _enum("exercise_type_enum", EXERCISE_TYPE_VALUES),
            primary_key=True,
        ),
        sa.Column("avg_hz", sa.Numeric(8, 2), nullable=False),
        sa.Column("stability_score", sa.SmallInteger, nullable=False),
        sa.Column("breaks_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("in_range_pct", sa.SmallInteger, nullable=False),
        sa.CheckConstraint(
            "stability_score BETWEEN 0 AND 100",
            name="ck_phonation_exercise_stability_range",
        ),
        sa.CheckConstraint(
            "in_range_pct BETWEEN 0 AND 100",
            name="ck_phonation_exercise_in_range_pct",
        ),
    )
    op.create_index(
        "ix_phonation_exercises_type", "phonation_session_exercises", ["exercise_type"]
    )

    op.create_table(
        "loudness_metrics",
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "preset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("loudness_presets.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("optimal_pct", sa.SmallInteger, nullable=False),
        sa.Column("low_pct", sa.SmallInteger, nullable=False),
        sa.Column("high_pct", sa.SmallInteger, nullable=False),
        sa.Column("clipping_pct", sa.SmallInteger, nullable=False),
        sa.Column("peak_db", sa.Numeric(8, 2), nullable=False),
        sa.CheckConstraint("optimal_pct BETWEEN 0 AND 100", name="ck_loudness_optimal_pct"),
        sa.CheckConstraint("low_pct BETWEEN 0 AND 100", name="ck_loudness_low_pct"),
        sa.CheckConstraint("high_pct BETWEEN 0 AND 100", name="ck_loudness_high_pct"),
        sa.CheckConstraint("clipping_pct BETWEEN 0 AND 100", name="ck_loudness_clipping_pct"),
        sa.CheckConstraint(
            "optimal_pct + low_pct + high_pct + clipping_pct = 100",
            name="ck_loudness_pct_total",
        ),
    )

    op.create_table(
        "accentuation_metrics",
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("pronunciation_score", sa.SmallInteger, nullable=False),
        sa.Column("rhythm_score", sa.SmallInteger, nullable=False),
        sa.Column("intonation_score", sa.SmallInteger, nullable=False),
        sa.Column("stress_score", sa.SmallInteger, nullable=False),
        sa.Column("phrases_count", sa.Integer, nullable=False, server_default="0"),
        sa.CheckConstraint(
            "pronunciation_score BETWEEN 0 AND 100",
            name="ck_accentuation_pronunciation_score",
        ),
        sa.CheckConstraint(
            "rhythm_score BETWEEN 0 AND 100", name="ck_accentuation_rhythm_score"
        ),
        sa.CheckConstraint(
            "intonation_score BETWEEN 0 AND 100", name="ck_accentuation_intonation_score"
        ),
        sa.CheckConstraint(
            "stress_score BETWEEN 0 AND 100", name="ck_accentuation_stress_score"
        ),
    )

    op.create_table(
        "pronunciation_metrics",
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("level", sa.String(20), nullable=False),
        sa.Column("vowel_score", sa.SmallInteger, nullable=False),
        sa.Column("consonant_score", sa.SmallInteger, nullable=False),
        sa.Column("fluency_score", sa.SmallInteger, nullable=False),
        sa.Column("intelligibility_score", sa.SmallInteger, nullable=False),
        sa.Column("phrases_count", sa.Integer, nullable=False, server_default="0"),
        sa.CheckConstraint(
            "vowel_score BETWEEN 0 AND 100", name="ck_pronunciation_vowel_score"
        ),
        sa.CheckConstraint(
            "consonant_score BETWEEN 0 AND 100", name="ck_pronunciation_consonant_score"
        ),
        sa.CheckConstraint(
            "fluency_score BETWEEN 0 AND 100", name="ck_pronunciation_fluency_score"
        ),
        sa.CheckConstraint(
            "intelligibility_score BETWEEN 0 AND 100",
            name="ck_pronunciation_intelligibility_score",
        ),
    )

    op.create_table(
        "muletillas_metrics",
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("fluency_score", sa.SmallInteger, nullable=False),
        sa.Column("muletillas_count", sa.Integer, nullable=False, server_default="0"),
        sa.CheckConstraint(
            "fluency_score BETWEEN 0 AND 100", name="ck_muletillas_fluency_score"
        ),
    )

    op.create_table(
        "muletillas_word_usage",
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("word", sa.String(100), primary_key=True),
        sa.Column("count", sa.Integer, nullable=False, server_default="1"),
        sa.Column(
            "severity",
            _enum("muletilla_severity_enum", MULETILLA_SEVERITY_VALUES),
            nullable=False,
        ),
    )
    op.create_index("ix_muletillas_word", "muletillas_word_usage", ["word"])

    op.create_table(
        "pause_metrics",
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("pauses_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_pause_ms", sa.Integer, nullable=False, server_default="0"),
        sa.Column("longest_pause_ms", sa.Integer, nullable=False, server_default="0"),
        sa.Column("silence_pct", sa.SmallInteger, nullable=False),
        sa.CheckConstraint("silence_pct BETWEEN 0 AND 100", name="ck_pause_silence_pct"),
    )

    op.create_table(
        "precision_metrics",
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "mode",
            _enum("precision_mode_enum", PRECISION_MODE_VALUES),
            nullable=False,
            server_default="standalone",
        ),
        sa.Column("rounds_total", sa.Integer, nullable=False),
        sa.Column("rounds_completed", sa.Integer, nullable=False, server_default="0"),
        sa.Column("relevance_score", sa.SmallInteger, nullable=True),
        sa.Column("directness_score", sa.SmallInteger, nullable=True),
        sa.Column("conciseness_score", sa.SmallInteger, nullable=True),
        sa.CheckConstraint(
            "relevance_score IS NULL OR (relevance_score BETWEEN 0 AND 100)",
            name="ck_precision_relevance_score",
        ),
        sa.CheckConstraint(
            "directness_score IS NULL OR (directness_score BETWEEN 0 AND 100)",
            name="ck_precision_directness_score",
        ),
        sa.CheckConstraint(
            "conciseness_score IS NULL OR (conciseness_score BETWEEN 0 AND 100)",
            name="ck_precision_conciseness_score",
        ),
    )

    op.create_table(
        "precision_rounds",
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("round_index", sa.SmallInteger, primary_key=True),
        sa.Column(
            "prompt_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("prompts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("score", sa.SmallInteger, nullable=True),
        sa.Column("relevance_score", sa.SmallInteger, nullable=True),
        sa.Column("directness_score", sa.SmallInteger, nullable=True),
        sa.Column("conciseness_score", sa.SmallInteger, nullable=True),
        sa.Column(
            "is_audio_intelligible", sa.Boolean, nullable=False, server_default=sa.true()
        ),
        sa.CheckConstraint(
            "score IS NULL OR (score BETWEEN 0 AND 100)",
            name="ck_precision_round_score",
        ),
        sa.CheckConstraint(
            "relevance_score IS NULL OR (relevance_score BETWEEN 0 AND 100)",
            name="ck_precision_round_relevance",
        ),
        sa.CheckConstraint(
            "directness_score IS NULL OR (directness_score BETWEEN 0 AND 100)",
            name="ck_precision_round_directness",
        ),
        sa.CheckConstraint(
            "conciseness_score IS NULL OR (conciseness_score BETWEEN 0 AND 100)",
            name="ck_precision_round_conciseness",
        ),
    )
    op.create_index("ix_precision_rounds_prompt", "precision_rounds", ["prompt_id"])

    op.create_table(
        "linguistic_versatility_metrics",
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "mode",
            _enum("linguistic_versatility_mode_enum", LEX_MODE_VALUES),
            nullable=False,
            server_default="guided",
        ),
        sa.Column("rounds_total", sa.Integer, nullable=False),
        sa.Column("rounds_completed", sa.Integer, nullable=False, server_default="0"),
        sa.Column("vocabulary_richness_avg", sa.SmallInteger, nullable=True),
        sa.CheckConstraint(
            "vocabulary_richness_avg IS NULL OR (vocabulary_richness_avg BETWEEN 0 AND 100)",
            name="ck_lex_richness_avg",
        ),
    )

    op.create_table(
        "linguistic_versatility_rounds",
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("round_index", sa.SmallInteger, primary_key=True),
        sa.Column(
            "prompt_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("prompts.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("score", sa.SmallInteger, nullable=True),
        sa.Column("vocabulary_richness", sa.SmallInteger, nullable=True),
        sa.Column(
            "is_audio_intelligible", sa.Boolean, nullable=False, server_default=sa.true()
        ),
        sa.CheckConstraint(
            "score IS NULL OR (score BETWEEN 0 AND 100)",
            name="ck_lex_round_score",
        ),
        sa.CheckConstraint(
            "vocabulary_richness IS NULL OR (vocabulary_richness BETWEEN 0 AND 100)",
            name="ck_lex_round_richness",
        ),
    )
    op.create_index("ix_lex_rounds_prompt", "linguistic_versatility_rounds", ["prompt_id"])

    op.create_table(
        "facial_expression_metrics",
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("expressiveness_score", sa.SmallInteger, nullable=False),
        sa.Column(
            "top_emotion", _enum("top_emotion_enum", TOP_EMOTION_VALUES), nullable=False
        ),
        sa.Column("happy_pct", sa.SmallInteger, nullable=False),
        sa.Column("sad_pct", sa.SmallInteger, nullable=False),
        sa.Column("angry_pct", sa.SmallInteger, nullable=False),
        sa.Column("surprised_pct", sa.SmallInteger, nullable=False),
        sa.Column("fearful_pct", sa.SmallInteger, nullable=False),
        sa.Column("disgusted_pct", sa.SmallInteger, nullable=False),
        sa.Column("neutral_pct", sa.SmallInteger, nullable=False),
        sa.CheckConstraint(
            "expressiveness_score BETWEEN 0 AND 100",
            name="ck_facial_expressiveness_score",
        ),
        sa.CheckConstraint("happy_pct BETWEEN 0 AND 100", name="ck_facial_happy_pct"),
        sa.CheckConstraint("sad_pct BETWEEN 0 AND 100", name="ck_facial_sad_pct"),
        sa.CheckConstraint("angry_pct BETWEEN 0 AND 100", name="ck_facial_angry_pct"),
        sa.CheckConstraint(
            "surprised_pct BETWEEN 0 AND 100", name="ck_facial_surprised_pct"
        ),
        sa.CheckConstraint("fearful_pct BETWEEN 0 AND 100", name="ck_facial_fearful_pct"),
        sa.CheckConstraint(
            "disgusted_pct BETWEEN 0 AND 100", name="ck_facial_disgusted_pct"
        ),
        sa.CheckConstraint("neutral_pct BETWEEN 0 AND 100", name="ck_facial_neutral_pct"),
        sa.CheckConstraint(
            "happy_pct + sad_pct + angry_pct + surprised_pct + fearful_pct + disgusted_pct + neutral_pct = 100",
            name="ck_facial_pct_total",
        ),
    )

    op.create_table(
        "fluency_metrics",
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("fluency_score", sa.SmallInteger, nullable=False),
        sa.Column("stuck_events_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "words_per_minute", sa.Numeric(6, 2), nullable=False, server_default="0"
        ),
        sa.CheckConstraint(
            "fluency_score BETWEEN 0 AND 100", name="ck_fluency_score"
        ),
    )

    op.create_table(
        "consistency_metrics",
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("consistency_score", sa.SmallInteger, nullable=False),
        sa.Column("volatility_score", sa.SmallInteger, nullable=False),
        sa.Column("active_pct", sa.SmallInteger, nullable=False),
        sa.CheckConstraint(
            "consistency_score BETWEEN 0 AND 100", name="ck_consistency_score"
        ),
        sa.CheckConstraint(
            "volatility_score BETWEEN 0 AND 100",
            name="ck_consistency_volatility_score",
        ),
        sa.CheckConstraint(
            "active_pct BETWEEN 0 AND 100", name="ck_consistency_active_pct"
        ),
    )

    op.create_table(
        "live_metrics",
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "stop_reason", _enum("stop_reason_enum", STOP_REASON_VALUES), nullable=False
        ),
    )


def downgrade() -> None:
    # Drop in reverse dependency order.
    for table in (
        "live_metrics",
        "consistency_metrics",
        "fluency_metrics",
        "facial_expression_metrics",
        "linguistic_versatility_rounds",
        "linguistic_versatility_metrics",
        "precision_rounds",
        "precision_metrics",
        "pause_metrics",
        "muletillas_word_usage",
        "muletillas_metrics",
        "pronunciation_metrics",
        "accentuation_metrics",
        "loudness_metrics",
        "phonation_session_exercises",
        "phonation_metrics",
        "sessions",
        "loudness_presets",
        "prompts",
        "users",
        "roles",
    ):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")

    for enum_name in (
        "muletilla_severity_enum",
        "linguistic_versatility_mode_enum",
        "precision_mode_enum",
        "top_emotion_enum",
        "exercise_type_enum",
        "stop_reason_enum",
        "session_status_enum",
        "module_enum",
    ):
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")
