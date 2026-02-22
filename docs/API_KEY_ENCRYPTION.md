# API Key 加密存储配置说明

本文档说明「钢子出击」系统中 API Key 的 AES 加密存储配置方法。

## 概述

系统使用 **Fernet 对称加密**（基于 AES-128-CBC + HMAC-SHA256）来保护用户的交易所 API Key 和 Secret。

- **加密字段**: `api_key_encrypted`, `api_secret_encrypted`
- **加密格式**: `enc:<Fernet加密后的Base64字符串>`
- **降级格式**: `plain:<原始字符串>`（未配置密钥时）

## 快速配置

### 方法一：使用密钥文件（推荐）

```bash
# 1. 创建数据目录
mkdir -p data

# 2. 生成密钥
python -c "from backend.utils.crypto import generate_encryption_key; print(generate_encryption_key())" > data/.encryption_key

# 3. 设置安全权限
chmod 600 data/.encryption_key

# 4. 添加到 .gitignore
echo "data/.encryption_key" >> .gitignore
```

### 方法二：使用环境变量

在 `.env` 文件中添加：

```bash
# 方式 A：直接使用 Fernet 格式密钥（推荐）
ENCRYPTION_KEY="your-32-byte-base64-encoded-key-here=="

# 方式 B：使用任意字符串（自动派生密钥）
ENCRYPTION_KEY="my-strong-password-here"
```

### 方法三：指定自定义密钥文件路径

在 `.env` 文件中添加：

```bash
ENCRYPTION_KEY_FILE="/path/to/secret.key"
```

## 配置项说明

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `ENCRYPTION_KEY` | 加密密钥（环境变量方式） | `""` |
| `ENCRYPTION_KEY_FILE` | 密钥文件路径 | `""` |
| `FORCE_ENCRYPTION` | 强制加密（未配置密钥时禁止启动） | `false` |

## 密钥加载优先级

系统按以下顺序加载加密密钥：

1. `ENCRYPTION_KEY` 环境变量
2. `ENCRYPTION_KEY_FILE` 指定的文件
3. `data/.encryption_key` 默认文件

找到第一个有效密钥后即停止搜索。

## API 端点

### 用户端点（需登录）

| 方法 | 端点 | 说明 |
|------|------|------|
| `POST` | `/api/auth/api-key` | 更新自己的 API Key |
| `GET` | `/api/auth/api-key` | 获取自己的 API Key（解密后） |
| `GET` | `/api/auth/api-key/status` | 查看加密状态 |

### 管理员端点（需管理员权限）

| 方法 | 端点 | 说明 |
|------|------|------|
| `GET` | `/api/auth/admin/users/{user_id}/api-key` | 查看指定用户的 API Key |
| `POST` | `/api/auth/admin/users/{user_id}/api-key` | 更新指定用户的 API Key |

## 密钥轮换（进阶）

如需更换加密密钥，使用以下代码：

```python
from backend.utils.crypto import rotate_encryption_key

# 试运行（不实际修改）
result = await rotate_encryption_key(
    new_key="your-new-key",
    db_session=db,
    dry_run=True,
)
print(result)

# 正式执行
result = await rotate_encryption_key(
    new_key="your-new-key",
    db_session=db,
    dry_run=False,
)
```

## 安全建议

1. **生产环境必须配置加密密钥**
   ```bash
   FORCE_ENCRYPTION=true
   ```

2. **密钥文件权限**
   ```bash
   chmod 600 data/.encryption_key
   chown <app-user>:<app-group> data/.encryption_key
   ```

3. **定期轮换密钥**
   - 建议每 3-6 个月轮换一次
   - 怀疑密钥泄露时立即轮换

4. **备份注意事项**
   - 数据库备份包含加密数据
   - 密钥必须单独安全备份
   - 丢失密钥将导致 API Key 无法解密

5. **密钥生成**
   ```python
   from backend.utils.crypto import generate_encryption_key
   
   # 生成新的安全密钥
   key = generate_encryption_key()
   print(key)  # 复制到配置文件
   ```

## 故障排查

### 警告：API Key 将以明文存储

**原因**: 未配置 `ENCRYPTION_KEY` 且未找到密钥文件

**解决**:
```bash
# 生成密钥文件
python -c "from backend.utils.crypto import generate_encryption_key; print(generate_encryption_key())" > data/.encryption_key
```

### 错误：无法解密

**原因**: 密钥不匹配或数据损坏

**解决**:
1. 检查 `ENCRYPTION_KEY` 是否正确配置
2. 确认密钥文件内容未被修改
3. 检查数据库中数据格式（应以 `enc:` 开头）

### 错误：强制加密未配置密钥

**原因**: `FORCE_ENCRYPTION=true` 但未配置有效密钥

**解决**: 配置密钥后重启，或设置 `FORCE_ENCRYPTION=false`（不推荐）

## 技术细节

### 加密算法

- **算法**: Fernet (AES-128-CBC + HMAC-SHA256)
- **密钥派生**: PBKDF2-HMAC-SHA256 (480000 轮)
- **盐值**: 固定盐值（仅用于密钥派生场景）

### 数据格式

```python
# 加密数据
api_key_encrypted = "enc:gAAAAAB..."  # Fernet 加密后的 Base64

# 明文数据（降级模式）
api_key_encrypted = "plain:actual_api_key_here"
```

### 代码示例

```python
from backend.utils.crypto import encrypt_api_key, decrypt_api_key

# 加密
encrypted = encrypt_api_key("my-api-key")
# 返回: "enc:gAAAAAB..." 或 "plain:my-api-key"

# 解密
decrypted = decrypt_api_key(encrypted)
# 返回: "my-api-key"
```
