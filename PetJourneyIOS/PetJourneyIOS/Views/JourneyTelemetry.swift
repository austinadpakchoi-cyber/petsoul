import AuthenticationServices
import MapKit
import SwiftUI
import UIKit

struct PixelPetActivityAnimation: View {
    var hint: String
    var petType: PetType
    var tint: Color
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        TimelineView(.animation(minimumInterval: 1 / 30, paused: reduceMotion)) { timeline in
            let time = reduceMotion ? 0 : timeline.date.timeIntervalSinceReferenceDate
            Canvas { context, size in
                let tick = Int(time * 3) % 4
                let cell = min(size.width, size.height) / 12
                let origin = CGPoint(
                    x: (size.width - cell * 12) / 2,
                    y: (size.height - cell * 12) / 2
                )

                func rect(_ x: Int, _ y: Int, _ color: Color, alpha: Double = 1.0) {
                    let inset = max(0.35, cell * 0.08)
                    let frame = CGRect(
                        x: origin.x + CGFloat(x) * cell + inset,
                        y: origin.y + CGFloat(y) * cell + inset,
                        width: cell - inset * 2,
                        height: cell - inset * 2
                    )
                    context.fill(Path(frame), with: .color(color.opacity(alpha)))
                }

                let ink = DesignTokens.ink
                let soft = tint.opacity(0.82)
                let warm = DesignTokens.pollen
                let blush = DesignTokens.clay
                let bodyOffset = hint == "walking" ? (tick % 2) : 0

                drawPet(rect: rect, ink: ink, soft: soft, warm: warm, bodyOffset: bodyOffset)

                switch hint {
                case "coffee_drink":
                    drawCup(rect: rect, tick: tick, color: blush)
                case "gaming":
                    drawScreen(rect: rect, tick: tick, color: DesignTokens.dusk)
                case "camera":
                    drawCamera(rect: rect, tick: tick, color: warm)
                case "transport_flight":
                    drawPlane(rect: rect, tick: tick, color: DesignTokens.dusk)
                case "transport_train":
                    drawTrain(rect: rect, tick: tick, color: DesignTokens.sage)
                case "transport_car":
                    drawCar(rect: rect, tick: tick, color: DesignTokens.amber)
                case "transport_ferry", "sightseeing_sea":
                    drawWaves(rect: rect, tick: tick, color: DesignTokens.dusk)
                case "snack":
                    drawSnack(rect: rect, tick: tick, color: warm)
                case "sleep":
                    drawSleep(rect: rect, tick: tick, color: DesignTokens.dusk)
                default:
                    drawSpark(rect: rect, tick: tick, color: soft)
                }
            }
        }
        .accessibilityLabel(accessibilityLabel)
    }

    var accessibilityLabel: String {
        switch hint {
        case "coffee_drink": "TA 正在喝咖啡"
        case "gaming": "TA 正在玩游戏"
        case "camera": "TA 正在观察附近"
        case "transport_flight": "TA 正在乘飞机"
        case "transport_train": "TA 正在乘火车"
        case "transport_car": "TA 正在坐车"
        case "transport_ferry": "TA 正在坐船"
        case "snack": "TA 正在吃东西"
        case "sleep": "TA 正在休息"
        case "walking": "TA 正在散步"
        default: "TA 正在观察附近"
        }
    }

    func drawPet(
        rect: (Int, Int, Color, Double) -> Void,
        ink: Color,
        soft: Color,
        warm: Color,
        bodyOffset: Int
    ) {
        switch petType {
        case .rabbit:
            for (x, y) in [(4, 0), (4, 1), (7, 0), (7, 1), (4, 2), (7, 2)] {
                rect(x, y + bodyOffset, ink, 0.9)
            }
        case .cat:
            for (x, y) in [(3, 2), (4, 1), (7, 1), (8, 2)] {
                rect(x, y + bodyOffset, ink, 0.92)
            }
        case .parrot, .bird:
            for (x, y) in [(4, 2), (7, 2), (3, 3), (8, 3)] {
                rect(x, y + bodyOffset, ink, 0.85)
            }
            rect(8, 5 + bodyOffset, warm, 0.95)
            rect(9, 5 + bodyOffset, warm, 0.75)
        case .hamster:
            for (x, y) in [(3, 3), (8, 3), (3, 4), (8, 4)] {
                rect(x, y + bodyOffset, ink, 0.82)
            }
        case .dog, .other:
            for (x, y) in [(3, 2), (3, 3), (8, 2), (8, 3)] {
                rect(x, y + bodyOffset, ink, 0.92)
            }
        }

        for x in 4...7 {
            rect(x, 3 + bodyOffset, ink, 0.92)
            rect(x, 4 + bodyOffset, ink, 0.92)
        }
        rect(3, 4 + bodyOffset, ink, 0.88)
        rect(8, 4 + bodyOffset, ink, 0.88)
        rect(5, 4 + bodyOffset, warm, 0.86)
        rect(7, 4 + bodyOffset, warm, 0.86)
        rect(6, 5 + bodyOffset, soft, 0.9)

        if petType == .parrot || petType == .bird {
            rect(3, 6 + bodyOffset, soft, 0.74)
            rect(4, 7 + bodyOffset, soft, 0.56)
            rect(8, 6 + bodyOffset, soft, 0.74)
        }

        for x in 4...8 {
            rect(x, 6 + bodyOffset, ink, 0.9)
            rect(x, 7 + bodyOffset, ink, 0.82)
        }
        rect(3, 7 + bodyOffset, ink, 0.7)
        rect(8, 8 + bodyOffset, ink, 0.7)
    }

    func drawCup(rect: (Int, Int, Color, Double) -> Void, tick: Int, color: Color) {
        rect(9, 7, color, 0.9)
        rect(10, 7, color, 0.9)
        rect(9, 8, color, 0.84)
        rect(10, 8, color, 0.84)
        rect(11, 8, color, 0.5)
        rect(9, 5 - tick % 2, color, 0.34)
        rect(10, 4 + tick % 2, color, 0.26)
    }

    func drawScreen(rect: (Int, Int, Color, Double) -> Void, tick: Int, color: Color) {
        for x in 8...10 {
            rect(x, 6, color, 0.82)
            rect(x, 7, color, tick % 2 == 0 ? 0.45 : 0.72)
        }
        rect(9, 8, color, 0.55)
        rect(8 + tick % 2, 9, color, 0.7)
    }

    func drawCamera(rect: (Int, Int, Color, Double) -> Void, tick: Int, color: Color) {
        for x in 8...10 {
            rect(x, 7, color, 0.84)
            rect(x, 8, color, 0.78)
        }
        rect(9, 8, .white, 0.9)
        if tick == 0 {
            rect(10, 5, color, 0.55)
            rect(11, 4, color, 0.42)
        }
    }

    func drawPlane(rect: (Int, Int, Color, Double) -> Void, tick: Int, color: Color) {
        let y = 8 - tick % 2
        for x in 7...10 { rect(x, y, color, 0.78) }
        rect(9, y - 1, color, 0.7)
        rect(9, y + 1, color, 0.7)
        rect(11, y, color, 0.48)
    }

    func drawTrain(rect: (Int, Int, Color, Double) -> Void, tick: Int, color: Color) {
        for x in 7...10 {
            rect(x, 7, color, 0.82)
            rect(x, 8, color, 0.72)
        }
        rect(8, 7, .white, 0.72)
        rect(10, 9, color, tick % 2 == 0 ? 0.72 : 0.4)
    }

    func drawCar(rect: (Int, Int, Color, Double) -> Void, tick: Int, color: Color) {
        for x in 7...10 { rect(x, 8, color, 0.8) }
        rect(8, 7, color, 0.64)
        rect(9, 7, color, 0.64)
        rect(7, 9, color, tick % 2 == 0 ? 0.75 : 0.45)
        rect(10, 9, color, tick % 2 == 0 ? 0.45 : 0.75)
    }

    func drawWaves(rect: (Int, Int, Color, Double) -> Void, tick: Int, color: Color) {
        for x in 7...11 where (x + tick) % 2 == 0 {
            rect(x, 9, color, 0.5)
        }
        for x in 8...10 where (x + tick) % 2 == 1 {
            rect(x, 10, color, 0.35)
        }
    }

    func drawSnack(rect: (Int, Int, Color, Double) -> Void, tick: Int, color: Color) {
        rect(9, 7, color, 0.9)
        rect(10, 7, color, 0.78)
        rect(9, 8, color, 0.7)
        rect(8, 6 + tick % 2, color, 0.38)
    }

    func drawSleep(rect: (Int, Int, Color, Double) -> Void, tick: Int, color: Color) {
        for x in 3...8 {
            rect(x, 7, DesignTokens.sky, 0.62)
            rect(x, 8, color, 0.28)
        }
        rect(2, 6, .white, 0.74)
        rect(3, 6, .white, 0.58)
        rect(8, 3, color, tick == 0 ? 0.35 : 0.8)
        rect(9, 2, color, tick == 1 ? 0.35 : 0.7)
        rect(10, 1, color, tick == 2 ? 0.35 : 0.62)
    }

    func drawSpark(rect: (Int, Int, Color, Double) -> Void, tick: Int, color: Color) {
        rect(9, 5, color, tick % 2 == 0 ? 0.72 : 0.28)
        rect(10, 4, color, tick % 2 == 1 ? 0.66 : 0.25)
        rect(10, 6, color, 0.42)
    }
}

struct RouteStatusLine: View {
    var routePlan: JourneyRoutePlan
    var activity: JourneyActivitySnapshot

    var body: some View {
        HStack(spacing: 7) {
            Label(activity.modeLabel, systemImage: activity.systemImage)
                .lineLimit(1)
            Spacer(minLength: 0)
            Text(activity.statusValue(routePlan: routePlan))
                .lineLimit(1)
        }
        .font(.caption.weight(.semibold))
        .foregroundStyle(DesignTokens.secondaryInk)
        .padding(.vertical, 8)
        .padding(.horizontal, 10)
        .background(DesignTokens.mist.opacity(0.5))
        .clipShape(RoundedRectangle(cornerRadius: 13, style: .continuous))
    }
}

struct NavigationTelemetryStrip: View {
    var routePlan: JourneyRoutePlan
    var activity: JourneyActivitySnapshot
    var nextStop: String
    @State var isMusicExpanded = false

    var body: some View {
        VStack(alignment: .leading, spacing: 9) {
            HStack(spacing: 8) {
                Label(activity.modeLabel, systemImage: activity.systemImage)
                    .lineLimit(1)
                Spacer(minLength: 0)
                Text(activity.statusValue(routePlan: routePlan))
                    .lineLimit(1)
            }
            .font(.caption.weight(.semibold))
            .foregroundStyle(DesignTokens.secondaryInk)

            GeometryReader { proxy in
                ZStack(alignment: .leading) {
                    Capsule()
                        .fill(DesignTokens.surface.opacity(0.58))
                    Capsule()
                        .fill(activity.tint.opacity(0.76))
                        .frame(width: max(12, proxy.size.width * activity.progress))
                    NavigationProgressGlint(tint: activity.tint)
                        .clipShape(Capsule())
                }
            }
            .frame(height: 7)

            HStack(spacing: 6) {
                Image(systemName: "arrow.triangle.turn.up.right.diamond.fill")
                    .font(.caption2.weight(.bold))
                    .foregroundStyle(activity.tint)
                Text("下一站 \(nextStop)")
                    .lineLimit(1)
                    .minimumScaleFactor(0.76)
                Spacer(minLength: 0)
                Text(activity.speedText)
                    .lineLimit(1)
                Text("·")
                Text(routePlan.sourceLabel)
                    .lineLimit(1)
            }
            .font(.caption2.weight(.semibold))
            .foregroundStyle(DesignTokens.secondaryInk)

            if let musicCue {
                Button {
                    withAnimation(.spring(response: 0.28, dampingFraction: 0.86)) {
                        isMusicExpanded.toggle()
                    }
                } label: {
                    VStack(alignment: .leading, spacing: 5) {
                        HStack(spacing: 7) {
                            Image(systemName: "headphones")
                                .font(.caption.weight(.bold))
                                .foregroundStyle(activity.tint)
                            Text("路上的歌")
                                .font(.caption2.weight(.bold))
                                .foregroundStyle(DesignTokens.secondaryInk)
                            Text(musicCue.title)
                                .font(.caption.weight(.semibold))
                                .foregroundStyle(DesignTokens.ink)
                                .lineLimit(1)
                            Spacer(minLength: 0)
                            Image(systemName: isMusicExpanded ? "chevron.up" : "chevron.down")
                                .font(.caption2.weight(.bold))
                                .foregroundStyle(DesignTokens.secondaryInk)
                        }

                        if isMusicExpanded {
                            Text(musicCue.detail)
                                .font(.caption2)
                                .foregroundStyle(DesignTokens.secondaryInk)
                                .lineSpacing(2)
                                .fixedSize(horizontal: false, vertical: true)
                                .transition(.opacity.combined(with: .move(edge: .top)))
                        }
                    }
                    .padding(.vertical, 8)
                    .padding(.horizontal, 9)
                    .background(DesignTokens.surface.opacity(0.58))
                    .clipShape(RoundedRectangle(cornerRadius: 13, style: .continuous))
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.vertical, 10)
        .padding(.horizontal, 11)
        .background(DesignTokens.mist.opacity(0.46))
        .clipShape(RoundedRectangle(cornerRadius: 15, style: .continuous))
    }

    var musicCue: JourneyMusicCue? {
        switch activity.kind {
        case .walking:
            JourneyMusicCue(
                title: "Island in the Sun",
                detail: "TA 把声音放得很低，边听边沿着路线慢慢走。以后这段歌会跟着当天回放一起存下来。"
            )
        case .transporting:
            JourneyMusicCue(
                title: "You Are Beautiful",
                detail: "车窗外的光在移动，TA 安静听着这首歌去下一站。"
            )
        default:
            nil
        }
    }
}


struct NavigationProgressGlint: View {
    var tint: Color
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        TimelineView(.animation(minimumInterval: 1 / 30, paused: reduceMotion)) { timeline in
            let time = reduceMotion ? 0 : timeline.date.timeIntervalSinceReferenceDate
            GeometryReader { proxy in
                let phase = time.truncatingRemainder(dividingBy: 2.4) / 2.4
                let width = proxy.size.width
                LinearGradient(
                    colors: [
                        .clear,
                        tint.opacity(0.0),
                        .white.opacity(0.62),
                        tint.opacity(0.0),
                        .clear
                    ],
                    startPoint: .leading,
                    endPoint: .trailing
                )
                .frame(width: width * 0.42)
                .offset(x: -width * 0.42 + width * phase * 1.42)
            }
        }
        .allowsHitTesting(false)
        .accessibilityHidden(true)
    }
}

struct NavigationPulseDot: View {
    var tint: Color
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        TimelineView(.animation(minimumInterval: 1 / 30, paused: reduceMotion)) { timeline in
            let time = reduceMotion ? 0 : timeline.date.timeIntervalSinceReferenceDate
            let phase = (time * 0.9).truncatingRemainder(dividingBy: 1)
            Circle()
                .fill(tint.opacity(0.72))
                .frame(width: 6, height: 6)
                .overlay {
                    Circle()
                        .stroke(tint.opacity(0.28 * (1 - phase)), lineWidth: 1.2)
                        .frame(width: 6 + CGFloat(phase * 13), height: 6 + CGFloat(phase * 13))
                }
        }
        .frame(width: 16, height: 16)
        .allowsHitTesting(false)
        .accessibilityHidden(true)
    }
}
