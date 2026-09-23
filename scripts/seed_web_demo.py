#!/usr/bin/env python3
"""本地演示数据（仅开发/联调）：在独立的演示库里造一个“演示账号”，把前端待接页面需要的状态都走一遍。

- 只写 ``PetJourneyBackend/data/web-demo/``（git 忽略）；不碰开发库、正式库或其他窗口正在用的数据库；
- 全程关闭真实供应商：不调用对话模型、地图、生图（攻略走模板、明信片没有自拍图），不产生任何付费调用；
- 账号名以 ``demo-`` 开头，宠物来自虚构的领养伙伴；口令随机生成，只写在演示目录里的 ``demo-login.local.txt``（git 忽略），
  不打印到终端、不写进仓库或文档；
- 用“回放时钟”把两天的生活压缩成几秒：所有事件都发生在过去；之后用开发后端打开，世界按真实时间继续往前走。

覆盖：入住（海边的家）→ DNA → 身份卡与银行卡 → 打工发薪 → 报名爪爪驾校 → 科目一练习 → 科目一首次考试没过 → 补考通过 →
科目二练习 → 科目二首次考试没过（侧方停车超时）→ 补考通过 → 科目三 → 科目四通过、签发驾照与借车券 → 领证仪式 →
第一次自驾（借车券抵租车费）→ 第二天打工、进城逛逛（攻略、明信片）→ 附近走走/喝一杯（可能认识星球居民）。
科二、科三由测试驾驶员（PetJourneyBackend/tests/driving_bots.py）按场地实际驾驶，操作记录照常上传、由服务端复算。

用法（仓库根目录）：
    python scripts/seed_web_demo.py                       # 生成演示库（已存在时拒绝覆盖）
    python scripts/seed_web_demo.py --reset               # 删除旧的演示库后重新生成（只删 data/web-demo）
    python scripts/seed_web_demo.py --examples out.json   # 另外导出每一步的真实请求/响应（写到你指定的本地文件）
    # 然后用演示库启动一个 mock 开发后端（不读任何密钥），前端指向它：
    PETSOUL_DEV_DATA_DIR=../PetJourneyBackend/data/web-demo PETSOUL_DEV_BACKEND_PORT=18762 node PetJourneyWeb/scripts/dev-backend.mjs
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "PetJourneyBackend"
DEMO_DIR = BACKEND_DIR / "data" / "web-demo"
PREFIX = "/api/v1/web"
LOCAL = timezone(timedelta(hours=8))
DEMO_DNA = {
    "owner_title": "姐姐",
    "nicknames": ["岚岚"],
    "personality": "不爱熬夜，不爱热闹，喜欢安静。",
    "voice_style": "慢吞吞的，说话前先眨眨眼",
    "habits": ["每天早上用头蹭一蹭姐姐的手", "偶尔半夜跑到窗台上看月亮"],
    "hobbies": ["看书", "晒太阳"],
    "favorite_places": ["海边"],
    "favorite_foods": ["冻干小鱼"],
    "fears": ["打雷"],
}
PROVIDER_ENV = ("OPENAI_API_KEY", "AMAP_API_KEY", "GOOGLE_MAPS_API_KEY", "DOUBAO_API_KEY", "PETJOURNEY_IMAGE_API_KEY", "IMAGE_API_KEY", "OPENAI_IMAGE_API_KEY",
                "PETJOURNEY_WEB_PROVIDERS")


class ReplayClock:
    """把 app.* 模块里的 utcnow 换成可推进的时钟（与测试用的 FakeClock 同一做法）。"""

    def __init__(self, start: datetime) -> None:
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **delta) -> None:
        self.now += timedelta(**delta)

    def install(self) -> None:
        import app.utils as utils

        original = utils.utcnow
        for name, module in list(sys.modules.items()):
            if (name == "app" or name.startswith("app.")) and getattr(module, "utcnow", None) is original:
                setattr(module, "utcnow", self)


class DemoOwner:
    def __init__(self, app, examples: list | None) -> None:
        from fastapi.testclient import TestClient

        self.client = TestClient(app)
        self.examples = examples

    def call(self, method: str, path: str, body=None, *, expect: int | None = None, label: str | None = None):
        headers = {}
        if method != "GET":
            headers = {"X-CSRF-Token": self.client.cookies.get("petsoul_csrf") or "", "Idempotency-Key": f"demo-{uuid.uuid4().hex[:16]}"}
        response = self.client.request(method, PREFIX + path, json=body, headers=headers)
        if expect is None and response.status_code >= 400:
            raise RuntimeError(f"{method} {path} → {response.status_code} {response.text[:300]}")
        if expect is not None and response.status_code != expect:
            raise RuntimeError(f"{method} {path} 期望 {expect}，实际 {response.status_code} {response.text[:300]}")
        data = response.json() if response.content else None
        if self.examples is not None and label:
            self.examples.append({"label": label, "method": method, "path": PREFIX + path, "request": body, "status": response.status_code, "response": data})
        return data

    def examples_has(self, label: str) -> bool:
        return any(e["label"] == label for e in self.examples or [])


def build_app(data_dir: Path):
    for key in PROVIDER_ENV:  # 即使本机环境里有真实密钥，也不让演示脚本读到
        os.environ.pop(key, None)
    sys.path.insert(0, str(BACKEND_DIR))
    sys.path.insert(0, str(BACKEND_DIR / "tests"))  # 测试驾驶员与作答辅助（只用于本地演示数据）
    os.chdir(BACKEND_DIR)
    from app.config import Settings
    from app.main import create_app

    settings = Settings(database_path=data_dir / "petjourney.sqlite3", upload_dir=data_dir / "uploads", web_private_media_dir=data_dir / "web-private-media",
                        public_base_url="http://127.0.0.1:18762", auth_secret=secrets.token_hex(32), apple_auth_mode="mock", scheduler_enabled=False,
                        web_providers_enabled=False, web_world_tick_seconds=0, web_cookie_secure=False)
    return create_app(settings)


def settle(owner: DemoOwner, clock: ReplayClock, **delta) -> None:
    clock.advance(**delta)
    owner.call("GET", "/journey/map")


def quiz(owner: DemoOwner, clock: ReplayClock, subject: str, mode: str, wrong: int, label: str) -> dict:
    """科一、科四：建局 → 开始 → 逐题作答（故意答错 wrong 题）→ 交卷。"""
    from app.web_driving.questions import ALL, correct_answer
    from school_helpers import wrong_answer

    session = owner.call("POST", "/driving/sessions", {"subject": subject, "mode": mode}, label=f"{label}：建立考局")
    session = owner.call("POST", f"/driving/sessions/{session['session_id']}/begin", label=f"{label}：开始")
    for index, question in enumerate(session["quiz"]["questions"]):
        qid = question["question_id"]
        answer = wrong_answer(qid) if index < wrong else correct_answer(ALL[qid])
        owner.call("PUT", f"/driving/sessions/{session['session_id']}/answers", {"question_id": qid, "answer": answer}, label=f"{label}：作答" if index == 0 else None)
        clock.advance(seconds=20)
    return owner.call("POST", f"/driving/sessions/{session['session_id']}/submit", label=f"{label}：交卷")


def drive(owner: DemoOwner, clock: ReplayClock, subject: str, mode: str, label: str, bots=None, item: str | None = None) -> dict:
    """科二、科三：建局 → 开始 → 测试驾驶员按场地实际驾驶，每秒上传一段操作，服务端复算。"""
    from driving_bots import Driver
    from school_helpers import bots_for

    body = {"subject": subject, "mode": mode, **({"item": item} if item else {})}
    session = owner.call("POST", "/driving/sessions", body, label=f"{label}：建立考局")
    session = owner.call("POST", f"/driving/sessions/{session['session_id']}/begin", label=f"{label}：开始")
    items = session["drive"]["items"]
    bots = bots or bots_for(subject, items[0]["course"]["variant"])
    for index, spec in enumerate(items):
        driver = Driver(spec["course"]).run(bots[index])
        tick, last = 0, None
        while tick < driver.tick:
            upto = min(driver.tick, tick + 30)
            chunk = {"item_index": index, "from_tick": tick, "upto_tick": upto, "events": [e for e in driver.events if tick <= e["t"] < upto]}
            last = owner.call("POST", f"/driving/sessions/{session['session_id']}/inputs", chunk, label=f"{label}：上传操作" if index == 0 and tick == 60 else None)
            tick = upto
        clock.advance(seconds=driver.tick // 30 + 20)
        if last["session_state"] == "settled":
            break
    return owner.call("GET", f"/driving/sessions/{session['session_id']}", label=f"{label}：结果")


def story(owner: DemoOwner, clock: ReplayClock, username: str, password: str) -> dict:
    owner.call("POST", "/auth/register", {"username": username, "password": password})
    owner.call("POST", "/adoption/adopt", {"candidate_id": "adopt-lan"}, label="领养")
    state = owner.call("POST", "/onboarding/move-in", {"public_posts": True, "habitat": "seaside"}, label="入住（海边的家）")
    pet_id = state["pet_id"]
    owner.call("GET", "/home/place", label="家在哪")
    owner.call("PUT", f"/pets/{pet_id}/dna", DEMO_DNA, label="保存 DNA")
    owner.call("GET", "/credentials", label="证件卡包（入住后）")

    owner.call("POST", "/journey/depart", {"destination_key": "work:fishing_port"}, label="去打工")
    owner.call("GET", "/jobs", label="打工记录（在路上）")
    settle(owner, clock, hours=4)

    owner.call("GET", "/driving/curriculum", label="驾校课程")
    owner.call("POST", "/driving/enroll", label="陪 TA 报名驾校")
    owner.call("POST", "/journey/depart", {"destination_key": "local:drive_trip"}, expect=403, label="没有驾照不能自驾")
    clock.advance(minutes=10)
    quiz(owner, clock, "s1", "practice", 2, "科目一练习")
    quiz(owner, clock, "s1", "formal", 2, "科目一首次考试（没过）")
    owner.call("GET", "/driving", label="驾校总览（科目一还剩一次补考）")
    clock.advance(minutes=30)
    quiz(owner, clock, "s1", "formal", 0, "科目一补考（通过）")
    clock.advance(minutes=30)
    drive(owner, clock, "s2", "practice", "科目二练习（倒车入库）", item="reverse_park")
    from driving_bots import curve_bot, reverse_park_bot, side_park_bot

    drive(owner, clock, "s2", "formal", "科目二首次考试（没过）", bots=[reverse_park_bot(2.8, 2.0, 1), side_park_bot(5.6, 0.62, 1), curve_bot(1)])
    clock.advance(minutes=30)
    drive(owner, clock, "s2", "formal", "科目二补考（通过）")
    clock.advance(minutes=30)
    drive(owner, clock, "s3", "formal", "科目三（通过）")
    clock.advance(minutes=30)
    quiz(owner, clock, "s4", "formal", 1, "科目四（通过，签发驾驶证）")
    owner.call("GET", "/driving", label="驾校总览（已拿证）")
    owner.call("POST", "/driving/ceremony", label="领证仪式")
    owner.call("GET", "/driving/history", label="练习与考试历史")
    cards = {c["kind"]: c for c in owner.call("GET", "/credentials") if c["credential_id"]}
    owner.call("GET", f"/credentials/{cards['bank_card']['credential_id']}", label="银行卡详情")
    owner.call("GET", f"/credentials/{cards['driver_license']['credential_id']}", label="驾驶证详情")
    owner.call("GET", "/journey/destinations", label="出发站（有驾照后含自驾）")

    clock.advance(minutes=30)
    owner.call("POST", "/journey/depart", {"destination_key": "local:drive_trip"}, label="自己开车去兜风（用借车券）")
    settle(owner, clock, hours=3)

    clock.now = clock.now.astimezone(LOCAL).replace(hour=9, minute=0).astimezone(timezone.utc) + timedelta(days=1)
    owner.call("GET", "/journey/map")
    owner.call("POST", "/journey/depart", {"destination_key": "work:fishing_port"})
    settle(owner, clock, hours=4)
    owner.call("POST", "/journey/depart", {"destination_key": "local:city_trip"}, label="进城逛逛（攻略、明信片）")
    settle(owner, clock, hours=4)
    for key in ("local:cafe", "local:stroll", "local:cafe", "local:stroll"):
        if owner.call("GET", "/friends"):
            break
        owner.call("POST", "/journey/depart", {"destination_key": key})
        settle(owner, clock, hours=2)
    return {"pet_id": pet_id}


def main() -> int:
    parser = argparse.ArgumentParser(description="生成本地演示库（只写 PetJourneyBackend/data/web-demo）")
    parser.add_argument("--reset", action="store_true", help="删除已有的演示库后重新生成")
    parser.add_argument("--examples", type=Path, help="把每一步的真实请求/响应导出到这个本地 JSON 文件")
    args = parser.parse_args()
    if DEMO_DIR.exists():
        if not args.reset:
            print(f"演示库已存在：{DEMO_DIR}（要重新生成请加 --reset）")
            return 1
        shutil.rmtree(DEMO_DIR)
    DEMO_DIR.mkdir(parents=True)
    now = datetime.now(timezone.utc)
    start = (now.astimezone(LOCAL) - timedelta(days=2)).replace(hour=9, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
    app = build_app(DEMO_DIR)
    clock = ReplayClock(start)
    clock.install()
    examples: list | None = [] if args.examples else None
    owner = DemoOwner(app, examples)
    username, password = f"demo-{secrets.token_hex(3)}", secrets.token_urlsafe(12)
    owner.pet_id = story(owner, clock, username, password)["pet_id"]
    clock.now = now - timedelta(minutes=5)
    counts = {path: len(owner.call("GET", path, label=f"读取 {path}")) for path in ("/credentials", "/jobs", "/timeline", "/guides", "/collection", "/friends")}
    owner.call("GET", "/driving", label="读取 /driving")
    owner.call("GET", f"/pets/{owner.pet_id}/dna", label="读取 DNA")
    owner.call("GET", f"/communicator/{owner.pet_id}/messages", label="星球通讯器消息")
    if args.examples:
        args.examples.write_text(json.dumps(examples, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    login = DEMO_DIR / "demo-login.local.txt"
    login.write_text(f"演示账号（仅本地演示库，非真实数据）\nusername={username}\npassword={password}\n", encoding="utf-8")
    print(f"演示库已生成：{DEMO_DIR}")
    print(f"演示账号：{username}（口令在 {login.name}，不打印）")
    print("各页面条目数：" + "，".join(f"{k} {v}" for k, v in counts.items()))
    print("启动：PETSOUL_DEV_DATA_DIR=../PetJourneyBackend/data/web-demo PETSOUL_DEV_BACKEND_PORT=18762 node PetJourneyWeb/scripts/dev-backend.mjs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
