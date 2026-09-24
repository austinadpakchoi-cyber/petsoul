"""接待叮嘱**不进生图**：CR-IMAGE-MEMORY-PURPOSE-2026-09-24 的 A 半（排队／发送／发布边界）。

背景（c84a 逐段核实、I 与 B 各自独立复核过）：`keepsake_of` 请求的是 `private_chat` 下的 `favorite_object`，
经 `render_story` 插进冒险故事（"带着你准备的…"那一句），故事又原样进了插画任务载荷与**供应商提示词**。
只授权过私聊的那句话，进了发给外部供应商的请求里。

两半各管一道、互相独立（任一侧失效，另一侧仍挡得住）：
  - **入口（I）**：`keepsake_of` 只放行同一条叮嘱同时授权 `public_story` 与 `media_generation` 的；
  - **图片这一侧（本文件）**：本批**彻底不让任何叮嘱内容进生图**——CR 第 20 行给的第二条路。

所以这里钉的是：
  1. 新排队的任务载荷里**连那段文本都不存**；
  2. 发送时按模板**不带叮嘱**重渲，场景描述保留；
  3. **按旧规则已排进队的在途任务**，其载荷里那段 story **一个字都不读**（CR 第 28 条：证明缓存载荷不夹带旧内容）；
  4. **不借 `privacy_epoch`**：无关设置改动不该挡住合法的照片（CR 第 29 条）。

一次性临时库、替身供应商；不联网、**0 次付费调用**。标记串是合成的，不是任何真实叮嘱。
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from app.image_provider.models import GeneratedImage
from app.utils import utcnow
from app.web_journey.adventures import ADVENTURES, render_story
from app.web_journey.illustrations import IllustrationService
from app.web_platform.runtime_epochs import bump_in
from app.web_platform.tasks import WebTaskQueue
from task_budget_helpers import open_storage

MARKER = "ZX-合成标记-7731围巾"  # 合成的"私聊叮嘱"。出现在提示词里就是泄露
KEY = "cafe_detective"
PNG = b"\x89PNG\r\n\x1a\nstub"


class _Recorder:
    """**替身**生图：只记提示词，不联网。"""

    available = True
    provider_label = "测试生图（假）"

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def render(self, prompt, reference=None, size="2048x2048", background=None) -> GeneratedImage:
        self.prompts.append(prompt)
        return GeneratedImage(image_bytes=PNG, mime_type="image/png", model="fake", provider="fake", source="b64")


class MemoryNeverReachesTheImageTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.storage = open_storage(str(root / "memory.sqlite3"))
        self.illustrations = IllustrationService(self.storage, root / "media", WebTaskQueue(self.storage))
        self.illustrator = _Recorder()
        self.illustrations.illustrator = self.illustrator
        self.illustrations.character_of = lambda pet_id: ("cat", "小银", None)
        self.illustrations.reference_photo_of = lambda pet_id: (PNG, "image/png")  # 有主人原照：不画证件照

    # ---- 辅助 ----
    def adventure(self, source: str = "ev-1") -> str:
        """一次真实形状的冒险事件：故事里**夹着**合成的叮嘱标记——就是入口修好之前会发生的样子。"""
        story = render_story(ADVENTURES[KEY], "小银", MARKER)
        self.assertIn(MARKER, story, "前提：事件里的故事确实夹着叮嘱")
        event = SimpleNamespace(journey=SimpleNamespace(user_id="u-1", pet_id="pet-1"), source_event_id=source,
                                data={"adventure_key": KEY, "title": ADVENTURES[KEY].title, "badge": "", "story": story})
        return self.illustrations.request(event)

    def payload_of(self, task_id: str) -> dict:
        with self.storage.connect() as conn:
            return json.loads(conn.execute("SELECT payload_json FROM web_tasks WHERE task_id = ?", (task_id,)).fetchone()["payload_json"])

    def rewrite_as_old_payload(self, task_id: str) -> None:
        """把载荷改回**旧规则**的样子：存着带叮嘱的 story、没有 adventure_key——模拟修复之前就排进队的在途任务。"""
        payload = self.payload_of(task_id)
        payload.pop("adventure_key", None)
        payload["story"] = render_story(ADVENTURES[KEY], "小银", MARKER)
        with self.storage.connect() as conn:
            conn.execute("UPDATE web_tasks SET payload_json = ? WHERE task_id = ?", (json.dumps(payload, ensure_ascii=False), task_id))

    # ---- ① 排队：载荷里连那段文本都不存 ----
    def test_a_new_task_does_not_store_the_story_at_all(self) -> None:
        task_id = self.adventure()

        payload = self.payload_of(task_id)

        self.assertNotIn("story", payload, "任务表里不该再积攒一份私人叮嘱的副本")
        self.assertNotIn(MARKER, json.dumps(payload, ensure_ascii=False))
        self.assertEqual(payload["adventure_key"], KEY, "存冒险键，发送时按模板重渲")

    # ---- ② 发送：按模板不带叮嘱重渲，场景保留 ----
    def test_the_prompt_keeps_the_scene_but_not_the_memory(self) -> None:
        self.adventure()

        self.illustrations.run_pending()

        self.assertEqual(len(self.illustrator.prompts), 1)
        prompt = self.illustrator.prompts[0]
        self.assertNotIn(MARKER, prompt, "叮嘱**一个字都不能**进供应商提示词")
        self.assertNotIn("带着你准备的", prompt, "连那句引子都不该出现")
        # 对照：场景描述还在——证明不是"整段故事都删了"这种过度修复
        self.assertIn(render_story(ADVENTURES[KEY], "小银", None)[:20], prompt, "模板场景要保留")

    # ---- ③ 在途旧任务：旧载荷里的 story 一个字都不读 ----
    def test_a_task_queued_under_the_old_rule_never_sends_its_stored_story(self) -> None:
        """**CR 第 28 条的后一半**："若彻底不再使用，证明缓存载荷也不夹带旧内容。"

        修复之前排进队的任务，载荷里静态存着带叮嘱的 story。这条证明**它从此不被读、不被发**。
        （那段文本仍静态留在 `web_tasks.payload_json` 里——要不要回刷是数据保留判断，
        且改在途载荷会碰领取围栏，**本批不做**，已交 c84a／Q 定。这条用例只证明"不再被用"。）
        """
        task_id = self.adventure()
        self.rewrite_as_old_payload(task_id)
        self.assertIn(MARKER, json.dumps(self.payload_of(task_id), ensure_ascii=False), "前提：旧载荷确实夹着")

        self.illustrations.run_pending()

        self.assertEqual(len(self.illustrator.prompts), 1)
        self.assertNotIn(MARKER, self.illustrator.prompts[0], "旧载荷里的 story 不能被发出去")
        self.assertIn(ADVENTURES[KEY].title, self.illustrator.prompts[0], "没有冒险键就只用标题")

    # ---- ④ 不借 privacy_epoch：无关设置改动不挡合法照片 ----
    def test_an_unrelated_privacy_change_mid_attempt_does_not_block_the_photo(self) -> None:
        """CR 第 29 条："修改无关的消息/模型偏好不应阻断仍合法的普通照片"。

        `privacy_epoch` 在 `pet_messages` / `model_replies` 变化时也会 +1。
        图片这一侧既然本批**根本不用叮嘱**，就没有任何东西需要靠它来判"撤回"——
        在两次读取之间把它 +1，照片照样画、照样发布。
        """
        task_id = self.adventure()
        with self.storage.connect() as conn:
            bump_in(conn, "pet-1", "privacy_epoch", utcnow())  # 模拟主人刚改了"TA 能不能主动来信"

        self.illustrations.run_pending()

        with self.storage.connect() as conn:
            status = conn.execute("SELECT status FROM web_illustrations WHERE task_id = ?", (task_id,)).fetchone()["status"]
        self.assertEqual(status, "ready", "无关设置改动不该挡住已经合法的照片")


if __name__ == "__main__":
    unittest.main()
