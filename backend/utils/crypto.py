"""
钢子出击 - API Key 加密/解密工具
使用 Fernet 对称加密（AES-128-CBC）保护敏感数据

安全特性：
- 密钥从环境变量或独立文件读取，绝不硬编码
- 支持密钥轮换机制
- 未配置密钥时降级为明文存储（带警告）
- 使用 Fernet 确保数据完整性和机密性
"""
import os
import base64
import logging
from typing import Optional
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logger = logging.getLogger(__name__)

# 全局加密器实例（延迟初始化）
_fernet_instance: Optional[Fernet] = None
_encryption_enabled: bool = False
_encryption_key_source: str = "none"


def _derive_key(password: bytes, salt: bytes) -> bytes:
    """
    使用 PBKDF2 从密码派生加密密钥
    
    Args:
        password: 原始密码/密钥材料
        salt: 盐值
        
    Returns:
        32字节 URL-safe base64 编码的密钥
    """
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=480000,  # OWASP 推荐迭代次数
    )
    key = base64.urlsafe_b64encode(kdf.derive(password))
    return key


def generate_encryption_key() -> str:
    """
    生成新的加密密钥（用于初始化密钥文件）
    
    Returns:
        URL-safe base64 编码的 32 字节密钥字符串
    """
    key = Fernet.generate_key()
    return key.decode('utf-8')


def init_encryption(
    key: Optional[str] = None,
    key_file: Optional[str] = None,
    key_env_var: str = "ENCRYPTION_KEY",
    allow_plaintext: bool = True,
) -> bool:
    """
    初始化加密模块
    
    密钥加载优先级：
    1. 传入的 key 参数
    2. key_file 指定的文件
    3. 环境变量 key_env_var
    4. data/.encryption_key 文件（项目默认位置）
    
    Args:
        key: 直接传入的密钥
        key_file: 密钥文件路径
        key_env_var: 环境变量名
        allow_plaintext: 未配置密钥时是否允许明文存储（默认 True，但会记录警告）
        
    Returns:
        True 表示加密已启用，False 表示降级为明文存储
    """
    global _fernet_instance, _encryption_enabled, _encryption_key_source
    
    key_value: Optional[str] = None
    source: str = ""
    
    # 1. 检查传入的 key 参数
    if key:
        key_value = key
        source = "parameter"
    
    # 2. 检查 key_file
    if not key_value and key_file:
        if os.path.isabs(key_file):
            key_path = key_file
        else:
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            key_path = os.path.join(base_dir, key_file)
        
        try:
            if os.path.exists(key_path):
                with open(key_path, "r", encoding="utf-8") as f:
                    key_value = f.read().strip()
                    if key_value:
                        source = f"file:{key_file}"
        except Exception as e:
            logger.warning(f"[加密] 读取密钥文件失败: {e}")
    
    # 3. 检查环境变量
    if not key_value:
        key_value = os.environ.get(key_env_var, "").strip()
        if key_value:
            source = f"env:{key_env_var}"
    
    # 4. 检查默认位置
    if not key_value:
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        default_key_path = os.path.join(base_dir, "data", ".encryption_key")
        try:
            if os.path.exists(default_key_path):
                with open(default_key_path, "r", encoding="utf-8") as f:
                    key_value = f.read().strip()
                    if key_value:
                        source = "file:data/.encryption_key"
        except Exception as e:
            logger.warning("[加密] 读取默认密钥文件失败: %s", e)
    
    # 初始化 Fernet
    if key_value:
        try:
            # 如果密钥不是标准 Fernet 格式（32字节 URL-safe base64），进行派生
            try:
                _fernet_instance = Fernet(key_value.encode('utf-8'))
            except ValueError:
                # 使用 PBKDF2 派生密钥
                salt = b'gangzi_chu_ji_static_salt_v1'  # 固定盐值用于派生
                derived_key = _derive_key(key_value.encode('utf-8'), salt)
                _fernet_instance = Fernet(derived_key)
            
            _encryption_enabled = True
            _encryption_key_source = source
            logger.info(f"[加密] API Key 加密已启用，密钥来源: {source}")
            return True
            
        except Exception as e:
            logger.error(f"[加密] 初始化加密失败: {e}")
    
    # 未启用加密
    _encryption_enabled = False
    _encryption_key_source = "none"
    
    if allow_plaintext:
        logger.warning("=" * 60)
        logger.warning("[加密] ⚠️ 警告：未配置 ENCRYPTION_KEY，API Key 将以明文存储！")
        logger.warning("[加密] 建议操作：")
        logger.warning("[加密]   1. 生成密钥: python -c \"from backend.utils.crypto import generate_encryption_key; print(generate_encryption_key())\" > data/.encryption_key")
        logger.warning("[加密]   2. 或在 .env 中添加 ENCRYPTION_KEY=your_key")
        logger.warning("[加密]   3. 设置文件权限: chmod 600 data/.encryption_key")
        logger.warning("=" * 60)
    else:
        raise RuntimeError("未配置 ENCRYPTION_KEY，且不允许明文存储。请配置加密密钥后重启。")
    
    return False


def is_encryption_enabled() -> bool:
    """检查加密是否已启用"""
    return _encryption_enabled


def get_encryption_status() -> dict:
    """获取加密状态信息"""
    return {
        "enabled": _encryption_enabled,
        "key_source": _encryption_key_source,
    }


def encrypt_api_key(api_key: str) -> str:
    """
    加密 API Key
    
    Args:
        api_key: 原始 API Key 字符串
        
    Returns:
        加密后的字符串（前缀标识是否加密），或明文（未启用加密时）
    """
    if not api_key:
        return ""
    
    # 如果已经是加密格式，直接返回
    if api_key.startswith("enc:"):
        return api_key
    
    if not _encryption_enabled or not _fernet_instance:
        # 明文存储，添加前缀标识
        return f"plain:{api_key}"
    
    try:
        encrypted = _fernet_instance.encrypt(api_key.encode('utf-8'))
        return f"enc:{encrypted.decode('utf-8')}"
    except Exception as e:
        logger.error(f"[加密] 加密失败: {e}")
        # 加密失败时降级为明文（带警告）
        return f"plain:{api_key}"


def decrypt_api_key(encrypted: str) -> str:
    """
    解密 API Key
    
    Args:
        encrypted: 加密后的字符串（含前缀）
        
    Returns:
        原始 API Key 字符串
    """
    if not encrypted:
        return ""
    
    # 检查前缀
    if encrypted.startswith("plain:"):
        return encrypted[6:]
    
    if encrypted.startswith("enc:"):
        if not _encryption_enabled or not _fernet_instance:
            logger.error("[加密] 无法解密：加密模块未初始化或密钥缺失")
            return ""
        
        try:
            ciphertext = encrypted[4:].encode('utf-8')
            decrypted = _fernet_instance.decrypt(ciphertext)
            return decrypted.decode('utf-8')
        except InvalidToken:
            logger.error("[加密] 解密失败：无效的令牌或密钥不匹配")
            return ""
        except Exception as e:
            logger.error(f"[加密] 解密失败: {e}")
            return ""
    
    # 无前缀的遗留数据，视为明文
    return encrypted


def rotate_encryption_key(
    new_key: str,
    db_session=None,
    dry_run: bool = True,
) -> dict:
    """
    密钥轮换工具（进阶功能）
    
    使用新密钥重新加密所有数据。注意：此操作需要数据库访问权限。
    
    Args:
        new_key: 新加密密钥
        db_session: 数据库会话（用于更新数据）
        dry_run: 是否为试运行（不实际修改数据）
        
    Returns:
        操作结果统计
    """
    from backend.database.models import User
    from sqlalchemy import select
    
    result = {
        "success": False,
        "dry_run": dry_run,
        "total_users": 0,
        "updated": 0,
        "errors": [],
    }
    
    if not db_session:
        result["errors"].append("未提供数据库会话")
        return result
    
    if not _encryption_enabled:
        result["errors"].append("当前未启用加密，无法轮换密钥")
        return result
    
    try:
        # 创建新密钥的 Fernet 实例
        try:
            new_fernet = Fernet(new_key.encode('utf-8'))
        except ValueError:
            salt = b'gangzi_chu_ji_static_salt_v1'
            derived_key = _derive_key(new_key.encode('utf-8'), salt)
            new_fernet = Fernet(derived_key)
        
        # 查询所有有 API Key 的用户
        stmt = select(User).where(
            (User.api_key_encrypted != "") | (User.api_secret_encrypted != "")
        )
        rows = db_session.execute(stmt).scalars().all()
        
        result["total_users"] = len(rows)
        
        for user in rows:
            try:
                # 解密旧数据
                old_api_key = decrypt_api_key(user.api_key_encrypted) if user.api_key_encrypted else ""
                old_api_secret = decrypt_api_key(user.api_secret_encrypted) if user.api_secret_encrypted else ""
                
                if not dry_run:
                    # 使用新密钥加密
                    if old_api_key:
                        encrypted_key = new_fernet.encrypt(old_api_key.encode('utf-8'))
                        user.api_key_encrypted = f"enc:{encrypted_key.decode('utf-8')}"
                    
                    if old_api_secret:
                        encrypted_secret = new_fernet.encrypt(old_api_secret.encode('utf-8'))
                        user.api_secret_encrypted = f"enc:{encrypted_secret.decode('utf-8')}"
                    
                    result["updated"] += 1
                    
            except Exception as e:
                error_msg = f"用户 {user.id} ({user.username}) 处理失败: {e}"
                result["errors"].append(error_msg)
                logger.error(f"[加密] {error_msg}")
        
        if not dry_run and result["updated"] > 0:
            db_session.commit()
            # 更新全局实例
            global _fernet_instance
            _fernet_instance = new_fernet
            logger.info(f"[加密] 密钥轮换完成，已更新 {result['updated']} 条记录")
        
        result["success"] = len(result["errors"]) == 0
        
    except Exception as e:
        result["errors"].append(f"密钥轮换失败: {e}")
        logger.error(f"[加密] 密钥轮换异常: {e}")
    
    return result


# 向后兼容的别名
encrypt = encrypt_api_key
decrypt = decrypt_api_key
