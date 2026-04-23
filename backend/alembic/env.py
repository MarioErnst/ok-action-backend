from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool, create_engine
from google.cloud.sql.connector import Connector

from app.infrastructure.db.base import Base
from config import settings

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_sync_connection():
    connector = Connector()
    conn = connector.connect(
        settings.cloud_sql_instance_connection_name,
        "pg8000",
        user=settings.db_user,
        password=settings.db_password,
        db=settings.db_name,
    )
    return conn


def run_migrations_offline():
    context.configure(
        url=f"postgresql+pg8000://{settings.db_user}:{settings.db_password}@/{settings.db_name}",
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    connectable = create_engine(
        "postgresql+pg8000://",
        creator=get_sync_connection,
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
