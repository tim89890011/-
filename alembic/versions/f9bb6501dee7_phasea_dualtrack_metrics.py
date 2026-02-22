"""phaseA_dualtrack_metrics

Revision ID: f9bb6501dee7
Revises: 003
Create Date: 2026-02-18 00:53:31.274953

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from datetime import datetime, timezone


# revision identifiers, used by Alembic.
revision: str = 'f9bb6501dee7'
down_revision: Union[str, None] = '003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_tables = set(inspector.get_table_names())

    # cooldown_records
    if "cooldown_records" not in existing_tables:
        op.create_table(
            "cooldown_records",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("symbol", sa.String(length=20), nullable=False, comment="交易对"),
            sa.Column(
                "side",
                sa.String(length=10),
                nullable=False,
                comment="方向: BUY/SELL/SHORT/COVER",
            ),
            sa.Column(
                "last_trade_ts",
                sa.Float(),
                nullable=False,
                comment="最后交易时间戳",
            ),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=True,
                comment="创建时间",
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(),
                nullable=True,
                comment="更新时间",
            ),
            sa.PrimaryKeyConstraint("id"),
        )
        with op.batch_alter_table("cooldown_records", schema=None) as batch_op:
            batch_op.create_index(
                "ix_cooldown_records_symbol_side", ["symbol", "side"], unique=True
            )

    # daily_pnl
    if "daily_pnl" not in existing_tables:
        op.create_table(
            "daily_pnl",
            sa.Column("date", sa.String(length=10), nullable=False, comment="日期 YYYY-MM-DD"),
            sa.Column("total_equity", sa.Float(), nullable=False, server_default="0", comment="总权益"),
            sa.Column("realized_pnl", sa.Float(), nullable=False, server_default="0", comment="已实现盈亏"),
            sa.Column("unrealized_pnl", sa.Float(), nullable=False, server_default="0", comment="未实现盈亏"),
            sa.Column("total_trades", sa.Integer(), nullable=False, server_default="0", comment="交易次数"),
            sa.Column("win_trades", sa.Integer(), nullable=False, server_default="0", comment="盈利交易次数"),
            sa.Column("loss_trades", sa.Integer(), nullable=False, server_default="0", comment="亏损交易次数"),
            sa.Column("max_drawdown_pct", sa.Float(), nullable=False, server_default="0", comment="最大回撤百分比"),
            sa.Column("api_cost", sa.Float(), nullable=False, server_default="0", comment="API 成本"),
            sa.Column("net_pnl", sa.Float(), nullable=False, server_default="0", comment="净盈亏"),
            sa.Column("created_at", sa.DateTime(), nullable=True, comment="创建时间"),
            sa.Column("updated_at", sa.DateTime(), nullable=True, comment="更新时间"),
            sa.PrimaryKeyConstraint("date"),
        )
        op.create_index("ix_daily_pnl_date", "daily_pnl", ["date"])

    # ai_signals: add pf_* columns (idempotent)
    #
    # 注意：SQLite 的 batch_alter_table 会通过“重建表 + DROP 原表”的方式实现 drop_column，
    # 而 signal_results 外键引用 ai_signals，重建时 DROP 会触发 FOREIGN KEY constraint failed。
    # 测试验证阶段我们只做 ADD COLUMN，不做 DROP legacy 列，避免破坏外键关系。
    if "ai_signals" in existing_tables:
        columns = {c["name"] for c in inspector.get_columns("ai_signals")}
        if "pf_direction" not in columns:
            op.add_column(
                "ai_signals",
                sa.Column(
                    "pf_direction",
                    sa.String(length=10),
                    nullable=True,
                    comment="pre-filter 建议方向: BUY/SELL/SHORT/COVER/HOLD",
                ),
            )
        if "pf_score" not in columns:
            op.add_column(
                "ai_signals",
                sa.Column(
                    "pf_score",
                    sa.Integer(),
                    nullable=True,
                    comment="pre-filter 综合得分 0-10",
                ),
            )
        if "pf_level" not in columns:
            op.add_column(
                "ai_signals",
                sa.Column(
                    "pf_level",
                    sa.String(length=10),
                    nullable=True,
                    comment="pre-filter 级别: STRONG/MODERATE/WEAK",
                ),
            )
        if "pf_reasons" not in columns:
            op.add_column(
                "ai_signals",
                sa.Column(
                    "pf_reasons",
                    sa.Text(),
                    nullable=True,
                    comment="pre-filter 触发规则（JSON）",
                ),
            )
        if "pf_agreed_with_ai" not in columns:
            op.add_column(
                "ai_signals",
                sa.Column(
                    "pf_agreed_with_ai",
                    sa.Boolean(),
                    nullable=True,
                    comment="pre-filter 方向是否与 AI 最终信号一致",
                ),
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "ai_signals" in existing_tables:
        columns = {c["name"] for c in inspector.get_columns("ai_signals")}
        with op.batch_alter_table("ai_signals", schema=None) as batch_op:
            for col in ("pf_agreed_with_ai", "pf_reasons", "pf_level", "pf_score", "pf_direction"):
                if col in columns:
                    batch_op.drop_column(col)

    if "daily_pnl" in existing_tables:
        try:
            op.drop_index("ix_daily_pnl_date", table_name="daily_pnl")
        except Exception:
            pass
        op.drop_table("daily_pnl")

    if "cooldown_records" in existing_tables:
        try:
            with op.batch_alter_table("cooldown_records", schema=None) as batch_op:
                batch_op.drop_index("ix_cooldown_records_symbol_side")
        except Exception:
            pass
        op.drop_table("cooldown_records")
