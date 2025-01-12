"""OpenNEM Database Module


Provides database engine connections and sessions across the entire
project


"""

import logging
from collections.abc import AsyncGenerator

import deprecation
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

from opennem import __version__, settings

DeclarativeBase = declarative_base()

logger = logging.getLogger("opennem.db")


def db_connect(db_conn_str: str | None = None, debug: bool = False, timeout: int = 10) -> AsyncEngine:
    """
    Performs database connection using database settings from settings.py.

    Returns sqlalchemy engine instance

    :param db_conn_str: Database connection string
    :param debug: Debug mode will render queries and info to terminal
    :param timeout: Database connection timeout
    """
    if not db_conn_str:
        db_conn_str = str(settings.db_url)

    if settings.db_debug:
        debug = True

    try:
        return create_async_engine(
            db_conn_str,
            query_cache_size=1200,
            echo=debug,
            future=True,
            pool_size=30,
            max_overflow=20,
            pool_recycle=100,
            pool_timeout=timeout,
            pool_pre_ping=True,
            pool_use_lifo=True,
        )
    except Exception as exc:
        logger.error("Could not connect to database: %s", exc)
        raise exc


engine = db_connect()


@deprecation.deprecated(
    deprecated_in="1.0", removed_in="0.1.14", current_version=__version__, details="Use the db_connect function instead"
)
def get_database_engine() -> AsyncEngine:
    """
    Gets a database engine connection

    @NOTE deprecate this eventually
    """
    engine = db_connect()

    return engine


SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_scoped_session() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session
