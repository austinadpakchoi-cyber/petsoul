#!/usr/bin/env bash
# 恢复（需停服务后执行）：先校验 SHA256，再替换数据库与媒体目录；原数据改名保留，便于反悔。
# 用法：./restore.sh <备份目录>
# 注意（入住叮嘱受控记忆）：恢复旧备份后，必须重新应用备份之后发生的“撤回/删除”记录——
#   web_memory_grants.revoked_at 与 web_care_notes.revoked_at 不能被旧备份“复活”。
#   做法：恢复前从当前库导出撤回清单（见下方 SQL），恢复后重放。
set -euo pipefail
SRC="${1:?备份目录}"
DATA_DIR="${PETSOUL_DATA_DIR:-/srv/petjourney/data}"
( cd "$SRC" && sha256sum -c SHA256SUMS )
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"

if [ -f "$DATA_DIR/petjourney.sqlite3" ]; then
  "${PYTHON:-python3}" - "$DATA_DIR/petjourney.sqlite3" "$SRC/revocations-$STAMP.json" <<'PY'
import json, sqlite3, sys
with sqlite3.connect(sys.argv[1]) as c:
    notes = c.execute("SELECT note_id, revoked_at FROM web_care_notes WHERE revoked_at IS NOT NULL").fetchall()
    grants = c.execute("SELECT grant_id, revoked_at FROM web_memory_grants WHERE revoked_at IS NOT NULL").fetchall()
json.dump({"notes": notes, "grants": grants}, open(sys.argv[2], "w"))
print("revocations exported:", len(notes), "notes,", len(grants), "grants")
PY
  mv "$DATA_DIR/petjourney.sqlite3" "$DATA_DIR/petjourney.sqlite3.before-restore-$STAMP"
fi
cp "$SRC/petjourney.sqlite3" "$DATA_DIR/petjourney.sqlite3"

REVOKE="$SRC/revocations-$STAMP.json"
if [ -f "$REVOKE" ]; then
  "${PYTHON:-python3}" - "$DATA_DIR/petjourney.sqlite3" "$REVOKE" <<'PY'
import json, sqlite3, sys
data = json.load(open(sys.argv[2]))
with sqlite3.connect(sys.argv[1]) as c:
    for note_id, at in data["notes"]:
        c.execute("UPDATE web_care_notes SET revoked_at = COALESCE(revoked_at, ?) WHERE note_id = ?", (at, note_id))
    for grant_id, at in data["grants"]:
        c.execute("UPDATE web_memory_grants SET revoked_at = COALESCE(revoked_at, ?) WHERE grant_id = ?", (at, grant_id))
print("revocations re-applied")
PY
fi

for sub in uploads web-private-media; do
  if [ -f "$SRC/$sub.tgz" ]; then
    [ -d "$DATA_DIR/$sub" ] && mv "$DATA_DIR/$sub" "$DATA_DIR/$sub.before-restore-$STAMP"
    tar -C "$DATA_DIR" -xzf "$SRC/$sub.tgz"
  fi
done
echo "restored from $SRC (previous data kept with suffix .before-restore-$STAMP)"
