import CoreLocation
import Foundation

struct DeviceRegistrationRequest: Codable, Equatable, Sendable {
    var petID: String
    var deviceToken: String
    var platform: String
    var environment: String

    enum CodingKeys: String, CodingKey {
        case petID = "pet_id"
        case deviceToken = "device_token"
        case platform
        case environment
    }
}

struct DeviceRegistrationResponse: Codable, Equatable, Sendable {
    var success: Bool
    var deviceID: String
    var provider: String
    var message: String

    enum CodingKeys: String, CodingKey {
        case success
        case deviceID = "device_id"
        case provider
        case message
    }
}

struct NotificationDelivery: Codable, Identifiable, Equatable, Sendable {
    var id: String
    var petID: String
    var deviceToken: String?
    var title: String
    var body: String
    var category: String
    var provider: String
    var status: String
    var timestamp: Date
    var error: String?

    enum CodingKeys: String, CodingKey {
        case id
        case petID = "pet_id"
        case deviceToken = "device_token"
        case title
        case body
        case category
        case provider
        case status
        case timestamp
        case error
    }
}

indirect enum JSONValue: Codable, Equatable, Sendable {
    case string(String)
    case number(Double)
    case bool(Bool)
    case object([String: JSONValue])
    case array([JSONValue])
    case null

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if container.decodeNil() {
            self = .null
        } else if let value = try? container.decode(Bool.self) {
            self = .bool(value)
        } else if let value = try? container.decode(Double.self) {
            self = .number(value)
        } else if let value = try? container.decode(String.self) {
            self = .string(value)
        } else if let value = try? container.decode([String: JSONValue].self) {
            self = .object(value)
        } else if let value = try? container.decode([JSONValue].self) {
            self = .array(value)
        } else {
            throw DecodingError.dataCorruptedError(in: container, debugDescription: "Unsupported JSON value")
        }
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self {
        case .string(let value):
            try container.encode(value)
        case .number(let value):
            try container.encode(value)
        case .bool(let value):
            try container.encode(value)
        case .object(let value):
            try container.encode(value)
        case .array(let value):
            try container.encode(value)
        case .null:
            try container.encodeNil()
        }
    }
}

