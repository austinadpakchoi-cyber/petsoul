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

