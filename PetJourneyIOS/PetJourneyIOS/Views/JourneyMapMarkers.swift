import AuthenticationServices
import MapKit
import SwiftUI
import UIKit

struct JourneyEventMarker: View {
    var event: JourneyMapEvent
    var phase: JourneyMapEventPhase
    var isSelected: Bool

    var body: some View {
        VStack(spacing: 4) {
            ZStack {
                Circle()
                    .fill(event.tint.opacity((isSelected ? 0.94 : 0.84) * phase.opacity))
                    .frame(width: isSelected ? 48 : 40, height: isSelected ? 48 : 40)
                    .overlay {
                        Circle()
                            .stroke(DesignTokens.surfaceStroke.opacity(0.92), lineWidth: isSelected ? 4 : 3)
                    }
                    .shadow(color: event.tint.opacity(0.23), radius: 13, x: 0, y: 7)
                Circle()
                    .fill(DesignTokens.surface.opacity(0.16))
                    .frame(width: isSelected ? 34 : 28, height: isSelected ? 34 : 28)
                if let asset = PetSoulAsset.from(systemImage: event.systemImage) {
                    PetSoulAssetIcon(
                        asset: asset,
                        fallbackSystemImage: event.systemImage,
                        fallbackTint: .white,
                        size: isSelected ? 32 : 27
                    )
                } else {
                    Image(systemName: event.systemImage)
                        .font(.system(size: isSelected ? 19 : 16, weight: .semibold))
                        .foregroundStyle(.white)
                }
            }
            .frame(width: isSelected ? 54 : 46, height: isSelected ? 54 : 46)
            .opacity(phase == .past && !isSelected ? 0.76 : 1)

            if isSelected {
                Text("\(event.fullTimeLabel) · \(phase.title)")
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(DesignTokens.ink)
                    .lineLimit(1)
                    .padding(.vertical, 4)
                    .padding(.horizontal, 7)
                    .background(DesignTokens.surface.opacity(0.9))
                    .clipShape(Capsule())
                    .transition(.opacity.combined(with: .scale))
            }
        }
    }
}

struct RouteStopMarker: View {
    var tint: Color
    var phase: JourneyMapEventPhase
    var isActive: Bool

    var body: some View {
        ZStack {
            if isActive || phase == .current {
                SignalPulseRings(tint: tint, size: 42, lineWidth: 1.1, ringCount: 2)
            }
            Circle()
                .fill(tint.opacity((isActive ? 0.9 : 0.68) * phase.opacity))
                .frame(width: isActive || phase == .current ? 22 : 14, height: isActive || phase == .current ? 22 : 14)
                .overlay {
                    Circle().stroke(DesignTokens.surfaceStroke.opacity(0.95), lineWidth: isActive || phase == .current ? 3 : 2)
                }
        }
        .opacity(phase == .past && !isActive ? 0.72 : 1)
        .shadow(color: DesignTokens.deepInk.opacity(isActive ? 0.12 : 0.06), radius: isActive ? 8 : 4, x: 0, y: 4)
    }
}

struct LivePetMarkerView: View {
    var petID: String
    var petType: PetType
    var name: String
    var statusText: String
    var systemImage: String?
    var activityKind: JourneyActivitySnapshot.Kind
    var animationHint: String
    var tint: Color
    var headingDegrees: Double? = nil

    var isSleepMode: Bool {
        activityKind == .resting || animationHint == "sleep"
    }

    /// 朝东走向右倾、朝西走向左倾,南北向不倾,最多 6°——只是一点身体语言。
    var leanAngle: Double {
        guard let headingDegrees else { return 0 }
        return sin(headingDegrees * .pi / 180) * 6
    }

    var body: some View {
        VStack(spacing: 5) {
            ZStack {
                PetMotionWake(kind: activityKind, tint: tint)
                SignalPulseRings(tint: tint, size: activityKind == .transporting ? 88 : 78, lineWidth: isSleepMode ? 0.9 : 1.4, ringCount: isSleepMode ? 1 : 3)
                    .opacity(isSleepMode ? 0.38 : 1)
                Circle()
                    .fill(tint.opacity(isSleepMode ? 0.10 : 0.18))
                    .frame(width: activityKind == .transporting ? 64 : 58, height: activityKind == .transporting ? 64 : 58)
                Circle()
                    .stroke(tint.opacity(isSleepMode ? 0.28 : 0.42), lineWidth: activityKind == .transporting ? 1.4 : 1)
                    .frame(width: activityKind == .transporting ? 56 : 50, height: activityKind == .transporting ? 56 : 50)
                Circle()
                    .fill(DesignTokens.surface.opacity(isSleepMode ? 0.90 : 0.96))
                    .frame(width: 42, height: 42)
                    .shadow(color: DesignTokens.deepInk.opacity(0.14), radius: 14, x: 0, y: 7)
                if let avatar = PetAvatarStore.image(for: petID) {
                    Image(uiImage: avatar)
                        .resizable()
                        .scaledToFill()
                        .frame(width: 38, height: 38)
                        .clipShape(Circle())
                        .overlay {
                            Circle()
                                .stroke(tint.opacity(isSleepMode ? 0.32 : 0.52), lineWidth: 1.2)
                        }
                        .saturation(isSleepMode ? 0.72 : 1)
                } else {
                    PetSoulAdaptiveIcon(
                        systemImage: systemImage ?? petType.symbolName,
                        tint: activityKind == .transporting || isSleepMode ? tint : DesignTokens.clay,
                        size: 34
                    )
                        .frame(width: 34, height: 34)
                        .background((activityKind == .transporting || isSleepMode ? tint.opacity(0.12) : DesignTokens.petal.opacity(0.9)))
                        .clipShape(Circle())
                }

                if activityKind == .walking {
                    PetFootstepOrbit(tint: tint)
                }

                if let accessoryIcon {
                    Image(systemName: accessoryIcon)
                        .font(.system(size: 9, weight: .bold))
                        .foregroundStyle(.white)
                        .frame(width: 18, height: 18)
                        .background(tint)
                        .clipShape(Circle())
                        .offset(x: isSleepMode ? 19 : 22, y: isSleepMode ? -17 : -18)
                }
            }
            .rotationEffect(.degrees(leanAngle))
            .animation(.easeInOut(duration: 0.8), value: leanAngle)

            VStack(spacing: 1) {
                Text(name)
                    .font(.caption.weight(.semibold))
                Text(statusText)
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(DesignTokens.secondaryInk)
            }
            .foregroundStyle(DesignTokens.ink)
            .padding(.vertical, 5)
            .padding(.horizontal, 9)
            .background(DesignTokens.surface.opacity(0.92))
            .clipShape(Capsule())
        }
    }

    var accessoryIcon: String? {
        if isSleepMode {
            return nil
        }
        if activityKind == .transporting {
            return systemImage ?? "location.fill"
        }
        switch animationHint {
        case "coffee_drink":
            return "cup.and.saucer.fill"
        case "gaming":
            return "headphones"
        case "camera":
            return "camera.fill"
        case "snack":
            return "fork.knife"
        case "sleep":
            return "moon.zzz.fill"
        case "sightseeing_sea":
            return "water.waves"
        default:
            return nil
        }
    }
}

struct PetMotionWake: View {
    var kind: JourneyActivitySnapshot.Kind
    var tint: Color

    var body: some View {
        TimelineView(.animation) { timeline in
            let phase = timeline.date.timeIntervalSinceReferenceDate.truncatingRemainder(dividingBy: 1.8) / 1.8
            ZStack {
                switch kind {
                case .transporting:
                    Capsule()
                        .fill(
                            LinearGradient(
                                colors: [.clear, tint.opacity(0.28), .white.opacity(0.36), .clear],
                                startPoint: .leading,
                                endPoint: .trailing
                            )
                        )
                        .frame(width: 86, height: 16)
                        .offset(x: -24 + CGFloat(phase) * 18)
                        .rotationEffect(.degrees(-18))
                        .blur(radius: 1.2)
                case .walking:
                    Capsule()
                        .fill(tint.opacity(0.18))
                        .frame(width: 54, height: 10)
                        .offset(x: -14 + CGFloat(phase) * 8, y: 10)
                        .rotationEffect(.degrees(-12))
                        .blur(radius: 0.8)
                case .staying, .checkingIn:
                    Circle()
                        .stroke(tint.opacity(0.22 * (1 - phase)), lineWidth: 1.2)
                        .frame(width: 58 + CGFloat(phase * 18), height: 58 + CGFloat(phase * 18))
                case .resting:
                    Circle()
                        .fill(tint.opacity(0.08 + 0.05 * sin(phase * .pi * 2)))
                        .frame(width: 68, height: 68)
                }
            }
        }
        .frame(width: 92, height: 82)
        .allowsHitTesting(false)
        .accessibilityHidden(true)
    }
}

struct PetFootstepOrbit: View {
    var tint: Color

    var body: some View {
        TimelineView(.animation) { timeline in
            let phase = timeline.date.timeIntervalSinceReferenceDate.truncatingRemainder(dividingBy: 1.2) / 1.2
            ZStack {
                ForEach(0..<3, id: \.self) { index in
                    let local = (phase + Double(index) * 0.28).truncatingRemainder(dividingBy: 1)
                    Capsule()
                        .fill(tint.opacity(0.34 * (1 - local)))
                        .frame(width: 4, height: 7)
                        .rotationEffect(.degrees(index.isMultiple(of: 2) ? -18 : 18))
                        .offset(x: -18 + CGFloat(local * 34), y: 22 + CGFloat(index % 2) * 4)
                }
            }
        }
        .frame(width: 62, height: 38)
        .allowsHitTesting(false)
        .accessibilityHidden(true)
    }
}

struct CompanionPetMarkerView: View {
    var companion: DemoCompanionPet
    var isSelected: Bool

    var body: some View {
        VStack(spacing: 4) {
            ZStack {
                if isSelected {
                    SignalPulseRings(tint: companion.tint, size: 54, lineWidth: 1.1, ringCount: 2)
                        .opacity(0.88)
                }

                Circle()
                    .fill(DesignTokens.surface.opacity(0.95))
                    .frame(width: isSelected ? 44 : 40, height: isSelected ? 44 : 40)
                    .shadow(color: DesignTokens.deepInk.opacity(0.14), radius: 12, x: 0, y: 7)

                Circle()
                    .fill(companion.tint.opacity(isSelected ? 0.18 : 0.13))
                    .frame(width: isSelected ? 32 : 29, height: isSelected ? 32 : 29)

                PetSoulAdaptiveIcon(
                    systemImage: companion.petType.symbolName,
                    tint: companion.tint,
                    size: isSelected ? 25 : 22
                )
                .frame(width: isSelected ? 28 : 25, height: isSelected ? 28 : 25)

                Circle()
                    .fill(companion.tint)
                    .frame(width: 8, height: 8)
                    .overlay(Circle().stroke(.white, lineWidth: 1.6))
                    .offset(x: 17, y: 17)
            }
            .frame(width: 72, height: 58)
            .contentShape(Rectangle())

            if companion.showsLabel || isSelected {
                Text("\(companion.name) \(companion.action)")
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(DesignTokens.ink)
                    .lineLimit(1)
                    .minimumScaleFactor(0.72)
                    .frame(maxWidth: 86)
                    .padding(.vertical, 4)
                    .padding(.horizontal, 7)
                    .background(DesignTokens.surface.opacity(isSelected ? 0.96 : 0.9))
                    .clipShape(Capsule())
                    .shadow(color: DesignTokens.deepInk.opacity(isSelected ? 0.10 : 0.04), radius: 8, x: 0, y: 4)
                    .transition(.opacity.combined(with: .scale))
            }
        }
        .frame(width: 104, height: companion.showsLabel || isSelected ? 84 : 68, alignment: .center)
        .background(Color.clear)
        .scaleEffect(isSelected ? 1.05 : 1)
        .animation(.spring(response: 0.28, dampingFraction: 0.82), value: isSelected)
    }
}

struct FeedbackButton: View {
    var title: String
    var systemImage: String
    var tint: Color
    var action: () -> Void

    var body: some View {
        Button(action: action) {
            Label(title, systemImage: systemImage)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(tint)
                .lineLimit(1)
                .minimumScaleFactor(0.78)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 12)
                .background(DesignTokens.surface.opacity(0.78))
                .clipShape(RoundedRectangle(cornerRadius: DesignTokens.controlRadius, style: .continuous))
                .overlay {
                    RoundedRectangle(cornerRadius: DesignTokens.controlRadius, style: .continuous)
                        .stroke(tint.opacity(0.18), lineWidth: 1)
                }
        }
        .buttonStyle(.plain)
    }
}
