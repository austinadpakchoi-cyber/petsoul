#!/usr/bin/env python3
"""按顶层类型（struct/class/enum/extension）分组拆分 SwiftUI View God File。

与 split_mock_service.py / split_journey_viewmodel.py 的差异：
  - 前两者拆「单一 class 的方法」，本脚本拆「一个文件里的多个顶层类型」。
  - 目标文件是「一组完整类型块」的集合，非「extension 包裹的方法」。

关键策略（与前两者一致）：
  1. 全文件去 `private `（行首 / @属性包装器后 / private(set)），统一放宽为 internal，
     使拆到不同文件后跨文件仍可访问（同 module 内 internal 可见，行为无破坏）。
  2. 每个新文件 = 原文件 import 头 + 该组类型块（按源顺序、空行分隔）。

用法：
    python scripts/split_views.py --analyze                  # 输出每个类型的 key + 声明行号
    python scripts/split_views.py --dry-run                  # 按 PLAN 预览分组结果
    python scripts/split_views.py                            # 执行拆分并写文件

配置：本文件底部的 PLAN 字典，形如
    PLAN = {
        "Views/WelcomeView.swift": {
            "WelcomeView.swift": ["PublicWorldView", "NativeGlobeMapView", ...],
            "WorldLifeEvent.swift": ["WorldLifeEvent"],
            ...
        }
    }
   key 为类型名；同名类型（如多个 `extension Array`）用 `name#2`、`name#3` 引用第 2、3 个。
   与源文件名同名的 key 即主文件（被重写，保留列出的类型）；未列出的类型必须全部归属某个文件。
"""

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VIEWS_DIR = ROOT / "PetJourneyIOS" / "PetJourneyIOS" / "Views"

# 顶层类型声明：列首，可选访问修饰符 + final + struct/class/enum/protocol/extension/actor
TYPE_RE = re.compile(
    r"^(?:(?:public|private|internal|fileprivate|open)\s+)*(?:final\s+)?"
    r"(?:struct|class|enum|protocol|extension|actor)\s+([A-Za-z_][A-Za-z0-9_]*)"
)

# 类型声明前的属性注解行（列首 @Xxx，如 @MainActor / @Observable / @available(...)）。
# 这些属性单独一行紧贴在类型声明上方，拆分时必须随类型块一起搬走，否则丢失（如 @MainActor
# 丢失会导致隔离域改变，出现「expression is async but not marked with await」编译错误）。
ATTRIBUTE_RE = re.compile(r"^@[A-Za-z_]")


def strip_private(text: str) -> str:
    """去掉三种 private 形态，统一放宽为 internal。"""
    # 1) private(set) var -> var（setter 放宽 internal）
    text = text.replace("private(set) ", "")
    # 2) 行首（含缩进）private -> 去掉
    text = re.sub(r"^(\s*)private ", r"\1", text, flags=re.MULTILINE)
    # 3) 属性包装器后的 private（含带参数形式）：@State private / @Environment(\.k) private
    text = re.sub(r"(@[A-Za-z]+(?:\([^)]*\))?) private ", r"\1 ", text)
    return text


def brace_end(lines, start):
    """从 start 行（含类型声明）找匹配的顶层 `}` 行号。"""
    depth = 0
    started = False
    for i in range(start, len(lines)):
        for ch in lines[i]:
            if ch == "{":
                depth += 1
                started = True
            elif ch == "}":
                depth -= 1
                if started and depth == 0:
                    return i
    return len(lines) - 1


def parse_types(lines):
    """返回 [(key, start, end)]，key 为 name 或 name#N（同名按源顺序编号）。

    start 会回溯包含类型声明前紧邻（无空行）的属性注解行（@MainActor 等），
    避免拆分时把属性丢失。end 仍由声明行的花括号平衡计算得到。
    """
    types = []
    seen = Counter()
    for i, l in enumerate(lines):
        m = TYPE_RE.match(l)
        if m:
            name = m.group(1)
            seen[name] += 1
            occ = seen[name]
            key = name if occ == 1 else f"{name}#{occ}"
            end = brace_end(lines, i)
            start = i
            j = i - 1
            while j >= 0 and ATTRIBUTE_RE.match(lines[j]):
                start = j
                j -= 1
            types.append((key, start, end))
    return types


def import_head(lines):
    """第一个类型声明之前的所有行（import + 文件级注释/空行），去尾空行。"""
    idx = next((i for i, l in enumerate(lines) if TYPE_RE.match(l)), 0)
    head = lines[:idx]
    while head and head[-1].strip() == "":
        head.pop()
    return head


def type_block(lines, start, end):
    """类型块：从 start 到 end（含），去尾空行。"""
    block = lines[start:end + 1]
    while block and block[-1].strip() == "":
        block.pop()
    return block


def build_plan_keys(plan):
    """返回 plan 中引用的全部 key（含 name#N），供校验。"""
    keys = []
    for groups in plan.values():
        for names in groups.values():
            keys.extend(names)
    return keys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--analyze", action="store_true", help="输出每个类型的 key 与声明行号")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--file", help="只处理指定源文件（PLAN 中的 key）")
    args = ap.parse_args()

    plan = PLAN if not args.file else {k: v for k, v in PLAN.items() if k.endswith(args.file)}

    if args.analyze:
        for rel, _groups in plan.items():
            p = ROOT / rel
            lines = p.read_text(encoding="utf-8").split("\n")
            types = parse_types(lines)
            print(f"\n===== {rel} =====")
            for key, s, e in types:
                print(f"  {s+1:5d}  {key:32s} {e - s + 1:4d} 行")
        return 0

    for rel, groups in plan.items():
        src = ROOT / rel
        if not src.exists():
            raise RuntimeError(f"源文件不存在：{src}")
        text = strip_private(src.read_text(encoding="utf-8"))
        lines = text.split("\n")
        types = parse_types(lines)
        lookup = {key: (s, e) for key, s, e in types}
        head = import_head(lines)

        # 校验：每个引用的 key 都存在于源；所有类型都被分配且只一次
        assigned = []
        for target, keys in groups.items():
            for k in keys:
                if k not in lookup:
                    raise RuntimeError(f"{rel}: 配置引用了不存在的类型 key '{k}'")
                assigned.append(k)
        if sorted(assigned) != sorted(lookup.keys()):
            missing = set(lookup) - set(assigned)
            extra = set(assigned) - set(lookup)
            raise RuntimeError(f"{rel}: 分配不完整。未分配={sorted(missing)} 多余={sorted(extra)}")

        files = {}
        for target, keys in groups.items():
            blocks = [type_block(lines, *lookup[k]) for k in keys]
            body = "\n\n".join("\n".join(b).rstrip("\n") for b in blocks)
            files[target] = "\n".join(head) + "\n\n" + body + "\n"

        # 花括号平衡校验
        for fn, c in files.items():
            if c.count("{") != c.count("}"):
                raise RuntimeError(f"{fn} 花括号不平衡: {{={c.count('{')} }}={c.count('}')}")

        if args.dry_run:
            print(f"\n===== {rel} -> {len(files)} 文件 =====")
            for fn, c in files.items():
                print(f"  {fn:45s} {c.count(chr(10)):5d} 行")
            continue

        out_dir = src.parent
        for fn, c in files.items():
            (out_dir / fn).write_text(c, encoding="utf-8")
            print(f"  写入 {fn} ({c.count(chr(10))} 行)")

    if args.dry_run:
        print("\n(未写文件，--dry-run 模式)")
    return 0


# ===================== 拆分计划 =====================
# key = 类型名；同名类型用 name#2 / name#3 引用第 2、3 个。
# 与源文件同名的 key 为主文件（重写保留列出的类型）。
PLAN = {
    # ---------- WelcomeView.swift（1569 行 / 13 类型）→ 3 文件 ----------
    "PetJourneyIOS/PetJourneyIOS/Views/WelcomeView.swift": {
        "WelcomeView.swift": [
            "PublicWorldView", "NativeGlobeMapView", "MKMapView",
            "WorldEventDetailCard", "WorldLiveStoryTicker", "WorldPill", "WorldNoteCard",
        ],
        "WorldLifeEvent.swift": ["WorldLifeEvent", "WorldAnimalField", "WorldLifeAnnotation", "UIColor"],
        "WorldAnimalViews.swift": ["WorldAnimalBadgeView", "WorldEventAnnotationView"],
    },

    # ---------- JourneyMapView.swift（5800 行 / 67 类型）→ 11 文件 ----------
    "PetJourneyIOS/PetJourneyIOS/Views/JourneyMapView.swift": {
        "JourneyMapView.swift": ["JourneyMapView"],
        "JourneyMapLoading.swift": [
            "IntroFlightState", "JourneyLoadingView", "JourneySignalErrorCard",
            "LoadingCommunicatorGlyph", "LoadingRoutePath", "LoadingRouteDots",
            "RoutePerspective", "JourneySheet",
        ],
        "JourneyMapViewport.swift": [
            "JourneyMapViewport", "LivingJourneyMap", "JourneyRouteVisual",
            "JourneyMapAtmosphere", "NavigationScanOverlay",
        ],
        "JourneyWorldCup.swift": [
            "WorldCupInvitationTeaserCard", "WorldCupMapStatusCard", "WorldCupStadiumMarker",
            "WorldCupQuestSheetView", "WorldCupHostTile", "WorldCupBagItem",
            "WorldCupBagItemTile", "PawPassPreviewCard", "PawPassStep", "ExistingWorldCupQuestCard",
        ],
        "JourneyLiveSignal.swift": [
            "LiveSignalPanel", "SleepBreathingHalo", "SleepBreathDot",
            "SleepRestStatusCard", "SleepInfoPill", "SleepQuietHint",
        ],
        "JourneyTelemetry.swift": [
            "PixelPetActivityAnimation", "RouteStatusLine", "NavigationTelemetryStrip",
            "JourneyMusicCue", "NavigationProgressGlint", "NavigationPulseDot",
        ],
        "JourneyPetCards.swift": [
            "PetTransmissionView", "PetVisibleThoughtCard", "PetCurrentActivityCard",
            "ActivityStatusChip", "SoftSignalChip", "MapEventCard", "CompanionPetPeekCard",
        ],
        "JourneyMapMarkers.swift": [
            "JourneyEventMarker", "RouteStopMarker", "LivePetMarkerView",
            "PetMotionWake", "PetFootstepOrbit", "CompanionPetMarkerView", "FeedbackButton",
        ],
        "JourneyMapModels.swift": [
            "JourneyMapEventPhase", "JourneyMapEvent", "MerchantStop",
            "DemoCompanionPet", "JourneyActivitySnapshot",
        ],
        "JourneyDaySchedule.swift": [
            "JourneyDaySchedule", "JourneyStatus", "Array", "ScheduledTransportLeg", "String",
        ],
        "JourneyDayRecap.swift": [
            "DayRecapChapter", "DayRecapBuilder", "DayRecapView",
            "RecapControlButton", "RecapPetMarker", "RecapChapterCard", "AccountLinkSheet",
        ],
    },

    # ---------- CommunicatorViews.swift（4445 行 / 66 类型）→ 8 文件 ----------
    "PetJourneyIOS/PetJourneyIOS/Views/CommunicatorViews.swift": {
        "CommunicatorViews.swift": [
            "JourneyHomeTabs", "CommunicatorViewModel", "CommunicatorHomeView",
            "CommunicatorEntryCard", "CommunicatorCompactEntry", "CommunicatorSignalChip",
            "CommunicatorPreviewPanel",
        ],
        "CommunicatorChat.swift": [
            "PetChatView", "ChatStatusStrip", "ChatTimeSeparator", "PetChatAvatar",
            "ChatEmptyState", "CommunicatorMessageRow", "String", "Date",
            "CommunicatorAttachmentView", "CommunicatorPhotoAttachmentView",
        ],
        "CommunicatorMoments.swift": [
            "MomentsView", "MomentCard", "CommunicatorMoment",
            "CommunicatorAttachment", "MomentSocialReactorRow",
        ],
        "MemoryHub.swift": [
            "MemoryArchiveHighlight", "MemoryHubViewModel", "MemoryHubView",
            "MemoryMomentArchiveView", "MemoryEditorValues", "MemoryEditorDraft",
            "MemoryArchiveFilter",
        ],
        "MemoryEditor.swift": [
            "EditableMemoryArchiveView", "MemoryArchiveFilterChip", "MemoryArchiveEmptyState",
            "MemoryArchiveSummaryCard", "EditableMemoryCard", "MemoryChip", "MemorySignalBar",
            "MemoryEditorSheet", "SliderValueRow", "MemoryOverviewCard", "MemoryStatTile",
            "MemoryLatestRow",
        ],
        "PetCredentialModels.swift": [
            "PetCredentialCategory", "PetCredentialPhotoRole", "PetCredentialKind",
            "PetSoulCredentialProfile", "PetCredentialSnapshot", "PetCredentialPromptTemplate",
        ],
        "PetCredentialWallet.swift": [
            "PetCredentialWalletView", "WalletCardDetailView", "CredentialPortraitArchiveSection",
            "CredentialPhotoArchivePreview", "CredentialPassportPhotoPattern",
            "CredentialPhotoAssetTile", "PetCredentialPortraitViewer",
        ],
        "PetCredentialCard.swift": [
            "WalletProgressPill", "CredentialWalletTile", "CredentialComingSoonTile",
            "PetCredentialCard", "CredentialCardTexture", "CredentialPetPhoto",
            "CredentialPortraitGlyph", "CredentialTinyField", "CredentialSeal",
            "CredentialDetailPanel", "CredentialActionLabel", "CredentialInfoTile",
        ],
    },

    # ---------- SecondaryViews.swift（4331 行 / 75 类型）→ 9 文件 ----------
    "PetJourneyIOS/PetJourneyIOS/Views/SecondaryViews.swift": {
        "SecondaryViews.swift": [
            "JourneyChapterMode", "DayPlanSheetView", "IllustratedGuideCard",
            "IllustratedGuidePageCard", "IllustratedGuideImagePlaceholder",
            "IllustratedGuideTurnButton", "IllustratedGuidePageDots",
        ],
        "IllustratedGuidePreview.swift": [
            "IllustratedGuidePreviewStop", "IllustratedGuidePreviewCanvas",
            "IllustratedGuideSpiralBinding", "IllustratedGuideSketchStamp",
            "IllustratedGuideMiniScene", "IllustratedGuideWindingPath",
            "IllustratedGuidePreviewStopRow",
        ],
        "JourneyGuideDigest.swift": [
            "JourneyDateStrip", "JourneyDateChipModel", "JourneyDateChip", "PetGuideDigest",
            "GuideDigestMetric", "GuideDigestStop", "GuideDigestMoment",
        ],
        "JourneyChapter.swift": [
            "JourneyChapterHeroCard", "FlowChipRow", "ChapterActionButton",
            "JourneyChapterModePicker", "CurrentJourneyMomentCard", "JourneyCoreRouteCard",
            "JourneyCoreStopRow", "JourneySelectedMomentsCard", "JourneyMomentRow",
        ],
        "TravelGuide.swift": [
            "PracticalGuideCard", "PracticalStopListCard", "Array", "TravelGuideDigestCard",
            "GuideDigestMetricChip", "GuideDigestRoutePreview", "GuideDigestStopRow",
            "RouteMovementDisclosureCard", "DayPlanItem", "JourneyPlanOverviewCard",
            "RouteSegmentRow",
        ],
        "TravelViews.swift": [
            "PostcardsView", "TravelKitSheetView", "SouvenirsView", "EconomySummaryCard",
            "EconomyMetricTile", "TravelWishComposer", "TravelQuestCard",
            "TravelQuestGuideSnapshot", "TravelQuestGuidePill", "TravelQuestStopRow",
        ],
        "TravelBagSouvenir.swift": [
            "TravelBagCard", "TravelBagItemChip", "TravelBagItemType", "TravelBagPreset",
            "SouvenirItemType", "SouvenirCard", "SouvenirValuePill",
        ],
        "DNASettings.swift": [
            "DNASettingsView", "DNAEditableField", "DNAEditableListField",
            "PetGuideSummaryCard", "GuideInfoChip", "DNAField", "DNAListField",
        ],
        "JourneyTimeline.swift": [
            "DayPlanTimelinePhase", "TimelineItemView", "TimelineEventCard", "TransportLegCard",
            "PostcardCard", "PostcardImageView", "DayPlanItem#2", "EmptyStateView",
            "String", "Array#2",
        ],
    },
}


if __name__ == "__main__":
    sys.exit(main())
