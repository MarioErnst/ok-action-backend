from collections.abc import AsyncGenerator

from google.cloud.sql.connector import Connector
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from config import settings

connector = Connector()


async def _get_connection():
    return await connector.connect_async(
        settings.cloud_sql_instance_connection_name,
        "asyncpg",
        user=settings.db_user,
        password=settings.db_password,
        db=settings.db_name,
    )


engine = create_async_engine(
    "postgresql+asyncpg://",
    async_creator=_get_connection,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)

async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession]:
    async with async_session_factory() as session:
        yield session


async def check_db_connection() -> bool:
    try:
        async with async_session_factory() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


async def dispose_connector():
    await connector.close_async()
    await engine.dispose()
