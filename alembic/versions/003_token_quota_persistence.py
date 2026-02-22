# pyright: reportAttributeAccessIssue=false
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table_name: str, column_name: str) -> bool:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if table_name not in inspector.get_table_names():
        return False
    columns = [col["name"] for col in inspector.get_columns(table_name)]
    return column_name in columns


def _table_exists(table_name: str) -> bool:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    if _table_exists("ai_signals") and not _column_exists(
        "ai_signals", "risk_assessment"
    ):
        op.add_column(
            "ai_signals",
            sa.Column(
                "risk_assessment", sa.Text(), nullable=True, comment="风险评估说明"
            ),
        )
        op.execute(
            text(
                "UPDATE ai_signals SET risk_assessment = '' WHERE risk_assessment IS NULL"
            )
        )

    if not _table_exists("refresh_tokens"):
        op.create_table(
            "refresh_tokens",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column(
                "jti",
                sa.String(length=64),
                nullable=False,
                comment="Refresh Token 唯一标识",
            ),
            sa.Column(
                "username", sa.String(length=50), nullable=False, comment="用户名"
            ),
            sa.Column(
                "expires_at",
                sa.DateTime(),
                nullable=False,
                comment="Refresh Token 过期时间",
            ),
            sa.Column(
                "revoked",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("0"),
                comment="是否已吊销",
            ),
            sa.Column("created_at", sa.DateTime(), nullable=True, comment="创建时间"),
            sa.Column("revoked_at", sa.DateTime(), nullable=True, comment="吊销时间"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("jti"),
        )
        op.create_index("ix_refresh_tokens_username", "refresh_tokens", ["username"])
        op.create_index(
            "ix_refresh_tokens_expires_at", "refresh_tokens", ["expires_at"]
        )
        op.create_index("ix_refresh_tokens_revoked", "refresh_tokens", ["revoked"])

    if not _table_exists("quota_daily_stats"):
        op.create_table(
            "quota_daily_stats",
            sa.Column(
                "date", sa.String(length=10), nullable=False, comment="日期 YYYY-MM-DD"
            ),
            sa.Column(
                "total_calls",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
                comment="总调用次数",
            ),
            sa.Column(
                "analysis_calls",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
                comment="分析调用次数",
            ),
            sa.Column(
                "chat_calls",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
                comment="聊天调用次数",
            ),
            sa.Column(
                "reasoner_calls",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
                comment="R1 调用次数",
            ),
            sa.Column(
                "tokens_input",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
                comment="输入 token 总数",
            ),
            sa.Column(
                "tokens_output",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
                comment="输出 token 总数",
            ),
            sa.Column(
                "estimated_cost",
                sa.Float(),
                nullable=False,
                server_default=sa.text("0"),
                comment="估算成本",
            ),
            sa.Column("updated_at", sa.DateTime(), nullable=True, comment="更新时间"),
            sa.PrimaryKeyConstraint("date"),
        )


def downgrade() -> None:
    if _table_exists("quota_daily_stats"):
        op.drop_table("quota_daily_stats")

    if _table_exists("refresh_tokens"):
        op.drop_index("ix_refresh_tokens_revoked", table_name="refresh_tokens")
        op.drop_index("ix_refresh_tokens_expires_at", table_name="refresh_tokens")
        op.drop_index("ix_refresh_tokens_username", table_name="refresh_tokens")
        op.drop_table("refresh_tokens")

    if _column_exists("ai_signals", "risk_assessment"):
        conn = op.get_bind()
        dialect = conn.engine.dialect.name
        if dialect == "sqlite":
            op.create_table(
                "ai_signals_tmp",
                sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
                sa.Column("symbol", sa.String(length=20), nullable=False),
                sa.Column("signal", sa.String(length=10), nullable=False),
                sa.Column("confidence", sa.Float(), nullable=True),
                sa.Column("price_at_signal", sa.Float(), nullable=True),
                sa.Column("role_opinions", sa.Text(), nullable=True),
                sa.Column("debate_log", sa.Text(), nullable=True),
                sa.Column("final_reason", sa.Text(), nullable=True),
                sa.Column("risk_level", sa.String(length=10), nullable=True),
                sa.Column("position_pct", sa.Float(), nullable=True),
                sa.Column("leverage", sa.Integer(), nullable=True),
                sa.Column("stop_loss_pct", sa.Float(), nullable=True),
                sa.Column("take_profit_pct", sa.Float(), nullable=True),
                sa.Column("daily_quote", sa.Text(), nullable=True),
                sa.Column("voice_text", sa.Text(), nullable=True),
                sa.Column("created_at", sa.DateTime(), nullable=True),
                sa.PrimaryKeyConstraint("id"),
            )
            op.execute(
                text("""
                INSERT INTO ai_signals_tmp(
                    id, symbol, signal, confidence, price_at_signal,
                    role_opinions, debate_log, final_reason, risk_level,
                    position_pct, leverage, stop_loss_pct, take_profit_pct,
                    daily_quote, voice_text, created_at
                )
                SELECT
                    id, symbol, signal, confidence, price_at_signal,
                    role_opinions, debate_log, final_reason, risk_level,
                    position_pct, leverage, stop_loss_pct, take_profit_pct,
                    daily_quote, voice_text, created_at
                FROM ai_signals
            """)
            )
            op.drop_table("ai_signals")
            op.rename_table("ai_signals_tmp", "ai_signals")
        else:
            op.drop_column("ai_signals", "risk_assessment")
