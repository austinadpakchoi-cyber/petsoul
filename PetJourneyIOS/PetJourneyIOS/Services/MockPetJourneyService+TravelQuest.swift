import Foundation

@MainActor
extension MockPetJourneyService {
    func fetchTravelQuests(petID: String, limit: Int) async throws -> [TravelQuest] {
        try ensureJourneyExists(for: petID)
        return Array((travelQuests[petID] ?? []).prefix(max(1, limit)))
    }

    func createTravelQuest(petID: String, request: TravelWishRequest) async throws -> TravelQuest {
        try ensureJourneyExists(for: petID)
        guard let journey = journeys[petID] else { throw PetJourneyError.noPetSession }
        let clean = request.message.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !clean.isEmpty else { throw PetJourneyError.requestFailed("先告诉 TA 想去哪里") }
        let destination = request.destination?.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty == false
            ? request.destination!
            : mockDestination(from: clean)
        let isWorldCup = clean.localizedCaseInsensitiveContains("世界杯") || clean.localizedCaseInsensitiveContains("world cup")
        let questID = "TQ-\(UUID().uuidString.prefix(8).uppercased())"
        let now = Date()
        let guide = makeMockTravelGuide(
            petName: journey.profile.name,
            ownerMessage: clean,
            destination: destination,
            isWorldCup: isWorldCup,
            now: now
        )
        let quest = TravelQuest(
            id: questID,
            petID: petID,
            questType: isWorldCup ? .worldcup : .cityTrip,
            status: .guideReady,
            currentPhase: .guideReady,
            tripType: isWorldCup ? .roundTrip : .openEnded,
            returnPolicy: .askAfterEvent,
            originAnchor: TravelAnchor(
                city: cityFor(journey: journey).name,
                placeName: "现在停留的街角",
                latitude: cityFor(journey: journey).position.latitude,
                longitude: cityFor(journey: journey).position.longitude,
                note: "这次支线旅行的出发锚点。"
            ),
            ownerMessage: clean,
            destination: destination,
            eventName: isWorldCup ? "世界杯比赛" : nil,
            preferredStartDate: request.preferredStartDate,
            autonomyDecision: "我会先把去 \(destination) 的路线和停留点想清楚，不会马上被推着出发。",
            currentPhaseMessage: "我先把去 \(destination) 的小攻略整理好了。看完以后，我再慢慢准备出发。",
            guide: guide,
            travelBag: nil,
            journeyPlan: nil,
            postEventOptions: [],
            souvenirPreview: [],
            selectedNextOptionID: nil,
            worldcupEvent: isWorldCup,
            createdAt: now,
            updatedAt: now
        )
        travelQuests[petID, default: []].insert(quest, at: 0)
        return quest
    }

    func prepareTravelQuest(petID: String, questID: String) async throws -> TravelQuest {
        try ensureJourneyExists(for: petID)
        guard var quests = travelQuests[petID],
              let index = quests.firstIndex(where: { $0.id == questID })
        else { throw PetJourneyError.requestFailed("这段旅行愿望还没有同步") }
        let quest = quests[index]
        let city = cityFor(journey: journeys[petID]!)
        let places = [
            PlaceSignal(
                id: "\(questID)-origin",
                name: city.name,
                category: "origin",
                city: city.name,
                latitude: city.position.latitude,
                longitude: city.position.longitude,
                activityHint: "出发前先休息",
                detailHint: "TA 会先把精神留好。",
                source: "mock-ios-travel-quest"
            ),
            PlaceSignal(
                id: "\(questID)-destination",
                name: quest.destination,
                category: quest.worldcupEvent ? "stadium" : "place",
                city: quest.destination,
                latitude: city.position.latitude + 0.18,
                longitude: city.position.longitude + 0.24,
                activityHint: "抵达后先找安静位置",
                detailHint: "TA 不会一下钻进人群。",
                source: "mock-ios-travel-quest"
            )
        ]
        let plan = JourneyPlan(
            petID: petID,
            city: quest.destination,
            generatedAt: Date(),
            provider: "mock-ios-travel-quest",
            horizonHours: 48,
            summary: "我准备从 \(city.name) 出发，先去 \(quest.destination) 看看。",
            currentActivity: "检查小包和路线",
            transportDecision: TransportDecision(
                selectedMode: quest.worldcupEvent ? .flight : .train,
                reason: "我会先按真实距离选择长途交通，到了当地再慢慢走。",
                rejectedModes: [.walk],
                autonomyNote: "这是我接受建议后自己的出发计划。"
            ),
            routeSegments: [
                RouteSegment(
                    id: "\(questID)-long-route",
                    mode: quest.worldcupEvent ? .flight : .train,
                    title: "前往目的地",
                    detail: "这段路会按现实交通时间推进。",
                    fromPlace: city.name,
                    toPlace: quest.destination,
                    distanceMeters: nil,
                    durationSeconds: nil,
                    provider: "mock-ios-travel-quest",
                    polyline: nil,
                    startTime: Date().addingTimeInterval(3_600),
                    endTime: Date().addingTimeInterval(18_000),
                    isSimulated: true
                )
            ],
            stops: [
                ItineraryStop(
                    id: "\(questID)-prep",
                    name: city.name,
                    category: "origin",
                    city: city.name,
                    latitude: city.position.latitude,
                    longitude: city.position.longitude,
                    title: "出发前先休息",
                    detail: "我会先睡够，不急着出门。",
                    plannedTime: "出发前",
                    dwellMinutes: 80,
                    postcardCandidate: false,
                    photoCandidate: false,
                    source: "mock-ios-travel-quest"
                ),
                ItineraryStop(
                    id: "\(questID)-arrival",
                    name: quest.destination,
                    category: quest.worldcupEvent ? "stadium" : "place",
                    city: quest.destination,
                    latitude: city.position.latitude + 0.18,
                    longitude: city.position.longitude + 0.24,
                    title: "把这一刻寄回来",
                    detail: "如果光和声音都刚好，我会拍一张照片给你。",
                    plannedTime: "抵达后",
                    dwellMinutes: 120,
                    postcardCandidate: true,
                    photoCandidate: true,
                    source: "mock-ios-travel-quest"
                )
            ],
            places: places,
            nextPostcardHint: "到 \(quest.destination) 后，我会寄回第一张照片。",
            worldcupEvent: quest.worldcupEvent
        )
        let updated = quest.with(status: .preparing, message: "我会先休息一下，检查路线和天气，然后慢慢出发。", journeyPlan: plan)
        quests[index] = updated
        travelQuests[petID] = quests
        return updated
    }

    func buildTravelQuestPostEventOptions(petID: String, questID: String) async throws -> TravelQuest {
        try ensureJourneyExists(for: petID)
        guard var quests = travelQuests[petID],
              let index = quests.firstIndex(where: { $0.id == questID })
        else { throw PetJourneyError.requestFailed("这段旅行愿望还没有同步") }
        let quest = quests[index]
        let origin = quest.originAnchor?.city ?? "原来的地方"
        let options = [
            TravelQuestNextOption(
                id: "return-home-anchor",
                title: "回到 \(origin)",
                decisionType: "return_to_origin",
                destination: origin,
                petVoice: "我想把这次路上的声音带回熟悉的地方，先好好睡一觉。",
                ownerVisibleReason: "支线旅行结束后可以接回主生活线。",
                transportOutline: [
                    TravelQuestTransportOutline(
                        mode: .flight,
                        fromPlace: quest.destination,
                        toPlace: origin,
                        estimatedDuration: "按真实交通时间推进",
                        realityLevel: "reference_schedule",
                        note: "先确认真实班次，再把回程时间写进路线。"
                    )
                ],
                recommended: true
            ),
            TravelQuestNextOption(
                id: "stay-one-more-day",
                title: "多待一天",
                decisionType: "stay_local",
                destination: quest.destination,
                petVoice: "我还有一点舍不得走，想明天再找一条安静的街。",
                ownerVisibleReason: "保留当地生活感。",
                transportOutline: [],
                recommended: false
            )
        ]
        let updated = quest.with(
            status: .returnPlanning,
            message: "我先休息一下，再认真想想下一步是回去、留下，还是继续去下一座城市。",
            postEventOptions: options
        )
        quests[index] = updated
        travelQuests[petID] = quests
        return updated
    }

    func selectTravelQuestNextStep(petID: String, questID: String, request: TravelQuestDecisionRequest) async throws -> TravelQuest {
        try ensureJourneyExists(for: petID)
        guard var quests = travelQuests[petID],
              let index = quests.firstIndex(where: { $0.id == questID })
        else { throw PetJourneyError.requestFailed("这段旅行愿望还没有同步") }
        let quest = quests[index]
        let option = quest.postEventOptions.first(where: { $0.id == request.optionID }) ?? quest.postEventOptions.first
        let updated = quest.with(
            status: option?.decisionType == "return_to_origin" ? .returnTraveling : .continuedElsewhere,
            message: option?.petVoice ?? "我会自己慢慢决定下一步。",
            selectedNextOptionID: option?.id
        )
        quests[index] = updated
        travelQuests[petID] = quests
        return updated
    }
}
