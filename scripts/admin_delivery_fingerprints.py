#!/usr/bin/env python3
"""运营后台这一批交付物的指纹（给独立验收用）。

    python scripts/admin_delivery_fingerprints.py            # 打印聚合指纹
    python scripts/admin_delivery_fingerprints.py --list     # 连每个文件的 SHA256 一起打印

只覆盖本窗口新增/修改的文件。聚合值把**相对路径**一起算进去，所以改名也会变。
不含 node_modules、dist、data/ 与任何生成物。

聚合顺序＝按 POSIX 相对路径字符串排序（区分大小写，逐码位比较），与操作系统无关。
**第四批之前的版本不是这样**：它用 `sorted(Path)`，而 Windows 的路径比较不分大小写、Linux 分，
`App.tsx` / `app.css` / `api/` 三者在两边排出不同顺序——同样的字节，两边算出不同的聚合值
（2026-09-23 Linux 容器实测撞出来的）。所以第一到第三批交接里记的聚合值，只能用当时那版脚本在 Windows 上复现；
逐文件的 SHA256（`--list`）不受影响。
"""

from __future__ import annotations

import argparse
import hashlib
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
TREES = (
    "PetJourneyBackend/app/web_admin",
    "PetJourneyBackend/app/routers/admin",
    "PetJourneyBackend/app/schemas/admin",
    "PetSoulAdmin/src",
)
FILES = (
    "PetJourneyBackend/app/content_overlay.py",
    "PetJourneyBackend/app/routers/web/announcements.py",
    "PetJourneyBackend/app/web_platform/migrations/m1520_admin_grant_batches.py",
    "PetJourneyBackend/app/web_platform/legacy_guard.py",
    "PetJourneyBackend/app/web_farm/service.py",
    "PetJourneyBackend/app/web_journey/local.py",
    "PetJourneyBackend/app/web_journey/catalog.py",
    "PetJourneyBackend/app/web_platform/migrations/m1530_admin_assets.py",
    "PetJourneyBackend/app/web_platform/migrations/m1540_admin_pricing.py",
    "PetJourneyBackend/app/web_platform/migrations/m1550_admin_batch_player_note.py",
    "PetJourneyBackend/app/web_platform/migrations/m1560_admin_report_claims.py",
    "PetJourneyBackend/app/web_platform/migrations/m1570_admin_pet_maintenance.py",
    "PetJourneyBackend/app/web_platform/migrations/m1580_admin_relay_receipts.py",
    "PetJourneyBackend/app/routers/web/report_outcomes.py",
    "PetJourneyBackend/tests/test_admin_destinations.py",
    "PetJourneyBackend/tests/test_admin_assets.py",
    "PetJourneyBackend/tests/test_admin_content_types.py",
    "PetJourneyBackend/tests/test_admin_batches.py",
    "PetJourneyBackend/tests/test_admin_concurrency.py",
    "PetJourneyBackend/tests/test_admin_pet_ledgers.py",
    "PetJourneyBackend/tests/test_admin_pricing.py",
    "PetJourneyBackend/tests/test_admin_economy_checks.py",
    "PetJourneyBackend/tests/test_admin_player_notes.py",
    "PetJourneyBackend/tests/test_admin_reversals.py",
    "PetJourneyBackend/tests/test_admin_report_claims.py",
    "PetJourneyBackend/tests/test_admin_labels.py",
    "PetJourneyBackend/tests/test_admin_belongings.py",
    "PetJourneyBackend/tests/test_admin_world8.py",
    "PetJourneyBackend/tests/test_admin_runtime9.py",
    "PetJourneyBackend/tests/test_admin_review10.py",
    "PetJourneyBackend/app/web_platform/migrations/m1500_admin.py",
    "PetJourneyBackend/app/web_platform/migrations/m1510_admin_content.py",
    "PetJourneyBackend/app/web_journey/adventures.py",
    "PetJourneyBackend/app/main.py",
    "PetJourneyBackend/tests/admin_base.py",
    "PetJourneyBackend/tests/test_admin_identity.py",
    "PetJourneyBackend/tests/test_admin_diagnosis.py",
    "PetJourneyBackend/tests/test_admin_commands.py",
    "PetJourneyBackend/tests/test_admin_content.py",
    "scripts/seed_admin_demo.py",
    "PetSoulAdmin/package.json",
    "PetSoulAdmin/vite.config.ts",
    "PetSoulAdmin/index.html",
    "PetSoulAdmin/scripts/dev-backend.mjs",
)


def relative(path: pathlib.Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def collect() -> list[pathlib.Path]:
    found: dict[str, pathlib.Path] = {}
    for tree in TREES:
        root = REPO_ROOT / tree
        for p in root.rglob("*"):
            if p.is_file() and "__pycache__" not in p.parts:
                found[relative(p)] = p
    for name in FILES:
        found[pathlib.PurePosixPath(name).as_posix()] = REPO_ROOT / name
    # 显式按 POSIX 相对路径字符串排序：不依赖操作系统怎么比较路径（见模块说明）
    return [found[key] for key in sorted(found)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="运营后台交付物指纹")
    parser.add_argument("--list", action="store_true", help="逐文件打印 SHA256")
    args = parser.parse_args(argv)

    aggregate = hashlib.sha256()
    missing: list[str] = []
    counted = 0
    for path in collect():
        rel = relative(path)
        if not path.exists():
            missing.append(rel)
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        aggregate.update(rel.encode("utf-8"))
        aggregate.update(digest.encode("ascii"))
        counted += 1
        if args.list:
            print(f"{digest}  {rel}")
    print(f"files={counted}")
    print(f"aggregate_sha256={aggregate.hexdigest()}")
    for name in missing:
        print(f"MISSING {name}", file=sys.stderr)
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
