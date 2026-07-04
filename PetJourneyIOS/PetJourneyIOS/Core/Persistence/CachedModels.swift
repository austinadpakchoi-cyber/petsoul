import Foundation
import SwiftData

/// 快照类数据的通用缓存行：按 (petID, kind) 一行，值为业务 Codable 结构的 JSON。
/// 不给两万行模型建关系表——新增业务面只需在 PayloadKind 补一个 case。
@Model
final class CachedPayload {
    var petID: String
    var kind: String
    var jsonData: Data
    var updatedAt: Date

    init(petID: String, kind: String, jsonData: Data, updatedAt: Date = Date()) {
        self.petID = petID
        self.kind = kind
        self.jsonData = jsonData
        self.updatedAt = updatedAt
    }
}

/// 离线时写下的主人讯息，重连后按写入顺序补发。
@Model
final class OutboundMessage {
    var petID: String
    var text: String
    var createdAt: Date
    var stateRaw: String
    var attempts: Int

    init(petID: String, text: String, createdAt: Date = Date()) {
        self.petID = petID
        self.text = text
        self.createdAt = createdAt
        stateRaw = OutboundMessageState.queued.rawValue
        attempts = 0
    }
}

enum OutboundMessageState: String {
    case queued
    case sending
    case sent
    case failed
}

/// 缓存槽位。
enum PayloadKind: String, CaseIterable {
    case agentStatus
    case cityPosition
    case dayPlan
    case journeyPlan
    case worldSnapshot
    case economy
    case travelQuests
    case souvenirs
    case illustratedGuide
    case dna
    case moments
    case communicatorMessages
    case memories
}
