import SwiftUI
import UIKit

struct JourneyChapterHeroCard: View {
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
                    .background(DesignTokens.surface.opacity(0.64))
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

struct FlowChipRow: View {
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

struct ChapterActionButton: View {
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
                .background(isActive ? DesignTokens.sage : DesignTokens.surface.opacity(0.72))
                .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
                .overlay {
                    RoundedRectangle(cornerRadius: 14, style: .continuous)
                        .stroke(isActive ? DesignTokens.sage.opacity(0.0) : DesignTokens.softLine, lineWidth: 1)
                }
        }
        .buttonStyle(.plain)
    }
}

struct JourneyChapterModePicker: View {
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

struct CurrentJourneyMomentCard: View {
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

struct JourneyCoreRouteCard: View {
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

struct JourneyCoreStopRow: View {
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
                                .background(DesignTokens.surface.opacity(0.66))
                                .clipShape(Capsule())
                        }
                    }
                }
            }
        }
    }
}

struct JourneySelectedMomentsCard: View {
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

struct JourneyMomentRow: View {
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
        .background(DesignTokens.surface.opacity(0.58))
        .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
    }
}
