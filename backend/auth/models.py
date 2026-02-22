"""
钢子出击 - 认证相关 Pydantic 模型
请求/响应数据校验
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class PasswordResetRequest(BaseModel):
    """密码重置申请请求"""

    username: str = Field(..., min_length=2, max_length=50, description="用户名")


class PasswordResetRequestResponse(BaseModel):
    """密码重置申请响应"""

    message: str = Field(..., description="响应消息")
    token: Optional[str] = Field(
        default=None, description="重置令牌（仅当用户存在时返回）"
    )
    expires_at: Optional[datetime] = Field(default=None, description="令牌过期时间")
    requires_admin_approval: bool = Field(
        default=True, description="是否需要管理员确认"
    )


class PasswordResetConfigResponse(BaseModel):
    requires_admin_approval: bool = Field(
        default=True, description="是否需要管理员确认"
    )


class PasswordResetConfirm(BaseModel):
    """管理员确认密码重置请求"""

    username: str = Field(..., min_length=2, max_length=50, description="用户名")
    token: str = Field(..., min_length=32, max_length=64, description="重置令牌")
    approve: bool = Field(default=True, description="是否批准重置")


class PasswordResetWithToken(BaseModel):
    """用户使用令牌设置新密码"""

    username: str = Field(..., min_length=2, max_length=50, description="用户名")
    token: str = Field(..., min_length=32, max_length=64, description="重置令牌")
    new_password: str = Field(..., min_length=6, max_length=128, description="新密码")


class LoginRequest(BaseModel):
    """登录请求"""

    username: str = Field(..., min_length=1, max_length=50, description="用户名")
    password: str = Field(..., min_length=1, max_length=128, description="密码")


class RegisterRequest(BaseModel):
    """注册请求（包含轻量人机校验字段）"""

    username: str = Field(..., min_length=2, max_length=50, description="用户名")
    password: str = Field(..., min_length=6, max_length=128, description="密码")
    captcha_id: str = Field(..., min_length=8, max_length=64, description="验证码ID")
    captcha_answer: str = Field(
        ..., min_length=1, max_length=16, description="验证码答案"
    )


class TokenResponse(BaseModel):
    """登录成功响应"""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    username: str


class UserInfo(BaseModel):
    """用户信息"""

    id: int
    username: str
    exchange: str
    is_active: bool


class UpdateAPIKeyRequest(BaseModel):
    """更新 API Key 请求（加密存储）"""

    exchange: str = Field(default="binance", max_length=20, description="交易所名称")
    api_key: str = Field(
        default="", max_length=255, description="交易所 API Key（将被加密）"
    )
    api_secret: str = Field(
        default="", max_length=255, description="交易所 API Secret（将被加密）"
    )


class APIKeyInfo(BaseModel):
    """API Key 信息响应（仅管理员可查看解密后内容）"""

    exchange: str
    api_key: str
    api_secret: str
    is_encrypted: bool


class EncryptionStatus(BaseModel):
    """加密状态信息"""

    enabled: bool
    key_source: str
    message: str = ""
