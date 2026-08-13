import CoreLocation
import Foundation

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

