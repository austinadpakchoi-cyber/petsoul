import Foundation
import SwiftData

/// 数据新鲜度：驱动 UI 上安静的"信号弱"提示，而不是错误弹窗。
enum DataFreshness: Equatable {
    case fresh
    case stale(Date?)
}

/// 缓存旁路仓库，服务器为真：请求成功写穿缓存；失败时读缓存并标记 stale。
@MainActor
final class JourneyCacheRepository {
    struct Snapshot<T> {
        let value: T
        let updatedAt: Date
    }

    private let context: ModelContext
    private let petID: String
    private let encoder: JSONEncoder
    private let decoder: JSONDecoder

    init(petID: String, container: ModelContainer = PetSoulModelContainer.shared) {
        self.petID = petID
        context = ModelContext(container)
        encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
    }

    func store<T: Encodable>(_ value: T, kind: PayloadKind) {
        guard let data = try? encoder.encode(value) else { return }
        if let row = fetchRow(kind: kind) {
            row.jsonData = data
            row.updatedAt = Date()
        } else {
            context.insert(CachedPayload(petID: petID, kind: kind.rawValue, jsonData: data))
        }
        try? context.save()
    }

    func load<T: Decodable>(_ type: T.Type, kind: PayloadKind) -> Snapshot<T>? {
        guard let row = fetchRow(kind: kind),
              let value = try? decoder.decode(T.self, from: row.jsonData) else { return nil }
        return Snapshot(value: value, updatedAt: row.updatedAt)
    }

    /// 远端优先：成功→写穿并返回 fresh；失败→回退缓存返回 stale；两者皆无→抛原错误。
    func remoteFirst<T: Codable>(_ kind: PayloadKind, fetch: () async throws -> T) async throws -> (value: T, freshness: DataFreshness) {
        do {
            let value = try await fetch()
            store(value, kind: kind)
            return (value, .fresh)
        } catch {
            if let cached = load(T.self, kind: kind) {
                return (cached.value, .stale(cached.updatedAt))
            }
            throw error
        }
    }

    func purgeAll() {
        for row in allRows() {
            context.delete(row)
        }
        try? context.save()
    }

    /// resetJourney 用：断开旅程时同步清掉该宠物的全部缓存。
    static func purge(petID: String, container: ModelContainer = PetSoulModelContainer.shared) {
        JourneyCacheRepository(petID: petID, container: container).purgeAll()
    }

    private func fetchRow(kind: PayloadKind) -> CachedPayload? {
        let pid = petID
        let kindValue = kind.rawValue
        var descriptor = FetchDescriptor<CachedPayload>(
            predicate: #Predicate { $0.petID == pid && $0.kind == kindValue }
        )
        descriptor.fetchLimit = 1
        return try? context.fetch(descriptor).first
    }

    private func allRows() -> [CachedPayload] {
        let pid = petID
        let descriptor = FetchDescriptor<CachedPayload>(predicate: #Predicate { $0.petID == pid })
        return (try? context.fetch(descriptor)) ?? []
    }
}
