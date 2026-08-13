#!/usr/bin/env python3
"""拆分 MockPetJourneyService.swift 为「主类 + 9 个 extension + demo 数据」共 10 个文件。

策略（与 PetModels.swift 拆分一致，机械、可校验）：
  1. 全文件 `private ` -> 去关键字（默认 internal），让跨文件 extension 可访问共享状态与 helper。
  2. 主文件保留：import + @MainActor + class 声明 + 3 个嵌套 struct + 15 个状态 var + 1 个 let + cities，
     以及类外 3 个 demo 声明（TravelQuest.with / MockDemoMedia / PetDNA.demoFrenchie）。
  3. 其余方法按领域切成 9 个 extension 文件，每个文件 <800 行。
  4. 校验：9 个 extension 文件的成员集合与「源类内成员」多重集完全一致，零丢失/重复；
     每个输出文件花括号平衡。

用法：python scripts/split_mock_service.py [--dry-run]
"""

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

SRC = Path("PetJourneyIOS/PetJourneyIOS/Services/MockPetJourneyService.swift")
OUT_DIR = SRC.parent

# 领域 -> 方法名（class 成员，不含 TravelQuest.with，它是类外扩展）。
# 同名重载（clamped Int/Double）按出现次数列出两次，脚本按源文件顺序依次消费。
DOMAINS = {
    "Core": [
        "ensureJourneyExists", "identityMemory", "refreshIdentityMemory", "makeMemory",
        "appendMemory", "ensureMemorySeed", "advanceJourney", "appendThought",
        "agentThought", "animalSpeech", "wave", "clamped", "clamped", "nonEmpty",
        "cityFor", "statusFor", "simulateElapsedTime",
        "registerPushDevice", "unregisterPushDevice", "fetchNotifications",
    ],
    "Pet": [
        "createPet", "fetchAgentStatus", "fetchDayPlan", "fetchDNA", "updateDNA",
        "fetchCityPosition", "signInWithApple", "claimPet", "mockClaimedPets",
    ],
    "Journey": [
        "fetchJourneyPlan", "fetchWorldSnapshot", "mockTimeline", "mockCurrentStop",
        "mockNextStop", "mockPlannedDate", "mockPlaces", "safeMockPlaces",
        "itineraryStop", "mockDestination", "fetchPhotoMission", "fetchCredentialPrompts",
        "fetchStreetRank", "fetchRoutePlan",
    ],
    "Guide": [
        "fetchPetGuide", "fetchIllustratedGuide", "generateIllustratedGuide",
        "mockIllustratedGuideLabel", "mockUserFacingText", "mockIllustratedGuidePages",
        "illustratedGuideLabel", "makeMockTravelGuide",
    ],
    "TravelQuest": [
        "fetchTravelQuests", "createTravelQuest", "prepareTravelQuest",
        "buildTravelQuestPostEventOptions", "selectTravelQuestNextStep",
    ],
    "Economy": [
        "fetchSouvenirs", "fetchEconomy", "fetchInventory",
        "collectTravelQuestSouvenirsWithEconomy", "collectTravelQuestSouvenirs",
        "sellItem", "archiveItem", "mockSouvenirSeeds", "mockBagSouvenirHint",
        "mockEconomyResponse", "mockWallet", "mockOwnerFund", "mockSnapshot",
        "mockExistingTransaction", "mockTransaction", "replaceSouvenir",
        "mockMarketValue", "mockBaseValue", "mockRarityMultiplier", "mockSouvenirImagePrompt",
    ],
    "TravelBag": [
        "fetchTravelBag", "packTravelBag", "mockText", "travelBagKey",
        "emptyTravelBag", "travelBagNote",
    ],
    "Communicator": [
        "fetchCommunicatorMessages", "sendCommunicatorMessage", "sendCommunicatorPhoto",
        "fetchMoments", "reactToMoment", "sendOwnerMessage", "sendFeedback",
        "fetchThoughtTranslation", "mockIntent", "mockReplyPolicy", "mockAttachments",
        "mockCommunicatorReply", "mockGeneralCommunicatorReply", "mockOwnerPhotoReply",
        "persistMockCommunicatorPhoto", "mockSceneFeeling", "seedMoments",
        "insertMockMomentIfNeeded", "mockSocialReactors", "mockReactionCounts",
    ],
    "Memory": [
        "fetchMemories", "addMemory", "updateMemory", "deleteMemory", "searchMemories",
        "generateSelfie",
    ],
}


def parse(lines):
    """返回 (members, class_end)。

    members = [{"start": 0based, "name": str}]，仅类体内的 4 空格缩进 func。
    class_end = 类体结束 `}` 的 0based 行号（紧跟最后一个类成员的顶层 `}`）。
    """
    class_open = next(
        i for i, l in enumerate(lines) if "final class MockPetJourneyService" in l
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
    text = re.sub(r"^(\s*)private ", r"\1", raw, flags=re.MULTILINE)
    lines = text.split("\n")

    members, class_end = parse(lines)

    # name -> 队列（源顺序的成员下标），用于按序消费同名重载
    name_queue = defaultdict(list)
    for k, mem in enumerate(members):
        name_queue[mem["name"]].append(k)

    # 领域 -> 成员下标列表（按源顺序）
    assignment = {}
    try:
        for domain, names in DOMAINS.items():
            idxs = [name_queue[n].pop(0) for n in names]
            assignment[domain] = sorted(idxs)
    except IndexError as e:
        raise RuntimeError(f"领域方法清单与源不匹配（某方法名出现次数不足）: {e}")

    # 校验：所有成员恰好被分配一次
    used = sorted(i for idxs in assignment.values() for i in idxs)
    if used != list(range(len(members))):
        missing = [members[i]["name"] for i in range(len(members)) if i not in used]
        raise RuntimeError(f"成员分配不完整，缺失/未分配: {missing}")

    # 主文件：类头部 + 类结束 `}` + 类外 demo 尾
    first_member_start = members[0]["start"]
    head = lines[:first_member_start]
    while head and head[-1].strip() == "":
        head.pop()
    tail = lines[class_end + 1:]  # demo 声明（跳过类结束 `}`，下面显式补齐）
    main_content = "\n".join(head) + "\n}\n" + "\n".join(tail).rstrip("\n") + "\n"

    files = {"MockPetJourneyService.swift": main_content}

    for domain, idxs in assignment.items():
        bodies = []
        for k in idxs:
            s = members[k]["start"]
            nxt = members[k + 1]["start"] if k + 1 < len(members) else class_end
            e = method_end(lines, s, nxt, class_end)
            bodies.append("\n".join(lines[s:e]).rstrip("\n"))
        body = "\n\n".join(bodies)
        files[f"MockPetJourneyService+{domain}.swift"] = (
            "import Foundation\n\n"
            "@MainActor\n"
            "extension MockPetJourneyService {\n"
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
