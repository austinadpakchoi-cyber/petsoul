"""无关的设置请求不能撤销别人刚完成的撤权（CR-Q13 的并发那一半）。

`PATCH /settings` 是**部分更新**：没给的字段要用旧值补齐。所以它天然是一次"读—改—写"。
读如果发生在写事务之外，两个请求交错时后写的那个会把旧值整份盖回去：

    A 只想改时区，读到 model_replies=True
    B 完成撤权，库里变成 False
    A 接着提交自己那份合并结果 → model_replies 又变回 True

一个跟授权毫无关系的请求，就这样撤销了别人的撤权。
这里全部走正式 HTTP 路径（`PATCH /settings`），不直接调服务方法。
"""

from __future__ import annotations

import threading
import time
import unittest

from web_base import LUNCH_UTC, FakeClock, WebPlatformTestBase


class ConsentConcurrencyTests(WebPlatformTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.clock = FakeClock(LUNCH_UTC).install(self)
        self.owner = self.user("consent-race")
        self.owner.adopt_and_move_in("adopt-lan")
        self.patch_settings(model_replies=True)

    def patch_settings(self, **body):
        return self.owner.patch("/settings", body)

    def model_replies(self) -> bool:
        return bool(self.owner.get("/settings").json()["model_replies"])

    def epoch(self) -> int:
        return int((self.web.projector.runtime.row(self.owner.pet_id) or {}).get("privacy_epoch") or 0)

    def test_a_timezone_only_patch_cannot_write_the_revocation_back(self) -> None:
        """确定性交错：让"只改时区"那一次在读到旧值之后停住，期间另一次请求去撤权。"""
        identity = self.web.identity
        original = identity._prefs_in
        entered, release, armed = threading.Event(), threading.Event(), threading.Event()

        def paused(conn, user_id):
            values = original(conn, user_id)
            if armed.is_set():
                armed.clear()  # 只拦第一次
                entered.set()
                release.wait(10)
            return values

        identity._prefs_in = paused
        self.addCleanup(lambda: setattr(identity, "_prefs_in", original))
        results: dict[str, int] = {}

        def timezone_only() -> None:
            results["tz"] = self.patch_settings(timezone="Asia/Tokyo").status_code

        def revoke() -> None:
            results["revoke"] = self.patch_settings(model_replies=False).status_code

        armed.set()
        first = threading.Thread(target=timezone_only)
        first.start()
        self.assertTrue(entered.wait(10), "改时区那一次应当已经读到旧设置并停住")

        second = threading.Thread(target=revoke)
        second.start()
        time.sleep(0.4)  # 让撤权那一次真的去抢写锁

        self.assertTrue(second.is_alive(), "撤权应当在等前一个请求的写锁——说明读改写被串起来了，不是各读各的")
        release.set()
        first.join(10)
        second.join(20)

        self.assertEqual((results.get("tz"), results.get("revoke")), (200, 200), results)
        self.assertFalse(self.model_replies(), "撤权必须留住：无关的请求不能把它写回去")
        self.assertEqual(self.owner.get("/settings").json()["timezone"], "Asia/Tokyo", "改时区那次也要生效，不能被整份丢弃")

    def test_the_revocation_survives_a_burst_of_unrelated_patches(self) -> None:
        """正式 HTTP 并发：一次撤权夹在一堆只改时区的请求中间，最终必须是撤权生效。"""
        for attempt in range(3):
            self.patch_settings(model_replies=True)
            zone = "Asia/Tokyo" if attempt % 2 == 0 else "Asia/Shanghai"
            codes: list[int] = []
            lock = threading.Lock()

            def unrelated(z=zone) -> None:
                code = self.patch_settings(timezone=z).status_code
                with lock:
                    codes.append(code)

            def revoke() -> None:
                code = self.patch_settings(model_replies=False).status_code
                with lock:
                    codes.append(code)

            threads = [threading.Thread(target=unrelated) for _ in range(3)] + [threading.Thread(target=revoke)]
            threads += [threading.Thread(target=unrelated) for _ in range(3)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(30)

            self.assertEqual(sorted(set(codes)), [200], codes)
            self.assertFalse(self.model_replies(), f"第 {attempt + 1} 轮：撤权被无关请求盖掉了")

    def test_repeated_revocations_do_not_keep_bumping_the_version(self) -> None:
        """并发里重复写同一个值仍然不算授权变化：代数只跟真实变化走。"""
        self.patch_settings(model_replies=False)
        before = self.epoch()

        threads = [threading.Thread(target=lambda: self.patch_settings(model_replies=False)) for _ in range(5)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(30)

        self.assertEqual(self.epoch(), before, "已经是关的，再关几次都不该换代")


if __name__ == "__main__":
    unittest.main()
