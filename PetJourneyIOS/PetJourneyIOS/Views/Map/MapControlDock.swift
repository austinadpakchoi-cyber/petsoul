import SwiftUI

/// 控制坞的动作集合，让 MapControlDock 与地图页解耦。
struct MapDockActions {
    var onCenter: () -> Void = {}
    var onTogglePerspective: () -> Void = {}
    var onToggleNearbySignals: () -> Void = {}
    var onShowDayPlan: () -> Void = {}
    var onShowRecap: () -> Void = {}
    var onShowPostcards: () -> Void = {}
    var onShowTravelKit: () -> Void = {}
    var onShowSouvenirs: () -> Void = {}
    var onShowStreetRank: () -> Void = {}
    var onShowDNA: () -> Void = {}
    var onShowAccount: () -> Void = {}
    var onReset: () -> Void = {}
}

/// 紧凑地图控制坞（审计 #3）：把散落的浮动控件收进右上角一列，
/// 让地图全出血、情感表达交给 PetPresenceCard。
struct MapControlDock: View {
    var hasUnreadPostcard: Bool
    var showNearbySignals: Bool
    var perspectiveTitle: String
    var perspectiveSystemImage: String
    var isSignedIn: Bool = false
    var accountName: String?
    var actions: MapDockActions

    var body: some View {
        VStack(spacing: 6) {
            menuButton
            dockButton(
                systemImage: "location.fill",
                tint: DesignTokens.sage,
                label: "回到 TA 的位置",
                action: actions.onCenter
            )
            dockButton(
                systemImage: perspectiveSystemImage,
                tint: DesignTokens.dusk,
                label: "切换视角：当前 \(perspectiveTitle)",
                action: actions.onTogglePerspective
            )
            dockButton(
                systemImage: showNearbySignals ? "eye.fill" : "eye.slash.fill",
                tint: DesignTokens.sea,
                label: showNearbySignals ? "隐藏附近信号" : "显示附近信号",
                action: actions.onToggleNearbySignals
            )
        }
        .padding(6)
        .background(DesignTokens.surface.opacity(0.88))
        .clipShape(Capsule())
        .overlay {
            Capsule().stroke(DesignTokens.surfaceStroke.opacity(0.78), lineWidth: 1)
        }
        .shadow(color: DesignTokens.deepInk.opacity(0.09), radius: 16, x: 0, y: 8)
    }

    private var menuButton: some View {
        Menu {
            Button(action: actions.onShowDayPlan) {
                Label("今日路线", systemImage: "map.fill")
            }
            Button(action: actions.onShowRecap) {
                Label("TA 的一天", systemImage: "play.rectangle.fill")
            }
            Button(action: actions.onShowPostcards) {
                Label(hasUnreadPostcard ? "查看新明信片" : "查看明信片", systemImage: "mail.stack")
            }
            Button(action: actions.onShowTravelKit) {
                Label("旅行小包", systemImage: "backpack.fill")
            }
            Button(action: actions.onShowSouvenirs) {
                Label("带回的小东西", systemImage: "gift.fill")
            }
            Button(action: actions.onShowStreetRank) {
                Label("这条街 TA 最想去哪", systemImage: "figure.walk.motion")
            }
            Divider()
            Button(action: actions.onShowAccount) {
                if isSignedIn {
                    Label("账号 · \(accountName ?? "已登录")", systemImage: "checkmark.icloud")
                } else {
                    Label("保存旅程到账号", systemImage: "person.crop.circle.badge.plus")
                }
            }
            Button(action: actions.onShowDNA) {
                Label("查看记忆档案", systemImage: "slider.horizontal.3")
            }
            Button(action: actions.onReset) {
                Label("重新寻找", systemImage: "arrow.counterclockwise")
            }
        } label: {
            ZStack(alignment: .topTrailing) {
                Image(systemName: "ellipsis")
                    .font(.subheadline.weight(.bold))
                    .foregroundStyle(DesignTokens.secondaryInk)
                    .frame(width: 40, height: 40)
                    .background(DesignTokens.mist.opacity(0.6))
                    .clipShape(Circle())
                if hasUnreadPostcard {
                    Circle()
                        .fill(DesignTokens.clay)
                        .frame(width: 8, height: 8)
                        .offset(x: -5, y: 5)
                }
            }
        }
        .accessibilityLabel(hasUnreadPostcard ? "更多（有新明信片）" : "更多")
    }

    private func dockButton(
        systemImage: String,
        tint: Color,
        label: String,
        action: @escaping () -> Void
    ) -> some View {
        Button(action: action) {
            Image(systemName: systemImage)
                .font(.system(size: 15, weight: .semibold))
                .foregroundStyle(tint)
                .frame(width: 40, height: 40)
                .background(DesignTokens.mist.opacity(0.6))
                .clipShape(Circle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel(label)
    }
}
