"""runtime-internal 共享类型的边界：只用标准库、不进网页契约、构造时拒绝缺权限元数据的值。"""

import ast
import sys
import unittest
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from pathlib import Path

import app.schemas.runtime_internal as ri
from app.schemas.runtime_internal import (
    AudienceScope,
    BrainProposal,
    HeartbeatAction,
    LostClaim,
    StaleClaim,
    Versions,
)

PACKAGE_DIR = Path(ri.__file__).parent
REPO_ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 9, 22, 16, 0, tzinfo=timezone.utc)


def _versions(**changes) -> Versions:
    base = {"runtime_epoch": 1, "activity_epoch": 4, "dna_version": 2, "privacy_epoch": 0, "membership_epoch": 3, "itinerary_version": None}
    return Versions(**{**base, **changes})


class RuntimeInternalBoundaryTests(unittest.TestCase):
    def test_every_export_resolves_and_version_is_set(self) -> None:
        self.assertEqual(ri.RUNTIME_INTERNAL_VERSION, "0.1.1")
        missing = [name for name in ri.__all__ if not hasattr(ri, name)]
        self.assertEqual(missing, [])

    def test_modules_import_only_stdlib_or_siblings(self) -> None:
        for path in PACKAGE_DIR.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.level == 0:
                    roots = [node.module.split(".")[0]]
                elif isinstance(node, ast.Import):
                    roots = [alias.name.split(".")[0] for alias in node.names]
                else:
                    continue
                for root in roots:
                    self.assertTrue(root == "__future__" or root in sys.stdlib_module_names, f"{path.name} 引入了非标准库 {root}")

    def test_not_part_of_public_web_contract(self) -> None:
        import app.schemas as schemas
        import app.schemas.web as web

        for name in ("HeartbeatDecision", "BrainProposal", "TaskClaim", "DecisionContext"):
            self.assertFalse(hasattr(schemas, name), f"app.schemas 不应导出 {name}")
            self.assertFalse(hasattr(web, name), f"app.schemas.web 不应导出 {name}")
        generated = REPO_ROOT / "PetJourneyWeb" / "src" / "shared" / "contracts" / "generated.ts"
        if generated.exists():
            self.assertNotIn("HeartbeatDecision", generated.read_text(encoding="utf-8"))


class RuntimeInternalValueTests(unittest.TestCase):
    def test_stale_fields_names_what_changed(self) -> None:
        seen = _versions()
        self.assertEqual(seen.stale_fields(_versions()), ())
        self.assertEqual(seen.stale_fields(_versions(activity_epoch=5, membership_epoch=4)), ("activity_epoch", "membership_epoch"))
        self.assertEqual(seen.stale_fields(_versions(itinerary_version=7)), (), "没有依赖行程的提案不因改签失效")
        self.assertEqual(_versions(itinerary_version=6).stale_fields(_versions(itinerary_version=7)), ("itinerary_version",))

    def test_audience_without_ids_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            AudienceScope("household")
        with self.assertRaises(ValueError):
            AudienceScope("private", household_id="hh-1")
        self.assertEqual(AudienceScope("public").kind, "public")
        self.assertEqual(AudienceScope("private", user_id="u-1").user_id, "u-1")

    def test_proposal_is_offer_or_continue_never_both(self) -> None:
        seen = _versions()
        BrainProposal("op-1", seen, "model", "先去打工攒钱", selected_offer_id="offer-work", model_ref="deepseek:deepseek-chat")
        BrainProposal("op-2", seen, "rule_fallback", "继续在家休息", continue_current=True)
        with self.assertRaises(ValueError):
            BrainProposal("op-3", seen, "model", "两个都要", selected_offer_id="offer-work", continue_current=True)
        with self.assertRaises(ValueError):
            BrainProposal("op-4", seen, "model", "什么都没选")

    def test_values_are_frozen(self) -> None:
        seen = _versions()
        with self.assertRaises(FrozenInstanceError):
            seen.dna_version = 9  # type: ignore[misc]

    def test_stale_claim_carries_the_lost_claim(self) -> None:
        lost = LostClaim("task-1", 2, "taken_over", current_status="running", current_generation=3)
        with self.assertRaises(StaleClaim) as caught:
            raise StaleClaim(lost)
        self.assertIs(caught.exception.lost, lost)

    def test_heartbeat_actions_match_contract_names(self) -> None:
        self.assertEqual([action.name for action in HeartbeatAction], ["CONTINUE", "APPLY_RULE", "REQUEST_BRAIN", "DEFER", "RECOVER"])


if __name__ == "__main__":
    unittest.main()
