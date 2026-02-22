# ⚡ 钢子出击 - AI 量化交易信号系统

AI 驱动的加密货币量化交易信号平台。5 位 AI 分析师并发辩论，DeepSeek R1 综合裁决，实时行情推送。

## 功能列表

### 核心功能
- **AI 五人辩论**：5 个 AI 角色（技术老王、趋势老李、情绪小张、资金老赵、风控老陈）并发分析，各自给出买/卖/观望信号
- **DeepSeek R1 裁决**：R1 推理模型综合 5 位分析师意见，给出最终决策
- **实时行情**：Binance WebSocket 实时价格推送（10 币种）
- **技术指标**：RSI、MACD、布林带、KDJ、ATR、均线系统
- **AI 聊天**：与 AI 实时对话，获取市场分析和建议
- **语音播报**：新信号自动中文语音播报

### 辅助功能
- **市场情绪温度计**：Fear & Greed Index 实时展示
- **巨鲸监控**：Binance 大额交易追踪
- **信号准确率**：历史信号自动验证和统计
- **AI 每日一句**：每次分析附赠一句 AI 格言
- **定时分析**：BTC/ETH 每 5 分钟分析，其余币种每 15 分钟

### 界面特性
- 暗色主题仪表盘
- 粒子动画背景
- K 线动画登录页
- 仪表盘转速表（Canvas）
- 价格闪烁动画
- 响应式设计（PC/平板/手机）

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端 | Python 3.11+ / FastAPI / Uvicorn |
| 数据库 | SQLite (aiosqlite) |
| AI | DeepSeek Chat V3 + Reasoner R1 |
| 行情 | Binance WebSocket + REST API |
| 指标 | pandas + pandas-ta |
| 认证 | JWT (python-jose + bcrypt) |
| 定时 | APScheduler |
| 前端 | 原生 HTML/CSS/JS + Chart.js |

## 快速开始

### 1. 克隆 & 安装

```bash
cd 钢子出击
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. 配置

编辑 `.env` 文件，填写：
- `DEEPSEEK_API_KEY`：DeepSeek API 密钥（必填）
- `JWT_SECRET`：已自动生成
- `ADMIN_PASSWORD`：建议修改默认密码

### 3. 启动

```bash
source venv/bin/activate
uvicorn backend.main:app --host 0.0.0.0 --port 9998
```

打开浏览器访问 `http://localhost:9998`，默认账号 `admin / admin123`。

## 部署指南（宝塔面板）

1. 上传项目到服务器
2. 运行 `bash deploy/setup.sh`
3. 编辑 `.env` 填写 API Key
4. 宝塔 → 网站 → 添加反向代理，配置见 `deploy/nginx.conf`
5. 宝塔 → 软件 → Supervisor，导入 `deploy/supervisor.conf`（含优雅停机参数）
6. 服务器安装 logrotate，并加载 `deploy/logrotate.conf`

## 配置说明

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| DEEPSEEK_API_KEY | DeepSeek API 密钥 | 需填写 |
| DEEPSEEK_BASE_URL | DeepSeek API 地址 | https://api.deepseek.com |
| JWT_SECRET | JWT 签名密钥 | 随机字符串 |
| JWT_ACCESS_EXPIRE_MINUTES | Access Token 过期分钟数 | 30 |
| JWT_REFRESH_EXPIRE_DAYS | Refresh Token 过期天数 | 7 |
| DATABASE_URL | 数据库连接 | SQLite 本地 |
| RESET_REQUIRE_ADMIN_APPROVAL | 密码重置是否需管理员确认 | false |
| ADMIN_USERNAME | 管理员用户名 | admin |
| ADMIN_PASSWORD | 管理员密码 | admin123 |
| PORT | 服务端口 | 9998 |
| TG_BOT_TOKEN | Telegram Bot Token | 留空不启用 |
| TG_CHAT_ID | Telegram Chat ID | 留空不启用 |

## API 列表

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/auth/login | 登录 |
| POST | /api/auth/refresh | 刷新令牌 |
| GET | /api/auth/reset-config | 获取密码重置流程配置 |
| POST | /api/auth/register | 注册 |
| GET | /api/auth/me | 当前用户 |
| GET | /api/market/prices | 实时价格 |
| GET | /api/market/kline/{symbol} | K 线数据 |
| GET | /api/market/indicators/{symbol} | 技术指标 |
| GET | /api/market/funding/{symbol} | 资金费率+持仓 |
| GET | /api/market/large-trades/{symbol} | 大额交易 |
| GET | /api/ai/latest-signal | 最新信号 |
| GET | /api/ai/debate/{symbol} | 辩论详情 |
| POST | /api/ai/analyze-now | 立即分析 |
| GET | /api/ai/history | 信号历史 |
| GET | /api/ai/accuracy | 准确率统计 |
| POST | /api/chat/send | 发送聊天 |
| GET | /api/chat/history | 聊天历史 |
| WS | /ws/market | 行情推送 |
| WS | /ws/signals | 信号推送 |

## AI 角色说明

| 角色 | 名称 | 分析维度 |
|------|------|----------|
| 📊 | 技术老王 | RSI/MACD/布林带/K线形态 |
| 📈 | 趋势老李 | 均线趋势/成交量/价格结构 |
| 🧠 | 情绪小张 | 资金费率/多空比/市场情绪 |
| 💰 | 资金老赵 | 持仓量/大单/资金流向 |
| 🛡️ | 风控老陈 | ATR波动率/止损/仓位/杠杆 |

## 常见问题

**Q: DeepSeek API Key 在哪里获取？**
A: 访问 https://platform.deepseek.com 注册并创建 API Key

**Q: 为什么没有实时价格？**
A: Binance WebSocket 连接需要几秒，如果网络受限可能无法连接

**Q: 信号准确率怎么看？**
A: 风控分析 Tab 中显示。需等待信号产生 1 小时后才有验证数据

**Q: 手机端可以用吗？**
A: 是的，已做响应式适配。建议横屏查看辩论面板

**Q: 怎么修改定时分析频率？**
A: 编辑 `backend/scheduler/tasks.py` 中的 IntervalTrigger 参数
