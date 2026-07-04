import SwiftUI

struct SoftCard<Content: View>: View {
    var padding: CGFloat = 16
    @ViewBuilder var content: Content

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            content
        }
        .padding(padding)
        .background(DesignTokens.surface.opacity(0.86))
        .clipShape(RoundedRectangle(cornerRadius: DesignTokens.cardRadius, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: DesignTokens.cardRadius, style: .continuous)
                .stroke(DesignTokens.surfaceStroke.opacity(0.8), lineWidth: 1)
        }
        .shadow(color: DesignTokens.deepInk.opacity(0.08), radius: 18, x: 0, y: 10)
    }
}
