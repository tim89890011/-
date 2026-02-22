"""
Alembic 环境配置 - 钢子出击

此文件配置 Alembic 与 SQLAlchemy 的集成，支持异步数据库操作。
"""
# pyright: reportAttributeAccessIssue=false

import asyncio
import importlib
import os
import sys
from logging.config import fileConfig

from sqlalchemy import pool, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# 导入 models 获取元数据
Base = importlib.import_module("backend.database.models").Base
_config_mod = importlib.import_module("backend.config")
settings = _config_mod.settings
BASE_DIR = _config_mod.BASE_DIR

# Alembic Config 对象
config = context.config

# 解析 .env 配置，覆盖 alembic.ini 中的数据库 URL
db_url = settings.DATABASE_URL
if db_url.startswith("sqlite+aiosqlite:///./"):
    # 将相对路径转为绝对路径
    relative_path = db_url.replace("sqlite+aiosqlite:///./", "")
    absolute_path = os.path.join(BASE_DIR, relative_path)
    db_url = f"sqlite+aiosqlite:///{absolute_path}"

config.set_main_option("sqlalchemy.url", db_url)

# 配置日志
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 目标元数据（用于 autogenerate）
target_metadata = Base.metadata


def _bootstrap_existing_sqlite_schema(connection: Connection) -> None:
    if "sqlite" not in str(connection.engine.url):
        return

    users_exists = (
        connection.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
        ).fetchone()
        is not None
    )
    if not users_exists:
        return

    has_version_table = (
        connection.execute(
            text(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='alembic_version'"
            )
        ).fetchone()
        is not None
    )

    if not has_version_table:
        connection.execute(
            text(
                "CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)"
            )
        )

    version_rows = connection.execute(
        text("SELECT version_num FROM alembic_version")
    ).fetchall()
    if len(version_rows) == 0:
        connection.execute(
            text("INSERT INTO alembic_version(version_num) VALUES ('002')")
        )


def run_migrations_offline() -> None:
    """离线模式运行迁移（生成 SQL 脚本，不实际执行）"""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """实际执行迁移"""
    _bootstrap_existing_sqlite_schema(connection)
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        # SQLite 需要单独配置以支持 ALTER 操作
        render_as_batch=True if "sqlite" in str(connection.engine.url) else False,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """异步模式运行迁移"""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        # SQLite: 开启外键支持
        if "sqlite" in str(connectable.url):
            await connection.execute(text("PRAGMA foreign_keys=ON"))

        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """在线模式运行迁移（实际修改数据库）"""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
