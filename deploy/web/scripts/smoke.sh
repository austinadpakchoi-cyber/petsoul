#!/usr/bin/env bash
# 部署后冒烟：元信息、能力诚实性、深链接刷新（SPA 回退）、旧接口/文档不对公网暴露、未登录写操作被拒。
# 用法：./smoke.sh https://web.example.invalid
set -euo pipefail
BASE="${1:?站点根地址}"
fail() { echo "FAIL: $*"; exit 1; }
meta="$(curl -fsS "$BASE/api/v1/web/meta")" || fail "meta 不可达"
echo "$meta" | "${PYTHON:-python3}" -c 'import json,sys; m=json.load(sys.stdin); assert m["data_origin"]=="live"; c={x["key"]:x["status"] for x in m["capabilities"]}; assert c["market.player_listing"]=="disabled"; assert c["intent.layer"] in ("disabled","available"); print("meta ok", m["contract_version"], m["backend_version"])'
for path in / /home /journey /circle /communicator /onboarding/reception /visits/any /homes/any; do
  code="$(curl -s -o /dev/null -w '%{http_code}' "$BASE$path")"
  [ "$code" = "200" ] || fail "深链接 $path 返回 $code"
done
for path in /docs /openapi.json /api/v1/pets; do
  code="$(curl -s -o /dev/null -w '%{http_code}' "$BASE$path")"
  [ "$code" = "404" ] || [ "$code" = "401" ] || [ "$code" = "403" ] || fail "$path 不应公开（$code）"
done
code="$(curl -s -o /dev/null -w '%{http_code}' -X POST "$BASE/api/v1/web/journey/depart" -H 'Content-Type: application/json' -d '{"destination_key":"harbour_cafe"}')"
[ "$code" = "401" ] || [ "$code" = "403" ] || fail "未登录出发应被拒（$code）"
curl -fsSI "$BASE/" | grep -qi "strict-transport-security" || fail "缺少 HSTS"
echo "smoke ok: $BASE"
