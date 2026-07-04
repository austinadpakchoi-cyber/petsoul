import Foundation

/// 推送点击后的应用内落点。
enum PushDestination: Equatable {
    case postcard(petID: String?)
    case thought(petID: String?)
    case message(petID: String?)
    case moment(petID: String?)
}

/// 通知点击 → Tab/弹层路由的桥。AppDelegate 写入 pending，
/// 主界面（JourneyHomeTabs）观察并消费后跳到对应模块。
@MainActor
final class PushDeepLinkRouter: ObservableObject {
    static let shared = PushDeepLinkRouter()

    @Published private(set) var pending: PushDestination?

    init() {}

    func handle(userInfo: [AnyHashable: Any]) {
        let aps = userInfo["aps"] as? [AnyHashable: Any]
        let category = (aps?["category"] as? String) ?? (userInfo["category"] as? String)
        let petID = userInfo["pet_id"] as? String
        switch category {
        case "postcard":
            pending = .postcard(petID: petID)
        case "thought":
            pending = .thought(petID: petID)
        case "message":
            pending = .message(petID: petID)
        case "moment_created", "moment":
            pending = .moment(petID: petID)
        default:
            break
        }
    }

    /// 读取并清空待处理落点；未消费前重复读取只会生效一次。
    func consume() -> PushDestination? {
        defer { pending = nil }
        return pending
    }
}
