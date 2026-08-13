import CoreLocation
import Foundation

struct MemoryRecord: Codable, Identifiable, Equatable, Sendable {
    var id: String
    var petID: String
    var kind: String
    var title: String
    var content: String
    var salience: Double
    var source: String
    var createdAt: Date
    var lastSeenAt: Date
    var metadata: [String: JSONValue]
    var memoryType: String?
    var importance: Double?
    var emotionalValence: Double?
    var confidence: Double?
    var sourceEventID: String?
    var structuredPayload: [String: JSONValue]?

    enum CodingKeys: String, CodingKey {
        case id
        case petID = "pet_id"
        case kind
        case title
        case content
        case salience
        case source
        case createdAt = "created_at"
        case lastSeenAt = "last_seen_at"
        case metadata
        case memoryType = "memory_type"
        case importance
        case emotionalValence = "emotional_valence"
        case confidence
        case sourceEventID = "source_event_id"
        case structuredPayload = "structured_payload"
    }
}

struct MemoryCreateRequest: Codable, Equatable, Sendable {
    var kind: String
    var title: String
    var content: String
    var salience: Double
    var source: String
    var metadata: [String: JSONValue]
    var memoryType: String?
    var importance: Double?
    var emotionalValence: Double?
    var confidence: Double?
    var sourceEventID: String?
    var structuredPayload: [String: JSONValue]?

    enum CodingKeys: String, CodingKey {
        case kind
        case title
        case content
        case salience
        case source
        case metadata
        case memoryType = "memory_type"
        case importance
        case emotionalValence = "emotional_valence"
        case confidence
        case sourceEventID = "source_event_id"
        case structuredPayload = "structured_payload"
    }
}

struct MemoryUpdateRequest: Codable, Equatable, Sendable {
    var kind: String?
    var title: String?
    var content: String?
    var salience: Double?
    var source: String?
    var metadata: [String: JSONValue]?
    var memoryType: String?
    var importance: Double?
    var emotionalValence: Double?
    var confidence: Double?
    var sourceEventID: String?
    var structuredPayload: [String: JSONValue]?

    enum CodingKeys: String, CodingKey {
        case kind
        case title
        case content
        case salience
        case source
        case metadata
        case memoryType = "memory_type"
        case importance
        case emotionalValence = "emotional_valence"
        case confidence
        case sourceEventID = "source_event_id"
        case structuredPayload = "structured_payload"
    }
}

struct MemoryDeleteResponse: Codable, Equatable, Sendable {
    var success: Bool
    var memoryID: String

    enum CodingKeys: String, CodingKey {
        case success
        case memoryID = "memory_id"
    }
}

struct MemorySearchRequest: Codable, Equatable, Sendable {
    var query: String
    var limit: Int
}

struct MemorySearchResponse: Codable, Equatable, Sendable {
    var petID: String
    var query: String
    var provider: String
    var items: [MemoryRecord]

    enum CodingKeys: String, CodingKey {
        case petID = "pet_id"
        case query
        case provider
        case items
    }
}

