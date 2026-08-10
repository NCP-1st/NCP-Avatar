import os
import sys
from logging.config import fileConfig

from sqlalchemy import create_engine
from sqlalchemy import pool

from alembic import context

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from database.models import Base
from database.conn.db import DATABASE_URL, user

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# sqlalchemy.url을 config에 쓰지 않고 파이썬 변수로만 들고 있는다 (비밀번호의 %가
# configparser 보간 문법과 충돌하는 것을 피하기 위함)
if not user:
    sync_url = "sqlite:///database/migrations/local_migration.db"
else:
    sync_url = DATABASE_URL.replace("postgresql+asyncpg", "postgresql+psycopg2")


def run_migrations_offline() -> None:
    context.configure(
        url=sync_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # engine_from_config(config...) 대신 create_engine(sync_url)로 직접 생성 —
    # config 파서를 거치지 않으므로 URL에 %가 있어도 안전하다.
    connectable = create_engine(sync_url, poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()