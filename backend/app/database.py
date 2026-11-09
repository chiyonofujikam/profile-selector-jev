"""Open database sessions for API requests and data imports."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from .config import get_settings

database_url = get_settings().database_url.replace("postgresql://", "postgresql+psycopg://", 1)
engine = create_engine(database_url, pool_pre_ping=True, connect_args={"connect_timeout": 3})
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    with SessionLocal() as session:
        yield session
