"""初始迁移 - 创建所有基础表

Revision ID: 001
Revises: 
Create Date: 2025-02-15 04:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """创建所有基础表结构"""
    
    # 创建 users 表
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('username', sa.String(length=50), nullable=False, comment='用户名'),
        sa.Column('password_hash', sa.String(length=255), nullable=False, comment='密码哈希（bcrypt）'),
        sa.Column('exchange', sa.String(length=20), nullable=True, comment='交易所代码，如 binance/okx'),
        sa.Column('api_key_encrypted', sa.Text(), nullable=True, comment='交易所 API Key（AES加密，格式: enc:... 或 plain:...）'),
        sa.Column('api_secret_encrypted', sa.Text(), nullable=True, comment='交易所 API Secret（AES加密，格式: enc:... 或 plain:...）'),
        sa.Column('is_active', sa.Boolean(), nullable=True, comment='账号是否启用'),
        sa.Column('created_at', sa.DateTime(), nullable=True, comment='创建时间'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('username')
    )
    
    # 创建 ai_signals 表
    op.create_table(
        'ai_signals',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('symbol', sa.String(length=20), nullable=False, comment='交易对，如 BTCUSDT'),
        sa.Column('signal', sa.String(length=10), nullable=False, comment='信号: BUY / SELL / HOLD'),
        sa.Column('confidence', sa.Float(), nullable=True, comment='综合置信度 0-100'),
        sa.Column('price_at_signal', sa.Float(), nullable=True, comment='出信号时的价格'),
        sa.Column('role_opinions', sa.Text(), nullable=True, comment='5个角色观点 JSON'),
        sa.Column('debate_log', sa.Text(), nullable=True, comment='辩论过程文本'),
        sa.Column('final_reason', sa.Text(), nullable=True, comment='最终裁决理由'),
        sa.Column('risk_level', sa.String(length=10), nullable=True, comment='风险等级: 低/中/中高/高/极高'),
        sa.Column('position_pct', sa.Float(), nullable=True, comment='建议仓位百分比'),
        sa.Column('leverage', sa.Integer(), nullable=True, comment='建议杠杆倍数'),
        sa.Column('stop_loss_pct', sa.Float(), nullable=True, comment='建议止损百分比'),
        sa.Column('take_profit_pct', sa.Float(), nullable=True, comment='建议止盈百分比'),
        sa.Column('daily_quote', sa.Text(), nullable=True, comment='AI 每日一句'),
        sa.Column('voice_text', sa.Text(), nullable=True, comment='语音播报文本'),
        sa.Column('created_at', sa.DateTime(), nullable=True, comment='创建时间'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # 创建 ai_signals 索引
    op.create_index('ix_ai_signals_created_at', 'ai_signals', ['created_at'])
    op.create_index('ix_ai_signals_symbol_created', 'ai_signals', ['symbol', 'created_at'])
    
    # 创建 signal_results 表
    op.create_table(
        'signal_results',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('signal_id', sa.Integer(), nullable=False, comment='关联信号ID'),
        sa.Column('price_after_1h', sa.Float(), nullable=True, comment='1小时后价格'),
        sa.Column('price_after_4h', sa.Float(), nullable=True, comment='4小时后价格'),
        sa.Column('price_after_24h', sa.Float(), nullable=True, comment='24小时后价格'),
        sa.Column('actual_result', sa.String(length=10), nullable=True, comment='[废弃] 实际结果: WIN / LOSS / NEUTRAL'),
        sa.Column('direction_result', sa.String(length=10), nullable=True, comment='方向一致性: CORRECT / INCORRECT / NEUTRAL'),
        sa.Column('pnl_percent', sa.Float(), nullable=True, comment='价格变化百分比（非实际盈亏）'),
        sa.Column('checked_at', sa.DateTime(), nullable=True, comment='检查时间'),
        sa.ForeignKeyConstraint(['signal_id'], ['ai_signals.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    
    # 创建 chat_messages 表
    op.create_table(
        'chat_messages',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False, comment='用户ID'),
        sa.Column('role', sa.String(length=20), nullable=False, comment='角色: user / assistant'),
        sa.Column('content', sa.Text(), nullable=False, comment='消息内容'),
        sa.Column('created_at', sa.DateTime(), nullable=True, comment='创建时间'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    
    # 创建 analyze_cooldowns 表
    op.create_table(
        'analyze_cooldowns',
        sa.Column('symbol', sa.String(length=20), nullable=False, comment='交易对'),
        sa.Column('last_analyze_ts', sa.Float(), nullable=False, comment='最后分析时间戳'),
        sa.Column('updated_at', sa.DateTime(), nullable=True, comment='更新时间'),
        sa.PrimaryKeyConstraint('symbol')
    )
    
    # 创建 revoked_tokens 表
    op.create_table(
        'revoked_tokens',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('jti', sa.String(length=64), nullable=False, comment='JWT 唯一标识'),
        sa.Column('username', sa.String(length=50), nullable=False, comment='用户名'),
        sa.Column('expires_at', sa.DateTime(), nullable=False, comment='Token 过期时间'),
        sa.Column('revoked_at', sa.DateTime(), nullable=True, comment='吊销时间'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('jti')
    )
    
    # 创建 auth_rate_limits 表
    op.create_table(
        'auth_rate_limits',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('rate_key', sa.String(length=120), nullable=False, comment='限流键，如 login:ip'),
        sa.Column('bucket', sa.String(length=20), nullable=False, comment='限流桶：login/register'),
        sa.Column('first_ts', sa.Float(), nullable=False, comment='窗口首个请求时间戳'),
        sa.Column('last_ts', sa.Float(), nullable=False, comment='最后请求时间戳'),
        sa.Column('count', sa.Integer(), nullable=False, comment='窗口内次数'),
        sa.Column('updated_at', sa.DateTime(), nullable=True, comment='更新时间'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('rate_key')
    )


def downgrade() -> None:
    """降级：删除所有表"""
    op.drop_table('auth_rate_limits')
    op.drop_table('revoked_tokens')
    op.drop_table('analyze_cooldowns')
    op.drop_table('chat_messages')
    op.drop_table('signal_results')
    op.drop_index('ix_ai_signals_symbol_created', table_name='ai_signals')
    op.drop_index('ix_ai_signals_created_at', table_name='ai_signals')
    op.drop_table('ai_signals')
    op.drop_table('users')
