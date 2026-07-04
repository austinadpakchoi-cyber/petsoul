import SwiftUI

struct EnergyRing: View {
    var title: String
    var value: Int
    var tint: Color

    private var progress: Double {
        Double(value) / 100
    }

    var body: some View {
        VStack(spacing: 8) {
            ZStack {
                Circle()
                    .stroke(DesignTokens.softLine.opacity(0.72), lineWidth: 7)
                Circle()
                    .trim(from: 0, to: progress)
                    .stroke(tint, style: StrokeStyle(lineWidth: 7, lineCap: .round))
                    .rotationEffect(.degrees(-90))
                Text("\(value)")
                    .font(.system(size: 17, weight: .semibold, design: .rounded))
                    .foregroundStyle(DesignTokens.ink)
                    .monospacedDigit()
            }
            .frame(width: 58, height: 58)

            Text(title)
                .font(.caption)
                .foregroundStyle(DesignTokens.secondaryInk)
                .lineLimit(1)
                .minimumScaleFactor(0.78)
        }
        .frame(maxWidth: .infinity)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(title) \(value)")
    }
}
