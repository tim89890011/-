"""
钢子出击 - 数据库 ORM 模型
定义所有数据表结构

安全说明：
- api_key_encrypted 和 api_secret_encrypted 字段存储加密后的 API 凭证
- 加密密钥由 backend/utils/crypto.py 管理，通过环境变量或密钥文件配置
- 字段命名带 _encrypted 后缀是为了明确标识存储的是加密数据
- 实际解密操作应在 service/router 层通过 crypto 模块完成
"""

from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    Text,
    DateTime,
    ForeignKey,
    Boolean,
    Index,
)
from sqlalchemy.orm import DeclarativeBase, relationship
from datetime import datetime, timezone


class Base(DeclarativeBase):
    """ORM 基类"""

    pass


class User(Base):
    """用户表"""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False, comment="用户名")
    password_hash = Column(String(255), nullable=False, comment="密码哈希（bcrypt）")
    exchange = Column(
        String(20), default="binance", comment="交易所代码，如 binance/okx"
    )

    # 加密存储的 API 凭证
    # 格式说明：
    # - 加密数据：enc:<Fernet加密后的字符串>
    # - 明文数据：plain:<原始字符串>（降级模式，带警告）
    # - 空值：未配置
    api_key_encrypted = Column(
        Text,
        default="",
        comment="交易所 API Key（AES加密，格式: enc:... 或 plain:...）",
    )
    api_secret_encrypted = Column(
        Text,
        default="",
        comment="交易所 API Secret（AES加密，格式: enc:... 或 plain:...）",
    )

    is_active = Column(Boolean, default=True, comment="账号是否启用")
    created_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间"
    )

    # 关联
    # 避免默认把所有聊天记录 selectin 拉出来导致内存膨胀
    chat_messages = relationship("ChatMessage", back_populates="user", lazy="select")


class AISignal(Base):
    """AI 信号表 - 记录每次 AI 分析结果"""

    __tablename__ = "ai_signals"
    # #81 修复：加索引加速 ORDER BY created_at DESC 查询
    __table_args__ = (
        Index("ix_ai_signals_created_at", "created_at"),
        Index("ix_ai_signals_symbol_created", "symbol", "created_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False, comment="交易对，如 BTCUSDT")
    signal = Column(String(10), nullable=False, comment="信号: BUY / SELL / HOLD")
    confidence = Column(Float, default=0, comment="综合置信度 0-100")
    price_at_signal = Column(Float, default=0, comment="出信号时的价格")

    # 5 个角色各自的观点（JSON 字符串）
    role_opinions = Column(Text, default="{}", comment="5个角色观点 JSON")
    # 辩论过程记录
    debate_log = Column(Text, default="", comment="辩论过程文本")
    # 综合理由
    final_reason = Column(Text, default="", comment="最终裁决理由")
    # 角色输入消息（JSON 字符串）
    role_input_messages = Column(Text, nullable=True, comment="5个角色输入消息 JSON")
    # 最终裁决输入（JSON 字符串）
    final_input_messages = Column(Text, nullable=True, comment="最终裁决输入消息 JSON")
    # 最终裁决原始输出
    final_raw_output = Column(Text, nullable=True, comment="最终裁决原始输出文本")

    # 批次/链路追踪
    batch_id = Column(String(36), nullable=True, comment="批次UUID，同一轮调度的多币种共享")
    prev_same_symbol_id = Column(Integer, nullable=True, comment="同币种上一条信号ID，便于前端快速定位对比")
    error_text = Column(Text, nullable=True, comment="分析失败时的错误信息")
    stage_timestamps = Column(Text, nullable=True, comment="各阶段耗时 JSON，如 {fetch:0.3,roles:2.1,r1:1.5}")

    risk_assessment = Column(Text, default="", comment="风险评估说明")

    # 交易建议
    risk_level = Column(
        String(10), default="中", comment="风险等级: 低/中/中高/高/极高"
    )

    # ===== Phase A/B：pre-filter 影子模式字段（仅记录不决策）=====
    pf_direction = Column(String(10), nullable=True, comment="pre-filter 建议方向: BUY/SHORT/HOLD/SELL/COVER")
    pf_score = Column(Integer, nullable=True, comment="pre-filter 综合得分(0-10)")
    pf_level = Column(String(10), nullable=True, comment="pre-filter 等级: STRONG/MODERATE/WEAK")
    pf_reasons = Column(Text, nullable=True, comment="pre-filter 触发规则（JSON）")
    pf_agreed_with_ai = Column(Boolean, nullable=True, comment="pre-filter 方向是否与 AI 一致")

    # AI 每日一句
    daily_quote = Column(Text, default="", comment="AI 每日一句")

    # 语音播报文本
    voice_text = Column(Text, default="", comment="语音播报文本")

    created_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间"
    )

    # 关联
    results = relationship("SignalResult", back_populates="signal_ref", lazy="selectin")
    snapshots = relationship("SignalSnapshot", back_populates="signal_ref", lazy="select")


class SignalResult(Base):
    """信号验证表 - 回测历史信号方向预测一致性"""

    __tablename__ = "signal_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    signal_id = Column(
        Integer, ForeignKey("ai_signals.id"), nullable=False, comment="关联信号ID"
    )

    price_after_1h = Column(Float, default=0, comment="1小时后价格")
    price_after_4h = Column(Float, default=0, comment="4小时后价格")
    price_after_24h = Column(Float, default=0, comment="24小时后价格")

    # 旧字段：保留用于向后兼容，不再更新
    actual_result = Column(
        String(10), default="", comment="[废弃] 实际结果: WIN / LOSS / NEUTRAL"
    )

    # 新字段：方向预测一致性结果
    direction_result = Column(
        String(10), default="", comment="方向一致性: CORRECT / INCORRECT / NEUTRAL"
    )
    pnl_percent = Column(Float, default=0, comment="价格变化百分比（非实际盈亏）")

    checked_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), comment="检查时间"
    )

    # 关联
    signal_ref = relationship("AISignal", back_populates="results", lazy="selectin")


class ChatMessage(Base):
    """聊天记录表"""

    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, comment="用户ID")
    role = Column(String(20), nullable=False, comment="角色: user / assistant")
    content = Column(Text, nullable=False, comment="消息内容")
    created_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间"
    )

    # 关联
    user = relationship("User", back_populates="chat_messages", lazy="select")


class AnalyzeCooldown(Base):
    """分析冷却记录（跨进程共享）"""

    __tablename__ = "analyze_cooldowns"

    symbol = Column(String(20), primary_key=True, comment="交易对")
    last_analyze_ts = Column(Float, default=0, nullable=False, comment="最后分析时间戳")
    updated_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), comment="更新时间"
    )


class CooldownRecord(Base):
    """交易冷却记录（跨重启共享）"""

    __tablename__ = "cooldown_records"
    __table_args__ = (
        Index("ix_cooldown_records_symbol_side", "symbol", "side", unique=True),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False, comment="交易对")
    side = Column(String(10), nullable=False, comment="方向: BUY/SELL/SHORT/COVER")
    last_trade_ts = Column(Float, default=0, nullable=False, comment="最后交易时间戳")
    created_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间"
    )
    updated_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), comment="更新时间"
    )


class DailyPnL(Base):
    """每日净值/盈亏快照（用于验证阶段的数据归因）"""

    __tablename__ = "daily_pnl"
    __table_args__ = (Index("ix_daily_pnl_date", "date"),)

    # 以 date 作为主键便于 upsert
    date = Column(String(10), primary_key=True, comment="日期 YYYY-MM-DD")
    total_equity = Column(Float, default=0, nullable=False, comment="总权益")
    realized_pnl = Column(Float, default=0, nullable=False, comment="已实现盈亏")
    unrealized_pnl = Column(Float, default=0, nullable=False, comment="未实现盈亏")
    total_trades = Column(Integer, default=0, nullable=False, comment="交易次数")
    win_trades = Column(Integer, default=0, nullable=False, comment="盈利交易次数")
    loss_trades = Column(Integer, default=0, nullable=False, comment="亏损交易次数")
    max_drawdown_pct = Column(Float, default=0, nullable=False, comment="最大回撤百分比")
    api_cost = Column(Float, default=0, nullable=False, comment="API 成本")
    net_pnl = Column(Float, default=0, nullable=False, comment="净盈亏=realized_pnl-api_cost")
    created_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间"
    )
    updated_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), comment="更新时间"
    )

class RevokedToken(Base):
    """已吊销 JWT（用于登出后失效）"""

    __tablename__ = "revoked_tokens"

    id = Column(Integer, primary_key=True, autoincrement=True)
    jti = Column(String(64), unique=True, nullable=False, comment="JWT 唯一标识")
    username = Column(String(50), nullable=False, comment="用户名")
    expires_at = Column(DateTime, nullable=False, comment="Token 过期时间")
    revoked_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), comment="吊销时间"
    )


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    __table_args__ = (
        Index("ix_refresh_tokens_username", "username"),
        Index("ix_refresh_tokens_expires_at", "expires_at"),
        Index("ix_refresh_tokens_revoked", "revoked"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    jti = Column(
        String(64), unique=True, nullable=False, comment="Refresh Token 唯一标识"
    )
    username = Column(String(50), nullable=False, comment="用户名")
    expires_at = Column(DateTime, nullable=False, comment="Refresh Token 过期时间")
    revoked = Column(Boolean, default=False, nullable=False, comment="是否已吊销")
    created_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间"
    )
    revoked_at = Column(DateTime, nullable=True, comment="吊销时间")


class QuotaDailyStat(Base):
    __tablename__ = "quota_daily_stats"

    date = Column(String(10), primary_key=True, comment="日期 YYYY-MM-DD")
    total_calls = Column(Integer, default=0, nullable=False, comment="总调用次数")
    analysis_calls = Column(Integer, default=0, nullable=False, comment="分析调用次数")
    chat_calls = Column(Integer, default=0, nullable=False, comment="聊天调用次数")
    reasoner_calls = Column(Integer, default=0, nullable=False, comment="R1 调用次数")
    tokens_input = Column(Integer, default=0, nullable=False, comment="输入 token 总数")
    tokens_output = Column(
        Integer, default=0, nullable=False, comment="输出 token 总数"
    )
    estimated_cost = Column(Float, default=0.0, nullable=False, comment="估算成本")
    updated_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), comment="更新时间"
    )


class AuthRateLimit(Base):
    """认证限流（持久化，跨重启保留）"""

    __tablename__ = "auth_rate_limits"

    id = Column(Integer, primary_key=True, autoincrement=True)
    rate_key = Column(
        String(120), unique=True, nullable=False, comment="限流键，如 login:ip"
    )
    bucket = Column(String(20), nullable=False, comment="限流桶：login/register")
    first_ts = Column(Float, default=0, nullable=False, comment="窗口首个请求时间戳")
    last_ts = Column(Float, default=0, nullable=False, comment="最后请求时间戳")
    count = Column(Integer, default=0, nullable=False, comment="窗口内次数")
    updated_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), comment="更新时间"
    )


class NotificationLog(Base):
    """通知记录表 - 用于失败重试和降级记录"""

    __tablename__ = "notification_logs"
    __table_args__ = (
        Index("ix_notification_logs_status", "status"),
        Index("ix_notification_logs_type", "type"),
        Index("ix_notification_logs_created_at", "created_at"),
        Index("ix_notification_logs_status_created", "status", "created_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    type = Column(
        String(20),
        nullable=False,
        comment="通知类型: trade_signal/price_alert/system_alert/error/info",
    )
    content = Column(Text, nullable=False, comment="通知内容")
    status = Column(
        String(20),
        nullable=False,
        default="pending",
        comment="状态: pending/sent/failed/fallback",
    )
    error_msg = Column(Text, default="", comment="错误信息")
    retry_count = Column(Integer, default=0, comment="重试次数")
    metadata_json = Column(
        "metadata", Text, default="", comment="附加元数据（JSON字符串）"
    )
    created_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间"
    )
    updated_at = Column(DateTime, nullable=True, comment="更新时间")


class UserSettings(Base):
    """用户策略配置表 - 每个用户独立的交易策略参数"""

    __tablename__ = "user_settings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False, comment="用户ID")

    # 策略预设模式：steady(稳健) / aggressive(激进) / custom(自定义)
    strategy_mode = Column(String(20), default="steady", comment="策略模式")

    # 仓位管理
    amount_usdt = Column(Float, default=50.0, comment="每单保证金(USDT)")
    amount_pct = Column(Float, default=3.0, comment="每单占可用余额百分比")
    max_position_usdt = Column(Float, default=500.0, comment="单币种持仓上限(USDT)")
    max_position_pct = Column(Float, default=20.0, comment="单币种持仓占比上限")
    daily_limit_usdt = Column(Float, default=500.0, comment="每日交易限额(USDT)")

    # 交易参数
    min_confidence = Column(Integer, default=65, comment="最低置信度阈值")
    cooldown_seconds = Column(Integer, default=600, comment="开仓冷却(秒)")
    close_cooldown_seconds = Column(Integer, default=30, comment="平仓冷却(秒)")
    leverage = Column(Integer, default=2, comment="杠杆倍数")
    margin_mode = Column(String(20), default="isolated", comment="保证金模式")

    # 止盈止损
    take_profit_pct = Column(Float, default=3.0, comment="止盈百分比")
    stop_loss_pct = Column(Float, default=1.5, comment="止损百分比")
    trailing_stop_enabled = Column(Boolean, default=True, comment="移动止损开关")
    position_timeout_hours = Column(Integer, default=24, comment="持仓超时(小时)")

    # 交易币种（逗号分隔）
    symbols = Column(String(500), default="BTCUSDT,ETHUSDT", comment="允许交易的币种")

    # Telegram 通知
    tg_enabled = Column(Boolean, default=False, comment="Telegram通知开关")
    tg_chat_id = Column(String(100), default="", comment="Telegram Chat ID")

    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), comment="更新时间")


# 导入交易记录模型，让 Base.metadata.create_all 自动建表
from backend.trading.models import TradeRecord, PositionMeta  # noqa: F401, E402


class PasswordResetToken(Base):
    """密码重置令牌表"""

    __tablename__ = "password_reset_tokens"

    id = Column(Integer, primary_key=True, autoincrement=True)
    token = Column(
        String(64), unique=True, nullable=False, comment="重置令牌（随机字符串）"
    )
    username = Column(String(50), nullable=False, comment="申请重置的用户名")
    expires_at = Column(DateTime, nullable=False, comment="令牌过期时间")
    used = Column(Boolean, default=False, comment="是否已使用")
    admin_approved = Column(Boolean, default=False, comment="管理员是否已批准")
    created_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间"
    )
    used_at = Column(DateTime, nullable=True, comment="使用时间")

    __table_args__ = (
        Index("ix_password_reset_tokens_username", "username"),
        Index("ix_password_reset_tokens_token", "token"),
    )


class SignalSnapshot(Base):

    __tablename__ = "signal_snapshots"
    __table_args__ = (
        Index("ix_signal_snapshots_signal_id", "signal_id"),
        Index("ix_signal_snapshots_symbol_created", "symbol", "created_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    signal_id = Column(
        Integer, ForeignKey("ai_signals.id"), nullable=False, comment="关联 ai_signals.id"
    )
    symbol = Column(String(20), nullable=False, comment="交易对")
    horizon = Column(String(10), nullable=True, comment="信号周期: 15m/1h/4h")
    signal = Column(String(10), nullable=False, comment="最终信号")
    confidence = Column(Float, default=0, comment="最终置信度")
    price_at_signal = Column(Float, default=0, comment="出信号时价格")

    kline_ref = Column(Text, nullable=True, comment="K线数据窗口引用 JSON")
    indicators_snapshot = Column(Text, nullable=True, comment="全量指标快照 JSON")
    market_data_snapshot = Column(Text, nullable=True, comment="市场数据快照 JSON")
    regime = Column(String(20), nullable=True, comment="市场状态: trend/range/volatile")

    prefilter_result = Column(Text, nullable=True, comment="pre-filter 结果 JSON")
    ai_votes = Column(Text, nullable=True, comment="5角色各自输出 JSON")
    final_decision = Column(Text, nullable=True, comment="R1 最终裁决 JSON")
    post_filters = Column(Text, nullable=True, comment="后置过滤器结果 JSON")
    riskgate_result = Column(Text, nullable=True, comment="RiskGate 各项检查 JSON")

    execution_intent = Column(Boolean, default=False, comment="本次是否计划执行交易")

    created_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), comment="创建时间"
    )

    # 关联
    signal_ref = relationship("AISignal", back_populates="snapshots", lazy="select")
