import CoreLocation
import Foundation

// MARK: - 证件卡包与街区排行

enum PetCredentialPromptKind: String, Codable, Equatable, Sendable, CaseIterable {
    case identity
    case passport
    case healthRecord = "health_record"
    case driverLicense = "driver_license"
    case boardingPass = "boarding_pass"
    case hotelKey = "hotel_key"
}

struct PetCredentialPrompt: Codable, Identifiable, Equatable, Sendable {
    var kind: PetCredentialPromptKind
    var title: String
    var subtitle: String
    var serial: String
    var imagePrompt: String
    var size: String
    var referenceRoles: [String]
    var safetyNotes: [String]
    var fields: [String: String]

    var id: String { serial }

    enum CodingKeys: String, CodingKey {
        case kind
        case title
        case subtitle
        case serial
        case imagePrompt = "image_prompt"
        case size
        case referenceRoles = "reference_roles"
        case safetyNotes = "safety_notes"
        case fields
    }
}

struct StreetRankItem: Codable, Identifiable, Equatable, Sendable {
    var rank: Int
    var place: PlaceSignal
    var rankScore: Double
    var reason: String
    var petAction: String
    var ownerTip: String
    var weatherNote: String

    var id: String { "\(rank)-\(place.id)" }

    enum CodingKeys: String, CodingKey {
        case rank
        case place
        case rankScore = "rank_score"
        case reason
        case petAction = "pet_action"
        case ownerTip = "owner_tip"
        case weatherNote = "weather_note"
    }
}

struct StreetRankResponse: Codable, Equatable, Sendable {
    var petID: String
    var city: String
    var theme: String
    var generatedAt: Date
    var provider: String
    var weather: String
    var items: [StreetRankItem]
    var sourceNotes: [String]

    enum CodingKeys: String, CodingKey {
        case petID = "pet_id"
        case city
        case theme
        case generatedAt = "generated_at"
        case provider
        case weather
        case items
        case sourceNotes = "source_notes"
    }
}

