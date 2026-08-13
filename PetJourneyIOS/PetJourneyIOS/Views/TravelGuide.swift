import SwiftUI
import UIKit

struct PracticalGuideCard: View {
    var digest: PetGuideDigest

    var body: some View {
        SoftCard {
            Label("我也想照着走", systemImage: "figure.walk")
                .font(.caption.weight(.bold))
                .foregroundStyle(DesignTokens.sage)

            Text(practicalTitle)
                .font(.headline.weight(.semibold))
                .foregroundStyle(DesignTokens.ink)
                .fixedSize(horizontal: false, vertical: true)

            LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 8) {
                GuideDigestMetricChip(metric: GuideDigestMetric(title: "交通", value: digest.transportText, systemImage: "arrow.triangle.swap"))
                GuideDigestMetricChip(metric: GuideDigestMetric(title: "时间", value: digest.durationText, systemImage: "clock"))
                GuideDigestMetricChip(metric: GuideDigestMetric(title: "距离", value: digest.distanceText, systemImage: "point.topleft.down.curvedto.point.bottomright.up"))
                GuideDigestMetricChip(metric: GuideDigestMetric(title: "节奏", value: digest.routeBadge == "可参考" ? "慢游参考" : "跟着看看", systemImage: "leaf.fill"))
            }

            if !qualityText.isEmpty {
                Text(qualityText)
                    .font(.footnote.weight(.medium))
                    .foregroundStyle(DesignTokens.secondaryInk)
                    .lineSpacing(3)
                    .padding(10)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(DesignTokens.mist.opacity(0.58))
                    .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
            }

            VStack(alignment: .leading, spacing: 8) {
                ForEach(digest.ownerTips, id: \.self) { tip in
                    HStack(alignment: .top, spacing: 8) {
                        Circle()
                            .fill(DesignTokens.sage.opacity(0.48))
                            .frame(width: 6, height: 6)
                            .padding(.top, 6)
                        Text(tip)
                            .font(.footnote)
                            .foregroundStyle(DesignTokens.secondaryInk)
                            .lineSpacing(3)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
            }
        }
    }

    var practicalTitle: String {
        digest.routeBadge == "可参考"
            ? "这条路线可以作为 \(digest.city) 慢游参考"
            : "先跟着 \(digest.petName) 看看这一段"
    }

    var qualityText: String {
        if digest.routeBadge == "可参考" {
            return "这条线已经保留了城市锚点、停留节奏和照片位置，你也可以按自己的体力慢慢来。"
        }
        let usefulNotes = digest.qualityNotes
            .filter { !$0.contains("已通过") }
            .prefix(2)
        if usefulNotes.isEmpty {
            return ""
        }
        return "这段更像 TA 的生活片段，先别完全照搬：\(usefulNotes.joined(separator: "，"))。"
    }
}

struct PracticalStopListCard: View {
    var stops: [GuideDigestStop]

    var body: some View {
        if !stops.isEmpty {
            SoftCard {
                Label("照着走时看这些", systemImage: "map")
                    .font(.caption.weight(.bold))
                    .foregroundStyle(DesignTokens.dusk)

                VStack(alignment: .leading, spacing: 11) {
                    ForEach(stops) { stop in
                        HStack(alignment: .top, spacing: 10) {
                            Text(stop.time)
                                .font(.caption.weight(.bold))
                                .foregroundStyle(stop.tint)
                                .frame(width: 48, alignment: .leading)
                            VStack(alignment: .leading, spacing: 4) {
                                Text(stop.name)
                                    .font(.subheadline.weight(.semibold))
                                    .foregroundStyle(DesignTokens.ink)
                                    .lineLimit(2)
                                Text(stop.note)
                                    .font(.footnote)
                                    .foregroundStyle(DesignTokens.secondaryInk)
                                    .lineLimit(2)
                                    .fixedSize(horizontal: false, vertical: true)
                                if !stop.tags.isEmpty {
                                    Text(stop.tags.joined(separator: " · "))
                                        .font(.caption2.weight(.semibold))
                                        .foregroundStyle(DesignTokens.secondaryInk.opacity(0.9))
                                        .lineLimit(1)
                                }
                            }
                            Spacer(minLength: 0)
                        }
                    }
                }
            }
        }
    }
}

extension Array where Element == String {
    func chunked(maxCharacters: Int) -> [[String]] {
        var rows: [[String]] = []
        var current: [String] = []
        var currentCount = 0

        for value in self {
            let projectedCount = currentCount + value.count
            if !current.isEmpty, projectedCount > maxCharacters {
                rows.append(current)
                current = [value]
                currentCount = value.count
            } else {
                current.append(value)
                currentCount = projectedCount
            }
        }

        if !current.isEmpty {
            rows.append(current)
        }
        return rows
    }
}

struct TravelGuideDigestCard: View {
    var digest: PetGuideDigest

    var body: some View {
        SoftCard {
            HStack(alignment: .top, spacing: 10) {
                Image(systemName: "map.fill")
                    .font(.headline.weight(.bold))
                    .foregroundStyle(DesignTokens.sage)
                    .frame(width: 40, height: 40)
                    .background(DesignTokens.sage.opacity(0.13))
                    .clipShape(Circle())

                VStack(alignment: .leading, spacing: 4) {
                    Text("TA 走过的小攻略")
                        .font(.caption.weight(.bold))
                        .foregroundStyle(DesignTokens.secondaryInk)
                    Text(digest.title)
                        .font(.title3.weight(.semibold))
                        .foregroundStyle(DesignTokens.ink)
                        .fixedSize(horizontal: false, vertical: true)
                }

                Spacer(minLength: 0)
            }

            Text(digest.summary)
                .font(.subheadline)
                .foregroundStyle(DesignTokens.secondaryInk)
                .lineSpacing(3)
                .fixedSize(horizontal: false, vertical: true)

            LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 8) {
                ForEach(digest.metrics) { metric in
                    GuideDigestMetricChip(metric: metric)
                }
            }

            VStack(alignment: .leading, spacing: 8) {
                Label("今天的主题", systemImage: "sparkles")
                    .font(.caption.weight(.bold))
                    .foregroundStyle(DesignTokens.clay)
                Text(digest.routeTheme.petSoulUserFacingText)
                    .font(.footnote)
                    .foregroundStyle(DesignTokens.secondaryInk)
                    .lineSpacing(3)
            }

            GuideDigestRoutePreview(stops: digest.stops, badge: digest.routeBadge)

            if !digest.ownerTips.isEmpty {
                VStack(alignment: .leading, spacing: 8) {
                    Label("给你的小参考", systemImage: "bookmark.fill")
                        .font(.caption.weight(.bold))
                        .foregroundStyle(DesignTokens.sage)

                    ForEach(Array(digest.ownerTips.enumerated()), id: \.offset) { _, tip in
                        HStack(alignment: .top, spacing: 8) {
                            Circle()
                                .fill(DesignTokens.sage.opacity(0.45))
                                .frame(width: 6, height: 6)
                                .padding(.top, 6)
                            Text(tip)
                                .font(.footnote)
                                .foregroundStyle(DesignTokens.secondaryInk)
                                .lineSpacing(3)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                    }
                }
            }
        }
    }
}

struct GuideDigestMetricChip: View {
    var metric: GuideDigestMetric

    var body: some View {
        HStack(spacing: 7) {
            Image(systemName: metric.systemImage)
                .font(.caption.weight(.bold))
                .foregroundStyle(DesignTokens.sage)
                .frame(width: 24, height: 24)
                .background(DesignTokens.sage.opacity(0.11))
                .clipShape(Circle())
            VStack(alignment: .leading, spacing: 2) {
                Text(metric.title)
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(DesignTokens.secondaryInk)
                Text(metric.value)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(DesignTokens.ink)
                    .lineLimit(1)
                    .minimumScaleFactor(0.76)
            }
            Spacer(minLength: 0)
        }
        .padding(.vertical, 8)
        .padding(.horizontal, 9)
        .background(DesignTokens.surface.opacity(0.58))
        .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
    }
}

struct GuideDigestRoutePreview: View {
    var stops: [GuideDigestStop]
    var badge: String

    var body: some View {
        if !stops.isEmpty {
            VStack(alignment: .leading, spacing: 10) {
                HStack(spacing: 7) {
                    Image(systemName: "list.number")
                        .font(.caption.weight(.bold))
                        .foregroundStyle(DesignTokens.dusk)
                    Text("当日核心路线")
                        .font(.caption.weight(.bold))
                        .foregroundStyle(DesignTokens.secondaryInk)
                    Spacer(minLength: 0)
                    Text(badge)
                        .font(.caption2.weight(.bold))
                        .foregroundStyle(DesignTokens.dusk)
                        .padding(.vertical, 4)
                        .padding(.horizontal, 8)
                        .background(DesignTokens.dusk.opacity(0.11))
                        .clipShape(Capsule())
                }

                ForEach(Array(stops.enumerated()), id: \.element.id) { rowIndex, stop in
                    GuideDigestStopRow(stop: stop, isLast: rowIndex == stops.count - 1)
                }
            }
            .padding(.top, 2)
        }
    }
}

struct GuideDigestStopRow: View {
    var stop: GuideDigestStop
    var isLast: Bool

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            VStack(spacing: 5) {
                ZStack {
                    Circle()
                        .fill(stop.tint.opacity(0.16))
                        .frame(width: 28, height: 28)
                    Text("\(stop.index)")
                        .font(.caption.weight(.black))
                        .foregroundStyle(stop.tint)
                }

                if !isLast {
                    Rectangle()
                        .fill(stop.tint.opacity(0.22))
                        .frame(width: 2, height: 38)
                }
            }

            VStack(alignment: .leading, spacing: 5) {
                HStack(alignment: .firstTextBaseline, spacing: 7) {
                    Text(stop.time)
                        .font(.caption.weight(.bold))
                        .foregroundStyle(stop.tint)
                        .frame(width: 52, alignment: .leading)
                    Text(stop.name)
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(DesignTokens.ink)
                        .lineLimit(1)
                    Spacer(minLength: 0)
                    Image(systemName: stop.systemImage)
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(stop.tint)
                }

                Text(stop.note)
                    .font(.caption)
                    .foregroundStyle(DesignTokens.secondaryInk)
                    .lineLimit(3)
                    .fixedSize(horizontal: false, vertical: true)

                HStack(spacing: 7) {
                    if let dwellMinutes = stop.dwellMinutes {
                        Label("\(dwellMinutes) 分钟", systemImage: "hourglass")
                    }
                }
                .font(.caption2.weight(.semibold))
                .foregroundStyle(DesignTokens.secondaryInk)
            }
        }
    }
}

struct RouteMovementDisclosureCard: View {
    var segments: [RouteSegment]
    var transports: [ScheduledTransportLeg]
    @State var isExpanded = false

    var body: some View {
        SoftCard {
            DisclosureGroup(isExpanded: $isExpanded) {
                VStack(alignment: .leading, spacing: 10) {
                    ForEach(segments.prefix(4)) { segment in
                        RouteSegmentRow(segment: segment)
                    }

                    ForEach(transports.prefix(3)) { leg in
                        TransportLegCard(leg: leg)
                    }
                }
                .padding(.top, 10)
            } label: {
                HStack(spacing: 10) {
                    Image(systemName: "point.topleft.down.curvedto.point.bottomright.up")
                        .font(.subheadline.weight(.bold))
                        .foregroundStyle(DesignTokens.sage)
                        .frame(width: 34, height: 34)
                        .background(DesignTokens.sage.opacity(0.12))
                        .clipShape(Circle())

                    VStack(alignment: .leading, spacing: 2) {
                        Text("真实移动")
                            .font(.subheadline.weight(.semibold))
                            .foregroundStyle(DesignTokens.ink)
                        Text(summary)
                            .font(.caption)
                            .foregroundStyle(DesignTokens.secondaryInk)
                            .lineLimit(2)
                    }

                    Spacer(minLength: 0)
                }
            }
        }
    }

    var summary: String {
        let movementCount = segments.filter { $0.mode != .stay && $0.mode != .checkIn }.count + transports.count
        if movementCount == 0 {
            return "没有需要展开的移动段"
        }
        return "\(movementCount) 段路，想看怎么到达时再展开"
    }
}

extension DayPlanItem.Kind {
    var systemImage: String {
        switch self {
        case .morning: "sunrise.fill"
        case .noon: "fork.knife"
        case .afternoon: "camera.fill"
        case .evening: "moon.stars.fill"
        }
    }

    var tint: Color {
        switch self {
        case .morning: DesignTokens.sage
        case .noon: DesignTokens.amber
        case .afternoon: DesignTokens.dusk
        case .evening: DesignTokens.ink
        }
    }
}

struct JourneyPlanOverviewCard: View {
    var plan: JourneyPlan
    @State var isRouteExpanded = false

    var body: some View {
        SoftCard {
            Label("今天想这样过", systemImage: "pawprint.fill")
                .font(.caption.weight(.bold))
                .foregroundStyle(DesignTokens.sage)

            Text(plan.summary.petSoulPetVoiceText)
                .font(.headline.weight(.semibold))
                .foregroundStyle(DesignTokens.ink)
                .lineSpacing(3)
                .fixedSize(horizontal: false, vertical: true)

            HStack(spacing: 8) {
                GuideInfoChip(
                    title: "我现在",
                    value: plan.currentActivity.petSoulPetVoiceText,
                    systemImage: "pawprint.fill"
                )
                GuideInfoChip(
                    title: "移动",
                    value: plan.transportDecision.selectedMode.displayName,
                    systemImage: plan.transportDecision.selectedMode.systemImage
                )
            }

            Text(plan.transportDecision.reason.petSoulPetVoiceText)
                .font(.footnote)
                .foregroundStyle(DesignTokens.secondaryInk)
                .lineSpacing(3)

            if !plan.routeSegments.isEmpty {
                DisclosureGroup(isExpanded: $isRouteExpanded) {
                    VStack(alignment: .leading, spacing: 9) {
                        ForEach(plan.routeSegments.prefix(5)) { segment in
                            RouteSegmentRow(segment: segment)
                        }
                    }
                    .padding(.top, 8)
                } label: {
                    Label("路上怎么走", systemImage: "figure.walk")
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(DesignTokens.ink)
                }
                .padding(.top, 4)
            }
        }
    }
}

struct RouteSegmentRow: View {
    var segment: RouteSegment

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: segment.mode.systemImage)
                .font(.caption.weight(.bold))
                .foregroundStyle(tint)
                .frame(width: 28, height: 28)
                .background(tint.opacity(0.13))
                .clipShape(Circle())

            VStack(alignment: .leading, spacing: 4) {
                Text(segment.title.petSoulUserFacingText)
                    .font(.footnote.weight(.semibold))
                    .foregroundStyle(DesignTokens.ink)
                    .lineLimit(2)
                Text(routeLine)
                    .font(.caption)
                    .foregroundStyle(DesignTokens.secondaryInk)
                    .lineLimit(2)
                Text(segment.detail.petSoulPetVoiceText)
                    .font(.caption2)
                    .foregroundStyle(DesignTokens.secondaryInk.opacity(0.86))
                    .lineLimit(2)
            }
        }
        .padding(.vertical, 7)
        .padding(.horizontal, 9)
        .background(DesignTokens.surface.opacity(0.56))
        .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
    }

    var routeLine: String {
        var parts = ["\(segment.fromPlace) → \(segment.toPlace)"]
        if let distance = segment.distanceMeters, distance > 0 {
            parts.append(distance >= 1_000 ? String(format: "%.1f km", Double(distance) / 1_000) : "\(distance) m")
        }
        if let seconds = segment.durationSeconds, seconds > 0 {
            parts.append("\(max(1, seconds / 60)) 分钟")
        }
        return parts.joined(separator: " · ")
    }

    var tint: Color {
        switch segment.mode {
        case .flight:
            DesignTokens.dusk
        case .drive:
            DesignTokens.amber
        case .train, .transit:
            DesignTokens.sage
        case .walk:
            DesignTokens.clay
        case .ferry:
            DesignTokens.pollen
        case .stay, .checkIn:
            DesignTokens.sage
        }
    }
}
