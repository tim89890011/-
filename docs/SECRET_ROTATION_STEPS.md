# 密钥轮换指南

> **需要人工执行** — 涉及外部服务密钥，自动化不安全。

## 需要轮换的密钥

| 密钥 | 来源 | 风险 | 轮换方式 |
|------|------|------|----------|
| `DEEPSEEK_API_KEY` | .env（可能在 git 历史中） | 高 | DeepSeek 控制台重新生成 |
| `QWEN_API_KEY` | .env（可能在 git 历史中） | 高 | 阿里云 DashScope 控制台重新生成 |
| `JWT_SECRET` | .env | 高 | 生成新随机字符串 |
| `BINANCE_TESTNET_API_KEY` | .env | 中 | Binance Testnet 重新生成 |
| `BINANCE_TESTNET_API_SECRET` | .env | 中 | 同上 |
| `TELEGRAM_BOT_TOKEN` | .env（若配置） | 中 | BotFather 重新生成 |
| `ADMIN_PASSWORD` | .env | 高 | 更改为强密码 |

## 轮换步骤

### 1. DEEPSEEK_API_KEY
```bash
# 1. 登录 https://platform.deepseek.com/
# 2. API Keys → 删除旧 key → 创建新 key
# 3. 更新服务器 .env:
#    DEEPSEEK_API_KEY=新key
# 4. 验证:
curl -H "Authorization: Bearer 新key" https://api.deepseek.com/models
```

### 2. QWEN_API_KEY
```bash
# 1. 登录阿里云 DashScope 控制台
# 2. API-KEY 管理 → 删除旧 key → 创建新 key
# 3. 更新服务器 .env:
#    QWEN_API_KEY=新key
```

### 3. JWT_SECRET
```bash
# 生成新的随机 secret
python3 -c "import secrets; print(secrets.token_urlsafe(64))"
# 更新 .env:
#   JWT_SECRET=生成的值
# ⚠️ 所有用户的 JWT token 将失效，需要重新登录
```

### 4. BINANCE_TESTNET_API_KEY / SECRET
```bash
# 1. 登录 https://testnet.binancefuture.com/
# 2. API Management → 删除旧 key → 创建新 key pair
# 3. 更新 .env
```

### 5. ADMIN_PASSWORD
```bash
# 更新 .env:
#   ADMIN_PASSWORD=新的强密码（至少16位，含大小写+数字+特殊字符）
# 重启服务后，admin 密码将自动更新
```

## 验证清单

- [ ] 每个新 key 都已在 .env 中更新
- [ ] 旧 key 已从服务商控制台删除/停用
- [ ] 服务重启后功能正常（AI 分析、交易、登录）
- [ ] git 历史已清理（参考 HISTORY_PURGE_GUIDE.md）
