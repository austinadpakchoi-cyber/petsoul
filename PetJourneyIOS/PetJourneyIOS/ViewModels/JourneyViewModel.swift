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

    @Published var status: AgentStatus?
    @Published var dayPlan: DayPlan?
    @Published var dna: PetDNA?
    @Published var cityPosition: CityPosition?
    @Published var journeyPlan: JourneyPlan?
    @Published var worldSnapshot: WorldSimulationSnapshot?
    @Published var petGuide: PetAuthoredGuide?
    @Published var illustratedGuide: IllustratedGuide?
    @Published var remoteRoutePlan: RemoteJourneyRoutePlan?
    @Published var photoMission: PhotoMission?
    @Published var travelQuests: [TravelQuest] = []
    @Published var travelBag: TravelBag?
    @Published var souvenirs: [SouvenirItem] = []
    @Published var economy: EconomyResponse?
    @Published var visibleThoughtTranslation: ThoughtTranslation?
    @Published var isTranslatingThought = false
    @Published var isGeneratingPhoto = false
    @Published var isSendingOwnerMessage = false
    @Published var isCreatingTravelQuest = false
    @Published var isOpeningWorldCupQuest = false
    @Published var isPackingTravelBag = false
    @Published var isCollectingSouvenir = false
    @Published var mutatingInventoryItemIDs: Set<String> = []
    @Published var isGeneratingIllustratedGuide = false
    @Published var isUpdatingDNA = false
    @Published var receivedPhotoMissionIDs: Set<String>
    @Published var ownerMessageReceipts: [OwnerMessageReceipt] = []
    @Published var loadState: LoadState = .loading
    @Published var dataFreshness: DataFreshness = .fresh
    @Published var toastMessage: String?
    @Published var hasUnreadPostcard = false

    let petID: String
    let service: any PetJourneyService
    let cache: JourneyCacheRepository
    let outbox: OutboundMessageQueue
    let receivedPhotoMissionStorageKey: String
    var refreshTask: Task<Void, Never>?
    var hydrationTask: Task<Void, Never>?
    var translationCache: [String: ThoughtTranslation] = [:]
    var lastPostcardCount = 0
    var lastRefreshSucceededAt: Date?
    var illustratedGuideGenerationIDs: Set<String> = []

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

    /// 登录成功后把当前宠物认领到账号；成功返回会话凭据供上层落盘，失败返回 nil。
    func linkAccount(identityToken: String, fullName: String?) async -> AuthSessionResponse? {
        do {
            let auth = try await service.signInWithApple(
                request: AppleSignInRequest(identityToken: identityToken, displayName: fullName)
            )
            _ = try? await service.claimPet(petID: petID)
            toastMessage = "TA 的旅程已经和你连在一起了。"
            return auth
        } catch {
            return nil
        }
    }
}

extension Array where Element == TravelQuest {
    mutating func insertOrReplaceFirst(_ quest: TravelQuest) {
        if let index = firstIndex(where: { $0.id == quest.id }) {
            self[index] = quest
        } else {
            insert(quest, at: 0)
        }
        sort(by: { $0.updatedAt > $1.updatedAt })
    }
}
