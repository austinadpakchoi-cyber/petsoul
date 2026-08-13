import CoreLocation
import Foundation

struct PetGuideStop: Codable, Identifiable, Equatable, Sendable {
    var id: String
    var placeID: String
    var name: String
    var category: String
    var role: String? = nil
    var isCore: Bool? = nil
    var isUserVisible: Bool? = nil
    var city: String
    var latitude: Double
    var longitude: Double
    var plannedTime: String?
    var dwellMinutes: Int
    var petReason: String
    var ownerTip: String
    var rating: Double?
    var photoURL: URL?
    var distanceMeters: Int?
    var guideScore: Double?
    var source: String

    enum CodingKeys: String, CodingKey {
        case id
        case placeID = "place_id"
        case name
        case category
        case role
        case isCore = "is_core"
        case isUserVisible = "is_user_visible"
        case city
        case latitude = "lat"
        case longitude = "lng"
        case plannedTime = "planned_time"
        case dwellMinutes = "dwell_minutes"
        case petReason = "pet_reason"
        case ownerTip = "owner_tip"
        case rating
        case photoURL = "photo_url"
        case distanceMeters = "distance_meters"
        case guideScore = "guide_score"
        case source
    }
}

struct PetAuthoredGuide: Codable, Equatable, Sendable {
    var petID: String
    var city: String
    var generatedAt: Date
    var provider: String
    var model: String
    var title: String
    var animalText: String
    var translation: String
    var languageStyle: String
    var routeTheme: String
    var mood: String
    var guideStops: [PetGuideStop]
    var scheduledTransport: [ScheduledTransportLeg]
    var sourcePlacesCount: Int
    var autonomyNote: String
    var qualityScore: Double? = nil
    var isReplicableRoute: Bool? = nil
    var qualityNotes: [String]? = nil
    var orchestrationRoles: [String]? = nil
    var qualityGateRules: [String]? = nil
    var voiceProvider: String? = nil
    var criticProvider: String? = nil
    var factProviderPriority: [String]? = nil

    enum CodingKeys: String, CodingKey {
        case petID = "pet_id"
        case city
        case generatedAt = "generated_at"
        case provider
        case model
        case title
        case animalText = "animal_text"
        case translation
        case languageStyle = "language_style"
        case routeTheme = "route_theme"
        case mood
        case guideStops = "guide_stops"
        case scheduledTransport = "scheduled_transport"
        case sourcePlacesCount = "source_places_count"
        case autonomyNote = "autonomy_note"
        case qualityScore = "quality_score"
        case isReplicableRoute = "is_replicable_route"
        case qualityNotes = "quality_notes"
        case orchestrationRoles = "orchestration_roles"
        case qualityGateRules = "quality_gate_rules"
        case voiceProvider = "voice_provider"
        case criticProvider = "critic_provider"
        case factProviderPriority = "fact_provider_priority"
    }
}

enum IllustratedGuideStatus: String, Codable, Equatable, Sendable {
    case promptReady = "prompt_ready"
    case generating
    case ready
    case failed
}

struct IllustratedGuideStop: Codable, Identifiable, Equatable, Sendable {
    var index: Int
    var time: String?
    var name: String
    var label: String
    var shortNote: String
    var category: String

    var id: Int { index }

    enum CodingKeys: String, CodingKey {
        case index
        case time
        case name
        case label
        case shortNote = "short_note"
        case category
    }
}

struct IllustratedGuidePage: Codable, Identifiable, Equatable, Sendable {
    var index: Int
    var title: String
    var subtitle: String
    var intent: String
    var pageType: String?
    var templateID: String?
    var visualStyle: String?
    var composition: String?
    var styleID: String?
    var styleName: String?
    var imagePrompt: String
    var imageURL: URL?
    var thumbnailURL: URL?
    var status: IllustratedGuideStatus

    var id: Int { index }

    init(
        index: Int,
        title: String,
        subtitle: String,
        intent: String,
        pageType: String? = nil,
        templateID: String? = nil,
        visualStyle: String? = nil,
        composition: String? = nil,
        styleID: String? = nil,
        styleName: String? = nil,
        imagePrompt: String,
        imageURL: URL?,
        thumbnailURL: URL?,
        status: IllustratedGuideStatus
    ) {
        self.index = index
        self.title = title
        self.subtitle = subtitle
        self.intent = intent
        self.pageType = pageType
        self.templateID = templateID
        self.visualStyle = visualStyle
        self.composition = composition
        self.styleID = styleID
        self.styleName = styleName
        self.imagePrompt = imagePrompt
        self.imageURL = imageURL
        self.thumbnailURL = thumbnailURL
        self.status = status
    }

    enum CodingKeys: String, CodingKey {
        case index
        case title
        case subtitle
        case intent
        case pageType = "page_type"
        case templateID = "template_id"
        case visualStyle = "visual_style"
        case composition
        case styleID = "style_id"
        case styleName = "style_name"
        case imagePrompt = "image_prompt"
        case imageURL = "image_url"
        case thumbnailURL = "thumbnail_url"
        case status
    }
}

struct IllustratedGuide: Codable, Identifiable, Equatable, Sendable {
    var id: String
    var petID: String
    var city: String
    var date: String
    var status: IllustratedGuideStatus
    var title: String
    var theme: String
    var petName: String
    var petThought: String
    var stops: [IllustratedGuideStop]
    var style: String
    var styleID: String?
    var styleName: String?
    var stylePackVersion: String?
    var styleLocked: Bool?
    var layoutMode: String?
    var pages: [IllustratedGuidePage]?
    var sourceItineraryID: String
    var imagePrompt: String
    var imageURL: URL?
    var thumbnailURL: URL?
    var provider: String
    var model: String?
    var errorMessage: String?
    var createdAt: Date

    enum CodingKeys: String, CodingKey {
        case id
        case petID = "pet_id"
        case city
        case date
        case status
        case title
        case theme
        case petName = "pet_name"
        case petThought = "pet_thought"
        case stops
        case style
        case styleID = "style_id"
        case styleName = "style_name"
        case stylePackVersion = "style_pack_version"
        case styleLocked = "style_locked"
        case layoutMode = "layout_mode"
        case pages
        case sourceItineraryID = "source_itinerary_id"
        case imagePrompt = "image_prompt"
        case imageURL = "image_url"
        case thumbnailURL = "thumbnail_url"
        case provider
        case model
        case errorMessage = "error_message"
        case createdAt = "created_at"
    }
}

