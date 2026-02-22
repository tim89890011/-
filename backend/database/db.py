"""
钢子出击 - 数据库连接与初始化
使用 SQLAlchemy async 引擎
"""

import os
import logging
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import text, event
from ..config import settings, BASE_DIR
from .models import Base

logger = logging.getLogger(__name__)

# 确保 data 目录存在
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

# 构建数据库 URL（相对路径基于项目根目录）
db_url = settings.DATABASE_URL
if db_url.startswith("sqlite+aiosqlite:///./"):
    # 将相对路径转为绝对路径
    relative_path = db_url.replace("sqlite+aiosqlite:///./", "")
    absolute_path = os.path.join(BASE_DIR, relative_path)
    db_url = f"sqlite+aiosqlite:///{absolute_path}"

# 创建异步引擎
_engine_kwargs = {"echo": False}  # 生产环境关闭 SQL 日志
if "sqlite" in db_url:
    # SQLite 并发写入优化：连接超时 30 秒，避免 database is locked
    _engine_kwargs["connect_args"] = {"timeout": 30}
else:
    _engine_kwargs["pool_pre_ping"] = True
engine = create_async_engine(db_url, **_engine_kwargs)

# SQLite 每个新连接自动设置 PRAGMA（busy_timeout 是 per-connection 的）
if "sqlite" in db_url:
    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=15000")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()

# 创建异步会话工厂
async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db():
    """FastAPI 依赖注入 - 获取数据库会话

    注意：不自动 commit，由业务代码自行 commit/rollback。
    避免与 debate.py / chat_handler.py 等手动 commit 冲突。
    """
    async with async_session() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def get_async_session():
    """
    获取异步数据库会话（生成器形式，用于非 FastAPI 依赖场景）

    使用示例:
        async for session in get_async_session():
            result = await session.execute(query)
            await session.commit()
    """
    async with async_session() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def init_db():
    """初始化数据库 - 创建所有表 + 开启 WAL 模式"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # #64 修复：开启 WAL 模式，提升并发读写性能
        if "sqlite" in str(engine.url):
            await conn.execute(text("PRAGMA journal_mode=WAL"))
            await conn.execute(text("PRAGMA busy_timeout=5000"))
            signal_results_columns = await conn.execute(
                text("PRAGMA table_info(signal_results)")
            )
            signal_results_col_names = {
                row[1] for row in signal_results_columns.fetchall()
            }
            if "direction_result" not in signal_results_col_names:
                await conn.execute(
                    text(
                        "ALTER TABLE signal_results ADD COLUMN direction_result VARCHAR(10)"
                    )
                )

            ai_signals_columns = await conn.execute(
                text("PRAGMA table_info(ai_signals)")
            )
            ai_signals_col_names = {row[1] for row in ai_signals_columns.fetchall()}
            if "risk_assessment" not in ai_signals_col_names:
                await conn.execute(
                    text(
                        "ALTER TABLE ai_signals ADD COLUMN risk_assessment TEXT DEFAULT ''"
                    )
                )
            # P2 #16: 为 user_settings 表补充 close_cooldown_seconds 字段
            user_settings_columns = await conn.execute(
                text("PRAGMA table_info(user_settings)")
            )
            user_settings_col_names = {
                row[1] for row in user_settings_columns.fetchall()
            }
            if "close_cooldown_seconds" not in user_settings_col_names:
                await conn.execute(
                    text(
                        "ALTER TABLE user_settings ADD COLUMN close_cooldown_seconds INTEGER DEFAULT 30"
                    )
                )
                logger.info("[数据库] user_settings 表已添加 close_cooldown_seconds 字段")

            logger.info("[数据库] SQLite WAL 模式已开启")
    logger.info("[数据库] 所有表已创建/确认存在")


async def close_db():
    """关闭数据库连接"""
    await engine.dispose()
    logger.info("[数据库] 连接已关闭")
