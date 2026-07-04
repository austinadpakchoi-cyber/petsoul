import SwiftUI
import UIKit

private enum JourneyChapterMode: String, CaseIterable, Identifiable {
    case story
    case guide

    var id: String { rawValue }

    var title: String {
        switch self {
        case .story: "看 TA 的一天"
        case .guide: "我也想照着走"
        }
    }

    var systemImage: String {
        switch self {
        case .story: "sparkles"
        case .guide: "figure.walk"
        }
    }
}

struct DayPlanSheetView: View {
    var dayPlan: DayPlan?
    var journeyPlan: JourneyPlan?
    var petGuide: PetAuthoredGuide?
    var illustratedGuide: IllustratedGuide?
    var isGeneratingIllustratedGuide: Bool = false
    @State private var activeMode: JourneyChapterMode = .story

    var body: some View {
        ZStack {
            AppBackground()

            if dayPlan != nil || journeyPlan != nil || petGuide != nil || illustratedGuide != nil {
                ScrollView {
                    VStack(alignment: .leading, spacing: 16) {
                        if let guideDigest {
                            JourneyChapterHeroCard(digest: guideDigest, activeMode: $activeMode)

                            IllustratedGuideCard(
                                guide: illustratedGuide,
                                digest: guideDigest,
                                isGenerating: isGeneratingIllustratedGuide
                            )

                            JourneyDateStrip(activeDate: journeyDate, city: routeCity)

                            JourneyChapterModePicker(activeMode: $activeMode)

                            switch activeMode {
                            case .story:
                                CurrentJourneyMomentCard(digest: guideDigest)
                                JourneyCoreRouteCard(stops: guideDigest.stops, badge: guideDigest.routeBadge)
                                JourneySelectedMomentsCard(digest: guideDigest)
                                movementDisclosure
                            case .guide:
                                PracticalGuideCard(digest: guideDigest)
                                PracticalStopListCard(stops: guideDigest.stops)
                                movementDisclosure
                            }
                        }
                    }
                    .padding(DesignTokens.pagePadding)
                }
            } else {
                VStack(spacing: 14) {
                    ProgressView()
                        .tint(DesignTokens.sage)
                        .controlSize(.large)
                    EmptyStateView(
                        title: "正在同步 TA 今天经过的地方",
                        detail: "先别急，手机正在把 TA 今天走过的痕迹整理成一条生活线。",
                        systemImage: "map"
                    )
                }
            }
        }
        .navigationTitle("旅程日历")
        .navigationBarTitleDisplayMode(.inline)
    }

    private var journeyDate: Date {
        if let journeyPlan {
            return journeyPlan.generatedAt
        }
        if let eventDate = dayPlan?.eventsToday.map(\.timestamp).min() {
            return eventDate
        }
        return Date()
    }

    private var journeyDateTitle: String {
        journeyDate.formatted(.dateTime.year().month(.wide).day())
    }

    private var routeSubtitle: String {
        if let petGuide {
            return "\(petGuide.city) · \(max(1, petGuide.guideStops.count)) 个核心停靠"
        }
        if let journeyPlan {
            return "\(journeyPlan.city) · 第 1 天 · \(max(1, journeyPlan.stops.count)) 个核心停靠"
        }
        if let dayPlan {
            return "\(dayPlan.location) · \(dayPlan.stayDuration) 的生活线"
        }
        return "正在同步"
    }

    private var routeCity: String {
        if let journeyPlan {
            return journeyPlan.city
        }
        if let dayPlan {
            return dayPlan.location
        }
        if let petGuide {
            return petGuide.city
        }
        return "旅程"
    }

    private var guideDigest: PetGuideDigest? {
        PetGuideDigest.make(dayPlan: dayPlan, journeyPlan: journeyPlan, guide: petGuide)
    }

    @ViewBuilder
    private var movementDisclosure: some View {
        if let journeyPlan, !journeyPlan.routeSegments.isEmpty {
            RouteMovementDisclosureCard(
                segments: journeyPlan.routeSegments,
                transports: dayPlan?.scheduledTransport ?? journeyPlan.scheduledTransport
            )
        } else if let dayPlan, !dayPlan.scheduledTransport.isEmpty {
            RouteMovementDisclosureCard(
                segments: [],
                transports: dayPlan.scheduledTransport
            )
        }
    }

    private func sheetHeader(title: String, subtitle: String) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title)
                .font(.title2.weight(.semibold))
                .foregroundStyle(DesignTokens.ink)
            Text(subtitle)
                .font(.subheadline)
                .foregroundStyle(DesignTokens.secondaryInk)
            Text("只看这一天的核心停靠，路过点和补给会收在更安静的位置。")
                .font(.footnote)
                .foregroundStyle(DesignTokens.secondaryInk.opacity(0.82))
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var visibleEvents: [JourneyEvent] {
        guard let dayPlan else { return [] }
        var seen = Set<String>()
        return dayPlan.eventsToday
            .sorted(by: { $0.timestamp > $1.timestamp })
            .filter { event in
                !event.title.contains("明信片")
                    && !event.title.contains("照片")
                    && !event.title.contains("自拍")
                    && !event.title.contains("旅程建立")
            }
            .filter { event in
                let key = "\(event.title)|\(event.detail)"
                return seen.insert(key).inserted
            }
            .prefix(4)
            .map { $0 }
    }

    private func dayPlanPhase(for items: [DayPlanItem], index: Int, now: Date = Date()) -> DayPlanTimelinePhase {
        guard let start = minuteOfDay(from: time(in: items, at: index)) else {
            return .upcoming
        }
        let current = Calendar.current.component(.hour, from: now) * 60 + Calendar.current.component(.minute, from: now)
        if current < start {
            return .upcoming
        }
        if let nextStart = minuteOfDay(from: time(in: items, at: index + 1)) {
            return current < nextStart ? .current : .past
        }
        return current < min(start + 120, 1_320) ? .current : .past
    }

    private func minuteOfDay(from time: String?) -> Int? {
        guard let time else { return nil }
        let parts = time.split(separator: ":")
        guard parts.count == 2, let hour = Int(parts[0]), let minute = Int(parts[1]) else {
            return nil
        }
        return hour * 60 + minute
    }

    private func time(in items: [DayPlanItem], at index: Int) -> String? {
        guard items.indices.contains(index) else { return nil }
        return items[index].time
    }
}

private struct IllustratedGuideCard: View {
    var guide: IllustratedGuide?
    var digest: PetGuideDigest
    var isGenerating: Bool

    @State private var selectedPageIndex = 1

    private var statusText: String {
        if isGenerating {
            return "正在画"
        }
        switch guide?.status {
        case .ready:
            return "已生成"
        case .generating:
            return "正在画"
        case .failed:
            return "稍后再试"
        case .promptReady, .none:
            return "等待成图"
        }
    }

    private var guideStyleName: String {
        guide?.styleName ?? "温柔手账风"
    }

    private var previewStops: [IllustratedGuidePreviewStop] {
        if let guide, !guide.stops.isEmpty {
            return guide.stops.prefix(5).map {
                IllustratedGuidePreviewStop(
                    id: "\($0.index)-\($0.name)",
                    index: $0.index,
                    time: $0.time,
                    name: $0.name,
                    label: $0.label,
                    note: $0.shortNote,
                    systemImage: IllustratedGuideCard.icon(for: $0.category)
                )
            }
        }

        return digest.stops.prefix(5).map {
            IllustratedGuidePreviewStop(
                id: $0.id,
                index: $0.index,
                time: $0.time,
                name: $0.name,
                label: $0.tags.first ?? "停留",
                note: $0.note,
                systemImage: $0.systemImage
            )
        }
    }

    private var pages: [IllustratedGuidePage] {
        if let guidePages = guide?.pages, !guidePages.isEmpty {
            return guidePages.sorted { $0.index < $1.index }
        }
        return [
            IllustratedGuidePage(
                index: 1,
                title: "手账封面",
                subtitle: "\(guide?.city ?? digest.city) · \(previewStops.count) 个停靠",
                intent: "像线圈本第一页，先把城市和今天的主题讲清楚",
                pageType: "cover",
                templateID: "spiral_cover_overview",
                visualStyle: "线圈手账封面，水彩插画，贴纸和便签",
                composition: "cover_overview",
                styleID: guide?.styleID ?? "warm_travel_journal",
                styleName: guideStyleName,
                imagePrompt: guide?.imagePrompt ?? "",
                imageURL: guide?.imageURL,
                thumbnailURL: guide?.thumbnailURL,
                status: guide?.status ?? .promptReady
            )
        ]
    }

    private var selectedPosition: Int {
        guard let index = pages.firstIndex(where: { $0.index == selectedPageIndex }) else { return 0 }
        return index
    }

    private var selectedPage: IllustratedGuidePage {
        pages.indices.contains(selectedPosition) ? pages[selectedPosition] : pages[0]
    }

    var body: some View {
        SoftCard {
            HStack(alignment: .top, spacing: 10) {
                Image(systemName: "paintpalette.fill")
                    .font(.headline.weight(.bold))
                    .foregroundStyle(DesignTokens.clay)
                    .frame(width: 40, height: 40)
                    .background(DesignTokens.clay.opacity(0.12))
                    .clipShape(Circle())

                VStack(alignment: .leading, spacing: 4) {
                    VStack(alignment: .leading, spacing: 5) {
                        HStack(spacing: 8) {
                            Text("今日旅程手账")
                                .font(.caption.weight(.bold))
                                .foregroundStyle(DesignTokens.secondaryInk)
                            Text("\(pages.count) 页")
                                .font(.caption2.weight(.bold))
                                .foregroundStyle(DesignTokens.sage)
                                .padding(.vertical, 3)
                                .padding(.horizontal, 7)
                                .background(DesignTokens.sage.opacity(0.12))
                                .clipShape(Capsule())
                        }

                        HStack(spacing: 8) {
                            Text(guideStyleName)
                                .font(.caption2.weight(.bold))
                                .foregroundStyle(DesignTokens.dusk)
                                .lineLimit(1)
                                .padding(.vertical, 3)
                                .padding(.horizontal, 7)
                                .background(DesignTokens.dusk.opacity(0.10))
                                .clipShape(Capsule())
                            Text(statusText)
                                .font(.caption2.weight(.bold))
                                .foregroundStyle(DesignTokens.clay)
                                .padding(.vertical, 3)
                                .padding(.horizontal, 7)
                                .background(DesignTokens.clay.opacity(0.12))
                                .clipShape(Capsule())
                        }
                    }

                    Text(guide?.title ?? "\(digest.petName)的\(digest.city)小手账")
                        .font(.title3.weight(.semibold))
                        .foregroundStyle(DesignTokens.ink)
                        .fixedSize(horizontal: false, vertical: true)
                }

                Spacer(minLength: 0)
            }

            VStack(spacing: 10) {
                HStack(spacing: 10) {
                    IllustratedGuideTurnButton(systemImage: "chevron.left") {
                        turnPage(-1)
                    }
                    .disabled(selectedPosition == 0)

                    VStack(spacing: 2) {
                        Text(selectedPage.title)
                            .font(.caption.weight(.bold))
                            .foregroundStyle(DesignTokens.ink)
                            .lineLimit(1)
                        Text("第 \(selectedPosition + 1) / \(pages.count) 页 · 左右滑动翻页")
                            .font(.caption2.weight(.medium))
                            .foregroundStyle(DesignTokens.secondaryInk)
                    }
                    .frame(maxWidth: .infinity)

                    IllustratedGuideTurnButton(systemImage: "chevron.right") {
                        turnPage(1)
                    }
                    .disabled(selectedPosition >= pages.count - 1)
                }

                TabView(selection: $selectedPageIndex) {
                    ForEach(pages) { page in
                        IllustratedGuidePageCard(
                            page: page,
                            fallbackTitle: guide?.title ?? digest.chapterTitle,
                            fallbackTheme: guide?.theme ?? digest.routeTheme,
                            petThought: guide?.petThought ?? "我先替你把这一天拆成几页小手账。以后有机会，你也可以来看看。",
                            city: guide?.city ?? digest.city,
                            stops: previewStops(for: page),
                            isGenerating: isGenerating || guide?.status == .generating,
                            isFailed: guide?.status == .failed
                        )
                        .padding(.horizontal, 2)
                        .tag(page.index)
                    }
                }
                .frame(height: 492)
                .tabViewStyle(.page(indexDisplayMode: .never))

                IllustratedGuidePageDots(pages: pages, selection: selectedPageIndex)
            }

            Text("这些页是 TA 给你翻看的手绘手账；详细路线、停留时间和交通方式仍在下面。")
                .font(.caption)
                .foregroundStyle(DesignTokens.secondaryInk.opacity(0.86))
                .lineSpacing(3)
                .fixedSize(horizontal: false, vertical: true)
        }
        .onAppear {
            selectedPageIndex = pages.first?.index ?? 1
        }
        .onChange(of: pages.count) {
            if !pages.contains(where: { $0.index == selectedPageIndex }) {
                selectedPageIndex = pages.first?.index ?? 1
            }
        }
    }

    private func previewStops(for page: IllustratedGuidePage) -> [IllustratedGuidePreviewStop] {
        previewStops
    }

    private func turnPage(_ delta: Int) {
        guard !pages.isEmpty else { return }
        let nextIndex = min(max(selectedPosition + delta, 0), pages.count - 1)
        withAnimation(.spring(response: 0.34, dampingFraction: 0.86)) {
            selectedPageIndex = pages[nextIndex].index
        }
    }

    private static func icon(for category: String) -> String {
        let value = category.lowercased()
        if value.contains("park") || value.contains("scenic") {
            return "tree.fill"
        }
        if value.contains("cafe") {
            return "cup.and.saucer.fill"
        }
        if value.contains("food") || value.contains("restaurant") {
            return "fork.knife"
        }
        if value.contains("shop") {
            return "bag.fill"
        }
        return "mappin"
    }
}

private struct IllustratedGuidePageCard: View {
    var page: IllustratedGuidePage
    var fallbackTitle: String
    var fallbackTheme: String
    var petThought: String
    var city: String
    var stops: [IllustratedGuidePreviewStop]
    var isGenerating: Bool
    var isFailed: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .firstTextBaseline, spacing: 7) {
                Text("\(page.index)")
                    .font(.caption.weight(.black))
                    .foregroundStyle(.white)
                    .frame(width: 22, height: 22)
                    .background(DesignTokens.clay)
                    .clipShape(Circle())

                VStack(alignment: .leading, spacing: 2) {
                    Text(page.title)
                        .font(.caption.weight(.bold))
                        .foregroundStyle(DesignTokens.ink)
                        .lineLimit(1)
                    Text(page.subtitle)
                        .font(.caption2.weight(.medium))
                        .foregroundStyle(DesignTokens.secondaryInk)
                        .lineLimit(1)
                }
            }

            if let imageURL = page.thumbnailURL ?? page.imageURL {
                PostcardImageView(url: imageURL, height: 440)
                    .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
            } else {
                IllustratedGuideImagePlaceholder(
                    title: page.title.isEmpty ? fallbackTitle : page.title,
                    styleName: page.styleName,
                    isGenerating: isGenerating,
                    isFailed: isFailed
                )
                .frame(height: 440)
            }
        }
        .padding(10)
        .background(.white.opacity(0.42))
        .clipShape(RoundedRectangle(cornerRadius: 22, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 22, style: .continuous)
                .stroke(.white.opacity(0.74), lineWidth: 1)
        )
    }
}

private struct IllustratedGuideImagePlaceholder: View {
    var title: String
    var styleName: String?
    var isGenerating: Bool
    var isFailed: Bool

    var body: some View {
        ZStack {
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .fill(
                    LinearGradient(
                        colors: [
                            Color(hex: 0xFFF7E8).opacity(0.92),
                            DesignTokens.porcelain.opacity(0.72),
                            DesignTokens.mist.opacity(0.58)
                        ],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    )
                )

            VStack(spacing: 16) {
                ZStack {
                    Circle()
                        .fill(DesignTokens.clay.opacity(0.10))
                        .frame(width: 82, height: 82)
                    Circle()
                        .stroke(DesignTokens.clay.opacity(0.18), style: StrokeStyle(lineWidth: 1, dash: [5, 5]))
                        .frame(width: 102, height: 102)
                    Image(systemName: isFailed ? "paintpalette" : "wand.and.stars")
                        .font(.system(size: 30, weight: .semibold))
                        .foregroundStyle(DesignTokens.clay)
                }

                VStack(spacing: 8) {
                    Text(statusTitle)
                        .font(.headline.weight(.semibold))
                        .foregroundStyle(DesignTokens.ink)
                    Text(title)
                        .font(.subheadline.weight(.medium))
                        .foregroundStyle(DesignTokens.secondaryInk)
                        .multilineTextAlignment(.center)
                        .lineLimit(2)
                    if let styleName, !styleName.isEmpty {
                        Text(styleName)
                            .font(.caption.weight(.bold))
                            .foregroundStyle(DesignTokens.dusk)
                            .padding(.vertical, 5)
                            .padding(.horizontal, 10)
                            .background(DesignTokens.dusk.opacity(0.10))
                            .clipShape(Capsule())
                    }
                }

                if isGenerating {
                    ProgressView()
                        .tint(DesignTokens.clay)
                    Text("路线、地点和文字已经锁定，正在生成真正的手绘攻略图。")
                        .font(.caption)
                        .foregroundStyle(DesignTokens.secondaryInk.opacity(0.84))
                        .multilineTextAlignment(.center)
                        .lineSpacing(3)
                        .padding(.horizontal, 26)
                } else if isFailed {
                    Text("生成信号暂时不稳定，稍后重新打开会再尝试。")
                        .font(.caption)
                        .foregroundStyle(DesignTokens.secondaryInk.opacity(0.84))
                        .multilineTextAlignment(.center)
                        .lineSpacing(3)
                        .padding(.horizontal, 26)
                } else {
                    Text("这不是最终攻略图，只是等待成图状态。")
                        .font(.caption)
                        .foregroundStyle(DesignTokens.secondaryInk.opacity(0.84))
                        .multilineTextAlignment(.center)
                        .lineSpacing(3)
                        .padding(.horizontal, 26)
                }
            }
            .padding(24)
        }
        .overlay(
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .stroke(.white.opacity(0.72), lineWidth: 1)
        )
    }

    private var statusTitle: String {
        if isFailed {
            return "这页还没画出来"
        }
        if isGenerating {
            return "正在画这页手账"
        }
        return "等待生成手绘攻略图"
    }
}

private struct IllustratedGuideTurnButton: View {
    var systemImage: String
    var action: () -> Void

    @Environment(\.isEnabled) private var isEnabled

    var body: some View {
        Button(action: action) {
            Image(systemName: systemImage)
                .font(.caption.weight(.black))
                .foregroundStyle(isEnabled ? DesignTokens.ink : DesignTokens.secondaryInk.opacity(0.35))
                .frame(width: 32, height: 32)
                .background(.white.opacity(isEnabled ? 0.86 : 0.46))
                .clipShape(Circle())
                .overlay(
                    Circle()
                        .stroke(DesignTokens.softLine.opacity(0.72), lineWidth: 1)
                )
        }
        .buttonStyle(.plain)
    }
}

private struct IllustratedGuidePageDots: View {
    var pages: [IllustratedGuidePage]
    var selection: Int

    var body: some View {
        HStack(spacing: 7) {
            ForEach(pages) { page in
                Capsule()
                    .fill(page.index == selection ? DesignTokens.clay : DesignTokens.softLine)
                    .frame(width: page.index == selection ? 18 : 7, height: 7)
                    .animation(.spring(response: 0.28, dampingFraction: 0.84), value: selection)
            }
        }
        .accessibilityHidden(true)
    }
}

private struct IllustratedGuidePreviewStop: Identifiable {
    var id: String
    var index: Int
    var time: String?
    var name: String
    var label: String
    var note: String
    var systemImage: String
}

private struct IllustratedGuidePreviewCanvas: View {
    var title: String
    var theme: String
    var petThought: String
    var city: String
    var templateID: String = "spiral_cover_overview"
    var stops: [IllustratedGuidePreviewStop]

    var body: some View {
        ZStack(alignment: .leading) {
            notebookPaper
            IllustratedGuideSpiralBinding()
                .padding(.leading, 6)

            Group {
                switch templateID {
                case "winding_route_map", "route_map":
                    routeMapPage
                case "vertical_timeline_journal", "timeline":
                    timelinePage
                default:
                    coverPage
                }
            }
            .padding(.leading, 26)
            .padding(.trailing, 16)
            .padding(.vertical, 18)
        }
        .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .stroke(Color(hex: 0xD8C8AA).opacity(0.48), lineWidth: 1)
        )
    }

    private var notebookPaper: some View {
        ZStack {
            Color(hex: 0xFFF6E5)
            LinearGradient(
                colors: [
                    Color.white.opacity(0.25),
                    DesignTokens.pollen.opacity(0.12),
                    DesignTokens.sky.opacity(0.18)
                ],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
        }
    }

    private var coverPage: some View {
        VStack(alignment: .leading, spacing: 11) {
            HStack(alignment: .top, spacing: 10) {
                VStack(alignment: .leading, spacing: 5) {
                    Text(title)
                        .font(.title3.weight(.black))
                        .foregroundStyle(DesignTokens.ink)
                        .lineLimit(2)
                        .minimumScaleFactor(0.72)
                    Text("从山上的风，到老城的烟火，再到傍晚的水边")
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(DesignTokens.dusk)
                        .lineLimit(2)
                        .padding(.vertical, 5)
                        .padding(.horizontal, 8)
                        .background(DesignTokens.sky.opacity(0.58))
                        .clipShape(Capsule())
                }
                Spacer(minLength: 0)
                IllustratedGuideSketchStamp(title: city, systemImage: "photo")
            }

            HStack(alignment: .center, spacing: 10) {
                Image(systemName: "pawprint.fill")
                    .font(.title.weight(.bold))
                    .foregroundStyle(DesignTokens.clay)
                    .frame(width: 50, height: 50)
                    .background(DesignTokens.clay.opacity(0.12))
                    .clipShape(Circle())
                Text(theme)
                    .font(.caption.weight(.medium))
                    .foregroundStyle(DesignTokens.secondaryInk)
                    .lineLimit(3)
                    .lineSpacing(2)
            }
            .padding(10)
            .background(.white.opacity(0.58))
            .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))

            Text("今日路线")
                .font(.caption.weight(.bold))
                .foregroundStyle(DesignTokens.sage)

            HStack(spacing: 7) {
                ForEach(stops.prefix(5)) { stop in
                    VStack(spacing: 5) {
                        IllustratedGuideMiniScene(stop: stop)
                        Text(stop.name)
                            .font(.caption2.weight(.bold))
                            .foregroundStyle(DesignTokens.ink)
                            .lineLimit(1)
                            .minimumScaleFactor(0.72)
                    }
                    .frame(maxWidth: .infinity)
                }
            }

            HStack(spacing: 6) {
                ForEach(stops.prefix(4)) { stop in
                    Text(stop.label)
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(DesignTokens.secondaryInk)
                        .lineLimit(1)
                        .padding(.vertical, 6)
                        .padding(.horizontal, 8)
                        .background(keywordTint(for: stop).opacity(0.18))
                        .clipShape(Capsule())
                }
            }

            thoughtBubble
        }
    }

    private var routeMapPage: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 4) {
                    Text("今日旅程图")
                        .font(.title3.weight(.black))
                        .foregroundStyle(DesignTokens.ink)
                    Text("\(city) · \(stops.count) 站串联")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(DesignTokens.dusk)
                }
                Spacer(minLength: 0)
                IllustratedGuideSketchStamp(title: "路线主题", systemImage: "map")
            }

            Text(theme)
                .font(.caption.weight(.medium))
                .foregroundStyle(DesignTokens.secondaryInk)
                .lineLimit(2)

            ZStack {
                IllustratedGuideWindingPath()
                    .stroke(DesignTokens.amber.opacity(0.42), style: StrokeStyle(lineWidth: 7, lineCap: .round, dash: [6, 8]))
                    .padding(.horizontal, 18)

                VStack(spacing: 8) {
                    ForEach(Array(stops.prefix(5).enumerated()), id: \.element.id) { offset, stop in
                        HStack(spacing: 8) {
                            if offset.isMultiple(of: 2) {
                                routeStopPill(stop)
                                Spacer(minLength: 18)
                            } else {
                                Spacer(minLength: 18)
                                routeStopPill(stop)
                            }
                        }
                    }
                }
            }
            .frame(maxHeight: .infinity)

            thoughtBubble
        }
    }

    private var timelinePage: some View {
        VStack(alignment: .leading, spacing: 11) {
            HStack(alignment: .firstTextBaseline) {
                Text("慢慢走的一天")
                    .font(.title3.weight(.black))
                    .foregroundStyle(DesignTokens.ink)
                Spacer(minLength: 0)
                Text(city)
                    .font(.caption.weight(.bold))
                    .foregroundStyle(DesignTokens.clay)
            }

            VStack(alignment: .leading, spacing: 8) {
                ForEach(Array(stops.prefix(5).enumerated()), id: \.element.id) { rowIndex, stop in
                    IllustratedGuidePreviewStopRow(stop: stop, isLast: rowIndex == min(stops.count, 5) - 1)
                }
            }
            .padding(.top, 2)

            Spacer(minLength: 0)
            thoughtBubble
        }
    }

    private var thoughtBubble: some View {
        HStack(alignment: .top, spacing: 8) {
            Image(systemName: "sparkles")
                .font(.caption.weight(.bold))
                .foregroundStyle(DesignTokens.clay)
            Text(petThought)
                .font(.caption.weight(.medium))
                .foregroundStyle(DesignTokens.secondaryInk)
                .lineSpacing(3)
                .lineLimit(3)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(10)
        .background(.white.opacity(0.58))
        .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .stroke(style: StrokeStyle(lineWidth: 1, dash: [5, 5]))
                .foregroundStyle(DesignTokens.clay.opacity(0.22))
        )
    }

    private func routeStopPill(_ stop: IllustratedGuidePreviewStop) -> some View {
        HStack(spacing: 7) {
            IllustratedGuideMiniScene(stop: stop)
                .frame(width: 42, height: 42)
            VStack(alignment: .leading, spacing: 2) {
                Text("\(stop.index)  \(stop.name)")
                    .font(.caption.weight(.bold))
                    .foregroundStyle(DesignTokens.ink)
                    .lineLimit(1)
                    .minimumScaleFactor(0.72)
                Text(stop.time ?? stop.label)
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(DesignTokens.secondaryInk)
            }
        }
        .padding(7)
        .frame(width: 190, alignment: .leading)
        .background(.white.opacity(0.66))
        .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
    }

    private func keywordTint(for stop: IllustratedGuidePreviewStop) -> Color {
        if stop.systemImage.contains("tree") { return DesignTokens.sage }
        if stop.systemImage.contains("cup") { return DesignTokens.sea }
        if stop.systemImage.contains("fork") { return DesignTokens.amber }
        return DesignTokens.clay
    }
}

private struct IllustratedGuideSpiralBinding: View {
    var body: some View {
        VStack(spacing: 13) {
            ForEach(0..<18, id: \.self) { _ in
                HStack(spacing: 0) {
                    Circle()
                        .stroke(Color(hex: 0x9B8C78).opacity(0.62), lineWidth: 1.4)
                        .frame(width: 9, height: 9)
                    RoundedRectangle(cornerRadius: 1)
                        .fill(Color(hex: 0x9B8C78).opacity(0.42))
                        .frame(width: 10, height: 2)
                }
            }
        }
    }
}

private struct IllustratedGuideSketchStamp: View {
    var title: String
    var systemImage: String

    var body: some View {
        VStack(spacing: 4) {
            Image(systemName: systemImage)
                .font(.caption.weight(.bold))
                .foregroundStyle(DesignTokens.dusk)
                .frame(width: 44, height: 34)
                .background(DesignTokens.sky.opacity(0.62))
                .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
            Text(title)
                .font(.system(size: 8, weight: .bold))
                .foregroundStyle(DesignTokens.secondaryInk)
                .lineLimit(1)
        }
        .padding(6)
        .rotationEffect(.degrees(3))
        .background(Color.white.opacity(0.62))
        .clipShape(RoundedRectangle(cornerRadius: 9, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 9, style: .continuous)
                .stroke(DesignTokens.clay.opacity(0.18), lineWidth: 1)
        )
    }
}

private struct IllustratedGuideMiniScene: View {
    var stop: IllustratedGuidePreviewStop

    var body: some View {
        ZStack {
            RoundedRectangle(cornerRadius: 10, style: .continuous)
                .fill(
                    LinearGradient(
                        colors: [
                            tint.opacity(0.22),
                            Color.white.opacity(0.7)
                        ],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    )
                )
            Image(systemName: stop.systemImage)
                .font(.caption.weight(.bold))
                .foregroundStyle(tint)
            VStack {
                Spacer()
                HStack {
                    Text("\(stop.index)")
                        .font(.system(size: 8, weight: .black))
                        .foregroundStyle(.white)
                        .frame(width: 14, height: 14)
                        .background(tint)
                        .clipShape(Circle())
                    Spacer()
                }
            }
            .padding(4)
        }
        .frame(height: 48)
    }

    private var tint: Color {
        if stop.systemImage.contains("tree") { return DesignTokens.sage }
        if stop.systemImage.contains("cup") { return DesignTokens.sea }
        if stop.systemImage.contains("fork") { return DesignTokens.amber }
        return DesignTokens.clay
    }
}

private struct IllustratedGuideWindingPath: Shape {
    func path(in rect: CGRect) -> Path {
        var path = Path()
        path.move(to: CGPoint(x: rect.minX + rect.width * 0.12, y: rect.minY + rect.height * 0.08))
        path.addCurve(
            to: CGPoint(x: rect.maxX - rect.width * 0.18, y: rect.minY + rect.height * 0.28),
            control1: CGPoint(x: rect.maxX - rect.width * 0.2, y: rect.minY + rect.height * 0.04),
            control2: CGPoint(x: rect.minX + rect.width * 0.36, y: rect.minY + rect.height * 0.28)
        )
        path.addCurve(
            to: CGPoint(x: rect.minX + rect.width * 0.22, y: rect.minY + rect.height * 0.56),
            control1: CGPoint(x: rect.maxX - rect.width * 0.06, y: rect.minY + rect.height * 0.42),
            control2: CGPoint(x: rect.minX + rect.width * 0.18, y: rect.minY + rect.height * 0.36)
        )
        path.addCurve(
            to: CGPoint(x: rect.maxX - rect.width * 0.18, y: rect.minY + rect.height * 0.86),
            control1: CGPoint(x: rect.minX + rect.width * 0.28, y: rect.minY + rect.height * 0.78),
            control2: CGPoint(x: rect.maxX - rect.width * 0.28, y: rect.minY + rect.height * 0.62)
        )
        return path
    }
}

private struct IllustratedGuidePreviewStopRow: View {
    var stop: IllustratedGuidePreviewStop
    var isLast: Bool

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            VStack(spacing: 4) {
                ZStack {
                    Circle()
                        .fill(.white.opacity(0.74))
                        .frame(width: 30, height: 30)
                    Text("\(stop.index)")
                        .font(.caption.weight(.black))
                        .foregroundStyle(DesignTokens.sage)
                }

                if !isLast {
                    RoundedRectangle(cornerRadius: 2)
                        .fill(DesignTokens.sage.opacity(0.26))
                        .frame(width: 2, height: 24)
                }
            }

            VStack(alignment: .leading, spacing: 3) {
                HStack(spacing: 6) {
                    if let time = stop.time, !time.isEmpty {
                        Text(time)
                            .font(.caption2.weight(.bold))
                            .foregroundStyle(DesignTokens.sage)
                    }
                    Image(systemName: stop.systemImage)
                        .font(.caption2.weight(.bold))
                        .foregroundStyle(DesignTokens.clay)
                    Text(stop.label)
                        .font(.caption2.weight(.bold))
                        .foregroundStyle(DesignTokens.clay)
                }

                Text(stop.name)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(DesignTokens.ink)
                    .lineLimit(1)

                Text(stop.note)
                    .font(.caption2)
                    .foregroundStyle(DesignTokens.secondaryInk)
                    .lineLimit(2)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }
}

private struct JourneyDateStrip: View {
    var activeDate: Date
    var city: String

    private var days: [JourneyDateChipModel] {
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

private struct JourneyDateChipModel: Identifiable {
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

private struct JourneyDateChip: View {
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
        .background(day.isActive ? DesignTokens.mist.opacity(0.78) : .white.opacity(0.56))
        .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .stroke(day.isActive ? DesignTokens.sage.opacity(0.24) : DesignTokens.softLine, lineWidth: 1)
        }
    }
}

private struct PetGuideDigest {
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

    private static func makeStops(dayPlan: DayPlan?, journeyPlan: JourneyPlan?, guide: PetAuthoredGuide?) -> [GuideDigestStop] {
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
        let nowMinute = Calendar.current.component(.hour, from: Date()) * 60 + Calendar.current.component(.minute, from: Date())
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
        let nowMinute = Calendar.current.component(.hour, from: Date()) * 60 + Calendar.current.component(.minute, from: Date())
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

    private static func petName(from title: String?) -> String {
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

    private static func openingThought(summary: String, routeTheme: String?) -> String {
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

    private static func stopTags(category: String, role: String?, dwellMinutes: Int?, canPhoto: Bool, canPostcard: Bool) -> [String] {
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

    private static func dayPlanTags(_ kind: DayPlanItem.Kind) -> [String] {
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

    private static func minuteOfDay(from time: String) -> Int? {
        let parts = time.split(separator: ":")
        guard parts.count == 2, let hour = Int(parts[0]), let minute = Int(parts[1]) else {
            return nil
        }
        return hour * 60 + minute
    }

    private static func transportSummary(journeyPlan: JourneyPlan?, guide: PetAuthoredGuide?) -> String {
        let modes = ((journeyPlan?.routeSegments.map(\.mode) ?? []) + (guide?.scheduledTransport.map(\.mode) ?? []))
            .filter { $0 != .stay && $0 != .checkIn }
        var seen = Set<String>()
        let names = modes.map(\.displayName).filter { seen.insert($0).inserted }
        return names.isEmpty ? "步行" : names.prefix(3).joined(separator: " + ")
    }

    private static func distanceSummary(journeyPlan: JourneyPlan?) -> String {
        let meters = journeyPlan?.routeSegments.compactMap(\.distanceMeters).reduce(0, +) ?? 0
        guard meters > 0 else { return "按地图同步" }
        if meters >= 1_000 {
            return String(format: "%.1f km", Double(meters) / 1_000)
        }
        return "\(meters) m"
    }

    private static func durationSummary(dwellMinutes: Int, routeSeconds: Int) -> String {
        let totalMinutes = max(30, dwellMinutes + routeSeconds / 60)
        if totalMinutes < 60 {
            return "\(totalMinutes) 分钟"
        }
        let hours = totalMinutes / 60
        let minutes = totalMinutes % 60
        return minutes == 0 ? "\(hours) 小时" : "\(hours)h \(minutes)m"
    }

    private static func sourceSummary(guide: PetAuthoredGuide?, journeyPlan: JourneyPlan?) -> String {
        if let guide {
            return "\(guide.guideStops.count) 个核心停靠"
        }
        if let count = journeyPlan?.places.count {
            return "\(count) 个地图点"
        }
        return "手机整理"
    }

    private static func routeBadge(city: String, stops: [GuideDigestStop]) -> String {
        return routeBadge(city: city, stops: stops, isReplicableRoute: nil)
    }

    private static func routeBadge(city: String, stops: [GuideDigestStop], isReplicableRoute: Bool?) -> String {
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

    private static func ownerTips(dayPlan: DayPlan?, journeyPlan: JourneyPlan?, guide: PetAuthoredGuide?, sourceText: String) -> [String] {
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

    private static func categoryIcon(_ category: String) -> String {
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

    private static func categoryTint(_ category: String) -> Color {
        switch category {
        case "food", "shop": DesignTokens.amber
        case "cafe", "park", "place", "beach": DesignTokens.sage
        case "netcafe": DesignTokens.dusk
        case "flower": DesignTokens.clay
        default: DesignTokens.sage
        }
    }
}

private struct GuideDigestMetric: Identifiable {
    var id: String { "\(title)-\(value)" }
    var title: String
    var value: String
    var systemImage: String
}

private struct GuideDigestStop: Identifiable {
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

private struct GuideDigestMoment: Identifiable {
    var id: String { "\(title)-\(detail)" }
    var title: String
    var detail: String
    var systemImage: String
    var tint: Color
}

private struct JourneyChapterHeroCard: View {
    var digest: PetGuideDigest
    @Binding var activeMode: JourneyChapterMode

    var body: some View {
        SoftCard {
            VStack(alignment: .leading, spacing: 14) {
                HStack(alignment: .top, spacing: 12) {
                    PetSoulAdaptiveIcon(systemImage: "map.fill", tint: DesignTokens.sage, size: 42)
                        .frame(width: 52, height: 52)
                        .background(DesignTokens.sage.opacity(0.12))
                        .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))

                    VStack(alignment: .leading, spacing: 6) {
                        Text(digest.chapterTitle)
                            .font(.title3.weight(.semibold))
                            .foregroundStyle(DesignTokens.ink)
                            .fixedSize(horizontal: false, vertical: true)

                        Text(digest.chapterSubtitle)
                            .font(.subheadline)
                            .foregroundStyle(DesignTokens.secondaryInk)
                            .lineSpacing(3)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }

                FlowChipRow(values: digest.metaChips)

                if let current = digest.currentStop {
                    VStack(alignment: .leading, spacing: 8) {
                        HStack(spacing: 8) {
                            Text(digest.currentStageText)
                                .font(.caption.weight(.bold))
                                .foregroundStyle(DesignTokens.sage)
                                .padding(.vertical, 4)
                                .padding(.horizontal, 8)
                                .background(DesignTokens.sage.opacity(0.12))
                                .clipShape(Capsule())
                            Text("\(current.time) · \(current.shortName)")
                                .font(.caption.weight(.semibold))
                                .foregroundStyle(DesignTokens.secondaryInk)
                        }

                        Text(current.note)
                            .font(.callout.weight(.medium))
                            .foregroundStyle(DesignTokens.ink)
                            .lineSpacing(3)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    .padding(12)
                    .background(.white.opacity(0.64))
                    .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
                    .overlay {
                        RoundedRectangle(cornerRadius: 16, style: .continuous)
                            .stroke(DesignTokens.softLine.opacity(0.8), lineWidth: 1)
                    }
                }

                HStack(spacing: 10) {
                    ChapterActionButton(
                        title: "查看今天路线",
                        systemImage: "list.number",
                        isActive: activeMode == .story
                    ) {
                        withAnimation(.snappy(duration: 0.22)) {
                            activeMode = .story
                        }
                    }

                    ChapterActionButton(
                        title: "我也想照着走",
                        systemImage: "figure.walk",
                        isActive: activeMode == .guide
                    ) {
                        withAnimation(.snappy(duration: 0.22)) {
                            activeMode = .guide
                        }
                    }
                }
            }
        }
    }
}

private struct FlowChipRow: View {
    var values: [String]

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            ForEach(values.chunked(maxCharacters: 18), id: \.self) { row in
                HStack(spacing: 8) {
                    ForEach(row, id: \.self) { value in
                        Text(value)
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(DesignTokens.secondaryInk)
                            .lineLimit(1)
                            .minimumScaleFactor(0.78)
                            .padding(.vertical, 6)
                            .padding(.horizontal, 9)
                            .background(DesignTokens.mist.opacity(0.72))
                            .clipShape(Capsule())
                    }
                }
            }
        }
    }
}

private struct ChapterActionButton: View {
    var title: String
    var systemImage: String
    var isActive: Bool
    var action: () -> Void

    var body: some View {
        Button(action: action) {
            Label(title, systemImage: systemImage)
                .font(.caption.weight(.bold))
                .foregroundStyle(isActive ? .white : DesignTokens.ink)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 11)
                .background(isActive ? DesignTokens.sage : .white.opacity(0.72))
                .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
                .overlay {
                    RoundedRectangle(cornerRadius: 14, style: .continuous)
                        .stroke(isActive ? DesignTokens.sage.opacity(0.0) : DesignTokens.softLine, lineWidth: 1)
                }
        }
        .buttonStyle(.plain)
    }
}

private struct JourneyChapterModePicker: View {
    @Binding var activeMode: JourneyChapterMode

    var body: some View {
        HStack(spacing: 8) {
            ForEach(JourneyChapterMode.allCases) { mode in
                Button {
                    withAnimation(.snappy(duration: 0.2)) {
                        activeMode = mode
                    }
                } label: {
                    HStack(spacing: 6) {
                        Image(systemName: mode.systemImage)
                            .font(.caption.weight(.bold))
                        Text(mode.title)
                            .font(.caption.weight(.bold))
                    }
                    .foregroundStyle(activeMode == mode ? DesignTokens.ink : DesignTokens.secondaryInk)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 10)
                    .background(activeMode == mode ? .white.opacity(0.84) : .white.opacity(0.42))
                    .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
                    .overlay {
                        RoundedRectangle(cornerRadius: 14, style: .continuous)
                            .stroke(activeMode == mode ? DesignTokens.sage.opacity(0.24) : DesignTokens.softLine.opacity(0.72), lineWidth: 1)
                    }
                }
                .buttonStyle(.plain)
            }
        }
    }
}

private struct CurrentJourneyMomentCard: View {
    var digest: PetGuideDigest

    var body: some View {
        if let stop = digest.currentStop {
            SoftCard {
                Label("当前进行中", systemImage: "dot.radiowaves.left.and.right")
                    .font(.caption.weight(.bold))
                    .foregroundStyle(DesignTokens.sage)

                Text("\(digest.petName)正在 \(stop.shortName)")
                    .font(.headline.weight(.semibold))
                    .foregroundStyle(DesignTokens.ink)
                    .fixedSize(horizontal: false, vertical: true)

                Text(stop.note)
                    .font(.subheadline)
                    .foregroundStyle(DesignTokens.secondaryInk)
                    .lineSpacing(3)
                    .fixedSize(horizontal: false, vertical: true)

                HStack(spacing: 8) {
                    Text(digest.currentStageText)
                    if let dwell = stop.dwellMinutes {
                        Text("停留 \(dwell) 分钟")
                    }
                    if !digest.routeLine.isEmpty {
                        Text("今天路线已整理")
                    }
                }
                .font(.caption.weight(.semibold))
                .foregroundStyle(DesignTokens.secondaryInk)
                .lineLimit(1)
                .minimumScaleFactor(0.72)
            }
        }
    }
}

private struct JourneyCoreRouteCard: View {
    var stops: [GuideDigestStop]
    var badge: String

    var body: some View {
        if !stops.isEmpty {
            SoftCard {
                HStack(alignment: .firstTextBaseline) {
                    Label("核心路线", systemImage: "list.number")
                        .font(.caption.weight(.bold))
                        .foregroundStyle(DesignTokens.dusk)
                    Spacer(minLength: 0)
                    Text(badge)
                        .font(.caption2.weight(.bold))
                        .foregroundStyle(DesignTokens.dusk)
                        .padding(.vertical, 4)
                        .padding(.horizontal, 8)
                        .background(DesignTokens.dusk.opacity(0.1))
                        .clipShape(Capsule())
                }

                VStack(alignment: .leading, spacing: 12) {
                    ForEach(Array(stops.enumerated()), id: \.element.id) { index, stop in
                        JourneyCoreStopRow(stop: stop, isLast: index == stops.count - 1)
                    }
                }
            }
        }
    }
}

private struct JourneyCoreStopRow: View {
    var stop: GuideDigestStop
    var isLast: Bool

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            VStack(spacing: 5) {
                ZStack {
                    Circle()
                        .fill(stop.tint.opacity(0.16))
                        .frame(width: 32, height: 32)
                    Text("\(stop.index)")
                        .font(.caption.weight(.black))
                        .foregroundStyle(stop.tint)
                }

                if !isLast {
                    Rectangle()
                        .fill(stop.tint.opacity(0.22))
                        .frame(width: 2, height: 42)
                }
            }

            VStack(alignment: .leading, spacing: 6) {
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    Text(stop.time)
                        .font(.caption.weight(.bold))
                        .foregroundStyle(stop.tint)
                    Text(stop.name)
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(DesignTokens.ink)
                        .lineLimit(2)
                    Spacer(minLength: 0)
                    Image(systemName: stop.systemImage)
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(stop.tint)
                }

                Text(stop.note)
                    .font(.footnote)
                    .foregroundStyle(DesignTokens.secondaryInk)
                    .lineSpacing(3)
                    .lineLimit(3)
                    .fixedSize(horizontal: false, vertical: true)

                if !stop.tags.isEmpty {
                    HStack(spacing: 6) {
                        ForEach(stop.tags, id: \.self) { tag in
                            Text(tag)
                                .font(.caption2.weight(.semibold))
                                .foregroundStyle(DesignTokens.secondaryInk)
                                .padding(.vertical, 4)
                                .padding(.horizontal, 7)
                                .background(.white.opacity(0.66))
                                .clipShape(Capsule())
                        }
                    }
                }
            }
        }
    }
}

private struct JourneySelectedMomentsCard: View {
    var digest: PetGuideDigest

    var body: some View {
        SoftCard {
            Label("TA 会寄回来的片段", systemImage: "sparkles")
                .font(.caption.weight(.bold))
                .foregroundStyle(DesignTokens.clay)

            VStack(alignment: .leading, spacing: 10) {
                ForEach(digest.memoryMoments) { moment in
                    JourneyMomentRow(moment: moment)
                }
            }
        }
    }
}

private struct JourneyMomentRow: View {
    var moment: GuideDigestMoment

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: moment.systemImage)
                .font(.caption.weight(.bold))
                .foregroundStyle(moment.tint)
                .frame(width: 30, height: 30)
                .background(moment.tint.opacity(0.13))
                .clipShape(Circle())

            VStack(alignment: .leading, spacing: 4) {
                Text(moment.title)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(DesignTokens.ink)
                Text(moment.detail.petSoulPetVoiceText)
                    .font(.footnote)
                    .foregroundStyle(DesignTokens.secondaryInk)
                    .lineSpacing(3)
                    .lineLimit(3)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(10)
        .background(.white.opacity(0.58))
        .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
    }
}

private struct PracticalGuideCard: View {
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

    private var practicalTitle: String {
        digest.routeBadge == "可参考"
            ? "这条路线可以作为 \(digest.city) 慢游参考"
            : "先跟着 \(digest.petName) 看看这一段"
    }

    private var qualityText: String {
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

private struct PracticalStopListCard: View {
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

private extension Array where Element == String {
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

private struct TravelGuideDigestCard: View {
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

private struct GuideDigestMetricChip: View {
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
        .background(.white.opacity(0.58))
        .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
    }
}

private struct GuideDigestRoutePreview: View {
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

private struct GuideDigestStopRow: View {
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

private struct RouteMovementDisclosureCard: View {
    var segments: [RouteSegment]
    var transports: [ScheduledTransportLeg]
    @State private var isExpanded = false

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

    private var summary: String {
        let movementCount = segments.filter { $0.mode != .stay && $0.mode != .checkIn }.count + transports.count
        if movementCount == 0 {
            return "没有需要展开的移动段"
        }
        return "\(movementCount) 段路，想看怎么到达时再展开"
    }
}

private extension DayPlanItem.Kind {
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

private struct JourneyPlanOverviewCard: View {
    var plan: JourneyPlan
    @State private var isRouteExpanded = false

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

private struct RouteSegmentRow: View {
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
        .background(.white.opacity(0.56))
        .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
    }

    private var routeLine: String {
        var parts = ["\(segment.fromPlace) → \(segment.toPlace)"]
        if let distance = segment.distanceMeters, distance > 0 {
            parts.append(distance >= 1_000 ? String(format: "%.1f km", Double(distance) / 1_000) : "\(distance) m")
        }
        if let seconds = segment.durationSeconds, seconds > 0 {
            parts.append("\(max(1, seconds / 60)) 分钟")
        }
        return parts.joined(separator: " · ")
    }

    private var tint: Color {
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

struct PostcardsView: View {
    var postcards: [Postcard]

    private var visiblePostcards: [Postcard] {
        var seenKeys = Set<String>()
        return postcards
            .sorted(by: { $0.timestamp > $1.timestamp })
            .filter { postcard in
                let normalizedText = postcard.text
                    .replacingOccurrences(of: #"\s+"#, with: " ", options: .regularExpression)
                    .trimmingCharacters(in: .whitespacesAndNewlines)
                let key = [
                    postcard.location,
                    normalizedText,
                    postcard.imageURL?.absoluteString ?? ""
                ].joined(separator: "|")
                return seenKeys.insert(key).inserted
            }
    }

    var body: some View {
        ZStack {
            AppBackground()

            if visiblePostcards.isEmpty {
                EmptyStateView(
                    title: "还没有明信片",
                    detail: "TA 可能正在路上。第一张明信片通常会在一段安静的停留后抵达。",
                    systemImage: "mail"
                )
            } else {
                ScrollView {
                    VStack(alignment: .leading, spacing: 16) {
                        VStack(alignment: .leading, spacing: 6) {
                            Text("明信片")
                                .font(.title2.weight(.semibold))
                                .foregroundStyle(DesignTokens.ink)
                            Text("TA 从另一端世界寄来的片段。")
                                .font(.subheadline)
                                .foregroundStyle(DesignTokens.secondaryInk)
                        }

                        ForEach(visiblePostcards) { postcard in
                            PostcardCard(postcard: postcard)
                        }
                    }
                    .padding(DesignTokens.pagePadding)
                }
            }
        }
        .navigationTitle("明信片")
        .navigationBarTitleDisplayMode(.inline)
    }
}

struct TravelKitSheetView: View {
    var petName: String
    var travelQuests: [TravelQuest]
    var travelBag: TravelBag?
    var souvenirs: [SouvenirItem]
    var economy: EconomyResponse?
    var isCreatingQuest: Bool
    var isPackingBag: Bool
    var isCollectingSouvenir: Bool
    var mutatingInventoryItemIDs: Set<String>
    @Binding var questMessage: String
    @Binding var bagMessage: String
    var onCreateQuest: () -> Void
    var onPackPreset: (TravelBagItemInput) -> Void
    var onPrepareDeparture: () -> Void
    var onCollectSouvenir: () -> Void
    var onShowSouvenirs: () -> Void
    var onSellSouvenir: (SouvenirItem) -> Void
    var onArchiveSouvenir: (SouvenirItem) -> Void

    private var activeQuest: TravelQuest? {
        travelQuests.first
    }

    var body: some View {
        ZStack {
            AppBackground()

            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    VStack(alignment: .leading, spacing: 6) {
                        Text("旅行小包")
                            .font(.title2.weight(.semibold))
                            .foregroundStyle(DesignTokens.ink)
                        Text("你可以轻轻准备，TA 会自己决定怎么走。")
                            .font(.subheadline)
                            .foregroundStyle(DesignTokens.secondaryInk)
                    }

                    TravelWishComposer(
                        text: $questMessage,
                        isLoading: isCreatingQuest,
                        onSubmit: onCreateQuest
                    )

                    if let activeQuest {
                        TravelQuestCard(
                            petName: petName,
                            quest: activeQuest,
                            isPreparing: isCreatingQuest,
                            isCollecting: isCollectingSouvenir,
                            onPrepareDeparture: onPrepareDeparture,
                            onCollectSouvenir: onCollectSouvenir
                        )
                    } else {
                        EmptyStateView(
                            title: "还没有支线旅行",
                            detail: "可以先告诉 TA 想去哪。TA 会先做攻略，不会立刻被推着出发。",
                            systemImage: "map"
                        )
                    }

                    TravelBagCard(
                        bag: travelBag,
                        message: $bagMessage,
                        isPacking: isPackingBag,
                        onPackPreset: onPackPreset
                    )

                    EconomySummaryCard(economy: economy)

                    Button(action: onShowSouvenirs) {
                        HStack(spacing: 10) {
                            Image(systemName: "gift.fill")
                                .font(.headline.weight(.semibold))
                            VStack(alignment: .leading, spacing: 2) {
                                Text("带回的小东西")
                                    .font(.subheadline.weight(.semibold))
                                Text(souvenirs.isEmpty ? "还没有收藏，等 TA 走完一段路。" : "\(souvenirs.count) 件小收藏已经放好")
                                    .font(.caption)
                            }
                            Spacer()
                            Image(systemName: "chevron.right")
                                .font(.caption.weight(.bold))
                        }
                        .foregroundStyle(DesignTokens.ink)
                    }
                    .buttonStyle(.plain)
                    .padding(14)
                    .background(.white.opacity(0.78))
                    .clipShape(RoundedRectangle(cornerRadius: DesignTokens.cardRadius, style: .continuous))
                    .overlay {
                        RoundedRectangle(cornerRadius: DesignTokens.cardRadius, style: .continuous)
                            .stroke(DesignTokens.softLine, lineWidth: 1)
                    }
                }
                .padding(DesignTokens.pagePadding)
            }
        }
        .navigationTitle("旅行小包")
        .navigationBarTitleDisplayMode(.inline)
    }
}

struct SouvenirsView: View {
    var souvenirs: [SouvenirItem]
    var economy: EconomyResponse? = nil
    var allowsActions = false
    var mutatingItemIDs: Set<String> = []
    var onSell: (SouvenirItem) -> Void = { _ in }
    var onArchive: (SouvenirItem) -> Void = { _ in }

    var body: some View {
        ZStack {
            AppBackground()

            if souvenirs.isEmpty {
                EmptyStateView(
                    title: "还没有带回物",
                    detail: "等 TA 完成一小段旅行，会带回玩具、票根、文创或一张小照片。",
                    systemImage: "gift"
                )
            } else {
                ScrollView {
                    VStack(alignment: .leading, spacing: 16) {
                        VStack(alignment: .leading, spacing: 6) {
                            Text("带回的小东西")
                                .font(.title2.weight(.semibold))
                                .foregroundStyle(DesignTokens.ink)
                            Text("不是商品，是 TA 从另一端世界带回来的记忆。")
                                .font(.subheadline)
                                .foregroundStyle(DesignTokens.secondaryInk)
                        }

                        EconomySummaryCard(economy: economy)

                        ForEach(souvenirs) { souvenir in
                            SouvenirCard(
                                souvenir: souvenir,
                                allowsActions: allowsActions,
                                isMutating: mutatingItemIDs.contains(souvenir.id),
                                onSell: { onSell(souvenir) },
                                onArchive: { onArchive(souvenir) }
                            )
                        }
                    }
                    .padding(DesignTokens.pagePadding)
                }
            }
        }
        .navigationTitle("小收藏")
        .navigationBarTitleDisplayMode(.inline)
    }
}

private struct EconomySummaryCard: View {
    var economy: EconomyResponse?

    var body: some View {
        SoftCard {
            HStack(alignment: .top, spacing: 12) {
                PetSoulAssetIcon(
                    asset: .memoryTray,
                    fallbackSystemImage: "bag.fill",
                    fallbackTint: DesignTokens.sage,
                    size: 34
                )
                VStack(alignment: .leading, spacing: 4) {
                    Text("小背包")
                        .font(.headline.weight(.semibold))
                        .foregroundStyle(DesignTokens.ink)
                    Text(walletLine)
                        .font(.caption)
                        .foregroundStyle(DesignTokens.secondaryInk)
                }
                Spacer(minLength: 0)
            }

            LazyVGrid(columns: [GridItem(.adaptive(minimum: 108), spacing: 8)], spacing: 8) {
                EconomyMetricTile(title: "背包价值", value: valueText(economy?.snapshot.totalDisplayValue), tint: DesignTokens.sage)
                EconomyMetricTile(title: "可出售", value: valueText(economy?.snapshot.sellableValue), tint: DesignTokens.amber)
                EconomyMetricTile(title: "收藏", value: valueText(economy?.snapshot.collectionValue), tint: DesignTokens.clay)
                EconomyMetricTile(title: "荣誉", value: valueText(economy?.snapshot.honorValue), tint: DesignTokens.dusk)
            }

            if let latest = economy?.recentTransactions.first {
                Label(latest.reason, systemImage: "clock.fill")
                    .font(.caption)
                    .foregroundStyle(DesignTokens.secondaryInk)
                    .lineLimit(2)
            }
        }
    }

    private var walletLine: String {
        guard let wallet = economy?.wallet else {
            return "旅贝 0 · 星尘 0 · 功勋 0"
        }
        return "旅贝 \(wallet.travelCoin) · 星尘 \(wallet.starDust) · 功勋 \(wallet.merit)"
    }

    private func valueText(_ value: Int?) -> String {
        "\(value ?? 0)"
    }
}

private struct EconomyMetricTile: View {
    var title: String
    var value: String
    var tint: Color

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(value)
                .font(.subheadline.weight(.bold))
                .foregroundStyle(DesignTokens.ink)
                .lineLimit(1)
                .minimumScaleFactor(0.75)
            Text(title)
                .font(.caption2.weight(.semibold))
                .foregroundStyle(DesignTokens.secondaryInk)
                .lineLimit(1)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.vertical, 9)
        .padding(.horizontal, 10)
        .background(tint.opacity(0.12))
        .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
    }
}

private struct TravelWishComposer: View {
    @Binding var text: String
    var isLoading: Bool
    var onSubmit: () -> Void

    var body: some View {
        SoftCard {
            Label("告诉 TA 一个想去的地方", systemImage: "paperplane.fill")
                .font(.caption.weight(.bold))
                .foregroundStyle(DesignTokens.sage)

            TextField("比如：明天去世界杯看德国队比赛，先做攻略", text: $text, axis: .vertical)
                .lineLimit(2...4)
                .font(.body)
                .textFieldStyle(.plain)
                .padding(12)
                .background(.white.opacity(0.76))
                .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))

            Button(action: onSubmit) {
                HStack {
                    if isLoading {
                        ProgressView()
                            .tint(.white)
                    }
                    Label("让 TA 先做攻略", systemImage: "sparkles")
                        .frame(maxWidth: .infinity)
                }
            }
            .buttonStyle(.borderedProminent)
            .tint(DesignTokens.sage)
            .disabled(text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || isLoading)
        }
    }
}

private struct TravelQuestCard: View {
    var petName: String
    var quest: TravelQuest
    var isPreparing: Bool
    var isCollecting: Bool
    var onPrepareDeparture: () -> Void
    var onCollectSouvenir: () -> Void
    @State private var isGuideExpanded = true

    var body: some View {
        SoftCard {
            HStack(alignment: .top, spacing: 10) {
                Image(systemName: quest.worldcupEvent ? "sportscourt.fill" : "map.fill")
                    .font(.headline.weight(.bold))
                    .foregroundStyle(quest.worldcupEvent ? DesignTokens.clay : DesignTokens.sage)
                    .frame(width: 38, height: 38)
                    .background((quest.worldcupEvent ? DesignTokens.clay : DesignTokens.sage).opacity(0.13))
                    .clipShape(Circle())

                VStack(alignment: .leading, spacing: 4) {
                    Text(quest.questType.displayName)
                        .font(.caption.weight(.bold))
                        .foregroundStyle(DesignTokens.secondaryInk)
                    Text(quest.guide?.title ?? "\(petName) 的旅行愿望")
                        .font(.headline.weight(.semibold))
                        .foregroundStyle(DesignTokens.ink)
                        .fixedSize(horizontal: false, vertical: true)
                    Text(quest.status.displayName)
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(DesignTokens.sage)
                }
                Spacer(minLength: 0)
            }

            Text((quest.guide?.petVoice ?? quest.currentPhaseMessage).petSoulPetVoiceText)
                .font(.subheadline)
                .foregroundStyle(DesignTokens.secondaryInk)
                .lineSpacing(3)

            if let guide = quest.guide {
                TravelQuestGuideSnapshot(guide: guide)

                DisclosureGroup(isExpanded: $isGuideExpanded) {
                    VStack(alignment: .leading, spacing: 9) {
                        Text(guide.summary.petSoulPetVoiceText)
                            .font(.footnote)
                            .foregroundStyle(DesignTokens.secondaryInk)
                            .lineSpacing(3)
                        ForEach(guide.stops.prefix(4)) { stop in
                            TravelQuestStopRow(stop: stop)
                        }
                    }
                    .padding(.top, 8)
                } label: {
                    Label("TA 整理的路线", systemImage: "list.bullet.rectangle")
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(DesignTokens.ink)
                }
            }

            HStack(spacing: 10) {
                Button(action: onPrepareDeparture) {
                    if isPreparing {
                        ProgressView()
                            .tint(DesignTokens.sage)
                            .frame(maxWidth: .infinity)
                    } else {
                        Label("准备出发", systemImage: "figure.walk")
                            .frame(maxWidth: .infinity)
                    }
                }
                .quietActionStyle()
                .disabled(isPreparing)

                Button(action: onCollectSouvenir) {
                    if isCollecting {
                        ProgressView()
                            .tint(DesignTokens.clay)
                            .frame(maxWidth: .infinity)
                    } else {
                        Label("看看带回物", systemImage: "gift.fill")
                            .frame(maxWidth: .infinity)
                    }
                }
                .quietActionStyle()
                .disabled(isCollecting)
            }
        }
    }
}

private struct TravelQuestGuideSnapshot: View {
    var guide: TravelQuestGuide

    var body: some View {
        VStack(alignment: .leading, spacing: 11) {
            HStack(alignment: .top, spacing: 10) {
                Image(systemName: "map.circle.fill")
                    .font(.title3.weight(.semibold))
                    .foregroundStyle(DesignTokens.sage)
                VStack(alignment: .leading, spacing: 4) {
                    Text("TA 先替你查了一遍")
                        .font(.caption.weight(.bold))
                        .foregroundStyle(DesignTokens.secondaryInk)
                    Text(guide.routeTheme.petSoulUserFacingText)
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(DesignTokens.ink)
                        .fixedSize(horizontal: false, vertical: true)
                }
                Spacer(minLength: 0)
            }

            HStack(spacing: 8) {
                TravelQuestGuidePill(title: "\(guide.cities.joined(separator: " → "))", systemImage: "mappin.and.ellipse")
                TravelQuestGuidePill(title: "\(guide.stops.count) 站", systemImage: "list.number")
            }

            if !guide.transportOutline.isEmpty {
                VStack(alignment: .leading, spacing: 7) {
                    Text("怎么过去")
                        .font(.caption.weight(.bold))
                        .foregroundStyle(DesignTokens.secondaryInk)
                    ForEach(guide.transportOutline.prefix(3)) { leg in
                        HStack(alignment: .top, spacing: 8) {
                            Image(systemName: leg.mode.systemImage)
                                .font(.caption.weight(.bold))
                                .foregroundStyle(transportTint(leg.mode))
                                .frame(width: 24, height: 24)
                                .background(transportTint(leg.mode).opacity(0.12))
                                .clipShape(Circle())
                            VStack(alignment: .leading, spacing: 2) {
                                Text("\(leg.fromPlace) → \(leg.toPlace)")
                                    .font(.caption.weight(.semibold))
                                    .foregroundStyle(DesignTokens.ink)
                                    .lineLimit(2)
                                Text("\(leg.mode.displayName) · \(leg.estimatedDuration) · \(leg.note.petSoulUserFacingText)")
                                    .font(.caption2)
                                    .foregroundStyle(DesignTokens.secondaryInk)
                                    .lineLimit(3)
                                    .fixedSize(horizontal: false, vertical: true)
                            }
                        }
                    }
                }
            }

            if let research = guide.research, hasResearchFindings(research) {
                VStack(alignment: .leading, spacing: 7) {
                    Text("攻略线索")
                        .font(.caption.weight(.bold))
                        .foregroundStyle(DesignTokens.secondaryInk)
                    if let socialFindings = research.socialFindings, !socialFindings.isEmpty {
                        ForEach(Array(socialFindings.prefix(3).enumerated()), id: \.offset) { _, finding in
                            VStack(alignment: .leading, spacing: 3) {
                                Label(finding.claim.petSoulUserFacingText, systemImage: socialFindingIcon(finding.evidenceType))
                                    .font(.caption)
                                    .foregroundStyle(DesignTokens.secondaryInk)
                                    .lineLimit(2)
                                if let risk = finding.risk?.petSoulUserFacingText, !risk.isEmpty {
                                    Text(risk)
                                        .font(.caption2)
                                        .foregroundStyle(DesignTokens.secondaryInk.opacity(0.78))
                                        .lineLimit(1)
                                }
                            }
                        }
                    } else {
                        ForEach(Array(research.findings.prefix(3).enumerated()), id: \.offset) { _, finding in
                            Label(finding.petSoulUserFacingText, systemImage: "magnifyingglass")
                                .font(.caption)
                                .foregroundStyle(DesignTokens.secondaryInk)
                                .lineLimit(2)
                        }
                    }
                }
            }

            if !guide.preparationNotes.isEmpty {
                VStack(alignment: .leading, spacing: 7) {
                    Text("出发前先确认")
                        .font(.caption.weight(.bold))
                        .foregroundStyle(DesignTokens.secondaryInk)
                    ForEach(Array(guide.preparationNotes.prefix(3).enumerated()), id: \.offset) { _, note in
                        Label(note.petSoulUserFacingText, systemImage: "checkmark.circle.fill")
                            .font(.caption)
                            .foregroundStyle(DesignTokens.secondaryInk)
                            .lineLimit(2)
                    }
                }
            }
        }
        .padding(12)
        .background(DesignTokens.mist.opacity(0.54))
        .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
    }

    private func transportTint(_ mode: TravelMode) -> Color {
        switch mode {
        case .flight, .train, .transit:
            DesignTokens.dusk
        case .drive, .ferry:
            DesignTokens.amber
        case .walk:
            DesignTokens.sage
        case .stay, .checkIn:
            DesignTokens.clay
        }
    }

    private func hasResearchFindings(_ research: TravelGuideResearch) -> Bool {
        !(research.socialFindings?.isEmpty ?? true) || !research.findings.isEmpty
    }

    private func socialFindingIcon(_ type: String?) -> String {
        switch type {
        case "photo_anchor":
            "camera.viewfinder"
        case "local_food":
            "fork.knife"
        case "avoid_note":
            "exclamationmark.triangle"
        case "time_window":
            "clock"
        default:
            "magnifyingglass"
        }
    }
}

private struct TravelQuestGuidePill: View {
    var title: String
    var systemImage: String

    var body: some View {
        Label(title, systemImage: systemImage)
            .font(.caption.weight(.semibold))
            .foregroundStyle(DesignTokens.ink)
            .lineLimit(1)
            .minimumScaleFactor(0.72)
            .frame(maxWidth: .infinity)
            .padding(.vertical, 8)
            .padding(.horizontal, 9)
            .background(.white.opacity(0.58))
            .clipShape(RoundedRectangle(cornerRadius: 13, style: .continuous))
    }
}

private struct TravelQuestStopRow: View {
    var stop: TravelQuestStop

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Text(stop.plannedTime ?? "途中")
                .font(.caption.weight(.bold))
                .foregroundStyle(DesignTokens.dusk)
                .frame(width: 58, alignment: .leading)

            VStack(alignment: .leading, spacing: 4) {
                Text(stop.name)
                    .font(.footnote.weight(.semibold))
                    .foregroundStyle(DesignTokens.ink)
                Text(stop.petVoice.petSoulPetVoiceText)
                    .font(.caption)
                    .foregroundStyle(DesignTokens.secondaryInk)
                    .lineLimit(3)
            }
        }
        .padding(.vertical, 8)
        .padding(.horizontal, 10)
        .background(.white.opacity(0.56))
        .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
    }
}

private struct TravelBagCard: View {
    var bag: TravelBag?
    @Binding var message: String
    var isPacking: Bool
    var onPackPreset: (TravelBagItemInput) -> Void

    var body: some View {
        SoftCard {
            PetSoulAssetLabel(
                title: "小包里现在有",
                asset: .travelBag,
                fallbackSystemImage: "bag.fill",
                tint: DesignTokens.clay,
                iconSize: 22
            )
                .font(.caption.weight(.bold))
                .foregroundStyle(DesignTokens.clay)

            Text(bag?.petVisibleNote ?? "这只小包还空着。出发前可以放一点小零食、护身符，或一句想让 TA 带着走的话。")
                .font(.subheadline)
                .foregroundStyle(DesignTokens.secondaryInk)
                .lineSpacing(3)

            if let bag, !bag.items.isEmpty {
                LazyVGrid(columns: [GridItem(.adaptive(minimum: 138), spacing: 8)], spacing: 8) {
                    ForEach(bag.items.suffix(8)) { item in
                        TravelBagItemChip(item: item)
                    }
                }
            }

            TextField("留一句装进小包的话", text: $message)
                .font(.subheadline)
                .textFieldStyle(.plain)
                .padding(12)
                .background(.white.opacity(0.72))
                .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))

            LazyVGrid(columns: [GridItem(.adaptive(minimum: 142), spacing: 8)], spacing: 8) {
                ForEach(TravelBagPreset.allCases) { preset in
                    Button {
                        onPackPreset(preset.itemInput)
                    } label: {
                        PetSoulAssetLabel(
                            title: preset.title,
                            asset: preset.asset,
                            fallbackSystemImage: preset.systemImage,
                            tint: DesignTokens.sage,
                            iconSize: 22
                        )
                            .font(.caption.weight(.semibold))
                            .frame(maxWidth: .infinity, minHeight: 34)
                    }
                    .quietActionStyle()
                    .disabled(isPacking)
                }
            }
        }
    }
}

private struct TravelBagItemChip: View {
    var item: TravelBagItem

    var body: some View {
        HStack(spacing: 7) {
            PetSoulAssetIcon(
                asset: item.itemType.petSoulAsset,
                fallbackSystemImage: item.itemType.systemImage,
                fallbackTint: DesignTokens.sage,
                size: 22
            )
            VStack(alignment: .leading, spacing: 1) {
                Text(item.title)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(DesignTokens.ink)
                    .lineLimit(1)
                Text(item.itemType.displayName)
                    .font(.caption2)
                    .foregroundStyle(DesignTokens.secondaryInk)
            }
        }
        .padding(.vertical, 8)
        .padding(.horizontal, 9)
        .background(.white.opacity(0.62))
        .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
    }
}

private extension TravelBagItemType {
    var petSoulAsset: PetSoulAsset {
        switch self {
        case .snack:
            .travelPropPaperBag
        case .comfortItem:
            .travelPropBlanket
        case .guideHint:
            .travelPropFoldedMap
        case .luckyCharm:
            .travelPropBell
        case .musicHint:
            .musicNote
        case .toy:
            .travelPropPetScarf
        }
    }
}

private enum TravelBagPreset: String, CaseIterable, Identifiable {
    case snack
    case charm
    case guide
    case music

    var id: String { rawValue }

    var title: String {
        switch self {
        case .snack: "放小零食"
        case .charm: "放护身符"
        case .guide: "放想看的地方"
        case .music: "放一首歌"
        }
    }

    var systemImage: String {
        switch self {
        case .snack: "takeoutbag.and.cup.and.straw.fill"
        case .charm: "sparkles"
        case .guide: "map.fill"
        case .music: "headphones"
        }
    }

    var asset: PetSoulAsset {
        switch self {
        case .snack: .travelPropPaperBag
        case .charm: .travelPropBell
        case .guide: .travelPropFoldedMap
        case .music: .musicNote
        }
    }

    var itemInput: TravelBagItemInput {
        switch self {
        case .snack:
            TravelBagItemInput(
                itemType: .snack,
                title: "路上小零食",
                note: "累的时候闻一闻就好",
                influenceTags: ["comfort", "slow_travel"]
            )
        case .charm:
            TravelBagItemInput(
                itemType: .luckyCharm,
                title: "小小护身符",
                note: "提醒 TA 不要赶路",
                influenceTags: ["return_home", "rare_photo"]
            )
        case .guide:
            TravelBagItemInput(
                itemType: .guideHint,
                title: "想看的街角",
                note: "如果路过就看一眼",
                influenceTags: ["local_life", "souvenir"]
            )
        case .music:
            TravelBagItemInput(
                itemType: .musicHint,
                title: "路上的歌",
                note: "让旅程安静一点",
                influenceTags: ["rest", "soft_mood"]
            )
        }
    }
}

private extension SouvenirItemType {
    var petSoulAsset: PetSoulAsset {
        switch self {
        case .toy:
            .travelPropPetScarf
        case .culturalCreative:
            .travelPropStamp
        case .foundObject:
            .travelPropSeashell
        case .ticketStub:
            .travelPropPostcard
        case .charm:
            .travelPropPhotoCharm
        case .snackPack:
            .travelPropPaperBag
        case .photoPrint:
            .travelPropPostcard
        }
    }
}

private struct SouvenirCard: View {
    var souvenir: SouvenirItem
    var allowsActions = false
    var isMutating = false
    var onSell: () -> Void = {}
    var onArchive: () -> Void = {}

    var body: some View {
        SoftCard {
            HStack(alignment: .top, spacing: 12) {
                PetSoulAssetIcon(
                    asset: souvenir.itemType.petSoulAsset,
                    fallbackSystemImage: souvenir.itemType.systemImage,
                    fallbackTint: tint,
                    size: 38
                )
                    .frame(width: 42, height: 42)
                    .background(tint.opacity(0.14))
                    .clipShape(Circle())

                VStack(alignment: .leading, spacing: 5) {
                    Text(souvenir.itemType.displayName)
                        .font(.caption.weight(.bold))
                        .foregroundStyle(DesignTokens.secondaryInk)
                    Text(souvenir.title)
                        .font(.headline.weight(.semibold))
                        .foregroundStyle(DesignTokens.ink)
                    Text("\(souvenir.city) · \(souvenir.placeName)")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(DesignTokens.sage)
                }
                Spacer(minLength: 0)
                Text(statusBadge)
                    .font(.caption2.weight(.bold))
                    .foregroundStyle(tint)
                    .padding(.vertical, 5)
                    .padding(.horizontal, 8)
                    .background(tint.opacity(0.12))
                    .clipShape(Capsule())
            }

            if let imageURL = souvenir.imageURL {
                PostcardImageView(url: imageURL, height: 172)
            }

            Text(souvenir.subtitle)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(DesignTokens.ink)

            Text(souvenir.story.petSoulPetVoiceText)
                .font(.footnote)
                .foregroundStyle(DesignTokens.secondaryInk)
                .lineSpacing(3)

            Text("“\(souvenir.petVoice.petSoulPetVoiceText)”")
                .font(.subheadline)
                .foregroundStyle(DesignTokens.ink)
                .lineSpacing(3)
                .padding(12)
                .background(DesignTokens.mist.opacity(0.62))
                .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))

            HStack(spacing: 8) {
                SouvenirValuePill(title: "可出售", value: "\(souvenir.resaleValue) 旅贝", tint: DesignTokens.amber)
                SouvenirValuePill(title: "收藏", value: "\(souvenir.displayEmotionalValue)", tint: DesignTokens.clay)
                if souvenir.displayHonorValue > 0 {
                    SouvenirValuePill(title: "荣誉", value: "\(souvenir.displayHonorValue)", tint: DesignTokens.dusk)
                }
            }

            Text(originLine)
                .font(.caption)
                .foregroundStyle(DesignTokens.secondaryInk)
                .lineLimit(2)

            if allowsActions && souvenir.effectiveStatus == .owned {
                HStack(spacing: 10) {
                    Button(action: onArchive) {
                        Label("珍藏", systemImage: "archivebox.fill")
                            .frame(maxWidth: .infinity)
                    }
                    .quietActionStyle()
                    .disabled(isMutating)

                    Button(action: onSell) {
                        if isMutating {
                            ProgressView()
                                .tint(DesignTokens.amber)
                                .frame(maxWidth: .infinity)
                        } else {
                            Label("出售", systemImage: "shell.fill")
                                .frame(maxWidth: .infinity)
                        }
                    }
                    .quietActionStyle()
                    .disabled(!souvenir.isSellable || isMutating)
                }
            }
        }
    }

    private var statusBadge: String {
        switch souvenir.effectiveStatus {
        case .sold:
            "已出售"
        case .archived:
            "珍藏"
        default:
            souvenir.rarity == "rare" ? "少见" : "小物"
        }
    }

    private var originLine: String {
        let city = souvenir.originCity ?? souvenir.city
        let place = souvenir.originPOIName ?? souvenir.placeName
        if let weather = souvenir.originWeather, !weather.isEmpty {
            return "\(city) · \(place) · \(weather)"
        }
        return "\(city) · \(place)"
    }

    private var tint: Color {
        switch souvenir.itemType {
        case .ticketStub:
            DesignTokens.clay
        case .photoPrint:
            DesignTokens.dusk
        case .culturalCreative, .charm:
            DesignTokens.sage
        case .snackPack:
            DesignTokens.amber
        case .toy:
            DesignTokens.pollen
        case .foundObject:
            DesignTokens.secondaryInk
        }
    }
}

private struct SouvenirValuePill: View {
    var title: String
    var value: String
    var tint: Color

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(value)
                .font(.caption.weight(.bold))
                .foregroundStyle(DesignTokens.ink)
                .lineLimit(1)
                .minimumScaleFactor(0.75)
            Text(title)
                .font(.caption2.weight(.semibold))
                .foregroundStyle(DesignTokens.secondaryInk)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.vertical, 7)
        .padding(.horizontal, 9)
        .background(tint.opacity(0.12))
        .clipShape(RoundedRectangle(cornerRadius: 13, style: .continuous))
    }
}

struct DNASettingsView: View {
    var dna: PetDNA?
    var isSaving = false
    var onSave: (PetDNA) -> Void = { _ in }

    @State private var isEditing = false
    @State private var ownerTitle: String
    @State private var personality: String
    @State private var catchphrase: String
    @State private var voiceStyle: String
    @State private var emojiPreference: String
    @State private var favoritePlaces: [String]
    @State private var hobbies: [String]
    @State private var favoritePlaceDraft = ""
    @State private var hobbyDraft = ""

    init(dna: PetDNA?, isSaving: Bool = false, onSave: @escaping (PetDNA) -> Void = { _ in }) {
        self.dna = dna
        self.isSaving = isSaving
        self.onSave = onSave
        let seed = dna ?? .fallback
        _ownerTitle = State(initialValue: seed.ownerTitle)
        _personality = State(initialValue: seed.personality)
        _catchphrase = State(initialValue: seed.catchphrase)
        _voiceStyle = State(initialValue: seed.voiceStyle)
        _emojiPreference = State(initialValue: seed.emojiPreference)
        _favoritePlaces = State(initialValue: seed.favoritePlaces)
        _hobbies = State(initialValue: seed.hobbies)
    }

    private var draftDNA: PetDNA {
        PetDNA(
            ownerTitle: ownerTitle.trimmedNonEmpty(fallback: dna?.ownerTitle ?? PetDNA.fallback.ownerTitle),
            personality: personality.trimmedNonEmpty(fallback: dna?.personality ?? PetDNA.fallback.personality),
            favoritePlaces: favoritePlaces.cleanedTags(fallback: dna?.favoritePlaces ?? PetDNA.fallback.favoritePlaces),
            hobbies: hobbies.cleanedTags(fallback: dna?.hobbies ?? PetDNA.fallback.hobbies),
            catchphrase: catchphrase.trimmedNonEmpty(fallback: dna?.catchphrase ?? PetDNA.fallback.catchphrase),
            emojiPreference: emojiPreference.trimmedNonEmpty(fallback: dna?.emojiPreference ?? PetDNA.fallback.emojiPreference),
            voiceStyle: voiceStyle.trimmedNonEmpty(fallback: dna?.voiceStyle ?? PetDNA.fallback.voiceStyle)
        )
    }

    private var canSave: Bool {
        guard let dna else { return false }
        return !isSaving && draftDNA != dna
    }

    var body: some View {
        ZStack {
            AppBackground()

            if let dna {
                ScrollView {
                    VStack(alignment: .leading, spacing: 16) {
                        HStack(alignment: .top, spacing: 12) {
                            VStack(alignment: .leading, spacing: 6) {
                                Text("通讯 DNA")
                                    .font(.title2.weight(.semibold))
                                    .foregroundStyle(DesignTokens.ink)
                                Text(isEditing ? "保存后会影响 TA 的旅程语气，并写入记忆档案。" : "这些偏好会慢慢影响 TA 的旅程语气。")
                                    .font(.subheadline)
                                    .foregroundStyle(DesignTokens.secondaryInk)
                            }
                            Spacer(minLength: 0)
                            HStack(spacing: 8) {
                                Button {
                                    if isEditing {
                                        resetDraft(from: dna)
                                    }
                                    isEditing.toggle()
                                } label: {
                                    Image(systemName: isEditing ? "xmark" : "pencil")
                                        .frame(width: 38, height: 38)
                                }
                                .buttonStyle(.plain)
                                .foregroundStyle(DesignTokens.ink)
                                .background(DesignTokens.mist.opacity(0.7))
                                .clipShape(Circle())
                                .accessibilityLabel(isEditing ? "取消编辑" : "编辑通讯 DNA")

                                if isEditing {
                                    Button {
                                        onSave(draftDNA)
                                        isEditing = false
                                    } label: {
                                        if isSaving {
                                            ProgressView()
                                                .frame(width: 38, height: 38)
                                        } else {
                                            Image(systemName: "checkmark")
                                                .frame(width: 38, height: 38)
                                        }
                                    }
                                    .buttonStyle(.plain)
                                    .foregroundStyle(.white)
                                    .background(canSave ? DesignTokens.sage : DesignTokens.secondaryInk.opacity(0.28))
                                    .clipShape(Circle())
                                    .disabled(!canSave)
                                    .accessibilityLabel("保存通讯 DNA")
                                }
                            }
                        }

                        DNAEditableField(title: "称呼", value: $ownerTitle, systemImage: "person", isEditing: isEditing)
                        DNAEditableField(title: "性格", value: $personality, systemImage: "sparkles", isEditing: isEditing, minHeight: 58)
                        DNAEditableField(title: "口头禅", value: $catchphrase, systemImage: "text.bubble", isEditing: isEditing)
                        DNAEditableField(title: "说话风格", value: $voiceStyle, systemImage: "waveform", isEditing: isEditing, minHeight: 58)
                        DNAEditableField(title: "语气标记", value: $emojiPreference, systemImage: "wand.and.stars", isEditing: isEditing)
                        DNAEditableListField(title: "喜欢的地方", values: $favoritePlaces, draft: $favoritePlaceDraft, systemImage: "mappin.and.ellipse", isEditing: isEditing)
                        DNAEditableListField(title: "爱好", values: $hobbies, draft: $hobbyDraft, systemImage: "sun.max", isEditing: isEditing)
                    }
                    .padding(DesignTokens.pagePadding)
                }
            } else {
                EmptyStateView(
                    title: "DNA 暂未同步",
                    detail: "手机还没有读到 TA 的完整偏好。",
                    systemImage: "slider.horizontal.3"
                )
            }
        }
        .navigationTitle("通讯 DNA")
        .navigationBarTitleDisplayMode(.inline)
        .onChange(of: dna) { _, nextDNA in
            if let nextDNA, !isEditing {
                resetDraft(from: nextDNA)
            }
        }
    }

    private func resetDraft(from dna: PetDNA) {
        ownerTitle = dna.ownerTitle
        personality = dna.personality
        catchphrase = dna.catchphrase
        voiceStyle = dna.voiceStyle
        emojiPreference = dna.emojiPreference
        favoritePlaces = dna.favoritePlaces
        hobbies = dna.hobbies
        favoritePlaceDraft = ""
        hobbyDraft = ""
    }
}

private struct DNAEditableField: View {
    var title: String
    @Binding var value: String
    var systemImage: String
    var isEditing: Bool
    var minHeight: CGFloat = 0

    var body: some View {
        SoftCard {
            Label(title, systemImage: systemImage)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(DesignTokens.secondaryInk)

            if isEditing {
                TextField(title, text: $value, axis: .vertical)
                    .font(.body.weight(.medium))
                    .foregroundStyle(DesignTokens.ink)
                    .lineLimit(1...4)
                    .padding(10)
                    .frame(minHeight: minHeight, alignment: .topLeading)
                    .background(DesignTokens.mist.opacity(0.72))
                    .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
            } else {
                Text(value)
                    .font(.body.weight(.medium))
                    .foregroundStyle(DesignTokens.ink)
                    .frame(maxWidth: .infinity, minHeight: minHeight, alignment: .leading)
            }
        }
    }
}

private struct DNAEditableListField: View {
    var title: String
    @Binding var values: [String]
    @Binding var draft: String
    var systemImage: String
    var isEditing: Bool

    var body: some View {
        SoftCard {
            Label(title, systemImage: systemImage)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(DesignTokens.secondaryInk)

            LazyVGrid(columns: [GridItem(.adaptive(minimum: 88), spacing: 8)], alignment: .leading, spacing: 8) {
                ForEach(values.indices, id: \.self) { index in
                    HStack(spacing: 6) {
                        Text(values[index])
                            .font(.subheadline.weight(.medium))
                            .foregroundStyle(DesignTokens.ink)
                            .lineLimit(1)
                        if isEditing {
                            Button {
                                values.remove(at: index)
                            } label: {
                                Image(systemName: "xmark")
                                    .font(.caption2.weight(.bold))
                            }
                            .buttonStyle(.plain)
                            .foregroundStyle(DesignTokens.secondaryInk)
                        }
                    }
                    .padding(.vertical, 8)
                    .padding(.horizontal, 10)
                    .background(DesignTokens.mist)
                    .clipShape(Capsule())
                }
            }

            if isEditing {
                HStack(spacing: 8) {
                    TextField("新增\(title)", text: $draft)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .font(.subheadline)
                        .padding(10)
                        .background(DesignTokens.mist.opacity(0.72))
                        .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
                        .onSubmit(addDraft)

                    Button(action: addDraft) {
                        Image(systemName: "plus")
                            .frame(width: 36, height: 36)
                    }
                    .buttonStyle(.plain)
                    .foregroundStyle(.white)
                    .background(draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? DesignTokens.secondaryInk.opacity(0.28) : DesignTokens.sage)
                    .clipShape(Circle())
                    .disabled(draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                }
            }
        }
    }

    private func addDraft() {
        let item = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !item.isEmpty else { return }
        if !values.contains(item) {
            values.append(item)
        }
        draft = ""
    }
}

private struct PetGuideSummaryCard: View {
    var guide: PetAuthoredGuide

    var body: some View {
        SoftCard {
            Label("TA 的小想法", systemImage: "sparkles")
                .font(.caption.weight(.bold))
                .foregroundStyle(DesignTokens.clay)

            Text(guide.title)
                .font(.title3.weight(.semibold))
                .foregroundStyle(DesignTokens.ink)

            Text(guide.animalText.petSoulUserFacingText)
                .font(.headline.weight(.semibold))
                .foregroundStyle(DesignTokens.ink)

            Text(guide.translation.petSoulPetVoiceText)
                .font(.subheadline)
                .foregroundStyle(DesignTokens.secondaryInk)
                .lineSpacing(3)

            ForEach(guide.guideStops) { stop in
                VStack(alignment: .leading, spacing: 5) {
                    HStack(alignment: .firstTextBaseline, spacing: 8) {
                        Text(stop.plannedTime ?? "--:--")
                            .font(.caption.weight(.bold))
                            .foregroundStyle(DesignTokens.dusk)
                        Text(stop.name)
                            .font(.subheadline.weight(.semibold))
                            .foregroundStyle(DesignTokens.ink)
                            .lineLimit(1)
                        Spacer(minLength: 0)
                        Label("\(stop.dwellMinutes) 分钟", systemImage: "hourglass")
                            .font(.caption2.weight(.semibold))
                            .foregroundStyle(DesignTokens.secondaryInk)
                    }
                    Text(stop.petReason.petSoulPetVoiceText)
                        .font(.footnote)
                        .foregroundStyle(DesignTokens.secondaryInk)
                        .lineLimit(3)
                }
                .padding(.vertical, 8)
                .padding(.horizontal, 10)
                .background(.white.opacity(0.52))
                .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
            }
        }
    }
}

private struct GuideInfoChip: View {
    var title: String
    var value: String
    var systemImage: String

    var body: some View {
        HStack(spacing: 6) {
            Image(systemName: systemImage)
                .font(.caption.weight(.semibold))
                .foregroundStyle(DesignTokens.sage)
            VStack(alignment: .leading, spacing: 1) {
                Text(title)
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(DesignTokens.secondaryInk)
                Text(value)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(DesignTokens.ink)
                    .lineLimit(2)
                    .minimumScaleFactor(0.78)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.vertical, 8)
        .padding(.horizontal, 9)
        .background(.white.opacity(0.66))
        .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
    }
}

private enum DayPlanTimelinePhase: Equatable {
    case past
    case current
    case upcoming

    var label: String {
        switch self {
        case .past: "已完成"
        case .current: "正在发生"
        case .upcoming: "计划中"
        }
    }

    var opacity: Double {
        switch self {
        case .past: 0.56
        case .current: 1.0
        case .upcoming: 0.76
        }
    }
}

private struct TimelineItemView: View {
    var item: DayPlanItem
    var phase: DayPlanTimelinePhase

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            VStack(spacing: 8) {
                Circle()
                    .fill(color)
                    .frame(width: phase == .current ? 15 : 12, height: phase == .current ? 15 : 12)
                    .overlay {
                        if phase == .current {
                            Circle()
                                .stroke(color.opacity(0.25), lineWidth: 7)
                        }
                    }
                Rectangle()
                    .fill(DesignTokens.softLine.opacity(phase == .past ? 0.5 : 1))
                    .frame(width: 2, height: 58)
            }
            .padding(.top, 6)

            SoftCard {
                HStack {
                    Text(item.time)
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(color)
                    Spacer()
                    Text(phase.label)
                        .font(.caption2.weight(.bold))
                        .foregroundStyle(phase == .current ? color : DesignTokens.secondaryInk.opacity(0.72))
                }

                Text(item.title)
                    .font(.headline)
                    .foregroundStyle(DesignTokens.ink)
                Text(phaseAdjustedDetail)
                    .font(.subheadline)
                    .foregroundStyle(DesignTokens.secondaryInk)
                    .lineSpacing(3)
            }
            .opacity(phase.opacity)
        }
    }

    private var phaseAdjustedDetail: String {
        var text = item.detail.petSoulPetVoiceText
        switch phase {
        case .past:
            text = text.replacingOccurrences(of: "我会", with: "我已经")
            text = text.replacingOccurrences(of: "我先", with: "我当时先")
            return "记录：\(text)"
        case .current:
            return "正在发生：\(text)"
        case .upcoming:
            return "计划：\(text)"
        }
    }

    private var color: Color {
        switch item.kind {
        case .morning: DesignTokens.sage
        case .noon: DesignTokens.clay
        case .afternoon: DesignTokens.dusk
        case .evening: DesignTokens.ink
        }
    }
}

private struct TimelineEventCard: View {
    var event: JourneyEvent

    var body: some View {
        SoftCard {
            HStack(spacing: 8) {
                Image(systemName: "bubble.left.and.text.bubble.right.fill")
                    .font(.caption.weight(.bold))
                    .foregroundStyle(DesignTokens.sage)
                Text(event.title.petSoulUserFacingText)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(DesignTokens.ink)
                Spacer(minLength: 0)
                Text(event.timestamp.formatted(date: .omitted, time: .shortened))
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(DesignTokens.secondaryInk)
            }

            Text(event.detail.petSoulEventText)
                .font(.footnote)
                .foregroundStyle(DesignTokens.secondaryInk)
                .lineSpacing(3)
        }
    }
}

private struct TransportLegCard: View {
    var leg: ScheduledTransportLeg

    var body: some View {
        SoftCard {
            HStack(alignment: .top, spacing: 12) {
                Image(systemName: leg.mode.systemImage)
                    .font(.system(size: 18, weight: .semibold))
                    .foregroundStyle(tint)
                    .frame(width: 38, height: 38)
                    .background(tint.opacity(0.14))
                    .clipShape(Circle())

                VStack(alignment: .leading, spacing: 7) {
                    HStack(spacing: 8) {
                        Text(leg.serviceLabel)
                            .font(.subheadline.weight(.semibold))
                            .foregroundStyle(DesignTokens.ink)
                            .lineLimit(1)
                        Spacer(minLength: 0)
                        Text(leg.status.displayName)
                            .font(.caption.weight(.bold))
                            .foregroundStyle(tint)
                            .padding(.vertical, 4)
                            .padding(.horizontal, 8)
                            .background(tint.opacity(0.12))
                            .clipShape(Capsule())
                    }

                    Text("\(leg.originName) → \(leg.destinationName)")
                        .font(.headline.weight(.semibold))
                        .foregroundStyle(DesignTokens.ink)
                        .lineLimit(2)
                        .fixedSize(horizontal: false, vertical: true)

                    Text(leg.timelineNote ?? leg.detail)
                        .font(.footnote)
                        .foregroundStyle(DesignTokens.secondaryInk)
                        .lineSpacing(3)
                        .lineLimit(3)

                    HStack(spacing: 8) {
                        Label(timeRange, systemImage: "clock")
                        Spacer(minLength: 0)
                        Text(progressText)
                    }
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(DesignTokens.secondaryInk)

                    GeometryReader { proxy in
                        ZStack(alignment: .leading) {
                            Capsule().fill(DesignTokens.mist)
                            Capsule()
                                .fill(tint.opacity(0.72))
                                .frame(width: max(10, proxy.size.width * max(0.02, min(1, leg.progress))))
                        }
                    }
                    .frame(height: 6)
                }
            }
        }
    }

    private var tint: Color {
        switch leg.mode {
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

    private var timeRange: String {
        let day = leg.scheduledDeparture.formatted(.dateTime.month().day())
        let departure = leg.scheduledDeparture.formatted(date: .omitted, time: .shortened)
        let arrival = leg.scheduledArrival.formatted(date: .omitted, time: .shortened)
        return "\(day) \(departure) - \(arrival)"
    }

    private var progressText: String {
        "\(Int(max(0, min(1, leg.progress)) * 100))%"
    }
}

private struct PostcardCard: View {
    var postcard: Postcard

    var body: some View {
        VStack(spacing: 0) {
            ZStack(alignment: .topLeading) {
                if let imageURL = postcard.imageURL {
                    PostcardImageView(url: imageURL, height: 250)
                } else {
                    postcardImagePlaceholder
                }

                LinearGradient(
                    colors: [.black.opacity(0.34), .clear],
                    startPoint: .top,
                    endPoint: .center
                )
                .clipShape(RoundedRectangle(cornerRadius: DesignTokens.cardRadius, style: .continuous))

                VStack(alignment: .leading, spacing: 0) {
                    Text("Greetings from")
                        .font(.system(size: 24, weight: .semibold, design: .serif))
                        .italic()
                    Text(greetingPlace)
                        .font(.system(size: 42, weight: .bold, design: .serif))
                        .italic()
                        .minimumScaleFactor(0.58)
                        .lineLimit(1)
                }
                .foregroundStyle(.white.opacity(0.94))
                .shadow(color: .black.opacity(0.28), radius: 8, x: 0, y: 3)
                .padding(18)
            }

            VStack(alignment: .leading, spacing: 13) {
                HStack(alignment: .top) {
                    VStack(alignment: .leading, spacing: 3) {
                        Text(postcard.location)
                            .font(.caption.weight(.bold))
                            .foregroundStyle(DesignTokens.secondaryInk)
                            .lineLimit(2)
                        Text(postcard.timestamp.formatted(date: .abbreviated, time: .shortened))
                            .font(.caption2.weight(.semibold))
                            .foregroundStyle(DesignTokens.secondaryInk.opacity(0.82))
                    }

                    Spacer(minLength: 0)

                    VStack(spacing: 3) {
                        Text("POSTCARD")
                            .font(.caption2.weight(.black))
                        Text(postcard.weather)
                            .font(.caption2.weight(.semibold))
                    }
                    .foregroundStyle(DesignTokens.dusk)
                    .padding(.vertical, 8)
                    .padding(.horizontal, 10)
                    .overlay {
                        RoundedRectangle(cornerRadius: 6, style: .continuous)
                            .stroke(DesignTokens.dusk.opacity(0.35), style: StrokeStyle(lineWidth: 1, dash: [4, 3]))
                    }
                }

                VStack(alignment: .leading, spacing: 8) {
                    Text("写给你，")
                        .font(.system(size: 18, weight: .regular, design: .serif))
                        .italic()

                    Text(postcard.text.petSoulPetVoiceText)
                        .font(.system(size: 20, weight: .regular, design: .serif))
                        .italic()
                        .foregroundStyle(DesignTokens.ink)
                        .lineSpacing(5)
                        .fixedSize(horizontal: false, vertical: true)

                    Text("With love, TA")
                        .font(.system(size: 20, weight: .semibold, design: .serif))
                        .italic()
                        .frame(maxWidth: .infinity, alignment: .trailing)
                }
                .foregroundStyle(DesignTokens.ink)
                .padding(.top, 2)
            }
            .padding(18)
        }
        .padding(10)
        .background(postcardPaper)
        .clipShape(RoundedRectangle(cornerRadius: 20, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 20, style: .continuous)
                .stroke(DesignTokens.pollen.opacity(0.32), lineWidth: 1)
        }
        .shadow(color: DesignTokens.ink.opacity(0.08), radius: 18, x: 0, y: 10)
    }

    private var greetingPlace: String {
        let pieces = postcard.location
            .split(separator: "·")
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
        return pieces.first ?? postcard.location
    }

    private var postcardPaper: Color {
        Color(red: 0.98, green: 0.94, blue: 0.84)
    }

    private var postcardImagePlaceholder: some View {
        ZStack {
            RoundedRectangle(cornerRadius: DesignTokens.cardRadius, style: .continuous)
                .fill(DesignTokens.mist)
            VStack(spacing: 8) {
                Image(systemName: "photo")
                    .font(.system(size: 26, weight: .semibold))
                Text("照片还在路上")
                    .font(.footnote.weight(.semibold))
            }
            .foregroundStyle(DesignTokens.secondaryInk)
        }
        .frame(height: 250)
    }
}

private struct PostcardImageView: View {
    var url: URL
    var height: CGFloat = 190

    var body: some View {
        Group {
            if url.isFileURL, let image = UIImage(contentsOfFile: url.path) {
                Image(uiImage: image)
                    .resizable()
                    .scaledToFill()
            } else {
                AsyncImage(url: url) { phase in
                    switch phase {
                    case .success(let image):
                        image
                            .resizable()
                            .scaledToFill()
                    case .failure:
                        imagePlaceholder
                    case .empty:
                        ProgressView()
                            .tint(DesignTokens.sage)
                    @unknown default:
                        imagePlaceholder
                    }
                }
            }
        }
        .frame(height: height)
        .frame(maxWidth: .infinity)
        .background(DesignTokens.mist)
        .clipShape(RoundedRectangle(cornerRadius: DesignTokens.cardRadius, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: DesignTokens.cardRadius, style: .continuous)
                .stroke(.white.opacity(0.58), lineWidth: 1)
        )
        .clipped()
    }

    private var imagePlaceholder: some View {
        VStack(spacing: 8) {
            Image(systemName: "photo")
                .font(.system(size: 24, weight: .semibold))
            Text("照片还在同步")
                .font(.footnote.weight(.medium))
        }
        .foregroundStyle(DesignTokens.secondaryInk)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

private extension DayPlanItem.Kind {
    var displayName: String {
        switch self {
        case .morning: "早晨"
        case .noon: "中午"
        case .afternoon: "午后"
        case .evening: "傍晚"
        }
    }
}

private struct DNAField: View {
    var title: String
    var value: String
    var systemImage: String

    var body: some View {
        SoftCard {
            Label(title, systemImage: systemImage)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(DesignTokens.secondaryInk)
            Text(value)
                .font(.body.weight(.medium))
                .foregroundStyle(DesignTokens.ink)
        }
    }
}

private struct DNAListField: View {
    var title: String
    var values: [String]
    var systemImage: String

    var body: some View {
        SoftCard {
            Label(title, systemImage: systemImage)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(DesignTokens.secondaryInk)

            LazyVGrid(columns: [GridItem(.adaptive(minimum: 88), spacing: 8)], alignment: .leading, spacing: 8) {
                ForEach(values, id: \.self) { value in
                    Text(value)
                        .font(.subheadline.weight(.medium))
                        .foregroundStyle(DesignTokens.ink)
                        .padding(.vertical, 8)
                        .padding(.horizontal, 10)
                        .background(DesignTokens.mist)
                        .clipShape(Capsule())
                }
            }
        }
    }
}

private struct EmptyStateView: View {
    var title: String
    var detail: String
    var systemImage: String

    var body: some View {
        VStack(spacing: 14) {
            Image(systemName: systemImage)
                .font(.system(size: 34, weight: .semibold))
                .foregroundStyle(DesignTokens.sage)
            Text(title)
                .font(.headline)
                .foregroundStyle(DesignTokens.ink)
            Text(detail)
                .font(.subheadline)
                .foregroundStyle(DesignTokens.secondaryInk)
                .multilineTextAlignment(.center)
                .lineSpacing(3)
        }
        .padding(DesignTokens.pagePadding)
    }
}

private extension String {
    var petSoulPetVoiceText: String {
        var text = petSoulUserFacingText
        let replacements: [(String, String)] = [
            ("TA 会", "我会"),
            ("TA 正在", "我正在"),
            ("TA 先", "我先"),
            ("TA 找", "我找"),
            ("TA 没有", "我没有"),
            ("TA 可能", "我会"),
            ("TA ", "我"),
            ("可能会", "会"),
            ("可能", ""),
            ("大概", ""),
            ("适合攻略型打卡", "我会进去看看"),
            ("适合攻略", "适合慢慢走"),
            ("打卡", "停留"),
            ("用户", "你"),
            ("主人", "你")
        ]
        for (source, target) in replacements {
            text = text.replacingOccurrences(of: source, with: target)
        }
        return text.petSoulCleanSpacing
    }

    var petSoulEventText: String {
        var text = petSoulUserFacingText
        text = text.replacingOccurrences(
            of: #"^[^。；;：「」]{1,32}发来[:：]"#,
            with: "你说：",
            options: .regularExpression
        )
        text = text.replacingOccurrences(
            of: #"我听见[^「。；;]{1,32}说「"#,
            with: "我听见你说「",
            options: .regularExpression
        )
        let replacements: [(String, String)] = [
            ("手机记录：", ""),
            ("这是一条建议或陪伴讯息，我会自己判断怎么回应。", "这句话已经被我收好了。"),
            ("宠物自主回应类型", "回应"),
            ("主人发来：", "你说："),
            ("给主人和自己的讯息", "你的想念"),
            ("可能会", "会"),
            ("可能", "")
        ]
        for (source, target) in replacements {
            text = text.replacingOccurrences(of: source, with: target)
        }
        return text.petSoulCleanSpacing
    }

    var petSoulUserFacingText: String {
        var text = self
        let replacements: [(String, String)] = [
            ("适合攻略型打卡，但不强迫 TA 喜欢这里。", "这里有真实的本地味道，TA 可以进去看看，再把感受记下来。"),
            ("适合攻略型打卡，但不强迫 TA 喜欢这里", "这里有真实的本地味道，TA 可以进去看看，再把感受记下来"),
            ("不强迫 TA 喜欢这里", "TA 只是按自己的节奏停一会儿"),
            ("用户可以收藏这段攻略，但不会改变 TA 的感受。", "你可以把这段记下来，TA 仍然会按自己的节奏继续走。"),
            ("用户可以收藏这段攻略，但不会改变 TA 的感受", "你可以把这段记下来，TA 仍然会按自己的节奏继续走"),
            ("给主人和自己的讯息", "你的想念")
        ]
        for (source, target) in replacements {
            text = text.replacingOccurrences(of: source, with: target)
        }

        let patterns = [
            #"[\s·。；;，,]*(?:地点来源|数据来源|来源|source|provider)\s*[:：]\s*[\w.+/\- ]+"#,
            #"这个地点来自[^。；;]*[。；;]?"#,
            #"来自(?:高德|Google|google|AMap|amap)[^。；;]*[。；;]?"#,
            #"\b(?:amap|google|mock|hybrid|openai|web|map|provider|service|engine|client|route|planner|mission)(?:[-_][A-Za-z0-9]+)+\b"#,
            #"适合[^。；;]*攻略型[^。；;]*[。；;]?"#
        ]
        for pattern in patterns {
            text = text.replacingOccurrences(of: pattern, with: "", options: .regularExpression)
        }
        return text.petSoulCleanSpacing
    }

    var petSoulCleanSpacing: String {
        var text = self
        text = text.replacingOccurrences(of: #"\s{2,}"#, with: " ", options: .regularExpression)
        text = text.replacingOccurrences(of: #"\s+([。；;，,])"#, with: "$1", options: .regularExpression)
        text = text.replacingOccurrences(of: #"([，,。；;])\1+"#, with: "$1", options: .regularExpression)
        return text.trimmingCharacters(in: CharacterSet.whitespacesAndNewlines.union(CharacterSet(charactersIn: "·,，;；。")))
    }

    func trimmedNonEmpty(fallback: String) -> String {
        let trimmed = trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? fallback : trimmed
    }
}

private extension Array where Element == String {
    func cleanedTags(fallback: [String]) -> [String] {
        var seen: Set<String> = []
        let cleaned = compactMap { item -> String? in
            let trimmed = item.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !trimmed.isEmpty, !seen.contains(trimmed) else { return nil }
            seen.insert(trimmed)
            return trimmed
        }
        return cleaned.isEmpty ? fallback : cleaned
    }
}
