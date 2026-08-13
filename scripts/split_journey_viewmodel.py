#!/usr/bin/env python3
"""拆分 JourneyViewModel.swift（829 行 ObservableObject）为「1 主类 + 5 extension」。

与 MockPetJourneyService 拆分（split_mock_service.py）同款机械策略，但有两点关键差异：
  1. ObservableObject 的 `@Published private(set) var` 的 setter 是 `private`，Swift 中
     `private` 只在「同文件（含同文件 extension）」可见；方法拆到别的文件后无法 set。
     故须把 `private(set)` 一并去掉（setter 放宽为 internal）。`@MainActor` 仍保证
     线程隔离，外部 View 层本就只读订阅，行为无破坏。
  2. `private let/var`、`private func`、类外 `private extension Array` 同款去 private
     （internal），让跨文件 extension 可访问共享状态与 helper。

主文件保留：imports + OwnerMessageReceipt + @MainActor class 声明 + LoadState 枚举
+ 全部 @Published 状态 + 状态属性 + init + 6 个计算属性 + 类外 Array extension。
方法按领域拆到 5 个 extension：Lifecycle / Details / Communication / Travel / Souvenirs。

用法：python scripts/split_journey_viewmodel.py [--dry-run]
"""

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

SRC = Path("PetJourneyIOS/PetJourneyIOS/ViewModels/JourneyViewModel.swift")
OUT_DIR = SRC.parent

# 领域 -> 方法名（class 成员）。38 个类内方法全部列出，无重载。
DOMAINS = {
    "Lifecycle": [
        "start", "stop", "loadInitial", "refreshStatus", "markRefreshSucceeded",
        "drainOutboxIfNeeded", "hydrateDetailsFromCache", "hydrateInitialDetails",
        "refreshDetails", "markPostcardsRead", "clearToast",
    ],
    "Details": [
        "updateDNA", "generateIllustratedGuideIfNeeded", "illustratedGuideNeedsImage",
        "illustratedGuideHasImage", "refreshRoutePlan", "refreshPhotoMission",
        "hasReceivedPhotoMission", "translateLatestThought", "receiveCurrentPhoto",
        "markPhotoMissionReceived",
    ],
    "Communication": [
        "sendOwnerMessage", "sendFeedback",
        "appendOwnerMessageReceipt", "updateOwnerMessageReceipt",
    ],
    "Travel": [
        "refreshTravelTools", "createTravelQuest", "openWorldCupQuest",
        "prepareActiveTravelQuest", "packTravelBag", "attachTravelBagToQuest",
        "refreshTravelBag",
    ],
    "Souvenirs": [
        "collectSouvenirsForActiveQuest", "sellSouvenir", "archiveSouvenir",
        "refreshEconomy", "mergeSouvenirs", "replaceSouvenir",
    ],
}


def parse(lines):
    """返回 (members, class_end)。

    members = [{"start": 0based, "name": str}]，仅类体内的 4 空格缩进 func。
    class_end = 类体结束 `}` 的 0based 行号（紧跟最后一个类成员的顶层 `}`）。
    """
    class_open = next(
        i for i, l in enumerate(lines) if "final class JourneyViewModel" in l
    )
    class_end = next(
        i for i in range(class_open + 1, len(lines)) if lines[i] == "}"
    )
    members = []
    for i in range(class_open, class_end):
        m = re.match(r"^    (?:private )?func (\w+)", lines[i])
        if m:
            members.append({"start": i, "name": m.group(1)})
    return members, class_end


def method_end(lines, start_idx, next_start_idx, class_end):
    end = next_start_idx if next_start_idx is not None else class_end
    while end > start_idx and lines[end - 1].strip() == "":
        end -= 1
    return end


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    raw = SRC.read_text(encoding="utf-8")
    # 1) 全文件去 `private `（含 private func / private let / private var / private extension）
    text = re.sub(r"^(\s*)private ", r"\1", raw, flags=re.MULTILINE)
    # 2) 去 `private(set) `：@Published private(set) var -> @Published var（跨文件 extension 需 internal setter）
    text = text.replace("private(set) ", "")
    lines = text.split("\n")

    members, class_end = parse(lines)

    name_queue = defaultdict(list)
    for k, mem in enumerate(members):
        name_queue[mem["name"]].append(k)

    assignment = {}
    try:
        for domain, names in DOMAINS.items():
            idxs = [name_queue[n].pop(0) for n in names]
            assignment[domain] = sorted(idxs)
    except IndexError as e:
        raise RuntimeError(f"领域方法清单与源不匹配（某方法名出现次数不足）: {e}")

    used = sorted(i for idxs in assignment.values() for i in idxs)
    if used != list(range(len(members))):
        missing = [members[i]["name"] for i in range(len(members)) if i not in used]
        raise RuntimeError(f"成员分配不完整，缺失/未分配: {missing}")

    # 主文件：类头部 + 类结束 `}` + 类外 extension 尾
    first_member_start = members[0]["start"]
    head = lines[:first_member_start]
    while head and head[-1].strip() == "":
        head.pop()
    tail = lines[class_end + 1:]
    main_content = "\n".join(head) + "\n}\n" + "\n".join(tail).rstrip("\n") + "\n"

    files = {"JourneyViewModel.swift": main_content}

    for domain, idxs in assignment.items():
        bodies = []
        for k in idxs:
            s = members[k]["start"]
            nxt = members[k + 1]["start"] if k + 1 < len(members) else class_end
            e = method_end(lines, s, nxt, class_end)
            bodies.append("\n".join(lines[s:e]).rstrip("\n"))
        body = "\n\n".join(bodies)
        files[f"JourneyViewModel+{domain}.swift"] = (
            "import Foundation\n\n"
            "@MainActor\n"
            "extension JourneyViewModel {\n"
            + body +
            "\n}\n"
        )

    # 花括号平衡校验
    for fn, c in files.items():
        if c.count("{") != c.count("}"):
            raise RuntimeError(f"{fn} 花括号不平衡: {{={c.count('{')} }}={c.count('}')}")

    if args.dry_run:
        print("=== 计划写入的文件 ===")
        for fn, c in files.items():
            print(f"{fn:45s} {c.count(chr(10)):4d} 行")
        print(f"\n总成员 {len(members)} 个 -> {len(files)-1} 个 extension + 1 主文件")
        return 0

    for fn, c in files.items():
        (OUT_DIR / fn).write_text(c, encoding="utf-8")
    print(f"已写入 {len(files)} 个文件")
    for fn in files:
        print("  ", fn)
    return 0


if __name__ == "__main__":
    sys.exit(main())
