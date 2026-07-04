import CoreLocation
import Foundation
import MapKit

struct OwnerMessageReceipt: Identifiable, Equatable {
    enum DeliveryState: Equatable {
        case sending
        case delivered
        case failed
    }

    let id: UUID
    let text: String
    let timestamp: Date
    var state: DeliveryState
    var response: String?
    var decision: String?
}

@MainActor
final class JourneyViewModel: ObservableObject {
    enum LoadState: Equatable {
        case loading
        case loaded
        case empty
        case failed(String)
    }

    @Published private(set) var status: AgentStatus?
    @Published private(set) var dayPlan: DayPlan?
    @Published private(set) var dna: PetDNA?
    @Published private(set) var cityPosition: CityPosition?
    @Published private(set) var journeyPlan: JourneyPlan?
    @Published private(set) var worldSnapshot: WorldSimulationSnapshot?
    @Published private(set) var petGuide: PetAuthoredGuide?
    @Published private(set) var illustratedGuide: IllustratedGuide?
    @Published private(set) var remoteRoutePlan: RemoteJourneyRoutePlan?
    @Published private(set) var photoMission: PhotoMission?
    @Published private(set) var travelQuests: [TravelQuest] = []
    @Published private(set) var travelBag: TravelBag?
    @Published private(set) var souvenirs: [SouvenirItem] = []
    @Published private(set) var economy: EconomyResponse?
    @Published private(set) var visibleThoughtTranslation: ThoughtTranslation?
    @Published private(set) var isTranslatingThought = false
    @Published private(set) var isGeneratingPhoto = false
    @Published private(set) var isSendingOwnerMessage = false
    @Published private(set) var isCreatingTravelQuest = false
    @Published private(set) var isOpeningWorldCupQuest = false
    @Published private(set) var isPackingTravelBag = false
    @Published private(set) var isCollectingSouvenir = false
    @Published private(set) var mutatingInventoryItemIDs: Set<String> = []
    @Published private(set) var isGeneratingIllustratedGuide = false
    @Published private(set) var isUpdatingDNA = false
    @Published private(set) var receivedPhotoMissionIDs: Set<String>
    @Published private(set) var ownerMessageReceipts: [OwnerMessageReceipt] = []
    @Published private(set) var loadState: LoadState = .loading
    @Published private(set) var dataFreshness: DataFreshness = .fresh
    @Published var toastMessage: String?
    @Published var hasUnreadPostcard = false

    private let petID: String
    private let service: any PetJourneyService
    private let cache: JourneyCacheRepository
    private let outbox: OutboundMessageQueue
    private let receivedPhotoMissionStorageKey: String
    private var refreshTask: Task<Void, Never>?
    private var hydrationTask: Task<Void, Never>?
    private var translationCache: [String: ThoughtTranslation] = [:]
    private var lastPostcardCount = 0
    private var lastRefreshSucceededAt: Date?
    private var illustratedGuideGenerationIDs: Set<String> = []

    init(
        petID: String,
        service: any PetJourneyService,
        cache: JourneyCacheRepository? = nil,
        outbox: OutboundMessageQueue? = nil
    ) {
        self.petID = petID
        self.service = service
        self.cache = cache ?? JourneyCacheRepository(petID: petID)
        self.outbox = outbox ?? OutboundMessageQueue(petID: petID)
        receivedPhotoMissionStorageKey = "petsoul.receivedPhotoMissions.\(petID)"
        receivedPhotoMissionIDs = Set(UserDefaults.standard.stringArray(forKey: receivedPhotoMissionStorageKey) ?? [])
    }

    var coordinate: CLLocationCoordinate2D {
        (cityPosition ?? .xiamen).coordinate
    }

    var coordinateKey: String {
        let position = cityPosition ?? .xiamen
        return "\(position.latitude)-\(position.longitude)"
    }

    var mapRegion: MKCoordinateRegion {
        MKCoordinateRegion(
            center: coordinate,
            span: MKCoordinateSpan(latitudeDelta: 0.16, longitudeDelta: 0.16)
        )
    }

    var activeTravelQuest: TravelQuest? {
        travelQuests.first
    }

    var activeWorldCupQuest: TravelQuest? {
        travelQuests.first { $0.worldcupEvent }
    }

    func start() {
        guard refreshTask == nil else { return }
        refreshTask = Task { [weak self] in
            guard let self else { return }
            await self.loadInitial()
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(5))
                if !Task.isCancelled {
                    await self.refreshStatus()
                }
            }
        }
    }

    func stop() {
        refreshTask?.cancel()
        refreshTask = nil
        hydrationTask?.cancel()
        hydrationTask = nil
    }

    func loadInitial() async {
        hydrationTask?.cancel()
        loadState = .loading
        do {
            async let status = service.fetchAgentStatus(petID: petID)
            async let cityPosition = service.fetchCityPosition(petID: petID)

            let nextStatus = try await status
            self.status = nextStatus
            cache.store(nextStatus, kind: .agentStatus)
            if let nextPosition = try? await cityPosition {
                self.cityPosition = nextPosition
                cache.store(nextPosition, kind: .cityPosition)
            } else if let cached = cache.load(CityPosition.self, kind: .cityPosition) {
                self.cityPosition = cached.value
            }
            lastPostcardCount = nextStatus.postcards.count
            markRefreshSucceeded()
            loadState = .loaded
            hydrationTask = Task { [weak self] in
                await self?.hydrateInitialDetails()
            }
        } catch {
            if Task.isCancelled { return }
            // 离线冷启动：有缓存就先让 TA 的世界亮起来，标记 stale 待信号恢复。
            if let cachedStatus = cache.load(AgentStatus.self, kind: .agentStatus) {
                status = cachedStatus.value
                cityPosition = cache.load(CityPosition.self, kind: .cityPosition)?.value
                lastPostcardCount = cachedStatus.value.postcards.count
                dataFreshness = .stale(cachedStatus.updatedAt)
                loadState = .loaded
                hydrateDetailsFromCache()
            } else {
                loadState = .failed(error.localizedDescription)
            }
        }
    }

    func refreshStatus() async {
        do {
            async let statusTask = service.fetchAgentStatus(petID: petID)
            async let positionTask = service.fetchCityPosition(petID: petID)
            async let worldSnapshotTask = service.fetchWorldSnapshot(petID: petID)
            let nextStatus = try await statusTask
            let nextCount = nextStatus.postcards.count
            let previousJourneyStatus = status?.agentState.status
            if nextCount > lastPostcardCount {
                hasUnreadPostcard = true
            }
            status = nextStatus

            let nextPosition = try? await positionTask
            if let nextPosition {
                cityPosition = nextPosition
                cache.store(nextPosition, kind: .cityPosition)
            }

            let nextWorldSnapshot = try? await worldSnapshotTask
            if let nextWorldSnapshot {
                worldSnapshot = nextWorldSnapshot
                cache.store(nextWorldSnapshot, kind: .worldSnapshot)
            }
            if photoMission == nil || nextStatus.agentState.status != previousJourneyStatus {
                await refreshPhotoMission()
            }
            if visibleThoughtTranslation?.thoughtID != nextStatus.agentState.latestThought?.id {
                visibleThoughtTranslation = nil
            }
            lastPostcardCount = nextCount
            cache.store(nextStatus, kind: .agentStatus)
            markRefreshSucceeded()
            await drainOutboxIfNeeded()
        } catch {
            dataFreshness = .stale(lastRefreshSucceededAt)
            toastMessage = "通讯信号有点弱，稍后会再试。"
        }
    }

    private func markRefreshSucceeded() {
        lastRefreshSucceededAt = Date()
        dataFreshness = .fresh
    }

    /// 信号恢复后补发离线期间存下的讯息。
    private func drainOutboxIfNeeded() async {
        guard outbox.pendingCount > 0 else { return }
        await outbox.drain { [service, petID] text in
            _ = try await service.sendOwnerMessage(
                petID: petID,
                request: OwnerMessageRequest(message: text, intentHint: "owner_suggestion_or_companion_message")
            )
        }
        if outbox.pendingCount == 0 {
            toastMessage = "刚才没送出去的话，已经送达 TA 的世界。"
        }
    }

    /// 离线冷启动时用缓存点亮细节面。
    private func hydrateDetailsFromCache() {
        if let cached = cache.load(DayPlan.self, kind: .dayPlan) { dayPlan = cached.value }
        if let cached = cache.load(PetDNA.self, kind: .dna) { dna = cached.value }
        if let cached = cache.load(WorldSimulationSnapshot.self, kind: .worldSnapshot) { worldSnapshot = cached.value }
        if let cached = cache.load(JourneyPlan.self, kind: .journeyPlan) {
            journeyPlan = cached.value
            remoteRoutePlan = cached.value.compatibilityRoutePlan
        }
        if let cached = cache.load(IllustratedGuide.self, kind: .illustratedGuide) { illustratedGuide = cached.value }
        if let cached = cache.load([TravelQuest].self, kind: .travelQuests) { travelQuests = cached.value }
        if let cached = cache.load([SouvenirItem].self, kind: .souvenirs) { souvenirs = cached.value }
        if let cached = cache.load(EconomyResponse.self, kind: .economy) { economy = cached.value }
    }

    private func hydrateInitialDetails() async {
        async let dayPlanTask = service.fetchDayPlan(petID: petID)
        async let dnaTask = service.fetchDNA(petID: petID)
        async let worldSnapshotTask = service.fetchWorldSnapshot(petID: petID)
        async let journeyPlanTask = service.fetchJourneyPlan(petID: petID)
        async let illustratedGuideTask = service.fetchIllustratedGuide(petID: petID)
        async let photoMissionTask = service.fetchPhotoMission(petID: petID)
        async let travelQuestTask = service.fetchTravelQuests(petID: petID, limit: 8)
        async let souvenirTask = service.fetchSouvenirs(petID: petID, limit: 40)
        async let economyTask = service.fetchEconomy(petID: petID)
        var pendingIllustratedGuide: IllustratedGuide?

        if let nextDayPlan = try? await dayPlanTask {
            dayPlan = nextDayPlan
            cache.store(nextDayPlan, kind: .dayPlan)
        } else if dayPlan == nil, let cached = cache.load(DayPlan.self, kind: .dayPlan) {
            dayPlan = cached.value
        }
        if let nextDNA = try? await dnaTask {
            dna = nextDNA
            cache.store(nextDNA, kind: .dna)
        } else if dna == nil, let cached = cache.load(PetDNA.self, kind: .dna) {
            dna = cached.value
        }
        if let nextWorldSnapshot = try? await worldSnapshotTask {
            worldSnapshot = nextWorldSnapshot
            cache.store(nextWorldSnapshot, kind: .worldSnapshot)
        }
        if let nextJourneyPlan = try? await journeyPlanTask {
            journeyPlan = nextJourneyPlan
            remoteRoutePlan = nextJourneyPlan.compatibilityRoutePlan
            cache.store(nextJourneyPlan, kind: .journeyPlan)
        } else if let fallbackRoutePlan = try? await service.fetchRoutePlan(petID: petID) {
            journeyPlan = nil
            remoteRoutePlan = fallbackRoutePlan
        } else if journeyPlan == nil, let cached = cache.load(JourneyPlan.self, kind: .journeyPlan) {
            journeyPlan = cached.value
            remoteRoutePlan = cached.value.compatibilityRoutePlan
        }
        if let nextIllustratedGuide = try? await illustratedGuideTask {
            illustratedGuide = nextIllustratedGuide
            pendingIllustratedGuide = nextIllustratedGuide
            cache.store(nextIllustratedGuide, kind: .illustratedGuide)
        } else if illustratedGuide == nil, let cached = cache.load(IllustratedGuide.self, kind: .illustratedGuide) {
            illustratedGuide = cached.value
        }
        if let nextPhotoMission = try? await photoMissionTask {
            photoMission = nextPhotoMission
        }
        if let nextTravelQuests = try? await travelQuestTask {
            travelQuests = nextTravelQuests
            cache.store(nextTravelQuests, kind: .travelQuests)
            await refreshTravelBag()
        } else if travelQuests.isEmpty, let cached = cache.load([TravelQuest].self, kind: .travelQuests) {
            travelQuests = cached.value
        }
        if let nextSouvenirs = try? await souvenirTask {
            souvenirs = nextSouvenirs
            cache.store(nextSouvenirs, kind: .souvenirs)
        } else if souvenirs.isEmpty, let cached = cache.load([SouvenirItem].self, kind: .souvenirs) {
            souvenirs = cached.value
        }
        if let nextEconomy = try? await economyTask {
            economy = nextEconomy
            cache.store(nextEconomy, kind: .economy)
        } else if economy == nil, let cached = cache.load(EconomyResponse.self, kind: .economy) {
            economy = cached.value
        }
        if let pendingIllustratedGuide {
            await generateIllustratedGuideIfNeeded(pendingIllustratedGuide)
        }
    }

    func refreshDetails() async {
        do {
            async let dayPlan = service.fetchDayPlan(petID: petID)
            async let dna = service.fetchDNA(petID: petID)
            async let worldSnapshot = service.fetchWorldSnapshot(petID: petID)
            async let petGuide = service.fetchPetGuide(petID: petID)
            async let illustratedGuide = service.fetchIllustratedGuide(petID: petID)
            async let travelQuests = service.fetchTravelQuests(petID: petID, limit: 8)
            async let souvenirs = service.fetchSouvenirs(petID: petID, limit: 40)
            async let economy = service.fetchEconomy(petID: petID)
            self.dayPlan = try await dayPlan
            self.dna = try await dna
            self.worldSnapshot = try? await worldSnapshot
            self.petGuide = try? await petGuide
            let nextIllustratedGuide = try? await illustratedGuide
            self.illustratedGuide = nextIllustratedGuide
            self.travelQuests = (try? await travelQuests) ?? self.travelQuests
            self.souvenirs = (try? await souvenirs) ?? self.souvenirs
            self.economy = (try? await economy) ?? self.economy
            await refreshTravelBag()
            await refreshRoutePlan()
            await refreshPhotoMission()
            if let nextIllustratedGuide {
                await generateIllustratedGuideIfNeeded(nextIllustratedGuide)
            }
        } catch {
            toastMessage = "细节暂时没有同步完整。"
        }
    }

    func updateDNA(_ nextDNA: PetDNA) async {
        isUpdatingDNA = true
        defer { isUpdatingDNA = false }
        do {
            dna = try await service.updateDNA(petID: petID, dna: nextDNA)
            toastMessage = "通讯 DNA 已更新。"
        } catch {
            toastMessage = "通讯 DNA 暂时保存失败。"
        }
    }

    private func generateIllustratedGuideIfNeeded(_ guide: IllustratedGuide) async {
        guard illustratedGuideNeedsImage(guide), !isGeneratingIllustratedGuide else { return }
        guard !illustratedGuideGenerationIDs.contains(guide.id) else { return }
        illustratedGuideGenerationIDs.insert(guide.id)
        isGeneratingIllustratedGuide = true
        defer { isGeneratingIllustratedGuide = false }

        do {
            let generatedGuide = try await service.generateIllustratedGuide(petID: petID)
            illustratedGuide = generatedGuide
            if illustratedGuideHasImage(generatedGuide) {
                toastMessage = "TA 的手绘旅程图画好了。"
            } else if generatedGuide.status == .failed {
                toastMessage = "这套手账图暂时没画出来，稍后再试。"
            }
        } catch {
            toastMessage = "手绘旅程图还在路上，信号好一点会再试。"
        }
    }

    private func illustratedGuideNeedsImage(_ guide: IllustratedGuide) -> Bool {
        if illustratedGuideHasImage(guide), guide.status == .ready {
            return false
        }
        guard let pages = guide.pages, !pages.isEmpty else {
            return guide.imageURL == nil && guide.thumbnailURL == nil
        }
        return pages.contains { $0.imageURL == nil && $0.thumbnailURL == nil }
    }

    private func illustratedGuideHasImage(_ guide: IllustratedGuide) -> Bool {
        if guide.imageURL != nil || guide.thumbnailURL != nil {
            return true
        }
        return guide.pages?.contains { $0.imageURL != nil || $0.thumbnailURL != nil } ?? false
    }

    func refreshRoutePlan() async {
        do {
            let nextJourneyPlan = try await service.fetchJourneyPlan(petID: petID)
            journeyPlan = nextJourneyPlan
            remoteRoutePlan = nextJourneyPlan.compatibilityRoutePlan
        } catch {
            do {
                journeyPlan = nil
                remoteRoutePlan = try await service.fetchRoutePlan(petID: petID)
            } catch {
                toastMessage = "路线还没有同步完整。"
            }
        }
    }

    func refreshPhotoMission() async {
        do {
            photoMission = try await service.fetchPhotoMission(petID: petID)
        } catch {
            photoMission = nil
        }
    }

    func hasReceivedPhotoMission(_ mission: PhotoMission?) -> Bool {
        guard let mission else { return false }
        return receivedPhotoMissionIDs.contains(mission.id)
    }

    func translateLatestThought() async {
        guard let thought = status?.agentState.latestThought else { return }
        if visibleThoughtTranslation?.thoughtID == thought.id {
            visibleThoughtTranslation = nil
            return
        }
        if let cached = translationCache[thought.id] {
            visibleThoughtTranslation = cached
            return
        }
        guard thought.translationAvailable else {
            toastMessage = "这句话还没有翻译出来。"
            return
        }

        isTranslatingThought = true
        defer { isTranslatingThought = false }
        do {
            let translation = try await service.fetchThoughtTranslation(petID: petID, thoughtID: thought.id)
            translationCache[thought.id] = translation
            visibleThoughtTranslation = translation
        } catch {
            toastMessage = "翻译信号有点弱，稍后再试。"
        }
    }

    func receiveCurrentPhoto() async {
        guard !isGeneratingPhoto else { return }
        isGeneratingPhoto = true
        defer { isGeneratingPhoto = false }

        do {
            let missionID = photoMission?.id
            _ = try await service.generateSelfie(petID: petID)
            if let missionID {
                markPhotoMissionReceived(missionID)
            }
            hasUnreadPostcard = true
            toastMessage = "手机里多了一张此刻照片。"
            PetPushRegistrationCoordinator.shared.requestAuthorizationForUserMoment()
            await refreshStatus()
            await refreshPhotoMission()
        } catch {
            toastMessage = "这张照片还没准备好。"
        }
    }

    func sendOwnerMessage(_ message: String) async {
        let clean = message.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !clean.isEmpty, !isSendingOwnerMessage else { return }
        let receiptID = UUID()
        appendOwnerMessageReceipt(
            OwnerMessageReceipt(
                id: receiptID,
                text: clean,
                timestamp: Date(),
                state: .sending,
                response: nil,
                decision: nil
            )
        )
        isSendingOwnerMessage = true
        defer { isSendingOwnerMessage = false }

        do {
            let response = try await service.sendOwnerMessage(
                petID: petID,
                request: OwnerMessageRequest(message: clean, intentHint: "owner_suggestion_or_companion_message")
            )
            updateOwnerMessageReceipt(
                id: receiptID,
                state: .delivered,
                response: response.message,
                decision: response.decision
            )
            toastMessage = response.message
            if let updatedStatus = response.updatedStatus {
                status = updatedStatus
                visibleThoughtTranslation = nil
                lastPostcardCount = updatedStatus.postcards.count
            } else {
                await refreshStatus()
            }
            await refreshPhotoMission()
        } catch {
            // 断网时不丢话：先收进发件队列，信号恢复后由 drainOutboxIfNeeded 自动送出。
            if case PetJourneyError.offline = error {
                outbox.enqueue(text: clean)
                updateOwnerMessageReceipt(
                    id: receiptID,
                    state: .sending,
                    response: "信号暂时没有接通，这句话已经收好，恢复后会自动送出。",
                    decision: nil
                )
                toastMessage = "这句话已经收好，信号恢复后会自动送出。"
            } else {
                updateOwnerMessageReceipt(
                    id: receiptID,
                    state: .failed,
                    response: "这句话暂时没有送到，等信号好一点可以再发一次。",
                    decision: nil
                )
                toastMessage = "这条讯息没有送达，等信号好一点再试。"
            }
        }
    }

    func sendFeedback(liked: Bool) async {
        guard let city = status?.agentState.location else { return }
        do {
            let response = try await service.sendFeedback(
                FeedbackRequest(petID: petID, city: city, liked: liked)
            )
            toastMessage = response.message
            if let updatedStatus = response.updatedStatus {
                status = updatedStatus
                visibleThoughtTranslation = nil
                lastPostcardCount = updatedStatus.postcards.count
            } else {
                await refreshStatus()
            }
        } catch {
            toastMessage = "这次回应没有送达。"
        }
    }

    func refreshTravelTools() async {
        do {
            async let quests = service.fetchTravelQuests(petID: petID, limit: 8)
            async let souvenirs = service.fetchSouvenirs(petID: petID, limit: 40)
            travelQuests = try await quests
            self.souvenirs = try await souvenirs
            await refreshTravelBag()
        } catch {
            toastMessage = "旅行小包还没有同步完整。"
        }
    }

    func createTravelQuest(message: String) async {
        let clean = message.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !clean.isEmpty, !isCreatingTravelQuest else { return }
        isCreatingTravelQuest = true
        defer { isCreatingTravelQuest = false }
        do {
            let quest = try await service.createTravelQuest(
                petID: petID,
                request: TravelWishRequest(
                    message: clean,
                    destination: nil,
                    eventName: nil,
                    preferredStartDate: nil
                )
            )
            travelQuests.insertOrReplaceFirst(quest)
            await refreshTravelBag()
            toastMessage = "TA 先整理好了一份小攻略。"
        } catch {
            toastMessage = "这份旅行愿望暂时没有送到。"
        }
    }

    func openWorldCupQuest(
        host: WorldCupHostCity,
        bagItems: Set<WorldCupBagItem>,
        ownerMessage: String?
    ) async {
        guard !isOpeningWorldCupQuest else { return }
        isOpeningWorldCupQuest = true
        defer { isOpeningWorldCupQuest = false }

        let cleanMessage = ownerMessage?.trimmingCharacters(in: .whitespacesAndNewlines)
        let invitationMessage = "收到一封远方球场邀请。想先看看 \(host.questDestination) 的世界杯球场灯光，但不要打断现在的旅程，先放进旅行包，等今天这段路走完再决定。"

        do {
            let quest = try await service.createTravelQuest(
                petID: petID,
                request: TravelWishRequest(
                    message: invitationMessage,
                    destination: host.questDestination,
                    eventName: "世界杯特别旅程",
                    preferredStartDate: nil
                )
            )
            travelQuests.insertOrReplaceFirst(quest)

            let packedItems = bagItems
                .sorted { $0.sortOrder < $1.sortOrder }
                .map(\.travelBagInput)
            if !packedItems.isEmpty || cleanMessage?.isEmpty == false {
                let bag = try await service.packTravelBag(
                    petID: petID,
                    request: TravelBagPackRequest(
                        questID: quest.id,
                        items: packedItems,
                        ownerMessage: cleanMessage?.isEmpty == false ? cleanMessage : nil
                    )
                )
                travelBag = bag
                attachTravelBagToQuest(bag)
            }

            toastMessage = "远方球场邀请已放进旅行包，TA 会先走完今天这段路。"
        } catch {
            toastMessage = "这封远方邀请暂时没有放好。"
        }
    }

    func prepareActiveTravelQuest() async {
        guard let quest = activeTravelQuest, !isCreatingTravelQuest else { return }
        isCreatingTravelQuest = true
        defer { isCreatingTravelQuest = false }
        do {
            let updated = try await service.prepareTravelQuest(petID: petID, questID: quest.id)
            travelQuests.insertOrReplaceFirst(updated)
            if let plan = updated.journeyPlan {
                journeyPlan = plan
                remoteRoutePlan = plan.compatibilityRoutePlan
            }
            toastMessage = "TA 开始检查小包和路线。"
        } catch {
            toastMessage = "这段出发准备还没有同步成功。"
        }
    }

    func packTravelBag(items: [TravelBagItemInput], ownerMessage: String? = nil) async {
        guard !isPackingTravelBag else { return }
        let cleanMessage = ownerMessage?.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !items.isEmpty || cleanMessage?.isEmpty == false else { return }
        isPackingTravelBag = true
        defer { isPackingTravelBag = false }
        do {
            let bag = try await service.packTravelBag(
                petID: petID,
                request: TravelBagPackRequest(
                    questID: activeTravelQuest?.id,
                    items: items,
                    ownerMessage: cleanMessage?.isEmpty == false ? cleanMessage : nil
                )
            )
            travelBag = bag
            attachTravelBagToQuest(bag)
            toastMessage = "小包已经收好。"
        } catch {
            toastMessage = "小包暂时没有装好。"
        }
    }

    func collectSouvenirsForActiveQuest() async {
        guard let quest = activeTravelQuest, !isCollectingSouvenir else { return }
        isCollectingSouvenir = true
        defer { isCollectingSouvenir = false }
        do {
            let response = try await service.collectTravelQuestSouvenirsWithEconomy(petID: petID, questID: quest.id)
            mergeSouvenirs(response.items)
            await refreshEconomy()
            toastMessage = "TA 带回了一点小东西。"
        } catch {
            toastMessage = "带回物还没有同步成功。"
        }
    }

    func sellSouvenir(_ souvenir: SouvenirItem) async {
        guard souvenir.isSellable, !mutatingInventoryItemIDs.contains(souvenir.id) else { return }
        mutatingInventoryItemIDs.insert(souvenir.id)
        defer { mutatingInventoryItemIDs.remove(souvenir.id) }
        do {
            let response = try await service.sellItem(
                petID: petID,
                itemID: souvenir.id,
                request: SellItemRequest(
                    clientRequestID: UUID().uuidString,
                    expectedItemVersion: souvenir.effectiveVersion
                )
            )
            replaceSouvenir(response.item)
            await refreshEconomy()
            toastMessage = "TA 把这件小收藏换成了 \(response.transaction.amounts.travelCoin) 旅贝。"
        } catch {
            toastMessage = "这件小收藏暂时没有卖出去。"
        }
    }

    func archiveSouvenir(_ souvenir: SouvenirItem) async {
        guard souvenir.effectiveStatus == .owned, !mutatingInventoryItemIDs.contains(souvenir.id) else { return }
        mutatingInventoryItemIDs.insert(souvenir.id)
        defer { mutatingInventoryItemIDs.remove(souvenir.id) }
        do {
            let response = try await service.archiveItem(
                petID: petID,
                itemID: souvenir.id,
                request: ArchiveItemRequest(
                    clientRequestID: UUID().uuidString,
                    expectedItemVersion: souvenir.effectiveVersion
                )
            )
            replaceSouvenir(response.item)
            await refreshEconomy()
            toastMessage = "已经放进珍藏里。"
        } catch {
            toastMessage = "这件小收藏暂时没有归档。"
        }
    }

    func markPostcardsRead() {
        hasUnreadPostcard = false
    }

    func clearToast() {
        toastMessage = nil
    }

    private func markPhotoMissionReceived(_ missionID: String) {
        receivedPhotoMissionIDs.insert(missionID)
        UserDefaults.standard.set(Array(receivedPhotoMissionIDs), forKey: receivedPhotoMissionStorageKey)
    }

    private func appendOwnerMessageReceipt(_ receipt: OwnerMessageReceipt) {
        ownerMessageReceipts.append(receipt)
        if ownerMessageReceipts.count > 5 {
            ownerMessageReceipts.removeFirst(ownerMessageReceipts.count - 5)
        }
    }

    private func updateOwnerMessageReceipt(
        id: UUID,
        state: OwnerMessageReceipt.DeliveryState,
        response: String?,
        decision: String?
    ) {
        guard let index = ownerMessageReceipts.firstIndex(where: { $0.id == id }) else { return }
        ownerMessageReceipts[index].state = state
        ownerMessageReceipts[index].response = response
        ownerMessageReceipts[index].decision = decision
    }

    private func attachTravelBagToQuest(_ bag: TravelBag) {
        guard let questID = bag.questID,
              let index = travelQuests.firstIndex(where: { $0.id == questID }) else { return }
        let quest = travelQuests[index]
        travelQuests[index] = TravelQuest(
            id: quest.id,
            petID: quest.petID,
            questType: quest.questType,
            status: quest.status,
            currentPhase: quest.currentPhase,
            tripType: quest.tripType,
            returnPolicy: quest.returnPolicy,
            originAnchor: quest.originAnchor,
            ownerMessage: quest.ownerMessage,
            destination: quest.destination,
            eventName: quest.eventName,
            preferredStartDate: quest.preferredStartDate,
            autonomyDecision: quest.autonomyDecision,
            currentPhaseMessage: quest.currentPhaseMessage,
            guide: quest.guide,
            travelBag: bag,
            journeyPlan: quest.journeyPlan,
            postEventOptions: quest.postEventOptions,
            souvenirPreview: quest.souvenirPreview,
            selectedNextOptionID: quest.selectedNextOptionID,
            worldcupEvent: quest.worldcupEvent,
            createdAt: quest.createdAt,
            updatedAt: Date()
        )
    }

    private func refreshTravelBag() async {
        do {
            travelBag = try await service.fetchTravelBag(petID: petID, questID: activeTravelQuest?.id)
        } catch {
            travelBag = nil
        }
    }

    private func refreshEconomy() async {
        if let nextEconomy = try? await service.fetchEconomy(petID: petID) {
            economy = nextEconomy
        }
    }

    private func mergeSouvenirs(_ items: [SouvenirItem]) {
        var seen = Set<String>()
        souvenirs = (items + souvenirs)
            .filter { seen.insert($0.id).inserted }
            .sorted(by: { $0.obtainedAt > $1.obtainedAt })
    }

    private func replaceSouvenir(_ item: SouvenirItem) {
        if let index = souvenirs.firstIndex(where: { $0.id == item.id }) {
            souvenirs[index] = item
        } else {
            souvenirs.insert(item, at: 0)
        }
        souvenirs.sort(by: { $0.obtainedAt > $1.obtainedAt })
    }
}

private extension Array where Element == TravelQuest {
    mutating func insertOrReplaceFirst(_ quest: TravelQuest) {
        if let index = firstIndex(where: { $0.id == quest.id }) {
            self[index] = quest
        } else {
            insert(quest, at: 0)
        }
        sort(by: { $0.updatedAt > $1.updatedAt })
    }
}
