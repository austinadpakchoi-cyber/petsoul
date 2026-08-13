import CoreLocation
import Foundation

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

