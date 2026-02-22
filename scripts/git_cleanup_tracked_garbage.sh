#!/usr/bin/env bash
# scripts/git_cleanup_tracked_garbage.sh
# 清理仍被 git 追踪的垃圾文件（幂等，可重复执行）
# 仅执行 git rm --cached（保留本地文件）
set -euo pipefail

echo "检查并清理 git 追踪的垃圾文件..."

cleanup() {
    local pattern="$1"
    local desc="$2"
    local files
    files=$(git ls-files -- "$pattern" 2>/dev/null || true)
    if [ -n "$files" ]; then
        echo "清理 $desc: $(echo "$files" | wc -l | tr -d ' ') 个文件"
        git rm --cached -r "$pattern" 2>/dev/null || true
    else
        echo "✓ $desc: 已干净"
    fi
}

cleanup '.cache/'               '缓存目录'
cleanup 'frontend-v2/'          '废弃的 frontend-v2'
cleanup '_backup_before_pull_*/' '拉取前备份'
cleanup 'frontend_broken_*/'    '损坏的前端备份'
cleanup 'backend/*.db'          '数据库文件'
cleanup 'Users/'                '本地路径泄露'
cleanup '*.tar.gz'              '压缩包'

echo ""
echo "完成。请检查 git status 并提交变更。"
