import CoreLocation
import Foundation

// MARK: - 证件卡包与街区排行

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

