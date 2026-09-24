"""统一世界状态 GET /world/state（CR-6C2B-MAP W1）。

按需求单的验收逐条钉：四种事实各一例、`phase` 与旅程时间线一致、在家与**从没出过门**都有
`home.center`、**请求前后世界表无写入**。

两条我额外钉的，因为它们是这份契约真正承重的地方：
  · **计划 ≠ 正在做**——去打工的路上 `kind=job` 但 `phase=going`，**工资未结**；
  · **每个坐标都要说明来路**——`position.basis` 必须是四个枚举之一，没有无出处的点。
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta

from app.schemas import EconomyTransactionType
from web_base import LUNCH_UTC, FakeClock, WebPlatformTestBase

# 读接口纯读：不靠后台跑一轮来"凑"状态，读到什么就是什么。
WORLD_TABLES = ("web_journeys", "web_visits", "web_journey_legs", "web_outbox", "web_tasks")


class WorldStateTestBase(WebPlatformTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.clock = FakeClock(LUNCH_UTC).install(self)
        self.owner = self.user("world-owner")
        self.owner.adopt_and_move_in("adopt-lan")

    def state(self) -> dict:
        response = self.owner.get("/world/state")
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def me(self) -> dict:
        pets = self.state()["pets"]
        return next(p for p in pets if p["pet_id"] == self.owner.pet_id)

    def activity(self) -> dict:
        return self.me()["activity"]

    def counts(self) -> dict[str, int]:
        """世界表的行数快照。纯读验证用——**比"没报错"硬**。"""
        with self.app.state.storage.connect() as conn:
            out = {}
            for table in WORLD_TABLES:
                try:
                    out[table] = conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]
                except Exception:
                    out[table] = -1  # 表不存在就记 -1，不静默跳过
            return out

    def depart(self, destination_key: str) -> None:
        response = self.owner.post("/journey/depart", {"destination_key": destination_key})
        self.assertEqual(response.status_code, 200, response.text)

    def advance_past(self, iso_ts: str, *, minutes: int = 1) -> None:
        """把时钟推到 `iso_ts` 之后 N 分钟。

        **不硬编码行程时长**——那会让这些用例依赖 `local.py` 里的配置：改一次店的距离，
        断言就会红在一个和它无关的地方。这里用的是接口自己给出的阶段时刻，
        所以顺带也验证了 `until` 确实是**这一阶段**的结束。
        """
        target = datetime.fromisoformat(iso_ts.replace("Z", "+00:00")) + timedelta(minutes=minutes)
        seconds = (target - self.clock.now).total_seconds()
        self.assertGreater(seconds, 0, f"{iso_ts} 已经过去了，这一步推进没有意义")
        self.clock.advance(seconds=seconds)


class HomeAndPurityTests(WorldStateTestBase):
    def test_a_pet_that_never_left_home_still_has_a_home_center(self) -> None:
        """**从没出过门也要有家的位置**：家在入住时就落进片区了，不依赖任何旅程记录。"""
        me = self.me()
        self.assertEqual(me["activity"]["phase"], "home")
        self.assertEqual(me["activity"]["kind"], "home")
        home = me["home"]
        self.assertIsNotNone(home, "从没出过门不是「不知道家在哪」")
        self.assertTrue(home["center"]["lat"] and home["center"]["lng"])
        self.assertGreaterEqual(home["precision_m"], 300, "模糊半径要如实反映，不许写小")
        self.assertTrue(home["label"])

    def test_position_at_home_is_the_home_area_and_says_so(self) -> None:
        position = self.me()["position"]
        self.assertIsNotNone(position)
        self.assertEqual(position["basis"], "home_area", "坐标必须说明来路")
        self.assertEqual(position["precision_m"], self.me()["home"]["precision_m"],
                         "在家时的精度就是家的模糊半径，不许报得更准")

    def test_reading_the_world_writes_nothing(self) -> None:
        """**纯读**：读接口不推进世界、不补齐到期事件。

        做法是比对世界表的**行数快照**，而不是「没有抛异常」——后者什么都证明不了。
        先出一趟门把时间推过到店时刻，制造「有到期事件待结算」的局面，这时读才有意义：
        如果读接口会补齐事件，行数就会变。
        """
        self.depart("harbour_cafe")
        self.clock.advance(minutes=45)
        before = self.counts()
        for _ in range(3):
            self.state()
        self.assertEqual(self.counts(), before, "读三次世界状态，世界表一行都不该变")

    def test_it_needs_a_session(self) -> None:
        stranger = self.user("world-stranger")
        self.assertIn(stranger.client.get("/api/v1/web/world/state").status_code, (401, 403, 409))


class ActivityPhaseTests(WorldStateTestBase):
    def test_a_cafe_trip_moves_through_going_there_and_returning(self) -> None:
        """四种事实之一：喝一杯。**phase 由时间线推**，三个阶段各断言一次。"""
        self.depart("harbour_cafe")
        going = self.activity()
        self.assertEqual(going["phase"], "going", "刚出发是在路上，不是已经到了")
        self.assertEqual(going["kind"], "cafe")
        self.assertIsNotNone(going["journey_id"])
        self.assertTrue(going["until"], "在路上要能回答「还要多久到」")

        self.advance_past(going["until"])  # going 这一阶段的结束＝到店
        there = self.activity()
        self.assertEqual(there["phase"], "there")
        self.assertIsNotNone(there["visit_id"], "到了才有 visit")
        self.assertIsNotNone(there["place"], "到了就该说在哪")
        self.assertTrue(there["since"] and there["until"], "这一阶段的起止都要给")

        self.advance_past(there["until"])  # 离店
        returning = self.activity()
        self.assertEqual(returning["phase"], "returning")

        self.advance_past(returning["until"])  # 到家
        self.assertEqual(self.activity()["phase"], "home", "回到家就是 home")

    def test_a_stroll_is_a_stroll_not_a_trip(self) -> None:
        self.depart("local:stroll")
        self.assertEqual(self.activity()["kind"], "stroll")

    def test_a_job_is_kind_job_and_is_not_paid_while_still_on_the_way(self) -> None:
        """**计划 ≠ 正在做**：去打工的路上 `kind=job` 但 `phase=going`，而且**工资还没结**。"""
        self.depart("work:cafe_helper")
        going = self.activity()
        self.assertEqual(going["kind"], "job")
        self.assertEqual(going["phase"], "going")
        self.assertIsNotNone(going["job"], "去打工的路上也该说明是哪份工")
        self.assertEqual(going["job"]["title"], "在咖啡馆帮工")
        self.assertGreater(going["job"]["pay"], 0)
        self.assertFalse(going["job"]["paid"], "还在路上就说已结工资，是把计划当成已发生")

        self.advance_past(going["until"])  # 到岗
        self.assertEqual(self.activity()["phase"], "there", "到了才算在做")
        self.assertFalse(self.activity()["job"]["paid"], "正在做也还没结")

    def test_every_position_says_where_it_came_from(self) -> None:
        """没有无出处的坐标：`basis` 必须落在四个枚举里。"""
        allowed = {"home_area", "place", "route", "unknown"}
        for step, advance in (("出发前", None), ("刚出发", None), ("到店", 7), ("回程", 40), ("到家", 240)):
            if step == "刚出发":
                self.depart("harbour_cafe")
            if advance:
                self.clock.advance(minutes=advance)
            with self.subTest(step=step):
                position = self.me()["position"]
                if position is not None:
                    self.assertIn(position["basis"], allowed)
                    self.assertGreater(position["precision_m"], 0, "精度要给真数，不给 0")


    def test_the_leg_is_the_one_ta_is_on_now_not_the_main_one(self) -> None:
        """多段行程：给的必须是 **TA 此刻实际在的那一段**，不是整趟的主段。

        `tokyo_flight` 去程是 打车(35) → 候机(60) → **飞机(240，main)** → 火车(40，main) → 步行(8)。
        出发 10 分钟时 TA 在**打车**去机场的路上；取 `kind == "main"` 的第一段会得到**飞机**——
        地图就会把位置点画在航线上、`mode` 显示成飞机。

        **这条是专门用来区分两种实现的**：改回取主段它必红。W1 原有的 21 条用例全用
        `harbour_cafe`（本地单段），**多段行程一条都没有**，所以修好之前它们也全是绿的——
        「跑绿了」和「这件事被测到了」是两回事。
        """
        self.web.economy.apply(self.owner.pet_id, 300, EconomyTransactionType.web_reward,
                               "test:world-tokyo", reason="测试", source="test")
        self.depart("tokyo_flight")
        self.clock.advance(minutes=10)
        me = self.me()
        self.assertEqual(me["activity"]["phase"], "going", "前提：这一刻确实在路上")
        self.assertIsNotNone(me["leg"], "在路上就该有当前段")
        self.assertEqual(me["leg"]["mode"], "taxi",
                         "出发 10 分钟还在打车去机场；给成 flight 说明取的是主段而不是当前段")


class PoseTests(WorldStateTestBase):
    """地图姿态（6c2b 请求）：**只由事实推出**。"""

    def test_at_home_is_idle_or_sleeping_never_a_guess(self) -> None:
        """作息没接上时给 `idle`，**不给 `sleeping`**——「不知道」不等于「睡着了」。"""
        self.assertIn(self.activity()["pose"], ("idle", "sleeping"))

    def test_on_the_way_the_pose_follows_the_actual_mode_of_that_leg(self) -> None:
        """走路那一段就是 walking，不是笼统的「在路上」。"""
        self.depart("harbour_cafe")
        me = self.me()
        self.assertIsNotNone(me["leg"], "在路上要给这一段")
        expected = "walking" if me["leg"]["mode"] == "walk" else "riding"
        self.assertEqual(me["activity"]["pose"], expected)

    def test_arriving_switches_the_pose_by_what_it_is_doing_there(self) -> None:
        self.depart("work:cafe_helper")
        self.advance_past(self.activity()["until"])
        self.assertEqual(self.activity()["pose"], "working", "到岗了就是在打工")

    def test_poses_without_a_source_are_never_produced(self) -> None:
        """`eating`／`sunbathing` 现在没有事实来源，**本批一次都不该出现**。

        枚举里留着位置是给前端先画图用的，**不是留给后端去猜**。
        """
        seen = set()
        self.depart("harbour_cafe")
        for _ in range(4):
            activity = self.activity()
            seen.add(activity["pose"])
            if not activity["until"]:
                break
            self.advance_past(activity["until"])
        self.assertFalse(seen & {"eating", "sunbathing"}, f"出现了没有来源的姿态：{seen}")


class HouseholdScopeTests(WorldStateTestBase):
    def test_my_own_pet_is_marked_mine(self) -> None:
        self.assertEqual(self.me()["relation"], "mine")

    def test_the_envelope_carries_server_time_and_coord_system(self) -> None:
        body = self.state()
        self.assertTrue(body["server_time"])
        self.assertEqual(body["coord_system"], "wgs84", "契约坐标一律 WGS-84，换算 GCJ-02 是前端的事")
        self.assertGreater(body["cache_seconds"], 0)
        self.assertTrue(body["pets"])


if __name__ == "__main__":
    unittest.main()
