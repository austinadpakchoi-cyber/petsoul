#!/usr/bin/env python3
"""运营后台的本地演示数据（仅开发）：隔离数据库、假供应商、零真实付费。

    python scripts/seed_admin_demo.py            # 已存在时拒绝覆盖
    python scripts/seed_admin_demo.py --reset    # 先删掉演示目录再生成（只删 data/web-admin-demo）

只写 `PetJourneyBackend/data/web-admin-demo/`（已被 .gitignore 覆盖）；不碰开发库、正式库，
也不碰其他窗口正在用的数据库。全程供应商关闭 + 替身生图，**一次真实付费调用都不会发生**。

造出来的东西（都是走真实业务接口跑出来的，不是往表里塞行）：
- 8 个员工账号，覆盖平台负责人 / 客服 / 运维 / 内容编辑 / 内容发布 / 审核 / 经济运营 / 经济负责人；
- 4 个玩家账号：三个领养居民（一个正常、一个照片出问题、一个发过公开动态并被举报），
  外加一个带自己的宠物来、上传过参考照的（用来验证参考照不能变成公共素材）；
- 3 张照片分别停在**已出图 / 没画成 / 结果未确认**——后两种就是后台要分辨的那两类；
- 一条公开动态与一条举报，供审核队列演示。

口令写在演示目录的 `admin-demo-logins.local.txt`，不打印、不进仓库。
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "PetJourneyBackend"
DEMO_DIR = BACKEND_DIR / "data" / "web-admin-demo"
PREFIX = "/api/v1/web"
STAFF_PASSWORD = "petsoul-demo-staff-2026"
PLAYER_PASSWORD = "petsoul-demo-player"

# 供应商密钥一律置空：即使 PetJourneyBackend/.env 里有真实密钥也读不到（config.load_env_file 不覆盖已有变量）。
for name in ("OPENAI_API_KEY", "AMAP_API_KEY", "GOOGLE_MAPS_API_KEY", "DOUBAO_API_KEY",
             "PETJOURNEY_IMAGE_API_KEY", "IMAGE_API_KEY", "OPENAI_IMAGE_API_KEY", "PETJOURNEY_WEB_PROVIDERS"):
    os.environ[name] = ""
os.environ["TZ"] = "UTC"

sys.path.insert(0, str(BACKEND_DIR))


class ReplayClock:
    """可推进的服务器时钟：把 app.* 里对 utils.utcnow 的引用换成它，让事件都发生在过去。"""

    def __init__(self, start: datetime) -> None:
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs) -> datetime:
        self.now = self.now + timedelta(**kwargs)
        return self.now

    def install(self) -> "ReplayClock":
        import app.utils as utils

        original = utils.utcnow
        for name, module in list(sys.modules.items()):
            if (name == "app" or name.startswith("app.")) and getattr(module, "utcnow", None) is original:
                setattr(module, "utcnow", self)
        return self


class DemoIllustrator:
    """替身生图：不联网、不付费。按 `fail_reason` 造三种结局。"""

    available = True
    provider_label = "演示替身"

    def __init__(self) -> None:
        self.fail_reason: str | None = None

    def render(self, prompt, reference=None, size="2048x2048"):
        from app.image_provider.models import GeneratedImage
        from app.web_providers import ImageUnavailable

        if self.fail_reason:
            raise ImageUnavailable(self.fail_reason)
        # 一张 8x8 纯色 PNG：能存能取、结构合法，但明显不是真实成图。
        # （早先这里写死了一段手抄的十六进制，IDAT 声明长度与实际数据对不上，
        #  存成身份头像之后任何解析器都会说 png_truncated——现在按字节现算，不再手抄。）
        return GeneratedImage(image_bytes=_solid_png(8, 8, (120, 140, 160)), mime_type="image/png",
                              model="demo-stub", provider="demo", source="stub")


class Player:
    def __init__(self, app, username: str) -> None:
        from fastapi.testclient import TestClient

        self.app = app
        self.client = TestClient(app)
        response = self.client.post(f"{PREFIX}/auth/register", json={"username": username, "password": PLAYER_PASSWORD})
        assert response.status_code == 201, response.text
        self.username = username
        self.user_id = response.json()["user"]["user_id"]
        self.pet_id: str | None = None

    @property
    def csrf(self) -> str:
        return self.client.cookies.get("petsoul_csrf") or ""

    def get(self, path: str):
        return self.client.get(f"{PREFIX}{path}")

    def post(self, path: str, body=None):
        import uuid

        return self.client.post(f"{PREFIX}{path}", json=body,
                                headers={"X-CSRF-Token": self.csrf, "Idempotency-Key": f"seed-{uuid.uuid4().hex[:16]}"})

    def patch(self, path: str, body=None):
        return self.client.patch(f"{PREFIX}{path}", json=body, headers={"X-CSRF-Token": self.csrf})

    def put(self, path: str, body=None):
        import uuid

        return self.client.put(f"{PREFIX}{path}", json=body,
                               headers={"X-CSRF-Token": self.csrf, "Idempotency-Key": f"seed-{uuid.uuid4().hex[:16]}"})

    def adopt(self, candidate_id: str) -> None:
        response = self.post("/adoption/adopt", {"candidate_id": candidate_id})
        assert response.status_code == 200, response.text
        self.pet_id = response.json()["pet_id"]
        moved = self.post("/onboarding/move-in", {"public_posts": True})
        assert moved.status_code == 200, moved.text
        self.pet_id = moved.json()["pet_id"]


def _solid_png(width: int, height: int, rgb: tuple[int, int, int]) -> bytes:
    """按字节现算一张纯色 PNG（不依赖 Pillow，也不手抄十六进制）。"""
    import struct
    import zlib

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    raw = b"".join(bytes([0]) + bytes(rgb) * width for _ in range(height))
    body = chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    body += chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")
    return bytes([0x89]) + b"PNG" + bytes([13, 10, 26, 10]) + body


def _demo_banner() -> bytes:
    """演示用的一张横幅。装了 Pillow 就画一张 480x160 的纯色图，没装就退回 1x1 PNG（如实，不假装）。"""
    try:
        import io

        from PIL import Image

        image = Image.new("RGB", (480, 160), (58, 96, 140))
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()
    except Exception:  # noqa: BLE001
        return _solid_png(48, 16, (58, 96, 140))


def top_up(web, pet_id: str, amount: int = 40) -> None:
    import uuid

    from app.schemas.base import EconomyTransactionType

    web.economy.apply(pet_id, amount, EconomyTransactionType.web_reward, f"seed:topup:{uuid.uuid4().hex[:12]}",
                      reason="演示数据准备旅费", source="seed.admin_demo")


def cafe_trip(player: Player, web, clock: ReplayClock, illustrator: DemoIllustrator, fail_reason: str | None) -> None:
    """走一次真实的咖啡馆之旅：到店 → 和居民打招呼（触发冒险）→ 拍一张照片 → 执行生图任务。"""
    illustrator.fail_reason = fail_reason
    top_up(web, player.pet_id)
    depart = player.post("/journey/depart", {"destination_key": "harbour_cafe"})
    assert depart.status_code == 200, depart.text
    clock.advance(minutes=7)
    visit_id = player.get("/journey/map").json()["current_visit_id"]
    assert visit_id, "这一刻应该已经到店了"
    activities = player.get(f"/visits/{visit_id}").json()["activities"]
    for kind in ("greet_resident", "take_photo"):
        target = next((a for a in activities if a["kind"] == kind), None)
        if target is not None:
            player.post(f"/visits/{visit_id}/actions", {"activity_id": target["activity_id"]})
            clock.advance(seconds=5)
    web.illustrations.run_pending()
    clock.advance(hours=2)
    web.journeys.advance_all(clock.now)
    from app.web_journey import FAST, SLOW

    web.journeys.deliver_outbox(clock.now, lanes=(FAST, SLOW))
    clock.advance(minutes=20)


def social_demo(players: list[Player], clock: ReplayClock) -> str:
    """林、赵、陈三位之间：赵在林的动态下评论、点赞、关注林家宠物；林把被自己举报的那位拉黑；
    林报名驾校、填一条带忌口的口味（忌口恒为私密，后台只看得到条数）；陈打开集市。"""
    lin, zhao, chen = players[0], players[1], players[2]
    with lin.app.state.storage.connect() as conn:
        own = conn.execute("SELECT post_id FROM web_posts WHERE user_id = ? AND visibility = 'public' ORDER BY created_at DESC LIMIT 1",
                           (lin.user_id,)).fetchone()
        reported = conn.execute("SELECT target_id FROM web_reports WHERE reporter_user_id = ? AND target_kind = 'post' LIMIT 1",
                                (lin.user_id,)).fetchone()
    done = []
    if own is not None:
        steps = [zhao.post(f"/posts/{own['post_id']}/comments", {"as_actor": "owner", "text": "看起来好惬意，下次也想带它去这家咖啡馆"}),
                 zhao.post(f"/posts/{own['post_id']}/reactions", {"as_actor": "owner"}),
                 zhao.post(f"/pets/{lin.pet_id}/follow", {"follow": True})]
        done.append("赵评论、点赞、关注林家宠物：" + " / ".join(str(r.status_code) for r in steps))
    if reported is not None:
        done.append(f"林拉黑被自己举报的作者：{lin.post('/blocks', {'post_id': reported['target_id']}).status_code}")
    done.append(f"林报名驾校：{lin.post('/driving/enroll').status_code}")
    preference = {"preference_id": "pref-demo-lin-owner", "subject": "owner", "pet_id": lin.pet_id, "version": 1, "label": "清淡",
                  "taste": {"spicy": -1}, "restrictions": [{"kind": "allergy", "label": "花生（只写给家人看）"}], "source": "explicit",
                  "updated_at": clock.now.astimezone(timezone.utc).isoformat()}
    done.append(f"林填口味：{lin.put('/food/preferences/owner', preference).status_code}")
    done.append(f"陈打开集市：{chen.get('/market').status_code}")
    return "社交与生活：" + "；".join(done)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="生成运营后台的本地演示数据")
    parser.add_argument("--reset", action="store_true", help="先删除演示目录再生成")
    args = parser.parse_args(argv)

    if DEMO_DIR.exists():
        if not args.reset:
            print(f"拒绝覆盖已有的演示目录：{DEMO_DIR}\n要重建请加 --reset。", file=sys.stderr)
            return 2
        shutil.rmtree(DEMO_DIR)
    DEMO_DIR.mkdir(parents=True, exist_ok=True)

    os.environ["PETJOURNEY_DB_PATH"] = str(DEMO_DIR / "petjourney.sqlite3")
    os.environ["PETJOURNEY_UPLOAD_DIR"] = str(DEMO_DIR / "uploads")
    os.environ["PETJOURNEY_WEB_PRIVATE_MEDIA_DIR"] = str(DEMO_DIR / "web-private-media")

    from app.config import Settings
    from app.main import create_app

    settings = Settings(
        database_path=DEMO_DIR / "petjourney.sqlite3",
        upload_dir=DEMO_DIR / "uploads",
        web_private_media_dir=DEMO_DIR / "web-private-media",
        public_base_url="http://127.0.0.1:18790",
        auth_secret="petsoul-admin-demo-secret-0123456789abcdef",
        apple_auth_mode="mock",
        scheduler_enabled=False,
        web_cookie_secure=False,
        web_demo_catalog=True,
        web_environment="dev",
    )
    app = create_app(settings)
    clock = ReplayClock(datetime(2026, 9, 21, 4, 0, tzinfo=timezone.utc)).install()
    web = app.state.web
    admin = app.state.admin
    illustrator = DemoIllustrator()
    web.illustrations.illustrator = illustrator

    # ---- 员工 ----
    staff_spec = [
        ("ops-owner", "平台负责人", ["platform_owner"]),
        ("support-mei", "客服 · 小美", ["support"]),
        ("sre-lin", "运维 · 阿林", ["sre"]),
        ("editor-yu", "内容编辑 · 小雨", ["content_editor"]),
        ("publisher-he", "内容发布 · 老何", ["content_publisher"]),
        ("moderator-zhou", "审核 · 小周", ["moderator"]),
        ("economy-tan", "经济运营 · 小谭", ["economy_ops"]),
        ("economy-lu", "经济负责人 · 老陆", ["economy_lead"]),  # 只审批，不提交（双人原则）

    ]
    staff_rows = []
    for username, display, roles in staff_spec:
        record = admin.identity.create_staff(username, STAFF_PASSWORD, display, roles, created_by="seed")
        staff_rows.append((username, display, ",".join(record.roles)))

    # ---- 玩家 ----
    # 待领养居民是启动时播种进去的；这里只读它们的编号，领养仍走玩家的正式接口。
    with app.state.storage.connect() as conn:
        candidates = [row["candidate_id"] for row in conn.execute(
            "SELECT candidate_id FROM web_adoption_candidates WHERE availability = 'available' ORDER BY candidate_id")]
    assert len(candidates) >= 3, f"演示需要至少 3 位待领养居民，实际只有 {len(candidates)}"

    players = []
    for index, username in enumerate(("demo-lin", "demo-zhao", "demo-chen")):
        player = Player(app, username)
        player.adopt(candidates[index])
        assert player.patch("/settings", {"generated_photos": True}).status_code == 200
        players.append(player)

    # 第四位：带着自己的宠物来，上传了一张参考照。
    # 素材库那条硬规则（参考照不能被收成公共素材）要有这张照片才验得了。
    uploader = Player(app, "demo-wen")
    created = uploader.client.post(
        f"{PREFIX}/pets", data={"name": "小满", "species": "cat"},
        files={"photo": ("xiaoman.png", _solid_png(24, 24, (210, 150, 120)), "image/png")},
        headers={"X-CSRF-Token": uploader.csrf, "Idempotency-Key": "seed-own-pet-0001"})
    assert created.status_code == 201, created.text
    uploader.pet_id = created.json()["pet_id"]
    players.append(uploader)

    # 三种照片结局：已出图 / 没画成（可恢复） / 结果未确认（不可恢复、不自动重发）
    cafe_trip(players[0], web, clock, illustrator, None)
    cafe_trip(players[1], web, clock, illustrator, "rejected")
    cafe_trip(players[2], web, clock, illustrator, "timeout")

    # ---- 一条公开动态与一条举报 ----
    with app.state.storage.connect() as conn:
        post = conn.execute("SELECT post_id FROM web_posts WHERE visibility = 'public' ORDER BY created_at DESC LIMIT 1").fetchone()
    report_note = "没有产生公开动态（演示线路本轮没有可公开的事件）"
    if post is not None:
        response = players[0].post("/reports", {"target_kind": "post", "target_id": post["post_id"], "reason": "内容看着不太合适"})
        report_note = f"已对动态 {post['post_id']} 提交一条举报（HTTP {response.status_code}）"

    # ---- 社交与生活里的几样东西（第八批：后台看得到关系与计数，看不到私密内容）----
    # 全部走玩家的正式接口：评论、点赞、关注、拉黑、报名驾校、填口味、打开集市（当天的居民订单在这时生成）。
    social_note = social_demo(players, clock)

    # ---- 一张公开素材（走真实上传流程，包括哈希比对与缩略图）----
    asset_note = "未生成"
    try:
        from app.web_admin.commands import ActorContext

        editor = next(record for record in admin.identity.list_staff() if record.username == "editor-yu")
        principal = admin.identity.resolve(admin.identity.issue_session(editor.staff_id).cookie_value)
        ctx = ActorContext(principal=principal, request_id="seed", operation_id="seed-asset-0001")
        result = admin.assets.upload(ctx, filename="harbour-banner.png", data=_demo_banner(),
                                     source="own_work", source_note="演示数据自带的运营自制横幅",
                                     license_note=None, usage_scope="public")
        asset_note = f"公开素材 {result['asset']['asset_id']}（{result['note']}）"
    except Exception as exc:  # noqa: BLE001 - 演示数据不因为素材没造出来就整体失败
        asset_note = f"素材未生成：{type(exc).__name__}"

    logins = DEMO_DIR / "admin-demo-logins.local.txt"
    lines = ["# PetSoul 运营后台演示账号（仅本地；不要用于任何部署）", "",
             f"# 生成时间（真实）：{datetime.now(timezone.utc).isoformat()}",
             f"# 演示世界时钟停在：{clock.now.isoformat()}", "",
             "## 员工（后台 http://127.0.0.1:5299）", f"共用口令：{STAFF_PASSWORD}", ""]
    lines += [f"{username}\t{display}\t{roles}" for username, display, roles in staff_rows]
    lines += ["", "## 玩家（玩家网页；后台用它们演示排查）", f"共用口令：{PLAYER_PASSWORD}", ""]
    lines += [f"{p.username}\t{p.user_id}\t{p.pet_id}" for p in players]
    lines += ["", f"## 备注", report_note,
              "三张照片分别是：已出图 / 没画成（可受控恢复） / 结果未确认（不自动重发）。",
              asset_note,
              social_note,
              "批量补偿默认关闭（额度未配置）。要演示闭环：PETSOUL_ADMIN_BATCH=on node PetSoulAdmin/scripts/dev-backend.mjs，"
              "由 economy-tan 提交、economy-lu 审批、economy-tan 执行。",
              "供应商全程关闭，生图走替身，没有任何真实付费调用。"]
    logins.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"演示库已生成：{DEMO_DIR}")
    print(f"账号与口令写在：{logins}（git 忽略，请勿提交）")
    print("启动后端（仓库根目录）：")
    print('  PETJOURNEY_DB_PATH=PetJourneyBackend/data/web-admin-demo/petjourney.sqlite3 \\')
    print("  ... 详见 docs/coordination/PETSOUL-ADMIN-HANDOFF.md 的启动命令")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
