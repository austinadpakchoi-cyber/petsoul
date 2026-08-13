import SwiftUI
import UIKit

enum DesignTokens {
    static let cardRadius: CGFloat = 18
    static let controlRadius: CGFloat = 14
    static let pagePadding: CGFloat = 18

    // 自适应色板：日间瓷白，夜间是灯下的暖夜色，不是纯黑。
    static let ink = Color(light: 0x1F2B2B, dark: 0xE9EEEA)
    static let secondaryInk = Color(light: 0x687774, dark: 0x9AA8A2)
    static let softLine = Color(light: 0xD8E1DE, dark: 0x37423E)
    static let porcelain = Color(light: 0xF7F8F4, dark: 0x131917)
    static let mist = Color(light: 0xEEF5F2, dark: 0x1A2320)
    static let sky = Color(light: 0xE9F1F8, dark: 0x16202B)
    static let petal = Color(light: 0xF7ECEF, dark: 0x261B21)
    static let sage = Color(light: 0x5F8E81, dark: 0x7FB5A5)
    static let dusk = Color(light: 0x5D738F, dark: 0x93A9C6)
    static let clay = Color(light: 0xB66F5E, dark: 0xCF8B78)
    static let amber = Color(light: 0xC8A25E, dark: 0xD9B678)
    static let sea = Color(light: 0x78B7C5, dark: 0x8AC5D2)
    static let pollen = Color(light: 0xE7C77B, dark: 0xE2C88F)

    // 语义表面：卡片、玻璃层与描边高光。
    static let surface = Color(light: 0xFFFFFF, dark: 0x1F2825)
    static let surfaceStroke = Color(light: 0xFFFFFF, dark: 0x3D4945)

    // 承载白色文字的实心填充与阴影：两种模式下都保持深色。
    static let deepInk = Color(light: 0x1F2B2B, dark: 0x0B100F)

    // 纸质纪念物（明信片等）是实物，夜里也保持暖纸配深墨。
    static let paper = Color(hex: 0xFAF0D6)
    static let paperShade = Color(hex: 0xF1E4C4)
    static let paperInk = Color(hex: 0x30352C)
    static let paperSecondaryInk = Color(hex: 0x77715C)
    static let paperAccent = Color(hex: 0x5D738F)

    // 下方均为「场景/实物」固定色（同 paper 系约定）：夜里也保持原有的暖纸/氛围/实物质感，
    // 不走 Color(light:dark:) 自适应，避免地图昼夜氛围、纸质插图、证件卡、欢迎暖调在夜间被
    // 错误翻转。这些原本散落在各 View 里的 hex 字面量收敛到此，作为唯一色值来源。

    /// 手账插图（IllustratedGuidePreview）的纸质底、描边与线圈装订。
    enum notebook {
        static let paper = Color(hex: 0xFFF6E5)
        static let stroke = Color(hex: 0xD8C8AA)
        static let binding = Color(hex: 0x9B8C78)
    }

    /// 地图昼夜氛围洗色（JourneyMapViewport）：时间场景色，非 UI 主题色。
    enum mapWash {
        static let dawnCream = Color(hex: 0xFBE8C8)
        static let duskMauve = Color(hex: 0x8A5A78)
        static let duskEmber = Color(hex: 0xE0956B)
        static let duskCream = Color(hex: 0xF6E3CE)
        static let nightDeep = Color(hex: 0x131E36)
        static let nightMid = Color(hex: 0x1E2A44)
        static let nightSoft = Color(hex: 0x2A3752)
        static let horizonGlow = Color(hex: 0xF8F2EA)
        static let nightStarlight = Color(hex: 0xFDF6DC)
    }

    /// 宠物证件卡渐变（PetCredentialModels / PetCredentialWallet）：实物卡面色。
    enum credential {
        static let identityDeep = Color(hex: 0x4E8074)
        static let identityLight = Color(hex: 0x9BC3B4)
        static let passportDeep = Color(hex: 0x33445E)
        static let passportLight = Color(hex: 0x6C7F9E)
        static let healthDeep = Color(hex: 0x6797A4)
        static let healthLight = Color(hex: 0xB7D8D7)
        static let driverDeep = Color(hex: 0xAF8441)
        static let driverLight = Color(hex: 0xE3C878)
        static let boardingDeep = Color(hex: 0x526D86)
        static let boardingLight = Color(hex: 0x9BB4C9)
        static let hotelDeep = Color(hex: 0xA46658)
        static let hotelLight = Color(hex: 0xE1A590)
        static let passportPhotoTop = Color(hex: 0xEAF4F7)
        static let passportPhotoBottom = Color(hex: 0xF8F2E6)
    }

    /// 欢迎/地球视角的暖纸暖棕主题（WelcomeView）。
    enum welcome {
        static let moodTop = Color(hex: 0xFFF7EF)
        static let moodBottom = Color(hex: 0xFFF9F0)
        static let radialBlush = Color(hex: 0xF8D9CF)
        static let radialCream = Color(hex: 0xF4EBD7)
        static let signalWarmth = Color(hex: 0xE0A25E)
        static let warmInk = Color(hex: 0x9E7866)
        static let chipCream = Color(hex: 0xFFF4EA)
        static let subInk = Color(hex: 0x7B766E)
        static let fallbackTint = Color(hex: 0xC8956D)
        static let iconCream = Color(hex: 0xFFF1E8)
        static let infoInk = Color(hex: 0x8C7166)
        static let shadowBrown = Color(hex: 0x7D5F54)
        static let tickerCream = Color(hex: 0xFFF9F1)
        static let pillCream = Color(hex: 0xFFF8F1)
        static let noteAccent = Color(hex: 0xC28A70)
    }

    /// 地图标注文字与阴影（WorldAnimalViews，UIKit）。
    enum annotation {
        static let cardSurface = UIColor(hex: 0xFDF9EF)
        static let shadowBrown = UIColor(hex: 0x6C554F)
        static let titleInk = UIColor(hex: 0x26302F)
        static let subtitleInk = UIColor(hex: 0x697673)
        static let generatedInk = UIColor(hex: 0x5F6C69)
    }

    /// 纪念品/明信片卡片（SecondaryViews）。
    enum souvenir {
        static let cardCream = Color(hex: 0xFFF7E8)
    }
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

    init(light: UInt, dark: UInt) {
        self.init(UIColor { traits in
            let hex = traits.userInterfaceStyle == .dark ? dark : light
            return UIColor(
                red: CGFloat((hex >> 16) & 0xFF) / 255,
                green: CGFloat((hex >> 8) & 0xFF) / 255,
                blue: CGFloat(hex & 0xFF) / 255,
                alpha: 1
            )
        })
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

    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        TimelineView(.animation(minimumInterval: 1 / 30, paused: reduceMotion)) { timeline in
            Canvas { context, size in
                let time = reduceMotion ? 0 : timeline.date.timeIntervalSinceReferenceDate * drift
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

    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        TimelineView(.animation(minimumInterval: 1 / 30, paused: reduceMotion)) { timeline in
            let time = reduceMotion ? 0 : timeline.date.timeIntervalSinceReferenceDate

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

    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        TimelineView(.animation(minimumInterval: 1 / 30, paused: reduceMotion)) { timeline in
            let time = timeline.date.timeIntervalSinceReferenceDate

            HStack(alignment: .center, spacing: 3) {
                ForEach(0..<5, id: \.self) { index in
                    let height = barHeight(index: index, time: time)
                    Capsule()
                        .fill(tint.opacity(isActive ? 0.82 : 0.28))
                        .frame(width: 3, height: height)
                }
            }
        }
        .frame(width: 28, height: 22)
        .accessibilityHidden(true)
    }

    private func barHeight(index: Int, time: TimeInterval) -> CGFloat {
        guard isActive else { return 6 }
        if reduceMotion {
            return [9, 13, 17, 12, 8][index]
        }
        return 8 + CGFloat((sin(time * 2.4 + Double(index) * 0.72) + 1) * 5)
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
                        DesignTokens.deepInk.opacity(configuration.isPressed ? 0.86 : 0.96),
                        DesignTokens.sage.opacity(configuration.isPressed ? 0.86 : 0.96)
                    ],
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                )
            )
            .clipShape(RoundedRectangle(cornerRadius: DesignTokens.controlRadius, style: .continuous))
            .shadow(color: DesignTokens.deepInk.opacity(configuration.isPressed ? 0.08 : 0.18), radius: 16, x: 0, y: 8)
            .scaleEffect(configuration.isPressed ? 0.97 : 1)
            .animation(.spring(response: 0.28, dampingFraction: 0.72), value: configuration.isPressed)
    }
}

struct QuietActionButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.subheadline.weight(.semibold))
            .foregroundStyle(DesignTokens.ink)
            .padding(.vertical, 11)
            .padding(.horizontal, 14)
            .background(DesignTokens.surface.opacity(configuration.isPressed ? 0.62 : 0.82))
            .clipShape(RoundedRectangle(cornerRadius: DesignTokens.controlRadius, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: DesignTokens.controlRadius, style: .continuous)
                    .stroke(DesignTokens.softLine.opacity(0.8), lineWidth: 1)
            }
            .scaleEffect(configuration.isPressed ? 0.98 : 1)
            .animation(.spring(response: 0.28, dampingFraction: 0.72), value: configuration.isPressed)
    }
}
