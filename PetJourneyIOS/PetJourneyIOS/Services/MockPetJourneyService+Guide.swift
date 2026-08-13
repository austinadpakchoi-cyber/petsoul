import Foundation

@MainActor
extension MockPetJourneyService {
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
            model: "mock-guide-model",
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

    func mockIllustratedGuideLabel(for category: String, name: String) -> String {
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

    func mockUserFacingText(_ value: String) -> String {
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

    func mockIllustratedGuidePages(
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

    func makeMockTravelGuide(
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
                ownerTip: "通讯器里展示为准备态。",
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
            providerName: isWorldCup ? "沿途线索 + 地图资料" : "本地生活线索 + 地图资料",
            destinationRegion: isWorldCup ? "海外赛事城市" : "国内/本地目的地",
            query: ownerMessage,
            strategy: isWorldCup ? "先确认比赛和城市交通，再找赛场外可停留的地点。" : "先看真实路线和本地推荐，再让 TA 选择想停的地方。",
            findings: isWorldCup
                ? ["先查赛程、场馆和入场时间", "长途交通用真实航班或中转时间推进", "到场后先找安静缓冲点，再靠近赛场"]
                : ["先看榜单、游记和真实地点", "同城路线优先用步行、地铁或短途打车", "每一站都要能产生照片、明信片或带回物"],
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

    func illustratedGuideLabel(for category: String, name: String) -> String {
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
