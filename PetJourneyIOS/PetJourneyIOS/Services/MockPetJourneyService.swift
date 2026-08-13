import Foundation

@MainActor
final class MockPetJourneyService: PetJourneyService {
    struct MockCity {
        var name: String
        var position: CityPosition
        var weather: String
        var phrases: [String]
        var thoughts: [String]
    }

    struct MockSouvenirSeed {
        var itemType: SouvenirItemType
        var title: String
        var subtitle: String
        var story: String
        var petVoice: String
        var rarity: String
    }

    struct MockJourney {
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

    var journeys: [String: MockJourney] = [:]
    var memories: [String: [MemoryRecord]] = [:]
    var notifications: [String: [NotificationDelivery]] = [:]
    var registeredDeviceIDs: [String: String] = [:]
    var travelQuests: [String: [TravelQuest]] = [:]
    var travelBags: [String: TravelBag] = [:]
    var souvenirs: [String: [SouvenirItem]] = [:]
    var wallets: [String: Wallet] = [:]
    var ownerFunds: [String: OwnerFund] = [:]
    var economyTransactions: [String: [EconomyTransaction]] = [:]
    var communicatorMessages: [String: [CommunicatorMessage]] = [:]
    var communicatorMoments: [String: [CommunicatorMoment]] = [:]
    var mockUserID: String?
    var mockUserDisplayName: String?
    var mockClaimedPetIDs: Set<String> = []

    let cities: [MockCity] = [
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
}

extension TravelQuest {
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

enum MockDemoMedia {
    static var frenchieProfileURL: URL? {
        resourceURL(named: "frenchie-profile")
    }

    static var frenchiePostcardURL: URL? {
        resourceURL(named: "frenchie-netcafe-postcard")
    }

    static func resourceURL(named name: String) -> URL? {
        Bundle.main.url(forResource: name, withExtension: "png", subdirectory: "DemoMedia")
            ?? Bundle.main.url(forResource: name, withExtension: "png")
    }
}

extension PetDNA {
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
