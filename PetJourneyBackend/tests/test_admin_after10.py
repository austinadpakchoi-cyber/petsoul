"""第十批之后的小改动（交接 §69、§70）。从 test_admin_review10.py 拆出来：架构门禁要求每个文件不超过 30 个 def/class。

- 偏好与玩家同一个判断（I 把模型回信改成默认开启后请本窗口复核）；账本来源的说法跟玩家事由对齐。
- 公告与举报结果两个玩家侧入口：后台装配只在标准入口没挂时补挂（Q 报它们的能力键进不了 /meta，登记进共享入口归 I）。
"""

from __future__ import annotations

import unittest

from admin_base import AdminTestBase

from app.web_admin import labels as L


class PlayerPrefsParityTests(AdminTestBase):
    """用户详情里的偏好与玩家那一侧**同一个判断**（I 2026-09-24 把模型回信改成默认开启后请本窗口复核）：
    后台自己读库，没有偏好行时要取与身份模块相同的默认值——否则客服会对着「否」排查一个其实开着的设置。
    四项逐项比，任何一项的默认值以后再改，这条都会红。"""

    def test_ops_sees_every_preference_the_way_the_player_does(self):
        user = self.user("prefs-parity")
        with self.app.state.storage.connect() as conn:
            conn.execute("DELETE FROM web_user_prefs WHERE user_id = ?", (user.user_id,))  # 从没选过：没有偏好行
            conn.commit()
        player = self.web.identity.prefs(user.user_id)
        staff = self.owner().get(f"/users/{user.user_id}").json()["prefs"]
        keys = ("model_replies", "generated_photos", "pet_messages", "timezone")
        self.assertEqual({k: staff[k] for k in keys}, {k: player[k] for k in keys}, "没有偏好行：后台显示的默认值要与玩家那一侧一致")
        self.assertTrue(staff["model_replies"], "对照：模型回信现在默认开启（这一条是这次复核的起因）")

    def test_ledger_sources_follow_the_player_wording(self):
        """账本来源的说法不把「旅费」当货币讲（玩家那边的用语规则同一条正则），入住那笔跟玩家事由一样叫「入住欢迎星币」。"""
        from test_web_player_wording import CURRENCY_AS_UNIT

        offending = {code: text for code, text in L.LEDGER_SOURCE.items() if CURRENCY_AS_UNIT.search(text)}
        self.assertEqual(offending, {}, "后台的账本来源也不能把旅费当成货币单位")
        self.assertTrue(L.LEDGER_SOURCE["web.home.move_in"].startswith("入住欢迎星币"))


class PlayerEntryMountTests(AdminTestBase):
    """公告与举报结果两个玩家侧入口（Q 2026-09-24 报：它们的能力键进不了 /meta；登记进共享入口 WEB_ROUTER_MODULES 归 I）。
    后台装配只在标准入口没挂时补挂、挂过就跳过，所以 I 什么时候登记都不会重复挂；
    它们声明「可用」也有据：跑起来的应用里后台一定装好、表一定就绪，接口里那道闸走不到。"""

    PATHS = ("/api/v1/web/announcements", "/api/v1/web/assets/{asset_id}", "/api/v1/web/reports/mine")

    def test_each_player_entry_is_mounted_exactly_once(self):
        paths = [getattr(route, "path", None) for route in self.app.routes]
        self.assertEqual({p: paths.count(p) for p in self.PATHS}, {p: 1 for p in self.PATHS})

    def test_mounting_skips_routes_the_standard_registry_already_mounted(self):
        from fastapi import FastAPI

        from app.routers.web.announcements import router
        from app.web_admin import _mount_once

        fresh, registered = FastAPI(), FastAPI()
        _mount_once(fresh, router)
        _mount_once(fresh, router)  # 同一个应用上再补挂一次：跳过
        registered.include_router(router)  # 模拟 I 把它登记进 WEB_ROUTER_MODULES 之后
        _mount_once(registered, router)
        for app in (fresh, registered):
            paths = [getattr(route, "path", None) for route in app.routes]
            self.assertEqual(paths.count("/api/v1/web/announcements"), 1)

    def test_a_started_app_always_has_the_admin_installed_and_its_tables_ready(self):
        """所以两个路由里 `admin is None or not admin.tables_ready` 那道闸在跑起来的应用里走不到，「可用」的声明与它不矛盾。
        哪天后台装配变成有条件、或后台迁移不再随启动执行，这条先红——那时能力声明要改成跟着同一个开关走。"""
        # 用 getattr 取：后台没装上时要报出下面这句原因，而不是 AttributeError 读起来像「测试自己炸了」（Q 建议）
        admin = getattr(self.app.state, "admin", None)
        self.assertIsNotNone(admin, "后台没装上：create_app 里的后台装配变成有条件了？report_outcomes 的「可用」声明要跟着重新考虑")
        self.assertTrue(admin.tables_ready, "后台表没就绪：后台迁移没随启动执行？report_outcomes 的「可用」声明要跟着重新考虑")
        self.assertEqual(self.client.get("/api/v1/web/announcements").json()["source"], "live")


if __name__ == "__main__":
    unittest.main()
