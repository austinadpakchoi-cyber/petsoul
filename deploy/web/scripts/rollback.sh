#!/usr/bin/env bash
# 回滚：网页切回上一个 releases 版本；后端切回上一个镜像标签。数据库迁移只增不删，旧版本代码可读新表。
# 用法：./rollback.sh [网页标签] [后端镜像标签]    不带参数时网页回到 HISTORY 里的上一版
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
REL="$HERE/releases"
TARGET="${1:-$(tail -n 2 "$REL/HISTORY" | head -n 1)}"
[ -d "$REL/$TARGET" ] || { echo "没有 releases/$TARGET"; exit 1; }
ln -sfn "$TARGET" "$REL/current.tmp" && mv -Tf "$REL/current.tmp" "$REL/current"
echo "$TARGET" >> "$REL/HISTORY"
echo "web current -> $TARGET"
if [ -n "${2:-}" ]; then
  PETSOUL_RELEASE="$2" docker compose -f "$HERE/docker-compose.web.example.yml" up -d --no-build backend
  echo "backend -> petsoul-backend:$2"
fi
