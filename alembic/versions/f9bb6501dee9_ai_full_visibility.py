"""ai_full_visibility

Revision ID: f9bb6501dee9
Revises: f9bb6501dee8
Create Date: 2026-02-22 04:20:00

目的：
- 为 ai_signals 增加“完整输入输出可见”字段
- 使用 inspector + add_column，兼容 SQLite，避免重复添加
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "f9bb6501dee9"
down_revision: Union[str, None] = "f9bb6501dee8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "ai_signals" in tables:
        cols = {c["name"] for c in inspector.get_columns("ai_signals")}
        if "role_input_messages" not in cols:
            op.add_column(
                "ai_signals",
                sa.Column("role_input_messages", sa.Text(), nullable=True, comment="5个角色输入消息 JSON"),
            )
        if "final_input_messages" not in cols:
            op.add_column(
                "ai_signals",
                sa.Column("final_input_messages", sa.Text(), nullable=True, comment="最终裁决输入消息 JSON"),
            )
        if "final_raw_output" not in cols:
            op.add_column(
                "ai_signals",
                sa.Column("final_raw_output", sa.Text(), nullable=True, comment="最终裁决原始输出文本"),
            )


def downgrade() -> None:
    # 保守：不做 drop_column，避免 SQLite batch 重建风险
    pass

