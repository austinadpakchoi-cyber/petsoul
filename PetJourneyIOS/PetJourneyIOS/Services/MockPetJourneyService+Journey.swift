import Foundation

@MainActor
extension MockPetJourneyService {
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
            itineraryStop(places[3], title: "去海边收下午的风", detail: "下午我会靠近环岛路和白城沙滩，走慢一点，把海面、树影和路边的光记进通讯器。", plannedTime: "14:30", dwellMinutes: 85, photoCandidate: true),
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

    func mockTimeline(for plan: JourneyPlan, now: Date) -> [WorldTimelineItem] {
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

    func mockCurrentStop(
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

    func mockNextStop(in stops: [ItineraryStop], now: Date) -> ItineraryStop? {
        for (index, stop) in stops.enumerated() {
            if mockPlannedDate(stop.plannedTime, index: index, now: now) > now {
                return stop
            }
        }
        return nil
    }

    func mockPlannedDate(_ raw: String?, index: Int, now: Date) -> Date {
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
            landmarkHints: ["真实地点附近的街巷", "低角度镜头视角"],
            localDetailHints: ["pet face close to lens", "one paw in foreground", "screen glow", "keyboard", "drink cup"],
            crowdHints: [],
            weather: "室内有蓝色的灯，外面应该还是温暖的",
            timeOfDay: "afternoon",
            imagePrompt: "PetSoul parallel-world first-person pet selfie from TA's own phone near \(place.name). Preserve the exact pet identity from the reference photo by redrawing a complete natural new image, not a cutout or pasted sticker. Close pet face or paw in the foreground, low handheld angle, slightly imperfect framing, screen glow, keyboard, drink cup, real local background behind, warm emotional phone-photo style, no visible text, no logo, no watermark.",
            postcardText: "我把镜头放得低低的，在 \(place.name) 把这一刻留下来了。这里有键盘声和一点点像冒险的光。",
            safetyNotes: ["Preserve pet identity", "No official logos or readable brand marks"]
        )
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

    func mockPlaces(for city: MockCity) -> [PlaceSignal] {
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

    func safeMockPlaces(for city: MockCity) -> [(String, String, String, Double, Double, String, String)] {
        switch city.name {
        case "厦门":
            [
                ("huweishan-walkway", "狐尾山 / 山海健康步道", "park", 24.4874, 118.0847, "在狐尾山的风里慢慢醒来，看见厦门从高处亮起来", "高处、绿意和城市边界都很清楚，适合作为一日路线的开场。"),
                ("bashi-kaihe-food", "八市 / 开禾路老街", "food", 24.4579, 118.0739, "走进八市和开禾路的人间烟火里，看摊位、听声音、选一口本地味道", "老城市场和本地小吃让路线有厦门记忆点，适合作为早午间核心停靠。"),
                ("shapowei-daxue-road", "沙坡尾 / 大学路", "place", 24.4386, 118.0930, "在沙坡尾和大学路慢慢逛，听海风钻进巷子里", "老港、巷子、小店和海风都有画面感，适合照片、明信片和慢逛。"),
                ("baicheng-beach-ring-road", "环岛路 / 白城沙滩", "park", 24.4319, 118.1036, "下午沿环岛路靠近白城沙滩，把海风记进通讯器", "海边和环岛路是厦门很强的城市标签，适合作为下午的核心照片点。"),
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
                ("coffee-window", "咖啡窗口", "cafe", city.position.latitude - 0.0008, city.position.longitude + 0.0014, "在咖啡窗口旁的小桌喝了一杯饮料", "TA 选了靠窗的小桌，把这段路记进通讯器。"),
                ("convenience", "便利店", "shop", city.position.latitude + 0.0015, city.position.longitude + 0.0010, "在便利店里挑了一个小补给", "灯光稳定、声音熟悉，适合走走停停。"),
                ("quiet-netcafe", "安静网吧", "netcafe", city.position.latitude - 0.0013, city.position.longitude - 0.0015, "在网吧角落待了一会儿", "这是 TA 自己选择的室内停留点。"),
                ("flower-window", "花店橱窗", "flower", city.position.latitude + 0.0005, city.position.longitude - 0.0017, "在花店前停住，看了很久的叶子", "街面安静、气味柔和，适合作为中途停留。")
            ]
        }
    }

    func itineraryStop(
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

    func mockDestination(from message: String) -> String {
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
}
