"""**谁在驱动这条链路**：进程内那一个线程到底泵不泵角色任务。

从 `test_web_character_autostart.py` 拆出来的（那边涨到 32 个 def/class，超了 `arch_gate` 的 30），
拆得也对——"上传会不会自动排队"和"排了之后有没有人去执行"是两件事，
而且**第二件出问题时第一件看起来完全正常**。

钉的那个缺口长这样：`illustrations.run_pending()` 里写死 `run_once(self.tasks, {KIND: self}, ...)`，
`KIND == "illustration"`；角色任务的 kind 是 `"pet_character"`，**永远不会被它领取**。
上传照常排队、库里真有行，却没有任何线程执行它——**数据库看起来一切正常，任务就是不动，没有任何报错**。

不联网、**0 次付费调用**（构造应用时只建对象，不发请求）。
"""

from __future__ import annotations

import unittest


class ImageWorkPumpTests(unittest.TestCase):
    """进程内那一个线程怎么同时泵两条生图链路。纯单元，不建应用、不联网。"""

    class Stub:
        def __init__(self, handled: int = 1, boom: Exception | None = None) -> None:
            self.handled, self.boom, self.rounds = handled, boom, 0

        def run_pending(self, limit: int = 5) -> int:
            self.rounds += 1
            if self.boom:
                raise self.boom
            return self.handled

    def test_the_pump_drives_every_service_and_adds_up_what_they_did(self) -> None:
        from app.web_character import ImageWorkPump

        first, second = self.Stub(handled=2), self.Stub(handled=3)

        handled = ImageWorkPump(first, second).run_pending()

        self.assertEqual((first.rounds, second.rounds), (1, 1))
        self.assertEqual(handled, 5)

    def test_one_failing_service_does_not_stop_the_others(self) -> None:
        """两条链路共用一个线程。一条抛出去把本轮带走，另一条就再也不跑了——
        **而且同样是静默的**，和"根本没人泵角色任务"是同一种形状的故障。

        `IllustrationWorker._loop` 自己那层 except 在**整轮之外**，兜不住这个，所以必须逐个兜。
        """
        from app.web_character import ImageWorkPump

        broken, healthy = self.Stub(boom=RuntimeError("这一轮插画炸了")), self.Stub(handled=1)

        with self.assertLogs("petsoul.web.character", level="ERROR"):
            handled = ImageWorkPump(broken, healthy).run_pending()

        self.assertEqual(healthy.rounds, 1, "前面那条炸了，后面这条照样要跑")
        self.assertEqual(handled, 1, "只算真正做成的那些")


class ProductionPumpWiringTests(unittest.TestCase):
    """**这条钉的是那个静默缺口本身**：生产装配里到底有没有人去领角色任务。

    缺口长这样：`illustrations.run_pending()` 里写死 `kind="illustration"`，
    角色任务的 kind 是 `"pet_character"`，**永远不会被它领取**——
    上传照常排队、库里真有行，但没有任何线程执行它。
    数据库看起来一切正常，任务就是不动，**没有任何报错**。

    所以这条不去断言"能画出来"（那是别的用例的事），只断言**装配把角色接进了那个线程**。
    构造一个配了生图供应商的应用（`worker` 只有在供应商可用时才建）；只建对象，**不发任何请求**。
    """

    def test_the_composed_app_pumps_character_tasks_too(self) -> None:
        import tempfile
        from pathlib import Path

        from app.config import Settings
        from app.main import create_app
        from app.web_character import CharacterService, ImageWorkPump

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        settings = Settings(database_path=root / "w.sqlite3", upload_dir=root / "u", web_private_media_dir=root / "p",
                            public_base_url="http://testserver", auth_secret="web-test-secret-0123456789abcdef-0123",
                            apple_auth_mode="mock", scheduler_enabled=False, legacy_api_policy="open",
                            economy_admin_token="t", web_cookie_secure=False, web_demo_catalog=True,
                            web_providers_enabled=True, image_provider_type="openai",
                            image_api_key="sk-not-a-real-key-never-sent")

        web = create_app(settings).state.web

        self.assertIsNotNone(web.worker, "配了生图供应商就该有 worker")
        pump = web.worker.service
        self.assertIsInstance(pump, ImageWorkPump)
        pumped = [service for service in pump.services if isinstance(service, CharacterService)]
        self.assertEqual(pumped, [web.character], "泵里那个角色服务必须就是 WebServices 上的同一个实例")
        self.assertIs(web.character.illustrator, web.providers.illustrator, "供应商也要接上，否则 available() 恒假")
        # 生产装配里 GPT 供应商会**真的**发 `background`，所以这里必须为真——
        # 否则拿回来的不透明会被一律记成 `transparency_not_requested`，把"中转没给"说成"我们没要"。
        # （先前那条"不可达守卫"钉的是**测试应用**里的值，那里供应商是 NoIllustrator，生产怎么翻它都绿——
        #  那是它的盲点；这一面必须在真实配置下钉。）
        self.assertTrue(web.character.transparency_requested, "GPT 供应商会请求透明底，能力标记要读进来")


if __name__ == "__main__":
    unittest.main()
