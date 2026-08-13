import Foundation

@MainActor
extension MockPetJourneyService {
    func fetchMemories(petID: String, limit: Int) async throws -> [MemoryRecord] {
        try ensureJourneyExists(for: petID)
        guard let journey = journeys[petID] else { throw PetJourneyError.noPetSession }
        ensureMemorySeed(petID: petID, profile: journey.profile)
        return Array((memories[petID] ?? []).prefix(max(1, limit)))
    }

    func addMemory(petID: String, request: MemoryCreateRequest) async throws -> MemoryRecord {
        try ensureJourneyExists(for: petID)
        let item = makeMemory(
            petID: petID,
            kind: request.kind,
            title: request.title,
            content: request.content,
            salience: request.salience,
            source: request.source,
            metadata: request.metadata,
            memoryType: request.memoryType,
            importance: request.importance,
            emotionalValence: request.emotionalValence,
            confidence: request.confidence,
            sourceEventID: request.sourceEventID,
            structuredPayload: request.structuredPayload
        )
        memories[petID, default: []].insert(item, at: 0)
        return item
    }

    func updateMemory(petID: String, memoryID: String, request: MemoryUpdateRequest) async throws -> MemoryRecord {
        try ensureJourneyExists(for: petID)
        guard var items = memories[petID],
              let index = items.firstIndex(where: { $0.id == memoryID })
        else {
            throw PetJourneyError.requestFailed("记忆档案没有找到")
        }
        var item = items[index]
        item.kind = nonEmpty(request.kind, fallback: item.kind)
        item.title = nonEmpty(request.title, fallback: item.title)
        item.content = nonEmpty(request.content, fallback: item.content)
        item.salience = clamped(request.salience ?? item.salience, 0, 1)
        item.source = nonEmpty(request.source, fallback: item.source)
        item.metadata = request.metadata ?? item.metadata
        item.memoryType = request.memoryType ?? item.memoryType
        item.importance = clamped(request.importance ?? item.importance ?? item.salience, 0, 1)
        item.emotionalValence = clamped(request.emotionalValence ?? item.emotionalValence ?? 0, -1, 1)
        item.confidence = clamped(request.confidence ?? item.confidence ?? 1, 0, 1)
        item.sourceEventID = request.sourceEventID ?? item.sourceEventID
        item.structuredPayload = request.structuredPayload ?? item.structuredPayload
        item.lastSeenAt = Date()
        items.remove(at: index)
        items.insert(item, at: 0)
        memories[petID] = items
        return item
    }

    func deleteMemory(petID: String, memoryID: String) async throws {
        try ensureJourneyExists(for: petID)
        memories[petID]?.removeAll { $0.id == memoryID }
    }

    func searchMemories(petID: String, request: MemorySearchRequest) async throws -> MemorySearchResponse {
        let all = try await fetchMemories(petID: petID, limit: 100)
        let query = request.query.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        let filtered = query.isEmpty ? all : all.filter {
            $0.title.lowercased().contains(query) || $0.content.lowercased().contains(query)
        }
        return MemorySearchResponse(
            petID: petID,
            query: request.query,
            provider: "mock-ios-memory-store",
            items: Array(filtered.prefix(max(1, request.limit)))
        )
    }

    func generateSelfie(petID: String) async throws -> Postcard {
        try ensureJourneyExists(for: petID)
        guard var journey = journeys[petID] else { throw PetJourneyError.noPetSession }
        let city = cityFor(journey: journey)
        let postcard = Postcard(
            id: UUID().uuidString,
            location: "\(city.name) · 安静网吧",
            text: "我找到一个很亮的屏幕，旁边的人都很专心。我戴着耳机坐了一会儿，像是在陪他们赢一局。",
            weather: "室内有蓝色的灯，外面应该还是温暖的",
            happiness: clamped(88 + journey.happinessOffset, 20, 99),
            timestamp: Date(),
            imageURL: MockDemoMedia.frenchiePostcardURL,
            isNew: true
        )
        journey.postcards.append(postcard)
        appendThought("我刚刚拍了一张照片给你。这里有键盘声、饮料杯，还有一点点像冒险的光。", to: &journey, tone: "selfie")
        journey.events.append(
            JourneyEvent(
                id: UUID().uuidString,
                title: "发回一张自主自拍",
                detail: "\(journey.profile.name) 在 \(postcard.location) 停下，把这一刻拍给你看。",
                timestamp: Date()
            )
        )
        journeys[petID] = journey
        appendMemory(
            petID: petID,
            kind: "postcard",
            title: "\(postcard.location) 的自拍",
            content: postcard.text,
            salience: 0.86,
            source: "mock_selfie",
            metadata: ["postcard_id": .string(postcard.id)]
        )
        return postcard
    }
}
