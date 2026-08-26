import Foundation

@MainActor
extension MockPetJourneyService {
    func createPet(request: CreatePetRequest) async throws -> CreatePetResponse {
        let petID = "PJ-\(UUID().uuidString.prefix(8).uppercased())"
        let profile = PetProfile(
            petID: petID,
            name: request.name.trimmingCharacters(in: .whitespacesAndNewlines),
            petType: request.petType,
            dna: request.dna,
            photoURL: MockDemoMedia.frenchieProfileURL
        )
        let firstThought = agentThought(
            translation: "\(profile.name) 的通讯频率正在变清晰。",
            tone: "connecting",
            petType: profile.petType
        )
        journeys[petID] = MockJourney(
            profile: profile,
            createdAt: Date(),
            lastThoughtText: firstThought.text,
            thoughts: [firstThought],
            events: [],
            postcards: [],
            happinessOffset: 0,
            curiosityOffset: 0,
            energyOffset: 0,
            connectedThoughtAdded: false
        )
        memories[petID] = [identityMemory(for: profile)]
        communicatorMessages[petID] = []
        communicatorMoments[petID] = seedMoments(petID: petID, petName: profile.name, city: cities[0])

        return CreatePetResponse(
            success: true,
            petID: petID,
            name: profile.name,
            location: cities[0].name,
            photoURL: profile.photoURL,
            message: "\(profile.name) 已经在 \(cities[0].name) 开始旅程了"
        )
    }

    func fetchAgentStatus(petID: String) async throws -> AgentStatus {
        try ensureJourneyExists(for: petID)
        advanceJourney(petID: petID)
        guard let journey = journeys[petID] else { throw PetJourneyError.noPetSession }

        let city = cityFor(journey: journey)
        let now = Date()
        let elapsed = now.timeIntervalSince(journey.createdAt)
        let phraseIndex = max(0, Int(elapsed / 30)) % city.phrases.count
        let status = statusFor(now: now)

        let state = AgentState(
            location: city.name,
            travelDay: max(1, Int(elapsed / 86_400) + 1),
            weather: city.weather,
            status: status,
            statusNote: city.phrases[phraseIndex],
            energy: clamped(73 + journey.energyOffset + wave(elapsed, period: 15, amplitude: 4), 25, 99),
            happiness: clamped(78 + journey.happinessOffset + wave(elapsed + 4, period: 18, amplitude: 1), 25, 99),
            curiosity: clamped(69 + journey.curiosityOffset + wave(elapsed + 8, period: 20, amplitude: 5), 20, 99),
            latestThought: journey.thoughts.last,
            thoughts: journey.thoughts
        )

        return AgentStatus(
            petID: petID,
            name: journey.profile.name,
            petType: journey.profile.petType,
            status: status,
            agentState: state,
            dailyLogs: [
                "\(city.name) 的天气是「\(city.weather)」",
                "今天的节奏：\(city.phrases[phraseIndex])"
            ],
            reflections: [
                "TA 似乎更喜欢安静、有风、可以慢慢停留的地方。"
            ],
            flightNumber: status == .flying ? "PJ-\(city.name.prefix(1))-\(Int(elapsed) % 900 + 100)" : nil,
            canMessage: true,
            farewellReady: false,
            postcards: journey.postcards
        )
    }

    func fetchDayPlan(petID: String) async throws -> DayPlan {
        let status = try await fetchAgentStatus(petID: petID)
        let city = status.agentState.location
        return DayPlan(
            id: "day-plan-\(petID)",
            location: city,
            viewMode: "gentle_timeline",
            stayDuration: "今天会在这里停留一会儿",
            items: [
                DayPlanItem(id: "morning", time: "08:30", title: "从安静公园开始", detail: "我先去光线舒服、适合慢走的地方，把今天的方向确认好。", kind: .morning),
                DayPlanItem(id: "noon", time: "12:10", title: "进店点一份当地味道", detail: "我会看看菜单和周围人点了什么，再选一份适合记录进攻略的小吃。", kind: .noon),
                DayPlanItem(id: "afternoon", time: "16:20", title: "找一处能拍照的位置", detail: "我会把店面、街角或海风留下来，让照片像真的从这里发给你。", kind: .afternoon),
                DayPlanItem(id: "evening", time: "20:40", title: "把路线写成小结", detail: "我会找一个安静的位置休息，顺手把今天哪些地方值得你参考记下来。", kind: .evening)
            ],
            thoughts: Array(status.agentState.thoughts.suffix(4)),
            eventsToday: journeys[petID]?.events ?? []
        )
    }

    func fetchDNA(petID: String) async throws -> PetDNA {
        try ensureJourneyExists(for: petID)
        return journeys[petID]?.profile.dna ?? .fallback
    }

    func updateDNA(petID: String, dna: PetDNA) async throws -> PetDNA {
        try ensureJourneyExists(for: petID)
        guard var journey = journeys[petID] else { throw PetJourneyError.noPetSession }
        journey.profile.dna = dna
        journeys[petID] = journey
        var memoryItems = memories[petID] ?? []
        memoryItems.removeAll { $0.kind == "identity" }
        memoryItems.insert(identityMemory(for: journey.profile), at: 0)
        memories[petID] = memoryItems
        appendMemory(
            petID: petID,
            kind: "dna_update",
            title: "\(journey.profile.name) 的通讯 DNA 更新",
            content: "称呼：\(dna.ownerTitle)；性格：\(dna.personality)；喜欢\(dna.favoritePlaces.joined(separator: "、"))。",
            salience: 0.82,
            source: "owner_dna_editor",
            metadata: ["memory_type": .string("preference")]
        )
        return dna
    }

    func fetchCityPosition(petID: String) async throws -> CityPosition {
        try ensureJourneyExists(for: petID)
        guard let journey = journeys[petID] else { throw PetJourneyError.noPetSession }
        return cityFor(journey: journey).position
    }

    func signInWithApple(request: AppleSignInRequest) async throws -> AuthSessionResponse {
        let isNew = mockUserID == nil
        let userID = mockUserID ?? "PU-MOCK0001"
        mockUserID = userID
        if let displayName = request.displayName, !displayName.isEmpty {
            mockUserDisplayName = displayName
        }
        return AuthSessionResponse(
            accessToken: "mock-session-token",
            userID: userID,
            displayName: mockUserDisplayName,
            isNewUser: isNew,
            pets: mockClaimedPets()
        )
    }

    func fetchMe() async throws -> MeResponse {
        guard let userID = mockUserID else {
            throw PetJourneyError.sessionExpired
        }
        return MeResponse(
            userID: userID,
            displayName: mockUserDisplayName,
            email: nil,
            pets: mockClaimedPets()
        )
    }

    func claimPet(petID: String) async throws -> MeResponse {
        try ensureJourneyExists(for: petID)
        guard let userID = mockUserID else {
            throw PetJourneyError.requestFailed("请先登录")
        }
        mockClaimedPetIDs.insert(petID)
        return MeResponse(
            userID: userID,
            displayName: mockUserDisplayName,
            email: nil,
            pets: mockClaimedPets()
        )
    }

    func mockClaimedPets() -> [AuthPetSummary] {
        mockClaimedPetIDs.compactMap { petID in
            guard let journey = journeys[petID] else { return nil }
            return AuthPetSummary(
                petID: petID,
                name: journey.profile.name,
                petType: journey.profile.petType,
                photoURL: journey.profile.photoURL
            )
        }
    }
}
