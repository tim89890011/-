# API 配额管理与成本监控配置说明

## 概述

钢子出击系统现已集成 DeepSeek API 配额管理和成本监控功能，帮助您：

1. **控制 API 调用成本** - 设置每日调用上限，避免意外高额账单
2. **监控配额使用情况** - 实时查看配额使用率和剩余配额
3. **自动降级策略** - 配额紧张时自动减少非必要调用
4. **成本估算** - 预估每日/每月 API 调用成本

---

## 配置项说明

### 基础配额配置

```env
# 是否启用配额限制（建议生产环境启用）
ENABLE_QUOTA_LIMIT=true

# 每日 API 调用上限（默认：10000）
# 根据分析频率计算：
# - 主要币种(BTC/ETH)每5分钟分析：2 × 12次/小时 × 24小时 = 576次
# - 次要币种每15分钟分析：8 × 4次/小时 × 24小时 = 768次
# - 每次分析6次API调用(5角色+1裁决)：(576+768) × 6 = 8064次/天
# 建议预留20%缓冲，设置为 10000
DAILY_API_QUOTA=10000

# 警告阈值（默认：0.8，即80%）
# 当配额使用率达到此值时发出警告
QUOTA_WARNING_THRESHOLD=0.8

# 危险阈值（默认：0.9，即90%）
# 当配额使用率达到此值时：
# - 跳过次要币种分析
# - 限制非必要调用
QUOTA_CRITICAL_THRESHOLD=0.9
```

### 成本配置

```env
# DeepSeek Chat V3 每千 token 成本（元）
# 官方定价：输入 0.001元/千token，输出 0.002元/千token
DEEPSEEK_CHAT_COST_PER_1K=0.001

# DeepSeek Reasoner R1 每千 token 成本（元）
# 官方定价：输入 0.003元/千token，输出 0.006元/千token
DEEPSEEK_R1_COST_PER_1K=0.003
```

---

## API 接口

### 1. 查询配额状态

```http
GET /api/ai/quota
Authorization: Bearer <token>
```

响应示例：
```json
{
  "success": true,
  "data": {
    "quota": {
      "date": "2026-02-15",
      "total_calls": 5234,
      "analysis_calls": 4800,
      "chat_calls": 234,
      "reasoner_calls": 200,
      "estimated_cost": 15.702,
      "quota_limit": 10000,
      "status": "normal",
      "remaining": 4766,
      "usage_percent": 52.34
    },
    "strategy": {
      "enabled": true,
      "current_usage": 52.34,
      "status": "normal",
      "actions": ["正常运行，持续监控"]
    },
    "cost_estimate": {
      "current_cost": 15.702,
      "projected_daily_cost": 31.404,
      "monthly_estimate": 942.12,
      "cost_per_call": 0.003,
      "currency": "CNY"
    }
  }
}
```

### 2. 查询配额历史

```http
GET /api/ai/quota/history?days=7
Authorization: Bearer <token>
```

### 3. 查询成本指标

```http
GET /api/ai/cost
Authorization: Bearer <token>
```

响应示例：
```json
{
  "success": true,
  "data": {
    "today": {
      "date": "2026-02-15",
      "total_calls": 5234,
      "successful_calls": 5180,
      "failed_calls": 54,
      "total_cost": 15.702,
      "avg_response_time": 2.345,
      "success_rate": 98.97,
      "by_model": {
        "deepseek-chat": {
          "calls": 5034,
          "cost": 10.068,
          "tokens_in": 10068000,
          "tokens_out": 1510200
        },
        "deepseek-reasoner": {
          "calls": 200,
          "cost": 5.634,
          "tokens_in": 1200000,
          "tokens_out": 278000
        }
      }
    },
    "errors": {
      "total_calls": 5234,
      "failed_calls": 54,
      "error_rate": 1.03,
      "error_types": {
        "timeout": 30,
        "rate_limit": 15,
        "other": 9
      }
    }
  }
}
```

### 4. 查询仪表板摘要

```http
GET /api/ai/cost/dashboard
Authorization: Bearer <token>
```

### 5. 查询实时指标

```http
GET /api/ai/metrics/realtime
Authorization: Bearer <token>
```

---

## 降级策略

系统根据配额使用率自动执行以下降级策略：

| 使用率 | 状态 | 策略 |
|--------|------|------|
| < 80% | 正常 | 正常运行，持续监控 |
| 80-90% | 警告 | 发送警告日志，准备降级预案 |
| 90-95% | 危险 | 跳过次要币种分析，限制聊天调用 |
| 95-100% | 严重 | 暂停所有定时分析任务 |
| >= 100% | 超限 | 仅保留用户主动触发的分析 |

---

## 前端监控面板

在系统界面中新增了「系统监控」标签页，包含：

1. **API 配额监控** - 实时显示配额使用环形图、调用类型分布、成本预估
2. **成本监控** - 显示调用成功率、响应时间分布、模型统计
3. **配额说明** - 配额机制的文字说明

---

## 成本估算示例

以当前系统配置为例（每日约 8000+ 次调用）：

### 单次分析成本估算

每次完整分析包含：
- 5 次角色分析（Chat V3）
- 1 次最终裁决（R1）

假设：
- 角色分析平均：2000 tokens 输入 + 500 tokens 输出
- R1 裁决平均：3000 tokens 输入 + 800 tokens 输出

计算：
```
角色分析成本 = 5 × (2000/1000 × 0.001 + 500/1000 × 0.002) = 5 × 0.003 = 0.015元
R1 裁决成本 = 3000/1000 × 0.003 + 800/1000 × 0.006 = 0.009 + 0.0048 = 0.0138元
单次分析总成本 ≈ 0.029元
```

### 每日成本估算

```
每日分析次数 ≈ 1344次 (BTC/ETH 288次 + 其他 1056次)
每日成本 ≈ 1344 × 0.029 ≈ 39元
每月成本 ≈ 39 × 30 ≈ 1170元
```

**注意**：实际成本取决于 token 使用量，上述为估算值。

---

## 最佳实践

1. **生产环境建议**：
   - 启用配额限制 (`ENABLE_QUOTA_LIMIT=true`)
   - 设置合理的每日配额（建议 10000）
   - 配置告警阈值（警告 80%，危险 90%）

2. **成本控制**：
   - 定期检查配额使用情况
   - 优化提示词减少 token 消耗
   - 考虑开启结果缓存

3. **监控告警**：
   - 关注日志中的配额告警
   - 定期查看成本趋势
   - 设置外部监控（如需要）

---

## 故障排查

### 配额超限

**现象**：API 调用返回 "配额不足"

**解决**：
1. 检查当日配额使用情况：`GET /api/ai/quota`
2. 等待次日配额重置
3. 或临时增加 `DAILY_API_QUOTA`

### 成本异常

**现象**：实际成本远高于估算

**排查**：
1. 检查是否有异常的大量调用
2. 查看错误日志中的失败调用
3. 确认 token 使用量是否符合预期

---

## 更新记录

- 2026-02-15: 初始版本，实现基础配额管理和成本监控
