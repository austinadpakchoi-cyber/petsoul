import Foundation

@MainActor
extension MockPetJourneyService {
    func registerPushDevice(_ request: DeviceRegistrationRequest) async throws -> DeviceRegistrationResponse {
        try ensureJourneyExists(for: request.petID)
        let deviceID = registeredDeviceIDs[request.deviceToken] ?? UUID().uuidString
        registeredDeviceIDs[request.deviceToken] = deviceID
        return DeviceRegistrationResponse(
            success: true,
            deviceID: deviceID,
            provider: "mock-notification-provider",
            message: "设备已经登记，TA 可以在 app 未打开时继续来信。"
        )
    }

    func unregisterPushDevice(_ request: DeviceRegistrationRequest) async throws {
        registeredDeviceIDs.removeValue(forKey: request.deviceToken)
    }

    func fetchNotifications(petID: String, limit: Int) async throws -> [NotificationDelivery] {
        try ensureJourneyExists(for: petID)
        return Array((notifications[petID] ?? []).prefix(max(1, limit)))
    }

    func simulateElapsedTime(_ seconds: TimeInterval, for petID: String) {
        guard var journey = journeys[petID] else { return }
        journey.createdAt = journey.createdAt.addingTimeInterval(-seconds)
        journeys[petID] = journey
    }

    func ensureJourneyExists(for petID: String) throws {
        if journeys[petID] != nil { return }
        let profile = PetProfile(
            petID: petID,
            name: "小黑",
            petType: .dog,
            dna: .demoFrenchie,
            photoURL: MockDemoMedia.frenchieProfileURL
        )
        let thought = agentThought(
            translation: "我回到通讯器里了，今天也会慢慢走。",
            tone: "restored",
            petType: profile.petType
        )
        journeys[petID] = MockJourney(
            profile: profile,
            createdAt: Date().addingTimeInterval(-18),
            lastThoughtText: thought.text,
            thoughts: [thought],
            events: [],
            postcards: [],
            happinessOffset: 0,
            curiosityOffset: 0,
            energyOffset: 0,
            connectedThoughtAdded: true
        )
        ensureMemorySeed(petID: petID, profile: profile)
    }

    func identityMemory(for profile: PetProfile) -> MemoryRecord {
        makeMemory(
            petID: profile.petID,
            kind: "identity",
            title: "\(profile.name) 的通讯 DNA",
            content: "\(profile.name) 的主人称呼是\(profile.dna.ownerTitle)，性格是\(profile.dna.personality)。喜欢\(profile.dna.favoritePlaces.joined(separator: "、"))。",
            salience: 0.95,
            source: "onboarding",
            metadata: ["pet_type": .string(profile.petType.rawValue)],
            memoryType: "relationship",
            importance: 0.96,
            emotionalValence: 0.42,
            confidence: 1,
            sourceEventID: nil,
            structuredPayload: ["origin": .string("dna_onboarding")]
        )
    }

    func refreshIdentityMemory(for profile: PetProfile) {
        var items = memories[profile.petID] ?? []
        items.removeAll { $0.kind == "identity" }
        items.insert(identityMemory(for: profile), at: 0)
        memories[profile.petID] = items
    }

    func makeMemory(
        petID: String,
        kind: String,
        title: String,
        content: String,
        salience: Double,
        source: String,
        metadata: [String: JSONValue],
        memoryType: String? = nil,
        importance: Double? = nil,
        emotionalValence: Double? = nil,
        confidence: Double? = nil,
        sourceEventID: String? = nil,
        structuredPayload: [String: JSONValue]? = nil
    ) -> MemoryRecord {
        MemoryRecord(
            id: UUID().uuidString,
            petID: petID,
            kind: kind,
            title: title,
            content: content,
            salience: salience,
            source: source,
            createdAt: Date(),
            lastSeenAt: Date(),
            metadata: metadata,
            memoryType: memoryType ?? kind,
            importance: importance ?? salience,
            emotionalValence: emotionalValence ?? 0,
            confidence: confidence ?? 1,
            sourceEventID: sourceEventID,
            structuredPayload: structuredPayload ?? [:]
        )
    }

    func appendMemory(
        petID: String,
        kind: String,
        title: String,
        content: String,
        salience: Double,
        source: String,
        metadata: [String: JSONValue]
    ) {
        let item = makeMemory(
            petID: petID,
            kind: kind,
            title: title,
            content: content,
            salience: salience,
            source: source,
            metadata: metadata
        )
        memories[petID, default: []].insert(item, at: 0)
    }

    func ensureMemorySeed(petID: String, profile: PetProfile) {
        if memories[petID]?.isEmpty == false { return }
        memories[petID] = [identityMemory(for: profile)]
    }

    func advanceJourney(petID: String) {
        guard var journey = journeys[petID] else { return }
        let elapsed = Date().timeIntervalSince(journey.createdAt)
        let city = cityFor(journey: journey)

        if elapsed >= 10, !journey.connectedThoughtAdded {
            appendThought("连接已经稳定了。我好像听见你在这边。", to: &journey, tone: "connected")
            journey.connectedThoughtAdded = true
        }

        let thoughtIndex = max(0, Int(elapsed / 5)) % city.thoughts.count
        let nextThought = city.thoughts[thoughtIndex]
        let lastThought = journey.thoughts.last
        let isRecentFeedback = lastThought.map {
            ["guide_saved", "guide_skipped"].contains($0.tone) && Date().timeIntervalSince($0.timestamp) < 8
        } ?? false
        if nextThought != journey.lastThoughtText, !isRecentFeedback {
            appendThought(nextThought, to: &journey, tone: "daily")
        }

        if elapsed >= 35, journey.postcards.isEmpty {
            journey.postcards.append(
                Postcard(
                    id: UUID().uuidString,
                    location: "\(city.name) · 安静网吧",
                    text: "我找到一个很亮的屏幕，旁边的人都很专心。我戴着耳机坐了一会儿，像是在陪他们赢一局。",
                    weather: "室内有蓝色的灯，外面应该还是温暖的",
                    happiness: clamped(88 + journey.happinessOffset, 20, 99),
                    timestamp: Date(),
                    imageURL: MockDemoMedia.frenchiePostcardURL,
                    isNew: true
                )
            )
            appendThought("我刚刚拍了一张照片给你。这里有键盘声、饮料杯，还有一点点像冒险的光。", to: &journey, tone: "selfie")
        }

        if journey.thoughts.count > 18 {
            journey.thoughts = Array(journey.thoughts.suffix(18))
        }
        journeys[petID] = journey
    }

    func appendThought(_ text: String, to journey: inout MockJourney, tone: String) {
        let thought = agentThought(translation: text, tone: tone, petType: journey.profile.petType)
        journey.thoughts.append(thought)
        journey.lastThoughtText = text
    }

    func agentThought(translation: String, tone: String, petType: PetType) -> JourneyThought {
        let animalText = animalSpeech(for: tone, petType: petType)
        return JourneyThought(
            id: UUID().uuidString,
            text: animalText,
            timestamp: Date(),
            tone: tone,
            animalText: animalText,
            translationAvailable: true,
            translation: translation,
            languageStyle: petType.languageStyle,
            model: "mock-agent"
        )
    }

    func animalSpeech(for tone: String, petType: PetType) -> String {
        petType.vocalization(for: tone)
    }

    func cityFor(journey: MockJourney) -> MockCity {
        let elapsed = Date().timeIntervalSince(journey.createdAt)
        let index = max(0, Int(elapsed / 172_800)) % cities.count
        return cities[index]
    }

    func statusFor(now: Date) -> JourneyStatus {
        let components = Calendar.current.dateComponents([.hour, .minute], from: now)
        let minuteOfDay = (components.hour ?? 0) * 60 + (components.minute ?? 0)

        switch minuteOfDay {
        case 0..<420:
            return .resting
        case 420..<510:
            return .staying
        case 510..<570:
            return .walking
        case 570..<690:
            return .staying
        case 690..<750:
            return .walking
        case 750..<900:
            return .staying
        case 900..<1_080:
            return .staying
        case 1_080..<1_140:
            return .walking
        default:
            return .resting
        }
    }

    func wave(_ elapsed: TimeInterval, period: TimeInterval, amplitude: Int) -> Int {
        Int(sin(elapsed / period * .pi * 2) * Double(amplitude))
    }

    func clamped(_ value: Int, _ lower: Int, _ upper: Int) -> Int {
        min(max(value, lower), upper)
    }

    func clamped(_ value: Double, _ lower: Double, _ upper: Double) -> Double {
        min(max(value, lower), upper)
    }

    func nonEmpty(_ value: String?, fallback: String) -> String {
        guard let value else { return fallback }
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? fallback : trimmed
    }
}
