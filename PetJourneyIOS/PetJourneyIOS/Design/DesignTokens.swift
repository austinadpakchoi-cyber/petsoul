import SwiftUI

enum DesignTokens {
    static let cardRadius: CGFloat = 8
    static let controlRadius: CGFloat = 16
    static let pagePadding: CGFloat = 18

    static let ink = Color(hex: 0x1F2B2B)
    static let secondaryInk = Color(hex: 0x687774)
    static let softLine = Color(hex: 0xD8E1DE)
    static let porcelain = Color(hex: 0xF7F8F4)
    static let mist = Color(hex: 0xEEF5F2)
    static let sky = Color(hex: 0xE9F1F8)
    static let petal = Color(hex: 0xF7ECEF)
    static let sage = Color(hex: 0x5F8E81)
    static let dusk = Color(hex: 0x5D738F)
    static let clay = Color(hex: 0xB66F5E)
    static let amber = Color(hex: 0xC8A25E)
    static let sea = Color(hex: 0x78B7C5)
    static let pollen = Color(hex: 0xE7C77B)
}

extension Color {
    init(hex: UInt, opacity: Double = 1) {
        self.init(
            .sRGB,
            red: Double((hex >> 16) & 0xFF) / 255,
            green: Double((hex >> 8) & 0xFF) / 255,
            blue: Double(hex & 0xFF) / 255,
            opacity: opacity
        )
    }
}

struct AppBackground: View {
    var body: some View {
        ZStack {
            DesignTokens.porcelain
            LinearGradient(
                colors: [
                    DesignTokens.sky.opacity(0.76),
                    DesignTokens.porcelain,
                    DesignTokens.petal.opacity(0.72)
                ],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
            AmbientSignalField(
                tint: DesignTokens.sage,
                warmth: DesignTokens.clay,
                density: 12,
                drift: 0.42
            )
            .opacity(0.44)
        }
        .ignoresSafeArea()
    }
}

struct AmbientSignalField: View {
    var tint: Color = DesignTokens.sage
    var warmth: Color = DesignTokens.clay
    var density: Int = 18
    var drift: Double = 1

    var body: some View {
        TimelineView(.animation) { timeline in
            Canvas { context, size in
                let time = timeline.date.timeIntervalSinceReferenceDate * drift
                drawCurrentLines(in: &context, size: size, time: time)
                drawSignalMotes(in: &context, size: size, time: time)
            }
        }
        .allowsHitTesting(false)
        .accessibilityHidden(true)
    }

    private func drawCurrentLines(in context: inout GraphicsContext, size: CGSize, time: TimeInterval) {
        guard size.width > 0, size.height > 0 else { return }

        for index in 0..<4 {
            let progress = Double(index) / 3
            let phase = time * 0.12 + progress * 1.7
            var path = Path()
            let startY = size.height * (0.16 + 0.2 * progress) + CGFloat(sin(phase) * 14)
            let endY = size.height * (0.56 + 0.12 * progress) + CGFloat(cos(phase) * 12)

            path.move(to: CGPoint(x: -20, y: startY))
            path.addCurve(
                to: CGPoint(x: size.width + 20, y: endY),
                control1: CGPoint(x: size.width * 0.26, y: startY - 38 - CGFloat(index * 8)),
                control2: CGPoint(x: size.width * 0.74, y: endY + 40 + CGFloat(index * 6))
            )

            context.stroke(
                path,
                with: .color((index.isMultiple(of: 2) ? tint : warmth).opacity(0.07)),
                style: StrokeStyle(lineWidth: 1.1, lineCap: .round)
            )
        }
    }

    private func drawSignalMotes(in context: inout GraphicsContext, size: CGSize, time: TimeInterval) {
        guard size.width > 0, size.height > 0 else { return }

        for index in 0..<density {
            let seed = Double(index + 1)
            let xBase = fract(sin(seed * 12.9898) * 43_758.5453)
            let yBase = fract(sin(seed * 78.233) * 24_634.6345)
            let wave = sin(time * (0.22 + seed.truncatingRemainder(dividingBy: 5) * 0.018) + seed)
            let x = size.width * xBase + CGFloat(wave * 10)
            let y = size.height * yBase + CGFloat(cos(time * 0.16 + seed) * 16)
            let radius = CGFloat(1.2 + fract(seed * 0.618) * 2.4)
            let alpha = 0.07 + 0.08 * (0.5 + wave * 0.5)
            let rect = CGRect(x: x, y: y, width: radius, height: radius)

            context.fill(
                Path(ellipseIn: rect),
                with: .color((index.isMultiple(of: 3) ? warmth : tint).opacity(alpha))
            )
        }
    }

    private func fract(_ value: Double) -> CGFloat {
        CGFloat(value - floor(value))
    }
}

struct SignalPulseRings: View {
    var tint: Color = DesignTokens.sage
    var size: CGFloat = 96
    var lineWidth: CGFloat = 1.6
    var ringCount: Int = 3

    var body: some View {
        TimelineView(.animation) { timeline in
            let time = timeline.date.timeIntervalSinceReferenceDate

            ZStack {
                ForEach(0..<ringCount, id: \.self) { index in
                    let phase = (time * 0.48 + Double(index) / Double(max(ringCount, 1))).truncatingRemainder(dividingBy: 1)
                    let ringSize = size * CGFloat(0.58 + phase * 0.62)
                    Circle()
                        .stroke(tint.opacity(0.26 * (1 - phase)), lineWidth: lineWidth)
                        .frame(width: ringSize, height: ringSize)
                        .scaleEffect(CGFloat(1 + phase * 0.04))
                }
            }
        }
        .frame(width: size, height: size)
        .allowsHitTesting(false)
        .accessibilityHidden(true)
    }
}

struct SignalBars: View {
    var tint: Color = DesignTokens.sage
    var isActive = true

    var body: some View {
        TimelineView(.animation) { timeline in
            let time = timeline.date.timeIntervalSinceReferenceDate

            HStack(alignment: .center, spacing: 3) {
                ForEach(0..<5, id: \.self) { index in
                    let height = isActive ? 8 + CGFloat((sin(time * 2.4 + Double(index) * 0.72) + 1) * 5) : 6
                    Capsule()
                        .fill(tint.opacity(isActive ? 0.82 : 0.28))
                        .frame(width: 3, height: height)
                }
            }
        }
        .frame(width: 28, height: 22)
        .accessibilityHidden(true)
    }
}

extension View {
    func primaryActionStyle() -> some View {
        buttonStyle(PrimaryActionButtonStyle())
    }

    func quietActionStyle() -> some View {
        buttonStyle(QuietActionButtonStyle())
    }
}

struct PrimaryActionButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.headline)
            .foregroundStyle(.white)
            .frame(maxWidth: .infinity)
            .padding(.vertical, 16)
            .background(
                LinearGradient(
                    colors: [
                        DesignTokens.ink.opacity(configuration.isPressed ? 0.86 : 0.96),
                        DesignTokens.sage.opacity(configuration.isPressed ? 0.86 : 0.96)
                    ],
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                )
            )
            .clipShape(RoundedRectangle(cornerRadius: DesignTokens.controlRadius, style: .continuous))
            .shadow(color: DesignTokens.ink.opacity(configuration.isPressed ? 0.08 : 0.18), radius: 16, x: 0, y: 8)
            .scaleEffect(configuration.isPressed ? 0.985 : 1)
    }
}

struct QuietActionButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.subheadline.weight(.semibold))
            .foregroundStyle(DesignTokens.ink)
            .padding(.vertical, 11)
            .padding(.horizontal, 14)
            .background(.white.opacity(configuration.isPressed ? 0.62 : 0.82))
            .clipShape(RoundedRectangle(cornerRadius: DesignTokens.controlRadius, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: DesignTokens.controlRadius, style: .continuous)
                    .stroke(DesignTokens.softLine.opacity(0.8), lineWidth: 1)
            }
    }
}
