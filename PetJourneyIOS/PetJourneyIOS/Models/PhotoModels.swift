import CoreLocation
import Foundation

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

struct PhotoQualityReport: Codable, Equatable, Sendable {
    var petIdentityScore: Double
    var placeRecognitionScore: Double
    var emotionalToneScore: Double
    var policySafety: Bool
    var logoBrandRisk: Double
    var uncannyRisk: Double
    var retryReason: String?
    var failureCategory: String?
    var evaluator: String?

    enum CodingKeys: String, CodingKey {
        case petIdentityScore = "pet_identity_score"
        case placeRecognitionScore = "place_recognition_score"
        case emotionalToneScore = "emotional_tone_score"
        case policySafety = "policy_safety"
        case logoBrandRisk = "logo_brand_risk"
        case uncannyRisk = "uncanny_risk"
        case retryReason = "retry_reason"
        case failureCategory = "failure_category"
        case evaluator
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
    var promptBlocks: [String: String]?
    var qualityReport: PhotoQualityReport?
    var retryCount: Int?
    var failureCategory: String?

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
        case promptBlocks = "prompt_blocks"
        case qualityReport = "quality_report"
        case retryCount = "retry_count"
        case failureCategory = "failure_category"
    }
}

