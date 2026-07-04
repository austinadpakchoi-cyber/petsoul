import SwiftUI

struct PetMarkerView: View {
    var petType: PetType
    var name: String

    var body: some View {
        VStack(spacing: 4) {
            ZStack {
                Circle()
                    .fill(.white)
                    .frame(width: 48, height: 48)
                    .shadow(color: DesignTokens.ink.opacity(0.14), radius: 14, x: 0, y: 7)
                Circle()
                    .fill(DesignTokens.petal)
                    .frame(width: 38, height: 38)
                Image(systemName: petType.symbolName)
                    .font(.system(size: 18, weight: .semibold))
                    .foregroundStyle(DesignTokens.clay)
            }

            Text(name)
                .font(.caption2.weight(.semibold))
                .foregroundStyle(DesignTokens.ink)
                .padding(.vertical, 4)
                .padding(.horizontal, 8)
                .background(.white.opacity(0.92))
                .clipShape(Capsule())
                .lineLimit(1)
                .minimumScaleFactor(0.75)
        }
    }
}
