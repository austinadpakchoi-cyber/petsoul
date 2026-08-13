import Foundation

@MainActor
extension MockPetJourneyService {
    func fetchTravelBag(petID: String, questID: String?) async throws -> TravelBag {
        try ensureJourneyExists(for: petID)
        let key = travelBagKey(petID: petID, questID: questID)
        if let bag = travelBags[key] {
            return bag
        }
        return emptyTravelBag(petID: petID, questID: questID)
    }

    func packTravelBag(petID: String, request: TravelBagPackRequest) async throws -> TravelBag {
        try ensureJourneyExists(for: petID)
        let key = travelBagKey(petID: petID, questID: request.questID)
        let existing = travelBags[key] ?? emptyTravelBag(petID: petID, questID: request.questID)
        let now = Date()
        let newItems = request.items.map {
            TravelBagItem(
                id: "TBI-\(UUID().uuidString.prefix(8).uppercased())",
                itemType: $0.itemType,
                title: $0.title,
                note: $0.note,
                influenceTags: $0.influenceTags,
                addedAt: now,
                source: "owner"
            )
        }
        let mergedItems = Array((existing.items + newItems).suffix(12))
        let updated = TravelBag(
            id: existing.id,
            petID: petID,
            questID: request.questID,
            items: mergedItems,
            ownerMessage: request.ownerMessage ?? existing.ownerMessage,
            petVisibleNote: travelBagNote(for: mergedItems),
            updatedAt: now
        )
        travelBags[key] = updated
        if let questID = request.questID,
           var quests = travelQuests[petID],
           let index = quests.firstIndex(where: { $0.id == questID }) {
            quests[index] = quests[index].with(travelBag: updated)
            travelQuests[petID] = quests
        }
        return updated
    }

    func mockText(_ text: String, containsAny keywords: [String]) -> Bool {
        keywords.contains { text.localizedCaseInsensitiveContains($0) }
    }

    func travelBagKey(petID: String, questID: String?) -> String {
        "\(petID)-\(questID ?? "main")"
    }

    func emptyTravelBag(petID: String, questID: String?) -> TravelBag {
        TravelBag(
            id: "TB-\(petID)-\(questID ?? "main")",
            petID: petID,
            questID: questID,
            items: [],
            ownerMessage: nil,
            petVisibleNote: "这只小包还空着。出发前可以放一点小零食、护身符，或一句想让 TA 带着走的话。",
            updatedAt: Date()
        )
    }

    func travelBagNote(for items: [TravelBagItem]) -> String {
        guard !items.isEmpty else {
            return "这只小包还空着。出发前可以放一点小零食、护身符，或一句想让 TA 带着走的话。"
        }
        let names = items.suffix(4).map(\.title).joined(separator: "、")
        return "我把 \(names) 收进小包里了。它们不会替我决定路线，但会在路上提醒我慢一点、记得回来。"
    }
}
