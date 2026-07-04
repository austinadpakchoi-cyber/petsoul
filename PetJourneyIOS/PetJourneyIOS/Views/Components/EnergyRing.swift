import SwiftUI

struct EnergyRing: View {
    var title: String
    var value: Int
    var tint: Color

    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var displayedProgress: Double = 0

    private var progress: Double {
        Double(value) / 100
    }

    var body: some View {
        VStack(spacing: 8) {
            ZStack {
                Circle()
                    .stroke(DesignTokens.softLine.opacity(0.72), lineWidth: 7)
                Circle()
                    .trim(from: 0, to: displayedProgress)
                    .stroke(tint, style: StrokeStyle(lineWidth: 7, lineCap: .round))
                    .rotationEffect(.degrees(-90))
                Text("\(value)")
                    .font(.system(size: 17, weight: .semibold, design: .rounded))
                    .foregroundStyle(DesignTokens.ink)
                    .monospacedDigit()
                    .contentTransition(.numericText(value: Double(value)))
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
        .onAppear {
            if reduceMotion {
                displayedProgress = progress
            } else {
                withAnimation(.spring(response: 0.9, dampingFraction: 0.82).delay(0.12)) {
                    displayedProgress = progress
                }
            }
        }
        .onChange(of: value) { _, _ in
            withAnimation(reduceMotion ? nil : .spring(response: 0.6, dampingFraction: 0.8)) {
                displayedProgress = progress
            }
        }
    }
}
