#!/usr/bin/env bash
# 发布网页静态产物：复制已构建的 dist 到 releases/<标签>，校验无密钥模式后原子切换 releases/current。
# 用法：./release.sh <标签>      （先在 PetJourneyWeb 里构建 live 版：npm run build -- --mode live；不带 --mode 构建出来的是演示版）
set -euo pipefail
TAG="${1:?版本标签，例如 git 短 SHA}"
HERE="$(cd "$(dirname "$0")/.." && pwd)"
DIST="$HERE/../../PetJourneyWeb/dist"
REL="$HERE/releases"
[ -f "$DIST/index.html" ] || { echo "缺少 $DIST/index.html，请先构建"; exit 1; }
if grep -RIlE "sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|PETJOURNEY_AUTH_SECRET|BEGIN (RSA|EC) PRIVATE KEY" "$DIST" >/dev/null; then
  echo "dist 中发现疑似密钥，停止发布"; exit 1
fi
# 必须是 live 构建。原先这里查 index.html 里的 "fixture" 字样，**永远不会响**（数据模式根本不在 index.html 里），
# 而且只 echo、不拦发布（Q 2026-09-25 实测：用同一份源码构建演示版与 live 版对照，两份 index.html 只差哈希文件名）。
# 判据：数据模式被压缩成 `return`live`` / `return`fixture`` 这一小段，出现在 assets 里（两份对照构建实测 1/0）。
# 限度：依赖压缩器当前的输出形状；形状变了这道检查会误拦——宁可误拦、不可误放。更稳的是让构建把模式写进 index.html（前端源码改动，另议）。
if ! grep -rqF 'return`live`' "$DIST/assets"; then
  echo "dist 不是 live 构建（VITE_PETSOUL_DATA_MODE 没设成 live），停止发布"; exit 1
fi
mkdir -p "$REL/$TAG"
cp -R "$DIST/." "$REL/$TAG/"
PREV="$(readlink "$REL/current" 2>/dev/null || true)"
ln -sfn "$TAG" "$REL/current.tmp" && mv -Tf "$REL/current.tmp" "$REL/current"
echo "$TAG" >> "$REL/HISTORY"
echo "current -> $TAG（上一版：${PREV:-无}）"
