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
    case onboarding
    case connecting(OnboardingDraft)
}

struct AppRouter: View {
    @EnvironmentObject private var session: AppSessionStore

    let service: any PetJourneyService
    @State private var route: AppRoute = .publicWorld

    var body: some View {
        Group {
            if session.onboardingCompleted, let petID = session.petID {
                JourneyHomeTabs(petID: petID, service: service) {
                    withAnimation(.easeInOut(duration: 0.25)) {
                        session.resetJourney()
                        route = .publicWorld
                    }
                }
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
                }
            }
        }
        .background(AppBackground())
        .task(id: session.petID ?? "no-pet") {
            PetPushRegistrationCoordinator.shared.configure(petID: session.petID, service: service)
        }
    }
}
