import Foundation

@MainActor
final class MockPetJourneyService: PetJourneyService {
    private struct MockCity {
        var name: String
        var position: CityPosition
        var weather: String
        var phrases: [String]
        var thoughts: [String]
    }

    private struct MockSouvenirSeed {
        var itemType: SouvenirItemType
        var title: String
        var subtitle: String
        var story: String
        var petVoice: String
        var rarity: String
    }

    private struct MockJourney {
        var profile: PetProfile
        var createdAt: Date
        var lastThoughtText: String
        var thoughts: [JourneyThought]
        var events: [JourneyEvent]
        var postcards: [Postcard]
        var happinessOffset: Int
        var curiosityOffset: Int
        var energyOffset: Int
        var connectedThoughtAdded: Bool
    }

    private var journeys: [String: MockJourney] = [:]
    private var memories: [String: [MemoryRecord]] = [:]
    private var notifications: [String: [NotificationDelivery]] = [:]
    private var registeredDeviceIDs: [String: String] = [:]
    private var travelQuests: [String: [TravelQuest]] = [:]
    private var travelBags: [String: TravelBag] = [:]
    private var souvenirs: [String: [SouvenirItem]] = [:]
    private var wallets: [String: Wallet] = [:]
    private var ownerFunds: [String: OwnerFund] = [:]
    private var economyTransactions: [String: [EconomyTransaction]] = [:]
    private var communicatorMessages: [String: [CommunicatorMessage]] = [:]
    private var communicatorMoments: [String: [CommunicatorMoment]] = [:]
    // 与后端一致：同一 (petID, clientMessageID) 的重发直接回放首次响应
    private var communicatorSendReplays: [String: CommunicatorSendResponse] = [:]
    private var mockUserID: String?
    private var mockUserDisplayName: String?
    private var mockClaimedPetIDs: Set<String> = []

    private let cities: [MockCity] = [
        MockCity(
            name: "厦门",
            position: CityPosition(city: "厦门", latitude: 24.4798, longitude: 118.0894),
            weather: "海风很轻",
            phrases: ["在海边慢慢散步", "停在一条有花香的小巷", "听见远处的浪声，心情很安静"],
            thoughts: [
                "这里的风很轻，我走得很慢，像以前等你跟上来那样。",
                "刚刚在一小片草地边坐了一会儿，风从耳朵旁边慢慢过去。",
                "我今天没有走太远，只是在一个能看见海的地方晒了会儿太阳。"
            ]
        ),
        MockCity(
            name: "京都",
            position: CityPosition(city: "京都", latitude: 35.0116, longitude: 135.7681),
            weather: "薄云和木香",
            phrases: ["坐在安静的屋檐下", "沿着石板路观察行人", "在午后的光里休息"],
            thoughts: [
                "这里很安静，连脚步声都像被轻轻收好了。",
                "我找到一条窄窄的路，路边有一盏小灯，我觉得你会喜欢。",
                "今天我学会了慢一点，好像慢一点就能把想念放得更稳。"
            ]
        ),
        MockCity(
            name: "雷克雅未克",
            position: CityPosition(city: "雷克雅未克", latitude: 64.1466, longitude: -21.9426),
            weather: "冷空气里有星光",
            phrases: ["在远处看见很亮的天", "把脚印留在安静的雪边", "休息在一间暖暖的小屋旁"],
            thoughts: [
                "这里的夜很长，可是天上有光，我没有害怕。",
                "我把鼻子贴近雪地，世界安静得像一封还没写完的信。",
                "如果你也在这里，我会把最暖的位置让给你。"
            ]
        )
    ]

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

    func fetchJourneyPlan(petID: String) async throws -> JourneyPlan {
        try ensureJourneyExists(for: petID)
        guard let journey = journeys[petID] else { throw PetJourneyError.noPetSession }
        let city = cityFor(journey: journey)
        let places = mockPlaces(for: city)
        let isXiamen = city.name == "厦门"
        let routeSegments: [RouteSegment] = isXiamen ? [
            RouteSegment(
                id: "huweishan-to-bashi",
                mode: .drive,
                title: "从山边去老城",
                detail: "早上的第一段距离稍远，我会搭一小段车，不把体力都花在赶路上。",
                fromPlace: places[0].name,
                toPlace: places[1].name,
                distanceMeters: 3_900,
                durationSeconds: 1_080,
                provider: "mock-ios-multimodal-route-planner",
                polyline: nil,
                startTime: nil,
                endTime: nil,
                isSimulated: true
            ),
            RouteSegment(
                id: "bashi-to-shapowei",
                mode: .drive,
                title: "老城到老港",
                detail: "我会沿城市道路靠近沙坡尾，中途不乱穿路，也不会突然跳到海上。",
                fromPlace: places[1].name,
                toPlace: places[2].name,
                distanceMeters: 3_000,
                durationSeconds: 960,
                provider: "mock-ios-multimodal-route-planner",
                polyline: nil,
                startTime: nil,
                endTime: nil,
                isSimulated: true
            ),
            RouteSegment(
                id: "shapowei-to-baicheng",
                mode: .walk,
                title: "慢慢走向海边",
                detail: "这一段适合步行。我会沿真实道路靠近白城，边走边停下来喝水和看海。",
                fromPlace: places[2].name,
                toPlace: places[3].name,
                distanceMeters: 1_500,
                durationSeconds: 1_500,
                provider: "mock-ios-multimodal-route-planner",
                polyline: nil,
                startTime: nil,
                endTime: nil,
                isSimulated: true
            ),
            RouteSegment(
                id: "baicheng-to-bailuzhou",
                mode: .drive,
                title: "傍晚回到湖边",
                detail: "下午结束后我会搭一小段车回到筼筜湖附近，把当天收在安静的地方。",
                fromPlace: places[3].name,
                toPlace: places[4].name,
                distanceMeters: 5_600,
                durationSeconds: 1_500,
                provider: "mock-ios-multimodal-route-planner",
                polyline: nil,
                startTime: nil,
                endTime: nil,
                isSimulated: true
            )
        ] : [
            RouteSegment(
                id: "wake-to-cafe",
                mode: .walk,
                title: "沿真实道路慢慢走",
                detail: "我沿着附近的道路慢慢过去，中途会停下来闻气味、看风景。",
                fromPlace: places[0].name,
                toPlace: places[1].name,
                distanceMeters: 1_250,
                durationSeconds: 1_120,
                provider: "mock-ios-multimodal-route-planner",
                polyline: nil,
                startTime: nil,
                endTime: nil,
                isSimulated: true
            ),
            RouteSegment(
                id: "cafe-to-food",
                mode: .walk,
                title: "短距离散步",
                detail: "我绕开太吵的路段，走更安静的街边。",
                fromPlace: places[1].name,
                toPlace: places[2].name,
                distanceMeters: 760,
                durationSeconds: 680,
                provider: "mock-ios-multimodal-route-planner",
                polyline: nil,
                startTime: nil,
                endTime: nil,
                isSimulated: true
            ),
            RouteSegment(
                id: "food-to-rest",
                mode: .drive,
                title: "搭一小段车",
                detail: "距离稍远，我会搭一小段车，不让自己一直赶路。",
                fromPlace: places[2].name,
                toPlace: places[3].name,
                distanceMeters: 3_100,
                durationSeconds: 840,
                provider: "mock-ios-multimodal-route-planner",
                polyline: nil,
                startTime: nil,
                endTime: nil,
                isSimulated: true
            ),
            RouteSegment(
                id: "rest-to-postcard",
                mode: .walk,
                title: "傍晚再慢慢走一段",
                detail: "休息够了再出发，我慢慢走向今天最后一段风。",
                fromPlace: places[3].name,
                toPlace: places[4].name,
                distanceMeters: 900,
                durationSeconds: 820,
                provider: "mock-ios-multimodal-route-planner",
                polyline: nil,
                startTime: nil,
                endTime: nil,
                isSimulated: true
            )
        ]
        let stops: [ItineraryStop] = isXiamen ? [
            itineraryStop(places[0], title: "在高一点的地方醒来", detail: "我想先去高一点、绿一点的地方。风从山海健康步道吹过来，我会慢慢把今天的方向想清楚。", plannedTime: "07:40", dwellMinutes: 45),
            itineraryStop(places[1], title: "走进老城的人间烟火", detail: "我会沿着八市和开禾路慢慢看，听摊位的声音，选一口厦门早午间的本地味道。", plannedTime: "09:20", dwellMinutes: 65, photoCandidate: true),
            itineraryStop(places[2], title: "在老港边慢慢逛", detail: "这里有海风、旧港和小店。我会在大学路附近找个不挡路的位置，坐下来把看到的颜色记住。", plannedTime: "11:10", dwellMinutes: 90, photoCandidate: true),
            itineraryStop(places[3], title: "去海边收下午的风", detail: "下午我会靠近环岛路和白城沙滩，走慢一点，把海面、树影和路边的光记进手机。", plannedTime: "14:30", dwellMinutes: 85, photoCandidate: true),
            itineraryStop(places[4], title: "傍晚写一封小信", detail: "天色变软以后，我会回到白鹭洲和筼筜湖边，让脚步慢下来，把今天写成一封小小的信。", plannedTime: "17:40", dwellMinutes: 50, postcardCandidate: true)
        ] : [
            itineraryStop(places[0], title: "醒来和确认方向", detail: "我先在这里听一会儿风和声音，慢慢醒过来。", plannedTime: "07:40", dwellMinutes: 55),
            itineraryStop(places[1], title: "靠窗喝一会儿", detail: "人不多，光线也软，我会进到靠窗的小桌边，点一杯店里的招牌饮品。", plannedTime: "09:40", dwellMinutes: 70),
            itineraryStop(places[2], title: "进店吃一份当地味道", detail: "中午我会看看菜单和周围人点了什么，再选一份适合记录进攻略的小吃。", plannedTime: "12:30", dwellMinutes: 50),
            itineraryStop(places[3], title: "安静室内停留", detail: "下午我会找一个不吵的位置待久一点，让脚步慢下来。", plannedTime: "15:20", dwellMinutes: 90, photoCandidate: true),
            itineraryStop(places[4], title: "傍晚生活点停留", detail: "天色变软以后，我会在这里多待一会儿，把今天记成一张小小的信。", plannedTime: "18:40", dwellMinutes: 55, postcardCandidate: true)
        ]
        return JourneyPlan(
            petID: petID,
            city: city.name,
            generatedAt: Date(),
            provider: "mock-ios-multimodal-route-planner",
            horizonHours: 24,
            summary: isXiamen
                ? "\(journey.profile.name) 今天想从山上的风开始，走进厦门老城，再到海边和湖边慢慢收尾。"
                : "\(journey.profile.name) 今天会在 \(city.name) 走走停停，像认真生活一样选择路线。",
            currentActivity: places[0].activityHint,
            transportDecision: TransportDecision(
                selectedMode: .walk,
                reason: isXiamen
                    ? "今天的主线是山海、老城和海边。近的路段慢慢走，远一点就搭短途车，让体力留给真正想停的地方。"
                    : "我今天想靠脚步认识这座城市。短路段慢慢走，远一点就休息或搭车。",
                rejectedModes: [.flight, .train],
                autonomyNote: "这是我的节奏，不是别人替我安排好的路线。"
            ),
            routeSegments: routeSegments,
            stops: stops,
            places: places,
            nextPostcardHint: "傍晚到 \(places[4].name) 时，我会把今天最安静的一幕寄回来。",
            worldcupEvent: false
        )
    }

    func fetchWorldSnapshot(petID: String) async throws -> WorldSimulationSnapshot {
        let status = try await fetchAgentStatus(petID: petID)
        let plan = try await fetchJourneyPlan(petID: petID)
        let now = Date()
        let fallbackStop = plan.stops.first ?? ItineraryStop(
            id: "mock-world-rest",
            name: plan.city,
            category: "city",
            city: plan.city,
            latitude: CityPosition.xiamen.latitude,
            longitude: CityPosition.xiamen.longitude,
            title: "安静待着",
            detail: "TA 还在附近慢慢观察，暂时没有决定下一站。",
            plannedTime: nil,
            dwellMinutes: 30,
            postcardCandidate: false,
            photoCandidate: false,
            source: "mock-ios-world-simulation"
        )
        let timeline = mockTimeline(for: plan, now: now)
        let currentItem = timeline.first(where: \.isCurrent)
        let nextStop = mockNextStop(in: plan.stops, now: now)
        let activeStop = mockCurrentStop(in: plan.stops, currentItem: currentItem, nextStop: nextStop) ?? fallbackStop
        let isRestingBeforeNext = currentItem == nil && nextStop != nil
        let activityTitle = currentItem?.title ?? (isRestingBeforeNext ? "\(journeys[petID]?.profile.name ?? "TA") 正在休息，等今天慢慢开始" : activeStop.title)
        let activityDetail = currentItem?.detail ?? (isRestingBeforeNext ? "TA 还没有出发去 \(nextStop?.name ?? "下一站")，现在先在 \(activeStop.name) 附近安静待着。" : activeStop.detail)
        let activityKind = currentItem?.kind ?? (isRestingBeforeNext ? "rest" : "stop")
        let activityStatus: JourneyStatus = {
            if activityKind == "movement" { return .walking }
            if activityKind == "rest" { return .resting }
            return status.status
        }()
        let currentActivity = WorldActivity(
            id: currentItem?.id ?? (isRestingBeforeNext ? "mock-rest-before-\(nextStop?.id ?? activeStop.id)" : activeStop.id),
            kind: activityKind,
            status: activityStatus,
            title: activityTitle,
            detail: activityDetail,
            city: activeStop.city,
            placeName: activeStop.name,
            latitude: currentItem?.latitude ?? activeStop.latitude,
            longitude: currentItem?.longitude ?? activeStop.longitude,
            mode: currentItem?.mode ?? .stay,
            startedAt: currentItem?.plannedStart,
            endsAt: currentItem?.plannedEnd,
            progress: currentItem?.progress ?? 0,
            dwellMinutes: activeStop.dwellMinutes,
            nextPlaceName: nextStop?.name,
            iconHint: activityKind == "rest" ? "moon" : "mappin",
            canGeneratePhoto: activeStop.photoCandidate,
            canSendPostcard: activeStop.postcardCandidate,
            source: activeStop.source,
            currentTransportID: nil
        )
        return WorldSimulationSnapshot(
            petID: petID,
            city: plan.city,
            generatedAt: now,
            provider: "mock-ios-world-simulation-engine",
            elapsedSeconds: max(0, Int(now.timeIntervalSince(journeys[petID]?.createdAt ?? now))),
            travelDay: status.agentState.travelDay,
            weather: status.agentState.weather,
            status: status.status,
            statusNote: status.agentState.statusNote,
            energy: status.agentState.energy,
            happiness: status.agentState.happiness,
            curiosity: status.agentState.curiosity,
            currentActivity: currentActivity,
            activeTransport: nil,
            nextStop: nextStop,
            timeline: timeline,
            rules: [
                "真实世界原则：长距离移动必须有交通方式，不瞬移。",
                "时间流逝原则：停留、候车、飞行和散步都按真实时间推进。",
                "自主性原则：用户可以收藏或参考攻略，但不能决定 TA 喜不喜欢哪里。"
            ]
        )
    }

    private func mockTimeline(for plan: JourneyPlan, now: Date) -> [WorldTimelineItem] {
        plan.stops.enumerated().map { index, stop in
            let start = mockPlannedDate(stop.plannedTime, index: index, now: now)
            let end = start.addingTimeInterval(TimeInterval(max(10, stop.dwellMinutes) * 60))
            let isCurrent = start <= now && now < end
            let progress = max(0, min(1, now.timeIntervalSince(start) / max(1, end.timeIntervalSince(start))))
            return WorldTimelineItem(
                id: stop.id,
                kind: "stop",
                title: stop.title,
                detail: stop.detail,
                city: stop.city,
                placeName: stop.name,
                latitude: stop.latitude,
                longitude: stop.longitude,
                mode: .stay,
                plannedStart: start,
                plannedEnd: end,
                progress: isCurrent ? progress : 0,
                isCurrent: isCurrent
            )
        }
    }

    private func mockCurrentStop(
        in stops: [ItineraryStop],
        currentItem: WorldTimelineItem?,
        nextStop: ItineraryStop?
    ) -> ItineraryStop? {
        if let currentItem, let stop = stops.first(where: { $0.id == currentItem.id }) {
            return stop
        }
        guard let nextStop, !stops.isEmpty else {
            return stops.last
        }
        guard let index = stops.firstIndex(where: { $0.id == nextStop.id }) else {
            return stops.last
        }
        return index == 0 ? stops.last : stops[index - 1]
    }

    private func mockNextStop(in stops: [ItineraryStop], now: Date) -> ItineraryStop? {
        for (index, stop) in stops.enumerated() {
            if mockPlannedDate(stop.plannedTime, index: index, now: now) > now {
                return stop
            }
        }
        return nil
    }

    private func mockPlannedDate(_ raw: String?, index: Int, now: Date) -> Date {
        let calendar = Calendar.current
        let dayStart = calendar.startOfDay(for: now)
        if
            let raw,
            let separator = raw.firstIndex(of: ":"),
            let hour = Int(raw[..<separator]),
            let minute = Int(raw[raw.index(after: separator)...]),
            let date = calendar.date(bySettingHour: hour, minute: minute, second: 0, of: dayStart)
        {
            return date
        }
        return dayStart.addingTimeInterval(TimeInterval((8 + index * 2) * 3_600))
    }

    func fetchPetGuide(petID: String) async throws -> PetAuthoredGuide {
        let plan = try await fetchJourneyPlan(petID: petID)
        let stops = plan.places.prefix(4).enumerated().map { index, place in
            PetGuideStop(
                id: "mock-guide-\(index)-\(place.id)",
                placeID: place.id,
                name: place.name,
                category: place.category,
                city: place.city,
                latitude: place.latitude,
                longitude: place.longitude,
                plannedTime: ["09:30", "12:20", "15:10", "18:30"][index],
                dwellMinutes: index == 0 ? 45 : 35,
                petReason: place.activityHint,
                ownerTip: place.guideReason ?? place.detailHint,
                rating: place.rating,
                photoURL: place.photoURL,
                distanceMeters: place.distanceMeters,
                guideScore: place.guideScore,
                source: place.source
            )
        }
        let profile = journeys[petID]?.profile
        let petType = profile?.petType ?? .dog
        return PetAuthoredGuide(
            petID: petID,
            city: plan.city,
            generatedAt: Date(),
            provider: "mock-ios-pet-guide-brain",
            model: "gpt-5.5",
            title: "\(profile?.name ?? "TA")的\(plan.city)慢游攻略",
            animalText: petType.vocalization(for: "guide_saved"),
            translation: "我想先替你在\(plan.city)慢慢走一遍，不赶路。哪里有舒服的光、好闻的味道，或者值得停久一点的小店，我都会记下来。以后有机会，你也可以来看看。",
            languageStyle: petType.languageStyle,
            routeTheme: "先找安静的光，再找一点好闻的味道",
            mood: "慢慢探索",
            guideStops: stops,
            scheduledTransport: plan.scheduledTransport,
            sourcePlacesCount: plan.places.count,
            autonomyNote: "这是 TA 自己想走的攻略，你可以参考，但不用命令 TA 照做。"
        )
    }

    func fetchIllustratedGuide(petID: String) async throws -> IllustratedGuide {
        let plan = try await fetchJourneyPlan(petID: petID)
        let guide = try await fetchPetGuide(petID: petID)
        let dateFormatter = DateFormatter()
        dateFormatter.calendar = Calendar(identifier: .gregorian)
        dateFormatter.locale = Locale(identifier: "zh_CN")
        dateFormatter.dateFormat = "yyyy-MM-dd"
        let petName = journeys[petID]?.profile.name ?? "TA"
        let stops = guide.guideStops.prefix(5).enumerated().map { index, stop in
            IllustratedGuideStop(
                index: index + 1,
                time: stop.plannedTime,
                name: stop.name,
                label: mockIllustratedGuideLabel(for: stop.category, name: stop.name),
                shortNote: mockUserFacingText(stop.petReason),
                category: stop.category
            )
        }

        return IllustratedGuide(
            id: "mock-illustrated-\(petID)-\(dateFormatter.string(from: plan.generatedAt))",
            petID: petID,
            city: plan.city,
            date: dateFormatter.string(from: plan.generatedAt),
            status: .promptReady,
            title: "\(petName)的\(plan.city)手绘小旅程",
            theme: mockUserFacingText(guide.routeTheme),
            petName: petName,
            petThought: "我先把今天的路线拆成几页小手账。以后你也可以沿着这些地方慢慢走一遍。",
            stops: stops,
            style: "loose_handdrawn_travel_journal",
            styleID: "warm_travel_journal",
            styleName: "温柔手账风",
            stylePackVersion: "2026-07-04-mvp1",
            styleLocked: true,
            layoutMode: "multi_page_sketchbook",
            pages: mockIllustratedGuidePages(petName: petName, city: plan.city, stops: stops),
            sourceItineraryID: plan.petID,
            imagePrompt: "Mock prompt for a loose hand-drawn PetSoul travel sketchbook page.",
            imageURL: nil,
            thumbnailURL: nil,
            provider: "mock-ios-illustrated-guide",
            model: nil,
            errorMessage: nil,
            createdAt: Date()
        )
    }

    private func mockIllustratedGuideLabel(for category: String, name: String) -> String {
        if name.contains("八市") || name.contains("开禾") {
            return "老城味道"
        }
        if name.contains("海") || name.contains("沙滩") || name.contains("环岛路") {
            return "海边停留"
        }
        if name.contains("咖啡") || category == "cafe" {
            return "小店休息"
        }
        if category == "park" {
            return "安静散步"
        }
        if category == "food" {
            return "本地小吃"
        }
        return "今日停靠"
    }

    private func mockUserFacingText(_ value: String) -> String {
        var text = value
        let replacements = [
            ("适合攻略型打卡，但不强迫 TA 喜欢这里。", "这里有真实的本地味道，TA 可以进去看看，再把感受记下来。"),
            ("适合攻略型打卡，但不强迫 TA 喜欢这里", "这里有真实的本地味道，TA 可以进去看看，再把感受记下来"),
            ("不强迫 TA 喜欢这里", "TA 只是按自己的节奏停一会儿"),
            ("攻略型打卡", "旅程记录"),
            ("打卡", "停留"),
            ("可能会", "会"),
            ("可能", "")
        ]
        for (source, target) in replacements {
            text = text.replacingOccurrences(of: source, with: target)
        }
        return text
            .replacingOccurrences(of: "  ", with: " ")
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }

    func generateIllustratedGuide(petID: String) async throws -> IllustratedGuide {
        try await fetchIllustratedGuide(petID: petID)
    }

    private func mockIllustratedGuidePages(
        petName: String,
        city: String,
        stops: [IllustratedGuideStop]
    ) -> [IllustratedGuidePage] {
        [
            IllustratedGuidePage(
                index: 1,
                title: "手账封面",
                subtitle: "\(petName)在\(city)慢慢生活的一天",
                intent: "像线圈本第一页，先把城市和今天的主题讲清楚",
                pageType: "cover",
                templateID: "spiral_cover_overview",
                visualStyle: "线圈手账封面，水彩插画，贴纸和便签",
                composition: "cover_overview",
                styleID: "warm_travel_journal",
                styleName: "温柔手账风",
                imagePrompt: "Spiral-bound hand-drawn Chinese travel notebook cover page for \(petName) in \(city).",
                imageURL: nil,
                thumbnailURL: nil,
                status: .promptReady
            ),
            IllustratedGuidePage(
                index: 2,
                title: "今日旅程图",
                subtitle: "\(city) · \(stops.count) 站串联",
                intent: "像手绘地图一样，让你一眼看懂 TA 怎么慢慢走过这座城",
                pageType: "route_map",
                templateID: "winding_route_map",
                visualStyle: "蜿蜒虚线路线，地点小插画，手写时间标签",
                composition: "route_map",
                styleID: "warm_travel_journal",
                styleName: "温柔手账风",
                imagePrompt: "Hand-drawn winding route map page with watercolor stop thumbnails for \(petName) in \(city).",
                imageURL: nil,
                thumbnailURL: nil,
                status: .promptReady
            ),
            IllustratedGuidePage(
                index: 3,
                title: "时间线手账",
                subtitle: "把慢慢走的一天摊开来看",
                intent: "像日记时间轴，按时间记录 TA 在每一站停下来做了什么",
                pageType: "timeline",
                templateID: "vertical_timeline_journal",
                visualStyle: "竖向时间线，小圆图，手写短句",
                composition: "timeline",
                styleID: "warm_travel_journal",
                styleName: "温柔手账风",
                imagePrompt: "Vertical hand-drawn timeline journal page with small circular watercolor sketches.",
                imageURL: nil,
                thumbnailURL: nil,
                status: .promptReady
            )
        ]
    }

    func fetchRoutePlan(petID: String) async throws -> RemoteJourneyRoutePlan {
        let journeyPlan = try await fetchJourneyPlan(petID: petID)
        return journeyPlan.compatibilityRoutePlan
    }

    func fetchPhotoMission(petID: String) async throws -> PhotoMission {
        try ensureJourneyExists(for: petID)
        guard let journey = journeys[petID] else { throw PetJourneyError.noPetSession }
        let plan = try await fetchJourneyPlan(petID: petID)
        let place = plan.places.first(where: { $0.category == "netcafe" }) ?? plan.places.first ?? PlaceSignal(
            id: "mock-place",
            name: plan.city,
            category: "place",
            city: plan.city,
            latitude: CityPosition.xiamen.latitude,
            longitude: CityPosition.xiamen.longitude,
            activityHint: "安静地停留了一会儿",
            detailHint: "TA 正在附近找一个舒服的位置",
            source: "mock-ios-place-interaction"
        )
        let interaction = PlaceInteraction(
            id: "mock-interaction-\(petID)-\(place.id)",
            petID: petID,
            place: place,
            interactionType: "indoor_screen_light_stop",
            title: "在 \(place.name) 的屏幕光里待了一会儿",
            detail: "\(journey.profile.name) 正在 \(place.name) 附近坐着，像陪别人打一局游戏。",
            petAction: "在屏幕光和键盘声旁边坐了一会儿，像陪别人打一局游戏",
            emotionalTone: "陪伴感、屏幕光、轻轻的冒险",
            dwellMinutes: 35,
            canGeneratePhoto: true,
            source: "mock-ios-place-interaction"
        )
        return PhotoMission(
            id: "mock-photo-\(petID)-\(place.id)",
            petID: petID,
            generatedAt: Date(),
            provider: "mock-ios-place-interaction",
            city: place.city,
            place: place,
            interaction: interaction,
            cameraPerspective: .firstPersonSelfie,
            sceneAnchor: "\(place.city) · \(place.name)",
            landmarkHints: ["真实地点附近的街巷", "低角度手机视角"],
            localDetailHints: ["pet face close to lens", "one paw in foreground", "screen glow", "keyboard", "drink cup"],
            crowdHints: [],
            weather: "室内有蓝色的灯，外面应该还是温暖的",
            timeOfDay: "afternoon",
            imagePrompt: "PetSoul parallel-world first-person pet selfie from TA's own phone near \(place.name). Preserve the exact pet identity from the reference photo by redrawing a complete natural new image, not a cutout or pasted sticker. Close pet face or paw in the foreground, low handheld angle, slightly imperfect framing, screen glow, keyboard, drink cup, real local background behind, warm emotional phone-photo style, no visible text, no logo, no watermark.",
            postcardText: "我把手机举得低低的，在 \(place.name) 把这一刻留下来了。这里有键盘声和一点点像冒险的光。",
            safetyNotes: ["Preserve pet identity", "No official logos or readable brand marks"]
        )
    }

    func fetchCredentialPrompts(petID: String) async throws -> [PetCredentialPrompt] {
        try ensureJourneyExists(for: petID)
        guard let journey = journeys[petID] else { throw PetJourneyError.noPetSession }
        let name = journey.profile.name
        let serialSeed = String(petID.replacingOccurrences(of: "-", with: "").prefix(6)).uppercased()
        return [
            PetCredentialPrompt(
                kind: .identity,
                title: "PetSoul 居民证",
                subtitle: "\(name) 在平行世界的身份",
                serial: "PS-\(serialSeed)-ID",
                imagePrompt: "PetSoul parallel-world resident card for \(name), warm paper texture, no readable logos",
                size: "1536x1024",
                referenceRoles: ["pet_photo"],
                safetyNotes: ["Preserve pet identity"],
                fields: ["姓名": name, "身份": "平行世界旅行者"]
            ),
            PetCredentialPrompt(
                kind: .healthRecord,
                title: "健康小手册",
                subtitle: "TA 在旅途中的元气记录",
                serial: "PS-\(serialSeed)-HR",
                imagePrompt: "PetSoul travel health booklet for \(name), soft illustration, no readable logos",
                size: "1536x1024",
                referenceRoles: ["pet_photo"],
                safetyNotes: ["Preserve pet identity"],
                fields: ["元气": "很好", "最近一次休息": "昨晚睡得很沉"]
            )
        ]
    }

    func fetchStreetRank(petID: String, theme: String) async throws -> StreetRankResponse {
        try ensureJourneyExists(for: petID)
        let plan = try await fetchJourneyPlan(petID: petID)
        let items = plan.places.prefix(3).enumerated().map { index, place in
            StreetRankItem(
                rank: index + 1,
                place: place,
                rankScore: 96 - Double(index) * 7,
                reason: "这条街上，TA 现在最想先去的位置。",
                petAction: "打算先在门口闻一闻，再决定进不进去。",
                ownerTip: "TA 逛到这里时，多半会想把见闻讲给你听。",
                weatherNote: "现在的天气正适合慢慢逛。"
            )
        }
        return StreetRankResponse(
            petID: petID,
            city: plan.city,
            theme: theme,
            generatedAt: Date(),
            provider: "mock-ios-street-rank",
            weather: "晴",
            items: Array(items),
            sourceNotes: ["示例数据，用于离线预览"]
        )
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

    private func mockClaimedPets() -> [AuthPetSummary] {
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

    func fetchSouvenirs(petID: String, limit: Int) async throws -> [SouvenirItem] {
        try ensureJourneyExists(for: petID)
        return Array((souvenirs[petID] ?? []).prefix(max(1, limit)))
    }

    func fetchEconomy(petID: String) async throws -> EconomyResponse {
        try ensureJourneyExists(for: petID)
        return mockEconomyResponse(petID: petID)
    }

    func fetchInventory(petID: String, status: ItemStatus?, limit: Int) async throws -> InventoryResponse {
        try ensureJourneyExists(for: petID)
        let filtered = (souvenirs[petID] ?? [])
            .filter { status == nil || $0.effectiveStatus == status }
            .prefix(max(1, limit))
        return InventoryResponse(items: Array(filtered), snapshot: mockSnapshot(petID: petID))
    }

    func collectTravelQuestSouvenirsWithEconomy(petID: String, questID: String) async throws -> CollectSouvenirsResponse {
        try ensureJourneyExists(for: petID)
        let idempotencyKey = "collect_souvenirs:\(petID):\(questID)"
        if let existing = souvenirs[petID]?.filter({ $0.questID == questID }), !existing.isEmpty {
            let transaction = mockExistingTransaction(petID: petID, idempotencyKey: idempotencyKey)
            return CollectSouvenirsResponse(
                items: existing,
                transactions: transaction.map { [$0] } ?? [],
                wallet: mockWallet(petID: petID),
                snapshot: mockSnapshot(petID: petID)
            )
        }
        let quest = travelQuests[petID]?.first(where: { $0.id == questID })
        let destination = quest?.destination ?? "远方"
        let placeName = quest?.guide?.stops.last?.name ?? destination
        let now = Date()
        let seeds = mockSouvenirSeeds(
            destination: destination,
            placeName: placeName,
            isWorldCup: quest?.worldcupEvent == true,
            bag: quest?.travelBag
        )
        let generated = seeds.enumerated().map { index, seed in
            let marketValue = mockMarketValue(for: seed)
            let itemID = "SV-\(questID.suffix(6).uppercased())-\(index)"
            return SouvenirItem(
                id: itemID,
                petID: petID,
                questID: questID,
                templateID: "mock_\(questID)_\(index)",
                itemType: seed.itemType,
                title: seed.title,
                subtitle: seed.subtitle,
                city: destination,
                placeName: placeName,
                story: seed.story,
                petVoice: seed.petVoice,
                imagePrompt: mockSouvenirImagePrompt(seed: seed, destination: destination, placeName: placeName, isWorldCup: quest?.worldcupEvent == true),
                rarity: seed.rarity,
                obtainedAt: now.addingTimeInterval(TimeInterval(index * 60)),
                source: "mock-ios-souvenir",
                status: .owned,
                version: 1,
                tradePolicy: .tradable,
                lockUntil: nil,
                marketValue: marketValue,
                emotionalValue: marketValue * 2 + 24,
                honorValue: 0,
                valueBreakdown: [
                    "base": .number(Double(mockBaseValue(for: seed.itemType))),
                    "rarity_multiplier": .number(mockRarityMultiplier(seed.rarity)),
                    "source_multiplier": .number(1.4),
                    "condition_multiplier": .number(0.96),
                    "story_bonus": .number(1.05),
                    "final_market_value": .number(Double(marketValue))
                ],
                acquireSource: .questReward,
                originEventID: "quest:\(questID):mock_\(index)",
                originActivityID: "quest-stop:\(quest?.guide?.stops.last?.id ?? questID)",
                originActivityType: "travel_quest_stop",
                originPOIName: placeName,
                originCity: destination,
                originWeather: nil,
                originCoords: [],
                updatedAt: now
            )
        }
        souvenirs[petID, default: []].insert(contentsOf: generated, at: 0)
        let transaction = mockTransaction(
            petID: petID,
            type: .itemAcquired,
            idempotencyKey: idempotencyKey,
            amounts: CurrencyAmounts(travelCoin: 0, starDust: 0, merit: 0),
            itemIDs: generated.map(\.id),
            reason: "从 \(destination) 带回 \(generated.count) 件小收藏",
            source: "mock_collect",
            operatorName: "pet"
        )
        economyTransactions[petID, default: []].insert(transaction, at: 0)
        return CollectSouvenirsResponse(
            items: generated,
            transactions: [transaction],
            wallet: mockWallet(petID: petID),
            snapshot: mockSnapshot(petID: petID)
        )
    }

    func collectTravelQuestSouvenirs(petID: String, questID: String) async throws -> [SouvenirItem] {
        try await collectTravelQuestSouvenirsWithEconomy(petID: petID, questID: questID).items
    }

    func sellItem(petID: String, itemID: String, request: SellItemRequest) async throws -> ItemMutationResponse {
        try ensureJourneyExists(for: petID)
        guard var item = souvenirs[petID]?.first(where: { $0.id == itemID }) else {
            throw PetJourneyError.requestFailed("没有找到这件小收藏")
        }
        let idempotencyKey = "sell_item:\(petID):\(itemID):\(request.clientRequestID)"
        if let existing = mockExistingTransaction(petID: petID, idempotencyKey: idempotencyKey) {
            return ItemMutationResponse(success: true, transaction: existing, wallet: mockWallet(petID: petID), item: item, snapshot: mockSnapshot(petID: petID))
        }
        guard item.effectiveVersion == request.expectedItemVersion, item.isSellable else {
            throw PetJourneyError.requestFailed("这件小收藏暂时不能出售")
        }
        let value = item.resaleValue
        var wallet = mockWallet(petID: petID)
        wallet.travelCoin += value
        wallet.updatedAt = Date()
        wallets[petID] = wallet
        item.status = .sold
        item.version = item.effectiveVersion + 1
        item.updatedAt = Date()
        replaceSouvenir(item, petID: petID)
        let transaction = mockTransaction(
            petID: petID,
            type: .itemSold,
            idempotencyKey: idempotencyKey,
            amounts: CurrencyAmounts(travelCoin: value, starDust: 0, merit: 0),
            itemIDs: [item.id],
            reason: "出售\(item.title)",
            source: "mock_sell",
            operatorName: "pet"
        )
        economyTransactions[petID, default: []].insert(transaction, at: 0)
        return ItemMutationResponse(success: true, transaction: transaction, wallet: wallet, item: item, snapshot: mockSnapshot(petID: petID))
    }

    func archiveItem(petID: String, itemID: String, request: ArchiveItemRequest) async throws -> ItemMutationResponse {
        try ensureJourneyExists(for: petID)
        guard var item = souvenirs[petID]?.first(where: { $0.id == itemID }) else {
            throw PetJourneyError.requestFailed("没有找到这件小收藏")
        }
        let idempotencyKey = "archive_item:\(petID):\(itemID):\(request.clientRequestID)"
        if let existing = mockExistingTransaction(petID: petID, idempotencyKey: idempotencyKey) {
            return ItemMutationResponse(success: true, transaction: existing, wallet: mockWallet(petID: petID), item: item, snapshot: mockSnapshot(petID: petID))
        }
        guard item.effectiveVersion == request.expectedItemVersion, item.effectiveStatus == .owned else {
            throw PetJourneyError.requestFailed("这件小收藏暂时不能归档")
        }
        item.status = .archived
        item.version = item.effectiveVersion + 1
        item.updatedAt = Date()
        replaceSouvenir(item, petID: petID)
        let transaction = mockTransaction(
            petID: petID,
            type: .itemArchived,
            idempotencyKey: idempotencyKey,
            amounts: CurrencyAmounts(travelCoin: 0, starDust: 0, merit: 0),
            itemIDs: [item.id],
            reason: "归档\(item.title)",
            source: "mock_archive",
            operatorName: "owner"
        )
        economyTransactions[petID, default: []].insert(transaction, at: 0)
        return ItemMutationResponse(success: true, transaction: transaction, wallet: mockWallet(petID: petID), item: item, snapshot: mockSnapshot(petID: petID))
    }

    func fetchThoughtTranslation(petID: String, thoughtID: String) async throws -> ThoughtTranslation {
        try ensureJourneyExists(for: petID)
        guard let journey = journeys[petID],
              let thought = journey.thoughts.first(where: { $0.id == thoughtID }),
              let translation = thought.translation
        else {
            throw PetJourneyError.requestFailed("这句话还没有翻译出来")
        }
        return ThoughtTranslation(
            thoughtID: thought.id,
            petID: petID,
            animalText: thought.animalText ?? thought.text,
            translation: translation,
            tone: thought.tone,
            languageStyle: thought.languageStyle,
            model: thought.model
        )
    }

    func sendFeedback(_ request: FeedbackRequest) async throws -> FeedbackResponse {
        try ensureJourneyExists(for: request.petID)
        guard var journey = journeys[request.petID] else { throw PetJourneyError.noPetSession }

        let text: String
        let tone: String
        if request.liked {
            tone = "guide_saved"
            text = "已为你收藏这段攻略。\(journey.profile.name) 的旅程不会被打断，TA 还在按自己的节奏探索。"
        } else {
            tone = "guide_skipped"
            text = "知道了，这类攻略会少推荐给你。\(journey.profile.name) 仍然可以自己喜欢、停留或离开。"
        }

        let thought = agentThought(translation: text, tone: tone, petType: journey.profile.petType)
        journey.thoughts.append(thought)
        journey.lastThoughtText = thought.text
        journey.events.append(
            JourneyEvent(
                id: UUID().uuidString,
                title: request.liked ? "你收藏了一段攻略" : "你略过了这类攻略",
                detail: request.liked ? "这是你的旅行偏好，不会决定 TA 对这个地方的感受。" : "手机会少给你推荐类似地点，但 TA 的旅程仍然自由。",
                timestamp: Date()
            )
        )
        journeys[request.petID] = journey
        appendMemory(
            petID: request.petID,
            kind: "owner_preference",
            title: "\(request.city) 的主人反馈",
            content: text,
            salience: 0.72,
            source: "feedback",
            metadata: ["city": .string(request.city), "liked": .bool(request.liked)]
        )

        let updated = try await fetchAgentStatus(petID: request.petID)
        return FeedbackResponse(success: true, message: text, updatedStatus: updated)
    }

    func sendOwnerMessage(petID: String, request: OwnerMessageRequest) async throws -> OwnerMessageResponse {
        try ensureJourneyExists(for: petID)
        guard var journey = journeys[petID] else { throw PetJourneyError.noPetSession }
        let clean = request.message.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !clean.isEmpty else { throw PetJourneyError.requestFailed("讯息不能为空") }

        let decision: String
        let reply: String
        if clean.contains("想你") || clean.contains("晚安") || clean.contains("早安") {
            decision = "comfort"
            reply = "我听见了。它像一点暖光，被我收进手机里。"
        } else if clean.contains("去") || clean.contains("看看") || clean.contains("咖啡") || clean.contains("海") {
            let accepts = abs(clean.hashValue) % 4 != 0
            decision = accepts ? "accepted" : "declined"
            reply = accepts
                ? "我听见你的建议了。等风和路线合适的时候，我会自己决定要不要靠近看看。"
                : "我听见你的建议了。今天我先把眼前这段路慢慢走完，再自己决定下一步。"
        } else {
            decision = "remembered"
            reply = "我先把这句话记住，不急着决定，等下一段旅程再慢慢判断。"
        }

        let thought = agentThought(translation: reply, tone: "owner_message_\(decision)", petType: journey.profile.petType)
        journey.thoughts.append(thought)
        journey.lastThoughtText = thought.text
        journey.events.append(
            JourneyEvent(
                id: UUID().uuidString,
                title: "TA 收到你的讯息",
                detail: "这是一条建议或陪伴讯息，TA 会自己判断怎么回应。",
                timestamp: Date()
            )
        )
        journeys[petID] = journey
        appendMemory(
            petID: petID,
            kind: "owner_message",
            title: "你的讯息",
            content: "你说：「\(clean)」。TA 回应：\(reply)",
            salience: 0.74,
            source: "owner_message",
            metadata: ["decision": .string(decision)]
        )

        let updated = try await fetchAgentStatus(petID: petID)
        return OwnerMessageResponse(
            success: true,
            decision: decision,
            message: reply,
            thought: thought,
            updatedStatus: updated
        )
    }

    func fetchCommunicatorMessages(petID: String, limit: Int) async throws -> [CommunicatorMessage] {
        try ensureJourneyExists(for: petID)
        return Array((communicatorMessages[petID] ?? []).suffix(max(1, limit)))
    }

    func sendCommunicatorMessage(petID: String, request: CommunicatorSendRequest) async throws -> CommunicatorSendResponse {
        try ensureJourneyExists(for: petID)
        guard let journey = journeys[petID] else { throw PetJourneyError.noPetSession }
        let clean = request.text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !clean.isEmpty else { throw PetJourneyError.requestFailed("讯息不能为空") }
        if let clientID = request.clientMessageID, !clientID.isEmpty,
           let replay = communicatorSendReplays["\(petID)|\(clientID)"] {
            return replay
        }
        let city = cityFor(journey: journey)
        let now = Date()
        let intent = mockIntent(for: clean)
        let policy = mockReplyPolicy(intent: intent, message: clean, journey: journey)
        let owner = CommunicatorMessage(
            id: "msg_\(UUID().uuidString)",
            petID: petID,
            sender: .owner,
            text: clean,
            intent: intent,
            messageState: "delivered",
            replyPolicy: policy,
            attachments: [],
            relatedMessageID: nil,
            clientMessageID: request.clientMessageID,
            createdAt: now,
            updatedAt: nil
        )
        communicatorMessages[petID, default: []].append(owner)

        let attachments = mockAttachments(intent: intent, policy: policy, city: city)
        let replyText = mockCommunicatorReply(intent: intent, message: clean, city: city)
        let sender: CommunicatorSender = policy.mode.hasPrefix("queued") ? .system : .pet
        let reply = CommunicatorMessage(
            id: "msg_\(UUID().uuidString)",
            petID: petID,
            sender: sender,
            text: sender == .system ? policy.visibleStatus : replyText,
            intent: intent,
            messageState: "sent",
            replyPolicy: policy,
            attachments: attachments,
            relatedMessageID: owner.id,
            createdAt: now.addingTimeInterval(1),
            updatedAt: nil
        )
        communicatorMessages[petID, default: []].append(reply)

        if sender == .pet {
            var updatedJourney = journey
            let thought = agentThought(translation: replyText, tone: "communicator_\(intent.rawValue.lowercased())", petType: journey.profile.petType)
            updatedJourney.thoughts.append(thought)
            updatedJourney.lastThoughtText = thought.text
            journeys[petID] = updatedJourney
        }

        if intent == .currentStatusVisualRequest || intent == .photoRequest || intent == .confirmPendingPhoto {
            insertMockMomentIfNeeded(petID: petID, petName: journey.profile.name, city: city, attachments: attachments)
        }

        let response = CommunicatorSendResponse(
            success: true,
            intent: intent,
            replyPolicy: policy,
            ownerMessage: owner,
            messages: [reply],
            pendingRequest: nil
        )
        if let clientID = request.clientMessageID, !clientID.isEmpty {
            communicatorSendReplays["\(petID)|\(clientID)"] = response
        }
        return response
    }

    func sendCommunicatorPhoto(petID: String, imageData: Data, caption: String?, clientMessageID: String?) async throws -> CommunicatorSendResponse {
        try ensureJourneyExists(for: petID)
        guard let journey = journeys[petID] else { throw PetJourneyError.noPetSession }
        if let clientID = clientMessageID, !clientID.isEmpty,
           let replay = communicatorSendReplays["\(petID)|\(clientID)"] {
            return replay
        }
        let city = cityFor(journey: journey)
        let now = Date()
        let clean = caption?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        let imageURL = try persistMockCommunicatorPhoto(imageData)
        let intent = CommunicatorIntent.ownerPhotoShare
        let policy = CommunicatorReplyPolicy(
            mode: "immediate",
            estimatedReplySeconds: 6,
            visibleStatus: "TA 看到了这张照片。",
            reasonCode: "owner_photo_shared",
            shouldBatch: false,
            shouldMarkSeen: true,
            cooldownApplied: false
        )
        let ownerAttachment = CommunicatorAttachment(
            type: .ownerPhoto,
            title: "你发来的照片",
            text: clean.isEmpty ? "给 TA 看的一张照片。" : clean,
            state: "ready",
            photoURL: imageURL,
            location: nil,
            photoMissionID: nil,
            availableAfter: nil
        )
        let owner = CommunicatorMessage(
            id: "msg_\(UUID().uuidString)",
            petID: petID,
            sender: .owner,
            text: clean,
            intent: intent,
            messageState: "delivered",
            replyPolicy: policy,
            attachments: [ownerAttachment],
            relatedMessageID: nil,
            clientMessageID: clientMessageID,
            createdAt: now,
            updatedAt: nil
        )
        communicatorMessages[petID, default: []].append(owner)

        let replyText = mockOwnerPhotoReply(caption: clean, city: city)
        let reply = CommunicatorMessage(
            id: "msg_\(UUID().uuidString)",
            petID: petID,
            sender: .pet,
            text: replyText,
            intent: intent,
            messageState: "sent",
            replyPolicy: policy,
            attachments: [],
            relatedMessageID: owner.id,
            createdAt: now.addingTimeInterval(1),
            updatedAt: nil
        )
        communicatorMessages[petID, default: []].append(reply)

        var updatedJourney = journey
        let thought = agentThought(translation: replyText, tone: "communicator_owner_photo_share", petType: journey.profile.petType)
        updatedJourney.thoughts.append(thought)
        updatedJourney.lastThoughtText = thought.text
        journeys[petID] = updatedJourney

        let response = CommunicatorSendResponse(
            success: true,
            intent: intent,
            replyPolicy: policy,
            ownerMessage: owner,
            messages: [reply],
            pendingRequest: nil
        )
        if let clientID = clientMessageID, !clientID.isEmpty {
            communicatorSendReplays["\(petID)|\(clientID)"] = response
        }
        return response
    }

    func fetchMoments(petID: String, limit: Int) async throws -> [CommunicatorMoment] {
        try ensureJourneyExists(for: petID)
        guard let journey = journeys[petID] else { throw PetJourneyError.noPetSession }
        if communicatorMoments[petID]?.isEmpty != false {
            communicatorMoments[petID] = seedMoments(petID: petID, petName: journey.profile.name, city: cityFor(journey: journey))
        }
        return Array((communicatorMoments[petID] ?? []).prefix(max(1, limit)))
    }

    func reactToMoment(petID: String, momentID: String, request: MomentReactionRequest) async throws -> MomentReactionResponse {
        try ensureJourneyExists(for: petID)
        guard let index = communicatorMoments[petID]?.firstIndex(where: { $0.id == momentID }) else {
            throw PetJourneyError.requestFailed("这条朋友圈动态暂时找不到")
        }
        var moment = communicatorMoments[petID]![index]
        if let previous = moment.ownerReaction {
            moment.reactions[previous.rawValue] = max(0, (moment.reactions[previous.rawValue] ?? 0) - 1)
        }
        moment.ownerReaction = request.reaction
        moment.reactions[request.reaction.rawValue] = (moment.reactions[request.reaction.rawValue] ?? 0) + 1
        moment.updatedAt = Date()
        communicatorMoments[petID]![index] = moment
        appendMemory(
            petID: petID,
            kind: "moment_reaction",
            title: "你回应了一条朋友圈",
            content: "你对「\(moment.text)」回应了 \(request.reaction.displayName)。",
            salience: 0.56,
            source: "communicator_moment_reaction",
            metadata: ["reaction": .string(request.reaction.rawValue)]
        )
        return MomentReactionResponse(
            success: true,
            momentID: momentID,
            reaction: request.reaction,
            message: request.reaction == .paw ? "TA 好像感受到你摸了摸它。" : (request.reaction == .hug ? "TA 把这个抱抱轻轻收好了。" : "TA 好像知道你喜欢这一刻。")
        )
    }

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

    func simulateElapsedTime(_ seconds: TimeInterval, for petID: String) {
        guard var journey = journeys[petID] else { return }
        journey.createdAt = journey.createdAt.addingTimeInterval(-seconds)
        journeys[petID] = journey
    }

    private func ensureJourneyExists(for petID: String) throws {
        if journeys[petID] != nil { return }
        let profile = PetProfile(
            petID: petID,
            name: "小黑",
            petType: .dog,
            dna: .demoFrenchie,
            photoURL: MockDemoMedia.frenchieProfileURL
        )
        let thought = agentThought(
            translation: "我回到手机里了，今天也会慢慢走。",
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

    private func identityMemory(for profile: PetProfile) -> MemoryRecord {
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

    private func refreshIdentityMemory(for profile: PetProfile) {
        var items = memories[profile.petID] ?? []
        items.removeAll { $0.kind == "identity" }
        items.insert(identityMemory(for: profile), at: 0)
        memories[profile.petID] = items
    }

    private func makeMemory(
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

    private func appendMemory(
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

    private func ensureMemorySeed(petID: String, profile: PetProfile) {
        if memories[petID]?.isEmpty == false { return }
        memories[petID] = [identityMemory(for: profile)]
    }

    private func advanceJourney(petID: String) {
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

    private func appendThought(_ text: String, to journey: inout MockJourney, tone: String) {
        let thought = agentThought(translation: text, tone: tone, petType: journey.profile.petType)
        journey.thoughts.append(thought)
        journey.lastThoughtText = text
    }

    private func agentThought(translation: String, tone: String, petType: PetType) -> JourneyThought {
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

    private func animalSpeech(for tone: String, petType: PetType) -> String {
        petType.vocalization(for: tone)
    }

    private func mockPlaces(for city: MockCity) -> [PlaceSignal] {
        let places = safeMockPlaces(for: city)
        return places.map { id, name, category, latitude, longitude, activity, detail in
            PlaceSignal(
                id: "\(city.name)-\(id)",
                name: name,
                category: category,
                city: city.name,
                latitude: latitude,
                longitude: longitude,
                activityHint: activity,
                detailHint: detail,
                source: "mock-ios-route-provider"
            )
        }
    }

    private func safeMockPlaces(for city: MockCity) -> [(String, String, String, Double, Double, String, String)] {
        switch city.name {
        case "厦门":
            [
                ("huweishan-walkway", "狐尾山 / 山海健康步道", "park", 24.4874, 118.0847, "在狐尾山的风里慢慢醒来，看见厦门从高处亮起来", "高处、绿意和城市边界都很清楚，适合作为一日路线的开场。"),
                ("bashi-kaihe-food", "八市 / 开禾路老街", "food", 24.4579, 118.0739, "走进八市和开禾路的人间烟火里，看摊位、听声音、选一口本地味道", "老城市场和本地小吃让路线有厦门记忆点，适合作为早午间核心停靠。"),
                ("shapowei-daxue-road", "沙坡尾 / 大学路", "place", 24.4386, 118.0930, "在沙坡尾和大学路慢慢逛，听海风钻进巷子里", "老港、巷子、小店和海风都有画面感，适合照片、明信片和慢逛。"),
                ("baicheng-beach-ring-road", "环岛路 / 白城沙滩", "park", 24.4319, 118.1036, "下午沿环岛路靠近白城沙滩，把海风记进手机", "海边和环岛路是厦门很强的城市标签，适合作为下午的核心照片点。"),
                ("bailuzhou-yundang-lake", "白鹭洲 / 筼筜湖", "park", 24.4772, 118.0961, "傍晚在白鹭洲和筼筜湖边慢下来，写一封小小的信", "傍晚湖面、城市灯和安静步道适合作为当天收束与明信片候选点。"),
                ("zhongshan-road-cafe-window", "中山路骑楼咖啡窗口", "cafe", 24.4570, 118.0806, "在骑楼边的小咖啡窗口喝一杯店里的特色饮品", "这是可选休息点，不抢主线，只在 TA 需要补给或躲雨时出现。"),
                ("local-supply-stop", "老城补给小店", "shop", 24.4592, 118.0786, "在老城小店里挑一件路上用得上的小东西", "隐藏补给点，不作为核心攻略站。")
            ]
        case "京都":
            [
                ("nishiki-food", "锦市场小食铺", "food", 35.0051, 135.7648, "在锦市场小食铺里点了一份热汤", "窄街、木色招牌和本地食物都适合写进攻略。"),
                ("sanjo-coffee", "三条咖啡窗口", "cafe", 35.0095, 135.7667, "在咖啡窗口旁边的小桌喝了一杯饮料", "TA 选了一个能看见街口的位置，让路线慢下来。"),
                ("shijo-convenience", "四条便利店", "shop", 35.0038, 135.7596, "在便利店里绕了一圈，挑了小补给", "灯光和街声稳定，适合表达 TA 在城市里认真生活。"),
                ("kawaramachi-netcafe", "河原町安静网咖", "netcafe", 35.0064, 135.7690, "在网咖角落听见很轻的键盘声", "室内停留点，适合长时间待着，不会一直机械移动。"),
                ("gion-flower", "祇园花店橱窗", "flower", 35.0034, 135.7752, "在花店橱窗前看了很久的叶子", "街面安静，适合作为明信片候选点。")
            ]
        case "雷克雅未克":
            [
                ("laugavegur-food", "Laugavegur 小食铺", "food", 64.1452, -21.9298, "在小食铺里点了一小碗热汤", "寒冷城市里的热气和灯光，适合做温柔停靠点。"),
                ("downtown-coffee", "市中心咖啡窗口", "cafe", 64.1462, -21.9317, "在咖啡窗口旁边喝了一杯热饮", "TA 坐在暖灯边，把这段城市夜色写进小卡片。"),
                ("harpa-convenience", "Harpa 附近便利店", "shop", 64.1490, -21.9321, "在便利店里选了一样小补给", "靠近城市建筑和步行街，不会落到海面。"),
                ("warm-game-room", "暖灯游戏小店", "netcafe", 64.1441, -21.9266, "在屏幕光旁边安静待了一会儿", "室内长停留点，符合电子宠物走走停停的节奏。"),
                ("rainbow-flower", "彩虹街花店橱窗", "flower", 64.1428, -21.9279, "在花店橱窗前看了很久的叶子", "色彩和街面都适合生成地点感强的照片。")
            ]
        default:
            [
                ("street-food", "街角小食铺", "food", city.position.latitude + 0.0012, city.position.longitude - 0.0010, "在街角小食铺里点了店里的招牌小吃", "TA 走进店里坐下，边听周围人说话边慢慢吃。"),
                ("coffee-window", "咖啡窗口", "cafe", city.position.latitude - 0.0008, city.position.longitude + 0.0014, "在咖啡窗口旁的小桌喝了一杯饮料", "TA 选了靠窗的小桌，把这段路记进手机。"),
                ("convenience", "便利店", "shop", city.position.latitude + 0.0015, city.position.longitude + 0.0010, "在便利店里挑了一个小补给", "灯光稳定、声音熟悉，适合走走停停。"),
                ("quiet-netcafe", "安静网吧", "netcafe", city.position.latitude - 0.0013, city.position.longitude - 0.0015, "在网吧角落待了一会儿", "这是 TA 自己选择的室内停留点。"),
                ("flower-window", "花店橱窗", "flower", city.position.latitude + 0.0005, city.position.longitude - 0.0017, "在花店前停住，看了很久的叶子", "街面安静、气味柔和，适合作为中途停留。")
            ]
        }
    }

    private func itineraryStop(
        _ place: PlaceSignal,
        title: String,
        detail: String,
        plannedTime: String,
        dwellMinutes: Int,
        postcardCandidate: Bool = false,
        photoCandidate: Bool = false
    ) -> ItineraryStop {
        ItineraryStop(
            id: "stop-\(place.id)",
            name: place.name,
            category: place.category,
            city: place.city,
            latitude: place.latitude,
            longitude: place.longitude,
            title: title,
            detail: detail,
            plannedTime: plannedTime,
            dwellMinutes: dwellMinutes,
            postcardCandidate: postcardCandidate,
            photoCandidate: photoCandidate,
            source: place.source
        )
    }

    private func cityFor(journey: MockJourney) -> MockCity {
        let elapsed = Date().timeIntervalSince(journey.createdAt)
        let index = max(0, Int(elapsed / 172_800)) % cities.count
        return cities[index]
    }

    private func statusFor(now: Date) -> JourneyStatus {
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

    private func wave(_ elapsed: TimeInterval, period: TimeInterval, amplitude: Int) -> Int {
        Int(sin(elapsed / period * .pi * 2) * Double(amplitude))
    }

    private func clamped(_ value: Int, _ lower: Int, _ upper: Int) -> Int {
        min(max(value, lower), upper)
    }

    private func clamped(_ value: Double, _ lower: Double, _ upper: Double) -> Double {
        min(max(value, lower), upper)
    }

    private func nonEmpty(_ value: String?, fallback: String) -> String {
        guard let value else { return fallback }
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? fallback : trimmed
    }

    private func mockDestination(from message: String) -> String {
        if message.contains("世界杯") || message.localizedCaseInsensitiveContains("world cup") {
            return "世界杯赛场城市"
        }
        for marker in ["去", "到", "想让你去"] {
            if let range = message.range(of: marker) {
                let suffix = message[range.upperBound...]
                let destination = suffix
                    .split(whereSeparator: { "，。,.!?！？ ".contains($0) })
                    .first
                    .map(String.init)?
                    .replacingOccurrences(of: "玩", with: "")
                    .replacingOccurrences(of: "看看", with: "")
                    .replacingOccurrences(of: "做攻略", with: "")
                    .trimmingCharacters(in: .whitespacesAndNewlines)
                if let destination, destination.count >= 2 {
                    return destination
                }
            }
        }
        return "鼓浪屿"
    }

    private func makeMockTravelGuide(
        petName: String,
        ownerMessage: String,
        destination: String,
        isWorldCup: Bool,
        now: Date
    ) -> TravelQuestGuide {
        let mainStopName = isWorldCup ? "赛场外安静广场" : "\(destination) 本地生活街"
        let stops = [
            TravelQuestStop(
                id: "mock-guide-rest",
                city: "厦门",
                name: "出发前安静休息点",
                role: "准备",
                plannedTime: "前一晚",
                dwellMinutes: 90,
                petVoice: "我会先睡够，不急着出门。",
                ownerTip: "手机里展示为准备态。",
                sourceNotes: []
            ),
            TravelQuestStop(
                id: "mock-guide-arrival",
                city: destination,
                name: isWorldCup ? "赛场附近咖啡店" : "\(destination) 抵达后的第一处安静地方",
                role: "缓冲",
                plannedTime: "抵达后",
                dwellMinutes: 70,
                petVoice: "到新地方以后，我会先找不太吵的位置，看看这里的风和灯光。",
                ownerTip: "如果你以后也来，这里可以作为刚抵达时先缓一缓的地方。",
                sourceNotes: ["先确认附近真实店铺和营业时间", "优先选择离交通点不远的位置"]
            ),
            TravelQuestStop(
                id: "mock-guide-main",
                city: destination,
                name: mainStopName,
                role: isWorldCup ? "看比赛" : "慢慢玩",
                plannedTime: "傍晚",
                dwellMinutes: 120,
                petVoice: isWorldCup ? "我想站在不拥挤的地方，把灯光和欢呼声记下来。" : "我不会只去热门景点，也想走进一点真正有人生活的街道。",
                ownerTip: "这是 TA 会认真体验的一站，之后会把照片、明信片或带回的小东西寄给你看。",
                sourceNotes: isWorldCup ? ["确认比赛时间和赛场周边交通", "避开最拥挤的入口"] : ["参考当地榜单和真实游记", "优先找能体现本地生活的街区"]
            )
        ]
        let research = TravelGuideResearch(
            provider: .hybrid,
            providerName: isWorldCup ? "GPT Web Search + 地图资料" : "豆包社媒线索 + 地图资料",
            destinationRegion: isWorldCup ? "海外赛事城市" : "国内/本地目的地",
            query: ownerMessage,
            strategy: isWorldCup ? "先确认比赛和城市交通，再找赛场外可停留的地点。" : "先看真实路线和本地推荐，再让 TA 选择想停的地方。",
            findings: isWorldCup
                ? ["先查赛程、场馆和入场时间", "长途交通用真实航班或中转时间推进", "到场后先找安静缓冲点，再靠近赛场"]
                : ["先看榜单、游记和真实 POI", "同城路线优先用步行、地铁或短途打车", "每一站都要能产生照片、明信片或带回物"],
            recommendedSources: isWorldCup ? ["赛事官网", "Google Maps", "旅行攻略网站"] : ["高德地图", "小红书/抖音线索", "本地榜单"],
            missingCapabilities: [],
            generatedAt: now
        )
        return TravelQuestGuide(
            id: "TQG-\(UUID().uuidString.prefix(8).uppercased())",
            title: isWorldCup ? "\(petName) 先替你去看看世界杯" : "\(petName) 先替你看看 \(destination)",
            summary: "我会先把路查清楚，再去 \(destination) 走一遍。哪里值得停、哪里适合拍照、哪里可以慢慢待，我会回来告诉你。",
            petVoice: "我听见你说「\(ownerMessage)」。我会先查路线和当地怎么玩，再自己决定什么时候出发。等我走过以后，如果有机会，你也可以来看看。",
            routeTheme: isWorldCup ? "先休息，再长途交通，最后靠近赛场" : "先替你看一遍，再把值得来的地方寄回来",
            cities: ["厦门", destination],
            stops: stops,
            transportOutline: [
                TravelQuestTransportOutline(
                    mode: isWorldCup ? .flight : .train,
                    fromPlace: "厦门",
                    toPlace: destination,
                    estimatedDuration: isWorldCup ? "按真实航班/中转时间推进" : "按城际交通推进",
                    realityLevel: "reference_schedule",
                    note: "先用真实班次或中转时间做时间轴。"
                ),
                TravelQuestTransportOutline(
                    mode: .walk,
                    fromPlace: stops[1].name,
                    toPlace: stops[2].name,
                    estimatedDuration: "10-25 分钟",
                    realityLevel: "map_route_available",
                    note: "最后一段我会按地图上的真实道路慢慢走过去。"
                )
            ],
            preparationNotes: [
                "先把攻略整理好，再决定什么时候出发。",
                "TA 可以接受、推迟或拒绝，保留自己的节奏。",
                "照片会结合地点、天气和宠物参考图来生成。"
            ],
            sourceNotes: research.recommendedSources,
            research: research,
            generatedAt: now,
            provider: "mock-ios-travel-quest"
        )
    }

    private func mockSouvenirSeeds(
        destination: String,
        placeName: String,
        isWorldCup: Bool,
        bag: TravelBag?
    ) -> [MockSouvenirSeed] {
        let bagHint = mockBagSouvenirHint(bag)
        let context = "\(destination) \(placeName) \(bag?.items.flatMap(\.influenceTags).joined(separator: " ") ?? "")"
        if isWorldCup {
            return [
                MockSouvenirSeed(
                    itemType: .ticketStub,
                    title: "球场灯光票根",
                    subtitle: "一小张被灯光照过的纸片",
                    story: "TA 在赛场外把路线票根夹进小包里。\(bagHint)",
                    petVoice: "我把灯光和欢呼声折小一点，带回来给你。",
                    rarity: "rare"
                ),
                MockSouvenirSeed(
                    itemType: .culturalCreative,
                    title: "城市小围巾挂件",
                    subtitle: "没有官方标志，只留下队伍颜色的氛围",
                    story: "路边摊位上挂着很多颜色，TA 选了最不吵的一条小挂件。",
                    petVoice: "它很轻，走路时会轻轻晃，好像还带着球场的风。",
                    rarity: "uncommon"
                ),
                MockSouvenirSeed(
                    itemType: .photoPrint,
                    title: "看台边的拍立得",
                    subtitle: "一张像被路人帮忙拍下来的小照片",
                    story: "比赛散场后，TA 在不拥挤的角落停了一会儿，把这一刻留下。",
                    petVoice: "我没有挤到最前面，但我看见了很亮的夜晚。",
                    rarity: "common"
                )
            ]
        }
        if mockText(context, containsAny: ["厦门", "鼓浪屿", "福建", "海", "sea"]) {
            return [
                MockSouvenirSeed(
                    itemType: .ticketStub,
                    title: "鼓浪屿渡船票角",
                    subtitle: "边缘带着海风的小票角",
                    story: "TA 从渡口出来时，把这张票角夹进小包里，像把一小段海路收好。\(bagHint)",
                    petVoice: "它闻起来有一点点咸，我一看到就想起船慢慢靠岸的声音。",
                    rarity: "uncommon"
                ),
                MockSouvenirSeed(
                    itemType: .culturalCreative,
                    title: "海风小船贴纸",
                    subtitle: "贴在手机角落也不会吵的小贴纸",
                    story: "靠近 \(placeName) 的小店里有一排安静的小船图案，TA 挑了颜色最轻的那一枚。",
                    petVoice: "我想把海边的小窗贴给你，等你想我的时候就看一眼。",
                    rarity: "common"
                ),
                MockSouvenirSeed(
                    itemType: .foundObject,
                    title: "凤凰花瓣纸签",
                    subtitle: "像傍晚路边掉下来的红色书签",
                    story: "TA 在街角等风停的时候捡到一片压扁的花瓣，把它夹进纸签里。",
                    petVoice: "它很轻，可是颜色很认真，像今天在认真想你。",
                    rarity: "common"
                )
            ]
        }
        if mockText(context, containsAny: ["京都", "kyoto", "鸭川", "祇园"]) {
            return [
                MockSouvenirSeed(
                    itemType: .charm,
                    title: "和纸小书签",
                    subtitle: "摸起来有一点木香和纸香",
                    story: "TA 在京都的窄路边停下，挑了一枚不亮眼的和纸书签。\(bagHint)",
                    petVoice: "它不会发出声音，只会安静地提醒我慢慢走。",
                    rarity: "uncommon"
                ),
                MockSouvenirSeed(
                    itemType: .snackPack,
                    title: "抹茶糖纸",
                    subtitle: "被折得很平的小糖纸",
                    story: "午后的光落在店门口，TA 把糖纸仔细抹平，像收好一小口苦甜。",
                    petVoice: "我没有吃太多，只把味道最轻的那一点带回来。",
                    rarity: "common"
                ),
                MockSouvenirSeed(
                    itemType: .foundObject,
                    title: "鸭川小石子",
                    subtitle: "一颗被水磨得圆圆的小石子",
                    story: "TA 沿着水边走了一会儿，选了一颗不会硌到包里的小石子。",
                    petVoice: "它比玩具还安静，但拿在爪边很踏实。",
                    rarity: "common"
                )
            ]
        }
        if mockText(context, containsAny: ["雷克雅未克", "reykjavik", "冰岛", "极光"]) {
            return [
                MockSouvenirSeed(
                    itemType: .foundObject,
                    title: "火山黑沙小瓶",
                    subtitle: "装着一点深色海岸线的小瓶子",
                    story: "TA 在冷风里低头看了很久，把一点黑沙收进透明小瓶。\(bagHint)",
                    petVoice: "它不像宝石，可是里面有很远很远的路。",
                    rarity: "uncommon"
                ),
                MockSouvenirSeed(
                    itemType: .charm,
                    title: "羊毛线结",
                    subtitle: "像从暖屋门口掉下来的一小截线",
                    story: "外面很冷，TA 在暖灯旁边发现一个松松的线结，把它当成回家的暗号。",
                    petVoice: "我把暖的那一头留给你，冷的那一头我自己拿着。",
                    rarity: "common"
                ),
                MockSouvenirSeed(
                    itemType: .photoPrint,
                    title: "极光色小卡",
                    subtitle: "一张没有文字的渐变色小卡",
                    story: "夜色很长的时候，TA 把天边的颜色记成一张小卡。",
                    petVoice: "我看见天空慢慢亮了一下，就像你在很远处叫我。",
                    rarity: "rare"
                )
            ]
        }
        if mockText(context, containsAny: ["花店", "公园", "park", "flower"]) {
            return [
                MockSouvenirSeed(
                    itemType: .foundObject,
                    title: "压平的小叶子",
                    subtitle: "一片像路上停顿号的小叶子",
                    story: "TA 在 \(placeName) 停下来闻了闻，把一片完整的小叶子夹进纸里。\(bagHint)",
                    petVoice: "它不会一直绿下去，可今天它很像我的心情。",
                    rarity: "common"
                ),
                MockSouvenirSeed(
                    itemType: .charm,
                    title: "花瓣书签",
                    subtitle: "夹着一点香气的薄纸签",
                    story: "TA 没有摘花，只收了一片落在地上的花瓣。",
                    petVoice: "这不是很大的礼物，但它刚好从风里掉到我面前。",
                    rarity: "common"
                ),
                MockSouvenirSeed(
                    itemType: .culturalCreative,
                    title: "\(destination) 生活街贴纸",
                    subtitle: "一枚记录这座城市日常颜色的小贴纸",
                    story: "TA 在 \(destination) 的生活街区停了一会儿，挑了一个不浮夸的小纪念物。",
                    petVoice: "我想把这座城市最小的一片颜色带回来。",
                    rarity: "common"
                )
            ]
        }
        return [
            MockSouvenirSeed(
                itemType: .culturalCreative,
                title: "\(destination) 生活街贴纸",
                subtitle: "一枚记录这座城市日常颜色的小贴纸",
                story: "TA 在 \(destination) 的生活街区停了一会儿，挑了一个不浮夸的小纪念物。\(bagHint)",
                petVoice: "我想把这座城市最小的一片颜色带回来。",
                rarity: "common"
            ),
            MockSouvenirSeed(
                itemType: .foundObject,
                title: "路边小卡片",
                subtitle: "夹着一点当地光线的纸片",
                story: "TA 在安静的角落发现一张好看的小卡片，像是这一天留下的页脚。",
                petVoice: "它没有很贵重，但我看见它的时候想到了你。",
                rarity: "common"
            ),
            MockSouvenirSeed(
                itemType: .toy,
                title: "软软小玩具",
                subtitle: "旅途中遇到的小伙伴",
                story: "TA 在路过的店里看见一个很软的小玩具，决定把它带回来。",
                petVoice: "它可以陪我睡一小会儿，也可以陪你等我的下一张照片。",
                rarity: "uncommon"
            )
        ]
    }

    private func mockBagSouvenirHint(_ bag: TravelBag?) -> String {
        guard let bag, !bag.items.isEmpty else {
            return "TA 凭自己的好奇心挑选了它。"
        }
        let titles = bag.items.suffix(3).map(\.title).joined(separator: "、")
        return "小包里还放着 \(titles)，所以这件小物也带着一点主人的提醒。"
    }

    private func mockEconomyResponse(petID: String) -> EconomyResponse {
        EconomyResponse(
            wallet: mockWallet(petID: petID),
            ownerFund: mockOwnerFund(petID: petID),
            snapshot: mockSnapshot(petID: petID),
            recentTransactions: Array((economyTransactions[petID] ?? []).prefix(20))
        )
    }

    private func mockWallet(petID: String) -> Wallet {
        if let wallet = wallets[petID] {
            return wallet
        }
        let wallet = Wallet(petID: petID, travelCoin: 0, starDust: 0, merit: 0, updatedAt: Date())
        wallets[petID] = wallet
        return wallet
    }

    private func mockOwnerFund(petID: String) -> OwnerFund {
        if let fund = ownerFunds[petID] {
            return fund
        }
        let date = String(ISO8601DateFormatter().string(from: Date()).prefix(10))
        let fund = OwnerFund(
            petID: petID,
            starDust: 0,
            projectBudget: 0,
            cosmeticBudget: 0,
            travelOpportunityBudget: 0,
            dailyCoinLimit: 300,
            coinInflowToday: 0,
            coinInflowDate: date,
            updatedAt: Date()
        )
        ownerFunds[petID] = fund
        return fund
    }

    private func mockSnapshot(petID: String) -> EconomySnapshot {
        let items = souvenirs[petID] ?? []
        let owned = items.filter { $0.effectiveStatus == .owned }
        let sellable = owned.filter(\.isSellable)
        return EconomySnapshot(
            petID: petID,
            totalDisplayValue: owned.reduce(0) { $0 + $1.displayMarketValue + $1.displayEmotionalValue + $1.displayHonorValue },
            sellableValue: sellable.reduce(0) { $0 + $1.resaleValue },
            collectionValue: owned.reduce(0) { $0 + $1.displayEmotionalValue },
            honorValue: owned.reduce(0) { $0 + $1.displayHonorValue },
            ownedItemCount: owned.count,
            sellableItemCount: sellable.count,
            archivedItemCount: items.filter { $0.effectiveStatus == .archived }.count,
            soldItemCount: items.filter { $0.effectiveStatus == .sold }.count,
            updatedAt: Date()
        )
    }

    private func mockExistingTransaction(petID: String, idempotencyKey: String) -> EconomyTransaction? {
        (economyTransactions[petID] ?? []).first { $0.idempotencyKey == idempotencyKey }
    }

    private func mockTransaction(
        petID: String,
        type: EconomyTransactionType,
        idempotencyKey: String,
        amounts: CurrencyAmounts,
        itemIDs: [String],
        reason: String,
        source: String,
        operatorName: String
    ) -> EconomyTransaction {
        EconomyTransaction(
            txID: "TX-\(UUID().uuidString.prefix(8).uppercased())",
            petID: petID,
            type: type,
            idempotencyKey: idempotencyKey,
            amounts: amounts,
            itemIDs: itemIDs,
            before: [:],
            after: [:],
            reason: reason,
            operatorName: operatorName,
            source: source,
            status: "committed",
            createdAt: Date()
        )
    }

    private func replaceSouvenir(_ item: SouvenirItem, petID: String) {
        guard var items = souvenirs[petID],
              let index = items.firstIndex(where: { $0.id == item.id }) else {
            return
        }
        items[index] = item
        souvenirs[petID] = items
    }

    private func mockMarketValue(for seed: MockSouvenirSeed) -> Int {
        Int(Double(mockBaseValue(for: seed.itemType)) * mockRarityMultiplier(seed.rarity) * 1.4 * 0.96 * 1.05)
    }

    private func mockBaseValue(for itemType: SouvenirItemType) -> Int {
        switch itemType {
        case .toy:
            25
        case .culturalCreative:
            28
        case .ticketStub:
            20
        case .charm:
            35
        case .snackPack:
            12
        case .photoPrint:
            45
        case .foundObject:
            18
        }
    }

    private func mockRarityMultiplier(_ rarity: String) -> Double {
        switch rarity {
        case "rare":
            10
        case "uncommon":
            3
        default:
            1
        }
    }

    private func mockSouvenirImagePrompt(
        seed: MockSouvenirSeed,
        destination: String,
        placeName: String,
        isWorldCup: Bool
    ) -> String {
        let eventConstraint = isWorldCup
            ? "If there is a match atmosphere, avoid official tournament logos, club crests, readable trademarks, or real ticket branding. "
            : ""
        return "Warm realistic keepsake photo from a parallel-world pet travel app. The keepsake is '\(seed.title)', type '\(seed.itemType.rawValue)', from \(destination), near \(placeName). Show it on soft cloth or a small cafe table with subtle local hints. \(eventConstraint)No UI text, no watermark, gentle emotional companion style."
    }

    private func mockText(_ text: String, containsAny keywords: [String]) -> Bool {
        keywords.contains { text.localizedCaseInsensitiveContains($0) }
    }

    private func travelBagKey(petID: String, questID: String?) -> String {
        "\(petID)-\(questID ?? "main")"
    }

    private func emptyTravelBag(petID: String, questID: String?) -> TravelBag {
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

    private func travelBagNote(for items: [TravelBagItem]) -> String {
        guard !items.isEmpty else {
            return "这只小包还空着。出发前可以放一点小零食、护身符，或一句想让 TA 带着走的话。"
        }
        let names = items.suffix(4).map(\.title).joined(separator: "、")
        return "我把 \(names) 收进小包里了。它们不会替我决定路线，但会在路上提醒我慢一点、记得回来。"
    }

    private func mockIntent(for text: String) -> CommunicatorIntent {
        if ["撑不住", "好难受", "不想活", "崩溃", "受不了了", "好痛苦"].contains(where: { text.contains($0) }) {
            return .emotionalDistress
        }
        let compact = text.replacingOccurrences(of: " ", with: "")
        if compact.count <= 12,
           ["好", "好滴", "好的", "嗯", "嗯嗯", "行", "可以", "ok", "OK"].contains(where: { compact.contains($0) }),
           ["看", "看看", "照片", "拍"].contains(where: { compact.contains($0) }),
           !["不看", "不用", "别拍", "不要"].contains(where: { compact.contains($0) }) {
            return .confirmPendingPhoto
        }
        if ["你现在干嘛", "现在干嘛", "在干嘛", "看看你", "给我看看", "让我看看你", "发张现在的照片"].contains(where: { text.contains($0) }) {
            return .currentStatusVisualRequest
        }
        if ["拍张照片", "发张照片", "自拍", "看看风景"].contains(where: { text.contains($0) }) {
            return .photoRequest
        }
        if ["寄张明信片", "明信片"].contains(where: { text.contains($0) }) {
            return .postcardRequest
        }
        if ["你在哪", "现在在哪", "到哪里了", "你在什么地方"].contains(where: { text.contains($0) }) {
            return .locationCheck
        }
        if ["想你", "抱抱", "摸摸", "乖乖", "宝宝"].contains(where: { text.contains($0) }) {
            return .affectionIMissYou
        }
        if ["累不累", "饿不饿", "冷不冷", "开心吗", "有没有休息"].contains(where: { text.contains($0) }) {
            return .careCheck
        }
        return .generalChat
    }

    private func mockReplyPolicy(intent: CommunicatorIntent, message: String, journey: MockJourney) -> CommunicatorReplyPolicy {
        let status = statusFor(now: Date())
        let isPhotoIntent = intent == .currentStatusVisualRequest || intent == .photoRequest || intent == .confirmPendingPhoto
        if status == .flying {
            return CommunicatorReplyPolicy(
                mode: "queued_until_landed",
                estimatedReplySeconds: 2700,
                visibleStatus: "TA 正在路上，信号一会儿有一会儿没有，落地后会看到。",
                reasonCode: "pet_flying",
                shouldBatch: false,
                shouldMarkSeen: true,
                cooldownApplied: false
            )
        }
        if intent == .generalChat && status == .walking {
            return CommunicatorReplyPolicy(
                mode: "delayed",
                estimatedReplySeconds: 180,
                visibleStatus: "TA 正在路上，可能会慢一点回你。",
                reasonCode: "general_chat_pet_in_transit",
                shouldBatch: false,
                shouldMarkSeen: true,
                cooldownApplied: false
            )
        }
        return CommunicatorReplyPolicy(
            mode: "immediate",
            estimatedReplySeconds: 6,
            visibleStatus: isPhotoIntent ? "这一刻可以拍给你。" : "TA 收到了。",
            reasonCode: isPhotoIntent ? "pet_at_photoable_scene" : "default_available",
            shouldBatch: false,
            shouldMarkSeen: true,
            cooldownApplied: false
        )
    }

    private func mockAttachments(intent: CommunicatorIntent, policy: CommunicatorReplyPolicy, city: MockCity) -> [CommunicatorAttachment] {
        let location = CommunicatorLocation(
            city: city.name,
            placeName: city.name == "厦门" ? "海边栈道" : "安静街角",
            latitude: city.position.latitude,
            longitude: city.position.longitude
        )
        if intent == .locationCheck {
            return [
                CommunicatorAttachment(type: .locationCard, title: "TA 此刻的位置", text: "\(city.name) · \(location.placeName ?? "旅途中")。\(city.weather)", state: "ready", photoURL: nil, location: location, photoMissionID: nil, availableAfter: nil)
            ]
        }
        if intent == .currentStatusVisualRequest || intent == .photoRequest || intent == .confirmPendingPhoto {
            // 与后端一致：位置卡只在 locationCheck 出现；排队/延迟时正文已说明"晚点拍"，不再挂同义卡
            guard policy.mode == "immediate" else { return [] }
            return [
                CommunicatorAttachment(type: .photoPlaceholder, title: "正在拍给你", text: "TA 现在在\(city.name) · \(location.placeName ?? "旅途中")，画面准备好后会发来。", state: "placeholder", photoURL: nil, location: location, photoMissionID: "mock-photo-\(UUID().uuidString)", availableAfter: Date().addingTimeInterval(25))
            ]
        }
        if intent == .postcardRequest {
            return [
                CommunicatorAttachment(type: .postcardCandidate, title: "明信片在路上", text: "TA 会等一个更适合写给你的画面。", state: "planned", photoURL: nil, location: location, photoMissionID: nil, availableAfter: Date().addingTimeInterval(7200))
            ]
        }
        if intent == .affectionIMissYou || intent == .careCheck {
            return [
                CommunicatorAttachment(type: .sticker, title: "🐾 蹭蹭", text: "轻轻蹭了蹭。", state: "ready", photoURL: nil, location: nil, photoMissionID: nil, availableAfter: nil)
            ]
        }
        return []
    }

    private func mockCommunicatorReply(intent: CommunicatorIntent, message: String, city: MockCity) -> String {
        switch intent {
        case .emotionalDistress:
            return "我看到你这句话了。先不要一个人硬撑，去找身边可信的人或当地紧急帮助；我会把一点光轻轻放在这里陪你。"
        case .currentStatusVisualRequest:
            return "我在\(city.name)这边。\(mockSceneFeeling(for: city))，我拍给你看。"
        case .photoRequest:
            return "好呀。我找个不晃的角度，拍给你。"
        case .confirmPendingPhoto:
            return "嗯嗯，我拍给你看。"
        case .locationCheck:
            return "我现在在\(city.name)。位置给你发过来了。"
        case .affectionIMissYou:
            return "我也有一点想你。刚才有阵风过来，像你摸了摸我。"
        case .careCheck:
            return "我会慢一点，找个舒服的地方停一下。你也记得照顾自己。"
        case .postcardRequest:
            return "我会等一个更适合写给你的画面，不急着把它寄出去。"
        default:
            return mockGeneralCommunicatorReply(message: message, city: city)
        }
    }

    private func mockGeneralCommunicatorReply(message: String, city: MockCity) -> String {
        let compact = message.replacingOccurrences(of: " ", with: "")
        let isShortAck = compact.count <= 8 && ["好", "好滴", "好的", "嗯", "嗯嗯", "行", "可以", "收到", "ok", "OK", "看看"].contains { compact.contains($0) }
        if isShortAck {
            if ["看", "照片", "拍"].contains(where: { compact.contains($0) }) {
                return "嗯嗯，等照片好了我发你。"
            }
            return "嗯嗯。"
        }
        if ["去", "看看", "路过", "下次", "有空"].contains(where: { message.contains($0) }) {
            return "我先记着。等路走到合适的地方，我再看一眼。"
        }
        if message.contains("谢谢") || message.contains("辛苦") {
            return "不辛苦，我慢慢走就好。"
        }
        if message.contains("晚安") {
            return "晚安。我把声音放轻一点。"
        }
        return "我看到啦。现在还在\(city.name)这边，等停稳一点再跟你说。"
    }

    private func mockOwnerPhotoReply(caption: String, city: MockCity) -> String {
        if ["家", "以前", "小时候", "想你"].contains(where: { caption.contains($0) }) {
            return "我看到啦。这里面有一点熟悉的味道，像从家里递过来的一小块光。"
        }
        if ["吃", "饭", "咖啡", "甜", "香"].contains(where: { caption.contains($0) }) {
            return "我看到啦。看起来很香，我在\(city.name)这边也慢慢闻了闻风。"
        }
        if ["看看", "看一下", "给你看"].contains(where: { caption.contains($0) }) {
            return "我看到啦。这个画面离我很近，像你把那边的一点点生活递过来了。"
        }
        if !caption.isEmpty {
            return "我看到啦。这张照片我收好了，晚点路上也会想起它。"
        }
        return "我看到啦。像你从那边轻轻递来了一小块画面。"
    }

    private func persistMockCommunicatorPhoto(_ imageData: Data) throws -> URL {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("petsoul-communicator", isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let fileURL = directory.appendingPathComponent("owner-photo-\(UUID().uuidString).jpg")
        try imageData.write(to: fileURL)
        return fileURL
    }

    private func mockSceneFeeling(for city: MockCity) -> String {
        if city.name == "厦门" {
            return "街边声音有点近"
        }
        return "\(city.weather)，这一刻还算安静"
    }

    private func seedMoments(petID: String, petName: String, city: MockCity) -> [CommunicatorMoment] {
        let location = CommunicatorLocation(city: city.name, placeName: city.name == "厦门" ? "海边栈道" : "安静街角", latitude: city.position.latitude, longitude: city.position.longitude)
        let restingDate = Date().addingTimeInterval(-18 * 60)
        let arrivalDate = Date().addingTimeInterval(-42 * 60)
        let restingReactors = mockSocialReactors(seed: "\(petID)-resting", createdAt: restingDate)
        let arrivalReactors = mockSocialReactors(seed: "\(petID)-arrival", createdAt: arrivalDate)
        return [
            CommunicatorMoment(
                id: "moment_mock_\(UUID().uuidString)",
                petID: petID,
                sourceType: "resting",
                sourceEventID: nil,
                text: "\(petName)在一个安静地方停了一小会儿，像是在把今天的路收进爪心。",
                location: location,
                mood: "calm",
                attachments: [
                    CommunicatorAttachment(
                        type: .locationCard,
                        title: "停留地点",
                        text: "\(city.name) · \(location.placeName ?? "安静角落")。TA 在这里慢慢待了一会儿。",
                        state: "ready",
                        photoURL: nil,
                        location: location,
                        photoMissionID: nil,
                        availableAfter: nil
                    )
                ],
                reactions: mockReactionCounts(for: restingReactors),
                ownerReaction: nil,
                isRead: false,
                createdAt: restingDate,
                updatedAt: nil,
                socialReactors: restingReactors
            ),
            CommunicatorMoment(
                id: "moment_mock_\(UUID().uuidString)",
                petID: petID,
                sourceType: "arrival",
                sourceEventID: nil,
                text: "到\(city.name)啦。这里的风和声音都还在慢慢认出来。",
                location: location,
                mood: "curious",
                attachments: MockDemoMedia.frenchiePostcardURL.map { photoURL in [
                    CommunicatorAttachment(
                        type: .photo,
                        title: "刚刚拍到的一眼",
                        text: "到\(city.name)后的第一眼，发给朋友圈一起看看。",
                        state: "ready",
                        photoURL: photoURL,
                        location: location,
                        photoMissionID: "mock-arrival-photo",
                        availableAfter: nil
                    )
                ] } ?? [
                    CommunicatorAttachment(
                        type: .locationCard,
                        title: "到达地点",
                        text: "\(city.name) · \(location.placeName ?? "安静角落")。TA 刚到这里，先向朋友圈报个平安。",
                        state: "ready",
                        photoURL: nil,
                        location: location,
                        photoMissionID: nil,
                        availableAfter: nil
                    )
                ],
                reactions: mockReactionCounts(for: arrivalReactors),
                ownerReaction: nil,
                isRead: false,
                createdAt: arrivalDate,
                updatedAt: nil,
                socialReactors: arrivalReactors
            )
        ]
    }

    private func insertMockMomentIfNeeded(petID: String, petName: String, city: MockCity, attachments: [CommunicatorAttachment]) {
        guard communicatorMoments[petID]?.first(where: { $0.sourceType == "current_status_photo" }) == nil else { return }
        let photoAttachments = attachments.filter { $0.type == .photo && $0.photoURL != nil }
        guard !photoAttachments.isEmpty else { return }
        let createdAt = Date()
        let reactors = mockSocialReactors(seed: "\(petID)-current-photo", createdAt: createdAt)
        let moment = CommunicatorMoment(
            id: "moment_mock_\(UUID().uuidString)",
            petID: petID,
            sourceType: "current_status_photo",
            sourceEventID: nil,
            text: "刚好遇到这一刻，就发到朋友圈里。大家路过的话，可以一起看看。",
            location: photoAttachments.first?.location,
            mood: "soft_happy",
            attachments: photoAttachments,
            reactions: mockReactionCounts(for: reactors),
            ownerReaction: nil,
            isRead: false,
            createdAt: createdAt,
            updatedAt: nil,
            socialReactors: reactors
        )
        communicatorMoments[petID, default: seedMoments(petID: petID, petName: petName, city: city)].insert(moment, at: 0)
    }

    private func mockSocialReactors(seed: String, createdAt: Date) -> [MomentSocialReactor] {
        // 与后端 communicator/npc_society.py 的常驻 NPC 保持同一批身份
        let pool: [(String, String, String, String, MomentReaction, String)] = [
            ("npc-nana-cat", "Nana", "cat", "🐱", .like, "在附近的窗台看见了这一刻"),
            ("npc-tuanzi-dog", "团子", "dog", "🐶", .like, "也觉得这里适合慢慢待着"),
            ("npc-jiujiu-parrot", "啾啾", "parrot", "🦜", .hug, "从公共频道轻轻回应了一下"),
            ("npc-momo-rabbit", "Momo", "rabbit", "🐰", .like, "把这一刻收藏进小地图"),
            ("npc-mili-hamster", "米粒", "hamster", "🐹", .hug, "偷偷把这一刻塞进了腮帮子"),
            ("npc-lucky-dog", "Lucky", "dog", "🐶", .like, "在街角朝这边汪了一声")
        ]
        let value = seed.unicodeScalars.reduce(0) { $0 + Int($1.value) }
        let count = 1 + value % 3
        let start = value % pool.count
        return (0..<count).map { index in
            let item = pool[(start + index) % pool.count]
            return MomentSocialReactor(
                id: item.0,
                name: item.1,
                species: item.2,
                avatarEmoji: item.3,
                reaction: item.4,
                note: item.5,
                createdAt: createdAt.addingTimeInterval(TimeInterval(18 + index * 31))
            )
        }
    }

    private func mockReactionCounts(for reactors: [MomentSocialReactor]) -> [String: Int] {
        var counts = ["like": 0, "paw": 0, "hug": 0]
        for reactor in reactors {
            counts[reactor.reaction.rawValue, default: 0] += 1
        }
        return counts
    }

    private func illustratedGuideLabel(for category: String, name: String) -> String {
        let lowercasedCategory = category.lowercased()
        if lowercasedCategory.contains("park") || name.contains("公园") {
            return "醒来"
        }
        if lowercasedCategory.contains("cafe") || name.contains("咖啡") {
            return "坐一会儿"
        }
        if lowercasedCategory.contains("food")
            || lowercasedCategory.contains("restaurant")
            || name.contains("沙茶")
            || name.contains("餐")
        {
            return "补给"
        }
        if lowercasedCategory.contains("scenic") || name.contains("海") || name.contains("岛") {
            return "看风景"
        }
        return "停留"
    }
}

private extension TravelQuest {
    func with(
        status: TravelQuestStatus? = nil,
        message: String? = nil,
        travelBag: TravelBag? = nil,
        journeyPlan: JourneyPlan? = nil,
        postEventOptions: [TravelQuestNextOption]? = nil,
        selectedNextOptionID: String? = nil
    ) -> TravelQuest {
        TravelQuest(
            id: id,
            petID: petID,
            questType: questType,
            status: status ?? self.status,
            currentPhase: status ?? currentPhase,
            tripType: tripType,
            returnPolicy: returnPolicy,
            originAnchor: originAnchor,
            ownerMessage: ownerMessage,
            destination: destination,
            eventName: eventName,
            preferredStartDate: preferredStartDate,
            autonomyDecision: autonomyDecision,
            currentPhaseMessage: message ?? currentPhaseMessage,
            guide: guide,
            travelBag: travelBag ?? self.travelBag,
            journeyPlan: journeyPlan ?? self.journeyPlan,
            postEventOptions: postEventOptions ?? self.postEventOptions,
            souvenirPreview: souvenirPreview,
            selectedNextOptionID: selectedNextOptionID ?? self.selectedNextOptionID,
            worldcupEvent: worldcupEvent,
            createdAt: createdAt,
            updatedAt: Date()
        )
    }
}

private enum MockDemoMedia {
    static var frenchieProfileURL: URL? {
        resourceURL(named: "frenchie-profile")
    }

    static var frenchiePostcardURL: URL? {
        resourceURL(named: "frenchie-netcafe-postcard")
    }

    private static func resourceURL(named name: String) -> URL? {
        Bundle.main.url(forResource: name, withExtension: "png", subdirectory: "DemoMedia")
            ?? Bundle.main.url(forResource: name, withExtension: "png")
    }
}

private extension PetDNA {
    static let demoFrenchie = PetDNA(
        ownerTitle: "妈妈",
        personality: "黏人、好奇、很会观察人的情绪，到了新地方会先看一圈再靠近。",
        favoritePlaces: ["有地毯的小店", "安静网吧", "能晒太阳的街角"],
        hobbies: ["盯着屏幕看", "戴耳机陪人打游戏", "闻咖啡和小吃的味道"],
        catchphrase: "我在这里玩一会儿，也在想你。",
        emojiPreference: "soft",
        voiceStyle: "像发来一张随手拍照片，语气轻轻的但很认真。"
    )
}
