"""金额闸门与交付入口的拒绝路径：每条守卫都要有一次**真的被触发**的证据。全程禁网。

覆盖 `batch.py` 与 `delivery.py` 的点位（`draft.py` / `validation.py` 各在自己那份里）。

**带参数的原因码单独说**：`batch_stopped:...`、`size_not_supported_by_sink:...`、
`delivery_would_drop_fields:...` 这几条把上下文拼进了消息，
所以**断言分两步**——冒号前的码用 `split(":")[0]` 钉住，冒号后的参数**再单独断言一次**。
参数本身是有信息的（哪一档尺寸、丢了哪些字段），只断言前半段等于放掉了它。

另外收了 4 条「**触发过、却没有任何用例断言它的原因码字面**」的：
`currency_missing`、`batch_stopped`、`delivery_would_drop_fields`、`model_output_missing_field`。
走到了和断言了走到的是哪一条，是两件事——只断言抛了异常的用例，
分不清抛的是不是**该抛的那一条**。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "fixtures" / "photo_director"))

import builders  # noqa: E402
from harness import OfflineCase  # noqa: E402

from app.web_photo_director import CURRENT_WEB_SINK, PhotoDirectorError  # noqa: E402
from app.web_photo_director.batch import (  # noqa: E402
    BatchGuard,
    Money,
    parse_money,
    validate_batch_cost,
)
from app.web_photo_director.delivery import SinkCapabilities, plan_delivery  # noqa: E402
from app.web_photo_director.draft import parse_model_draft  # noqa: E402

QUOTE = {"unit": 0.25, "currency": "CNY"}
CAP = {"amount": 3, "currency": "CNY"}


class BatchCostRejectionTests(OfflineCase):
    """金额算错了不是"少画一张"，是**在不知情的情况下超支**，所以这几条必须有证据。"""

    def refuses(self, call, code: str) -> None:
        with self.assertRaises(PhotoDirectorError) as caught:
            call()
        self.assertEqual(str(caught.exception), code)

    def test_a_non_numeric_amount_is_refused(self):
        self.refuses(lambda: Money("一块钱", "CNY"), "amount_not_numeric")

    def test_a_boolean_is_not_accepted_as_an_amount(self):
        """`True` 在 Python 里是 1——不挡住它，`cap=True` 会变成 1 元上限。"""
        self.refuses(lambda: Money(True, "CNY"), "amount_not_numeric")

    def test_a_negative_amount_is_refused(self):
        self.refuses(lambda: Money(-0.01, "CNY"), "amount_negative")

    def test_a_missing_currency_is_refused(self):
        """币种缺失不能当成"默认人民币"：报价 CNY、上限 USD 直接比数值是错的。"""
        self.refuses(lambda: Money(1.0, "   "), "currency_missing")

    def test_a_quote_that_is_not_an_object_is_refused_with_its_field_name(self):
        """原因码把字段名拼了进去，所以两个调用点报的不是同一个码。"""
        self.refuses(lambda: parse_money("0.25 元", field_name="provider_quote"),
                     "provider_quote_not_an_object")

    def test_a_cap_that_is_not_an_object_blocks_the_batch(self):
        checked = validate_batch_cost(QUOTE, "三块钱", 4)
        self.assertFalse(checked["ok"])
        self.assertEqual(checked["problems"], ["batch_cap_not_an_object"])

    def test_a_zero_unit_price_blocks_the_batch(self):
        """单价 0 多半是没解析出来，不是真免费——放行会让上限形同虚设。"""
        checked = validate_batch_cost({"unit": 0, "currency": "CNY"}, CAP, 4)
        self.assertFalse(checked["ok"])
        self.assertIn("provider_quote_must_be_positive", checked["problems"])

    def test_a_stopped_guard_refuses_the_next_send_and_says_why(self):
        """停批之后再问"还能发吗"必须继续拒绝，并且带上**当初停批的原因**。"""
        guard = BatchGuard.from_spec(QUOTE, CAP, 4)
        guard.record("unknown", note="cafe")
        with self.assertRaises(PhotoDirectorError) as caught:
            guard.check_next()
        message = str(caught.exception)
        self.assertEqual(message.split(":")[0], "batch_stopped")
        self.assertEqual(message.split(":", 1)[1], "unknown_result",
                         "停批原因要带出来，否则运维分不清是超上限还是结果不明")


class DeliveryRejectionTests(OfflineCase):
    """交付层的职责是**不许静默丢字段**，所以它的拒绝路径就是它的全部价值。"""

    def photo(self, **kwargs):
        context = builders.build_context("cafe", **kwargs)
        return self.director.direct(context, builders.build_access(context))

    def test_a_size_the_sink_cannot_accept_is_refused_with_that_size(self):
        narrow = SinkCapabilities(
            name="fx-sink", max_references=1, supports_negative_prompt=True,
            known_reference_roles=frozenset({"pet_identity"}),
            preserves_reference_order=True, allowed_sizes=frozenset({"1024x1024"}),
        )
        with self.assertRaises(PhotoDirectorError) as caught:
            plan_delivery(self.photo(), narrow)
        message = str(caught.exception)
        self.assertEqual(message.split(":")[0], "size_not_supported_by_sink")
        self.assertEqual(message.split(":", 1)[1], "2048x2048")

    def test_a_sink_that_knows_no_reference_role_is_refused(self):
        """一张参考都送不进去时宁可不出图——没有身份参考就不是这只宠物。"""
        blind = SinkCapabilities(
            name="fx-sink", max_references=1, supports_negative_prompt=True,
            known_reference_roles=frozenset(), preserves_reference_order=True,
        )
        with self.assertRaises(PhotoDirectorError) as caught:
            plan_delivery(self.photo(), blind, strict=False)
        self.assertEqual(str(caught.exception), "no_reference_survives_sink")

    def test_an_identity_reference_that_is_not_first_is_refused(self):
        """入口只认得地点参考时，身份参考会被丢掉、地点顶到第一位——这不能放行。"""
        place_only = SinkCapabilities(
            name="fx-sink", max_references=2, supports_negative_prompt=True,
            known_reference_roles=frozenset({"place_environment"}),
            preserves_reference_order=True,
        )
        with self.assertRaises(PhotoDirectorError) as caught:
            plan_delivery(self.photo(with_place_reference=True), place_only, strict=False)
        self.assertEqual(str(caught.exception), "identity_reference_must_be_first")

    def test_a_sink_that_reorders_references_records_the_loss(self):
        """顺序丢了也是语义丢失：底层按自己的角色表重排，导演给的顺序保不住。"""
        shuffling = SinkCapabilities(
            name="fx-sink", max_references=2, supports_negative_prompt=True,
            known_reference_roles=frozenset({"pet_identity", "place_environment"}),
            preserves_reference_order=False,
        )
        plan = plan_delivery(self.photo(with_place_reference=True), shuffling, strict=False)
        self.assertIn("reference_order", plan.dropped)
        self.assertTrue(any("顺序" in note for note in plan.notes))

    def test_strict_mode_refuses_and_names_every_field_it_would_drop(self):
        """`delivery_would_drop_fields` 后面那串是给人看的证据，断言它顺便钉住了格式。"""
        with self.assertRaises(PhotoDirectorError) as caught:
            plan_delivery(self.photo(), CURRENT_WEB_SINK, strict=True)
        message = str(caught.exception)
        self.assertEqual(message.split(":")[0], "delivery_would_drop_fields")
        self.assertEqual(message.split(":", 1)[1], "negative_prompt")

    def test_the_delivery_plan_reports_what_it_would_actually_send(self):
        """`evidence()` 是运维看的那份，缺了它"丢了什么"只在异常里一闪而过。"""
        plan = plan_delivery(self.photo(), CURRENT_WEB_SINK, strict=False)
        evidence = plan.evidence()
        self.assertEqual(evidence["size"], "2048x2048")
        self.assertIs(evidence["negative_prompt_sent"], False)
        self.assertEqual(evidence["dropped"], ["negative_prompt"])
        self.assertEqual([slot[1] for slot in evidence["references"]], ["pet_identity"])
        self.assertTrue(evidence["notes"])


class ModelReplyFieldTests(OfflineCase):
    """补一条只差"断言字面"的：原本走到过，但没有任何用例说清走到的是哪一条。"""

    def test_a_model_reply_missing_a_required_field_is_refused(self):
        context = builders.build_context("cafe")
        with self.assertRaises(PhotoDirectorError) as caught:
            parse_model_draft('{"expression": "curious"}', context)
        self.assertEqual(str(caught.exception), "model_output_missing_field")
