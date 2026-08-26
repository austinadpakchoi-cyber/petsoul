import Foundation

@MainActor
final class RemotePetJourneyService: PetJourneyService {
    private let client: APIClient
    private var encoder: JSONEncoder { client.encoder }

    /// 会话令牌由 AppSessionStore 提供；有值时所有请求自动带 Authorization 头
    var authTokenProvider: (() -> String?)?

    init(baseURL: URL, session: URLSession = .shared) {
        client = APIClient(baseURL: baseURL, session: session)
    }

    func createPet(request: CreatePetRequest) async throws -> CreatePetResponse {
        let dnaData = try encoder.encode(request.dna)
        guard let dnaString = String(data: dnaData, encoding: .utf8) else {
            throw PetJourneyError.requestFailed("DNA 数据暂时无法编码")
        }

        var urlRequest = URLRequest(url: endpoint("/api/v1/create_pet"))
        urlRequest.httpMethod = "POST"
        let boundary = "Boundary-\(UUID().uuidString)"
        urlRequest.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        urlRequest.httpBody = makeMultipartBody(
            boundary: boundary,
            fields: [
                "pet_name": request.name,
                "pet_type": request.petType.rawValue,
                "dna": dnaString
            ],
            fileField: request.photoData.map {
                MultipartFile(
                    fieldName: "pet_photo",
                    filename: request.photoFilename ?? "pet-photo.jpg",
                    mimeType: "image/jpeg",
                    data: $0
                )
            }
        )
        return try await decode(CreatePetResponse.self, from: urlRequest)
    }

    func fetchAgentStatus(petID: String) async throws -> AgentStatus {
        try await get(AgentStatus.self, path: "/api/v1/agent_status/\(petID)")
    }

    func fetchDayPlan(petID: String) async throws -> DayPlan {
        try await get(DayPlan.self, path: "/api/v1/day_plan/\(petID)")
    }

    func fetchDNA(petID: String) async throws -> PetDNA {
        try await get(PetDNA.self, path: "/api/v1/pet_dna/\(petID)")
    }

    func updateDNA(petID: String, dna: PetDNA) async throws -> PetDNA {
        try await patchJSON(PetDNA.self, path: "/api/v1/pet_dna/\(petID)", body: dna)
    }

    func fetchCityPosition(petID: String) async throws -> CityPosition {
        try await get(CityPosition.self, path: "/api/v1/pets/\(petID)/city_position")
    }

    func fetchJourneyPlan(petID: String) async throws -> JourneyPlan {
        try await get(JourneyPlan.self, path: "/api/v1/pets/\(petID)/journey_plan")
    }

    func fetchWorldSnapshot(petID: String) async throws -> WorldSimulationSnapshot {
        try await get(WorldSimulationSnapshot.self, path: "/api/v1/pets/\(petID)/world_snapshot")
    }

    func fetchPetGuide(petID: String) async throws -> PetAuthoredGuide {
        try await get(PetAuthoredGuide.self, path: "/api/v1/pets/\(petID)/pet_guide")
    }

    func fetchIllustratedGuide(petID: String) async throws -> IllustratedGuide {
        try await get(IllustratedGuide.self, path: "/api/v1/pets/\(petID)/illustrated_guide")
    }

    func generateIllustratedGuide(petID: String) async throws -> IllustratedGuide {
        var request = URLRequest(url: endpoint("/api/v1/pets/\(petID)/illustrated_guide/generate"))
        request.httpMethod = "POST"
        request.timeoutInterval = 720
        return try await decode(IllustratedGuide.self, from: request)
    }

    func fetchRoutePlan(petID: String) async throws -> RemoteJourneyRoutePlan {
        try await get(RemoteJourneyRoutePlan.self, path: "/api/v1/pets/\(petID)/route_plan")
    }

    func fetchPhotoMission(petID: String) async throws -> PhotoMission {
        try await get(PhotoMission.self, path: "/api/v1/pets/\(petID)/photo_mission")
    }

    func fetchTravelQuests(petID: String, limit: Int) async throws -> [TravelQuest] {
        try await get([TravelQuest].self, path: "/api/v1/pets/\(petID)/travel_quests?limit=\(limit)")
    }

    func createTravelQuest(petID: String, request: TravelWishRequest) async throws -> TravelQuest {
        try await postJSON(TravelQuest.self, path: "/api/v1/pets/\(petID)/travel_quests", body: request)
    }

    func prepareTravelQuest(petID: String, questID: String) async throws -> TravelQuest {
        var request = URLRequest(url: endpoint("/api/v1/pets/\(petID)/travel_quests/\(questID)/prepare_departure"))
        request.httpMethod = "POST"
        return try await decode(TravelQuest.self, from: request)
    }

    func buildTravelQuestPostEventOptions(petID: String, questID: String) async throws -> TravelQuest {
        var request = URLRequest(url: endpoint("/api/v1/pets/\(petID)/travel_quests/\(questID)/post_event_options"))
        request.httpMethod = "POST"
        return try await decode(TravelQuest.self, from: request)
    }

    func selectTravelQuestNextStep(petID: String, questID: String, request: TravelQuestDecisionRequest) async throws -> TravelQuest {
        try await postJSON(TravelQuest.self, path: "/api/v1/pets/\(petID)/travel_quests/\(questID)/select_next_step", body: request)
    }

    func fetchTravelBag(petID: String, questID: String?) async throws -> TravelBag {
        if let questID, !questID.isEmpty {
            let encodedQuestID = questID.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? questID
            return try await get(TravelBag.self, path: "/api/v1/pets/\(petID)/travel_bag?quest_id=\(encodedQuestID)")
        }
        return try await get(TravelBag.self, path: "/api/v1/pets/\(petID)/travel_bag")
    }

    func packTravelBag(petID: String, request: TravelBagPackRequest) async throws -> TravelBag {
        try await postJSON(TravelBag.self, path: "/api/v1/pets/\(petID)/travel_bag", body: request)
    }

    func fetchSouvenirs(petID: String, limit: Int) async throws -> [SouvenirItem] {
        try await get([SouvenirItem].self, path: "/api/v1/pets/\(petID)/souvenirs?limit=\(limit)")
    }

    func fetchEconomy(petID: String) async throws -> EconomyResponse {
        try await get(EconomyResponse.self, path: "/api/v1/pets/\(petID)/economy")
    }

    func fetchInventory(petID: String, status: ItemStatus?, limit: Int) async throws -> InventoryResponse {
        let statusValue = status?.rawValue ?? "all"
        return try await get(InventoryResponse.self, path: "/api/v1/pets/\(petID)/inventory?status=\(statusValue)&limit=\(limit)")
    }

    func collectTravelQuestSouvenirsWithEconomy(petID: String, questID: String) async throws -> CollectSouvenirsResponse {
        var request = URLRequest(url: endpoint("/api/v1/pets/\(petID)/travel_quests/\(questID)/souvenirs/collect"))
        request.httpMethod = "POST"
        return try await decode(CollectSouvenirsResponse.self, from: request)
    }

    func sellItem(petID: String, itemID: String, request: SellItemRequest) async throws -> ItemMutationResponse {
        try await postJSON(ItemMutationResponse.self, path: "/api/v1/pets/\(petID)/items/\(itemID)/sell", body: request)
    }

    func archiveItem(petID: String, itemID: String, request: ArchiveItemRequest) async throws -> ItemMutationResponse {
        try await postJSON(ItemMutationResponse.self, path: "/api/v1/pets/\(petID)/items/\(itemID)/archive", body: request)
    }

    func fetchThoughtTranslation(petID: String, thoughtID: String) async throws -> ThoughtTranslation {
        let encodedPetID = petID.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? petID
        return try await get(
            ThoughtTranslation.self,
            path: "/api/v1/thoughts/\(thoughtID)/translation?pet_id=\(encodedPetID)"
        )
    }

    func sendFeedback(_ request: FeedbackRequest) async throws -> FeedbackResponse {
        var urlRequest = URLRequest(url: endpoint("/api/v1/feedback"))
        urlRequest.httpMethod = "POST"
        let boundary = "Boundary-\(UUID().uuidString)"
        urlRequest.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        urlRequest.httpBody = makeMultipartBody(
            boundary: boundary,
            fields: [
                "pet_id": request.petID,
                "city": request.city,
                "liked": request.liked ? "true" : "false"
            ],
            fileField: nil
        )
        return try await decode(FeedbackResponse.self, from: urlRequest)
    }

    func sendOwnerMessage(petID: String, request: OwnerMessageRequest) async throws -> OwnerMessageResponse {
        try await postJSON(OwnerMessageResponse.self, path: "/api/v1/pets/\(petID)/messages", body: request)
    }

    func fetchCommunicatorMessages(petID: String, limit: Int) async throws -> [CommunicatorMessage] {
        try await get([CommunicatorMessage].self, path: "/api/v1/pets/\(petID)/communicator/messages?limit=\(limit)")
    }

    func sendCommunicatorMessage(petID: String, request: CommunicatorSendRequest) async throws -> CommunicatorSendResponse {
        try await postJSON(CommunicatorSendResponse.self, path: "/api/v1/pets/\(petID)/communicator/messages", body: request)
    }

    func sendCommunicatorPhoto(petID: String, imageData: Data, caption: String?) async throws -> CommunicatorSendResponse {
        var urlRequest = URLRequest(url: endpoint("/api/v1/pets/\(petID)/communicator/messages/photo"))
        urlRequest.httpMethod = "POST"
        let boundary = "Boundary-\(UUID().uuidString)"
        urlRequest.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        var fields: [String: String] = [:]
        if let caption, !caption.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            fields["text"] = caption
        }
        urlRequest.httpBody = makeMultipartBody(
            boundary: boundary,
            fields: fields,
            fileField: MultipartFile(
                fieldName: "image",
                filename: "owner-photo.jpg",
                mimeType: "image/jpeg",
                data: imageData
            )
        )
        return try await decode(CommunicatorSendResponse.self, from: urlRequest)
    }

    func fetchMoments(petID: String, limit: Int) async throws -> [CommunicatorMoment] {
        try await get([CommunicatorMoment].self, path: "/api/v1/pets/\(petID)/communicator/moments?limit=\(limit)")
    }

    func reactToMoment(petID: String, momentID: String, request: MomentReactionRequest) async throws -> MomentReactionResponse {
        try await postJSON(
            MomentReactionResponse.self,
            path: "/api/v1/pets/\(petID)/communicator/moments/\(momentID)/reaction",
            body: request
        )
    }

    func registerPushDevice(_ request: DeviceRegistrationRequest) async throws -> DeviceRegistrationResponse {
        try await postJSON(DeviceRegistrationResponse.self, path: "/api/v1/push/register", body: request)
    }

    func unregisterPushDevice(_ request: DeviceRegistrationRequest) async throws {
        let _: SuccessResponse = try await postJSON(SuccessResponse.self, path: "/api/v1/push/unregister", body: request)
    }

    func fetchNotifications(petID: String, limit: Int) async throws -> [NotificationDelivery] {
        try await get([NotificationDelivery].self, path: "/api/v1/pets/\(petID)/notifications?limit=\(limit)")
    }

    func fetchMemories(petID: String, limit: Int) async throws -> [MemoryRecord] {
        try await get([MemoryRecord].self, path: "/api/v1/pets/\(petID)/memories?limit=\(limit)")
    }

    func addMemory(petID: String, request: MemoryCreateRequest) async throws -> MemoryRecord {
        try await postJSON(MemoryRecord.self, path: "/api/v1/pets/\(petID)/memories", body: request)
    }

    func updateMemory(petID: String, memoryID: String, request: MemoryUpdateRequest) async throws -> MemoryRecord {
        try await patchJSON(MemoryRecord.self, path: "/api/v1/pets/\(petID)/memories/\(memoryID)", body: request)
    }

    func deleteMemory(petID: String, memoryID: String) async throws {
        let _: MemoryDeleteResponse = try await delete(MemoryDeleteResponse.self, path: "/api/v1/pets/\(petID)/memories/\(memoryID)")
    }

    func searchMemories(petID: String, request: MemorySearchRequest) async throws -> MemorySearchResponse {
        try await postJSON(MemorySearchResponse.self, path: "/api/v1/pets/\(petID)/memories/search", body: request)
    }

    func generateSelfie(petID: String) async throws -> Postcard {
        var request = URLRequest(url: endpoint("/api/v1/pets/\(petID)/generate_selfie"))
        request.httpMethod = "POST"
        return try await decode(Postcard.self, from: request)
    }

    func fetchStreetRank(petID: String, theme: String) async throws -> StreetRankResponse {
        let encodedTheme = theme.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? theme
        return try await get(StreetRankResponse.self, path: "/api/v1/pets/\(petID)/street_rank?theme=\(encodedTheme)")
    }

    func signInWithApple(request: AppleSignInRequest) async throws -> AuthSessionResponse {
        try await postJSON(AuthSessionResponse.self, path: "/api/v1/auth/apple", body: request)
    }

    func fetchMe() async throws -> MeResponse {
        try await get(MeResponse.self, path: "/api/v1/me")
    }

    func claimPet(petID: String) async throws -> MeResponse {
        try await postJSON(MeResponse.self, path: "/api/v1/me/claim_pet", body: ClaimPetRequest(petID: petID))
    }

    private func get<T: Decodable>(_ type: T.Type, path: String) async throws -> T {
        var request = URLRequest(url: endpoint(path))
        request.httpMethod = "GET"
        return try await decode(T.self, from: request, retry: .idempotent)
    }

    private func postJSON<T: Decodable, Body: Encodable>(_ type: T.Type, path: String, body: Body) async throws -> T {
        var request = URLRequest(url: endpoint(path))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try encoder.encode(body)
        return try await decode(type, from: request)
    }

    private func patchJSON<T: Decodable, Body: Encodable>(_ type: T.Type, path: String, body: Body) async throws -> T {
        var request = URLRequest(url: endpoint(path))
        request.httpMethod = "PATCH"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try encoder.encode(body)
        return try await decode(type, from: request)
    }

    private func delete<T: Decodable>(_ type: T.Type, path: String) async throws -> T {
        var request = URLRequest(url: endpoint(path))
        request.httpMethod = "DELETE"
        return try await decode(type, from: request)
    }

    /// 传输与重试交给 APIClient；APIError 在此边界归一成 PetJourneyError，调用点无感。
    private func decode<T: Decodable>(_ type: T.Type, from request: URLRequest, retry: RetryPolicy = .none) async throws -> T {
        var request = request
        if let token = authTokenProvider?(), !token.isEmpty {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        do {
            return try await client.send(type, request: request, retry: retry)
        } catch let error as APIError {
            throw error.asPetJourneyError
        }
    }

    private func endpoint(_ path: String) -> URL {
        client.endpoint(path)
    }

    private struct MultipartFile {
        var fieldName: String
        var filename: String
        var mimeType: String
        var data: Data
    }

    private struct SuccessResponse: Decodable {
        var success: Bool
    }

    private func makeMultipartBody(boundary: String, fields: [String: String], fileField: MultipartFile?) -> Data {
        var body = Data()
        for (name, value) in fields {
            body.appendString("--\(boundary)\r\n")
            body.appendString("Content-Disposition: form-data; name=\"\(name)\"\r\n\r\n")
            body.appendString("\(value)\r\n")
        }

        if let fileField {
            body.appendString("--\(boundary)\r\n")
            body.appendString("Content-Disposition: form-data; name=\"\(fileField.fieldName)\"; filename=\"\(fileField.filename)\"\r\n")
            body.appendString("Content-Type: \(fileField.mimeType)\r\n\r\n")
            body.append(fileField.data)
            body.appendString("\r\n")
        }

        body.appendString("--\(boundary)--\r\n")
        return body
    }
}

private extension Data {
    mutating func appendString(_ string: String) {
        append(Data(string.utf8))
    }
}
