"""ai_batch_error_fields

Revision ID: f9bb6501deea
Revises: f9bb6501dee9
Create Date: 2026-02-22 15:00:00

目的：
- 为 ai_signals 增加批次追踪、链路、错误记录、阶段耗时字段
- 使用 inspector + add_column，兼容 SQLite，避免重复添加
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "f9bb6501deea"
down_revision: Union[str, None] = "f9bb6501dee9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "ai_signals" in tables:
        cols = {c["name"] for c in inspector.get_columns("ai_signals")}
        if "batch_id" not in cols:
            op.add_column(
                "ai_signals",
                sa.Column("batch_id", sa.String(36), nullable=True, comment="批次UUID"),
            )
        if "prev_same_symbol_id" not in cols:
            op.add_column(
                "ai_signals",
                sa.Column("prev_same_symbol_id", sa.Integer(), nullable=True, comment="同币种上一条信号ID"),
            )
        if "error_text" not in cols:
            op.add_column(
                "ai_signals",
                sa.Column("error_text", sa.Text(), nullable=True, comment="分析失败时的错误信息"),
            )
        if "stage_timestamps" not in cols:
            op.add_column(
                "ai_signals",
                sa.Column("stage_timestamps", sa.Text(), nullable=True, comment="各阶段耗时 JSON"),
            )


def downgrade() -> None:
    pass
