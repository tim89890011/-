"""合规性修复 - 移除敏感字段，添加风险评估

Revision ID: 002
Revises: 001
Create Date: 2025-02-15 04:30:00.000000

变更内容：
1. ai_signals 表：
   - 移除: position_pct, leverage, stop_loss_pct, take_profit_pct
   - 添加: risk_assessment (风险评估 JSON)

2. signal_results 表：
   - 添加: direction_result (方向一致性结果)

3. 新增 notifications 表：
   - 用户通知记录表

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = '002'
down_revision: Union[str, None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade_ai_signals() -> None:
    """升级 ai_signals 表：移除敏感字段，添加风险评估"""
    # SQLite 不支持 DROP COLUMN，需要使用表重建策略
    # 1. 创建新表（不含敏感字段）
    op.create_table(
        'ai_signals_new',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('symbol', sa.String(length=20), nullable=False, comment='交易对，如 BTCUSDT'),
        sa.Column('signal', sa.String(length=10), nullable=False, comment='信号: BUY / SELL / HOLD'),
        sa.Column('confidence', sa.Float(), nullable=True, comment='综合置信度 0-100'),
        sa.Column('price_at_signal', sa.Float(), nullable=True, comment='出信号时的价格'),
        sa.Column('role_opinions', sa.Text(), nullable=True, comment='5个角色观点 JSON'),
        sa.Column('debate_log', sa.Text(), nullable=True, comment='辩论过程文本'),
        sa.Column('final_reason', sa.Text(), nullable=True, comment='最终裁决理由'),
        sa.Column('risk_level', sa.String(length=10), nullable=True, comment='风险等级: 低/中/中高/高/极高'),
        sa.Column('risk_assessment', sa.Text(), nullable=True, comment='风险评估 JSON（不含具体仓位/杠杆建议）'),
        sa.Column('daily_quote', sa.Text(), nullable=True, comment='AI 每日一句'),
        sa.Column('voice_text', sa.Text(), nullable=True, comment='语音播报文本'),
        sa.Column('created_at', sa.DateTime(), nullable=True, comment='创建时间'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # 2. 创建索引
    op.create_index('ix_ai_signals_new_created_at', 'ai_signals_new', ['created_at'])
    op.create_index('ix_ai_signals_new_symbol_created', 'ai_signals_new', ['symbol', 'created_at'])
    
    # 3. 复制数据（跳过被移除的字段）
    op.execute(text("""
        INSERT INTO ai_signals_new (
            id, symbol, signal, confidence, price_at_signal,
            role_opinions, debate_log, final_reason, risk_level,
            risk_assessment, daily_quote, voice_text, created_at
        )
        SELECT 
            id, symbol, signal, confidence, price_at_signal,
            role_opinions, debate_log, final_reason, risk_level,
            NULL, daily_quote, voice_text, created_at
        FROM ai_signals
    """))
    
    # 4. 删除旧表
    op.drop_index('ix_ai_signals_symbol_created', table_name='ai_signals')
    op.drop_index('ix_ai_signals_created_at', table_name='ai_signals')
    op.drop_table('ai_signals')
    
    # 5. 重命名新表
    op.rename_table('ai_signals_new', 'ai_signals')
    op.rename_table('ix_ai_signals_new_created_at', 'ix_ai_signals_created_at')
    op.rename_table('ix_ai_signals_new_symbol_created', 'ix_ai_signals_symbol_created')


def downgrade_ai_signals() -> None:
    """降级 ai_signals 表：恢复敏感字段"""
    # 1. 创建旧表结构
    op.create_table(
        'ai_signals_old',
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
    
    # 2. 创建索引
    op.create_index('ix_ai_signals_old_created_at', 'ai_signals_old', ['created_at'])
    op.create_index('ix_ai_signals_old_symbol_created', 'ai_signals_old', ['symbol', 'created_at'])
    
    # 3. 复制数据
    op.execute(text("""
        INSERT INTO ai_signals_old (
            id, symbol, signal, confidence, price_at_signal,
            role_opinions, debate_log, final_reason, risk_level,
            position_pct, leverage, stop_loss_pct, take_profit_pct,
            daily_quote, voice_text, created_at
        )
        SELECT 
            id, symbol, signal, confidence, price_at_signal,
            role_opinions, debate_log, final_reason, risk_level,
            0, 0, 0, 0,
            daily_quote, voice_text, created_at
        FROM ai_signals
    """))
    
    # 4. 删除新表
    op.drop_index('ix_ai_signals_symbol_created', table_name='ai_signals')
    op.drop_index('ix_ai_signals_created_at', table_name='ai_signals')
    op.drop_table('ai_signals')
    
    # 5. 重命名旧表
    op.rename_table('ai_signals_old', 'ai_signals')


def upgrade_signal_results() -> None:
    """升级 signal_results 表：添加 direction_result 字段"""
    # 检查字段是否已存在
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('signal_results')]
    
    if 'direction_result' not in columns:
        op.add_column(
            'signal_results',
            sa.Column('direction_result', sa.String(length=10), nullable=True, comment='方向一致性: CORRECT / INCORRECT / NEUTRAL')
        )


def downgrade_signal_results() -> None:
    """降级 signal_results 表：移除 direction_result 字段"""
    # SQLite 不支持 DROP COLUMN，需要使用表重建
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('signal_results')]
    
    if 'direction_result' in columns:
        # 创建新表（不含 direction_result）
        op.create_table(
            'signal_results_new',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('signal_id', sa.Integer(), nullable=False, comment='关联信号ID'),
            sa.Column('price_after_1h', sa.Float(), nullable=True, comment='1小时后价格'),
            sa.Column('price_after_4h', sa.Float(), nullable=True, comment='4小时后价格'),
            sa.Column('price_after_24h', sa.Float(), nullable=True, comment='24小时后价格'),
            sa.Column('actual_result', sa.String(length=10), nullable=True, comment='[废弃] 实际结果: WIN / LOSS / NEUTRAL'),
            sa.Column('pnl_percent', sa.Float(), nullable=True, comment='价格变化百分比（非实际盈亏）'),
            sa.Column('checked_at', sa.DateTime(), nullable=True, comment='检查时间'),
            sa.ForeignKeyConstraint(['signal_id'], ['ai_signals.id'], ),
            sa.PrimaryKeyConstraint('id')
        )
        
        # 复制数据
        op.execute(text("""
            INSERT INTO signal_results_new (
                id, signal_id, price_after_1h, price_after_4h, price_after_24h,
                actual_result, pnl_percent, checked_at
            )
            SELECT 
                id, signal_id, price_after_1h, price_after_4h, price_after_24h,
                actual_result, pnl_percent, checked_at
            FROM signal_results
        """))
        
        # 删除旧表，重命名新表
        op.drop_table('signal_results')
        op.rename_table('signal_results_new', 'signal_results')


def create_notifications_table() -> None:
    """创建 notifications 表"""
    op.create_table(
        'notifications',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False, comment='用户ID'),
        sa.Column('type', sa.String(length=20), nullable=False, comment='通知类型: signal / system / trade'),
        sa.Column('title', sa.String(length=100), nullable=False, comment='通知标题'),
        sa.Column('content', sa.Text(), nullable=False, comment='通知内容'),
        sa.Column('data', sa.Text(), nullable=True, comment='附加数据 JSON'),
        sa.Column('is_read', sa.Boolean(), nullable=True, comment='是否已读'),
        sa.Column('read_at', sa.DateTime(), nullable=True, comment='阅读时间'),
        sa.Column('created_at', sa.DateTime(), nullable=True, comment='创建时间'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    
    # 创建索引
    op.create_index('ix_notifications_user_id', 'notifications', ['user_id'])
    op.create_index('ix_notifications_created_at', 'notifications', ['created_at'])
    op.create_index('ix_notifications_user_read', 'notifications', ['user_id', 'is_read'])


def drop_notifications_table() -> None:
    """删除 notifications 表"""
    op.drop_index('ix_notifications_user_read', table_name='notifications')
    op.drop_index('ix_notifications_created_at', table_name='notifications')
    op.drop_index('ix_notifications_user_id', table_name='notifications')
    op.drop_table('notifications')


def upgrade() -> None:
    """执行升级迁移"""
    # 1. 修复 ai_signals 表
    upgrade_ai_signals()
    
    # 2. 修复 signal_results 表
    upgrade_signal_results()
    
    # 3. 创建 notifications 表
    create_notifications_table()


def downgrade() -> None:
    """执行降级迁移"""
    # 1. 删除 notifications 表
    drop_notifications_table()
    
    # 2. 降级 signal_results 表
    downgrade_signal_results()
    
    # 3. 降级 ai_signals 表
    downgrade_ai_signals()
