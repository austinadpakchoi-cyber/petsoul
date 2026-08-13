import SwiftUI
import UIKit

struct JourneyDateStrip: View {
    var activeDate: Date
    var city: String

    var days: [JourneyDateChipModel] {
        let calendar = Calendar.current
        return [
            JourneyDateChipModel(
                date: calendar.date(byAdding: .day, value: -1, to: activeDate) ?? activeDate,
                title: "昨天",
                subtitle: "已归档",
                isActive: false
            ),
            JourneyDateChipModel(
                date: activeDate,
                title: "今天",
                subtitle: city,
                isActive: true
            ),
            JourneyDateChipModel(
                date: calendar.date(byAdding: .day, value: 1, to: activeDate) ?? activeDate,
                title: "明天",
                subtitle: "准备中",
                isActive: false
            )
        ]
    }

    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                ForEach(days) { day in
                    JourneyDateChip(day: day)
                }
            }
            .padding(.vertical, 2)
        }
        .accessibilityLabel("按日期查看旅程")
    }
}

struct JourneyDateChipModel: Identifiable {
    var date: Date
    var title: String
    var subtitle: String
    var isActive: Bool

    var id: String {
        "\(title)-\(date.timeIntervalSince1970)"
    }

    var dateText: String {
        date.formatted(.dateTime.month().day())
    }
}

struct JourneyDateChip: View {
    var day: JourneyDateChipModel

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(spacing: 5) {
                Text(day.title)
                    .font(.caption.weight(.bold))
                Text(day.dateText)
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(day.isActive ? DesignTokens.sage : DesignTokens.secondaryInk)
            }

            Text(day.subtitle)
                .font(.caption2.weight(.semibold))
                .foregroundStyle(day.isActive ? DesignTokens.ink : DesignTokens.secondaryInk)
                .lineLimit(1)
        }
        .foregroundStyle(day.isActive ? DesignTokens.ink : DesignTokens.secondaryInk)
        .padding(.vertical, 9)
        .padding(.horizontal, 12)
        .frame(minWidth: 112, alignment: .leading)
        .background(day.isActive ? DesignTokens.mist.opacity(0.78) : DesignTokens.surface.opacity(0.56))
        .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .stroke(day.isActive ? DesignTokens.sage.opacity(0.24) : DesignTokens.softLine, lineWidth: 1)
        }
    }
}

struct PetGuideDigest {
    var city: String
    var petName: String
    var title: String
    var summary: String
    var routeTheme: String
    var routeBadge: String
    var durationText: String
    var transportText: String
    var distanceText: String
    var postcardHint: String?
    var openingThought: String
    var qualityScore: Double?
    var isReplicableRoute: Bool?
    var qualityNotes: [String]
    var metrics: [GuideDigestMetric]
    var stops: [GuideDigestStop]
    var ownerTips: [String]

    static func make(dayPlan: DayPlan?, journeyPlan: JourneyPlan?, guide: PetAuthoredGuide?) -> PetGuideDigest? {
        let city = guide?.city ?? journeyPlan?.city ?? dayPlan?.location ?? "旅程"
        let stops = makeStops(dayPlan: dayPlan, journeyPlan: journeyPlan, guide: guide)
        guard !stops.isEmpty || journeyPlan != nil || guide != nil else { return nil }

        let totalDwell = guide?.guideStops.map(\.dwellMinutes).reduce(0, +) ?? stops.compactMap(\.dwellMinutes).reduce(0, +)
        let routeSeconds = journeyPlan?.routeSegments.compactMap(\.durationSeconds).reduce(0, +) ?? 0
        let transportModes = transportSummary(journeyPlan: journeyPlan, guide: guide)
        let distanceText = distanceSummary(journeyPlan: journeyPlan)
        let durationText = durationSummary(dwellMinutes: totalDwell, routeSeconds: routeSeconds)
        let sourceText = sourceSummary(guide: guide, journeyPlan: journeyPlan)
        let summaryText = (guide?.translation ?? journeyPlan?.summary ?? dayPlan?.stayDuration ?? "TA 会把今天走过的地方整理成一份可以参考的路线。").petSoulUserFacingText
        let petName = petName(from: guide?.title)

        let metrics = [
            GuideDigestMetric(title: "核心停靠", value: "\(max(1, stops.count)) 处", systemImage: "mappin.and.ellipse"),
            GuideDigestMetric(title: "预计", value: durationText, systemImage: "clock"),
            GuideDigestMetric(title: "交通", value: transportModes, systemImage: "arrow.triangle.swap"),
            GuideDigestMetric(title: "距离", value: distanceText, systemImage: "point.topleft.down.curvedto.point.bottomright.up")
        ]

        return PetGuideDigest(
            city: city,
            petName: petName,
            title: guide?.title ?? "\(city) 一日慢游攻略",
            summary: summaryText,
            routeTheme: guide?.routeTheme ?? journeyPlan?.transportDecision.reason.petSoulUserFacingText ?? "慢慢走、认真停留，不把旅程变成赶路。",
            routeBadge: routeBadge(city: city, stops: stops, isReplicableRoute: guide?.isReplicableRoute),
            durationText: durationText,
            transportText: transportModes,
            distanceText: distanceText,
            postcardHint: journeyPlan?.nextPostcardHint?.petSoulUserFacingText,
            openingThought: openingThought(summary: summaryText, routeTheme: guide?.routeTheme ?? journeyPlan?.transportDecision.reason),
            qualityScore: guide?.qualityScore,
            isReplicableRoute: guide?.isReplicableRoute,
            qualityNotes: guide?.qualityNotes ?? [],
            metrics: metrics,
            stops: stops,
            ownerTips: ownerTips(dayPlan: dayPlan, journeyPlan: journeyPlan, guide: guide, sourceText: sourceText)
        )
    }

    static func makeStops(dayPlan: DayPlan?, journeyPlan: JourneyPlan?, guide: PetAuthoredGuide?) -> [GuideDigestStop] {
        if let guide, !guide.guideStops.isEmpty {
            let visibleStops = guide.guideStops.filter { $0.isUserVisible != false && $0.isCore != false }
            return visibleStops.prefix(5).enumerated().map { index, stop in
                GuideDigestStop(
                    id: stop.id,
                    index: index + 1,
                    time: stop.plannedTime ?? "--:--",
                    name: stop.name,
                    note: stop.petReason.petSoulPetVoiceText,
                    dwellMinutes: stop.dwellMinutes,
                    role: stop.role,
                    tags: stopTags(category: stop.category, role: stop.role, dwellMinutes: stop.dwellMinutes, canPhoto: stop.photoURL != nil, canPostcard: index == visibleStops.prefix(5).count - 1),
                    systemImage: categoryIcon(stop.category),
                    tint: categoryTint(stop.category)
                )
            }
        }

        if let journeyPlan, !journeyPlan.stops.isEmpty {
            return journeyPlan.stops.prefix(5).enumerated().map { index, stop in
                GuideDigestStop(
                    id: stop.id,
                    index: index + 1,
                    time: stop.plannedTime ?? "--:--",
                    name: stop.name,
                    note: stop.detail.petSoulPetVoiceText,
                    dwellMinutes: stop.dwellMinutes,
                    role: nil,
                    tags: stopTags(category: stop.category, role: nil, dwellMinutes: stop.dwellMinutes, canPhoto: stop.photoCandidate, canPostcard: stop.postcardCandidate),
                    systemImage: categoryIcon(stop.category),
                    tint: categoryTint(stop.category)
                )
            }
        }

        return (dayPlan?.items ?? []).prefix(5).enumerated().map { index, item in
            GuideDigestStop(
                id: item.id,
                index: index + 1,
                time: item.time,
                name: item.title,
                note: item.detail.petSoulPetVoiceText,
                dwellMinutes: nil,
                role: nil,
                tags: dayPlanTags(item.kind),
                systemImage: item.kind.systemImage,
                tint: item.kind.tint
            )
        }
    }

    var chapterTitle: String {
        if petName == "TA" {
            return "TA 在 \(city) 慢慢生活的一天"
        }
        return "\(petName)在\(city)慢慢生活的一天"
    }

    var chapterSubtitle: String {
        let trimmedTheme = routeTheme.petSoulUserFacingText
        if !trimmedTheme.isEmpty {
            return trimmedTheme
        }
        return "不赶路，认真停下来，把这座城市慢慢看一遍。"
    }

    var metaChips: [String] {
        [
            "\(city) · 第 1 天",
            "\(max(1, stops.count)) 个停靠",
            "约 \(durationText)",
            transportText
        ]
    }

    var routeLine: String {
        stops.map(\.shortName).joined(separator: " → ")
    }

    var currentStop: GuideDigestStop? {
        guard !stops.isEmpty else { return nil }
        let nowMinute = Date().petSoulMinuteOfDay
        let timedStops = stops.compactMap { stop -> (GuideDigestStop, Int) in
            (stop, Self.minuteOfDay(from: stop.time) ?? 0)
        }
        if let first = timedStops.first, nowMinute < first.1 {
            return first.0
        }
        return timedStops.last(where: { $0.1 <= nowMinute })?.0 ?? stops.first
    }

    var currentStageText: String {
        guard let currentStop else { return "正在同步" }
        let nowMinute = Date().petSoulMinuteOfDay
        guard let start = Self.minuteOfDay(from: currentStop.time) else {
            return "正在停留"
        }
        if nowMinute < start {
            return "准备开始"
        }
        let end = start + (currentStop.dwellMinutes ?? 45)
        if nowMinute < start + 10 {
            return "刚刚到达"
        }
        if nowMinute <= end {
            return "正在停留"
        }
        if currentStop.index == stops.count {
            return "慢慢收尾"
        }
        return "准备下一站"
    }

    var memoryMoments: [GuideDigestMoment] {
        var moments: [GuideDigestMoment] = [
            GuideDigestMoment(
                title: "TA 刚刚想了想",
                detail: openingThought,
                systemImage: "sparkles",
                tint: DesignTokens.clay
            )
        ]

        if let photoStop = stops.first(where: { $0.tags.contains("可拍照") }) {
            moments.append(
                GuideDigestMoment(
                    title: "TA 可能会拍一张",
                    detail: "\(photoStop.shortName) 的这一刻会更适合留成照片。",
                    systemImage: "camera.fill",
                    tint: DesignTokens.dusk
                )
            )
        }

        if let postcardHint, !postcardHint.isEmpty {
            moments.append(
                GuideDigestMoment(
                    title: "今天可能会写成一封小信",
                    detail: postcardHint,
                    systemImage: "mail.stack.fill",
                    tint: DesignTokens.amber
                )
            )
        } else if let postcardStop = stops.last(where: { $0.tags.contains("明信片") }) {
            moments.append(
                GuideDigestMoment(
                    title: "今天可能会写成一封小信",
                    detail: "如果傍晚的风刚好，TA 会从 \(postcardStop.shortName) 把这一天寄回来。",
                    systemImage: "mail.stack.fill",
                    tint: DesignTokens.amber
                )
            )
        }

        return Array(moments.prefix(3))
    }

    static func petName(from title: String?) -> String {
        guard let title else { return "TA" }
        let compact = title
            .replacingOccurrences(of: " ", with: "")
            .replacingOccurrences(of: "　", with: "")
        for marker in ["的", "在", "今天"] {
            if let range = compact.range(of: marker) {
                let candidate = String(compact[..<range.lowerBound])
                if !candidate.isEmpty, candidate.count <= 8 {
                    return candidate
                }
            }
        }
        return "TA"
    }

    static func openingThought(summary: String, routeTheme: String?) -> String {
        let candidates = [
            summary,
            routeTheme?.petSoulUserFacingText,
            "我会先替你慢慢走一遍，把值得停下来的地方记下来。"
        ]
        for candidate in candidates.compactMap({ $0 }) {
            let trimmed = candidate.petSoulPetVoiceText
            if !trimmed.isEmpty {
                return String(trimmed.prefix(92))
            }
        }
        return "我会先替你慢慢走一遍，把值得停下来的地方记下来。"
    }

    static func stopTags(category: String, role: String?, dwellMinutes: Int?, canPhoto: Bool, canPostcard: Bool) -> [String] {
        var tags: [String] = []
        if let dwellMinutes {
            tags.append("停留 \(dwellMinutes) 分钟")
        }
        switch role ?? category {
        case "food_anchor":
            tags.append("本地味道")
        case "photo_anchor":
            tags.append("照片点")
        case "memory_anchor":
            tags.append("会留下记忆")
        case "rest_stop":
            tags.append("休息停靠")
        case "food":
            tags.append("本地味道")
        case "cafe":
            tags.append("适合坐一会儿")
        case "park":
            tags.append("适合开场")
        case "beach":
            tags.append("海边")
        case "shop":
            tags.append("可逛小店")
        default:
            tags.append("慢慢看看")
        }
        if canPhoto {
            tags.append("可拍照")
        }
        if canPostcard {
            tags.append("明信片")
        }
        return Array(tags.prefix(3))
    }

    static func dayPlanTags(_ kind: DayPlanItem.Kind) -> [String] {
        switch kind {
        case .morning:
            ["适合开场"]
        case .noon:
            ["补给", "休息"]
        case .afternoon:
            ["可拍照"]
        case .evening:
            ["明信片", "收尾"]
        }
    }

    static func minuteOfDay(from time: String) -> Int? {
        let parts = time.split(separator: ":")
        guard parts.count == 2, let hour = Int(parts[0]), let minute = Int(parts[1]) else {
            return nil
        }
        return hour * 60 + minute
    }

    static func transportSummary(journeyPlan: JourneyPlan?, guide: PetAuthoredGuide?) -> String {
        let modes = ((journeyPlan?.routeSegments.map(\.mode) ?? []) + (guide?.scheduledTransport.map(\.mode) ?? []))
            .filter { $0 != .stay && $0 != .checkIn }
        var seen = Set<String>()
        let names = modes.map(\.displayName).filter { seen.insert($0).inserted }
        return names.isEmpty ? "步行" : names.prefix(3).joined(separator: " + ")
    }

    static func distanceSummary(journeyPlan: JourneyPlan?) -> String {
        let meters = journeyPlan?.routeSegments.compactMap(\.distanceMeters).reduce(0, +) ?? 0
        guard meters > 0 else { return "按地图同步" }
        if meters >= 1_000 {
            return String(format: "%.1f km", Double(meters) / 1_000)
        }
        return "\(meters) m"
    }

    static func durationSummary(dwellMinutes: Int, routeSeconds: Int) -> String {
        let totalMinutes = max(30, dwellMinutes + routeSeconds / 60)
        if totalMinutes < 60 {
            return "\(totalMinutes) 分钟"
        }
        let hours = totalMinutes / 60
        let minutes = totalMinutes % 60
        return minutes == 0 ? "\(hours) 小时" : "\(hours)h \(minutes)m"
    }

    static func sourceSummary(guide: PetAuthoredGuide?, journeyPlan: JourneyPlan?) -> String {
        if let guide {
            return "\(guide.guideStops.count) 个核心停靠"
        }
        if let count = journeyPlan?.places.count {
            return "\(count) 个地图点"
        }
        return "通讯器整理"
    }

    static func routeBadge(city: String, stops: [GuideDigestStop]) -> String {
        return routeBadge(city: city, stops: stops, isReplicableRoute: nil)
    }

    static func routeBadge(city: String, stops: [GuideDigestStop], isReplicableRoute: Bool?) -> String {
        if let isReplicableRoute {
            return isReplicableRoute ? "可参考" : "TA 的路线"
        }
        let names = stops.map(\.name).joined(separator: " ")
        let hasCityAnchor = ["八市", "沙坡尾", "环岛路", "白城", "白鹭洲", "筼筜湖", "鼓浪屿", "山海"]
            .filter { names.contains($0) }
            .count >= 2
        if city == "厦门", hasCityAnchor, (4...6).contains(stops.count) {
            return "可参考"
        }
        return "TA 的路线"
    }

    static func ownerTips(dayPlan: DayPlan?, journeyPlan: JourneyPlan?, guide: PetAuthoredGuide?, sourceText: String) -> [String] {
        var tips: [String] = []
        tips.append("这条线可以当作慢游参考，不需要完全复制 TA 的节奏。")
        if let firstMode = journeyPlan?.transportDecision.selectedMode {
            tips.append("主要交通方式：\(firstMode.displayName)。远一点的路段再看地图决定是否打车。")
        }
        tips.append("照片和明信片会从真实停靠点慢慢补回来。")
        if let note = guide?.autonomyNote.petSoulUserFacingText, !note.isEmpty {
            tips.append(note)
        }
        var seen = Set<String>()
        return tips
            .map { $0.petSoulUserFacingText }
            .filter { !$0.isEmpty && seen.insert($0).inserted }
            .prefix(3)
            .map { $0 }
    }

    static func categoryIcon(_ category: String) -> String {
        switch category {
        case "food": "fork.knife"
        case "cafe": "cup.and.saucer.fill"
        case "shop": "basket.fill"
        case "netcafe": "desktopcomputer"
        case "flower": "camera.macro"
        case "park": "tree.fill"
        case "place": "figure.walk"
        case "beach": "water.waves"
        default: "mappin.and.ellipse"
        }
    }

    static func categoryTint(_ category: String) -> Color {
        switch category {
        case "food", "shop": DesignTokens.amber
        case "cafe", "park", "place", "beach": DesignTokens.sage
        case "netcafe": DesignTokens.dusk
        case "flower": DesignTokens.clay
        default: DesignTokens.sage
        }
    }
}

struct GuideDigestMetric: Identifiable {
    var id: String { "\(title)-\(value)" }
    var title: String
    var value: String
    var systemImage: String
}

struct GuideDigestStop: Identifiable {
    var id: String
    var index: Int
    var time: String
    var name: String
    var note: String
    var dwellMinutes: Int?
    var role: String?
    var tags: [String]
    var systemImage: String
    var tint: Color

    var shortName: String {
        let separators = [" / ", "·", "（", "("]
        for separator in separators {
            if let range = name.range(of: separator) {
                return String(name[..<range.lowerBound]).trimmingCharacters(in: .whitespacesAndNewlines)
            }
        }
        return name
    }
}

struct GuideDigestMoment: Identifiable {
    var id: String { "\(title)-\(detail)" }
    var title: String
    var detail: String
    var systemImage: String
    var tint: Color
}
