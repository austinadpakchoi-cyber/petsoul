import SwiftUI

/// 「TA 在这里」：登录账号名下已有的宠物。
/// 数据跟着账号走——换设备登录，TA 会在这里重新出现；也可以随时寻找新的 TA。
struct PetPickerView: View {
    let pets: [AuthPetSummary]
    var onSelect: (AuthPetSummary) -> Void
    var onFindNew: () -> Void

    var body: some View {
        ZStack {
            AppBackground()

            AmbientSignalField(
                tint: DesignTokens.sage,
                warmth: DesignTokens.pollen,
                density: 14,
                drift: 0.42
            )
            .opacity(0.42)

            VStack(spacing: 0) {
                // P2-2：内容向视觉中心收拢，空态不「断开」
                Spacer(minLength: 20)

                VStack(spacing: 10) {
                    Text("TA 在这里")
                        .font(.system(size: 32, weight: .semibold, design: .rounded))
                        .foregroundStyle(DesignTokens.ink)

                    Text("这些都是跟着你账号的 TA。选一位，继续你们的旅程。")
                        .font(.subheadline)
                        .foregroundStyle(DesignTokens.secondaryInk)
                        .multilineTextAlignment(.center)
                        .lineSpacing(4)
                }
                .padding(.horizontal, DesignTokens.pagePadding)
                .padding(.top, 48)
                .padding(.bottom, 26)

                if pets.isEmpty {
                    emptyState
                } else {
                    ScrollView {
                        VStack(spacing: 14) {
                            ForEach(pets) { pet in
                                petCard(pet)
                            }
                        }
                        .padding(.horizontal, DesignTokens.pagePadding)
                        .padding(.bottom, 18)
                    }
                }

                Spacer(minLength: 12)

                Button(action: onFindNew) {
                    Label(pets.isEmpty ? "开始寻找 TA" : "寻找新的 TA", systemImage: "antenna.radiowaves.left.and.right")
                        .font(.subheadline.weight(.semibold))
                        .frame(maxWidth: .infinity)
                }
                .primaryActionStyle()
                .padding(.horizontal, DesignTokens.pagePadding)
                .padding(.bottom, 26)
            }
        }
    }

    private var emptyState: some View {
        VStack(spacing: 14) {
            Image(systemName: "dot.radiowaves.left.and.right")
                .font(.system(size: 40, weight: .medium))
                .foregroundStyle(DesignTokens.sage)

            Text("还没有 TA 等在这里。\n用一张你最熟悉的照片，开始第一次寻找。")
                .font(.subheadline)
                .foregroundStyle(DesignTokens.secondaryInk)
                .multilineTextAlignment(.center)
                .lineSpacing(5)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 36)
        .padding(.horizontal, DesignTokens.pagePadding)
    }

    private func petCard(_ pet: AuthPetSummary) -> some View {
        Button {
            onSelect(pet)
        } label: {
            HStack(spacing: 14) {
                AsyncImage(url: pet.photoURL) { phase in
                    switch phase {
                    case .success(let image):
                        image
                            .resizable()
                            .scaledToFill()
                    default:
                        ZStack {
                            DesignTokens.surface
                            Image(systemName: "pawprint.fill")
                                .foregroundStyle(DesignTokens.sage.opacity(0.7))
                        }
                    }
                }
                .frame(width: 58, height: 58)
                .clipShape(RoundedRectangle(cornerRadius: DesignTokens.controlRadius, style: .continuous))

                VStack(alignment: .leading, spacing: 3) {
                    Text(pet.name)
                        .font(.headline)
                        .foregroundStyle(DesignTokens.ink)
                    Text(pet.petType.displayName)
                        .font(.footnote)
                        .foregroundStyle(DesignTokens.secondaryInk)
                }

                Spacer()

                Image(systemName: "chevron.right")
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(DesignTokens.secondaryInk)
            }
            .padding(14)
            .background(DesignTokens.surface.opacity(0.86))
            .clipShape(RoundedRectangle(cornerRadius: DesignTokens.cardRadius, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: DesignTokens.cardRadius, style: .continuous)
                    .stroke(DesignTokens.surfaceStroke, lineWidth: 1)
            }
        }
        .buttonStyle(.plain)
    }
}
