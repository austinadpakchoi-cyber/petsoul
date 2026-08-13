import Foundation

@MainActor
extension MockPetJourneyService {
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

    func mockSouvenirSeeds(
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

    func mockBagSouvenirHint(_ bag: TravelBag?) -> String {
        guard let bag, !bag.items.isEmpty else {
            return "TA 凭自己的好奇心挑选了它。"
        }
        let titles = bag.items.suffix(3).map(\.title).joined(separator: "、")
        return "小包里还放着 \(titles)，所以这件小物也带着一点主人的提醒。"
    }

    func mockEconomyResponse(petID: String) -> EconomyResponse {
        EconomyResponse(
            wallet: mockWallet(petID: petID),
            ownerFund: mockOwnerFund(petID: petID),
            snapshot: mockSnapshot(petID: petID),
            recentTransactions: Array((economyTransactions[petID] ?? []).prefix(20))
        )
    }

    func mockWallet(petID: String) -> Wallet {
        if let wallet = wallets[petID] {
            return wallet
        }
        let wallet = Wallet(petID: petID, travelCoin: 0, starDust: 0, merit: 0, updatedAt: Date())
        wallets[petID] = wallet
        return wallet
    }

    func mockOwnerFund(petID: String) -> OwnerFund {
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

    func mockSnapshot(petID: String) -> EconomySnapshot {
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

    func mockExistingTransaction(petID: String, idempotencyKey: String) -> EconomyTransaction? {
        (economyTransactions[petID] ?? []).first { $0.idempotencyKey == idempotencyKey }
    }

    func mockTransaction(
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

    func replaceSouvenir(_ item: SouvenirItem, petID: String) {
        guard var items = souvenirs[petID],
              let index = items.firstIndex(where: { $0.id == item.id }) else {
            return
        }
        items[index] = item
        souvenirs[petID] = items
    }

    func mockMarketValue(for seed: MockSouvenirSeed) -> Int {
        Int(Double(mockBaseValue(for: seed.itemType)) * mockRarityMultiplier(seed.rarity) * 1.4 * 0.96 * 1.05)
    }

    func mockBaseValue(for itemType: SouvenirItemType) -> Int {
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

    func mockRarityMultiplier(_ rarity: String) -> Double {
        switch rarity {
        case "rare":
            10
        case "uncommon":
            3
        default:
            1
        }
    }

    func mockSouvenirImagePrompt(
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
}
