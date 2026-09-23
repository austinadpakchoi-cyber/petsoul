#!/usr/bin/env bash
# 发布网页静态产物：复制已构建的 dist 到 releases/<标签>，校验无密钥模式后原子切换 releases/current。
# 用法：./release.sh <标签>      （先在 PetJourneyWeb 里 live 模式 npm run build）
set -euo pipefail
TAG="${1:?版本标签，例如 git 短 SHA}"
HERE="$(cd "$(dirname "$0")/.." && pwd)"
DIST="$HERE/../../PetJourneyWeb/dist"
REL="$HERE/releases"
[ -f "$DIST/index.html" ] || { echo "缺少 $DIST/index.html，请先构建"; exit 1; }
if grep -RIlE "sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|PETJOURNEY_AUTH_SECRET|BEGIN (RSA|EC) PRIVATE KEY" "$DIST" >/dev/null; then
  echo "dist 中发现疑似密钥，停止发布"; exit 1
fi
grep -q '"fixture"' "$DIST/index.html" && echo "注意：index.html 含 fixture 字样，请确认是 live 构建" || true
mkdir -p "$REL/$TAG"
cp -R "$DIST/." "$REL/$TAG/"
PREV="$(readlink "$REL/current" 2>/dev/null || true)"
ln -sfn "$TAG" "$REL/current.tmp" && mv -Tf "$REL/current.tmp" "$REL/current"
echo "$TAG" >> "$REL/HISTORY"
echo "current -> $TAG（上一版：${PREV:-无}）"
