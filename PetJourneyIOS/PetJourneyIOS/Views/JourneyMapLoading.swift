import AuthenticationServices
import MapKit
import SwiftUI
import UIKit

enum IntroFlightState {
    case pending
    case flying
    case done
}

struct JourneyLoadingView: View {
    @Environment(\.accessibilityReduceMotion) var reduceMotion

    let phases: [(title: String, detail: String, symbol: String, tint: Color)] = [
        ("正在接收 TA 的位置", "先确认 TA 停在哪一片光里。", "mappin.and.ellipse", DesignTokens.sage),
        ("正在听今天的信号", "今天想靠近的地方，会一点点浮出来。", "dot.radiowaves.left.and.right", DesignTokens.sea),
        ("正在整理脚印路线", "进入地图后，脚印和小照片会慢慢出现。", "map.fill", DesignTokens.amber)
    ]

    var body: some View {
        TimelineView(.animation(minimumInterval: 1 / 30, paused: reduceMotion)) { timeline in
            let time = reduceMotion ? 0 : timeline.date.timeIntervalSinceReferenceDate
            let phaseIndex = Int(time / 1.55) % phases.count
            let phase = phases[phaseIndex]
            let pulse = reduceMotion ? 0.5 : (sin(time * 2.4) + 1) / 2
            let routeProgress = reduceMotion ? 0.45 : (time * 0.42).truncatingRemainder(dividingBy: 1)

            VStack(spacing: 18) {
                LoadingCommunicatorGlyph(
                    tint: phase.tint,
                    pulse: pulse,
                    routeProgress: routeProgress
                )

                VStack(spacing: 7) {
                    Label(phase.title, systemImage: phase.symbol)
                        .font(.headline.weight(.semibold))
                        .foregroundStyle(DesignTokens.ink)
                        .lineLimit(1)
                        .minimumScaleFactor(0.78)

                    Text(phase.detail)
                        .font(.subheadline)
                        .foregroundStyle(DesignTokens.secondaryInk)
                        .multilineTextAlignment(.center)
                        .lineSpacing(3)
                        .fixedSize(horizontal: false, vertical: true)
                }

                LoadingRouteDots(activeIndex: phaseIndex, tint: phase.tint)
            }
            .frame(maxWidth: .infinity)
            .padding(.vertical, 24)
            .padding(.horizontal, 18)
            .background {
                RoundedRectangle(cornerRadius: 25, style: .continuous)
                    .fill(.ultraThinMaterial)
                RoundedRectangle(cornerRadius: 25, style: .continuous)
                    .fill(DesignTokens.surface.opacity(0.72))
            }
            .clipShape(RoundedRectangle(cornerRadius: 25, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: 25, style: .continuous)
                    .stroke(DesignTokens.surfaceStroke.opacity(0.78), lineWidth: 1)
            }
            .shadow(color: DesignTokens.deepInk.opacity(0.12), radius: 26, x: 0, y: 14)
            .accessibilityElement(children: .combine)
            .accessibilityLabel("正在接收 TA 的旅程，地图会先出现，细节随后同步")
        }
    }
}

struct JourneySignalErrorCard: View {
    @Environment(\.accessibilityReduceMotion) var reduceMotion

    var message: String
    var onRetry: () -> Void

    var body: some View {
        SoftCard(padding: 18) {
            VStack(alignment: .leading, spacing: 18) {
                HStack(alignment: .top, spacing: 14) {
                    communicatorGlyph

                    VStack(alignment: .leading, spacing: 8) {
                        HStack(spacing: 7) {
                            SignalBars(tint: DesignTokens.sage, isActive: !reduceMotion)
                            Text("信号暂时飘远了")
                                .font(.headline.weight(.semibold))
                                .foregroundStyle(DesignTokens.ink)
                                .lineLimit(1)
                                .minimumScaleFactor(0.82)
                        }

                        Text(detailText)
                            .font(.subheadline)
                            .foregroundStyle(DesignTokens.secondaryInk)
                            .lineSpacing(3)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }

                HStack(spacing: 8) {
                    Image(systemName: "antenna.radiowaves.left.and.right.slash")
                        .font(.caption.weight(.semibold))
                    Text(reasonText)
                        .font(.caption.weight(.semibold))
                }
                .foregroundStyle(DesignTokens.sage)
                .padding(.vertical, 8)
                .padding(.horizontal, 10)
                .background(DesignTokens.mist.opacity(0.74))
                .clipShape(RoundedRectangle(cornerRadius: DesignTokens.cardRadius, style: .continuous))

                Button(action: onRetry) {
                    Label("重新接收信号", systemImage: "arrow.clockwise")
                }
                .primaryActionStyle()
            }
        }
        .frame(maxWidth: 360)
        .accessibilityElement(children: .combine)
        .accessibilityLabel("信号暂时飘远了。\(detailText)。\(reasonText)。可以重新接收信号。")
    }

    var communicatorGlyph: some View {
        ZStack {
            if !reduceMotion {
                SignalPulseRings(tint: DesignTokens.sage, size: 82, lineWidth: 1.2, ringCount: 2)
                    .opacity(0.42)
            }

            Circle()
                .fill(
                    LinearGradient(
                        colors: [
                            DesignTokens.porcelain.opacity(0.98),
                            DesignTokens.mist.opacity(0.94)
                        ],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    )
                )
                .frame(width: 58, height: 58)
                .overlay {
                    Circle()
                        .stroke(DesignTokens.surfaceStroke.opacity(0.92), lineWidth: 1)
                }
                .shadow(color: DesignTokens.sage.opacity(0.16), radius: 14, x: 0, y: 8)

            PetSoulAssetIcon(
                asset: .communicator,
                fallbackSystemImage: "antenna.radiowaves.left.and.right",
                fallbackTint: DesignTokens.sage,
                size: 36
            )
        }
        .frame(width: 78, height: 78)
    }

    var detailText: String {
        "刚刚没能连上远方的信号站。别担心，TA 的旅程还在，等信号回来就能继续同步。"
    }

    var reasonText: String {
        let normalizedMessage = message.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        if normalizedMessage.contains("server") || normalizedMessage.contains("connect") {
            return "远方信号站暂时没有回应"
        }
        if normalizedMessage.contains("internet") || normalizedMessage.contains("network") || normalizedMessage.contains("offline") {
            return "当前网络有点不稳定"
        }
        return "通讯器会保留刚刚的位置"
    }
}

struct LoadingCommunicatorGlyph: View {
    var tint: Color
    var pulse: Double
    var routeProgress: Double

    var body: some View {
        ZStack {
            SignalPulseRings(
                tint: tint,
                size: 154 + CGFloat(pulse * 10),
                lineWidth: 1.4,
                ringCount: 3
            )
            .opacity(0.54)

            LoadingRoutePath(progress: routeProgress, tint: tint)
                .frame(width: 156, height: 112)

            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .fill(
                    LinearGradient(
                        colors: [
                            DesignTokens.porcelain.opacity(0.98),
                            DesignTokens.mist.opacity(0.94)
                        ],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    )
                )
                .frame(width: 78, height: 78)
                .overlay {
                    RoundedRectangle(cornerRadius: 18, style: .continuous)
                        .stroke(DesignTokens.surfaceStroke.opacity(0.9), lineWidth: 1)
                }
                .shadow(color: DesignTokens.deepInk.opacity(0.10), radius: 16, x: 0, y: 8)

            VStack(spacing: 5) {
                Image(systemName: "dot.radiowaves.left.and.right")
                    .font(.system(size: 22, weight: .semibold))
                    .foregroundStyle(tint)
                HStack(spacing: 4) {
                    ForEach(0..<4, id: \.self) { index in
                        RoundedRectangle(cornerRadius: 2, style: .continuous)
                            .fill(index <= Int(routeProgress * 4) ? tint : DesignTokens.softLine)
                            .frame(width: 7, height: 18 - CGFloat(index % 2) * 4)
                    }
                }
            }
        }
        .frame(width: 180, height: 150)
    }
}

struct LoadingRoutePath: View {
    var progress: Double
    var tint: Color

    var body: some View {
        Canvas { context, size in
            var path = Path()
            path.move(to: CGPoint(x: size.width * 0.12, y: size.height * 0.70))
            path.addCurve(
                to: CGPoint(x: size.width * 0.88, y: size.height * 0.30),
                control1: CGPoint(x: size.width * 0.30, y: size.height * 0.18),
                control2: CGPoint(x: size.width * 0.62, y: size.height * 0.90)
            )

            context.stroke(
                path,
                with: .color(DesignTokens.softLine.opacity(0.82)),
                style: StrokeStyle(lineWidth: 6, lineCap: .round, lineJoin: .round)
            )
            context.stroke(
                path.trimmedPath(from: 0, to: max(0.08, min(progress, 1))),
                with: .color(tint.opacity(0.82)),
                style: StrokeStyle(lineWidth: 6, lineCap: .round, lineJoin: .round)
            )

            let stops = [
                CGPoint(x: size.width * 0.12, y: size.height * 0.70),
                CGPoint(x: size.width * 0.47, y: size.height * 0.52),
                CGPoint(x: size.width * 0.88, y: size.height * 0.30)
            ]
            for (index, stop) in stops.enumerated() {
                let active = progress >= Double(index) / Double(max(stops.count - 1, 1))
                let rect = CGRect(x: stop.x - 7, y: stop.y - 7, width: 14, height: 14)
                context.fill(Path(ellipseIn: rect), with: .color(DesignTokens.surface.opacity(0.96)))
                context.fill(Path(ellipseIn: rect.insetBy(dx: 3, dy: 3)), with: .color((active ? tint : DesignTokens.softLine).opacity(0.95)))
            }
        }
        .allowsHitTesting(false)
        .accessibilityHidden(true)
    }
}

struct LoadingRouteDots: View {
    var activeIndex: Int
    var tint: Color

    var body: some View {
        HStack(spacing: 8) {
            ForEach(0..<3, id: \.self) { index in
                Capsule()
                    .fill(index == activeIndex ? tint : DesignTokens.softLine.opacity(0.86))
                    .frame(width: index == activeIndex ? 22 : 8, height: 8)
                    .animation(.spring(response: 0.32, dampingFraction: 0.86), value: activeIndex)
            }
        }
        .accessibilityHidden(true)
    }
}

enum RoutePerspective: String {
    case twoD = "2D"
    case threeD = "3D"

    var title: String { rawValue }

    var systemImage: String {
        switch self {
        case .twoD: "map.fill"
        case .threeD: "cube.fill"
        }
    }

    mutating func toggle() {
        self = self == .twoD ? .threeD : .twoD
    }
}

enum JourneySheet: String, Identifiable {
    case dayPlan
    case postcards
    case travelKit
    case souvenirs
    case worldCupQuest
    case dna
    case streetRank

    var id: String { rawValue }

    var presentationDetents: Set<PresentationDetent> {
        switch self {
        case .dayPlan, .travelKit, .souvenirs, .postcards, .worldCupQuest:
            return [.large]
        case .dna, .streetRank:
            return [.medium, .large]
        }
    }
}
