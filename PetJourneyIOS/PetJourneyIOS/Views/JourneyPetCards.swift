import AuthenticationServices
import MapKit
import SwiftUI
import UIKit

struct PetTransmissionView: View {
    var thought: JourneyThought
    var translation: ThoughtTranslation?
    var isTranslating: Bool
    var onTranslate: () -> Void

    var isShowingTranslation: Bool {
        translation?.thoughtID == thought.id
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 7) {
                Label("TA 原声", systemImage: "waveform")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(DesignTokens.secondaryInk)

                Spacer(minLength: 0)

                if thought.translationAvailable {
                    Button(action: onTranslate) {
                        HStack(spacing: 5) {
                            if isTranslating {
                                ProgressView()
                                    .controlSize(.mini)
                                    .tint(DesignTokens.sage)
                            } else {
                                Image(systemName: isShowingTranslation ? "text.bubble.fill" : "text.bubble")
                            }
                            Text(isShowingTranslation ? "收起" : "翻译")
                        }
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(DesignTokens.sage)
                    }
                    .buttonStyle(.plain)
                    .disabled(isTranslating)
                }
            }

            Text(thought.animalText ?? thought.text)
                .font(.title3.weight(.semibold))
                .foregroundStyle(DesignTokens.ink)
                .lineLimit(2)
                .fixedSize(horizontal: false, vertical: true)

            if isShowingTranslation, let translation {
                Text(translation.translation)
                    .font(.subheadline)
                    .foregroundStyle(DesignTokens.secondaryInk)
                    .lineSpacing(3)
                    .fixedSize(horizontal: false, vertical: true)
                    .transition(.opacity.combined(with: .move(edge: .top)))
            }
        }
        .padding(12)
        .background(DesignTokens.mist.opacity(0.52))
        .clipShape(RoundedRectangle(cornerRadius: 15, style: .continuous))
    }
}

struct PetVisibleThoughtCard: View {
    var thought: LifeVisibleThought
    var tint: Color

    var confidenceText: String {
        "\(Int((thought.confidence * 100).rounded()))%"
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 9) {
            HStack(spacing: 8) {
                Image(systemName: "sparkles")
                    .font(.caption.weight(.bold))
                    .foregroundStyle(tint)
                    .frame(width: 24, height: 24)
                    .background(tint.opacity(0.12))
                    .clipShape(Circle())

                Text("TA 的小想法")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(DesignTokens.secondaryInk)

                Spacer(minLength: 0)

                Text(thought.timeWindow)
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(tint)
                    .padding(.vertical, 4)
                    .padding(.horizontal, 8)
                    .background(tint.opacity(0.11))
                    .clipShape(Capsule())
            }

            Text("“\(thought.currentInnerVoice.petSoulUserFacingText)”")
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(DesignTokens.ink)
                .lineSpacing(3)
                .fixedSize(horizontal: false, vertical: true)

            VStack(alignment: .leading, spacing: 5) {
                Label(thought.nextIntention.petSoulUserFacingText, systemImage: "arrow.forward.circle")
                Label(thought.reason.petSoulUserFacingText, systemImage: "leaf")
            }
            .font(.caption)
            .foregroundStyle(DesignTokens.secondaryInk)
            .lineLimit(2)

            if let echo = thought.ownerMessageEcho?.petSoulUserFacingText, !echo.isEmpty {
                Text(echo)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(tint)
                    .lineLimit(2)
                    .fixedSize(horizontal: false, vertical: true)
            }

            HStack(spacing: 6) {
                Text("倾向")
                ProgressView(value: thought.confidence)
                    .tint(tint)
                Text(confidenceText)
                    .monospacedDigit()
            }
            .font(.caption2.weight(.semibold))
            .foregroundStyle(DesignTokens.secondaryInk)
        }
        .padding(12)
        .background(tint.opacity(0.07))
        .clipShape(RoundedRectangle(cornerRadius: 15, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 15, style: .continuous)
                .stroke(tint.opacity(0.14), lineWidth: 1)
        }
    }
}

struct PetCurrentActivityCard: View {
    var activity: JourneyActivitySnapshot
    var nextStopName: String
    var tint: Color

    var isMemoryMoment: Bool {
        activity.kind == .checkingIn
    }

    var bodyText: String {
        activity.detail.isEmpty ? activity.title : activity.detail
    }

    var memoryHint: String {
        if isMemoryMoment {
            return "如果 TA 觉得这一刻值得留下，会自己拍下来，之后发给你或放进回忆。"
        }
        return "TA 会按自己的节奏继续，看到喜欢的东西再自己留下。"
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 11) {
            HStack(spacing: 10) {
                ZStack {
                    RoundedRectangle(cornerRadius: 15, style: .continuous)
                        .fill(tint.opacity(0.13))
                    Image(systemName: isMemoryMoment ? "sparkles" : activity.systemImage)
                        .font(.title3.weight(.semibold))
                        .foregroundStyle(tint)
                }
                .frame(width: 44, height: 44)
                .clipShape(RoundedRectangle(cornerRadius: 15, style: .continuous))

                VStack(alignment: .leading, spacing: 3) {
                    Text("TA 现在在干嘛")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(DesignTokens.secondaryInk)
                    Text(activity.title)
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(DesignTokens.ink)
                        .lineLimit(2)
                        .fixedSize(horizontal: false, vertical: true)
                }

                Spacer(minLength: 0)
            }

            Text(bodyText)
                .font(.subheadline)
                .foregroundStyle(DesignTokens.ink)
                .lineSpacing(3)
                .lineLimit(3)
                .fixedSize(horizontal: false, vertical: true)

            ViewThatFits(in: .horizontal) {
                HStack(spacing: 7) {
                    ActivityStatusChip(title: activity.modeLabel, systemImage: activity.systemImage, tint: tint)
                    ActivityStatusChip(title: activity.durationText, systemImage: "clock.fill", tint: tint)
                    ActivityStatusChip(title: nextStopName, systemImage: "mappin.and.ellipse", tint: tint)
                }

                VStack(alignment: .leading, spacing: 7) {
                    ActivityStatusChip(title: activity.modeLabel, systemImage: activity.systemImage, tint: tint)
                    ActivityStatusChip(title: activity.durationText, systemImage: "clock.fill", tint: tint)
                    ActivityStatusChip(title: nextStopName, systemImage: "mappin.and.ellipse", tint: tint)
                }
            }

            Label(memoryHint, systemImage: isMemoryMoment ? "photo.on.rectangle.angled" : "leaf.fill")
                .font(.caption.weight(.semibold))
                .foregroundStyle(DesignTokens.secondaryInk)
                .lineLimit(3)
                .fixedSize(horizontal: false, vertical: true)
                .padding(.top, 1)
        }
        .padding(12)
        .background {
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .fill(DesignTokens.porcelain.opacity(0.72))
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .fill(tint.opacity(0.06))
        }
        .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .stroke(DesignTokens.surfaceStroke.opacity(0.62), lineWidth: 1)
        }
    }
}

struct ActivityStatusChip: View {
    var title: String
    var systemImage: String
    var tint: Color

    var body: some View {
        Label(title, systemImage: systemImage)
            .font(.caption2.weight(.semibold))
            .foregroundStyle(DesignTokens.secondaryInk)
            .lineLimit(1)
            .minimumScaleFactor(0.74)
            .frame(maxWidth: .infinity)
            .padding(.vertical, 7)
            .padding(.horizontal, 7)
            .background(DesignTokens.surface.opacity(0.62))
            .clipShape(RoundedRectangle(cornerRadius: 11, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: 11, style: .continuous)
                    .stroke(tint.opacity(0.12), lineWidth: 1)
            }
    }
}

struct SoftSignalChip: View {
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
                    .lineLimit(1)
                    .minimumScaleFactor(0.78)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.vertical, 8)
        .padding(.horizontal, 9)
        .background(DesignTokens.surface.opacity(0.66))
        .clipShape(RoundedRectangle(cornerRadius: 13, style: .continuous))
    }
}

struct MapEventCard: View {
    var event: JourneyMapEvent
    var phase: JourneyMapEventPhase
    var petName: String
    @Binding var isExpanded: Bool
    var onClose: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 10) {
                HStack(spacing: 10) {
                    Image(systemName: event.systemImage)
                        .font(.system(size: 16, weight: .semibold))
                        .foregroundStyle(event.tint)
                        .frame(width: 34, height: 34)
                        .background(event.tint.opacity(0.15))
                        .clipShape(Circle())

                    VStack(alignment: .leading, spacing: 3) {
                        HStack(spacing: 6) {
                            Text(event.fullTimeLabel)
                            Text(phase.title)
                                .foregroundStyle(event.tint)
                        }
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(DesignTokens.secondaryInk)
                        .lineLimit(1)

                        Text("\(petName) \(event.title)")
                            .font(.subheadline.weight(.semibold))
                            .foregroundStyle(DesignTokens.ink)
                            .lineLimit(isExpanded ? 2 : 1)
                    }
                }
                .contentShape(Rectangle())
                .onTapGesture {
                    withAnimation(.spring(response: 0.32, dampingFraction: 0.88)) {
                        isExpanded.toggle()
                    }
                }

                Spacer(minLength: 0)

                Image(systemName: isExpanded ? "chevron.down" : "chevron.up")
                    .font(.caption.weight(.bold))
                    .foregroundStyle(DesignTokens.secondaryInk)
                    .frame(width: 26, height: 26)
                    .background(DesignTokens.surface.opacity(0.62))
                    .clipShape(Circle())
                    .onTapGesture {
                        withAnimation(.spring(response: 0.32, dampingFraction: 0.88)) {
                            isExpanded.toggle()
                        }
                    }

                Button(action: onClose) {
                    Image(systemName: "xmark")
                        .font(.caption.weight(.bold))
                        .foregroundStyle(DesignTokens.secondaryInk)
                        .frame(width: 26, height: 26)
                        .background(DesignTokens.surface.opacity(0.62))
                        .clipShape(Circle())
                }
                .buttonStyle(.plain)
                .accessibilityLabel("关闭停留点")
            }

            if isExpanded {
                VStack(alignment: .leading, spacing: 6) {
                    Label(phase.cardHeading, systemImage: "sparkles")
                        .font(.caption2.weight(.bold))
                        .foregroundStyle(event.tint)
                    Text(phase.detailText(for: event.detail.petSoulUserFacingText))
                        .font(.caption)
                        .foregroundStyle(DesignTokens.secondaryInk)
                        .lineSpacing(2)
                        .lineLimit(4)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .padding(.top, 2)
                .transition(.opacity.combined(with: .move(edge: .top)))
            }
        }
        .padding(isExpanded ? 14 : 10)
        .background {
            RoundedRectangle(cornerRadius: isExpanded ? 20 : 18, style: .continuous)
                .fill(.ultraThinMaterial)
            RoundedRectangle(cornerRadius: isExpanded ? 20 : 18, style: .continuous)
                .fill(DesignTokens.surface.opacity(isExpanded ? 0.76 : 0.62))
        }
        .clipShape(RoundedRectangle(cornerRadius: isExpanded ? 20 : 18, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: isExpanded ? 20 : 18, style: .continuous)
                .stroke(DesignTokens.surfaceStroke.opacity(0.75), lineWidth: 1)
        }
        .shadow(color: DesignTokens.deepInk.opacity(0.12), radius: 20, x: 0, y: 10)
        .animation(.spring(response: 0.32, dampingFraction: 0.88), value: isExpanded)
    }
}

struct CompanionPetPeekCard: View {
    var companion: DemoCompanionPet
    var onClose: () -> Void

    var body: some View {
        HStack(alignment: .top, spacing: 11) {
            ZStack {
                Circle()
                    .fill(companion.tint.opacity(0.14))
                    .frame(width: 44, height: 44)
                Image(systemName: companion.petType.symbolName)
                    .font(.system(size: 20, weight: .semibold))
                    .foregroundStyle(companion.tint)
            }

            VStack(alignment: .leading, spacing: 6) {
                HStack(spacing: 6) {
                    Text("公共世界信号")
                    Text(companion.action)
                        .foregroundStyle(companion.tint)
                }
                .font(.caption.weight(.semibold))
                .foregroundStyle(DesignTokens.secondaryInk)
                .lineLimit(1)

                Text("\(companion.name) 在 \(companion.placeName)")
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(DesignTokens.ink)
                    .lineLimit(1)
                    .minimumScaleFactor(0.78)

                Text(companion.microStory)
                    .font(.caption)
                    .foregroundStyle(DesignTokens.secondaryInk)
                    .lineSpacing(2)
                    .lineLimit(3)
                    .fixedSize(horizontal: false, vertical: true)

                Label(companion.nextHint, systemImage: "sparkles")
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(companion.tint)
                    .lineLimit(2)
                    .fixedSize(horizontal: false, vertical: true)
            }

            Spacer(minLength: 0)

            Button(action: onClose) {
                Image(systemName: "xmark")
                    .font(.caption.weight(.bold))
                    .foregroundStyle(DesignTokens.secondaryInk)
                    .frame(width: 28, height: 28)
                    .background(DesignTokens.surface.opacity(0.64))
                    .clipShape(Circle())
            }
            .buttonStyle(.plain)
            .accessibilityLabel("关闭公共世界信号")
        }
        .padding(12)
        .background {
            RoundedRectangle(cornerRadius: 20, style: .continuous)
                .fill(.ultraThinMaterial)
            RoundedRectangle(cornerRadius: 20, style: .continuous)
                .fill(DesignTokens.surface.opacity(0.72))
        }
        .clipShape(RoundedRectangle(cornerRadius: 20, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 20, style: .continuous)
                .stroke(DesignTokens.surfaceStroke.opacity(0.76), lineWidth: 1)
        }
        .shadow(color: DesignTokens.deepInk.opacity(0.12), radius: 20, x: 0, y: 10)
    }
}
