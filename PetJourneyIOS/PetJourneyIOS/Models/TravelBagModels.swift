import CoreLocation
import Foundation

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

