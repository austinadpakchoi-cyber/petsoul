import AuthenticationServices
import MapKit
import SwiftUI
import UIKit

struct JourneyMapView: View {
    @StateObject var viewModel: JourneyViewModel
    @State var cameraPosition: MapCameraPosition
    @State var activeSheet: JourneySheet?
    @State var selectedMapEvent: JourneyMapEvent?
    @State var plannedRoute: JourneyRoutePlan = .empty
    @State var plannedRouteKey = ""
    @State var routePerspective: RoutePerspective = .threeD
    @State var showNearbySignals = false
    @State var isSignalPanelExpanded = false
    @State var isCheckInCardExpanded = false
    @State var selectedCompanion: DemoCompanionPet?
    @State var travelQuestMessage = ""
    @State var travelBagMessage = ""
    @State var showWorldCupStadiums = false
    @State var selectedWorldCupHost: WorldCupHostCity?
    @State var introFlightState = IntroFlightState.pending
    @State var showDayRecap = false
    @EnvironmentObject var session: AppSessionStore
    @AppStorage("account_link_prompted") var accountLinkPrompted = false
    @State var showAccountSheet = false

    var onReset: () -> Void
    let petID: String
    let service: any PetJourneyService

    init(petID: String, service: any PetJourneyService, onReset: @escaping () -> Void) {
        _viewModel = StateObject(wrappedValue: JourneyViewModel(petID: petID, service: service))
        _cameraPosition = State(initialValue: Self.introCameraPosition(above: CityPosition.xiamen.coordinate))
        self.onReset = onReset
        self.petID = petID
        self.service = service
    }

    var body: some View {
        NavigationStack {
            ZStack {
                switch viewModel.loadState {
                case .loading:
                    AppBackground()
                    loadingView
                case .empty:
                    AppBackground()
                    emptyView
                case .failed(let message):
                    AppBackground()
                    errorView(message: message)
                case .loaded:
                    if let status = viewModel.status {
                        journeyWorld(status: status)
                    }
                }

                if let toastMessage = viewModel.toastMessage {
                    VStack {
                        Spacer()
                        ToastView(message: toastMessage)
                            .padding(.horizontal, DesignTokens.pagePadding)
                            .padding(.bottom, 18)
                            .transition(.move(edge: .bottom).combined(with: .opacity))
                    }
                }
            }
            .toolbar(.hidden, for: .navigationBar)
            .sheet(item: $activeSheet) { sheet in
                NavigationStack {
                    switch sheet {
                    case .dayPlan:
                        DayPlanSheetView(
                            dayPlan: viewModel.dayPlan,
                            journeyPlan: viewModel.journeyPlan,
                            petGuide: viewModel.petGuide,
                            illustratedGuide: viewModel.illustratedGuide,
                            isGeneratingIllustratedGuide: viewModel.isGeneratingIllustratedGuide
                        )
                    case .postcards:
                        PostcardsView(postcards: viewModel.status?.postcards ?? [])
                    case .travelKit:
                        TravelKitSheetView(
                            petName: viewModel.status?.name ?? "TA",
                            travelQuests: viewModel.travelQuests,
                            travelBag: viewModel.travelBag,
                            souvenirs: viewModel.souvenirs,
                            economy: viewModel.economy,
                            isCreatingQuest: viewModel.isCreatingTravelQuest,
                            isPackingBag: viewModel.isPackingTravelBag,
                            isCollectingSouvenir: viewModel.isCollectingSouvenir,
                            mutatingInventoryItemIDs: viewModel.mutatingInventoryItemIDs,
                            questMessage: $travelQuestMessage,
                            bagMessage: $travelBagMessage,
                            onCreateQuest: {
                                let message = travelQuestMessage
                                travelQuestMessage = ""
                                Task { await viewModel.createTravelQuest(message: message) }
                            },
                            onPackPreset: { item in
                                Task { await viewModel.packTravelBag(items: [item], ownerMessage: travelBagMessage) }
                            },
                            onPrepareDeparture: {
                                Task { await viewModel.prepareActiveTravelQuest() }
                            },
                            onCollectSouvenir: {
                                Task { await viewModel.collectSouvenirsForActiveQuest() }
                            },
                            onShowSouvenirs: {
                                activeSheet = .souvenirs
                            },
                            onSellSouvenir: { souvenir in
                                Task { await viewModel.sellSouvenir(souvenir) }
                            },
                            onArchiveSouvenir: { souvenir in
                                Task { await viewModel.archiveSouvenir(souvenir) }
                            }
                        )
                    case .souvenirs:
                        SouvenirsView(
                            souvenirs: viewModel.souvenirs,
                            economy: viewModel.economy,
                            allowsActions: true,
                            mutatingItemIDs: viewModel.mutatingInventoryItemIDs,
                            onSell: { souvenir in
                                Task { await viewModel.sellSouvenir(souvenir) }
                            },
                            onArchive: { souvenir in
                                Task { await viewModel.archiveSouvenir(souvenir) }
                            }
                        )
                    case .worldCupQuest:
                        WorldCupQuestSheetView(
                            petName: viewModel.status?.name ?? "TA",
                            currentCity: viewModel.status?.agentState.location ?? "现在这座城市",
                            selectedHost: selectedWorldCupHost,
                            hosts: WorldCupHostCity.hostCities,
                            existingQuest: viewModel.activeWorldCupQuest,
                            isPreparing: viewModel.isOpeningWorldCupQuest,
                            onShowMap: {
                                activeSheet = nil
                                showWorldCupStadiumMap()
                            },
                            onSelectHost: { host in
                                selectedWorldCupHost = host
                                focusWorldCupHost(host)
                            },
                            onPrepare: { host, bagItems, ownerMessage in
                                Task {
                                    await viewModel.openWorldCupQuest(
                                        host: host,
                                        bagItems: bagItems,
                                        ownerMessage: ownerMessage
                                    )
                                    selectedWorldCupHost = host
                                    showWorldCupStadiums = true
                                    activeSheet = nil
                                }
                            }
                        )
                    case .dna:
                        DNASettingsView(
                            dna: viewModel.dna,
                            isSaving: viewModel.isUpdatingDNA,
                            onSave: { nextDNA in
                                Task { await viewModel.updateDNA(nextDNA) }
                            }
                        )
                    case .streetRank:
                        StreetRankSheet(petID: petID, service: service)
                    }
                }
                .presentationDetents(sheet.presentationDetents)
                .presentationDragIndicator(.visible)
            }
            .fullScreenCover(isPresented: $showDayRecap) {
                if let status = viewModel.status {
                    DayRecapView(
                        status: status,
                        chapters: DayRecapBuilder.chapters(
                            events: JourneyMapEvent.events(
                                around: viewModel.coordinate,
                                status: status,
                                dayPlan: viewModel.dayPlan,
                                remoteRoutePlan: viewModel.remoteRoutePlan
                            ),
                            routePlan: JourneyRoutePlan.backendPlan(from: viewModel.journeyPlan) ?? plannedRoute,
                            postcards: status.postcards
                        )
                    )
                }
            }
            .onAppear {
                viewModel.start()
            }
            .onDisappear {
                viewModel.stop()
            }
            .onChange(of: viewModel.coordinateKey) { _, _ in
                selectedMapEvent = nil
                selectedCompanion = nil
                plannedRoute = .empty
                plannedRouteKey = ""
                if introFlightState == .done {
                    withAnimation(.easeInOut(duration: 0.7)) {
                        cameraPosition = Self.cameraPosition(around: viewModel.coordinate, perspective: routePerspective)
                    }
                }
                Task { await viewModel.refreshRoutePlan() }
            }
            .onChange(of: routePerspective) { _, newValue in
                withAnimation(.easeInOut(duration: 0.45)) {
                    cameraPosition = Self.cameraPosition(
                        around: viewModel.worldSnapshot?.currentActivity.coordinate ?? viewModel.coordinate,
                        routePlan: JourneyRoutePlan.backendPlan(from: viewModel.journeyPlan) ?? plannedRoute,
                        events: [],
                        perspective: newValue,
                        navigationMode: viewModel.worldSnapshot?.currentActivity.mode
                    )
                }
            }
            .onChange(of: selectedMapEvent?.id) { _, newValue in
                guard newValue != nil else { return }
                selectedCompanion = nil
                withAnimation(.spring(response: 0.34, dampingFraction: 0.86)) {
                    isCheckInCardExpanded = true
                    isSignalPanelExpanded = false
                }
            }
            .onChange(of: viewModel.hasUnreadPostcard) { _, newValue in
                guard newValue, !session.isSignedIn, !accountLinkPrompted else { return }
                accountLinkPrompted = true
                Task {
                    try? await Task.sleep(for: .seconds(1.4))
                    showAccountSheet = true
                }
            }
            .sheet(isPresented: $showAccountSheet) {
                AccountLinkSheet(
                    petName: viewModel.status?.name ?? "TA",
                    isSignedIn: session.isSignedIn,
                    displayName: session.userDisplayName,
                    onAuthorized: { identityToken, fullName in
                        await linkAccount(identityToken: identityToken, fullName: fullName)
                    },
                    onSignOut: {
                        session.signOut()
                    }
                )
                .presentationDetents([.medium])
                .presentationDragIndicator(.visible)
            }
            .onChange(of: viewModel.toastMessage) { _, newValue in
                guard newValue != nil else { return }
                Task {
                    try? await Task.sleep(for: .seconds(2.8))
                    viewModel.clearToast()
                }
            }
        }
    }

    func journeyWorld(status: AgentStatus) -> some View {
        TimelineView(.periodic(from: .now, by: 1.0)) { timeline in
            let mapEvents = JourneyMapEvent.events(
                around: viewModel.coordinate,
                status: status,
                dayPlan: viewModel.dayPlan,
                remoteRoutePlan: viewModel.remoteRoutePlan
            )
            let routeStops = JourneyMotion.stopCoordinates(anchor: viewModel.coordinate, events: mapEvents)
            let routeKey = JourneyMotion.routeKey(stops: routeStops)
            let fallbackPlan = JourneyRoutePlan.fallback(key: routeKey, stops: routeStops)
            let backendPlan = JourneyRoutePlan.backendPlan(from: viewModel.journeyPlan)
            let routePlan = backendPlan ?? (plannedRoute.key == routeKey && plannedRoute.hasRoute ? plannedRoute : fallbackPlan)
            let route = routePlan.coordinates
            let movingCoordinate = JourneyMotion.stablePreviewCoordinate(route: route, fallback: viewModel.coordinate)
            let fallbackActivity = JourneyDaySchedule.activity(
                date: timeline.date,
                anchor: viewModel.coordinate,
                events: mapEvents,
                movingCoordinate: movingCoordinate,
                scheduledTransport: viewModel.journeyPlan?.scheduledTransport ?? []
            )
            let activity = JourneyActivitySnapshot.from(
                snapshot: viewModel.worldSnapshot,
                journeyPlan: viewModel.journeyPlan,
                events: mapEvents,
                anchor: viewModel.coordinate
            ) ?? fallbackActivity
            let liveCoordinate = activity.liveCoordinate
            let displayCoordinate = wanderAdjustedCoordinate(for: activity, petID: status.petID, date: timeline.date)
            let liveEvent = activity.relatedEvent ?? JourneyMotion.nearestEvent(to: liveCoordinate, events: mapEvents, maxDistanceMeters: 180)
            let selectedDisplayEvent = selectedMapEvent.flatMap { selected in
                mapEvents.first(where: { $0.id == selected.id }) ?? selected
            }
            let companions = DemoCompanionPet.samples(around: mapEvents, fallback: viewModel.coordinate)
            let selectedDisplayCompanion = selectedCompanion.flatMap { selected in
                companions.first(where: { $0.id == selected.id }) ?? selected
            }

            ZStack(alignment: .bottom) {
                LivingJourneyMap(
                    status: status,
                    homeCoordinate: viewModel.coordinate,
                    petCoordinate: displayCoordinate,
                    now: timeline.date,
                    events: mapEvents,
                    companions: companions,
                    routePlan: routePlan,
                    activity: activity,
                    liveEvent: liveEvent,
                    showNearbySignals: showNearbySignals,
                    showWorldCupStadiums: showWorldCupStadiums,
                    cameraPosition: $cameraPosition,
                    selectedEvent: $selectedMapEvent,
                    selectedCompanion: $selectedCompanion,
                    selectedWorldCupHost: $selectedWorldCupHost,
                    onSelectWorldCupHost: focusWorldCupHost
                )
                .ignoresSafeArea()
                .onAppear {
                    startIntroFlight(to: liveCoordinate)
                }

                JourneyMapAtmosphere(tint: activity.tint, date: timeline.date)

                // 审计 #3：地图全出血，顶部只留一张情感状态卡 + 一列紧凑控制坞。
                VStack(spacing: 0) {
                    HStack(alignment: .top, spacing: 10) {
                        PetPresenceCard(
                            petName: status.name,
                            travelDay: status.agentState.travelDay,
                            location: status.agentState.location,
                            modeLabel: activity.modeLabel,
                            modeSystemImage: activity.systemImage,
                            tint: activity.tint,
                            statusNote: status.agentState.statusNote.petSoulUserFacingText
                        )

                        Spacer(minLength: 10)

                        MapControlDock(
                            hasUnreadPostcard: viewModel.hasUnreadPostcard,
                            showNearbySignals: showNearbySignals,
                            perspectiveTitle: perspectiveTitle(for: activity),
                            perspectiveSystemImage: perspectiveSystemImage(for: activity),
                            isSignedIn: session.isSignedIn,
                            accountName: session.userDisplayName,
                            actions: MapDockActions(
                                onCenter: {
                                    centerOnJourney(liveCoordinate, routePlan: routePlan, events: mapEvents, activity: activity)
                                },
                                onTogglePerspective: togglePerspective,
                                onToggleNearbySignals: toggleNearbySignals,
                                onShowDayPlan: showDayPlan,
                                onShowRecap: { showDayRecap = true },
                                onShowPostcards: showPostcards,
                                onShowTravelKit: showTravelKit,
                                onShowSouvenirs: showSouvenirs,
                                onShowStreetRank: { activeSheet = .streetRank },
                                onShowDNA: showDNA,
                                onShowAccount: { showAccountSheet = true },
                                onReset: onReset
                            )
                        )
                    }
                    .padding(.horizontal, DesignTokens.pagePadding)
                    .padding(.top, 12)

                    Spacer()
                }

                VStack(spacing: 10) {
                    if showWorldCupStadiums {
                        WorldCupMapStatusCard(
                            selectedHost: selectedWorldCupHost,
                            activeQuest: viewModel.activeWorldCupQuest,
                            onOpenInvitation: {
                                if selectedWorldCupHost == nil {
                                    selectedWorldCupHost = WorldCupHostCity.recommended
                                }
                                activeSheet = .worldCupQuest
                            },
                            onFocusAll: showWorldCupStadiumMap,
                            onClose: {
                                withAnimation(.easeInOut(duration: 0.25)) {
                                    showWorldCupStadiums = false
                                    selectedWorldCupHost = nil
                                }
                                centerOnJourney(liveCoordinate, routePlan: routePlan, events: mapEvents, activity: activity)
                            }
                        )
                        .transition(.move(edge: .bottom).combined(with: .opacity))
                    } else if viewModel.activeWorldCupQuest == nil {
                        WorldCupInvitationTeaserCard(
                            petName: status.name,
                            onOpen: {
                                selectedWorldCupHost = WorldCupHostCity.recommended
                                showWorldCupStadiumMap()
                            }
                        )
                        .transition(.move(edge: .bottom).combined(with: .opacity))
                    }

                    if let selectedDisplayCompanion {
                        CompanionPetPeekCard(
                            companion: selectedDisplayCompanion,
                            onClose: {
                                withAnimation(.easeInOut(duration: 0.2)) {
                                    self.selectedCompanion = nil
                                }
                            }
                        )
                        .transition(.move(edge: .bottom).combined(with: .opacity))
                    }

                    if let selectedDisplayEvent {
                        MapEventCard(
                            event: selectedDisplayEvent,
                            phase: selectedDisplayEvent.displayPhase(liveEvent: liveEvent),
                            petName: status.name,
                            isExpanded: $isCheckInCardExpanded,
                            onClose: {
                                withAnimation(.easeInOut(duration: 0.2)) {
                                    self.selectedMapEvent = nil
                                }
                            }
                        )
                        .transition(.move(edge: .bottom).combined(with: .opacity))
                    }

                    LiveSignalPanel(
                        status: status,
                        selectedEvent: selectedDisplayEvent,
                        liveEvent: liveEvent,
                        routePlan: routePlan,
                        activity: activity,
                        needState: viewModel.worldSnapshot?.lifeTick?.needState,
                        visibleThought: viewModel.worldSnapshot?.lifeTick?.visibleThought,
                        translation: viewModel.visibleThoughtTranslation,
                        isTranslating: viewModel.isTranslatingThought,
                        hasUnreadPostcard: viewModel.hasUnreadPostcard,
                        isExpanded: $isSignalPanelExpanded,
                        onShowDayPlan: showDayPlan,
                        onShowPostcards: showPostcards,
                        onShowTravelKit: showTravelKit,
                        onShowSouvenirs: showSouvenirs,
                        onTranslate: {
                            Task { await viewModel.translateLatestThought() }
                        },
                        onLike: {
                            Task { await viewModel.sendFeedback(liked: true) }
                        },
                        onDislike: {
                            Task { await viewModel.sendFeedback(liked: false) }
                        }
                    )
                }
                .padding(.horizontal, DesignTokens.pagePadding)
                .padding(.bottom, 18)
            }
            .task(id: routeKey) {
                await planRoute(stops: routeStops, key: routeKey)
            }
            .task(id: activity.cameraKey) {
                try? await Task.sleep(for: .milliseconds(350))
                guard !Task.isCancelled else { return }
                guard !showWorldCupStadiums else { return }
                centerOnJourney(activity.liveCoordinate, routePlan: routePlan, events: mapEvents, activity: activity)
            }
        }
    }

    var loadingView: some View {
        JourneyLoadingView()
            .padding(DesignTokens.pagePadding)
    }

    var emptyView: some View {
        SoftCard {
            Label("还没有旅程", systemImage: "map")
                .font(.headline)
                .foregroundStyle(DesignTokens.ink)
            Text("手机已经准备好，但还没有收到第一段位置。")
                .font(.subheadline)
                .foregroundStyle(DesignTokens.secondaryInk)
            Button(action: onReset) {
                Label("重新寻找", systemImage: "arrow.clockwise")
            }
            .quietActionStyle()
        }
        .padding(DesignTokens.pagePadding)
    }

    func errorView(message: String) -> some View {
        JourneySignalErrorCard(message: message) {
            Task { await viewModel.loadInitial() }
        }
        .padding(.horizontal, DesignTokens.pagePadding)
    }

    func centerOnCoordinate(_ coordinate: CLLocationCoordinate2D) {
        withAnimation(.easeInOut(duration: 0.45)) {
            cameraPosition = Self.cameraPosition(around: coordinate, perspective: routePerspective)
        }
    }

    func centerOnJourney(
        _ coordinate: CLLocationCoordinate2D,
        routePlan: JourneyRoutePlan,
        events: [JourneyMapEvent],
        activity: JourneyActivitySnapshot? = nil
    ) {
        withAnimation(.easeInOut(duration: 0.45)) {
            cameraPosition = Self.cameraPosition(
                around: coordinate,
                routePlan: routePlan,
                events: events,
                perspective: routePerspective,
                activity: activity
            )
        }
    }

    func togglePerspective() {
        routePerspective.toggle()
    }

    func perspectiveTitle(for activity: JourneyActivitySnapshot) -> String {
        if routePerspective == .threeD, activity.prefersNavigationCamera {
            return "导航"
        }
        return routePerspective.title
    }

    func perspectiveSystemImage(for activity: JourneyActivitySnapshot) -> String {
        if routePerspective == .threeD, activity.prefersNavigationCamera {
            return "location.north.line.fill"
        }
        return routePerspective.systemImage
    }

    func toggleNearbySignals() {
        withAnimation(.easeInOut(duration: 0.25)) {
            showNearbySignals.toggle()
            if !showNearbySignals {
                selectedMapEvent = nil
                selectedCompanion = nil
            }
        }
    }

    func planRoute(stops: [CLLocationCoordinate2D], key: String) async {
        guard plannedRouteKey != key else { return }
        plannedRouteKey = key
        plannedRoute = .fallback(key: key, stops: stops)

        guard let resolvedRoute = await JourneyRoutePlanner.walkingPlan(through: stops, key: key) else { return }
        guard !Task.isCancelled, plannedRouteKey == key else { return }
        plannedRoute = resolvedRoute
    }

    func showDayPlan() {
        activeSheet = .dayPlan
        Task {
            await viewModel.refreshDetails()
        }
    }

    func showPostcards() {
        viewModel.markPostcardsRead()
        activeSheet = .postcards
    }

    func showTravelKit() {
        activeSheet = .travelKit
        Task {
            await viewModel.refreshTravelTools()
        }
    }

    func showSouvenirs() {
        activeSheet = .souvenirs
        Task {
            await viewModel.refreshTravelTools()
        }
    }

    func showDNA() {
        activeSheet = .dna
        Task {
            await viewModel.refreshDetails()
        }
    }

    /// 登录成功后把当前宠物认领到账号；返回 nil 表示成功，否则为展示给用户的错误文案
    func linkAccount(identityToken: String, fullName: String?) async -> String? {
        do {
            let auth = try await service.signInWithApple(
                request: AppleSignInRequest(identityToken: identityToken, displayName: fullName)
            )
            session.storeAuthSession(
                token: auth.accessToken,
                userID: auth.userID,
                displayName: auth.displayName ?? fullName
            )
            _ = try? await service.claimPet(petID: petID)
            viewModel.toastMessage = "TA 的旅程已经和你连在一起了。"
            return nil
        } catch {
            return "这次没有连上，稍后可以从右上角菜单再试。"
        }
    }

    func showWorldCupStadiumMap() {
        withAnimation(.easeInOut(duration: 0.36)) {
            routePerspective = .twoD
            showWorldCupStadiums = true
            selectedWorldCupHost = selectedWorldCupHost ?? WorldCupHostCity.recommended
            cameraPosition = Self.worldCupCameraPosition()
        }
    }

    func focusWorldCupHost(_ host: WorldCupHostCity) {
        withAnimation(.easeInOut(duration: 0.32)) {
            showWorldCupStadiums = true
            selectedWorldCupHost = host
            cameraPosition = .region(
                MKCoordinateRegion(
                    center: host.coordinate,
                    span: MKCoordinateSpan(latitudeDelta: 8.5, longitudeDelta: 8.5)
                )
            )
        }
    }

    static func worldCupCameraPosition() -> MapCameraPosition {
        .region(
            MKCoordinateRegion(
                center: CLLocationCoordinate2D(latitude: 38.8, longitude: -98.6),
                span: MKCoordinateSpan(latitudeDelta: 42, longitudeDelta: 78)
            )
        )
    }

    static func cameraPosition(around coordinate: CLLocationCoordinate2D, perspective: RoutePerspective) -> MapCameraPosition {
        cameraPosition(around: coordinate, routePlan: .empty, events: [], perspective: perspective)
    }

    func wanderAdjustedCoordinate(
        for activity: JourneyActivitySnapshot,
        petID: String,
        date: Date
    ) -> CLLocationCoordinate2D {
        guard activity.kind == .staying || activity.kind == .checkingIn else {
            return activity.liveCoordinate
        }
        return JourneyMotion.wanderedCoordinate(
            around: activity.liveCoordinate,
            date: date,
            seed: JourneyMotion.seed(petID)
        )
    }

    static func introCameraPosition(above coordinate: CLLocationCoordinate2D) -> MapCameraPosition {
        .camera(MapCamera(centerCoordinate: coordinate, distance: 1_600_000, heading: 0, pitch: 0))
    }

    func startIntroFlight(to coordinate: CLLocationCoordinate2D) {
        guard introFlightState == .pending else { return }
        introFlightState = .flying
        cameraPosition = Self.introCameraPosition(above: coordinate)
        Task {
            try? await Task.sleep(for: .milliseconds(420))
            withAnimation(.easeInOut(duration: 2.1)) {
                cameraPosition = Self.cameraPosition(around: coordinate, perspective: routePerspective)
            }
            try? await Task.sleep(for: .seconds(2.2))
            introFlightState = .done
        }
    }

    static func cameraPosition(
        around coordinate: CLLocationCoordinate2D,
        routePlan: JourneyRoutePlan,
        events: [JourneyMapEvent],
        perspective: RoutePerspective,
        activity: JourneyActivitySnapshot? = nil,
        navigationMode: TravelMode? = nil
    ) -> MapCameraPosition {
        let routeCoordinates = activity?.routeCoordinatesOverride ?? routePlan.coordinates
        let routeDistanceMeters = routeCoordinates.count > 1
            ? JourneyMotion.totalDistance(of: routeCoordinates)
            : routePlan.distanceMeters
        let viewport = JourneyMapViewport(
            focus: coordinate,
            routeCoordinates: routeCoordinates,
            eventCoordinates: events.map(\.coordinate),
            routeDistanceMeters: routeDistanceMeters
        )
        let resolvedMode = activity?.travelMode ?? navigationMode
        let shouldUseNavigationCamera = activity?.prefersNavigationCamera
            ?? JourneyActivitySnapshot.prefersNavigationCamera(mode: resolvedMode)
        switch perspective {
        case .twoD:
            return .region(
                MKCoordinateRegion(
                    center: viewport.regionCenter,
                    span: viewport.regionSpan
                )
            )
        case .threeD:
            if shouldUseNavigationCamera, !viewport.isGlobalRoute {
                return .camera(
                    MapCamera(
                        centerCoordinate: viewport.navigationCenter(lookAheadMeters: resolvedMode?.navigationLookAheadMeters ?? 120),
                        distance: resolvedMode?.navigationCameraDistance ?? 760,
                        heading: viewport.navigationHeading,
                        pitch: resolvedMode?.navigationPitch ?? 74
                    )
                )
            }
            return .camera(
                MapCamera(
                    centerCoordinate: viewport.cameraCenter,
                    distance: viewport.cameraDistance,
                    heading: viewport.heading,
                    pitch: viewport.pitch
                )
            )
        }
    }
}
