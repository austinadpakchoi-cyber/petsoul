import Foundation
import SwiftData

enum PetSoulModelContainer {
    /// 磁盘容器打不开时退回内存容器：App 照常可用，只是本次会话失去离线兜底。
    static let shared: ModelContainer = {
        if let container = try? make(inMemory: false) {
            return container
        }
        return try! make(inMemory: true)
    }()

    static func make(inMemory: Bool) throws -> ModelContainer {
        let schema = Schema([CachedPayload.self, OutboundMessage.self])
        let configuration = ModelConfiguration(schema: schema, isStoredInMemoryOnly: inMemory)
        return try ModelContainer(for: schema, configurations: [configuration])
    }
}
