import AuthenticationServices
import MapKit
import SwiftUI
import UIKit

struct LiveSignalPanel: View {
    var status: AgentStatus
    var selectedEvent: JourneyMapEvent?
    var liveEvent: JourneyMapEvent?
    var routePlan: JourneyRoutePlan
    var activity: JourneyActivitySnapshot
    var needState: PetNeedState?
    var visibleThought: LifeVisibleThought?
    var translation: ThoughtTranslation?
    var isTranslating: Bool
    var hasUnreadPostcard: Bool
    @Binding var isExpanded: Bool
    var onShowDayPlan: () -> Void
    var onShowPostcards: () -> Void
    var onShowTravelKit: () -> Void
    var onShowSouvenirs: () -> Void
    var onTranslate: () -> Void
    var onLike: () -> Void
    var onDislike: () -> Void

    var visibleEvent: JourneyMapEvent? {
        if activity.isSleepLike {
            return nil
        }
        if let selectedEvent, selectedEvent.displayPhase(liveEvent: liveEvent) == .current {
            return selectedEvent
        }
        return liveEvent
    }

    var thoughtText: String {
        status.agentState.latestThought?.text ?? status.agentState.statusNote
    }

    var headline: String {
        if isSleepMode {
            return activity.sleepHeadline(petName: status.name)
        }
        if let visibleEvent {
            return visibleEvent.title
        }
        return activity.title
    }

    var supportingText: String {
        if isSleepMode {
            return activity.sleepDetail(petName: status.name)
        }
        if let visibleEvent {
            return visibleEvent.detail.petSoulUserFacingText
        }
        return (activity.detail.isEmpty ? thoughtText : activity.detail).petSoulUserFacingText
    }

    var signalTint: Color {
        isSleepMode ? DesignTokens.dusk : (visibleEvent?.tint ?? activity.tint)
    }

    var isSleepMode: Bool {
        activity.isSleepLike
    }

    var compactEyebrow: String {
        if isSleepMode {
            return "TA 睡着了"
        }
        if let selectedEvent, selectedEvent.displayPhase(liveEvent: liveEvent) == .current {
            return "TA 此刻在这里"
        }
        return activity.eyebrow
    }

    var moodSummary: String {
        if status.agentState.energy < 35 {
            return "慢慢蓄电"
        }
        if status.agentState.happiness >= 78 {
            return "心里亮亮的"
        }
        if status.agentState.happiness >= 55 {
            return "安稳走着"
        }
        return "想放慢一点"
    }

    var curiositySummary: String {
        if status.agentState.curiosity >= 78 {
            return "想多看看"
        }
        if status.agentState.curiosity >= 52 {
            return "按节奏看"
        }
        return "先靠近一点"
    }

    var needSummary: String {
        switch needState?.primaryNeed {
        case "rest":
            return "想歇一下"
        case "drink":
            return "想喝点"
        case "eat":
            return "想吃点"
        case "quiet":
            return "想安静"
        default:
            break
        }
        if let sleepiness = needState?.sleepiness, sleepiness >= 76 {
            return "想睡会儿"
        }
        if let thirst = needState?.thirst, thirst >= 76 {
            return "想补水"
        }
        if let hunger = needState?.hunger, hunger >= 76 {
            return "想吃点"
        }
        return curiositySummary
    }

    var expandedPanelMaxHeight: CGFloat {
        min(UIScreen.main.bounds.height * 0.58, 560)
    }

    var nextStopName: String {
        guard let visibleEvent else { return status.agentState.location }
        return visibleEvent.place
            .components(separatedBy: "·")
            .last?
            .trimmingCharacters(in: .whitespacesAndNewlines) ?? visibleEvent.place
    }

    var body: some View {
        VStack(alignment: .leading, spacing: isExpanded ? 12 : 8) {
            Capsule()
                .fill(DesignTokens.secondaryInk.opacity(0.18))
                .frame(width: 38, height: 4)
                .frame(maxWidth: .infinity)
                .padding(.top, 3)

            Button {
                withAnimation(.spring(response: 0.34, dampingFraction: 0.86)) {
                    isExpanded.toggle()
                }
            } label: {
                compactHeader
            }
            .buttonStyle(.plain)

            if isExpanded {
                ScrollView(showsIndicators: false) {
                    expandedContent
                        .padding(.bottom, 4)
                }
                .frame(maxHeight: expandedPanelMaxHeight)
                .transition(.opacity.combined(with: .move(edge: .bottom)))
            }
        }
        .padding(.horizontal, 14)
        .padding(.bottom, isExpanded ? 15 : 12)
        .background(panelBackground)
        .clipShape(RoundedRectangle(cornerRadius: 25, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 25, style: .continuous)
                .stroke(DesignTokens.surfaceStroke.opacity(0.72), lineWidth: 1)
        }
        .shadow(color: DesignTokens.deepInk.opacity(0.16), radius: 26, x: 0, y: 13)
        .animation(.spring(response: 0.34, dampingFraction: 0.86), value: isExpanded)
    }

    var compactHeader: some View {
        HStack(spacing: 12) {
            ZStack {
                if isSleepMode {
                    SleepBreathingHalo(tint: signalTint, size: isExpanded ? 58 : 52)
                } else {
                    SignalPulseRings(tint: signalTint, size: isExpanded ? 52 : 46, lineWidth: 1.2, ringCount: 2)
                        .opacity(0.68)
                }
                PixelPetActivityAnimation(
                    hint: activity.animationHint,
                    petType: status.petType ?? .dog,
                    tint: signalTint
                )
                .frame(width: 38, height: 38)
                .background(signalTint.opacity(0.13))
                .clipShape(RoundedRectangle(cornerRadius: 9, style: .continuous))
            }
            .frame(width: 43, height: 43)

            VStack(alignment: .leading, spacing: 4) {
                HStack(spacing: 6) {
                    Text(compactEyebrow)
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(DesignTokens.secondaryInk)
                        .lineLimit(1)

                    if isSleepMode {
                        SleepBreathDot(tint: signalTint)
                    } else {
                        NavigationPulseDot(tint: signalTint)
                    }
                }

                Text(headline)
                    .font(.headline.weight(.semibold))
                    .foregroundStyle(DesignTokens.ink)
                    // P0-3：标题不允许截断（半收态也放两行）
                    .lineLimit(2)
                    .fixedSize(horizontal: false, vertical: true)

                HStack(spacing: 6) {
                    if isSleepMode {
                        Label("轻睡中", systemImage: "moon.zzz.fill")
                        Text(activity.sleepRemainingText)
                    } else {
                        Label(activity.modeLabel, systemImage: activity.systemImage)
                        Text("下一站 \(nextStopName)")
                    }
                }
                .font(.caption.weight(.semibold))
                .foregroundStyle(DesignTokens.secondaryInk)
                .lineLimit(1)
                .minimumScaleFactor(0.72)
            }

            Spacer(minLength: 0)

            VStack(spacing: 5) {
                SignalBars(tint: signalTint)
                Image(systemName: isExpanded ? "chevron.down" : "chevron.up")
                    .font(.caption.weight(.bold))
                    .foregroundStyle(DesignTokens.secondaryInk)
                    .frame(width: 24, height: 24)
                    .background(DesignTokens.surface.opacity(0.62))
                    .clipShape(Circle())
            }
        }
        .contentShape(Rectangle())
        .padding(.top, 2)
    }

    var expandedContent: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(supportingText)
                .font(.subheadline)
                .foregroundStyle(DesignTokens.secondaryInk)
                .lineSpacing(3)
                .lineLimit(isSleepMode ? 4 : 3)
                .fixedSize(horizontal: false, vertical: true)

            if isSleepMode {
                SleepRestStatusCard(
                    petName: status.name,
                    activity: activity,
                    tint: signalTint
                )
            }

            if !isSleepMode, let thought = status.agentState.latestThought {
                PetTransmissionView(
                    thought: thought,
                    translation: translation,
                    isTranslating: isTranslating,
                    onTranslate: onTranslate
                )
            }

            if !isSleepMode, let visibleThought {
                PetVisibleThoughtCard(thought: visibleThought, tint: signalTint)
            }

            if !isSleepMode {
                PetCurrentActivityCard(
                    activity: activity,
                    nextStopName: nextStopName,
                    tint: signalTint
                )
            }

            if isSleepMode {
                SleepQuietHint(tint: signalTint)
            } else {
                NavigationTelemetryStrip(
                    routePlan: routePlan,
                    activity: activity,
                    nextStop: nextStopName
                )
            }

            if !isSleepMode {
                HStack(spacing: 8) {
                    SoftSignalChip(title: "外面", value: status.agentState.weather.petSoulUserFacingText, systemImage: "cloud.sun")
                    SoftSignalChip(title: "现在", value: moodSummary, systemImage: "heart")
                    SoftSignalChip(title: "需要", value: needSummary, systemImage: "sparkles")
                }
            }

            HStack(spacing: 10) {
                Button(action: onShowDayPlan) {
                    PetSoulAssetLabel(
                        title: "今天路线",
                        asset: .travelMap,
                        fallbackSystemImage: "map.fill",
                        tint: signalTint
                    )
                        .frame(maxWidth: .infinity)
                }
                .quietActionStyle()

                Button(action: onShowPostcards) {
                    PetSoulAssetLabel(
                        title: hasUnreadPostcard ? "新明信片" : "明信片",
                        asset: .postcardMemory,
                        fallbackSystemImage: "mail",
                        tint: signalTint
                    )
                        .frame(maxWidth: .infinity)
                }
                .quietActionStyle()
            }

            HStack(spacing: 10) {
                Button(action: onShowTravelKit) {
                    PetSoulAssetLabel(
                        title: "旅行小包",
                        asset: .travelBag,
                        fallbackSystemImage: "backpack.fill",
                        tint: signalTint
                    )
                        .frame(maxWidth: .infinity)
                }
                .quietActionStyle()

                Button(action: onShowSouvenirs) {
                    Label("小收藏", systemImage: "gift.fill")
                        .frame(maxWidth: .infinity)
                }
                .quietActionStyle()
            }

            if !isSleepMode {
                HStack(spacing: 10) {
                    FeedbackButton(
                        title: "收藏攻略",
                        systemImage: "bookmark.fill",
                        tint: DesignTokens.clay,
                        action: onLike
                    )

                    FeedbackButton(
                        title: "不适合我",
                        systemImage: "xmark.circle.fill",
                        tint: DesignTokens.secondaryInk,
                        action: onDislike
                    )
                }
            }
        }
    }

    var panelBackground: some View {
        ZStack {
            RoundedRectangle(cornerRadius: 25, style: .continuous)
                .fill(.ultraThinMaterial)
            RoundedRectangle(cornerRadius: 25, style: .continuous)
                .fill(DesignTokens.surface.opacity(isSleepMode ? 0.68 : (isExpanded ? 0.72 : 0.58)))
            LinearGradient(
                colors: [
                    signalTint.opacity(isSleepMode ? 0.20 : 0.12),
                    isSleepMode ? DesignTokens.sky.opacity(0.22) : .clear,
                    (isSleepMode ? DesignTokens.dusk : DesignTokens.porcelain).opacity(isSleepMode ? 0.13 : 0.34)
                ],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
        }
    }

}

struct SleepBreathingHalo: View {
    var tint: Color
    var size: CGFloat
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        TimelineView(.animation(minimumInterval: 1 / 30, paused: reduceMotion)) { timeline in
            let time = reduceMotion ? 0 : timeline.date.timeIntervalSinceReferenceDate
            let phase = (sin(time * 1.4) + 1) / 2
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .fill(
                    LinearGradient(
                        colors: [
                            tint.opacity(0.10 + phase * 0.08),
                            DesignTokens.sky.opacity(0.22 + phase * 0.08)
                        ],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    )
                )
                .frame(width: size, height: size)
                .overlay {
                    RoundedRectangle(cornerRadius: 14, style: .continuous)
                        .stroke(tint.opacity(0.12 + phase * 0.10), lineWidth: 1)
                }
                .scaleEffect(0.96 + phase * 0.06)
        }
        .allowsHitTesting(false)
        .accessibilityHidden(true)
    }
}

struct SleepBreathDot: View {
    var tint: Color
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        TimelineView(.animation(minimumInterval: 1 / 30, paused: reduceMotion)) { timeline in
            let time = reduceMotion ? 0 : timeline.date.timeIntervalSinceReferenceDate
            let phase = (sin(time * 1.8) + 1) / 2
            HStack(spacing: 3) {
                ForEach(0..<3, id: \.self) { index in
                    Circle()
                        .fill(tint.opacity(0.32 + phase * 0.32))
                        .frame(width: 3 + CGFloat(index), height: 3 + CGFloat(index))
                        .offset(y: CGFloat(index) * -1)
                }
            }
        }
        .frame(width: 18, height: 12)
        .allowsHitTesting(false)
        .accessibilityHidden(true)
    }
}

struct SleepRestStatusCard: View {
    var petName: String
    var activity: JourneyActivitySnapshot
    var tint: Color

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 9) {
                Image(systemName: "moon.zzz.fill")
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundStyle(tint)
                    .frame(width: 32, height: 32)
                    .background(tint.opacity(0.13))
                    .clipShape(Circle())

                VStack(alignment: .leading, spacing: 2) {
                    Text("通讯器已调低声音")
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(DesignTokens.ink)
                    Text("\(petName) 醒来后会继续自己的小旅程")
                        .font(.caption)
                        .foregroundStyle(DesignTokens.secondaryInk)
                        .lineLimit(1)
                        .minimumScaleFactor(0.78)
                }

                Spacer(minLength: 0)
            }

            HStack(spacing: 8) {
                SleepInfoPill(title: "状态", value: "睡着了", systemImage: "bed.double.fill", tint: tint)
                SleepInfoPill(title: "醒来", value: activity.sleepRemainingText, systemImage: "alarm.fill", tint: tint)
            }
        }
        .padding(12)
        .background {
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .fill(DesignTokens.sky.opacity(0.30))
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .fill(DesignTokens.surface.opacity(0.38))
        }
        .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .stroke(tint.opacity(0.12), lineWidth: 1)
        }
    }
}

struct SleepInfoPill: View {
    var title: String
    var value: String
    var systemImage: String
    var tint: Color

    var body: some View {
        HStack(spacing: 6) {
            Image(systemName: systemImage)
                .font(.caption.weight(.bold))
                .foregroundStyle(tint)
            VStack(alignment: .leading, spacing: 1) {
                Text(title)
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(DesignTokens.secondaryInk)
                Text(value)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(DesignTokens.ink)
                    .lineLimit(1)
                    .minimumScaleFactor(0.72)
            }
            Spacer(minLength: 0)
        }
        .padding(.vertical, 8)
        .padding(.horizontal, 9)
        .background(DesignTokens.surface.opacity(0.62))
        .clipShape(RoundedRectangle(cornerRadius: 13, style: .continuous))
    }
}

struct SleepQuietHint: View {
    var tint: Color

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: "speaker.slash.fill")
                .font(.caption.weight(.bold))
                .foregroundStyle(tint)
            Text("TA 现在不用赶路，也不用回复。你留下的话会安静放在通讯器里。")
                .font(.caption.weight(.semibold))
                .foregroundStyle(DesignTokens.secondaryInk)
                .lineLimit(2)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(.vertical, 9)
        .padding(.horizontal, 11)
        .background(DesignTokens.mist.opacity(0.44))
        .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
    }
}
