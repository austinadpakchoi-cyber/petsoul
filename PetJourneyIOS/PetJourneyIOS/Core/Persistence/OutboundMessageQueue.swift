import Foundation
import SwiftData

/// 离线发件队列：断网时主人讯息先落盘，信号恢复后按写入顺序补发。
@MainActor
final class OutboundMessageQueue: ObservableObject {
    @Published private(set) var pendingCount = 0

    private let context: ModelContext
    private let petID: String
    private var isDraining = false

    init(petID: String, container: ModelContainer = PetSoulModelContainer.shared) {
        self.petID = petID
        context = ModelContext(container)
        refreshPendingCount()
    }

    func enqueue(text: String) {
        context.insert(OutboundMessage(petID: petID, text: text))
        try? context.save()
        refreshPendingCount()
    }

    /// 逐条补发；一旦失败立即停下，剩余讯息留到下次信号恢复。送达即删，历史由服务器消息流承载。
    func drain(send: (String) async throws -> Void) async {
        guard !isDraining else { return }
        isDraining = true
        defer {
            isDraining = false
            refreshPendingCount()
        }
        for message in queuedMessages() {
            message.stateRaw = OutboundMessageState.sending.rawValue
            message.attempts += 1
            try? context.save()
            do {
                try await send(message.text)
                context.delete(message)
                try? context.save()
            } catch {
                message.stateRaw = OutboundMessageState.queued.rawValue
                try? context.save()
                break
            }
        }
    }

    func purgeAll() {
        for message in allMessages() {
            context.delete(message)
        }
        try? context.save()
        refreshPendingCount()
    }

    static func purge(petID: String, container: ModelContainer = PetSoulModelContainer.shared) {
        OutboundMessageQueue(petID: petID, container: container).purgeAll()
    }

    private func queuedMessages() -> [OutboundMessage] {
        let pid = petID
        let queued = OutboundMessageState.queued.rawValue
        let descriptor = FetchDescriptor<OutboundMessage>(
            predicate: #Predicate { $0.petID == pid && $0.stateRaw == queued },
            sortBy: [SortDescriptor(\.createdAt)]
        )
        return (try? context.fetch(descriptor)) ?? []
    }

    private func allMessages() -> [OutboundMessage] {
        let pid = petID
        let descriptor = FetchDescriptor<OutboundMessage>(predicate: #Predicate { $0.petID == pid })
        return (try? context.fetch(descriptor)) ?? []
    }

    private func refreshPendingCount() {
        pendingCount = queuedMessages().count
    }
}
