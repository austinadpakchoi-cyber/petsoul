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

