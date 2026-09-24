"""后台界面上的「人话」（app/web_admin/labels.py）：说法与领域里的代码必须一一对得上。

三道核对：
1. 能枚举的代码族（安静原因、心跳结论与依据、到期事项、账本类型、角色、权限）与领域枚举**双向**相等：
   领域多一个值、词表少一句就红；词表多写一个领域里没有的值也红。
2. 没法枚举的代码族（账本来源、错误原因、事件种类……）**不许编**：词表里的每个代码都必须在 app/ 的源码里真实出现过。
3. 审计动作由 `admin_base.AdminTestBase.tearDown` 在每个后台用例收尾时核：真实产生过的每个动作都要有说法。
"""

from __future__ import annotations

import pathlib
import re
import unittest

from admin_base import AdminTestBase

from app.schemas.base import EconomyTransactionType
from app.web_admin import labels as L
from app.schemas.web.pets import PetSpecies
from app.web_admin.economy_checks import RULES as AdminEconomyChecksRules
from app.web_admin.permissions import Permission, Role
from app.web_runtime.heartbeat_policy import HeartbeatAction
from app.web_runtime.reasons import ReasonCode, SilenceKind, SilenceReason
from app.web_runtime.state import DueKind

APP = pathlib.Path(__file__).resolve().parent.parent / "app"
SCRIPTS = pathlib.Path(__file__).resolve().parent.parent.parent / "scripts"  # 演示数据脚本也会写代码（seed.admin_demo）


def _source_without_labels() -> str:
    files = [path for path in APP.rglob("*.py") if not (path.name == "labels.py" and path.parent.name == "web_admin")]
    files += sorted(SCRIPTS.glob("*.py")) if SCRIPTS.is_dir() else []
    return "\n".join(path.read_text(encoding="utf-8") for path in files)


class EnumerableFamilyTests(unittest.TestCase):
    def assertSameCodes(self, family: dict, enum_cls, *, extra: set[str] = frozenset()):
        expected = {member.value for member in enum_cls} | set(extra)
        self.assertEqual(set(family), expected,
                         f"{enum_cls.__name__}：词表多了 {sorted(set(family) - expected)}，少了 {sorted(expected - set(family))}")

    def test_runtime_families_match_the_domain_enums(self):
        self.assertSameCodes(L.SILENCE, SilenceReason)
        self.assertSameCodes(L.SILENCE_KIND, SilenceKind)
        self.assertSameCodes(L.HEARTBEAT_ACTION, HeartbeatAction)
        self.assertSameCodes(L.REASON, ReasonCode)
        self.assertSameCodes(L.DUE_KIND, DueKind)

    def test_character_reasons_and_task_kinds_follow_the_source(self):
        """角色形象与证件照的原因码与对外契约 CharacterReason 双向相等；任务类型与源码里每一处入队的种类**双向**相等。
        入队处写的是常量名（KIND / POSE_KIND / RESEARCH_KIND）或字面量：常量名按**那个模块里的真实取值**解析，
        新增一种入队、这里没收录就红（第十批回归快照里就这样抓到了旅行心愿的 travel_research）；词表多写一种没人入队的也红。"""
        import importlib

        from app.schemas.web.character import CharacterReason
        from app.web_character import id_photo, model
        from app.web_journey import illustrations

        self.assertSameCodes(L.CHARACTER_REASON, CharacterReason)
        enqueued: set[str] = set()
        for path in APP.rglob("*.py"):
            if "web_admin" in path.parts or (path.name == "tasks.py" and path.parent.name == "web_platform"):
                continue  # 队列自己的定义不是入队点
            text = path.read_text(encoding="utf-8")
            for arg in re.findall(r"\.enqueue(?:_in)?\(\s*(?:conn,\s*)?([A-Za-z_][A-Za-z0-9_]*|[\"'][a-z_]+[\"'])", text):
                if arg[0] in "\"'":
                    enqueued.add(arg[1:-1])
                elif arg.isupper():
                    module = importlib.import_module(".".join(path.relative_to(APP.parent).with_suffix("").parts))
                    self.assertTrue(hasattr(module, arg), f"{path.name}：入队用的 {arg} 解析不出来——扫描规则要跟着改")
                    enqueued.add(getattr(module, arg))
                # 小写的是转手的形参或正文（比如 poses.enqueue_in(conn, payload, …)），不是任务类型
        self.assertGreaterEqual(enqueued, {illustrations.KIND, model.KIND, model.POSE_KIND, id_photo.KIND},
                                f"扫描入队点的规则失效了：只找到 {sorted(enqueued)}")
        self.assertEqual(enqueued - set(L.TASK_KIND), set(), "这些任务类型有人在入队，后台词表里没有")
        self.assertEqual(set(L.TASK_KIND) - enqueued, set(), "词表里这些任务类型没有任何入队点——是不是编的，或者入队处改名了？")

    def test_budget_purposes_and_providers_follow_every_reservation(self):
        """额度预占的用途与供应商都要有说法（平台成本、两本账、每天生图、宠物运行的今日额度都按它们显示）：
        每一处 `.reserve(…)` 里写的 purpose / provider——字面量，或常量（按**那个模块里的真实取值**解析，
        旅行研究就是 `purpose=PURPOSE, provider=PROVIDER`）——再加源码别处写死的 `purpose="…"`（生活规划是按位置传进去的）。"""
        import importlib

        purposes: set[str] = set()
        providers: set[str] = set()
        for path in APP.rglob("*.py"):
            if "web_admin" in path.parts:
                continue
            text = path.read_text(encoding="utf-8")
            purposes |= set(re.findall(r"""\bpurpose=["']([a-z_]+)["']""", text))
            for args in re.findall(r"\.reserve\(((?:[^()]|\([^()]*\))*)\)", text):
                for key, value in re.findall(r"""\b(purpose|provider)=([A-Z][A-Z_]*\b|["'][a-z_]+["'])""", args):
                    if value[0] in "\"'":
                        resolved = value[1:-1]
                    else:
                        module = importlib.import_module(".".join(path.relative_to(APP.parent).with_suffix("").parts))
                        self.assertTrue(hasattr(module, value), f"{path.name}：预占用的 {value} 解析不出来——扫描规则要跟着改")
                        resolved = getattr(module, value)
                    (purposes if key == "purpose" else providers).add(resolved)
        self.assertGreaterEqual(purposes, {"illustration", "character", "id_photo", "life_plan"}, f"扫描规则失效了：只找到 {sorted(purposes)}")
        self.assertGreaterEqual(providers, {"image", "llm"}, f"扫描规则失效了：只找到 {sorted(providers)}")
        self.assertEqual(purposes - set(L.PURPOSE), set(), "这些用途有人在预占，后台词表里没有")
        self.assertEqual(providers - set(L.PROVIDER), set(), "这些供应商有人在预占，后台词表里没有")

    def test_brain_backoff_reasons_cover_every_writer(self):
        """AI 思考写进安静原因的 `brain:<原因>`：DecisionFailureCode 的每个值、BrainLife 退避时写死的每个原因、
        异常退避（_stall）的每个原因、对照模式的 shadow，都要有说法。"""
        from app.schemas.runtime_internal.decision import DecisionFailureCode

        life = (APP / "web_agent" / "brain_life.py").read_text(encoding="utf-8")
        wiring = (APP / "web_agent" / "brain_wiring.py").read_text(encoding="utf-8")
        backed_off = set(re.findall(r"""_back_off\(pet_id, \w+, BrainOutcome\([^)]*?reason=f?["']([a-z_]+)""", life, re.S))
        stalled = set(re.findall(r"""_stall\(projector, life, pet_id, now, ["']([a-z_]+)["']\)""", wiring))
        attempts = set(re.findall(r"""record_attempt\([^)]*reason=["']brain:([a-z_]+)["']""", life))
        self.assertGreaterEqual(backed_off, {"no_offers", "deadline_exceeded", "consent_withdrawn", "versions_changed", "offer_expired"},
                                f"扫描退避原因的规则失效了：只找到 {sorted(backed_off)}")
        self.assertEqual(stalled, {"evaluate_failed", "round_failed"})
        self.assertEqual(attempts, {"shadow"})
        written = backed_off | stalled | attempts | {code.value for code in DecisionFailureCode} | {"unknown"}
        self.assertEqual(written - set(L.BRAIN_BACKOFF), set(), "这些原因会写进安静原因，后台没有说法")

    def test_ledger_types_roles_and_permissions_match(self):
        self.assertSameCodes(L.LEDGER_TYPE, EconomyTransactionType)
        self.assertSameCodes(L.ROLE, Role)
        self.assertSameCodes(L.PERMISSION, Permission)
        self.assertSameCodes(L.SPECIES, PetSpecies)
        self.assertEqual(set(L.FINDING_KIND), set(AdminEconomyChecksRules), "对账发现的种类与 economy_checks.RULES 一一对应")

    def test_batch_eight_families_match_the_player_contract(self):
        from app.schemas.web.character import CharacterPose
        from app.schemas.web.companion_media import MediaSessionState, ParticipationMode
        from app.schemas.web.food import FoodMode, PreferenceSubject
        from app.schemas.web.journey import VenueTemplate, VisitActivityKind, VisitActivityState
        from app.schemas.web.pets import AdoptionAvailability, PetOrigin
        from app.schemas.web.social import ActorKind, FriendKind, PostVisibility
        from app.schemas.web.transport import DataFreshness, LegKind, PositionBasis, TimeBasis, TransportMode, TravellerRole

        for family, enum_cls in ((L.TRANSPORT_MODE, TransportMode), (L.LEG_KIND, LegKind), (L.TRAVELLER_ROLE, TravellerRole),
                                 (L.TIME_BASIS, TimeBasis), (L.DATA_FRESHNESS, DataFreshness), (L.POSITION_BASIS, PositionBasis),
                                 (L.VENUE_TEMPLATE, VenueTemplate), (L.VISIT_ACTIVITY, VisitActivityKind),
                                 (L.VISIT_ACTIVITY_STATE, VisitActivityState), (L.ACTOR_KIND, ActorKind), (L.FRIEND_KIND, FriendKind),
                                 (L.POST_VISIBILITY, PostVisibility), (L.MEDIA_STATE, MediaSessionState),
                                 (L.PARTICIPATION_MODE, ParticipationMode), (L.ADOPTION_AVAILABILITY, AdoptionAvailability),
                                 (L.PET_ORIGIN, PetOrigin), (L.FOOD_SUBJECT, PreferenceSubject), (L.FOOD_MODE, FoodMode),
                                 (L.CHARACTER_POSE, CharacterPose)):
            self.assertSameCodes(family, enum_cls)

    def test_content_fields_and_announcement_options_are_all_labelled(self):
        """内容页上出现的每个字段名（可发布、不可发布、预览里算出来的）都要有说法；公告的级别与范围与白名单双向相等。"""
        from app.routers.admin.content import CONTENT_TYPE_INFO
        from app.web_admin.content_types import ANNOUNCEMENT_AUDIENCES, ANNOUNCEMENT_SEVERITIES

        codes = {f for info in CONTENT_TYPE_INFO for f in info["publishable"] + info["blocked"] if re.fullmatch(r"[a-z0-9_]+", f)}
        self.assertEqual(sorted(codes - set(L.CONTENT_FIELD)), [], "这些字段名在内容页上会显示成代码")
        self.assertEqual(set(L.ANNOUNCEMENT_SEVERITY), set(ANNOUNCEMENT_SEVERITIES))
        self.assertEqual(set(L.ANNOUNCEMENT_AUDIENCE), set(ANNOUNCEMENT_AUDIENCES))

    def test_credential_kinds_follow_the_player_catalog(self):
        """证件的种类与玩家后端的目录双向相等，说法以目录里的名字开头（后台只能在后面补提示）：玩家那边改名、这里没跟上就红。"""
        from app.web_credentials.service import CATALOG

        self.assertEqual(set(L.CREDENTIAL_KIND), set(CATALOG), "证件种类与玩家后端的目录不一致")
        for kind, info in CATALOG.items():
            self.assertTrue(L.CREDENTIAL_KIND[kind].startswith(info.label), f"{kind}：后台写「{L.CREDENTIAL_KIND[kind]}」，玩家那边叫「{info.label}」")

    def test_collection_kinds_follow_every_grant_site(self):
        """藏品种类：与玩家时间线认得的种类双向相等，且源码里每一处发放藏品的写入口（_grant 的 kind=、grant_item 的第四个参数、
        明信片那条 INSERT 里写死的种类）都收录了——漏一种，后台就会在宠物页上显示「未收录」。"""
        from app.web_agent.timeline import COLLECTION_TITLE

        self.assertEqual(set(L.COLLECTION_KIND), set(COLLECTION_TITLE), "藏品种类与玩家时间线不一致")
        root = pathlib.Path(__file__).resolve().parents[1] / "app"
        granted: set[str] = set()
        for path in root.rglob("*.py"):
            if "web_admin" in path.parts:
                continue
            text = path.read_text(encoding="utf-8")
            granted.update(re.findall(r"""_grant\([^)]*?kind=["']([a-z_]+)["']""", text, re.S))
            granted.update(re.findall(r"""grant_item\(conn, [a-z_]+, [a-z_]+, ["']([a-z_]+)["']""", text))
            granted.update(re.findall(r"""INSERT[^;]*?INTO web_collection_items \([^)]*\) VALUES \(\?, \?, \?, '([a-z_]+)'""", text, re.S))
        self.assertGreaterEqual(granted, {"postcard", "badge", "seed", "shared_memory", "license_photo", "car_voucher"},
                                f"扫描发放入口的正则失效了：只找到 {sorted(granted)}")
        self.assertEqual(granted - set(L.COLLECTION_KIND), set(), "这些藏品种类有人在发，后台词表里没有")

    def test_every_family_is_served(self):
        for name, family in L.FAMILIES.items():
            self.assertTrue(family, f"{name} 是空的")
            for code, text in family.items():
                self.assertIsInstance(text, str, f"{name}.{code}")
                self.assertTrue(text.strip(), f"{name}.{code} 没有说法")


class NoInventedCodesTests(unittest.TestCase):
    """没法枚举的代码族：词表里的每个代码都得在源码里真实出现过（写成字符串字面量），不许凭印象编。"""

    FREE_FAMILIES = ("activity", "journey_lifecycle", "world_event", "illustration_status", "call_state", "task_status",
                     "reservation_status", "provider", "purpose", "task_error", "director_hold", "photo_surface",
                     "ledger_source", "ledger_status", "consent", "audit_status", "report_decision", "lane",
                     "collection_kind", "driving_stage", "character_state", "reply_reason", "reply_outcome",
                     "outbox_status", "outbox_consumer", "worker_role", "plot_state", "decided_by", "target_kind", "world_runner", "batch_item_status", "content_field",
                     "school_mode", "school_state", "search_match",
                     "heartbeat_mode", "brain_mode", "heartbeat_state", "brain_state", "rule_decision", "image_bucket",
                     "lane_state", "task_kind", "brain_backoff")

    def test_free_codes_exist_in_the_source(self):
        source = _source_without_labels()
        missing = []
        for name in self.FREE_FAMILIES:
            for code in L.FAMILIES[name]:
                # 两种写法也算真实出现：组合串的开头（`f"payload_missing:{key}"`，错误串按冒号拆开认），
                # 以及异常类名（任务队列把可以重试的异常按 type(exc).__name__ 记进错误串）
                if not re.search(r"""["']""" + re.escape(code) + r"""(?:["']|:)""", source) and \
                        not re.search(r"^\s*class " + re.escape(code) + r"\b", source, re.M):
                    missing.append(f"{name}.{code}")
        self.assertEqual(missing, [], "这些代码在 app/ 的源码里一次都没出现过——是不是编的？")

    def test_audit_actions_exist_in_the_source(self):
        """审计动作有两种拼法：字面量（"economy.grant"），以及 f"report.{decision}" / f"provider.{state}" 这种拼出来的。"""
        source = _source_without_labels()
        composed = {f"report.{d}" for d in L.REPORT_DECISION} | {"provider.active", "provider.paused"}
        self.assertIn('f"report.{decision}"', source)
        self.assertIn('f"provider.{state}"', source)
        missing = [action for action in L.AUDIT_ACTION
                   if action not in composed and not re.search(r"""["']""" + re.escape(action) + r"""["']""", source)]
        self.assertEqual(missing, [], "这些审计动作在源码里找不到")

    def test_errors_are_translated_only_when_recognised(self):
        self.assertIn("身份参考照", L.error_label("image director_hold:identity_reference_missing"))
        self.assertIn("（缺：species）", L.error_label("image director_hold:hold_missing_required:species"))
        self.assertIn("结果未确认", L.error_label("image timeout"))
        self.assertIn("没有发出", L.error_label("image daily_cap"))
        self.assertIsNone(L.error_label("image something_new"), "认不出来就是 None，界面照原样显示原始错误串")
        self.assertIn("证件照", L.error_label("id_photo photo_blank"), "证件照任务的错误写的是它自己的原因码")
        self.assertIn("贴边被裁", L.error_label("character subject_cut_off"))
        self.assertIsNone(L.error_label("image subject_cut_off"), "照片链路的错误不借角色的原因码去猜")
        self.assertIn("额度用完", L.error_label("image budget_denied"))
        self.assertIn("自动再试", L.error_label("ImageUnavailable"), "可以重试的供应商错误按异常类名记")
        self.assertIn("（缺：household_id）", L.error_label("image director_hold:payload_missing:household_id"))
        self.assertIn("还不支持", L.error_label("image director_hold:scene_not_supported"))
        self.assertEqual(L.silence_label("asleep"), "TA 在睡觉")
        self.assertEqual(L.silence_label("brain:timeout"), "AI 思考：模型超时没回")
        self.assertEqual(L.silence_label("brain:versions_changed:itinerary"), L.silence_label("brain:versions_changed"))
        self.assertEqual(L.silence_label("brain:NotEnoughStarDust"), "AI 思考：这次没想成，稍后再试",
                         "出发被规则拒绝的原因是开放集合：认不出来就说这条路径的共同事实")
        self.assertIsNone(L.silence_label("not_a_reason"))
        self.assertIsNone(L.error_label(None))
        self.assertEqual(L.reason_label("silence:asleep"), "安静原因：TA 在睡觉")
        self.assertIsNone(L.reason_label("silence:not_a_reason"))
        self.assertIn("被挡下", L.audit_action_label("denied:GET /api/v1/admin/audit"))


class CheckConstraintFamilyTests(AdminTestBase):
    """表上有 CHECK 约束的代码族：拿测试库里**实际建出来的表结构**比，不抄一份取值。"""

    def check_values(self, table: str, column: str) -> set[str]:
        with self.app.state.storage.connect() as conn:
            sql = conn.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)).fetchone()["sql"]
        match = re.search(r"CHECK\s*\(\s*" + column + r"\s+IN\s*\(([^)]*)\)\s*\)", sql)
        self.assertIsNotNone(match, f"{table}.{column} 没有 CHECK 约束了——换别的办法核对")
        return set(re.findall(r"'([^']*)'", match.group(1)))

    def test_families_match_the_table_constraints(self):
        self.assertEqual(set(L.LEG_DIRECTION), self.check_values("web_journey_legs", "direction"))
        self.assertEqual(set(L.RESIDENT_KIND), self.check_values("web_residents", "kind"))
        self.assertEqual(set(L.RESIDENT_STATUS), self.check_values("web_residents", "status"))
        self.assertEqual(set(L.BATCH_ITEM_STATUS), self.check_values("admin_grant_batch_items", "status"))
        self.assertEqual(set(L.AUDIT_STATUS), self.check_values("admin_audit", "status"))


class GlossaryRouteTests(AdminTestBase):
    def test_labels_need_a_staff_session_but_no_particular_permission(self):
        self.assertEqual(self.client.get("/api/v1/admin/labels").status_code, 401, "没有员工会话就不给")
        moderator = self.staff("glossary-moderator", ["moderator"])  # 没有 ops.read，也要能看懂自己的页面
        moderator.login_ok()
        body = moderator.get("/labels").json()
        self.assertEqual(body["families"]["world_event"]["leg_arrived"], "到达一站")
        self.assertEqual(body["families"]["role"]["moderator"], "审核")
        self.assertIn("asleep", body["silence_hints"])

    def test_staff_names_show_names_only(self):
        lead = self.staff("glossary-lead", ["economy_lead"])
        lead.login_ok()
        body = lead.get("/staff/names").json()
        self.assertEqual(body["staff"][lead.staff_id]["username"], "glossary-lead")
        self.assertEqual(set(body["staff"][lead.staff_id]), {"username", "display_name", "disabled"},
                         "只给名字与是否停用：角色、权限、登录时间仍然只在员工页")
        self.assertIn("web", body["operators"])


if __name__ == "__main__":
    unittest.main()
