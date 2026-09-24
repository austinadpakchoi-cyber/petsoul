"""用真实模型验一次“自主决策”（默认 shadow，不出门）。

为什么单独一个脚本：平时的用例都用假模型，证明不了“真的是模型在选”。这里在一个**全新的临时库**里
建一个新家庭、一只新宠物，只打开对话模型这一个供应商（地图、生图都不配），然后走一次完整决策：
规则给可行机会 → 预算预占 → 真实模型选一项 → 复核 → （live 时）变成真实行程。

边界：
- 会产生**真实的付费模型调用**（默认 1 次），所以必须显式加 --yes；不加就只打印会做什么。
- 只用 PetJourneyBackend/data/secrets/web-providers.env 里已授权的对话模型；不读外部环境里的密钥，不打印密钥。
- 临时库用完就删；不碰 18763 的验收环境，不碰生产。
- 默认 --mode shadow：调用模型、记录它会选什么，但不出门、不发消息。--mode live 才真的执行。

用法（在仓库根目录）：
    python scripts/verify_brain_live.py --dry-run            # 不配模型、不花钱：只验这条链路跑得通
    python scripts/verify_brain_live.py --yes                # shadow：看模型会选什么
    python scripts/verify_brain_live.py --yes --mode live    # live：让这次选择真的成行
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "PetJourneyBackend"
SECRETS = BACKEND / "data" / "secrets" / "web-providers.env"
EVIDENCE = BACKEND / "data" / "web-real-acceptance" / "evidence"
PREFIX = "/api/v1/web"
NOON_HK = datetime(2026, 9, 23, 4, 0, tzinfo=timezone.utc)  # 香港 12:00：醒着、在出门时段
LLM_KEYS = ("OPENAI_API_KEY", "PETJOURNEY_LLM_PROVIDER", "PETJOURNEY_OPENAI_BASE_URL", "PETJOURNEY_AGENT_MODEL")

sys.path.insert(0, str(BACKEND))


def load_llm_secrets() -> dict[str, str]:
    """只取对话模型那几项；地图与生图一概不配，这次验证不产生它们的调用。"""
    if not SECRETS.exists():
        raise SystemExit(f"找不到供应商配置：{SECRETS.relative_to(ROOT)}")
    values: dict[str, str] = {}
    for line in SECRETS.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() in LLM_KEYS and value.strip():
            values[key.strip()] = value.strip()
    if "OPENAI_API_KEY" not in values:
        raise SystemExit("配置里没有对话模型的密钥，先配好再验")
    return values


DROP_KEYS = ("OPENAI_API_KEY", "AMAP_API_KEY", "GOOGLE_MAPS_API_KEY", "DOUBAO_API_KEY", "IMAGE_API_KEY", "PETJOURNEY_IMAGE_API_KEY")


def build_env(data_dir: Path, mode: str, secrets: dict[str, str]) -> dict[str, str]:
    """只返回要覆盖的那些变量：系统自己的环境（PATH、SystemRoot 等）原样保留，不清空。"""
    env: dict[str, str] = {}
    env.update({
        "TZ": "UTC",
        "PETJOURNEY_DB_PATH": str(data_dir / "brain-check.sqlite3"),
        "PETJOURNEY_UPLOAD_DIR": str(data_dir / "uploads"),
        "PETJOURNEY_WEB_PRIVATE_MEDIA_DIR": str(data_dir / "media"),
        "PETJOURNEY_AUTH_SECRET": uuid.uuid4().hex * 2,
        "PETJOURNEY_WEB_COOKIE_SECURE": "false",
        "PETJOURNEY_SCHEDULER_ENABLED": "false",
        "PETJOURNEY_WEB_WORLD_RUNNER": "off",
        "PETJOURNEY_WEB_ENVIRONMENT": "real-local",
        "PETJOURNEY_WEB_DEMO_CATALOG": "",
        "PETJOURNEY_WEB_PROVIDERS": "1",
        "PETJOURNEY_PROVIDER_MODE": "mock",
        "PETJOURNEY_MAP_PROVIDER": "mock",
        "PETJOURNEY_WEB_BRAIN_MODE": mode,
        "PETJOURNEY_WEB_BRAIN_DAILY_PER_PET": "2",
        "PETJOURNEY_WEB_LLM_DAILY_CAP": "4",
    })
    env.update(secrets)
    return env


def install_clock(now: datetime):
    """把 app.* 里对 utcnow 的引用换成固定时刻（宠物在醒着的中午做决定），不改生产代码。"""
    import app.utils as utils

    original = utils.utcnow
    patched = [mod for name, mod in list(sys.modules.items())
               if (name == "app" or name.startswith("app.")) and getattr(mod, "utcnow", None) is original]
    for mod in patched:
        setattr(mod, "utcnow", lambda: now)
    return lambda: [setattr(mod, "utcnow", original) for mod in patched]


def make_family(client) -> tuple[str, str, str]:
    """新账号 → 上传一只宠物 → 入住 → 同意把共用资料交给模型。返回 (user_id, pet_id, home_id)。"""
    name = f"brainchk{uuid.uuid4().hex[:8]}"
    registered = client.post(f"{PREFIX}/auth/register", json={"username": name, "password": "longpassword1"})
    _ok(registered, "注册")
    user_id = registered.json()["user"]["user_id"]
    pet = client.post(f"{PREFIX}/pets", data={"name": "小海", "species": "cat"}, files={"photo": ("pet.png", png_bytes(), "image/png")},
                      headers=_head(client))
    _ok(pet, "上传宠物")
    pet_id = pet.json()["pet_id"]
    home = client.post(f"{PREFIX}/onboarding/move-in", json={"pet_id": pet_id, "public_posts": True}, headers=_head(client))
    _ok(home, "入住")
    _ok(client.patch(f"{PREFIX}/settings", json={"model_replies": True}, headers=_head(client)), "同意模型回信")
    return user_id, pet_id, home.json()["home_id"]


def _head(client) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies.get("petsoul_csrf") or "", "Idempotency-Key": uuid.uuid4().hex}


def _ok(response, what: str):
    if response.status_code >= 400:
        raise SystemExit(f"{what}失败：{response.status_code} {response.text[:300]}")
    return response


def png_bytes() -> bytes:
    """1×1 的 PNG，带一条香港的 GPS 备注（和测试夹具一样，让新家落在香港）。"""
    import zlib

    def chunk(kind: bytes, payload: bytes) -> bytes:
        return len(payload).to_bytes(4, "big") + kind + payload + zlib.crc32(kind + payload).to_bytes(4, "big")

    body = chunk(b"IHDR", (1).to_bytes(4, "big") + (1).to_bytes(4, "big") + bytes([8, 2, 0, 0, 0]))
    body += chunk(b"tEXt", b"GPS" + bytes([0]) + b"22.28,114.15")
    body += chunk(b"IDAT", zlib.compress(bytes([0, 255, 0, 0]))) + chunk(b"IEND", b"")
    return bytes([0x89]) + b"PNG" + bytes([13, 10, 26, 10]) + body


def run(mode: str) -> dict:
    from fastapi.testclient import TestClient

    from app.main import create_app

    app = create_app()
    restore = install_clock(NOON_HK)
    try:
        with TestClient(app) as client:
            _, pet_id, _ = make_family(client)
            web = app.state.web
            life = web.brain_life
            life.mode = mode
            chat = web.providers.chat
            before = calls_today(app, "llm")
            outcome = life.consider(pet_id, NOON_HK)
            after = calls_today(app, "llm")
            journey = web.journeys.repo.active_for_pet(pet_id)
            row = web.projector.runtime.row(pet_id)
            return {
                "模式": mode,
                "模型供应商": getattr(life.brain.model, "provider_label", "?"),
                "模型可用": bool(getattr(chat, "available", False)),
                "结论": {"status": outcome.status, "composed_by": outcome.composed_by, "destination_key": outcome.destination_key,
                         "intent": outcome.intent, "reason": outcome.reason, "operation_id": outcome.operation_id},
                "真实调用次数": {"之前": before, "之后": after},
                "真的成行了吗": None if journey is None else {"journey_id": journey.journey_id, "destination_key": journey.destination_key,
                                                      "departed_at": journey.departed_at.isoformat()},
                "运行记录": _decision_row(row),
            }
    finally:
        restore()


def _decision_row(row) -> dict | None:
    """运行记录里“上次是谁决定的、什么时候”；还没记过就返回 None（不同版本的列名不一定齐全）。"""
    if row is None:
        return None
    keys = set(row.keys())
    return {k: row[k] for k in ("last_decision_by", "last_decision_at", "next_review_at") if k in keys} or None


def calls_today(app, provider: str) -> int | None:
    if getattr(app.state.web.providers, "meter", None) is None:
        return None
    with app.state.storage.connect() as conn:
        row = conn.execute("SELECT calls FROM web_provider_usage WHERE provider = ?", (provider,)).fetchone()
    return None if row is None else row["calls"]


def main() -> int:
    parser = argparse.ArgumentParser(description="用真实模型验一次自主决策（会产生真实付费调用）")
    parser.add_argument("--mode", choices=("shadow", "live"), default="shadow")
    parser.add_argument("--yes", action="store_true", help="确认要发起真实模型调用")
    parser.add_argument("--dry-run", action="store_true", help="不配置模型、不发起任何调用，只验证这条链路能跑通")
    parser.add_argument("--out", default=str(EVIDENCE / "24-brain-real-model.json"))
    args = parser.parse_args()
    sys.stdout.reconfigure(errors="replace")

    if not (args.yes or args.dry_run):
        print(f"这会在一个临时库里发起 1 次真实的对话模型调用（模式 {args.mode}）。确认请加 --yes；只想验链路就加 --dry-run。")
        return 0
    data_dir = Path(tempfile.mkdtemp(prefix="brain-check-"))
    import os

    saved = dict(os.environ)
    for key in DROP_KEYS:
        os.environ.pop(key, None)  # 不继承外部环境里的密钥，只用白名单文件里的
    os.environ.update(build_env(data_dir, args.mode, {} if args.dry_run else load_llm_secrets()))
    try:
        result = run(args.mode)
    finally:
        os.environ.clear()
        os.environ.update(saved)
        shutil.rmtree(data_dir, ignore_errors=True)

    result["记录时间"] = datetime.now(timezone.utc).isoformat()
    result["说明"] = ("链路演练：没有配置模型，所以不会有任何调用；看的是这条链路能不能跑到底。" if args.dry_run
                    else "全新临时库、只配了对话模型；临时库已删除。判定看 composed_by 是否为 model。")
    if args.dry_run:
        ok = result["结论"]["composed_by"] in ("rule_fallback", None) and result["真实调用次数"]["之后"] in (None, 0)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        print("链路演练：", "跑得通，且确实一次调用都没有" if ok else "有问题，看上面的 reason")
        return 0 if ok else 1
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    ok = result["结论"]["composed_by"] == "model"
    print("结论：", "真的是模型在选（composed_by=model）" if ok else "不是模型选的，看 reason")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
