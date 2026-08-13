import SwiftUI
import UIKit

enum JourneyChapterMode: String, CaseIterable, Identifiable {
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
    @State var activeMode: JourneyChapterMode = .story

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

    var journeyDate: Date {
        if let journeyPlan {
            return journeyPlan.generatedAt
        }
        if let eventDate = dayPlan?.eventsToday.map(\.timestamp).min() {
            return eventDate
        }
        return Date()
    }

    var journeyDateTitle: String {
        journeyDate.formatted(.dateTime.year().month(.wide).day())
    }

    var routeSubtitle: String {
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

    var routeCity: String {
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

    var guideDigest: PetGuideDigest? {
        PetGuideDigest.make(dayPlan: dayPlan, journeyPlan: journeyPlan, guide: petGuide)
    }

    @ViewBuilder
    var movementDisclosure: some View {
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

    func sheetHeader(title: String, subtitle: String) -> some View {
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

    var visibleEvents: [JourneyEvent] {
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

    func dayPlanPhase(for items: [DayPlanItem], index: Int, now: Date = Date()) -> DayPlanTimelinePhase {
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

    func minuteOfDay(from time: String?) -> Int? {
        guard let time else { return nil }
        let parts = time.split(separator: ":")
        guard parts.count == 2, let hour = Int(parts[0]), let minute = Int(parts[1]) else {
            return nil
        }
        return hour * 60 + minute
    }

    func time(in items: [DayPlanItem], at index: Int) -> String? {
        guard items.indices.contains(index) else { return nil }
        return items[index].time
    }
}

struct IllustratedGuideCard: View {
    var guide: IllustratedGuide?
    var digest: PetGuideDigest
    var isGenerating: Bool

    @State var selectedPageIndex = 1

    var statusText: String {
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

    var guideStyleName: String {
        guide?.styleName ?? "温柔手账风"
    }

    var previewStops: [IllustratedGuidePreviewStop] {
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

    var pages: [IllustratedGuidePage] {
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

    var selectedPosition: Int {
        guard let index = pages.firstIndex(where: { $0.index == selectedPageIndex }) else { return 0 }
        return index
    }

    var selectedPage: IllustratedGuidePage {
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

    func previewStops(for page: IllustratedGuidePage) -> [IllustratedGuidePreviewStop] {
        previewStops
    }

    func turnPage(_ delta: Int) {
        guard !pages.isEmpty else { return }
        let nextIndex = min(max(selectedPosition + delta, 0), pages.count - 1)
        withAnimation(.spring(response: 0.34, dampingFraction: 0.86)) {
            selectedPageIndex = pages[nextIndex].index
        }
    }

    static func icon(for category: String) -> String {
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

struct IllustratedGuidePageCard: View {
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
        .background(DesignTokens.surface.opacity(0.42))
        .clipShape(RoundedRectangle(cornerRadius: 22, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 22, style: .continuous)
                .stroke(DesignTokens.surfaceStroke.opacity(0.74), lineWidth: 1)
        )
    }
}

struct IllustratedGuideImagePlaceholder: View {
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
                .stroke(DesignTokens.surfaceStroke.opacity(0.72), lineWidth: 1)
        )
    }

    var statusTitle: String {
        if isFailed {
            return "这页还没画出来"
        }
        if isGenerating {
            return "正在画这页手账"
        }
        return "等待生成手绘攻略图"
    }
}

struct IllustratedGuideTurnButton: View {
    var systemImage: String
    var action: () -> Void

    @Environment(\.isEnabled) var isEnabled

    var body: some View {
        Button(action: action) {
            Image(systemName: systemImage)
                .font(.caption.weight(.black))
                .foregroundStyle(isEnabled ? DesignTokens.ink : DesignTokens.secondaryInk.opacity(0.35))
                .frame(width: 32, height: 32)
                .background(DesignTokens.surface.opacity(isEnabled ? 0.86 : 0.46))
                .clipShape(Circle())
                .overlay(
                    Circle()
                        .stroke(DesignTokens.softLine.opacity(0.72), lineWidth: 1)
                )
        }
        .buttonStyle(.plain)
    }
}

struct IllustratedGuidePageDots: View {
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
