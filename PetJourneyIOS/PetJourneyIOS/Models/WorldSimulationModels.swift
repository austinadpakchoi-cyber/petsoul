import CoreLocation
import Foundation

struct WorldTimelineItem: Codable, Identifiable, Equatable, Sendable {
    var id: String
    var kind: String
    var title: String
    var detail: String
    var city: String
    var placeName: String?
    var latitude: Double?
    var longitude: Double?
    var mode: TravelMode?
    var plannedStart: Date?
    var plannedEnd: Date?
    var progress: Double
    var isCurrent: Bool

    var coordinate: CLLocationCoordinate2D? {
        guard let latitude, let longitude else { return nil }
        return CLLocationCoordinate2D(latitude: latitude, longitude: longitude)
    }

    enum CodingKeys: String, CodingKey {
        case id
        case kind
        case title
        case detail
        case city
        case placeName = "place_name"
        case latitude = "lat"
        case longitude = "lng"
        case mode
        case plannedStart = "planned_start"
        case plannedEnd = "planned_end"
        case progress
        case isCurrent = "is_current"
    }
}

struct WorldActivity: Codable, Identifiable, Equatable, Sendable {
    var id: String
    var kind: String
    var status: JourneyStatus
    var title: String
    var detail: String
    var city: String
    var placeName: String?
    var latitude: Double
    var longitude: Double
    var mode: TravelMode?
    var startedAt: Date?
    var endsAt: Date?
    var progress: Double
    var dwellMinutes: Int?
    var nextPlaceName: String?
    var iconHint: String
    var canGeneratePhoto: Bool
    var canSendPostcard: Bool
    var source: String
    var currentTransportID: String?

    var coordinate: CLLocationCoordinate2D {
        CLLocationCoordinate2D(latitude: latitude, longitude: longitude)
    }

    enum CodingKeys: String, CodingKey {
        case id
        case kind
        case status
        case title
        case detail
        case city
        case placeName = "place_name"
        case latitude = "lat"
        case longitude = "lng"
        case mode
        case startedAt = "started_at"
        case endsAt = "ends_at"
        case progress
        case dwellMinutes = "dwell_minutes"
        case nextPlaceName = "next_place_name"
        case iconHint = "icon_hint"
        case canGeneratePhoto = "can_generate_photo"
        case canSendPostcard = "can_send_postcard"
        case source
        case currentTransportID = "current_transport_id"
    }
}

struct PetNeedState: Codable, Equatable, Sendable {
    var energy: Int?
    var hunger: Int?
    var thirst: Int?
    var sleepiness: Int?
    var sensoryLoad: Int?
    var heatStress: Int?
    var social: Int?
    var curiosity: Int?
    var comfort: Int?
    var playfulness: Int?
    var primaryNeed: String?

    enum CodingKeys: String, CodingKey {
        case energy
        case hunger
        case thirst
        case sleepiness
        case sensoryLoad = "sensory_load"
        case heatStress = "heat_stress"
        case social
        case curiosity
        case comfort
        case playfulness
        case primaryNeed = "primary_need"
    }
}

struct LifeWorldAction: Codable, Equatable, Sendable {
    var actionType: String?
    var title: String?
    var detail: String?
    var mode: TravelMode?
    var placeName: String?
    var lat: Double?
    var lng: Double?
    var durationMinutes: Int?
    var animationHint: String?
    var photoOpportunity: Bool?
    var messageOpportunity: Bool?

    enum CodingKeys: String, CodingKey {
        case actionType = "action_type"
        case title
        case detail
        case mode
        case placeName = "place_name"
        case lat
        case lng
        case durationMinutes = "duration_minutes"
        case animationHint = "animation_hint"
        case photoOpportunity = "photo_opportunity"
        case messageOpportunity = "message_opportunity"
    }
}

struct LifePetIntent: Codable, Equatable, Sendable {
    var kind: String?
    var title: String?
    var reason: String?
    var confidence: Double?
}

struct LifeGameMasterDecision: Codable, Equatable, Sendable {
    var allowed: Bool?
    var reason: String?
    var adjusted: Bool?
    var blockedReasons: [String]?

    enum CodingKeys: String, CodingKey {
        case allowed
        case reason
        case adjusted
        case blockedReasons = "blocked_reasons"
    }
}

struct LifeVisibleThought: Codable, Equatable, Sendable {
    var currentInnerVoice: String
    var nextIntention: String
    var reason: String
    var timeWindow: String
    var confidence: Double
    var ownerMessageEcho: String?

    enum CodingKeys: String, CodingKey {
        case currentInnerVoice = "current_inner_voice"
        case nextIntention = "next_intention"
        case reason
        case timeWindow = "time_window"
        case confidence
        case ownerMessageEcho = "owner_message_echo"
    }
}

struct WorldObservation: Codable, Equatable, Sendable {
    var petID: String
    var city: String
    var weather: String
    var localTime: Date
    var currentActivity: WorldActivity
    var nearbyPlaces: [PlaceSignal]
    var activeTransport: ScheduledTransportLeg?
    var constraints: [String]

    enum CodingKeys: String, CodingKey {
        case petID = "pet_id"
        case city
        case weather
        case localTime = "local_time"
        case currentActivity = "current_activity"
        case nearbyPlaces = "nearby_places"
        case activeTransport = "active_transport"
        case constraints
    }
}

struct LifeTickResult: Codable, Equatable, Sendable {
    var petID: String
    var generatedAt: Date
    var provider: String
    var observation: WorldObservation?
    var retrievedMemories: [MemoryRecord]?
    var needState: PetNeedState?
    var intent: LifePetIntent?
    var action: LifeWorldAction?
    var decision: LifeGameMasterDecision?
    var ownerVisibleSummary: String
    var visibleThought: LifeVisibleThought?
    var animalTextHint: String
    var animationHint: String
    var shouldNotifyOwner: Bool
    var nextTickAfterSeconds: Int

    enum CodingKeys: String, CodingKey {
        case petID = "pet_id"
        case generatedAt = "generated_at"
        case provider
        case observation
        case retrievedMemories = "retrieved_memories"
        case needState = "need_state"
        case intent
        case action
        case decision
        case ownerVisibleSummary = "owner_visible_summary"
        case visibleThought = "visible_thought"
        case animalTextHint = "animal_text_hint"
        case animationHint = "animation_hint"
        case shouldNotifyOwner = "should_notify_owner"
        case nextTickAfterSeconds = "next_tick_after_seconds"
    }
}

struct WorldSimulationSnapshot: Codable, Equatable, Sendable {
    var petID: String
    var city: String
    var generatedAt: Date
    var provider: String
    var elapsedSeconds: Int
    var travelDay: Int
    var weather: String
    var status: JourneyStatus
    var statusNote: String
    var energy: Int
    var happiness: Int
    var curiosity: Int
    var currentActivity: WorldActivity
    var activeTransport: ScheduledTransportLeg?
    var nextStop: ItineraryStop?
    var timeline: [WorldTimelineItem]
    var rules: [String]
    var lifeTick: LifeTickResult?

    enum CodingKeys: String, CodingKey {
        case petID = "pet_id"
        case city
        case generatedAt = "generated_at"
        case provider
        case elapsedSeconds = "elapsed_seconds"
        case travelDay = "travel_day"
        case weather
        case status
        case statusNote = "status_note"
        case energy
        case happiness
        case curiosity
        case currentActivity = "current_activity"
        case activeTransport = "active_transport"
        case nextStop = "next_stop"
        case timeline
        case rules
        case lifeTick = "life_tick"
    }
}

