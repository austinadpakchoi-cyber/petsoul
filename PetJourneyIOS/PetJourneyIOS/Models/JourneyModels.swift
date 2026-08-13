import CoreLocation
import Foundation

struct JourneyThought: Codable, Identifiable, Equatable, Sendable {
    var id: String
    var text: String
    var timestamp: Date
    var tone: String
    var animalText: String?
    var translationAvailable: Bool = false
    var translation: String?
    var languageStyle: String = "human"
    var model: String?

    enum CodingKeys: String, CodingKey {
        case id
        case text
        case timestamp
        case tone
        case animalText = "animal_text"
        case translationAvailable = "translation_available"
        case translation
        case languageStyle = "language_style"
        case model
    }
}

struct ThoughtTranslation: Codable, Equatable, Sendable {
    var thoughtID: String
    var petID: String
    var animalText: String
    var translation: String
    var tone: String
    var languageStyle: String
    var model: String?

    enum CodingKeys: String, CodingKey {
        case thoughtID = "thought_id"
        case petID = "pet_id"
        case animalText = "animal_text"
        case translation
        case tone
        case languageStyle = "language_style"
        case model
    }
}

struct DayPlan: Codable, Identifiable, Equatable, Sendable {
    var id: String
    var location: String
    var viewMode: String
    var stayDuration: String
    var items: [DayPlanItem]
    var scheduledTransport: [ScheduledTransportLeg] = []
    var thoughts: [JourneyThought]
    var eventsToday: [JourneyEvent]

    enum CodingKeys: String, CodingKey {
        case id
        case location
        case viewMode = "view_mode"
        case stayDuration = "stay_duration"
        case items = "day_plan"
        case scheduledTransport = "scheduled_transport"
        case thoughts
        case eventsToday = "events_today"
    }
}

struct DayPlanItem: Codable, Identifiable, Equatable, Sendable {
    enum Kind: String, Codable, Sendable {
        case morning
        case noon
        case afternoon
        case evening
    }

    var id: String
    var time: String
    var title: String
    var detail: String
    var kind: Kind
}

struct JourneyEvent: Codable, Identifiable, Equatable, Sendable {
    var id: String
    var title: String
    var detail: String
    var timestamp: Date
}

struct Postcard: Codable, Identifiable, Equatable, Sendable {
    var id: String
    var location: String
    var text: String
    var weather: String
    var happiness: Int
    var timestamp: Date
    var imageURL: URL?
    var isNew: Bool

    enum CodingKeys: String, CodingKey {
        case id
        case location
        case text
        case weather
        case happiness
        case timestamp
        case imageURL = "image_url"
        case isNew = "is_new"
    }
}

struct CityPosition: Codable, Equatable, Sendable {
    var city: String
    var latitude: Double
    var longitude: Double

    var coordinate: CLLocationCoordinate2D {
        CLLocationCoordinate2D(latitude: latitude, longitude: longitude)
    }

    enum CodingKeys: String, CodingKey {
        case city
        case latitude = "lat"
        case longitude = "lng"
    }

    static let xiamen = CityPosition(city: "厦门", latitude: 24.4798, longitude: 118.0894)
}

struct FeedbackRequest: Codable, Equatable, Sendable {
    var petID: String
    var city: String
    var liked: Bool

    enum CodingKeys: String, CodingKey {
        case petID = "pet_id"
        case city
        case liked
    }
}

struct FeedbackResponse: Codable, Equatable, Sendable {
    var success: Bool
    var message: String
    var updatedStatus: AgentStatus?

    enum CodingKeys: String, CodingKey {
        case success
        case message
        case updatedStatus = "updated_status"
    }
}

struct OwnerMessageRequest: Codable, Equatable, Sendable {
    var message: String
    var intentHint: String?

    enum CodingKeys: String, CodingKey {
        case message
        case intentHint = "intent_hint"
    }
}

struct OwnerIntentResult: Codable, Equatable, Sendable {
    var intent: String
    var strength: Double
    var entities: [String: JSONValue]?
    var shouldAffectRoute: Bool?
    var shouldWriteMemory: Bool?
    var responsePolicy: String?
    var decision: String?
    var safetyNotes: [String]?

    enum CodingKeys: String, CodingKey {
        case intent
        case strength
        case entities
        case shouldAffectRoute = "should_affect_route"
        case shouldWriteMemory = "should_write_memory"
        case responsePolicy = "response_policy"
        case decision
        case safetyNotes = "safety_notes"
    }
}

struct OwnerMessageResponse: Codable, Equatable, Sendable {
    var success: Bool
    var decision: String
    var message: String
    var thought: JourneyThought
    var updatedStatus: AgentStatus?
    var ownerIntent: OwnerIntentResult?

    enum CodingKeys: String, CodingKey {
        case success
        case decision
        case message
        case thought
        case updatedStatus = "updated_status"
        case ownerIntent = "owner_intent"
    }
}

