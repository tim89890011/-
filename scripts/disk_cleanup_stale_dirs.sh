#!/usr/bin/env bash
# scripts/disk_cleanup_stale_dirs.sh
# 清理本地磁盘上的废弃目录和文件（破坏性操作，需人工确认）
#
# 用法: bash scripts/disk_cleanup_stale_dirs.sh [--dry-run|--execute]
# 默认 --dry-run 只显示不删除
set -euo pipefail

MODE="${1:---dry-run}"

STALE_ITEMS=(
    "_archive_py"                              # 历史归档 patch 文件 (360K)
    "frontend_broken_20260221"                 # 损坏的前端备份 (142M)
    "frontend-v2"                              # 废弃的 v2 前端 (80M)
    "_backup_before_pull_20260222_140835"       # 拉取前备份 (444K)
    "frontend.tar.gz"                          # 前端压缩包 (142M)
    "钢子出击_server_backup_20260221.tar.gz"     # 服务器备份 (7.2M)
    ".cache"                                   # 回测K线缓存 (34M)
)

echo "=== 废弃文件/目录清理 ==="
echo "模式: $MODE"
echo ""

total_size=0
for item in "${STALE_ITEMS[@]}"; do
    if [ -e "$item" ]; then
        size=$(du -sh "$item" 2>/dev/null | cut -f1)
        echo "  [存在] $item ($size)"
        if [ "$MODE" = "--execute" ]; then
            rm -rf "$item"
            echo "         → 已删除"
        fi
    else
        echo "  [不存在] $item (已清理)"
    fi
done

echo ""
if [ "$MODE" = "--dry-run" ]; then
    echo "以上为 dry-run 预览。确认后执行:"
    echo "  bash scripts/disk_cleanup_stale_dirs.sh --execute"
else
    echo "清理完成。"
fi
