from logging.config import fileConfig
from alembic import context
from sqlalchemy import create_engine
from backend.app.config import get_settings
from backend.app.models import Base

if context.config.config_file_name:
    fileConfig(context.config.config_file_name)
target_metadata = Base.metadata
url = get_settings().database_url.replace("postgresql://", "postgresql+psycopg://", 1)

if context.is_offline_mode():
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = create_engine(url, connect_args={"connect_timeout": 5})
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
