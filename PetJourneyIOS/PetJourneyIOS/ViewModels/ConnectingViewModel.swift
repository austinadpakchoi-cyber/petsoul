import Foundation

/// 「调频连接」阶段的业务：把宠物创建请求发出去，推进连接三阶段状态。
/// 原 ConnectingView 在 View 结构体里直接 createPet + 状态机，下沉到 VM；动画交给 View 层。
@MainActor
final class ConnectingViewModel: ObservableObject {
    let draft: OnboardingDraft
    let service: any PetJourneyService

    @Published var stageIndex = 0
    @Published var response: CreatePetResponse?
    @Published var errorMessage: String?
    @Published var hasStarted = false

    init(draft: OnboardingDraft, service: any PetJourneyService) {
        self.draft = draft
        self.service = service
    }

    /// View 首次出现时调用一次；幂等，避免 `.task` 重复触发。
    func start() async {
        guard !hasStarted else { return }
        hasStarted = true
        await connect()
    }

    func connect() async {
        errorMessage = nil
        response = nil
        do {
            stageIndex = 0
            try await Task.sleep(for: .seconds(1))
            stageIndex = 1
            try await Task.sleep(for: .seconds(1.2))
            let created = try await service.createPet(request: draft.createRequest)
            if let photoData = draft.photoData {
                PetAvatarStore.save(photoData, petID: created.petID)
            }
            response = created
            stageIndex = 2
        } catch {
            errorMessage = "这次连接没有稳定下来，可以稍后再试。"
        }
    }
}
