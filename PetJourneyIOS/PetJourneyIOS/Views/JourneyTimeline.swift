import SwiftUI
import UIKit

enum DayPlanTimelinePhase: Equatable {
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

struct TimelineItemView: View {
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

    var phaseAdjustedDetail: String {
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

    var color: Color {
        switch item.kind {
        case .morning: DesignTokens.sage
        case .noon: DesignTokens.clay
        case .afternoon: DesignTokens.dusk
        case .evening: DesignTokens.ink
        }
    }
}

struct TimelineEventCard: View {
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

struct TransportLegCard: View {
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

    var tint: Color {
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

    var timeRange: String {
        let day = leg.scheduledDeparture.formatted(.dateTime.month().day())
        let departure = leg.scheduledDeparture.formatted(date: .omitted, time: .shortened)
        let arrival = leg.scheduledArrival.formatted(date: .omitted, time: .shortened)
        return "\(day) \(departure) - \(arrival)"
    }

    var progressText: String {
        "\(Int(max(0, min(1, leg.progress)) * 100))%"
    }
}

struct PostcardCard: View {
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
                            .foregroundStyle(DesignTokens.paperSecondaryInk)
                            .lineLimit(2)
                        Text(postcard.timestamp.formatted(date: .abbreviated, time: .shortened))
                            .font(.caption2.weight(.semibold))
                            .foregroundStyle(DesignTokens.paperSecondaryInk.opacity(0.82))
                    }

                    Spacer(minLength: 0)

                    VStack(spacing: 3) {
                        Text("POSTCARD")
                            .font(.caption2.weight(.black))
                        Text(postcard.weather)
                            .font(.caption2.weight(.semibold))
                    }
                    .foregroundStyle(DesignTokens.paperAccent)
                    .padding(.vertical, 8)
                    .padding(.horizontal, 10)
                    .overlay {
                        RoundedRectangle(cornerRadius: 6, style: .continuous)
                            .stroke(DesignTokens.paperAccent.opacity(0.35), style: StrokeStyle(lineWidth: 1, dash: [4, 3]))
                    }
                    .overlay(alignment: .bottomLeading) {
                        postmark
                            .offset(x: -22, y: 10)
                    }
                }

                VStack(alignment: .leading, spacing: 8) {
                    Text("写给你，")
                        .font(.system(size: 18, weight: .regular, design: .serif))
                        .italic()

                    Text(postcard.text.petSoulPetVoiceText)
                        .font(.system(size: 20, weight: .regular, design: .serif))
                        .italic()
                        .lineSpacing(5)
                        .fixedSize(horizontal: false, vertical: true)

                    Text("With love, TA")
                        .font(.system(size: 20, weight: .semibold, design: .serif))
                        .italic()
                        .frame(maxWidth: .infinity, alignment: .trailing)
                }
                .foregroundStyle(DesignTokens.paperInk)
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
        .shadow(color: DesignTokens.deepInk.opacity(0.08), radius: 18, x: 0, y: 10)
    }

    var greetingPlace: String {
        let pieces = postcard.location
            .split(separator: "·")
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
        return pieces.first ?? postcard.location
    }

    // 邮戳：盖在邮票框左下角，用固定纸面色，与暖纸一起构成"实物"。
    var postmark: some View {
        ZStack {
            Circle()
                .stroke(DesignTokens.paperAccent.opacity(0.4), lineWidth: 1.2)
                .frame(width: 34, height: 34)
            VStack(spacing: 2.5) {
                ForEach(0..<3, id: \.self) { _ in
                    Capsule()
                        .fill(DesignTokens.paperAccent.opacity(0.34))
                        .frame(width: 15, height: 1.2)
                }
            }
        }
        .rotationEffect(.degrees(-12))
        .allowsHitTesting(false)
    }

    var postcardPaper: some ShapeStyle {
        LinearGradient(
            colors: [DesignTokens.paper, DesignTokens.paperShade],
            startPoint: .topLeading,
            endPoint: .bottomTrailing
        )
    }

    var postcardImagePlaceholder: some View {
        ZStack {
            RoundedRectangle(cornerRadius: DesignTokens.cardRadius, style: .continuous)
                .fill(DesignTokens.paperShade)
            VStack(spacing: 8) {
                Image(systemName: "photo")
                    .font(.system(size: 26, weight: .semibold))
                Text("照片还在路上")
                    .font(.footnote.weight(.semibold))
            }
            .foregroundStyle(DesignTokens.paperSecondaryInk)
        }
        .frame(height: 250)
    }
}

struct PostcardImageView: View {
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
                .stroke(DesignTokens.surfaceStroke.opacity(0.58), lineWidth: 1)
        )
        .clipped()
    }

    var imagePlaceholder: some View {
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

extension DayPlanItem.Kind {
    var displayName: String {
        switch self {
        case .morning: "早晨"
        case .noon: "中午"
        case .afternoon: "午后"
        case .evening: "傍晚"
        }
    }
}

struct EmptyStateView: View {
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

extension String {
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
            ("给主人和自己的讯息", "你的想念"),
            ("适合攻略型打卡", "适合进去看看"),
            ("攻略型打卡", "旅程记录"),
            ("可能会", "会"),
            ("可能", ""),
            ("打卡", "停留")
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

extension Array where Element == String {
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
