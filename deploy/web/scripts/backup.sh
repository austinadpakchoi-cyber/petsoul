#!/usr/bin/env bash
# 在线备份：SQLite 用 .backup API（事务一致，不需要停服务）+ 上传与私有媒体目录打包。
# 用法：./backup.sh [备份目录]        默认 ./backups
# 在容器里执行：docker compose -f ../docker-compose.web.example.yml exec backend bash /srv/petjourney/deploy-scripts/backup.sh
set -euo pipefail
DATA_DIR="${PETSOUL_DATA_DIR:-/srv/petjourney/data}"
OUT_DIR="${1:-./backups}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DEST="$OUT_DIR/petsoul-$STAMP"
mkdir -p "$DEST"

"${PYTHON:-python3}" - "$DATA_DIR/petjourney.sqlite3" "$DEST/petjourney.sqlite3" <<'PY'
import sqlite3, sys
src, dst = sys.argv[1], sys.argv[2]
with sqlite3.connect(src) as s, sqlite3.connect(dst) as d:
    s.backup(d)
    # 备份自检：能打开、完整性通过、迁移表存在
    assert d.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    d.execute("SELECT COUNT(*) FROM web_schema_migrations").fetchone()
print("sqlite backup ok:", dst)
PY

for sub in uploads web-private-media; do
  if [ -d "$DATA_DIR/$sub" ]; then
    tar -C "$DATA_DIR" -czf "$DEST/$sub.tgz" "$sub"
  fi
done
( cd "$DEST" && sha256sum * > SHA256SUMS )
echo "backup written: $DEST"
