# 验收 Checklist

## 一键验证

```bash
# 1. 安装依赖
make setup

# 2. 运行完整 CI
make ci
# 预期: 所有步骤 ✓，退出码 0

# 3. 运行测试（含详细输出）
make test
# 预期: 全部 PASSED
```

## 逐项验收

### P0 — 仓库卫生
- [ ] `.gitignore` 包含 `.cache/`, `frontend-v2/`, `_backup_before_pull_*/`, `backend/*.db`, `.env`
- [ ] `git ls-files -- '.cache/'` 返回空（已 untrack）
- [ ] `git ls-files -- 'frontend-v2/'` 返回空（已 untrack）
- [ ] `git ls-files -- '*.db'` 返回空（已 untrack）
- [ ] 无硬编码密钥: `grep -rn "sk-[a-zA-Z0-9]\{20,\}" backend/` 返回空

### P1 — Schema 护栏
- [ ] `backend/ai_engine/schemas.py` 存在 SignalOutput Pydantic 模型
- [ ] `tests/test_signal_schema.py` 存在且全绿
- [ ] json_parser 返回经过 schema 验证的数据（非裸 dict）
- [ ] 非法 JSON 输入产生明确错误日志（非静默 None）

### P1 — Callback 测试
- [ ] `tests/test_callback_wiring.py` 存在且全绿
- [ ] 覆盖: signal → broadcast_signal 被调用
- [ ] 覆盖: signal → execute_signal 被调用

### P2 — 静默异常修复
- [ ] `grep -rn "except.*:.*pass" backend/` 结果数量减少
- [ ] 关键路径异常有 logger.error/warning 记录

### CI 基础设施
- [ ] `make ci` 退出码 0
- [ ] `scripts/ci.sh` 可独立执行
- [ ] `.pre-commit-config.yaml` 存在
- [ ] `.github/workflows/ci.yml` 存在

### 人工操作项（需要你执行）
- [ ] 轮换泄露的密钥（见 `docs/SECRET_ROTATION_STEPS.md`）
- [ ] 清理 git 历史中的大文件（见 `docs/HISTORY_PURGE_GUIDE.md`）
