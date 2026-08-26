import Foundation
import SwiftData

/// 离线发件队列：断网时主人讯息先落盘，信号恢复后按写入顺序补发。
/// 每条消息独立计数：超过上限标记 failed（死信），不再阻塞后面的消息；
/// 死信对上层可见（failedCount），可经 retryFailed() 再给一次机会。
@MainActor
final class OutboundMessageQueue: ObservableObject {
    static let maxAttempts = 5

    struct DrainResult: Equatable {
        var delivered = 0
        var failed = 0
    }

    @Published private(set) var pendingCount = 0
    @Published private(set) var failedCount = 0

    private let context: ModelContext
    private let petID: String
    private var isDraining = false

    init(petID: String, container: ModelContainer = PetSoulModelContainer.shared) {
        self.petID = petID
        context = ModelContext(container)
        recoverInterruptedSending()
        refreshCounts()
    }

    func enqueue(text: String, clientMessageID: String = UUID().uuidString) {
        context.insert(OutboundMessage(petID: petID, text: text, clientMessageID: clientMessageID))
        try? context.save()
        refreshCounts()
    }

    /// 逐条补发：失败的消息独立回退为 queued 并累计 attempts；达到上限标记 failed（死信）并跳过，
    /// 不再阻塞队列中后面的消息。送达即删，历史由服务器消息流承载。
    /// 返回本轮真实的送达/失败计数——上层据此决定「已送达」文案，绝不谎报。
    @discardableResult
    func drain(send: (OutboundMessage) async throws -> Void) async -> DrainResult {
        guard !isDraining else { return DrainResult() }
        isDraining = true
        defer {
            isDraining = false
            refreshCounts()
        }
        var result = DrainResult()
        for message in queuedMessages() {
            message.stateRaw = OutboundMessageState.sending.rawValue
            message.attempts += 1
            try? context.save()
            do {
                try await send(message)
                context.delete(message)
                try? context.save()
                result.delivered += 1
            } catch {
                if message.attempts >= Self.maxAttempts {
                    message.stateRaw = OutboundMessageState.failed.rawValue
                    result.failed += 1
                } else {
                    message.stateRaw = OutboundMessageState.queued.rawValue
                }
                try? context.save()
            }
        }
        return result
    }

    /// 死信出口：把 failed 全部复位回 queued，再给一次机会（attempts 保留，
    /// 毒消息下一轮一次失败即回到死信，不会无限循环）。
    func retryFailed() {
        let pid = petID
        let failed = OutboundMessageState.failed.rawValue
        let descriptor = FetchDescriptor<OutboundMessage>(
            predicate: #Predicate { $0.petID == pid && $0.stateRaw == failed }
        )
        guard let messages = try? context.fetch(descriptor), !messages.isEmpty else { return }
        for message in messages {
            message.stateRaw = OutboundMessageState.queued.rawValue
        }
        try? context.save()
        refreshCounts()
    }

    func purgeAll() {
        for message in allMessages() {
            context.delete(message)
        }
        try? context.save()
        refreshCounts()
    }

    static func purge(petID: String, container: ModelContainer = PetSoulModelContainer.shared) {
        OutboundMessageQueue(petID: petID, container: container).purgeAll()
    }

    /// 进程中断恢复：上一次 drain 中断在发送中的消息（.sending 是崩溃黑点）
    /// 一律复位回 queued，让它们重回补发队列，绝不静默消失。
    private func recoverInterruptedSending() {
        let pid = petID
        let sending = OutboundMessageState.sending.rawValue
        let descriptor = FetchDescriptor<OutboundMessage>(
            predicate: #Predicate { $0.petID == pid && $0.stateRaw == sending }
        )
        guard let messages = try? context.fetch(descriptor), !messages.isEmpty else { return }
        for message in messages {
            message.stateRaw = OutboundMessageState.queued.rawValue
        }
        try? context.save()
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

    private func refreshCounts() {
        let pid = petID
        let queued = OutboundMessageState.queued.rawValue
        let failed = OutboundMessageState.failed.rawValue
        let queuedDescriptor = FetchDescriptor<OutboundMessage>(
            predicate: #Predicate { $0.petID == pid && $0.stateRaw == queued }
        )
        let failedDescriptor = FetchDescriptor<OutboundMessage>(
            predicate: #Predicate { $0.petID == pid && $0.stateRaw == failed }
        )
        pendingCount = (try? context.fetchCount(queuedDescriptor)) ?? 0
        failedCount = (try? context.fetchCount(failedDescriptor)) ?? 0
    }
}
