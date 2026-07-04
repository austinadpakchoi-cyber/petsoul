import Foundation
import Network

/// 网络可达性监视。离线时 UI 显示安静的"信号弱"提示，不弹错误 toast。
@MainActor
final class NetworkMonitor: ObservableObject {
    @Published private(set) var isOnline = true

    private let monitor: NWPathMonitor?

    /// startsMonitoring 传 false 用于测试与预览，可达状态由 apply(isOnline:) 驱动。
    init(startsMonitoring: Bool = true) {
        guard startsMonitoring else {
            monitor = nil
            return
        }
        let monitor = NWPathMonitor()
        self.monitor = monitor
        monitor.pathUpdateHandler = { [weak self] path in
            let satisfied = path.status == .satisfied
            Task { @MainActor [weak self] in
                self?.apply(isOnline: satisfied)
            }
        }
        monitor.start(queue: DispatchQueue(label: "petsoul.network-monitor"))
    }

    func apply(isOnline: Bool) {
        guard self.isOnline != isOnline else { return }
        self.isOnline = isOnline
    }

    deinit {
        monitor?.cancel()
    }
}
