"""网页测试共用基类与多账号辅助（非测试模块，不以 test_ 开头）。"""

from __future__ import annotations

import json
import struct
import sys
import tempfile
import unittest
import uuid
import zlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.web_journey import FAST, SLOW

DNA = {
    "owner_title": "妈妈",
    "personality": "测试用性格",
    "favorite_places": ["阳台"],
    "hobby": ["晒太阳"],
    "catchphrase": "测试口头禅",
    "emoji_pref": "soft",
    "voice_style": "测试语气",
}
PREFIX = "/api/v1/web"


def tiny_png(with_text_chunk: bool = True) -> bytes:
    """1x1 PNG；可选带 tEXt 元数据块（用于验证上传时被剥离）。"""
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    body = chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    if with_text_chunk:
        body += chunk(b"tEXt", b"GPS" + bytes([0]) + b"22.28,114.15")
    body += chunk(b"IDAT", zlib.compress(bytes([0, 255, 0, 0]))) + chunk(b"IEND", b"")
    return bytes([0x89]) + b"PNG" + bytes([13, 10, 26, 10]) + body


class FakeClock:
    """可推进的服务器时钟：替换 app.* 模块里对 utils.utcnow 的引用（不改生产代码）。"""

    def __init__(self, start: datetime) -> None:
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs) -> datetime:
        self.now = self.now + timedelta(**kwargs)
        return self.now

    def install(self, case: unittest.TestCase) -> "FakeClock":
        import app.utils as utils

        original = utils.utcnow
        patched = [mod for name, mod in list(sys.modules.items())
                   if (name == "app" or name.startswith("app.")) and getattr(mod, "utcnow", None) is original]
        for mod in patched:
            setattr(mod, "utcnow", self)
        case.addCleanup(lambda: [setattr(mod, "utcnow", original) for mod in patched])
        return self


LUNCH_UTC = datetime(2026, 9, 22, 4, 0, tzinfo=timezone.utc)  # 香港 12:00，示例店营业中


class WebUser:
    """一个独立浏览器会话（独立 cookie），写操作自动带 CSRF 与幂等键。"""

    # 读接口是纯读的（不推进世界）。设成 True 时，每次 GET 前先跑一轮后台，等价于“任务进程一直跟得上”，
    # 让那些“时间过去以后读页面就该看到结果”的老用例继续成立；验证 GET 纯读的用例保持 False。
    settle_on_read = False

    def __init__(self, app, username: str, password: str = "longpassword1") -> None:
        self.app = app
        self.client = TestClient(app)
        response = self.client.post(f"{PREFIX}/auth/register", json={"username": username, "password": password})
        assert response.status_code == 201, response.text
        self.user_id = response.json()["user"]["user_id"]
        self.pet_id: str | None = None
        self.home_id: str | None = None

    @property
    def csrf(self) -> str:
        return self.client.cookies.get("petsoul_csrf") or ""

    def get(self, path: str, **kwargs):
        if self.settle_on_read:
            settle_world(self.app)
        return self.client.get(f"{PREFIX}{path}", **kwargs)

    def post(self, path: str, body=None, key: str | None = None, **kwargs):
        headers = {"X-CSRF-Token": self.csrf, "Idempotency-Key": key or f"t-{uuid.uuid4().hex[:16]}", **kwargs.pop("headers", {})}
        return self.client.post(f"{PREFIX}{path}", json=body, headers=headers, **kwargs)

    def put(self, path: str, body=None, key: str | None = None):
        return self.client.put(f"{PREFIX}{path}", json=body, headers={"X-CSRF-Token": self.csrf, "Idempotency-Key": key or f"t-{uuid.uuid4().hex[:16]}"})

    def patch(self, path: str, body=None):
        return self.client.patch(f"{PREFIX}{path}", json=body, headers={"X-CSRF-Token": self.csrf})

    def upload_pet(self, name: str, species: str = "cat", photo: bytes | None = None, key: str | None = None, household_id: str | None = None):
        """household_id：已经建过家的账号再加一只宠物时要带上（否则 409 household_exists）。"""
        files = {"photo": ("pet.png", photo, "image/png")} if photo is not None else None
        data = {"name": name, "species": species, **({"household_id": household_id} if household_id else {})}
        return self.client.post(f"{PREFIX}/pets", data=data, files=files,
                                headers={"X-CSRF-Token": self.csrf, "Idempotency-Key": key or f"t-{uuid.uuid4().hex[:16]}"})

    def delete(self, path: str):
        return self.client.delete(f"{PREFIX}{path}", headers={"X-CSRF-Token": self.csrf})

    def adopt_and_move_in(self, candidate_id: str, public_posts: bool = True) -> None:
        response = self.post("/adoption/adopt", {"candidate_id": candidate_id})
        assert response.status_code == 200, response.text
        self.pet_id = response.json()["pet_id"]
        self.move_in(public_posts)

    def move_in(self, public_posts: bool = True) -> dict:
        response = self.post("/onboarding/move-in", {"public_posts": public_posts})
        assert response.status_code == 200, response.text
        state = response.json()
        self.home_id = state["home_id"]
        self.pet_id = state["pet_id"]
        return state

    def home(self) -> dict:
        response = self.get("/home")
        assert response.status_code == 200, response.text
        return response.json()


def settle_world(app, now: datetime | None = None) -> None:
    """任务进程每轮对旅程与消息做的事（不含租约、不含慢通道）：结算到期事件、投递 fast 下游、兑现到点的排队回复。

    now 为空时交给各服务自己的时间入口（测试里被 FakeClock 替换过），不要在这里取宿主机时间。
    """
    web = app.state.web
    web.journeys.advance_all(now)
    web.journeys.deliver_outbox(now, lanes=(FAST,))
    web.communicator.deliver_due(now)


class WebPlatformTestBase(unittest.TestCase):
    policy = "open"
    # True：每次 GET 前先跑一轮后台（模拟任务进程一直跟得上）。默认 False：读接口纯读，读到的就是已经结算过的事实。
    settle_on_read = False
    # 这些测试验证的是旅程机制本身，跑在“演示环境”（演示线路开着）；真实交通与去演示化见 test_web_real_transport.py
    demo_catalog = True

    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        root = Path(self.tempdir.name)
        self.settings = Settings(
            database_path=root / "web.sqlite3",
            upload_dir=root / "uploads",
            web_private_media_dir=root / "private",
            public_base_url="http://testserver",
            auth_secret="web-test-secret-0123456789abcdef-0123",
            apple_auth_mode="mock",
            scheduler_enabled=False,
            legacy_api_policy=self.policy,
            economy_admin_token="admin-test-token",
            web_cookie_secure=False,
            web_demo_catalog=self.demo_catalog,
        )
        self.app = create_app(self.settings)
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        self.client.close()
        self.tempdir.cleanup()

    @property
    def web(self):
        return self.app.state.web

    def run_background(self, now: datetime | None = None) -> None:
        """任务进程每轮会做的旅程部分（不拿租约）：结算到期事件，投递 fast 与 slow 两个通道的 outbox。
        测试里显式调用它，代替后台线程；可能调模型的下游（攻略、朋友相遇）只在这里投递。"""
        now = now or (self.clock.now if getattr(self, "clock", None) is not None else datetime.now(timezone.utc))
        self.web.journeys.advance_all(now)
        self.web.journeys.deliver_outbox(now, lanes=(FAST, SLOW))

    def tick_all(self, now: datetime | None = None) -> None:
        """两条后台线各跑一轮：世界线（结算、确定性下游、出门前复核、规则生活、驾校）与认知线（攻略/相遇的表达、到点回复、主动消息）。"""
        now = now or (self.clock.now if getattr(self, "clock", None) is not None else datetime.now(timezone.utc))
        self.web.ticker.tick(now)
        self.web.cognition.tick(now)

    def user(self, name: str) -> WebUser:
        user = WebUser(self.app, name)
        user.settle_on_read = self.settle_on_read
        return user

    def sign_in(self, sub: str) -> tuple[str, str]:
        response = self.client.post("/api/v1/auth/apple", json={"identity_token": f"mock-apple-sub:{sub}"})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        return body["access_token"], body["user_id"]

    def create_owned_pet(self, token: str, name: str = "测试伙伴") -> str:
        response = self.client.post(
            "/api/v1/create_pet",
            data={"pet_name": name, "pet_type": "cat", "dna": json.dumps(DNA, ensure_ascii=False)},
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(response.status_code, 200)
        pet_id = response.json()["pet_id"]
        claim = self.client.post("/api/v1/me/claim_pet", json={"pet_id": pet_id}, headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(claim.status_code, 200)
        return pet_id

    def assert_envelope(self, response, status: int, code: str) -> dict:
        self.assertEqual(response.status_code, status, response.text)
        body = response.json()
        self.assertEqual(body["error"]["code"], code)
        self.assertTrue(body["error"]["request_id"])
        self.assertEqual(response.headers.get("X-Request-ID"), body["error"]["request_id"])
        self.assertNotIn("Traceback", response.text)
        return body
