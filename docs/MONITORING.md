# 钢子出击 - 监控模块配置说明

## 功能概述

监控模块为「钢子出击」加密货币量化交易系统提供以下功能：

- **健康检查端点**: 系统和各组件的健康状态检查
- **Prometheus 指标导出**: 标准化的监控指标，可被 Prometheus 抓取
- **前端监控面板**: 实时指标图表、健康状态显示、告警提示
- **API 性能追踪**: 响应时间 P50/P90/P99 统计
- **成本分析**: DeepSeek API 调用成本估算

## 文件结构

```
backend/monitoring/
├── __init__.py          # 模块初始化
├── health.py            # 健康检查端点
├── metrics.py           # 指标采集器
└── metrics_exporter.py  # Prometheus 指标导出和 API

frontend/js/
└── monitoring.js        # 前端监控面板

backend/main.py          # 修改：注册监控路由和中间件
backend/ai_engine/debate.py  # 修改：集成信号指标记录
frontend/index.html      # 修改：添加监控脚本引用
frontend/js/app.js       # 修改：Tab 切换初始化监控面板
```

## API 端点

### 健康检查端点

| 端点 | 描述 | 认证 |
|------|------|------|
| `GET /api/health` | 整体健康状态 | 否 |
| `GET /api/health/db` | 数据库连接状态 | 否 |
| `GET /api/health/ws` | WebSocket 连接状态 | 否 |
| `GET /api/health/ai` | AI 服务状态 | 否 |
| `GET /api/health/detailed` | 详细健康状态（含指标） | 是 |
| `GET /api/health/live` | K8s 存活探针 | 否 |
| `GET /api/health/ready` | K8s 就绪探针 | 否 |

### 指标端点

| 端点 | 描述 | 认证 |
|------|------|------|
| `GET /api/metrics` | Prometheus 格式指标 | 否 |
| `GET /api/metrics/json` | JSON 格式完整指标 | 是 |
| `GET /api/metrics/summary` | 简化指标摘要 | 否 |
| `GET /api/metrics/api-calls` | API 调用详细指标 | 是 |
| `GET /api/metrics/signals` | 信号生成指标 | 是 |
| `GET /api/metrics/performance` | 性能指标（P50/P90/P99） | 是 |
| `GET /api/metrics/cost` | 成本分析 | 是 |

## 监控指标列表

### 业务指标

- `ai_analysis_total` - AI 分析总次数（按模型分类）
- `ai_analysis_success_rate` - AI 分析成功率（最近 5 分钟）
- `signals_generated_total` - 信号生成总数
- `signals_by_symbol` - 各币种信号统计
- `signals_by_type` - 按类型统计（BUY/SELL/HOLD）
- `avg_signal_confidence` - 平均信号置信度

### 技术指标

- `http_requests_total` - HTTP 请求总数（按状态码分类）
- `http_request_duration_seconds` - HTTP 请求耗时
- `http_requests_per_second` - HTTP 请求速率
- `api_response_time_ms` - API 响应时间
- `api_latency_p50/p90/p95/p99` - API 响应时间百分位数
- `websocket_connections` - WebSocket 连接数
- `websocket_peak_connections` - WebSocket 峰值连接数

### 运营指标

- `deepseek_api_calls` - DeepSeek API 调用次数
- `deepseek_tokens_input` - 输入 Token 数量
- `deepseek_tokens_output` - 输出 Token 数量
- `api_cost_yuan` - API 成本（人民币）
- `daily_quota_usage_percent` - 每日配额使用百分比

### 系统指标

- `system_uptime_seconds` - 系统运行时间
- `database_latency_ms` - 数据库查询延迟
- `health_check_status` - 健康检查状态

## Prometheus 配置示例

```yaml
# prometheus.yml
scrape_configs:
  - job_name: 'gangzi-trading'
    static_configs:
      - targets: ['localhost:8000']
    metrics_path: '/api/metrics'
    scrape_interval: 15s
```

## Grafana 面板配置

### 1. API 成功率面板

```json
{
  "title": "API 成功率 (5分钟)",
  "targets": [
    {
      "expr": "ai_analysis_success_rate",
      "legendFormat": "成功率 %"
    }
  ],
  "type": "stat",
  "fieldConfig": {
    "thresholds": {
      "steps": [
        {"value": 0, "color": "red"},
        {"value": 95, "color": "yellow"},
        {"value": 99, "color": "green"}
      ]
    }
  }
}
```

### 2. WebSocket 连接数面板

```json
{
  "title": "WebSocket 连接数",
  "targets": [
    {
      "expr": "websocket_connections",
      "legendFormat": "{{type}} 连接"
    }
  ],
  "type": "timeseries"
}
```

### 3. API 成本面板

```json
{
  "title": "API 成本 (CNY)",
  "targets": [
    {
      "expr": "api_cost_yuan",
      "legendFormat": "今日成本"
    }
  ],
  "type": "stat"
}
```

## 告警规则

### Prometheus AlertManager 规则

```yaml
groups:
  - name: gangzi-trading
    rules:
      # API 成功率告警
      - alert: LowApiSuccessRate
        expr: ai_analysis_success_rate < 95
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "API 成功率低于 95%"
          description: "当前成功率: {{ $value }}%"
      
      # 配额告警
      - alert: QuotaWarning
        expr: daily_quota_usage_percent > 80
        for: 1m
        labels:
          severity: warning
        annotations:
          summary: "API 配额即将耗尽"
          
      - alert: QuotaCritical
        expr: daily_quota_usage_percent > 90
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "API 配额严重不足"
      
      # WebSocket 断开告警
      - alert: NoWebSocketConnections
        expr: websocket_connections == 0
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "无 WebSocket 连接"
      
      # 系统健康告警
      - alert: SystemUnhealthy
        expr: health_check_status == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "系统健康状态异常"
```

## Kubernetes 部署

### 存活探针

```yaml
livenessProbe:
  httpGet:
    path: /api/health/live
    port: 8000
  initialDelaySeconds: 30
  periodSeconds: 10
```

### 就绪探针

```yaml
readinessProbe:
  httpGet:
    path: /api/health/ready
    port: 8000
  initialDelaySeconds: 5
  periodSeconds: 5
```

## 前端监控面板

访问系统后，点击顶部导航栏的 **「⚙️ 系统监控」** Tab 即可查看：

- 系统健康状态卡片（数据库、AI 服务、行情 WebSocket）
- API 成功率实时图表
- WebSocket 连接数趋势图
- API 成本分析
- 性能指标（P50/P90/P95/P99）
- 实时告警提示

## 调试与排查

### 查看健康状态

```bash
curl http://localhost:8000/api/health | jq
```

### 查看 Prometheus 指标

```bash
curl http://localhost:8000/api/metrics
```

### 查看详细指标（需认证）

```bash
curl -H "Authorization: Bearer <token>" http://localhost:8000/api/metrics/json | jq
```

## 性能影响

- 指标采集对系统性能影响极小（异步非阻塞）
- 历史数据默认保留最近 10000 条记录
- 图表数据每 10 秒自动刷新
- 静态文件请求不计入 HTTP 指标

## 扩展开发

如需添加新的监控指标：

1. 在 `metrics.py` 中添加指标采集方法
2. 在业务代码中调用 `metrics_collector.record_xxx()`
3. 在 `metrics_exporter.py` 中添加 API 端点
4. 在前端 `monitoring.js` 中添加图表展示
