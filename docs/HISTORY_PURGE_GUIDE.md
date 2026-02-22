# Git 历史清理指南

> **需要人工执行** — 此操作会重写 git 历史，影响所有协作者。

## 为什么需要清理

当前 git 历史中包含：
- `.cache/backtest_klines/` — 约 2770 个 JSON 文件（数 MB）
- `frontend-v2/node_modules/` — node 依赖
- `backend/*.db` — SQLite 数据库文件
- 可能的 `.env` 历史版本（含密钥）

虽然已经 `git rm --cached`，但这些文件仍存在于历史提交中，占用仓库体积。

## 方案 A: git-filter-repo（推荐）

```bash
# 1. 安装
pip install git-filter-repo

# 2. 备份当前仓库（必须！）
cp -r .git .git-backup

# 3. 清理大文件/敏感文件
git filter-repo --invert-paths \
  --path .cache/ \
  --path frontend-v2/node_modules/ \
  --path backend/gangzi.db \
  --path backend/trade_history.db \
  --path .env

# 4. 验证仓库大小
git count-objects -vH

# 5. 强制推送（⚠️ 影响所有协作者）
git push origin --force --all
```

## 方案 B: BFG Repo-Cleaner

```bash
# 1. 下载 BFG
# https://rtyley.github.io/bfg-repo-cleaner/

# 2. 删除大文件
java -jar bfg.jar --delete-files '*.db' --delete-folders '.cache'

# 3. 清理
git reflog expire --expire=now --all
git gc --prune=now --aggressive

# 4. 强制推送
git push origin --force --all
```

## 风险提示

1. **所有协作者必须重新 clone**，或执行 `git fetch --all && git reset --hard origin/main`
2. **PR/Issue 中的 commit hash 会失效**
3. **建议在没有进行中的 PR 时操作**
4. **务必先备份 `.git` 目录**

## 验证步骤

```bash
# 清理后验证无敏感文件
git log --all --full-history -- '.env' | head -5
# 应该无输出

# 验证仓库大小减小
git count-objects -vH
```
