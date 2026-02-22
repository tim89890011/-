# 数据库迁移管理指南

本文档介绍「钢子出击」项目的数据库迁移管理流程，使用 Alembic 工具进行版本控制。

## 目录

- [概述](#概述)
- [安装与初始化](#安装与初始化)
- [常用命令](#常用命令)
- [迁移脚本说明](#迁移脚本说明)
- [生产环境迁移](#生产环境迁移)
- [故障排查](#故障排查)

## 概述

### 为什么需要数据库迁移？

- **版本控制**：跟踪数据库结构的变更历史
- **团队协作**：确保开发、测试、生产环境的数据库结构一致
- **安全回滚**：支持回退到之前的版本
- **自动化部署**：CI/CD 流程中自动执行数据库升级

### 技术栈

- **Alembic**: SQLAlchemy 的数据库迁移工具
- **SQLite**: 开发环境数据库
- **Async SQLAlchemy**: 异步数据库操作支持

## 安装与初始化

### 1. 安装依赖

```bash
# 确保已安装 alembic
pip install alembic

# 或在项目根目录执行
pip install -r requirements.txt
```

### 2. 初始化 Alembic（已完成）

项目已配置好 Alembic，如需在新项目初始化：

```bash
alembic init alembic
```

### 3. 配置数据库连接

编辑 `alembic.ini` 文件：

```ini
# 开发环境（默认）
sqlalchemy.url = sqlite+aiosqlite:///./data/gangzi.db

# 生产环境（PostgreSQL 示例）
# sqlalchemy.url = postgresql+asyncpg://user:password@localhost/gangzi
```

或通过环境变量覆盖：

```bash
export DATABASE_URL="sqlite+aiosqlite:///./data/gangzi.db"
```

## 常用命令

### 查看当前状态

```bash
# 查看当前版本
alembic current

# 查看迁移历史
alembic history --verbose

# 查看待执行的迁移
alembic history --indicate-current
```

### 创建迁移脚本

```bash
# 自动根据 models.py 变更生成迁移脚本
alembic revision --autogenerate -m "添加用户邮箱字段"

# 手动创建空迁移脚本
alembic revision -m "手动数据修复"
```

### 执行迁移

```bash
# 升级到最新版本
alembic upgrade head

# 升级到指定版本
alembic upgrade 001

# 降级到前一个版本
alembic downgrade -1

# 降级到指定版本
alembic downgrade 001

# 降级到最初状态（所有表）
alembic downgrade base
```

### 预览迁移 SQL（不实际执行）

```bash
# 查看升级 SQL
alembic upgrade head --sql

# 查看降级 SQL
alembic downgrade -1 --sql
```

## 迁移脚本说明

### 已有迁移脚本

| 版本 | 文件名 | 描述 |
|------|--------|------|
| 001 | `001_initial.py` | 初始迁移，创建所有基础表 |
| 002 | `002_compliance_fixes.py` | 合规性修复，移除敏感字段，添加风险评估 |

### 001_initial.py

创建以下表：

- `users` - 用户表
- `ai_signals` - AI 信号表（含仓位/杠杆等敏感字段）
- `signal_results` - 信号验证表
- `chat_messages` - 聊天记录表
- `analyze_cooldowns` - 分析冷却记录
- `revoked_tokens` - 吊销的 JWT Token
- `auth_rate_limits` - 认证限流记录

### 002_compliance_fixes.py

合规性修复，包含以下变更：

**ai_signals 表：**
- 移除: `position_pct` (建议仓位百分比)
- 移除: `leverage` (建议杠杆倍数)
- 移除: `stop_loss_pct` (建议止损百分比)
- 移除: `take_profit_pct` (建议止盈百分比)
- 添加: `risk_assessment` (风险评估 JSON)

**signal_results 表：**
- 添加: `direction_result` (方向一致性结果)

**新增 notifications 表：**
- 用户通知记录表

## 生产环境迁移

### 迁移前检查清单

- [ ] 备份数据库
- [ ] 在测试环境验证迁移脚本
- [ ] 检查迁移脚本的降级逻辑
- [ ] 确认维护窗口时间

### 生产环境执行流程

```bash
# 1. 备份数据库
cp /path/to/gangzi.db /path/to/gangzi.db.backup.$(date +%Y%m%d)

# 2. 设置生产环境变量
export DATABASE_URL="postgresql+asyncpg://prod_user:xxx@db.prod/gangzi"

# 3. 预览迁移 SQL
alembic upgrade head --sql > migration_preview.sql

# 4. 执行迁移
alembic upgrade head

# 5. 验证
alembic current
```

### 回滚流程

```bash
# 如果迁移后出现问题，立即回滚
alembic downgrade -1

# 或回滚到指定版本
alembic downgrade 001
```

## 故障排查

### 问题 1: "Can't locate revision identified by 'xxx'"

**原因**：数据库中的版本号与本地迁移脚本不匹配

**解决**：
```bash
# 查看数据库当前版本
alembic current

# 如果数据库版本不存在于本地，可手动标记为 base
alembic stamp base

# 然后重新升级到目标版本
alembic upgrade head
```

### 问题 2: SQLite 不支持 ALTER TABLE DROP COLUMN

**说明**：002 迁移脚本已处理此问题，使用表重建策略

**手动处理**：
```python
# 使用 batch_alter_table 在 SQLite 中模拟 ALTER
with op.batch_alter_table('table_name') as batch_op:
    batch_op.drop_column('column_name')
```

### 问题 3: 迁移后 models.py 与数据库不一致

**解决**：
```bash
# 重新生成迁移脚本
alembic revision --autogenerate -m "同步 models.py 变更"

# 执行迁移
alembic upgrade head
```

### 问题 4: 迁移执行超时

**原因**：大数据量表的结构变更

**解决**：
- 考虑使用 `op.execute()` 执行原生 SQL 分批处理
- 或在低峰期执行迁移

## 最佳实践

1. **提交迁移脚本到版本控制**：所有迁移脚本都应提交到 Git
2. **测试迁移脚本**：在合并到主分支前，在测试环境验证
3. **保持迁移脚本幂等**：确保重复执行不会出错
4. **记录破坏性变更**：在迁移脚本注释中说明不兼容变更
5. **定期清理旧迁移**：项目稳定后，可合并旧迁移到基础迁移

## 参考文档

- [Alembic 官方文档](https://alembic.sqlalchemy.org/)
- [SQLAlchemy 文档](https://docs.sqlalchemy.org/)
- [项目 README](../README.md)
