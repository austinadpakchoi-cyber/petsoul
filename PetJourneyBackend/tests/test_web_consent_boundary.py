"""授权闸被摘掉之后，照片链路还剩哪些边界。

**这个文件原先叫"撤权边界"，测的是"主人在生图过程中收回授权会发生什么"**——
四个场景对应协调方在 candidate-0829 上的独立复现
（E:/petsoul-audit/coordination-audit/image-revocation-20260923/FINDING.md）。

**那条边界已被产品决定拿掉。** 用户 2026-09-23 直接决定取消逐次授权询问（角色与生活/旅行两类都取消），
计划文档改成「上传处说明照片会用于准备专属形象；按图片服务的新策略自动处理，不另设家庭生图许可」。
原先那四条（开工前撤权、两次调用之间撤权、写入前撤权、同连接复核）**不再成立，已被替换**。

现在钉的是三件事：

  1. 许可不变时照常出图并发布（对照，一直没变）；
  2. **撤掉旧开关不再挡**——产品决定的反向证据，谁把闸加回来它当场红；
  3. **以原名加回的授权钩子说什么都不算数**——那两个接线口已删除，谁以原名把读它们的检查加回来，这条当场红；
  4. **访问权那一道还在**——摘掉的是「询问」，不是「谁能看这只宠物」。

走真实 HTTP 家庭设置入口、真实组合根与队列，**只有生图供应商是替身**；不联网、不产生真实付费。

三层说法不能互相冒充（本文件的断言按这三层分开写）：
  - 事实层：已经发出的远端调用**撤不回**，也撤不回可能已产生的费用；
  - 本地费用层：已发出／已拿到结果的按**实际次数**结算，**不得退成 `not_sent`**；
  - 展示层：不发布时页面显示 `failed`（无图），**不冒充 `unknown`**。
"""

from __future__ import annotations

import unittest

from web_base import LUNCH_UTC, FakeClock, WebPlatformTestBase
from web_provider_fakes import FakeIllustrator


class HookedIllustrator(FakeIllustrator):
    """替身生图：可以在**某一次调用返回之后**触发回调，用来精确制造“两次调用之间撤权”。

    `after_call[n]` 在第 n 次调用（从 1 开始）返回之前执行。进程内确定性注入，
    不是真实的并发供应商事务，也不是网络测试。
    """

    def __init__(self) -> None:
        super().__init__()
        self.after_call: dict[int, callable] = {}

    def render(self, prompt, reference=None, size="2048x2048"):
        result = super().render(prompt, reference, size)
        hook = self.after_call.get(len(self.prompts))
        if hook is not None:
            hook()
        return result


class ConsentBoundaryTests(WebPlatformTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.clock = FakeClock(LUNCH_UTC).install(self)
        self.illustrator = HookedIllustrator()
        self.web.illustrations.illustrator = self.illustrator  # 唯一的替换：供应商换成替身

    # ---- 场景辅助 ----
    def owner_with_photos(self):
        owner = self.user("consent-owner")
        owner.adopt_and_move_in("adopt-lan")
        self.household_id = owner.get("/onboarding").json()["households"][0]["household_id"]
        self.assertTrue(owner.patch("/settings", {"generated_photos": True}).json()["generated_photos"])
        self.owner = owner
        return owner

    def revoke(self) -> None:
        """走正式家庭设置入口把旧的「生成照片」开关关掉（与协调方探针同一条路）。

        **这里原先断言 `illustrations.opted_in(...)` 为假**。组合根摘掉那条接线之后（2026-09-23），
        `opted_in` 落回服务里的默认 `lambda …: False`——**那句断言从此恒为真、什么都不测**。
        改成直接读这次设置**真的落了库**：它要证明的本来就是"开关确实关上了"，不是"钩子说假"。
        """
        response = self.owner.patch(f"/households/{self.household_id}/settings", {"generated_photos": False})
        self.assertEqual(response.status_code, 200, response.text)
        stored = self.row("SELECT generated_photos FROM web_households WHERE household_id = ?", (self.household_id,))
        self.assertEqual(stored["generated_photos"], 0, "开关确实关上了——下面的用例才是在测「关上了也不挡」")

    def cafe_adventure(self) -> None:
        owner = self.owner
        owner.post("/journey/depart", {"destination_key": "harbour_cafe"})
        self.clock.advance(minutes=7)
        visit_id = owner.get("/journey/map").json()["current_visit_id"]
        greet = next(a for a in owner.get(f"/visits/{visit_id}").json()["activities"] if a["kind"] == "greet_resident")
        owner.post(f"/visits/{visit_id}/actions", {"activity_id": greet["activity_id"]})
        self.clock.advance(seconds=5)

    def message(self) -> dict:
        return next(m for m in self.owner.get(f"/communicator/{self.owner.pet_id}/messages").json()["items"]
                    if "咖啡馆小侦探" in m["text"])

    def row(self, sql: str, params: tuple):
        with self.web.illustrations.storage.connect() as conn:
            return conn.execute(sql, params).fetchone()

    def task_of(self, message: dict) -> str:
        return self.row("SELECT photo_task_id FROM web_messages WHERE message_id = ?", (message["message_id"],))["photo_task_id"]

    def reservations(self, task_id: str) -> list[tuple]:
        """这个任务的本地预占：(状态, 结果口径, 实际计量单位)。"""
        with self.web.illustrations.storage.connect() as conn:
            rows = conn.execute("SELECT status, outcome, actual_units FROM web_budget_reservations WHERE operation_id LIKE ? "
                                "ORDER BY rowid", (f"illustration:{task_id}:%",)).fetchall()
        return [(r["status"], r["outcome"], r["actual_units"]) for r in rows]

    def illustration(self, task_id: str):
        return self.row("SELECT status, rel_path FROM web_illustrations WHERE task_id = ?", (task_id,))

    def start_photo(self) -> str:
        """走完一次真实冒险，排上生图任务，返回任务号（还没执行）。"""
        self.cafe_adventure()
        message = self.message()
        self.assertEqual(message["photo_status"], "processing", "刚排队时是处理中")
        self.message_id = message["message_id"]
        return self.task_of(message)

    def settled(self) -> str:
        return self.row("SELECT status FROM web_tasks WHERE task_id = ?", (self.task_id,))["status"]

    def privacy_epoch(self) -> int:
        row = self.row("SELECT privacy_epoch FROM web_entity_runtime WHERE pet_id = ?", (self.owner.pet_id,))
        return int(row["privacy_epoch"]) if row else 0

    # ---- 1. 正常许可（对照）：修复前就应该通过 ----
    def test_with_permission_unchanged_the_photo_is_produced_and_published(self) -> None:
        self.owner_with_photos()
        self.task_id = self.start_photo()

        self.web.illustrations.run_pending()

        self.assertEqual(len(self.illustrator.prompts), 2, "没有参考照片：证件照＋场景图两次替身调用")
        self.assertEqual(self.settled(), "succeeded")
        self.assertEqual(self.illustration(self.task_id)["status"], "ready")
        done = self.message()
        self.assertEqual(done["photo_status"], "ready")
        self.assertEqual(self.owner.get(done["photo_url"].removeprefix("/api/v1/web")).status_code, 200)
        self.assertEqual(self.reservations(self.task_id), [("settled", "succeeded", 2)], "两次都发出了，按 2 结算")

    # ---- 2. 撤掉旧开关**不再**挡照片：这是产品决定，钉住它 ----
    def test_turning_the_old_switch_off_no_longer_blocks_the_photo(self) -> None:
        """原先这里的四条用例测的是"撤权之后会发生什么"。**那条边界已被产品决定拿掉。**

        用户 2026-09-23 直接决定取消逐次授权询问（角色与生活/旅行两类都取消），
        计划文档改成「上传处说明照片会用于准备专属形象；按图片服务的新策略自动处理，不另设家庭生图许可」。

        所以现在钉的是**反向事实**：把那个旧开关关掉，照片照常生成并发布。
        留这条而不是删掉整个文件——它是那条边界的反向证据，**谁把闸加回来，它会当场红**。
        """
        self.owner_with_photos()
        self.task_id = self.start_photo()

        self.revoke()
        self.web.illustrations.run_pending()

        self.assertEqual(len(self.illustrator.prompts), 2, "旧开关关掉了，照样两次调用")
        self.assertEqual(self.illustration(self.task_id)["status"], "ready", "照样发布")
        self.assertEqual(self.message()["photo_status"], "ready")

    # ---- 3. 更硬的一条：以原名加回的授权钩子**说什么都不算数** ----
    def test_no_consent_hook_is_consulted_anywhere_in_the_attempt(self) -> None:
        """在服务上挂两个与旧接线口同名的钩子，都设成"一律不允许"，照片仍然要画出来并发布。

        为什么要比走设置入口那条更硬：那条只证明"那条路不再挡"；
        这一条直接让同名钩子说"不行"，证明**这次尝试里一处都没有再读它们**——
        登记时、领取时、两次发送之前、发布之前，原先五个点位现在一个都不剩。

        `opted_in` / `consent_in` 两个属性已于 2026-09-24 从服务里删除（最后的读者先后被摘）。
        下面的赋值是**有意只写不读**：删后它仍有鉴别力。在删后的代码上做内存变异（本文件与 `test_web_photo_atomic` 共 13 条）：

            以原名加回检查、默认不放行   → 13 条全红
            以原名加回检查、默认放行     → 只红 2 条：本条与 `test_web_photo_atomic` 那条反向用例
            换个名字加回、默认不放行     → 13 条全红
            换个名字加回、默认放行       → 0 红

        第二行是这两条别的用例替代不了的地方：检查加回来了、平时又放行，只有让同名钩子说「不行」才看得出来。
        **本条抓不到的就是最后一行**。那一类只有在新检查读的是家庭设置时，才可能由
        `test_turning_the_old_switch_off_no_longer_blocks_the_photo` 兜住（推理，未做变异验证）。
        所以不改成 `hasattr`：换名加回它同样抓不到，加回一个没人读的无害属性它反而红。
        """
        self.owner_with_photos()
        self.task_id = self.start_photo()
        self.web.illustrations.opted_in = lambda user_id, pet_id=None: False
        self.web.illustrations.consent_in = lambda conn, user_id, pet_id: False

        self.web.illustrations.run_pending()

        self.assertEqual(len(self.illustrator.prompts), 2, "钩子说不行也不算数——本模块不读它们")
        self.assertEqual(self.illustration(self.task_id)["status"], "ready")
        self.assertEqual(self.reservations(self.task_id), [("settled", "succeeded", 2)], "按实际发出的 2 次结算")

    # ---- 4. 访问权那一道在**导演路径**上，不在这条 ----
    def test_this_adventure_path_never_consulted_access_either(self) -> None:
        """如实记下一件我写上一条时搞错、查清后改正的事。

        我原本想在这里断言"看不了这只宠物就不发"，结果它照发——**因为这条路径压根不问访问权**。
        `_render` 里 `directed = bool(scene_key) and style == "selfie"`：冒险照两样都不满足，
        走的是非导演路径，`can_access` 根本不进入判断。
        所以"摘掉授权闸把访问权也带走了"这个怀疑在这条路径上**不成立**——它本来就没有。

        真正有访问权闸的是**导演路径**（主人主动发起的自拍），
        那一条钉在 `test_web_photo_director_worker.py::test_someone_who_cannot_see_the_pet_gets_no_photo`。

        非导演路径不问访问权**不是安全缺口**：它由世界事件为**主人自己的**宠物触发，
        出图之后的读取仍然走鉴权路由。但这条差异值得写下来，免得下一个人以为两条路一样。
        """
        self.owner_with_photos()
        self.task_id = self.start_photo()
        self.web.illustrations.can_view_pet = lambda user_id, pet_id: False

        self.web.illustrations.run_pending()

        self.assertEqual(len(self.illustrator.prompts), 2, "非导演路径不读 can_access，照发")
        self.assertEqual(self.illustration(self.task_id)["status"], "ready")


if __name__ == "__main__":
    unittest.main()
