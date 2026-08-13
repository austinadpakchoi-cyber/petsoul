import SwiftUI

/// 地图上唯一的情感状态卡（审计 #3、#5）：TA 是谁、在哪、正在做什么，
/// 附一句 TA 当下的状态低语。操作入口一律交给 MapControlDock，这里不放按钮。
struct PetPresenceCard: View {
    var petName: String
    var travelDay: Int
    var location: String
    var modeLabel: String
    var modeSystemImage: String
    var tint: Color
    var statusNote: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 7) {
            HStack(spacing: 9) {
                PetSoulAssetIcon(
                    asset: .signalPaw,
                    fallbackSystemImage: "dot.radiowaves.left.and.right",
                    fallbackTint: tint,
                    size: 26
                )
                .frame(width: 32, height: 32)
                .background(DesignTokens.mist.opacity(0.94))
                .clipShape(Circle())

                VStack(alignment: .leading, spacing: 2) {
                    Text("\(petName) · 第 \(travelDay) 天")
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(DesignTokens.ink)
                        .lineLimit(1)
                        .minimumScaleFactor(0.78)
                    Label("\(location) · \(modeLabel)", systemImage: modeSystemImage)
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(DesignTokens.secondaryInk)
                        .lineLimit(1)
                        .minimumScaleFactor(0.78)
                }
            }

            if let statusNote, !statusNote.isEmpty {
                Text(statusNote)
                    .font(.caption)
                    .foregroundStyle(DesignTokens.secondaryInk)
                    .lineLimit(2)
                    .lineSpacing(1.5)
            }
        }
        .padding(.vertical, 10)
        .padding(.horizontal, 12)
        .background(DesignTokens.surface.opacity(0.9))
        .clipShape(RoundedRectangle(cornerRadius: DesignTokens.cardRadius, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: DesignTokens.cardRadius, style: .continuous)
                .stroke(DesignTokens.surfaceStroke.opacity(0.75), lineWidth: 1)
        }
        .shadow(color: DesignTokens.deepInk.opacity(0.09), radius: 16, x: 0, y: 8)
        .accessibilityElement(children: .combine)
    }
}
