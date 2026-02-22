"""fix_partial_tables

Revision ID: f9bb6501dee8
Revises: f9bb6501dee7
Create Date: 2026-02-18 01:17:30

目的：
- 兼容之前迁移中途失败导致的“表已创建但缺列”情况
- 只做 ADD COLUMN（SQLite 安全），不触发 batch 重建
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "f9bb6501dee8"
down_revision: Union[str, None] = "f9bb6501dee7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "cooldown_records" in tables:
        cols = {c["name"] for c in inspector.get_columns("cooldown_records")}
        if "created_at" not in cols:
            op.add_column(
                "cooldown_records",
                sa.Column("created_at", sa.DateTime(), nullable=True, comment="创建时间"),
            )
        if "updated_at" not in cols:
            op.add_column(
                "cooldown_records",
                sa.Column("updated_at", sa.DateTime(), nullable=True, comment="更新时间"),
            )

    if "daily_pnl" in tables:
        cols = {c["name"] for c in inspector.get_columns("daily_pnl")}
        if "updated_at" not in cols:
            op.add_column(
                "daily_pnl",
                sa.Column("updated_at", sa.DateTime(), nullable=True, comment="更新时间"),
            )


def downgrade() -> None:
    # 保守：不做 drop_column，避免 SQLite batch 重建破坏外键
    pass

