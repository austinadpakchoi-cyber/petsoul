"""旅行心愿用例共用的替身与装置。非测试模块。**假的**研究端口：不联网、0 次付费调用。

`FakeResearchPort` 按**真实发送边界**计数：每一次 `research()` 调用记一笔（Q 的判据：看调用次数，不只看 attempts）。
"""

from __future__ import annotations

import hashlib
import shutil
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from character_fakes import rgb_png
from task_budget_helpers import open_storage

from app.image_provider.models import GeneratedImage
from app.utils import iso, utcnow
from app.web_journey.illustrations import IllustrationService
from app.web_photo_director.journal_brief import JournalIdentity
from app.web_platform.budget import BudgetLedger
from app.web_platform.tasks import WebTaskQueue
from app.web_travel.journal import TravelJournalService
from app.web_travel.ports import DraftStop, ResearchDraft, ResearchFact, ResearchResult, ResearchSource
from app.web_travel.research import TravelResearchService
from app.web_travel.service import RESEARCH_KIND, TravelWishService

SEA = {"destination_key": "hk-repulse-bay", "name": "浅水湾", "city": "香港"}
PRIVATE_REASON = "主人说过下次替我看看海-合成标记-7Q3Z"  # 给主人的理由里带一个合成标记：研究请求里一个字都不许出现（T11）


def good_result(**overrides) -> ResearchResult:
    """一份正常的研究结果：检索真的执行过；主目的地身份与路线由地图核验；当天天气是一小时前的观测；顺路建议有特色事实支撑。"""
    now = utcnow()
    sources = (ResearchSource("s-map", url=None, publisher="高德地图", retrieved_at=iso(now)),
               ResearchSource("s-weather", url=None, publisher="香港天文台", retrieved_at=iso(now)),
               ResearchSource("s-web", url="https://example.org/stanley", publisher="赤柱官网", retrieved_at=iso(now),
                              published_at=iso(now - timedelta(days=20))))
    facts = (ResearchFact("identity", "destination_identity", "浅水湾", {"lat": 22.2367, "lng": 114.1955}, ("s-map",), verification="map"),
             ResearchFact("route", "route", "浅水湾", "中环乘 6 路巴士", ("s-map",), verification="map"),
             ResearchFact("weather", "weather", "浅水湾", {"suitable": True, "summary": "多云"}, ("s-weather",),
                          observed_at=iso(now - timedelta(hours=1)), verification="weather_api"),
             ResearchFact("stanley", "feature", "赤柱", "海边小镇，适合散步", ("s-web",), verification="search"))
    draft = ResearchDraft(title="去看海", summary="我想去海边听一会儿浪。",
                          stops=(DraftStop("浅水湾", "main", "听浪", "带一瓶水", ("identity", "route")),
                                 DraftStop("赤柱", "suggested", "顺路散步", "", ("stanley",))),
                          owner_tips=("坐 6 路巴士去", "记得带水"), tip_fact_keys=(("route",), ()), rain_alternative="下雨就改天去")
    fields = {"requested_model": "deepseek-flash", "effective_model": "deepseek-flash", "provider_request_id": "req-1",
              "usage": {"input_tokens": 1200, "output_tokens": 300}, "search_uses": 1, "tool_executions": 1,
              "tool_execution_ids": ("srvtool-1",), "sources": sources, "facts": facts, "draft": draft}
    fields.update(overrides)
    return ResearchResult(**fields)


class FakeResearchPort:
    def __init__(self, result: ResearchResult | None = None, *, raises: BaseException | None = None) -> None:
        self.calls: list = []
        self.result = result or good_result()
        self.raises = raises
        self.on_call = None  # 调用发生时的钩子（模拟"发出以后进程被杀"等）

    def research(self, request):
        self.calls.append(request)
        if self.on_call is not None:
            self.on_call(request)
        if self.raises is not None:
            raise self.raises
        return self.result


class TravelResearchTestBase(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.storage = open_storage(str(Path(tmp.name) / "travel.sqlite3"))
        self.tasks = WebTaskQueue(self.storage)
        self.ledger = BudgetLedger(self.storage)
        self.wishes = TravelWishService(self.storage, self.tasks)
        self.research = TravelResearchService(self.storage, self.tasks, self.wishes, ledger=self.ledger)
        self.port = FakeResearchPort()
        self.research.port = self.port

    def propose(self, trigger: str = "evt-1", **overrides):
        kwargs = {"pet_id": "pet-1", "user_id": "user-1", "trigger_event_id": trigger, "candidates": [SEA], "selected": 0,
                  "interest_tags": ["sea"], "owner_reason": PRIVATE_REASON, "funds_goal": 120}
        kwargs.update(overrides)
        return self.wishes.propose(**kwargs)

    def query(self, sql: str, params: tuple = ()):
        with self.storage.connect() as conn:
            return conn.execute(sql, params).fetchall()

    def receipts(self):
        return self.query("SELECT * FROM web_travel_research_receipts ORDER BY attempt_no, rowid")

    def plans(self):
        return self.query("SELECT * FROM web_travel_plans ORDER BY plan_revision")

    def task(self):
        return self.query("SELECT * FROM web_tasks WHERE kind = ?", (RESEARCH_KIND,))[0]

    def reservations(self):
        return self.query("SELECT * FROM web_budget_reservations WHERE purpose = 'travel_research' ORDER BY rowid")


class FakePainter:
    """**假的**画师：记下每一次真的发出的调用。"""

    available = True

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.raises: BaseException | None = None

    def render(self, prompt, reference=None, size="2048x2048", background=None):
        self.calls.append({"prompt": prompt, "reference": reference, "size": size, "background": background})
        if self.raises is not None:
            raise self.raises
        return GeneratedImage(image_bytes=rgb_png(16, 24), mime_type="image/png", model="fake-painter", provider="fake", source="b64_json")


class TravelJournalTestBase(TravelResearchTestBase):
    def setUp(self) -> None:
        super().setUp()
        media = Path(tempfile.mkdtemp(prefix="journal-media-"))
        self.addCleanup(shutil.rmtree, media, True)
        self.ills = IllustrationService(self.storage, media, self.tasks)
        self.painter = FakePainter()
        self.ills.illustrator = self.painter
        self.ills.character_of = lambda pet_id: ("cat", "小银", None)
        self.photo = rgb_png(64, 64)
        self.ills.reference_photo_of = lambda pet_id: (self.photo, "image/png") if self.photo else None
        self.ills.reference_origin_of = lambda pet_id: "owner_original"
        self.portraits: list[str] = []
        self.ills.portrait_saver = lambda pet_id, data, mime: self.portraits.append(pet_id) or True
        self.ills.reserve = lambda op, pet_id, units: self.ledger.reserve(op, provider="image", purpose="illustration",
                                                                          subject_scope=f"pet:{pet_id}", units=units)
        self.ills.settle = lambda permit, outcome, actual_units=None: self.ledger.settle(permit, outcome, actual_units=actual_units)
        self.journals = TravelJournalService(self.storage, self.ills)
        compiled_photo = self.photo
        self.journals.identity_of = lambda conn, pet_id: JournalIdentity("cat", 1, hashlib.sha256(compiled_photo).hexdigest(), "owner_original")
        self.research.journals = self.journals
        self.journals.complete_wish_in = self.wishes.complete_in  # 与 install_travel 同一根线（那边另有用例钉装配）

    def publish(self) -> None:
        self.propose()
        self.research.run_pending()

    def journal_rows(self):
        return self.query("SELECT * FROM web_travel_journals ORDER BY journal_revision")

    def drawings(self):
        return self.query("SELECT * FROM web_tasks WHERE kind = 'illustration' ORDER BY created_at")

    def image_units(self) -> list[int]:
        return [r["reserved_units"] for r in self.query("SELECT reserved_units FROM web_budget_reservations WHERE purpose = 'illustration' ORDER BY rowid")]

    def image(self, journal=None):
        journal = journal or self.journal_rows()[-1]
        with self.storage.connect() as conn:
            return self.journals.image_in(conn, journal["image_task_id"])
