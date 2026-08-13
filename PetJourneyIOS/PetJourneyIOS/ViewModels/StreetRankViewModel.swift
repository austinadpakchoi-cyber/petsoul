import Foundation

/// 「这条街 TA 最想去哪」：街区心愿清单的加载状态与业务。
/// 原 StreetRankSheet 直接在 View 结构体里调用 service 并维护加载状态，下沉到 VM。
@MainActor
final class StreetRankViewModel: ObservableObject {
    let petID: String
    let service: any PetJourneyService
    let theme: String

    @Published var response: StreetRankResponse?
    @Published var isLoading = true
    @Published var errorMessage: String?

    init(petID: String, service: any PetJourneyService, theme: String = "street") {
        self.petID = petID
        self.service = service
        self.theme = theme
    }

    func load() async {
        defer { isLoading = false }
        do {
            response = try await service.fetchStreetRank(petID: petID, theme: theme)
        } catch {
            errorMessage = "这条街的信号还没接通，稍后再来听。"
        }
    }
}
