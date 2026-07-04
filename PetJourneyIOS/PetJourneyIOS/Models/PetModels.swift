import CoreLocation
import Foundation

enum PetType: String, Codable, CaseIterable, Identifiable, Sendable {
    case dog
    case cat
    case parrot
    case rabbit
    case hamster
    case bird
    case other

    var id: String { rawValue }

    var displayName: String {
        switch self {
        case .dog: "狗狗"
        case .cat: "猫咪"
        case .parrot: "鹦鹉"
        case .rabbit: "兔兔"
        case .hamster: "仓鼠"
        case .bird: "小鸟"
        case .other: "小动物"
        }
    }

    var searchWorldName: String {
        switch self {
        case .dog: "汪汪星"
        case .cat: "喵喵星"
        case .parrot: "鹦羽星"
        case .rabbit: "月兔星"
        case .hamster: "软爪星"
        case .bird: "啾啾星"
        case .other: "小动物星"
        }
    }

    var symbolName: String {
        switch self {
        case .dog: "pawprint.fill"
        case .cat: "cat.fill"
        case .parrot: "bird.fill"
        case .rabbit: "hare.fill"
        case .hamster: "circle.fill"
        case .bird: "bird.fill"
        case .other: "pawprint.fill"
        }
    }

    var languageStyle: String {
        switch self {
        case .dog: "dog_vocalization_with_hidden_translation"
        case .cat: "cat_vocalization_with_hidden_translation"
        case .parrot: "parrot_chirp_with_hidden_translation"
        case .rabbit: "rabbit_soft_signal_with_hidden_translation"
        case .hamster: "hamster_soft_signal_with_hidden_translation"
        case .bird: "bird_chirp_with_hidden_translation"
        case .other: "companion_animal_signal_with_hidden_translation"
        }
    }

    func vocalization(for tone: String) -> String {
        switch self {
        case .dog:
            switch tone {
            case "connecting": "汪...呜汪。汪汪。"
            case "connected": "汪呜！汪汪，呜。"
            case "selfie": "汪呜汪，汪汪！呜汪。"
            case "guide_saved": "汪汪。呜汪，汪呜汪。"
            case "guide_skipped": "呜。汪呜汪，汪。"
            default: "汪呜...汪汪。呜。"
            }
        case .cat:
            switch tone {
            case "connecting": "喵...喵呜。喵喵。"
            case "connected": "喵呜！喵喵，喵。"
            case "selfie": "喵呜喵，喵喵！呼噜。"
            case "guide_saved": "喵喵。喵呜，呼噜呼噜。"
            case "guide_skipped": "喵。喵呜喵，喵。"
            default: "喵呜...喵喵。喵。"
            }
        case .parrot:
            switch tone {
            case "connected": "啾！你好呀，啾啾。"
            case "selfie": "咔哒，啾啾！咕。"
            case "guide_saved": "啾啾。好地方，啾。"
            case "guide_skipped": "咕。先飞过，啾。"
            default: "啾啾...咕咕。啾。"
            }
        case .rabbit:
            switch tone {
            case "connected": "嗅嗅。耳朵动了一下。"
            case "selfie": "嗒嗒，嗅嗅。轻轻靠近。"
            case "guide_saved": "嗅嗅。爪爪轻轻点了点。"
            case "guide_skipped": "嗒。耳朵慢慢转过去。"
            default: "嗅嗅...轻轻蹭。嗒。"
            }
        case .hamster:
            switch tone {
            case "connected": "吱吱！小爪子动了动。"
            case "selfie": "吱，咔哒。嗅嗅。"
            case "guide_saved": "吱吱。抱住一颗小光点。"
            case "guide_skipped": "吱。先藏进软软的地方。"
            default: "吱吱...嗅嗅。吱。"
            }
        case .bird:
            switch tone {
            case "selfie": "啾啾，咔哒！"
            case "guide_saved": "啾啾。咕咕。"
            case "guide_skipped": "咕。啾。"
            default: "啾啾...咕。啾。"
            }
        case .other:
            switch tone {
            case "connected": "小小的信号亮了一下。"
            case "selfie": "咔哒。TA 轻轻动了一下。"
            case "guide_saved": "信号闪了闪，像是记住了。"
            case "guide_skipped": "信号慢慢变轻，TA 先按自己的节奏走。"
            default: "小小的信号，轻轻亮了一下。"
            }
        }
    }
}

enum JourneyStatus: String, Codable, CaseIterable, Identifiable, Sendable {
    case traveling
    case flying
    case resting
    case staying
    case walking

    var id: String { rawValue }

    var displayName: String {
        switch self {
        case .traveling: "旅行中"
        case .flying: "交通中"
        case .resting: "休息中"
        case .staying: "停留中"
        case .walking: "散步中"
        }
    }
}

struct PetDNA: Codable, Equatable, Sendable {
    var ownerTitle: String
    var personality: String
    var favoritePlaces: [String]
    var hobbies: [String]
    var catchphrase: String
    var emojiPreference: String
    var voiceStyle: String

    enum CodingKeys: String, CodingKey {
        case ownerTitle = "owner_title"
        case personality
        case favoritePlaces = "favorite_places"
        case hobbies = "hobby"
        case catchphrase
        case emojiPreference = "emoji_pref"
        case voiceStyle = "voice_style"
    }

    static let fallback = PetDNA(
        ownerTitle: "妈妈",
        personality: "温柔",
        favoritePlaces: ["海边", "草地"],
        hobbies: ["散步", "晒太阳"],
        catchphrase: "我在路上，也在想你",
        emojiPreference: "soft",
        voiceStyle: "轻轻的、像寄信"
    )
}

struct CreatePetRequest: Equatable, Sendable {
    var name: String
    var petType: PetType
    var photoData: Data?
    var photoFilename: String?
    var dna: PetDNA
}

struct CreatePetResponse: Codable, Equatable, Sendable {
    var success: Bool
    var petID: String
    var name: String
    var location: String
    var photoURL: URL?
    var message: String

    enum CodingKeys: String, CodingKey {
        case success
        case petID = "pet_id"
        case name
        case location
        case photoURL = "photo_url"
        case message
    }
}

struct PetProfile: Codable, Identifiable, Equatable, Sendable {
    var id: String { petID }

    var petID: String
    var name: String
    var petType: PetType
    var dna: PetDNA
    var photoURL: URL?

    enum CodingKeys: String, CodingKey {
        case petID = "pet_id"
        case name
        case petType = "pet_type"
        case dna
        case photoURL = "photo_url"
    }
}

struct AgentStatus: Codable, Equatable, Sendable {
    var petID: String
    var name: String
    var petType: PetType?
    var status: JourneyStatus
    var agentState: AgentState
    var dailyLogs: [String]
    var reflections: [String]
    var flightNumber: String?
    var canMessage: Bool
    var farewellReady: Bool
    var postcards: [Postcard]

    enum CodingKeys: String, CodingKey {
        case petID = "pet_id"
        case name
        case petType = "pet_type"
        case status
        case agentState = "agent_state"
        case dailyLogs = "daily_logs"
        case reflections
        case flightNumber = "flight_number"
        case canMessage = "can_message"
        case farewellReady = "farewell_ready"
        case postcards
    }
}

struct AgentState: Codable, Equatable, Sendable {
    var location: String
    var travelDay: Int
    var weather: String
    var status: JourneyStatus
    var statusNote: String
    var energy: Int
    var happiness: Int
    var curiosity: Int
    var latestThought: JourneyThought?
    var thoughts: [JourneyThought]

    enum CodingKeys: String, CodingKey {
        case location
        case travelDay = "travel_day"
        case weather
        case status
        case statusNote = "status_note"
        case energy
        case happiness
        case curiosity
        case latestThought = "latest_thought"
        case thoughts
    }
}

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

struct OwnerMessageResponse: Codable, Equatable, Sendable {
    var success: Bool
    var decision: String
    var message: String
    var thought: JourneyThought
    var updatedStatus: AgentStatus?

    enum CodingKeys: String, CodingKey {
        case success
        case decision
        case message
        case thought
        case updatedStatus = "updated_status"
    }
}

enum CommunicatorIntent: String, Codable, Equatable, Sendable {
    case emotionalDistress = "EMOTIONAL_DISTRESS"
    case farewellOrGriefSpike = "FAREWELL_OR_GRIEF_SPIKE"
    case currentStatusVisualRequest = "CURRENT_STATUS_VISUAL_REQUEST"
    case photoRequest = "PHOTO_REQUEST"
    case confirmPendingPhoto = "CONFIRM_PENDING_PHOTO"
    case ownerPhotoShare = "OWNER_PHOTO_SHARE"
    case postcardRequest = "POSTCARD_REQUEST"
    case locationCheck = "LOCATION_CHECK"
    case affectionIMissYou = "AFFECTION_I_MISS_YOU"
    case careCheck = "CARE_CHECK"
    case generalChat = "GENERAL_CHAT"
}

enum CommunicatorSender: String, Codable, Equatable, Sendable {
    case owner
    case pet
    case system
}

enum CommunicatorAttachmentType: String, Codable, Equatable, Sendable {
    case text
    case sticker
    case locationCard = "location_card"
    case photoStatusCard = "photo_status_card"
    case photoPlaceholder = "photo_placeholder"
    case photo
    case ownerPhoto = "owner_photo"
    case pendingPhotoRequest = "pending_photo_request"
    case postcardCandidate = "postcard_candidate"
}

enum MomentReaction: String, Codable, CaseIterable, Identifiable, Sendable {
    case like
    case paw
    case hug

    var id: String { rawValue }

    var displayName: String {
        switch self {
        case .like: "喜欢"
        case .paw: "摸摸"
        case .hug: "抱抱"
        }
    }

    var systemImage: String {
        switch self {
        case .like: "heart.fill"
        case .paw: "pawprint.fill"
        case .hug: "hands.sparkles.fill"
        }
    }
}

struct MomentSocialReactor: Codable, Identifiable, Equatable, Sendable {
    var id: String
    var name: String
    var species: String
    var avatarEmoji: String
    var reaction: MomentReaction
    var note: String?
    var createdAt: Date?

    enum CodingKeys: String, CodingKey {
        case id
        case name
        case species
        case avatarEmoji = "avatar_emoji"
        case reaction
        case note
        case createdAt = "created_at"
    }
}

struct CommunicatorLocation: Codable, Equatable, Sendable {
    var city: String
    var placeName: String?
    var latitude: Double?
    var longitude: Double?

    enum CodingKeys: String, CodingKey {
        case city
        case placeName = "place_name"
        case latitude = "lat"
        case longitude = "lng"
    }
}

struct CommunicatorReplyPolicy: Codable, Equatable, Sendable {
    var mode: String
    var estimatedReplySeconds: Int
    var visibleStatus: String
    var reasonCode: String
    var shouldBatch: Bool
    var shouldMarkSeen: Bool
    var cooldownApplied: Bool

    enum CodingKeys: String, CodingKey {
        case mode
        case estimatedReplySeconds = "estimated_reply_seconds"
        case visibleStatus = "visible_status"
        case reasonCode = "reason_code"
        case shouldBatch = "should_batch"
        case shouldMarkSeen = "should_mark_seen"
        case cooldownApplied = "cooldown_applied"
    }
}

struct CommunicatorAttachment: Codable, Identifiable, Equatable, Sendable {
    var id: String { "\(type.rawValue)-\(title)-\(photoMissionID ?? photoURL?.absoluteString ?? text)" }
    var type: CommunicatorAttachmentType
    var title: String
    var text: String
    var state: String
    var photoURL: URL?
    var location: CommunicatorLocation?
    var photoMissionID: String?
    var availableAfter: Date?

    enum CodingKeys: String, CodingKey {
        case type
        case title
        case text
        case state
        case photoURL = "photo_url"
        case location
        case photoMissionID = "photo_mission_id"
        case availableAfter = "available_after"
    }
}

struct CommunicatorMessage: Codable, Identifiable, Equatable, Sendable {
    var id: String
    var petID: String
    var sender: CommunicatorSender
    var text: String
    var intent: CommunicatorIntent?
    var messageState: String
    var replyPolicy: CommunicatorReplyPolicy?
    var attachments: [CommunicatorAttachment]
    var relatedMessageID: String?
    var createdAt: Date
    var updatedAt: Date?

    enum CodingKeys: String, CodingKey {
        case id
        case petID = "pet_id"
        case sender
        case text
        case intent
        case messageState = "message_state"
        case replyPolicy = "reply_policy"
        case attachments
        case relatedMessageID = "related_message_id"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
    }
}

struct CommunicatorSendRequest: Codable, Equatable, Sendable {
    var text: String
}

struct PendingPhotoRequest: Codable, Identifiable, Equatable, Sendable {
    var id: String
    var petID: String
    var sourceMessageID: String
    var intent: CommunicatorIntent
    var pendingType: String
    var status: String
    var reason: String
    var trigger: String
    var requestedScene: String
    var sceneHash: String
    var createdAt: Date
    var availableAfter: Date
    var expiresAt: Date
    var fulfilledMessageID: String?

    enum CodingKeys: String, CodingKey {
        case id
        case petID = "pet_id"
        case sourceMessageID = "source_message_id"
        case intent
        case pendingType = "pending_type"
        case status
        case reason
        case trigger
        case requestedScene = "requested_scene"
        case sceneHash = "scene_hash"
        case createdAt = "created_at"
        case availableAfter = "available_after"
        case expiresAt = "expires_at"
        case fulfilledMessageID = "fulfilled_message_id"
    }
}

struct CommunicatorSendResponse: Codable, Equatable, Sendable {
    var success: Bool
    var intent: CommunicatorIntent
    var replyPolicy: CommunicatorReplyPolicy
    var ownerMessage: CommunicatorMessage
    var messages: [CommunicatorMessage]
    var pendingRequest: PendingPhotoRequest?

    enum CodingKeys: String, CodingKey {
        case success
        case intent
        case replyPolicy = "reply_policy"
        case ownerMessage = "owner_message"
        case messages
        case pendingRequest = "pending_request"
    }
}

struct CommunicatorMoment: Codable, Identifiable, Equatable, Sendable {
    var id: String
    var petID: String
    var sourceType: String
    var sourceEventID: String?
    var text: String
    var location: CommunicatorLocation?
    var mood: String
    var attachments: [CommunicatorAttachment]
    var reactions: [String: Int]
    var ownerReaction: MomentReaction?
    var isRead: Bool
    var createdAt: Date
    var updatedAt: Date?
    var socialReactors: [MomentSocialReactor]?

    enum CodingKeys: String, CodingKey {
        case id
        case petID = "pet_id"
        case sourceType = "source_type"
        case sourceEventID = "source_event_id"
        case text
        case location
        case mood
        case attachments
        case reactions
        case ownerReaction = "owner_reaction"
        case isRead = "is_read"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
        case socialReactors = "social_reactors"
    }
}

struct MomentReactionRequest: Codable, Equatable, Sendable {
    var reaction: MomentReaction
}

struct MomentReactionResponse: Codable, Equatable, Sendable {
    var success: Bool
    var momentID: String
    var reaction: MomentReaction
    var message: String

    enum CodingKeys: String, CodingKey {
        case success
        case momentID = "moment_id"
        case reaction
        case message
    }
}

enum TravelMode: String, Codable, Equatable, Sendable {
    case stay
    case walk
    case drive
    case transit
    case train
    case flight
    case ferry
    case checkIn = "check_in"
}

extension TravelMode {
    var displayName: String {
        switch self {
        case .stay: "停留"
        case .walk: "步行"
        case .drive: "汽车"
        case .transit: "公共交通"
        case .train: "火车"
        case .flight: "飞机"
        case .ferry: "轮渡"
        case .checkIn: "打卡"
        }
    }

    var systemImage: String {
        switch self {
        case .stay: "mappin.and.ellipse"
        case .walk: "pawprint.fill"
        case .drive: "car.fill"
        case .transit: "bus.fill"
        case .train: "tram.fill"
        case .flight: "airplane"
        case .ferry: "ferry.fill"
        case .checkIn: "camera.fill"
        }
    }

    var navigationLookAheadMeters: CLLocationDistance {
        switch self {
        case .drive:
            180
        case .transit:
            140
        default:
            100
        }
    }

    var navigationCameraDistance: CLLocationDistance {
        switch self {
        case .drive:
            920
        case .transit:
            840
        default:
            760
        }
    }

    var navigationPitch: Double {
        switch self {
        case .drive:
            76
        case .transit:
            72
        default:
            68
        }
    }
}

enum TransportLegStatus: String, Codable, Equatable, Sendable {
    case scheduled
    case waiting
    case boarding
    case inTransit = "in_transit"
    case arrived
    case delayed
    case cancelled

    var displayName: String {
        switch self {
        case .scheduled: "已计划"
        case .waiting: "等待中"
        case .boarding: "准备出发"
        case .inTransit: "进行中"
        case .arrived: "已抵达"
        case .delayed: "延误"
        case .cancelled: "已取消"
        }
    }
}

struct RouteSegment: Codable, Identifiable, Equatable, Sendable {
    var id: String
    var mode: TravelMode
    var title: String
    var detail: String
    var fromPlace: String
    var toPlace: String
    var distanceMeters: Int?
    var durationSeconds: Int?
    var provider: String
    var polyline: String?
    var startTime: Date?
    var endTime: Date?
    var isSimulated: Bool

    enum CodingKeys: String, CodingKey {
        case id
        case mode
        case title
        case detail
        case fromPlace = "from_place"
        case toPlace = "to_place"
        case distanceMeters = "distance_meters"
        case durationSeconds = "duration_seconds"
        case provider
        case polyline
        case startTime = "start_time"
        case endTime = "end_time"
        case isSimulated = "is_simulated"
    }
}

struct ScheduledTransportLeg: Codable, Identifiable, Equatable, Sendable {
    var id: String
    var mode: TravelMode
    var status: TransportLegStatus
    var title: String
    var detail: String
    var originName: String
    var destinationName: String
    var originLatitude: Double
    var originLongitude: Double
    var destinationLatitude: Double
    var destinationLongitude: Double
    var scheduledDeparture: Date
    var scheduledArrival: Date
    var actualDeparture: Date?
    var actualArrival: Date?
    var carrier: String?
    var serviceNumber: String?
    var terminalOrPlatform: String?
    var distanceMeters: Int?
    var durationSeconds: Int?
    var routePolyline: String?
    var progress: Double
    var provider: String
    var realityLevel: String
    var isSimulated: Bool
    var timelineNote: String?

    var originCoordinate: CLLocationCoordinate2D {
        CLLocationCoordinate2D(latitude: originLatitude, longitude: originLongitude)
    }

    var destinationCoordinate: CLLocationCoordinate2D {
        CLLocationCoordinate2D(latitude: destinationLatitude, longitude: destinationLongitude)
    }

    var serviceLabel: String {
        let parts = [carrier, serviceNumber]
            .compactMap { $0?.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
        return parts.isEmpty ? mode.displayName : parts.joined(separator: " ")
    }

    enum CodingKeys: String, CodingKey {
        case id
        case mode
        case status
        case title
        case detail
        case originName = "origin_name"
        case destinationName = "destination_name"
        case originLatitude = "origin_lat"
        case originLongitude = "origin_lng"
        case destinationLatitude = "destination_lat"
        case destinationLongitude = "destination_lng"
        case scheduledDeparture = "scheduled_departure"
        case scheduledArrival = "scheduled_arrival"
        case actualDeparture = "actual_departure"
        case actualArrival = "actual_arrival"
        case carrier
        case serviceNumber = "service_number"
        case terminalOrPlatform = "terminal_or_platform"
        case distanceMeters = "distance_meters"
        case durationSeconds = "duration_seconds"
        case routePolyline = "route_polyline"
        case progress
        case provider
        case realityLevel = "reality_level"
        case isSimulated = "is_simulated"
        case timelineNote = "timeline_note"
    }
}

struct ItineraryStop: Codable, Identifiable, Equatable, Sendable {
    var id: String
    var name: String
    var category: String
    var city: String
    var latitude: Double
    var longitude: Double
    var title: String
    var detail: String
    var plannedTime: String?
    var dwellMinutes: Int
    var postcardCandidate: Bool
    var photoCandidate: Bool
    var source: String

    var coordinate: CLLocationCoordinate2D {
        CLLocationCoordinate2D(latitude: latitude, longitude: longitude)
    }

    enum CodingKeys: String, CodingKey {
        case id
        case name
        case category
        case city
        case latitude = "lat"
        case longitude = "lng"
        case title
        case detail
        case plannedTime = "planned_time"
        case dwellMinutes = "dwell_minutes"
        case postcardCandidate = "postcard_candidate"
        case photoCandidate = "photo_candidate"
        case source
    }
}

struct TransportDecision: Codable, Equatable, Sendable {
    var selectedMode: TravelMode
    var reason: String
    var rejectedModes: [TravelMode]
    var autonomyNote: String

    enum CodingKeys: String, CodingKey {
        case selectedMode = "selected_mode"
        case reason
        case rejectedModes = "rejected_modes"
        case autonomyNote = "autonomy_note"
    }
}

struct JourneyPlan: Codable, Equatable, Sendable {
    var petID: String
    var city: String
    var generatedAt: Date
    var provider: String
    var horizonHours: Int
    var summary: String
    var currentActivity: String
    var transportDecision: TransportDecision
    var routeSegments: [RouteSegment]
    var scheduledTransport: [ScheduledTransportLeg] = []
    var stops: [ItineraryStop]
    var places: [PlaceSignal]
    var nextPostcardHint: String?
    var worldcupEvent: Bool

    enum CodingKeys: String, CodingKey {
        case petID = "pet_id"
        case city
        case generatedAt = "generated_at"
        case provider
        case horizonHours = "horizon_hours"
        case summary
        case currentActivity = "current_activity"
        case transportDecision = "transport_decision"
        case routeSegments = "route_segments"
        case scheduledTransport = "scheduled_transport"
        case stops
        case places
        case nextPostcardHint = "next_postcard_hint"
        case worldcupEvent = "worldcup_event"
    }
}

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

struct LifeTickResult: Codable, Equatable, Sendable {
    var petID: String
    var generatedAt: Date
    var provider: String
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

enum TravelBagItemType: String, Codable, CaseIterable, Equatable, Sendable {
    case snack
    case comfortItem = "comfort_item"
    case guideHint = "guide_hint"
    case luckyCharm = "lucky_charm"
    case musicHint = "music_hint"
    case toy

    var displayName: String {
        switch self {
        case .snack: "小零食"
        case .comfortItem: "记忆物"
        case .guideHint: "想看的地方"
        case .luckyCharm: "护身符"
        case .musicHint: "路上的歌"
        case .toy: "小玩具"
        }
    }

    var systemImage: String {
        switch self {
        case .snack: "takeoutbag.and.cup.and.straw.fill"
        case .comfortItem: "heart.text.square.fill"
        case .guideHint: "map.fill"
        case .luckyCharm: "sparkles"
        case .musicHint: "headphones"
        case .toy: "gift.fill"
        }
    }
}

struct TravelBagItemInput: Codable, Equatable, Sendable {
    var itemType: TravelBagItemType
    var title: String
    var note: String?
    var influenceTags: [String]

    enum CodingKeys: String, CodingKey {
        case itemType = "item_type"
        case title
        case note
        case influenceTags = "influence_tags"
    }
}

struct TravelBagPackRequest: Codable, Equatable, Sendable {
    var questID: String?
    var items: [TravelBagItemInput]
    var ownerMessage: String?

    enum CodingKeys: String, CodingKey {
        case questID = "quest_id"
        case items
        case ownerMessage = "owner_message"
    }
}

struct TravelBagItem: Codable, Identifiable, Equatable, Sendable {
    var id: String
    var itemType: TravelBagItemType
    var title: String
    var note: String?
    var influenceTags: [String]
    var addedAt: Date
    var source: String

    enum CodingKeys: String, CodingKey {
        case id
        case itemType = "item_type"
        case title
        case note
        case influenceTags = "influence_tags"
        case addedAt = "added_at"
        case source
    }
}

struct TravelBag: Codable, Identifiable, Equatable, Sendable {
    var id: String
    var petID: String
    var questID: String?
    var items: [TravelBagItem]
    var ownerMessage: String?
    var petVisibleNote: String
    var updatedAt: Date

    enum CodingKeys: String, CodingKey {
        case id
        case petID = "pet_id"
        case questID = "quest_id"
        case items
        case ownerMessage = "owner_message"
        case petVisibleNote = "pet_visible_note"
        case updatedAt = "updated_at"
    }
}

enum TradePolicy: String, Codable, Equatable, Sendable {
    case tradable
    case soulbound
    case timeLocked = "time_locked"
    case questLocked = "quest_locked"
    case systemLocked = "system_locked"
    case devOnly = "dev_only"
}

enum ItemStatus: String, Codable, Equatable, Sendable {
    case owned
    case equipped
    case stored
    case listed
    case sold
    case consumed
    case archived
    case deleted
}

enum AcquisitionSource: String, Codable, Equatable, Sendable {
    case found
    case shopPurchase = "shop_purchase"
    case npcGift = "npc_gift"
    case questReward = "quest_reward"
    case photoMission = "photo_mission"
    case eventReward = "event_reward"
    case activityReward = "activity_reward"
    case devGrant = "dev_grant"
}

enum EconomyTransactionType: String, Codable, Equatable, Sendable {
    case itemAcquired = "item_acquired"
    case itemSold = "item_sold"
    case ownerFundGranted = "owner_fund_granted"
    case fundToCoinConverted = "fund_to_coin_converted"
    case itemLocked = "item_locked"
    case itemUnlocked = "item_unlocked"
    case itemArchived = "item_archived"
}

struct CurrencyAmounts: Codable, Equatable, Sendable {
    var travelCoin: Int
    var starDust: Int
    var merit: Int

    enum CodingKeys: String, CodingKey {
        case travelCoin = "travel_coin"
        case starDust = "star_dust"
        case merit
    }
}

struct Wallet: Codable, Equatable, Sendable {
    var petID: String
    var travelCoin: Int
    var starDust: Int
    var merit: Int
    var updatedAt: Date

    enum CodingKeys: String, CodingKey {
        case petID = "pet_id"
        case travelCoin = "travel_coin"
        case starDust = "star_dust"
        case merit
        case updatedAt = "updated_at"
    }
}

struct OwnerFund: Codable, Equatable, Sendable {
    var petID: String
    var starDust: Int
    var projectBudget: Int
    var cosmeticBudget: Int
    var travelOpportunityBudget: Int
    var dailyCoinLimit: Int
    var coinInflowToday: Int
    var coinInflowDate: String
    var updatedAt: Date

    enum CodingKeys: String, CodingKey {
        case petID = "pet_id"
        case starDust = "star_dust"
        case projectBudget = "project_budget"
        case cosmeticBudget = "cosmetic_budget"
        case travelOpportunityBudget = "travel_opportunity_budget"
        case dailyCoinLimit = "daily_coin_limit"
        case coinInflowToday = "coin_inflow_today"
        case coinInflowDate = "coin_inflow_date"
        case updatedAt = "updated_at"
    }
}

struct EconomySnapshot: Codable, Equatable, Sendable {
    var petID: String
    var totalDisplayValue: Int
    var sellableValue: Int
    var collectionValue: Int
    var honorValue: Int
    var ownedItemCount: Int
    var sellableItemCount: Int
    var archivedItemCount: Int
    var soldItemCount: Int
    var updatedAt: Date

    enum CodingKeys: String, CodingKey {
        case petID = "pet_id"
        case totalDisplayValue = "total_display_value"
        case sellableValue = "sellable_value"
        case collectionValue = "collection_value"
        case honorValue = "honor_value"
        case ownedItemCount = "owned_item_count"
        case sellableItemCount = "sellable_item_count"
        case archivedItemCount = "archived_item_count"
        case soldItemCount = "sold_item_count"
        case updatedAt = "updated_at"
    }
}

struct EconomyTransaction: Codable, Identifiable, Equatable, Sendable {
    var id: String { txID }

    var txID: String
    var petID: String
    var type: EconomyTransactionType
    var idempotencyKey: String
    var amounts: CurrencyAmounts
    var itemIDs: [String]
    var before: [String: JSONValue]
    var after: [String: JSONValue]
    var reason: String
    var operatorName: String
    var source: String
    var status: String
    var createdAt: Date

    enum CodingKeys: String, CodingKey {
        case txID = "tx_id"
        case petID = "pet_id"
        case type
        case idempotencyKey = "idempotency_key"
        case amounts
        case itemIDs = "item_ids"
        case before
        case after
        case reason
        case operatorName = "operator"
        case source
        case status
        case createdAt = "created_at"
    }
}

struct EconomyResponse: Codable, Equatable, Sendable {
    var wallet: Wallet
    var ownerFund: OwnerFund
    var snapshot: EconomySnapshot
    var recentTransactions: [EconomyTransaction]

    enum CodingKeys: String, CodingKey {
        case wallet
        case ownerFund = "owner_fund"
        case snapshot
        case recentTransactions = "recent_transactions"
    }
}

struct CollectSouvenirsResponse: Codable, Equatable, Sendable {
    var items: [SouvenirItem]
    var transactions: [EconomyTransaction]
    var wallet: Wallet
    var snapshot: EconomySnapshot
}

struct InventoryResponse: Codable, Equatable, Sendable {
    var items: [SouvenirItem]
    var snapshot: EconomySnapshot
}

struct SellItemRequest: Codable, Equatable, Sendable {
    var clientRequestID: String
    var expectedItemVersion: Int

    enum CodingKeys: String, CodingKey {
        case clientRequestID = "client_request_id"
        case expectedItemVersion = "expected_item_version"
    }
}

struct ArchiveItemRequest: Codable, Equatable, Sendable {
    var clientRequestID: String
    var expectedItemVersion: Int

    enum CodingKeys: String, CodingKey {
        case clientRequestID = "client_request_id"
        case expectedItemVersion = "expected_item_version"
    }
}

struct ItemMutationResponse: Codable, Equatable, Sendable {
    var success: Bool
    var transaction: EconomyTransaction
    var wallet: Wallet
    var item: SouvenirItem
    var snapshot: EconomySnapshot
}

enum SouvenirItemType: String, Codable, Equatable, Sendable {
    case toy
    case culturalCreative = "cultural_creative"
    case ticketStub = "ticket_stub"
    case charm
    case snackPack = "snack_pack"
    case photoPrint = "photo_print"
    case foundObject = "found_object"

    var displayName: String {
        switch self {
        case .toy: "小玩具"
        case .culturalCreative: "文创"
        case .ticketStub: "票根"
        case .charm: "护身符"
        case .snackPack: "小零食"
        case .photoPrint: "照片小卡"
        case .foundObject: "路上捡到的小东西"
        }
    }

    var systemImage: String {
        switch self {
        case .ticketStub: "ticket.fill"
        case .photoPrint: "photo.on.rectangle.angled"
        case .culturalCreative: "sparkles.square.filled.on.square"
        case .charm: "seal.fill"
        case .snackPack: "takeoutbag.and.cup.and.straw.fill"
        case .toy: "gift.fill"
        case .foundObject: "leaf.fill"
        }
    }
}

struct SouvenirItem: Codable, Identifiable, Equatable, Sendable {
    var id: String
    var petID: String
    var questID: String?
    var templateID: String? = nil
    var itemType: SouvenirItemType
    var title: String
    var subtitle: String
    var city: String
    var placeName: String
    var story: String
    var petVoice: String
    var imagePrompt: String
    var imageURL: URL? = nil
    var rarity: String
    var obtainedAt: Date
    var source: String
    var status: ItemStatus? = nil
    var version: Int? = nil
    var tradePolicy: TradePolicy? = nil
    var lockUntil: Date? = nil
    var marketValue: Int? = nil
    var emotionalValue: Int? = nil
    var honorValue: Int? = nil
    var valueBreakdown: [String: JSONValue]? = nil
    var acquireSource: AcquisitionSource? = nil
    var originEventID: String? = nil
    var originActivityID: String? = nil
    var originActivityType: String? = nil
    var originPOIName: String? = nil
    var originCity: String? = nil
    var originWeather: String? = nil
    var originCoords: [Double]? = nil
    var updatedAt: Date? = nil

    enum CodingKeys: String, CodingKey {
        case id
        case petID = "pet_id"
        case questID = "quest_id"
        case templateID = "template_id"
        case itemType = "item_type"
        case title
        case subtitle
        case city
        case placeName = "place_name"
        case story
        case petVoice = "pet_voice"
        case imagePrompt = "image_prompt"
        case imageURL = "image_url"
        case rarity
        case obtainedAt = "obtained_at"
        case source
        case status
        case version
        case tradePolicy = "trade_policy"
        case lockUntil = "lock_until"
        case marketValue = "market_value"
        case emotionalValue = "emotional_value"
        case honorValue = "honor_value"
        case valueBreakdown = "value_breakdown"
        case acquireSource = "acquire_source"
        case originEventID = "origin_event_id"
        case originActivityID = "origin_activity_id"
        case originActivityType = "origin_activity_type"
        case originPOIName = "origin_poi_name"
        case originCity = "origin_city"
        case originWeather = "origin_weather"
        case originCoords = "origin_coords"
        case updatedAt = "updated_at"
    }

    var effectiveStatus: ItemStatus { status ?? .owned }
    var effectiveVersion: Int { version ?? 1 }
    var effectiveTradePolicy: TradePolicy { tradePolicy ?? .tradable }
    var displayMarketValue: Int { marketValue ?? 0 }
    var displayEmotionalValue: Int { emotionalValue ?? 0 }
    var displayHonorValue: Int { honorValue ?? 0 }
    var resaleValue: Int { displayMarketValue / 2 }
    var isSellable: Bool { effectiveStatus == .owned && effectiveTradePolicy == .tradable && resaleValue > 0 }
}

struct TravelQuest: Codable, Identifiable, Equatable, Sendable {
    var id: String
    var petID: String
    var questType: TravelQuestType
    var status: TravelQuestStatus
    var currentPhase: TravelQuestStatus
    var tripType: TravelQuestTripType
    var returnPolicy: TravelQuestReturnPolicy
    var originAnchor: TravelAnchor?
    var ownerMessage: String
    var destination: String
    var eventName: String?
    var preferredStartDate: String?
    var autonomyDecision: String
    var currentPhaseMessage: String
    var guide: TravelQuestGuide?
    var travelBag: TravelBag?
    var journeyPlan: JourneyPlan?
    var postEventOptions: [TravelQuestNextOption]
    var souvenirPreview: [SouvenirItem]
    var selectedNextOptionID: String?
    var worldcupEvent: Bool
    var createdAt: Date
    var updatedAt: Date

    enum CodingKeys: String, CodingKey {
        case id
        case petID = "pet_id"
        case questType = "quest_type"
        case status
        case currentPhase = "current_phase"
        case tripType = "trip_type"
        case returnPolicy = "return_policy"
        case originAnchor = "origin_anchor"
        case ownerMessage = "owner_message"
        case destination
        case eventName = "event_name"
        case preferredStartDate = "preferred_start_date"
        case autonomyDecision = "autonomy_decision"
        case currentPhaseMessage = "current_phase_message"
        case guide
        case travelBag = "travel_bag"
        case journeyPlan = "journey_plan"
        case postEventOptions = "post_event_options"
        case souvenirPreview = "souvenir_preview"
        case selectedNextOptionID = "selected_next_option_id"
        case worldcupEvent = "worldcup_event"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
    }
}

struct RemoteJourneyRoutePlan: Codable, Equatable, Sendable {
    var petID: String
    var city: String
    var generatedAt: Date
    var provider: String
    var steps: [RemoteRouteStep]
    var places: [PlaceSignal]

    enum CodingKeys: String, CodingKey {
        case petID = "pet_id"
        case city
        case generatedAt = "generated_at"
        case provider
        case steps
        case places
    }
}

extension JourneyPlan {
    var compatibilityRoutePlan: RemoteJourneyRoutePlan {
        let stopSteps = stops.map { stop in
            RemoteRouteStep(
                id: "\(stop.id)-stay",
                mode: TravelMode.stay.rawValue,
                title: stop.title,
                detail: stop.detail,
                startTime: nil,
                endTime: nil,
                fromPlace: stop.name,
                toPlace: nil
            )
        }
        let segmentSteps = routeSegments.map { segment in
            RemoteRouteStep(
                id: segment.id,
                mode: segment.mode.rawValue,
                title: segment.title,
                detail: segment.detail,
                startTime: segment.startTime,
                endTime: segment.endTime,
                fromPlace: segment.fromPlace,
                toPlace: segment.toPlace
            )
        }
        return RemoteJourneyRoutePlan(
            petID: petID,
            city: city,
            generatedAt: generatedAt,
            provider: provider,
            steps: stopSteps + segmentSteps,
            places: places
        )
    }
}

struct RemoteRouteStep: Codable, Identifiable, Equatable, Sendable {
    var id: String
    var mode: String
    var title: String
    var detail: String
    var startTime: Date?
    var endTime: Date?
    var fromPlace: String?
    var toPlace: String?

    enum CodingKeys: String, CodingKey {
        case id
        case mode
        case title
        case detail
        case startTime = "start_time"
        case endTime = "end_time"
        case fromPlace = "from_place"
        case toPlace = "to_place"
    }
}

struct PlaceSignal: Codable, Identifiable, Equatable, Sendable {
    var id: String
    var name: String
    var category: String
    var city: String
    var latitude: Double
    var longitude: Double
    var activityHint: String
    var detailHint: String
    var source: String
    var rating: Double? = nil
    var cost: String? = nil
    var photoURL: URL? = nil
    var businessArea: String? = nil
    var distanceMeters: Int? = nil
    var guideScore: Double? = nil
    var guideReason: String? = nil

    var coordinate: CLLocationCoordinate2D {
        CLLocationCoordinate2D(latitude: latitude, longitude: longitude)
    }

    enum CodingKeys: String, CodingKey {
        case id
        case name
        case category
        case city
        case latitude = "lat"
        case longitude = "lng"
        case activityHint = "activity_hint"
        case detailHint = "detail_hint"
        case source
        case rating
        case cost
        case photoURL = "photo_url"
        case businessArea = "business_area"
        case distanceMeters = "distance_meters"
        case guideScore = "guide_score"
        case guideReason = "guide_reason"
    }
}

enum PhotoPerspective: String, Codable, Equatable, Sendable {
    case firstPersonSelfie = "first_person_selfie"
    case passerbyThirdPerson = "passerby_third_person"
    case communicatorView = "communicator_view"
}

struct PlaceInteraction: Codable, Identifiable, Equatable, Sendable {
    var id: String
    var petID: String
    var place: PlaceSignal
    var interactionType: String
    var title: String
    var detail: String
    var petAction: String
    var emotionalTone: String
    var dwellMinutes: Int
    var canGeneratePhoto: Bool
    var source: String

    enum CodingKeys: String, CodingKey {
        case id
        case petID = "pet_id"
        case place
        case interactionType = "interaction_type"
        case title
        case detail
        case petAction = "pet_action"
        case emotionalTone = "emotional_tone"
        case dwellMinutes = "dwell_minutes"
        case canGeneratePhoto = "can_generate_photo"
        case source
    }
}

struct PhotoMission: Codable, Identifiable, Equatable, Sendable {
    var id: String
    var petID: String
    var generatedAt: Date
    var provider: String
    var city: String
    var place: PlaceSignal
    var interaction: PlaceInteraction
    var cameraPerspective: PhotoPerspective
    var sceneAnchor: String
    var landmarkHints: [String]
    var localDetailHints: [String]
    var crowdHints: [String]
    var weather: String
    var timeOfDay: String
    var imagePrompt: String
    var postcardText: String
    var safetyNotes: [String]

    enum CodingKeys: String, CodingKey {
        case id
        case petID = "pet_id"
        case generatedAt = "generated_at"
        case provider
        case city
        case place
        case interaction
        case cameraPerspective = "camera_perspective"
        case sceneAnchor = "scene_anchor"
        case landmarkHints = "landmark_hints"
        case localDetailHints = "local_detail_hints"
        case crowdHints = "crowd_hints"
        case weather
        case timeOfDay = "time_of_day"
        case imagePrompt = "image_prompt"
        case postcardText = "postcard_text"
        case safetyNotes = "safety_notes"
    }
}

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

struct WorldCupHostCity: Identifiable, Hashable, Sendable {
    var id: String
    var city: String
    var region: String
    var country: String
    var stadiumName: String
    var latitude: Double
    var longitude: Double
    var atmosphereHint: String

    var coordinate: CLLocationCoordinate2D {
        CLLocationCoordinate2D(latitude: latitude, longitude: longitude)
    }

    var displayName: String {
        "\(city) · \(stadiumName)"
    }

    var questDestination: String {
        "\(country) · \(city)"
    }

    var shortLocation: String {
        "\(country) · \(city)"
    }

    static let recommended = hostCities.first { $0.id == "los-angeles" } ?? hostCities[0]

    static let hostCities: [WorldCupHostCity] = [
        WorldCupHostCity(
            id: "vancouver",
            city: "温哥华",
            region: "Canada",
            country: "加拿大",
            stadiumName: "BC Place",
            latitude: 49.2767,
            longitude: -123.1119,
            atmosphereHint: "海风、山影和球场灯"
        ),
        WorldCupHostCity(
            id: "toronto",
            city: "多伦多",
            region: "Canada",
            country: "加拿大",
            stadiumName: "BMO Field",
            latitude: 43.6328,
            longitude: -79.4186,
            atmosphereHint: "湖边风和红色围巾"
        ),
        WorldCupHostCity(
            id: "seattle",
            city: "西雅图",
            region: "United States",
            country: "美国",
            stadiumName: "Lumen Field",
            latitude: 47.5952,
            longitude: -122.3316,
            atmosphereHint: "港口、雨后街道和低低欢呼"
        ),
        WorldCupHostCity(
            id: "san-francisco-bay",
            city: "旧金山湾区",
            region: "United States",
            country: "美国",
            stadiumName: "Levi's Stadium",
            latitude: 37.4032,
            longitude: -121.9698,
            atmosphereHint: "湾区傍晚和球迷广场"
        ),
        WorldCupHostCity(
            id: "los-angeles",
            city: "洛杉矶",
            region: "United States",
            country: "美国",
            stadiumName: "SoFi Stadium",
            latitude: 33.9535,
            longitude: -118.3392,
            atmosphereHint: "很亮的夜、棕榈树和远方球场"
        ),
        WorldCupHostCity(
            id: "guadalajara",
            city: "瓜达拉哈拉",
            region: "Mexico",
            country: "墨西哥",
            stadiumName: "Estadio Akron",
            latitude: 20.6819,
            longitude: -103.4621,
            atmosphereHint: "暖色街道和小旗子"
        ),
        WorldCupHostCity(
            id: "mexico-city",
            city: "墨西哥城",
            region: "Mexico",
            country: "墨西哥",
            stadiumName: "Estadio Azteca",
            latitude: 19.3029,
            longitude: -99.1505,
            atmosphereHint: "高处城市、古老球场和人群声"
        ),
        WorldCupHostCity(
            id: "monterrey",
            city: "蒙特雷",
            region: "Mexico",
            country: "墨西哥",
            stadiumName: "Estadio BBVA",
            latitude: 25.6687,
            longitude: -100.2447,
            atmosphereHint: "山影和热闹入口"
        ),
        WorldCupHostCity(
            id: "houston",
            city: "休斯敦",
            region: "United States",
            country: "美国",
            stadiumName: "NRG Stadium",
            latitude: 29.6847,
            longitude: -95.4107,
            atmosphereHint: "热空气、车灯和球迷广场"
        ),
        WorldCupHostCity(
            id: "dallas",
            city: "达拉斯",
            region: "United States",
            country: "美国",
            stadiumName: "AT&T Stadium",
            latitude: 32.7473,
            longitude: -97.0945,
            atmosphereHint: "宽阔公路和银色球场"
        ),
        WorldCupHostCity(
            id: "kansas-city",
            city: "堪萨斯城",
            region: "United States",
            country: "美国",
            stadiumName: "Arrowhead Stadium",
            latitude: 39.049,
            longitude: -94.4839,
            atmosphereHint: "红色人潮和长长尾声"
        ),
        WorldCupHostCity(
            id: "atlanta",
            city: "亚特兰大",
            region: "United States",
            country: "美国",
            stadiumName: "Mercedes-Benz Stadium",
            latitude: 33.7554,
            longitude: -84.4008,
            atmosphereHint: "城市灯光和室内球场声"
        ),
        WorldCupHostCity(
            id: "miami",
            city: "迈阿密",
            region: "United States",
            country: "美国",
            stadiumName: "Hard Rock Stadium",
            latitude: 25.958,
            longitude: -80.2389,
            atmosphereHint: "热带夜风和颜色很亮的人群"
        ),
        WorldCupHostCity(
            id: "philadelphia",
            city: "费城",
            region: "United States",
            country: "美国",
            stadiumName: "Lincoln Financial Field",
            latitude: 39.9008,
            longitude: -75.1675,
            atmosphereHint: "老城故事和赛前灯光"
        ),
        WorldCupHostCity(
            id: "new-york-new-jersey",
            city: "纽约新泽西",
            region: "United States",
            country: "美国",
            stadiumName: "MetLife Stadium",
            latitude: 40.8135,
            longitude: -74.0745,
            atmosphereHint: "很大的城市风和远处看台"
        ),
        WorldCupHostCity(
            id: "boston",
            city: "波士顿",
            region: "United States",
            country: "美国",
            stadiumName: "Gillette Stadium",
            latitude: 42.0909,
            longitude: -71.2643,
            atmosphereHint: "郊外球场和清凉空气"
        )
    ]
}

enum WorldCupBagItem: String, CaseIterable, Identifiable, Hashable, Sendable {
    case scarf
    case snack
    case cameraCharm
    case footballBadge
    case smallFlag

    var id: String { rawValue }

    var title: String {
        switch self {
        case .scarf: "小围巾"
        case .snack: "小零食"
        case .cameraCharm: "拍照小挂件"
        case .footballBadge: "小足球徽章"
        case .smallFlag: "小旗子"
        }
    }

    var systemImage: String {
        switch self {
        case .scarf: "scarf.fill"
        case .snack: "takeoutbag.and.cup.and.straw.fill"
        case .cameraCharm: "camera.fill"
        case .footballBadge: "seal.fill"
        case .smallFlag: "flag.fill"
        }
    }

    var sortOrder: Int {
        switch self {
        case .scarf: 0
        case .snack: 1
        case .cameraCharm: 2
        case .footballBadge: 3
        case .smallFlag: 4
        }
    }

    var travelBagInput: TravelBagItemInput {
        switch self {
        case .scarf:
            TravelBagItemInput(
                itemType: .comfortItem,
                title: "小围巾",
                note: "去远方球场时可以轻轻搭在小包边上。",
                influenceTags: ["worldcup", "scarf", "warmth"]
            )
        case .snack:
            TravelBagItemInput(
                itemType: .snack,
                title: "长途小零食",
                note: "路很远，先放一点不会太甜的小零食。",
                influenceTags: ["worldcup", "energy", "long_trip"]
            )
        case .cameraCharm:
            TravelBagItemInput(
                itemType: .luckyCharm,
                title: "拍照小挂件",
                note: "看到球场灯光时，提醒 TA 拍给你看。",
                influenceTags: ["worldcup", "photo", "current_status"]
            )
        case .footballBadge:
            TravelBagItemInput(
                itemType: .luckyCharm,
                title: "小足球徽章",
                note: "这不是球票，只是一枚远方邀请的标记。",
                influenceTags: ["worldcup", "invitation", "paw_pass"]
            )
        case .smallFlag:
            TravelBagItemInput(
                itemType: .toy,
                title: "小旗子",
                note: "到了球迷广场，可以跟着风轻轻晃一下。",
                influenceTags: ["worldcup", "fan_zone", "color"]
            )
        }
    }
}

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
