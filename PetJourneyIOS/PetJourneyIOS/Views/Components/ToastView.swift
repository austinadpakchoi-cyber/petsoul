import SwiftUI

struct ToastView: View {
    var message: String

    var body: some View {
        Text(message)
            .font(.subheadline.weight(.semibold))
            .foregroundStyle(.white)
            .multilineTextAlignment(.center)
            .padding(.vertical, 12)
            .padding(.horizontal, 16)
            .frame(maxWidth: .infinity)
            .background(DesignTokens.ink.opacity(0.92))
            .clipShape(RoundedRectangle(cornerRadius: DesignTokens.controlRadius, style: .continuous))
            .padding(.horizontal, DesignTokens.pagePadding)
            .shadow(color: DesignTokens.ink.opacity(0.18), radius: 18, x: 0, y: 10)
    }
}
