import CoreLocation
import Foundation

enum TravelQuestStatus: String, Codable, Equatable, Sendable {
    case suggested
    case thinking
    case guideReady = "guide_ready"
    case preparing
    case outbound
    case traveling
    case arrived
    case onsiteExploring = "onsite_exploring"
    case watchingEvent = "watching_event"
    case postEventRest = "post_event_rest"
    case returnPlanning = "return_planning"
    case returnTraveling = "return_traveling"
    case returned
    case continuedElsewhere = "continued_elsewhere"
    case declined
    case completed

    var displayName: String {
        switch self {
        case .suggested, .thinking: "正在想"
        case .guideReady: "攻略好了"
        case .preparing: "准备出发"
        case .outbound, .traveling: "在路上"
        case .arrived: "已抵达"
        case .onsiteExploring: "慢慢逛"
        case .watchingEvent: "看比赛"
        case .postEventRest: "赛后休息"
        case .returnPlanning: "整理下一步"
        case .returnTraveling: "回程中"
        case .returned: "已回来"
        case .continuedElsewhere: "继续旅行"
        case .declined: "先不去了"
        case .completed: "已完成"
        }
    }
}

enum TravelQuestType: String, Codable, Equatable, Sendable {
    case openDestination = "open_destination"
    case worldcup
    case cityTrip = "city_trip"

    var displayName: String {
        switch self {
        case .worldcup: "世界杯彩蛋"
        case .cityTrip: "城市旅行"
        case .openDestination: "旅行愿望"
        }
    }
}

enum TravelQuestTripType: String, Codable, Equatable, Sendable {
    case roundTrip = "round_trip"
    case oneWay = "one_way"
    case multiCity = "multi_city"
    case openEnded = "open_ended"
}

enum TravelQuestReturnPolicy: String, Codable, Equatable, Sendable {
    case returnToOrigin = "return_to_origin"
    case continueJourney = "continue_journey"
    case askAfterEvent = "ask_after_event"
}

enum TravelGuideResearchProvider: String, Codable, Equatable, Sendable {
    case mock
    case doubaoSocial = "doubao_social"
    case openAIWebSearch = "openai_web_search"
    case hybrid
}

struct TravelAnchor: Codable, Equatable, Sendable {
    var city: String
    var placeName: String
    var latitude: Double
    var longitude: Double
    var note: String

    enum CodingKeys: String, CodingKey {
        case city
        case placeName = "place_name"
        case latitude = "lat"
        case longitude = "lng"
        case note
    }
}

struct TravelWishRequest: Codable, Equatable, Sendable {
    var message: String
    var destination: String?
    var eventName: String?
    var preferredStartDate: String?
    var force: Bool = false

    enum CodingKeys: String, CodingKey {
        case message
        case destination
        case eventName = "event_name"
        case preferredStartDate = "preferred_start_date"
        case force
    }
}

struct TravelQuestStop: Codable, Identifiable, Equatable, Sendable {
    var id: String
    var city: String
    var name: String
    var role: String
    var plannedTime: String?
    var dwellMinutes: Int
    var petVoice: String
    var ownerTip: String
    var sourceNotes: [String]

    enum CodingKeys: String, CodingKey {
        case id
        case city
        case name
        case role
        case plannedTime = "planned_time"
        case dwellMinutes = "dwell_minutes"
        case petVoice = "pet_voice"
        case ownerTip = "owner_tip"
        case sourceNotes = "source_notes"
    }
}

struct TravelQuestTransportOutline: Codable, Identifiable, Equatable, Sendable {
    var id: String { "\(mode.rawValue)-\(fromPlace)-\(toPlace)-\(estimatedDuration)" }

    var mode: TravelMode
    var fromPlace: String
    var toPlace: String
    var estimatedDuration: String
    var realityLevel: String
    var note: String

    enum CodingKeys: String, CodingKey {
        case mode
        case fromPlace = "from_place"
        case toPlace = "to_place"
        case estimatedDuration = "estimated_duration"
        case realityLevel = "reality_level"
        case note
    }
}

struct SocialTravelFinding: Codable, Equatable, Sendable {
    var claim: String
    var evidenceType: String?
    var mentionedPlaces: [String]?
    var sentiment: String?
    var usefulness: Double?
    var risk: String?
    var suggestedTime: String?
    var tags: [String]?
    var evidenceLevel: String?
    var sourceType: String?
    var recency: String?
    var confidence: Double?
    var shouldVerifyWithMap: Bool?

    enum CodingKeys: String, CodingKey {
        case claim
        case evidenceType = "evidence_type"
        case mentionedPlaces = "mentioned_places"
        case sentiment
        case usefulness
        case risk
        case suggestedTime = "suggested_time"
        case tags
        case evidenceLevel = "evidence_level"
        case sourceType = "source_type"
        case recency
        case confidence
        case shouldVerifyWithMap = "should_verify_with_map"
    }
}

struct PlaceEvidenceScores: Codable, Equatable, Sendable {
    var citySignature: Double?
    var localFoodValue: Double?
    var photoPotential: Double?
    var petFit: Double?
    var crowdPenalty: Double?
    var chainStorePenalty: Double?
    var overhypedPenalty: Double?
    var confidence: Double?

    enum CodingKeys: String, CodingKey {
        case citySignature = "city_signature"
        case localFoodValue = "local_food_value"
        case photoPotential = "photo_potential"
        case petFit = "pet_fit"
        case crowdPenalty = "crowd_penalty"
        case chainStorePenalty = "chain_store_penalty"
        case overhypedPenalty = "overhyped_penalty"
        case confidence
    }
}

struct PlaceEvidencePacket: Codable, Equatable, Sendable {
    var canonicalPlaceId: String
    var name: String
    var city: String
    var lat: Double?
    var lng: Double?
    var coordinateSource: String?
    var sourcePriority: [String]?
    var derivedScores: PlaceEvidenceScores?
    var eligibleRoles: [String]?
    var userVisible: Bool?
    var needsVerification: Bool?
    var verificationStatus: String?
    var evidenceNotes: [String]?

    enum CodingKeys: String, CodingKey {
        case canonicalPlaceId = "canonical_place_id"
        case name
        case city
        case lat
        case lng
        case coordinateSource = "coordinate_source"
        case sourcePriority = "source_priority"
        case derivedScores = "derived_scores"
        case eligibleRoles = "eligible_roles"
        case userVisible = "user_visible"
        case needsVerification = "needs_verification"
        case verificationStatus = "verification_status"
        case evidenceNotes = "evidence_notes"
    }
}

struct TravelGuideResearch: Codable, Equatable, Sendable {
    var provider: TravelGuideResearchProvider
    var providerName: String
    var destinationRegion: String
    var query: String
    var strategy: String
    var findings: [String]
    var researchBrief: [String: JSONValue]? = nil
    var socialFindings: [SocialTravelFinding]? = nil
    var evidencePackets: [PlaceEvidencePacket]? = nil
    var factProviderPriority: [String]? = nil
    var qualityGateNotes: [String]? = nil
    var orchestrationRoles: [String]? = nil
    var pipelineSteps: [String]? = nil
    var qualityGateRules: [String]? = nil
    var voiceWriter: String? = nil
    var deepCritic: String? = nil
    var deepCriticRequired: Bool? = nil
    var canInformReplicableRoute: Bool? = nil
    var recommendedSources: [String]
    var missingCapabilities: [String]
    var generatedAt: Date

    enum CodingKeys: String, CodingKey {
        case provider
        case providerName = "provider_name"
        case destinationRegion = "destination_region"
        case query
        case strategy
        case findings
        case researchBrief = "research_brief"
        case socialFindings = "social_findings"
        case evidencePackets = "evidence_packets"
        case factProviderPriority = "fact_provider_priority"
        case qualityGateNotes = "quality_gate_notes"
        case orchestrationRoles = "orchestration_roles"
        case pipelineSteps = "pipeline_steps"
        case qualityGateRules = "quality_gate_rules"
        case voiceWriter = "voice_writer"
        case deepCritic = "deep_critic"
        case deepCriticRequired = "deep_critic_required"
        case canInformReplicableRoute = "can_inform_replicable_route"
        case recommendedSources = "recommended_sources"
        case missingCapabilities = "missing_capabilities"
        case generatedAt = "generated_at"
    }
}

struct TravelQuestGuide: Codable, Identifiable, Equatable, Sendable {
    var id: String
    var title: String
    var summary: String
    var petVoice: String
    var routeTheme: String
    var cities: [String]
    var stops: [TravelQuestStop]
    var transportOutline: [TravelQuestTransportOutline]
    var preparationNotes: [String]
    var sourceNotes: [String]
    var research: TravelGuideResearch?
    var generatedAt: Date
    var provider: String

    enum CodingKeys: String, CodingKey {
        case id
        case title
        case summary
        case petVoice = "pet_voice"
        case routeTheme = "route_theme"
        case cities
        case stops
        case transportOutline = "transport_outline"
        case preparationNotes = "preparation_notes"
        case sourceNotes = "source_notes"
        case research
        case generatedAt = "generated_at"
        case provider
    }
}

struct TravelQuestNextOption: Codable, Identifiable, Equatable, Sendable {
    var id: String
    var title: String
    var decisionType: String
    var destination: String
    var petVoice: String
    var ownerVisibleReason: String
    var transportOutline: [TravelQuestTransportOutline]
    var recommended: Bool

    enum CodingKeys: String, CodingKey {
        case id
        case title
        case decisionType = "decision_type"
        case destination
        case petVoice = "pet_voice"
        case ownerVisibleReason = "owner_visible_reason"
        case transportOutline = "transport_outline"
        case recommended
    }
}

struct TravelQuestDecisionRequest: Codable, Equatable, Sendable {
    var optionID: String?
    var ownerMessage: String?

    enum CodingKeys: String, CodingKey {
        case optionID = "option_id"
        case ownerMessage = "owner_message"
    }
}

