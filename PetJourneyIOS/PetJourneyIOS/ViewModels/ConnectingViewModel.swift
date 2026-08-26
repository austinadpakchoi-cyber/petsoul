import Foundation

/// 「调频连接」阶段的业务：把宠物创建请求发出去，推进连接三阶段状态。
/// 原 ConnectingView 在 View 结构体里直接 createPet + 状态机，下沉到 VM；动画交给 View 层。
///
/// 账号模式（claimsToAccount == true）：宠物创建成功后立刻绑定到登录账号，
/// 绑定失败不丢弃结果，重试只重新绑定、不重复创建宠物。
@MainActor
final class ConnectingViewModel: ObservableObject {
    let draft: OnboardingDraft
    let service: any PetJourneyService
    let claimsToAccount: Bool

    @Published var stageIndex = 0
    @Published var response: CreatePetResponse?
    @Published var errorMessage: String?
    @Published var hasStarted = false

    private var createdResponse: CreatePetResponse?
    private var pendingClaim = false

    init(draft: OnboardingDraft, service: any PetJourneyService, claimsToAccount: Bool = false) {
        self.draft = draft
        self.service = service
        self.claimsToAccount = claimsToAccount
    }

    /// View 首次出现时调用一次；幂等，避免 `.task` 重复触发。
    func start() async {
        guard !hasStarted else { return }
        hasStarted = true
        await connect()
    }

    func connect() async {
        errorMessage = nil
        // 宠物已创建、只差账号绑定：重试时只重新绑定，绝不重复创建。
        if let created = createdResponse, pendingClaim {
            await claimOnly(created)
            return
        }
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
            createdResponse = created
            if claimsToAccount {
                pendingClaim = true
                await claimOnly(created)
                return
            }
            response = created
            stageIndex = 2
        } catch {
            errorMessage = "这次连接没有稳定下来，可以稍后再试。"
        }
    }

    private func claimOnly(_ created: CreatePetResponse) async {
        do {
            _ = try await service.claimPet(petID: created.petID)
            pendingClaim = false
            errorMessage = nil
            response = created
            stageIndex = 2
        } catch {
            response = nil
            errorMessage = "TA 已经启程，但还没跟你的账号连上。稍后再试一次。"
        }
    }
}
