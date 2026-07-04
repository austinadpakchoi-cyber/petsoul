import Foundation

enum PetJourneyError: LocalizedError, Equatable {
    case invalidBaseURL
    case invalidResponse
    case noPetSession
    case offline
    case requestFailed(String)

    var errorDescription: String? {
        switch self {
        case .invalidBaseURL:
            "baseURL 无效"
        case .invalidResponse:
            "服务返回的数据暂时无法识别"
        case .noPetSession:
            "还没有建立宠物旅程"
        case .offline:
            "信号暂时没有接通，稍后会自动再试。"
        case .requestFailed(let message):
            message
        }
    }
}

@MainActor
protocol PetJourneyService: AnyObject {
    func createPet(request: CreatePetRequest) async throws -> CreatePetResponse
    func fetchAgentStatus(petID: String) async throws -> AgentStatus
    func fetchDayPlan(petID: String) async throws -> DayPlan
    func fetchDNA(petID: String) async throws -> PetDNA
    func updateDNA(petID: String, dna: PetDNA) async throws -> PetDNA
    func fetchCityPosition(petID: String) async throws -> CityPosition
    func fetchJourneyPlan(petID: String) async throws -> JourneyPlan
    func fetchWorldSnapshot(petID: String) async throws -> WorldSimulationSnapshot
    func fetchPetGuide(petID: String) async throws -> PetAuthoredGuide
    func fetchIllustratedGuide(petID: String) async throws -> IllustratedGuide
    func generateIllustratedGuide(petID: String) async throws -> IllustratedGuide
    func fetchRoutePlan(petID: String) async throws -> RemoteJourneyRoutePlan
    func fetchPhotoMission(petID: String) async throws -> PhotoMission
    func fetchTravelQuests(petID: String, limit: Int) async throws -> [TravelQuest]
    func createTravelQuest(petID: String, request: TravelWishRequest) async throws -> TravelQuest
    func prepareTravelQuest(petID: String, questID: String) async throws -> TravelQuest
    func buildTravelQuestPostEventOptions(petID: String, questID: String) async throws -> TravelQuest
    func selectTravelQuestNextStep(petID: String, questID: String, request: TravelQuestDecisionRequest) async throws -> TravelQuest
    func fetchTravelBag(petID: String, questID: String?) async throws -> TravelBag
    func packTravelBag(petID: String, request: TravelBagPackRequest) async throws -> TravelBag
    func fetchSouvenirs(petID: String, limit: Int) async throws -> [SouvenirItem]
    func fetchEconomy(petID: String) async throws -> EconomyResponse
    func fetchInventory(petID: String, status: ItemStatus?, limit: Int) async throws -> InventoryResponse
    func collectTravelQuestSouvenirsWithEconomy(petID: String, questID: String) async throws -> CollectSouvenirsResponse
    func collectTravelQuestSouvenirs(petID: String, questID: String) async throws -> [SouvenirItem]
    func sellItem(petID: String, itemID: String, request: SellItemRequest) async throws -> ItemMutationResponse
    func archiveItem(petID: String, itemID: String, request: ArchiveItemRequest) async throws -> ItemMutationResponse
    func fetchThoughtTranslation(petID: String, thoughtID: String) async throws -> ThoughtTranslation
    func sendFeedback(_ request: FeedbackRequest) async throws -> FeedbackResponse
    func sendOwnerMessage(petID: String, request: OwnerMessageRequest) async throws -> OwnerMessageResponse
    func fetchCommunicatorMessages(petID: String, limit: Int) async throws -> [CommunicatorMessage]
    func sendCommunicatorMessage(petID: String, request: CommunicatorSendRequest) async throws -> CommunicatorSendResponse
    func sendCommunicatorPhoto(petID: String, imageData: Data, caption: String?) async throws -> CommunicatorSendResponse
    func fetchMoments(petID: String, limit: Int) async throws -> [CommunicatorMoment]
    func reactToMoment(petID: String, momentID: String, request: MomentReactionRequest) async throws -> MomentReactionResponse
    func registerPushDevice(_ request: DeviceRegistrationRequest) async throws -> DeviceRegistrationResponse
    func unregisterPushDevice(_ request: DeviceRegistrationRequest) async throws
    func fetchNotifications(petID: String, limit: Int) async throws -> [NotificationDelivery]
    func fetchMemories(petID: String, limit: Int) async throws -> [MemoryRecord]
    func addMemory(petID: String, request: MemoryCreateRequest) async throws -> MemoryRecord
    func updateMemory(petID: String, memoryID: String, request: MemoryUpdateRequest) async throws -> MemoryRecord
    func deleteMemory(petID: String, memoryID: String) async throws
    func searchMemories(petID: String, request: MemorySearchRequest) async throws -> MemorySearchResponse
    func generateSelfie(petID: String) async throws -> Postcard
    func fetchCredentialPrompts(petID: String) async throws -> [PetCredentialPrompt]
    func fetchStreetRank(petID: String, theme: String) async throws -> StreetRankResponse
    func signInWithApple(request: AppleSignInRequest) async throws -> AuthSessionResponse
    func claimPet(petID: String) async throws -> MeResponse
}
