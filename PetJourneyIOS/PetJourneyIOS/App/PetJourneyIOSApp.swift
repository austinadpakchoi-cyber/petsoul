import SwiftUI

@main
struct PetJourneyIOSApp: App {
    @UIApplicationDelegateAdaptor(PetJourneyAppDelegate.self) private var appDelegate
    @StateObject private var session: AppSessionStore
    @StateObject private var services: ServiceContainer

    init() {
        let session = AppSessionStore()
        _session = StateObject(wrappedValue: session)
        _services = StateObject(wrappedValue: ServiceContainer(session: session))
    }

    var body: some Scene {
        WindowGroup {
            AppRouter(service: services.journeyService)
                .environmentObject(session)
        }
    }
}

private enum AppRoute {
    case publicWorld
    case signIn
    case onboarding
    case connecting(OnboardingDraft)
    case petPicker
}

/// 路由门禁：
/// - Mock（开发演示）模式保持原有「世界 → 寻找 TA → 调频连接」流程；
/// - 远端账号模式必须先登录，宠物数据跟着账号走（可替换），
///   登录后从账号名下的 TA 里选择，或开始一次新的寻找（创建后立即绑定账号）。
struct AppRouter: View {
    @EnvironmentObject private var session: AppSessionStore

    let service: any PetJourneyService
    @State private var route: AppRoute = .publicWorld
    @State private var accountPets: [AuthPetSummary]?

    var body: some View {
        Group {
            if session.useMockData {
                mockFlow
            } else {
                remoteFlow
            }
        }
        .background(AppBackground())
        .task(id: session.petID ?? "no-pet") {
            PetPushRegistrationCoordinator.shared.configure(petID: session.petID, service: service)
        }
        .onChange(of: session.isSignedIn) { _, signedIn in
            if !signedIn {
                accountPets = nil
                withAnimation(.easeInOut(duration: 0.25)) {
                    route = .petPicker
                }
            }
        }
    }

    // MARK: - Mock 流程（开发演示，不要求登录）

    @ViewBuilder
    private var mockFlow: some View {
        if session.onboardingCompleted, let petID = session.petID {
            journeyTabs(petID: petID)
        } else {
            switch route {
            case .publicWorld:
                PublicWorldView {
                    withAnimation(.easeInOut(duration: 0.25)) {
                        route = .onboarding
                    }
                }
            case .onboarding:
                PetOnboardingView(
                    onBack: {
                        withAnimation(.easeInOut(duration: 0.25)) {
                            route = .publicWorld
                        }
                    },
                    onComplete: { draft in
                        withAnimation(.easeInOut(duration: 0.25)) {
                            route = .connecting(draft)
                        }
                    }
                )
            case .connecting(let draft):
                ConnectingView(
                    draft: draft,
                    service: service,
                    onBack: {
                        withAnimation(.easeInOut(duration: 0.25)) {
                            route = .onboarding
                        }
                    },
                    onEnterJourney: { petID in
                        session.completeOnboarding(petID: petID)
                    }
                )
            case .signIn, .petPicker:
                EmptyView()
            }
        }
    }

    // MARK: - 远端账号流程（登录 → 账号里的 TA）

    @ViewBuilder
    private var remoteFlow: some View {
        if !session.isSignedIn {
            SignInView(service: service) { auth in
                accountPets = auth.pets
                withAnimation(.easeInOut(duration: 0.25)) {
                    route = .petPicker
                }
            }
        } else if let pets = accountPets {
            if let petID = session.petID, pets.contains(where: { $0.petID == petID }) {
                journeyTabs(petID: petID)
            } else {
                switch route {
                case .onboarding:
                    PetOnboardingView(
                        onBack: {
                            withAnimation(.easeInOut(duration: 0.25)) {
                                route = .petPicker
                            }
                        },
                        onComplete: { draft in
                            withAnimation(.easeInOut(duration: 0.25)) {
                                route = .connecting(draft)
                            }
                        }
                    )
                case .connecting(let draft):
                    ConnectingView(
                        draft: draft,
                        service: service,
                        claimsToAccount: true,
                        onBack: {
                            withAnimation(.easeInOut(duration: 0.25)) {
                                route = .onboarding
                            }
                        },
                        onEnterJourney: { petID in
                            session.completeOnboarding(petID: petID)
                            accountPets = nil
                        }
                    )
                default:
                    PetPickerView(
                        pets: pets,
                        onSelect: { pet in
                            session.completeOnboarding(petID: pet.petID, petName: pet.name)
                        },
                        onFindNew: {
                            withAnimation(.easeInOut(duration: 0.25)) {
                                route = .onboarding
                            }
                        }
                    )
                }
            }
        } else {
            accountSyncView
                .task {
                    await loadAccountPets()
                }
        }
    }

    private var accountSyncView: some View {
        ZStack {
            AppBackground()
            AmbientSignalField(tint: DesignTokens.sea, warmth: DesignTokens.pollen, density: 16, drift: 0.5)
                .opacity(0.4)
            VStack(spacing: 14) {
                ProgressView()
                    .tint(DesignTokens.sage)
                Text("正在同步你的信号站")
                    .font(.subheadline)
                    .foregroundStyle(DesignTokens.secondaryInk)
            }
        }
    }

    private func journeyTabs(petID: String) -> some View {
        JourneyHomeTabs(petID: petID, service: service) {
            withAnimation(.easeInOut(duration: 0.25)) {
                session.resetJourney()
                route = session.useMockData ? .publicWorld : .petPicker
            }
        }
    }

    private func loadAccountPets() async {
        do {
            let me = try await service.fetchMe()
            accountPets = me.pets
        } catch {
            // 会话失效（401 等）→ 清会话回登录页；signOut 会连带清理本机旅程。
            session.signOut()
        }
    }
}
