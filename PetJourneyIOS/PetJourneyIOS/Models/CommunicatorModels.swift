import CoreLocation
import Foundation

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

