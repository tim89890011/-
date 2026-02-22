"""
钢子出击 - 全局配置管理
从 .env 文件加载所有配置项
"""
# pyright: reportMissingImports=false

from pydantic_settings import BaseSettings
from pydantic import Field
import os
from typing import Any

# 确保从项目根目录加载 .env
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Settings(BaseSettings):
    """全局配置，自动从 .env 读取"""

    # DeepSeek API
    DEEPSEEK_API_KEY: str = Field(default="sk-xxx", description="DeepSeek API 密钥")
    DEEPSEEK_API_KEY_FILE: str = Field(
        default="", description="DeepSeek API 密钥文件路径"
    )
    DEEPSEEK_BASE_URL: str = Field(
        default="https://api.deepseek.com", description="DeepSeek API 地址"
    )

    # Qwen（DashScope OpenAI 兼容）API
    QWEN_API_KEY: str = Field(default="", description="千问（DashScope）API Key")
    QWEN_API_KEY_FILE: str = Field(default="", description="千问 API Key 文件路径")
    # 中国大陆：https://dashscope.aliyuncs.com/compatible-mode/v1
    QWEN_BASE_URL: str = Field(
        default="https://dashscope.aliyuncs.com/compatible-mode/v1",
        description="千问 OpenAI 兼容 API Base URL",
    )

    # JWT 认证
    JWT_SECRET: str = Field(default="", description="JWT 签名密钥（必填，留空将阻止启动）")
    JWT_ALGORITHM: str = Field(default="HS256", description="JWT 算法")
    JWT_ACCESS_EXPIRE_MINUTES: int = Field(
        default=30, description="Access Token 过期分钟数"
    )
    JWT_REFRESH_EXPIRE_DAYS: int = Field(
        default=7, description="Refresh Token 过期天数"
    )

    # 数据库
    DATABASE_URL: str = Field(
        default="sqlite+aiosqlite:///./data/gangzi.db", description="数据库连接地址"
    )

    # 管理员账号
    ADMIN_USERNAME: str = Field(default="admin", description="管理员用户名")
    ADMIN_PASSWORD: str = Field(default="admin123", description="管理员密码")
    ENABLE_PUBLIC_REGISTER: bool = Field(default=False, description="是否开放公开注册")
    RESET_REQUIRE_ADMIN_APPROVAL: bool = Field(
        default=True, description="密码重置是否必须管理员确认"
    )
    ALLOW_WEAK_ADMIN_PASSWORD: bool = Field(
        default=False, description="是否允许弱管理员密码启动"
    )
    ALLOW_DEFAULT_JWT_SECRET: bool = Field(
        default=False, description="是否允许未配置 JWT_SECRET 启动"
    )
    ALLOW_PLAINTEXT_API_KEYS: bool = Field(
        default=False, description="是否允许 API Key 不加密存储"
    )

    # 服务器
    HOST: str = Field(default="127.0.0.1", description="监听地址（生产环境通过 .env 设为 0.0.0.0）")
    PORT: int = Field(default=8000, description="监听端口")

    # Telegram
    TG_BOT_TOKEN: str = Field(default="", description="Telegram Bot Token")
    TG_CHAT_ID: str = Field(default="", description="Telegram Chat ID")

    # Telegram 重试配置
    TG_MAX_RETRIES: int = Field(default=3, description="Telegram 最大重试次数")
    TG_RETRY_BASE_DELAY: float = Field(
        default=1.0, description="Telegram 重试基础延迟（秒）"
    )
    TG_ENABLE_QUEUE: bool = Field(default=False, description="是否启用消息队列")
    TG_QUEUE_MAX_SIZE: int = Field(default=1000, description="消息队列最大长度")
    TG_RATE_LIMIT: float = Field(default=1.0, description="消息队列发送间隔（秒）")
    TG_LOG_SUCCESS: bool = Field(
        default=False, description="是否记录成功发送的通知到数据库"
    )

    # #12 修复：CORS 域名白名单（生产部署时配置）
    ALLOWED_ORIGIN: str = Field(default="", description="额外允许的 CORS 来源域名")
    TRUSTED_PROXY_IPS: str = Field(
        default="127.0.0.1", description="可信反代 IP 白名单（逗号分隔），仅这些来源才信任 X-Forwarded-For"
    )

    # ============ API 配额配置 ============
    ENABLE_QUOTA_LIMIT: bool = Field(default=True, description="是否启用 API 配额限制")
    DAILY_API_QUOTA: int = Field(default=10000, description="每日 API 调用上限")
    QUOTA_WARNING_THRESHOLD: float = Field(
        default=0.8, description="配额警告阈值（0-1）"
    )
    QUOTA_CRITICAL_THRESHOLD: float = Field(
        default=0.9, description="配额危险阈值（0-1）"
    )

    # ============ 成本配置 ============
    DEEPSEEK_CHAT_COST_PER_1K: float = Field(
        default=0.001, description="Chat V3 每千 token 成本（元）"
    )
    DEEPSEEK_R1_COST_PER_1K: float = Field(
        default=0.003, description="Reasoner R1 每千 token 成本（元）"
    )

    # ============ 自动交易配置 ============
    TRADE_ENABLED: bool = Field(default=False, description="是否启用自动交易")
    BINANCE_TESTNET_API_KEY: str = Field(
        default="", description="币安模拟盘 API Key"
    )
    BINANCE_TESTNET_API_SECRET: str = Field(
        default="", description="币安模拟盘 API Secret"
    )
    TRADE_AMOUNT_USDT: float = Field(
        default=100.0, description="每次开仓保证金（USDT），作为百分比模式的兜底上限"
    )
    TRADE_AMOUNT_PCT: float = Field(
        default=5.0, description="每次开仓保证金占可用余额百分比（0=禁用，使用固定值）"
    )
    TRADE_SYMBOLS: str = Field(
        default="BTCUSDT,ETHUSDT", description="允许自动交易的币种列表（逗号分隔）"
    )
    TRADE_MIN_CONFIDENCE: int = Field(
        default=60, description="全局最低置信度阈值（低于此值不执行交易）"
    )
    TRADE_MIN_CONF_BUY: int = Field(
        default=60, description="BUY/COVER（做多方向）最低置信度"
    )
    TRADE_MIN_CONF_SHORT: int = Field(
        default=70, description="SHORT（开空）最低置信度"
    )
    TRADE_MIN_CONF_SELL: int = Field(
        default=80, description="SELL（平多信号）最低置信度，准确率较低需高门槛"
    )
    # ============ 分层置信度阈值（方案B：主流低门槛，山寨高门槛） ============
    TRADE_TIERED_CONFIDENCE_ENABLED: bool = Field(
        default=False, description="是否启用按币种分层的置信度门槛（true=启用，false=全局统一）"
    )
    TRADE_TIER1_SYMBOLS: str = Field(
        default="BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT",
        description="Tier1 主流币列表（逗号分隔），这些币使用基础门槛",
    )
    TRADE_ALTCOIN_CONF_BUY_DELTA: int = Field(
        default=0,
        description="非 Tier1 币种 BUY/COVER 置信度门槛增量（在 TRADE_MIN_CONF_BUY 基础上加）",
    )
    TRADE_ALTCOIN_CONF_SHORT_DELTA: int = Field(
        default=0,
        description="非 Tier1 币种 SHORT 置信度门槛增量（在 TRADE_MIN_CONF_SHORT 基础上加）",
    )
    TRADE_ALTCOIN_CONF_SELL_DELTA: int = Field(
        default=0,
        description="非 Tier1 币种 SELL 置信度门槛增量（在 TRADE_MIN_CONF_SELL 基础上加）",
    )
    TRADE_SELL_CLOSE_CONFIDENCE: int = Field(
        default=85,
        description="SELL 信号直接平多阈值（与 TRADE_FLIP_CONFIDENCE 分离，避免互相影响）",
    )
    TRADE_FLIP_CONFIDENCE: int = Field(
        default=85,
        description="强制平仓/翻仓阈值：当反向信号置信度 >= 此值时，允许直接平仓或先平再反向开仓（默认 85）",
    )
    TRADE_MAX_POSITION_USDT: float = Field(
        default=500.0, description="单币种最大持仓名义价值(USDT)兜底上限"
    )
    TRADE_MAX_POSITION_PCT: float = Field(
        default=30.0, description="单币种最大持仓名义价值占账户总资金百分比（0=禁用，使用固定值）"
    )
    TRADE_DAILY_LIMIT_USDT: float = Field(
        default=1000.0, description="每日交易限额(USDT)，超过停止交易"
    )
    TRADE_BALANCE_UTILIZATION_PCT: float = Field(
        default=80.0,
        description="资金利用率上限（%）：只动用可用余额的 N%，默认 80（留 20% 备用）",
    )
    TRADE_COOLDOWN_SECONDS: int = Field(
        default=1200, description="BUY 冷却时间(秒)，默认20分钟"
    )
    TRADE_MIN_HOLD_SECONDS: int = Field(
        default=300,
        description="最短持仓时间（秒）：开仓后 N 秒内禁止主动平仓（SELL/COVER/止盈/移动止盈），仅允许止损触发",
    )
    TRADE_LEVERAGE: int = Field(
        default=3, description="合约杠杆倍数（默认3x）"
    )
    TRADE_MARGIN_MODE: str = Field(
        default="isolated", description="保证金模式：isolated(逐仓) / cross(全仓)"
    )
    TRADE_TAKE_PROFIT_PCT: float = Field(
        default=4.0, description="止盈百分比-价格维度（3x杠杆下保证金收益约12%）"
    )
    TRADE_STOP_LOSS_PCT: float = Field(
        default=2.0, description="止损百分比-价格维度（3x杠杆下保证金亏损约6%）"
    )
    TRADE_TRAILING_STOP_ENABLED: bool = Field(
        default=True, description="是否启用移动止盈（盈利时自动上移止损位）"
    )
    TRADE_POSITION_TIMEOUT_HOURS: int = Field(
        default=24, description="持仓超时（小时），超时且无盈利自动平仓（0=禁用）"
    )

    # ============ 止损磨损防护 ============
    TRADE_SL_COOLDOWN_MULTIPLIER: float = Field(
        default=2.0, description="止损后冷却时间倍率（止损后冷却 = 正常冷却 × 此倍率，1.0=不加倍）"
    )
    TRADE_MAX_CONSECUTIVE_SL: int = Field(
        default=3, description="单币种连续止损次数上限，达到后暂停该币种开仓"
    )
    TRADE_SL_PAUSE_MINUTES: int = Field(
        default=30, description="触发连续止损暂停后，暂停开仓的时长（分钟）"
    )

    # ============ API Key 加密配置 ============
    ENCRYPTION_KEY: str = Field(
        default="", description="API Key 加密密钥（Fernet 格式或任意字符串）"
    )
    ENCRYPTION_KEY_FILE: str = Field(default="", description="API Key 加密密钥文件路径")
    FORCE_ENCRYPTION: bool = Field(
        default=False, description="强制加密：未配置密钥时禁止启动（生产环境建议开启）"
    )

    # ============ RiskGate（测试阶段：最小熔断） ============
    RISK_MAX_DAILY_DRAWDOWN_PCT: float = Field(
        default=5.0, description="日内最大回撤熔断阈值（%），超过则交易信号降级为 HOLD"
    )
    RISK_MAX_CONSECUTIVE_INCORRECT: int = Field(
        default=5, description="方向一致性连续 INCORRECT 次数阈值，超过则降级 HOLD"
    )

    # ---- 波动率尖峰降级 ----
    RISK_ATR_SPIKE_MULTIPLIER: float = Field(
        default=0.0,
        description="ATR 尖峰倍率阈值（当前 ATR > 滚动均值 × 此倍率时触发降级）。0=禁用",
    )
    RISK_ATR_SPIKE_CONFIDENCE_REDUCTION: float = Field(
        default=30.0, description="ATR 尖峰触发时置信度下调幅度（绝对值 %）"
    )
    RISK_ATR_HISTORY_WINDOW: int = Field(
        default=20, description="ATR 滚动窗口大小（需积累足够样本后才开始检测）"
    )

    # ---- 相关性暴露检查 ----
    RISK_CORRELATED_SYMBOLS: str = Field(
        default="",
        description="需做相关性暴露检查的币种列表（逗号分隔，如 BTCUSDT,ETHUSDT）。留空=禁用",
    )
    RISK_MAX_CORRELATED_EXPOSURE_PCT: float = Field(
        default=50.0, description="相关币种同向总暴露上限（占账户权益 %），超过则降级置信度"
    )
    RISK_CORRELATED_EXPOSURE_CONFIDENCE_REDUCTION: float = Field(
        default=20.0, description="相关性暴露触发时置信度下调幅度（绝对值 %）"
    )

    model_config = {
        "env_file": os.path.join(BASE_DIR, ".env"),
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


# 全局配置实例
settings = Settings()

_deepseek_key_file_path = ""
_qwen_key_file_path = ""

# 支持从文件读取 API Key，避免明文放在 .env
if (
    not settings.DEEPSEEK_API_KEY or settings.DEEPSEEK_API_KEY == "sk-xxx"
) and settings.DEEPSEEK_API_KEY_FILE:
    _key_file = settings.DEEPSEEK_API_KEY_FILE
    if not os.path.isabs(_key_file):
        _key_file = os.path.join(BASE_DIR, _key_file)
    _deepseek_key_file_path = _key_file
    try:
        with open(_key_file, "r", encoding="utf-8") as f:
            file_key = f.read().strip()
            if file_key:
                settings.DEEPSEEK_API_KEY = file_key
    except FileNotFoundError:
        raise RuntimeError(
            f"DEEPSEEK_API_KEY_FILE 配置为 '{_key_file}' 但文件不存在。"
            "请创建该文件或移除 DEEPSEEK_API_KEY_FILE 配置。"
        )

# 支持从文件读取千问 API Key
if (not settings.QWEN_API_KEY) and settings.QWEN_API_KEY_FILE:
    _key_file = settings.QWEN_API_KEY_FILE
    if not os.path.isabs(_key_file):
        _key_file = os.path.join(BASE_DIR, _key_file)
    _qwen_key_file_path = _key_file
    try:
        with open(_key_file, "r", encoding="utf-8") as f:
            file_key = f.read().strip()
            if file_key:
                settings.QWEN_API_KEY = file_key
    except FileNotFoundError:
        raise RuntimeError(
            f"QWEN_API_KEY_FILE 配置为 '{_key_file}' 但文件不存在。"
            "请创建该文件或移除 QWEN_API_KEY_FILE 配置。"
        )


def validate_runtime_settings(log: Any) -> None:
    """
    启动时安全校验与告警（由 main.lifespan 调用）。

    目的：
    - 避免在 import 阶段 print/raise 影响运维观测
    - 统一走日志系统输出
    """
    warnings: list[str] = []

    # 配额配置校验
    if settings.ENABLE_QUOTA_LIMIT and settings.DAILY_API_QUOTA < 1000:
        warnings.append(
            f"⚠️  DAILY_API_QUOTA 设置过低（{settings.DAILY_API_QUOTA}），可能影响正常功能"
        )

    # 交易资金利用率校验
    if settings.TRADE_BALANCE_UTILIZATION_PCT <= 0 or settings.TRADE_BALANCE_UTILIZATION_PCT > 100:
        warnings.append(
            f"⚠️  TRADE_BALANCE_UTILIZATION_PCT 需在 (0,100]，当前={settings.TRADE_BALANCE_UTILIZATION_PCT}；将导致仓位计算异常"
        )

    # 翻仓/强平阈值校验
    if settings.TRADE_FLIP_CONFIDENCE <= 0 or settings.TRADE_FLIP_CONFIDENCE > 100:
        warnings.append(
            f"⚠️  TRADE_FLIP_CONFIDENCE 需在 (0,100]，当前={settings.TRADE_FLIP_CONFIDENCE}；将导致翻仓/强平逻辑异常"
        )

    # 安全默认值检查
    if not settings.JWT_SECRET or settings.JWT_SECRET == "change_me":
        warnings.append("⚠️  JWT_SECRET 未配置或使用默认值，存在安全风险！请在 .env 中设置随机字符串")

    if settings.ADMIN_PASSWORD == "admin123":
        warnings.append("⚠️  ADMIN_PASSWORD 使用默认弱密码 'admin123'，建议修改")

    if not settings.DEEPSEEK_API_KEY or settings.DEEPSEEK_API_KEY == "sk-xxx":
        warnings.append("⚠️  DEEPSEEK_API_KEY 未配置，AI 分析功能将不可用")

    if settings.DEEPSEEK_API_KEY_FILE and _deepseek_key_file_path:
        if not os.path.exists(_deepseek_key_file_path):
            warnings.append(f"⚠️  DEEPSEEK_API_KEY_FILE 文件不存在：{_deepseek_key_file_path}")

    # 千问用于“角色分析/聊天”，未配置则对应能力不可用
    if not settings.QWEN_API_KEY:
        warnings.append("⚠️  QWEN_API_KEY 未配置，AI 聊天/角色分析将不可用（裁决仍走 DeepSeek）")

    if settings.QWEN_API_KEY_FILE and _qwen_key_file_path:
        if not os.path.exists(_qwen_key_file_path):
            warnings.append(f"⚠️  QWEN_API_KEY_FILE 文件不存在：{_qwen_key_file_path}")

    # 检查加密配置
    if not settings.ENCRYPTION_KEY and not settings.ENCRYPTION_KEY_FILE:
        warnings.append("⚠️  ENCRYPTION_KEY 未配置，API Key 将以明文存储（强烈建议配置）")

    if warnings:
        log.warning("=" * 50)
        log.warning("🔒 安全检查警告")
        log.warning("=" * 50)
        for w in warnings:
            log.warning(w)
        log.warning("=" * 50)

    # 弱管理员密码检查
    if not settings.ALLOW_WEAK_ADMIN_PASSWORD and settings.ADMIN_PASSWORD == "admin123":
        raise RuntimeError(
            "检测到弱管理员密码 admin123。请修改 .env 后重启，"
            "或显式设置 ALLOW_WEAK_ADMIN_PASSWORD=true（不推荐）。"
        )

    # JWT 签名密钥检查
    if not settings.ALLOW_DEFAULT_JWT_SECRET and (not settings.JWT_SECRET or settings.JWT_SECRET == "change_me"):
        raise RuntimeError(
            "JWT_SECRET 未配置或仍为默认值。请在 .env 中设置一个随机字符串，"
            "或显式设置 ALLOW_DEFAULT_JWT_SECRET=true（不推荐）。"
        )

    # API Key 加密检查
    if not settings.ALLOW_PLAINTEXT_API_KEYS and (not settings.ENCRYPTION_KEY and not settings.ENCRYPTION_KEY_FILE):
        raise RuntimeError(
            "ENCRYPTION_KEY 未配置。生产环境必须配置 API Key 加密密钥，"
            "或显式设置 ALLOW_PLAINTEXT_API_KEYS=true（不推荐）。"
        )

    if settings.TRADE_ENABLED and (not settings.BINANCE_TESTNET_API_KEY or not settings.BINANCE_TESTNET_API_SECRET):
        raise RuntimeError(
            "TRADE_ENABLED=true 但 BINANCE_TESTNET_API_KEY/SECRET 未配置，禁止启动以避免误运行。"
        )
