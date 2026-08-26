import SwiftUI

/// 账号页：当前登录的 Apple 账号与 TA 的归属关系。
/// 重新选择 TA / 退出登录都会回到账号门禁，数据跟着账号走，不会被设备里的演示数据顶替。
struct AccountSheetView: View {
    @EnvironmentObject private var session: AppSessionStore
    @Environment(\.dismiss) private var dismiss

    let currentPetName: String?

    var body: some View {
        NavigationStack {
            ZStack {
                AppBackground()

                VStack(spacing: 0) {
                    VStack(spacing: 10) {
                        Image(systemName: "person.crop.circle.fill")
                            .font(.system(size: 46, weight: .medium))
                            .foregroundStyle(DesignTokens.sage)
                            .padding(.top, 22)

                        Text(displayTitle)
                            .font(.system(size: 24, weight: .semibold, design: .rounded))
                            .foregroundStyle(DesignTokens.ink)

                        if let currentPetName {
                            Text("现在陪着你的是 \(currentPetName)")
                                .font(.subheadline)
                                .foregroundStyle(DesignTokens.secondaryInk)
                        }

                        Text("TA 的照片、路线和回忆都保存在你的账号里，不会走散。")
                            .font(.footnote)
                            .foregroundStyle(DesignTokens.secondaryInk)
                            .multilineTextAlignment(.center)
                            .lineSpacing(3)
                            .padding(.horizontal, DesignTokens.pagePadding)
                    }
                    .padding(.bottom, 26)

                    VStack(spacing: 12) {
                        Button {
                            session.resetJourney()
                            dismiss()
                        } label: {
                            Label("重新选择 TA", systemImage: "dot.radiowaves.left.and.right")
                                .font(.subheadline.weight(.semibold))
                                .frame(maxWidth: .infinity)
                        }
                        .primaryActionStyle()

                        Button {
                            session.signOut()
                            dismiss()
                        } label: {
                            Label("退出登录", systemImage: "rectangle.portrait.and.arrow.right")
                                .font(.subheadline.weight(.semibold))
                                .frame(maxWidth: .infinity)
                        }
                        .buttonStyle(.bordered)
                        .tint(DesignTokens.ink)
                    }
                    .padding(.horizontal, DesignTokens.pagePadding)

                    Spacer()
                }
            }
            .navigationTitle("账号")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("完成") {
                        dismiss()
                    }
                    .foregroundStyle(DesignTokens.ink)
                }
            }
        }
    }

    private var displayTitle: String {
        if let name = session.userDisplayName, !name.isEmpty {
            return "\(name) 的旅程"
        }
        return "这位旅人的旅程"
    }
}
