import MapKit
import SwiftUI
import UIKit

struct JourneyMapView: View {
    @StateObject private var viewModel: JourneyViewModel
    @State private var cameraPosition: MapCameraPosition
    @State private var activeSheet: JourneySheet?
    @State private var selectedMapEvent: JourneyMapEvent?
    @State private var plannedRoute: JourneyRoutePlan = .empty
    @State private var plannedRouteKey = ""
    @State private var routePerspective: RoutePerspective = .threeD
    @State private var showNearbySignals = false
    @State private var isSignalPanelExpanded = false
    @State private var isCheckInCardExpanded = false
    @State private var selectedCompanion: DemoCompanionPet?
    @State private var travelQuestMessage = ""
    @State private var travelBagMessage = ""
    @State private var showWorldCupStadiums = false
    @State private var selectedWorldCupHost: WorldCupHostCity?
    @State private var introFlightState = IntroFlightState.pending

    var onReset: () -> Void

    init(petID: String, service: any PetJourneyService, onReset: @escaping () -> Void) {
        _viewModel = StateObject(wrappedValue: JourneyViewModel(petID: petID, service: service))
        _cameraPosition = State(initialValue: Self.introCameraPosition(above: CityPosition.xiamen.coordinate))
        self.onReset = onReset
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
                    }
                }
                .presentationDetents(sheet.presentationDetents)
                .presentationDragIndicator(.visible)
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
            .onChange(of: viewModel.toastMessage) { _, newValue in
                guard newValue != nil else { return }
                Task {
                    try? await Task.sleep(for: .seconds(2.8))
                    viewModel.clearToast()
                }
            }
        }
    }

    private func journeyWorld(status: AgentStatus) -> some View {
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
                    petCoordinate: liveCoordinate,
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

                VStack(spacing: 0) {
                    JourneyTopBar(
                        status: status,
                        hasUnreadPostcard: viewModel.hasUnreadPostcard,
                        onCenter: {
                            centerOnJourney(liveCoordinate, routePlan: routePlan, events: mapEvents, activity: activity)
                        },
                        onShowDayPlan: showDayPlan,
                        onShowPostcards: showPostcards,
                        onShowTravelKit: showTravelKit,
                        onShowSouvenirs: showSouvenirs,
                        onShowDNA: showDNA,
                        onReset: onReset
                    )
                    .padding(.horizontal, DesignTokens.pagePadding)
                    .padding(.top, 12)

                    HStack {
                        NavigationModeStrip(
                            perspective: routePerspective,
                            routePlan: routePlan,
                            activity: activity,
                            showNearbySignals: showNearbySignals,
                            onTogglePerspective: togglePerspective,
                            onToggleNearbySignals: toggleNearbySignals
                        )

                        Spacer(minLength: 0)
                    }
                    .padding(.horizontal, DesignTokens.pagePadding)
                    .padding(.top, 8)

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

    private var loadingView: some View {
        JourneyLoadingView()
            .padding(DesignTokens.pagePadding)
    }

    private var emptyView: some View {
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

    private func errorView(message: String) -> some View {
        JourneySignalErrorCard(message: message) {
            Task { await viewModel.loadInitial() }
        }
        .padding(.horizontal, DesignTokens.pagePadding)
    }

    private func centerOnCoordinate(_ coordinate: CLLocationCoordinate2D) {
        withAnimation(.easeInOut(duration: 0.45)) {
            cameraPosition = Self.cameraPosition(around: coordinate, perspective: routePerspective)
        }
    }

    private func centerOnJourney(
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

    private func togglePerspective() {
        routePerspective.toggle()
    }

    private func toggleNearbySignals() {
        withAnimation(.easeInOut(duration: 0.25)) {
            showNearbySignals.toggle()
            if !showNearbySignals {
                selectedMapEvent = nil
                selectedCompanion = nil
            }
        }
    }

    private func planRoute(stops: [CLLocationCoordinate2D], key: String) async {
        guard plannedRouteKey != key else { return }
        plannedRouteKey = key
        plannedRoute = .fallback(key: key, stops: stops)

        guard let resolvedRoute = await JourneyRoutePlanner.walkingPlan(through: stops, key: key) else { return }
        guard !Task.isCancelled, plannedRouteKey == key else { return }
        plannedRoute = resolvedRoute
    }

    private func showDayPlan() {
        activeSheet = .dayPlan
        Task {
            await viewModel.refreshDetails()
        }
    }

    private func showPostcards() {
        viewModel.markPostcardsRead()
        activeSheet = .postcards
    }

    private func showTravelKit() {
        activeSheet = .travelKit
        Task {
            await viewModel.refreshTravelTools()
        }
    }

    private func showSouvenirs() {
        activeSheet = .souvenirs
        Task {
            await viewModel.refreshTravelTools()
        }
    }

    private func showDNA() {
        activeSheet = .dna
        Task {
            await viewModel.refreshDetails()
        }
    }

    private func showWorldCupStadiumMap() {
        withAnimation(.easeInOut(duration: 0.36)) {
            routePerspective = .twoD
            showWorldCupStadiums = true
            selectedWorldCupHost = selectedWorldCupHost ?? WorldCupHostCity.recommended
            cameraPosition = Self.worldCupCameraPosition()
        }
    }

    private func focusWorldCupHost(_ host: WorldCupHostCity) {
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

    private static func worldCupCameraPosition() -> MapCameraPosition {
        .region(
            MKCoordinateRegion(
                center: CLLocationCoordinate2D(latitude: 38.8, longitude: -98.6),
                span: MKCoordinateSpan(latitudeDelta: 42, longitudeDelta: 78)
            )
        )
    }

    private static func cameraPosition(around coordinate: CLLocationCoordinate2D, perspective: RoutePerspective) -> MapCameraPosition {
        cameraPosition(around: coordinate, routePlan: .empty, events: [], perspective: perspective)
    }

    private static func introCameraPosition(above coordinate: CLLocationCoordinate2D) -> MapCameraPosition {
        .camera(MapCamera(centerCoordinate: coordinate, distance: 1_600_000, heading: 0, pitch: 0))
    }

    private func startIntroFlight(to coordinate: CLLocationCoordinate2D) {
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

    private static func cameraPosition(
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

private enum IntroFlightState {
    case pending
    case flying
    case done
}

private struct JourneyLoadingView: View {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    private let phases: [(title: String, detail: String, symbol: String, tint: Color)] = [
        ("正在接收 TA 的位置", "先确认 TA 停在哪一片光里。", "mappin.and.ellipse", DesignTokens.sage),
        ("正在听今天的信号", "今天想靠近的地方，会一点点浮出来。", "dot.radiowaves.left.and.right", DesignTokens.sea),
        ("正在整理脚印路线", "进入地图后，脚印和小照片会慢慢出现。", "map.fill", DesignTokens.amber)
    ]

    var body: some View {
        TimelineView(.animation) { timeline in
            let time = timeline.date.timeIntervalSinceReferenceDate
            let phaseIndex = Int(time / 1.55) % phases.count
            let phase = phases[phaseIndex]
            let pulse = reduceMotion ? 0.5 : (sin(time * 2.4) + 1) / 2
            let routeProgress = reduceMotion ? 0.45 : (time * 0.42).truncatingRemainder(dividingBy: 1)

            VStack(spacing: 18) {
                LoadingCommunicatorGlyph(
                    tint: phase.tint,
                    pulse: pulse,
                    routeProgress: routeProgress
                )

                VStack(spacing: 7) {
                    Label(phase.title, systemImage: phase.symbol)
                        .font(.headline.weight(.semibold))
                        .foregroundStyle(DesignTokens.ink)
                        .lineLimit(1)
                        .minimumScaleFactor(0.78)

                    Text(phase.detail)
                        .font(.subheadline)
                        .foregroundStyle(DesignTokens.secondaryInk)
                        .multilineTextAlignment(.center)
                        .lineSpacing(3)
                        .fixedSize(horizontal: false, vertical: true)
                }

                LoadingRouteDots(activeIndex: phaseIndex, tint: phase.tint)
            }
            .frame(maxWidth: .infinity)
            .padding(.vertical, 24)
            .padding(.horizontal, 18)
            .background {
                RoundedRectangle(cornerRadius: 25, style: .continuous)
                    .fill(.ultraThinMaterial)
                RoundedRectangle(cornerRadius: 25, style: .continuous)
                    .fill(.white.opacity(0.72))
            }
            .clipShape(RoundedRectangle(cornerRadius: 25, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: 25, style: .continuous)
                    .stroke(.white.opacity(0.78), lineWidth: 1)
            }
            .shadow(color: DesignTokens.ink.opacity(0.12), radius: 26, x: 0, y: 14)
            .accessibilityElement(children: .combine)
            .accessibilityLabel("正在接收 TA 的旅程，地图会先出现，细节随后同步")
        }
    }
}

private struct JourneySignalErrorCard: View {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var message: String
    var onRetry: () -> Void

    var body: some View {
        SoftCard(padding: 18) {
            VStack(alignment: .leading, spacing: 18) {
                HStack(alignment: .top, spacing: 14) {
                    communicatorGlyph

                    VStack(alignment: .leading, spacing: 8) {
                        HStack(spacing: 7) {
                            SignalBars(tint: DesignTokens.sage, isActive: !reduceMotion)
                            Text("信号暂时飘远了")
                                .font(.headline.weight(.semibold))
                                .foregroundStyle(DesignTokens.ink)
                                .lineLimit(1)
                                .minimumScaleFactor(0.82)
                        }

                        Text(detailText)
                            .font(.subheadline)
                            .foregroundStyle(DesignTokens.secondaryInk)
                            .lineSpacing(3)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }

                HStack(spacing: 8) {
                    Image(systemName: "antenna.radiowaves.left.and.right.slash")
                        .font(.caption.weight(.semibold))
                    Text(reasonText)
                        .font(.caption.weight(.semibold))
                }
                .foregroundStyle(DesignTokens.sage)
                .padding(.vertical, 8)
                .padding(.horizontal, 10)
                .background(DesignTokens.mist.opacity(0.74))
                .clipShape(RoundedRectangle(cornerRadius: DesignTokens.cardRadius, style: .continuous))

                Button(action: onRetry) {
                    Label("重新接收信号", systemImage: "arrow.clockwise")
                }
                .primaryActionStyle()
            }
        }
        .frame(maxWidth: 360)
        .accessibilityElement(children: .combine)
        .accessibilityLabel("信号暂时飘远了。\(detailText)。\(reasonText)。可以重新接收信号。")
    }

    private var communicatorGlyph: some View {
        ZStack {
            if !reduceMotion {
                SignalPulseRings(tint: DesignTokens.sage, size: 82, lineWidth: 1.2, ringCount: 2)
                    .opacity(0.42)
            }

            Circle()
                .fill(
                    LinearGradient(
                        colors: [
                            DesignTokens.porcelain.opacity(0.98),
                            DesignTokens.mist.opacity(0.94)
                        ],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    )
                )
                .frame(width: 58, height: 58)
                .overlay {
                    Circle()
                        .stroke(.white.opacity(0.92), lineWidth: 1)
                }
                .shadow(color: DesignTokens.sage.opacity(0.16), radius: 14, x: 0, y: 8)

            PetSoulAssetIcon(
                asset: .communicator,
                fallbackSystemImage: "antenna.radiowaves.left.and.right",
                fallbackTint: DesignTokens.sage,
                size: 36
            )
        }
        .frame(width: 78, height: 78)
    }

    private var detailText: String {
        "刚刚没能连上远方的信号站。别担心，TA 的旅程还在，等信号回来就能继续同步。"
    }

    private var reasonText: String {
        let normalizedMessage = message.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        if normalizedMessage.contains("server") || normalizedMessage.contains("connect") {
            return "远方信号站暂时没有回应"
        }
        if normalizedMessage.contains("internet") || normalizedMessage.contains("network") || normalizedMessage.contains("offline") {
            return "当前网络有点不稳定"
        }
        return "手机会保留刚刚的位置"
    }
}

private struct LoadingCommunicatorGlyph: View {
    var tint: Color
    var pulse: Double
    var routeProgress: Double

    var body: some View {
        ZStack {
            SignalPulseRings(
                tint: tint,
                size: 154 + CGFloat(pulse * 10),
                lineWidth: 1.4,
                ringCount: 3
            )
            .opacity(0.54)

            LoadingRoutePath(progress: routeProgress, tint: tint)
                .frame(width: 156, height: 112)

            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .fill(
                    LinearGradient(
                        colors: [
                            DesignTokens.porcelain.opacity(0.98),
                            DesignTokens.mist.opacity(0.94)
                        ],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    )
                )
                .frame(width: 78, height: 78)
                .overlay {
                    RoundedRectangle(cornerRadius: 18, style: .continuous)
                        .stroke(.white.opacity(0.9), lineWidth: 1)
                }
                .shadow(color: DesignTokens.ink.opacity(0.10), radius: 16, x: 0, y: 8)

            VStack(spacing: 5) {
                Image(systemName: "dot.radiowaves.left.and.right")
                    .font(.system(size: 22, weight: .semibold))
                    .foregroundStyle(tint)
                HStack(spacing: 4) {
                    ForEach(0..<4, id: \.self) { index in
                        RoundedRectangle(cornerRadius: 2, style: .continuous)
                            .fill(index <= Int(routeProgress * 4) ? tint : DesignTokens.softLine)
                            .frame(width: 7, height: 18 - CGFloat(index % 2) * 4)
                    }
                }
            }
        }
        .frame(width: 180, height: 150)
    }
}

private struct LoadingRoutePath: View {
    var progress: Double
    var tint: Color

    var body: some View {
        Canvas { context, size in
            var path = Path()
            path.move(to: CGPoint(x: size.width * 0.12, y: size.height * 0.70))
            path.addCurve(
                to: CGPoint(x: size.width * 0.88, y: size.height * 0.30),
                control1: CGPoint(x: size.width * 0.30, y: size.height * 0.18),
                control2: CGPoint(x: size.width * 0.62, y: size.height * 0.90)
            )

            context.stroke(
                path,
                with: .color(DesignTokens.softLine.opacity(0.82)),
                style: StrokeStyle(lineWidth: 6, lineCap: .round, lineJoin: .round)
            )
            context.stroke(
                path.trimmedPath(from: 0, to: max(0.08, min(progress, 1))),
                with: .color(tint.opacity(0.82)),
                style: StrokeStyle(lineWidth: 6, lineCap: .round, lineJoin: .round)
            )

            let stops = [
                CGPoint(x: size.width * 0.12, y: size.height * 0.70),
                CGPoint(x: size.width * 0.47, y: size.height * 0.52),
                CGPoint(x: size.width * 0.88, y: size.height * 0.30)
            ]
            for (index, stop) in stops.enumerated() {
                let active = progress >= Double(index) / Double(max(stops.count - 1, 1))
                let rect = CGRect(x: stop.x - 7, y: stop.y - 7, width: 14, height: 14)
                context.fill(Path(ellipseIn: rect), with: .color(.white.opacity(0.96)))
                context.fill(Path(ellipseIn: rect.insetBy(dx: 3, dy: 3)), with: .color((active ? tint : DesignTokens.softLine).opacity(0.95)))
            }
        }
        .allowsHitTesting(false)
        .accessibilityHidden(true)
    }
}

private struct LoadingRouteDots: View {
    var activeIndex: Int
    var tint: Color

    var body: some View {
        HStack(spacing: 8) {
            ForEach(0..<3, id: \.self) { index in
                Capsule()
                    .fill(index == activeIndex ? tint : DesignTokens.softLine.opacity(0.86))
                    .frame(width: index == activeIndex ? 22 : 8, height: 8)
                    .animation(.spring(response: 0.32, dampingFraction: 0.86), value: activeIndex)
            }
        }
        .accessibilityHidden(true)
    }
}

private enum RoutePerspective: String {
    case twoD = "2D"
    case threeD = "3D"

    var title: String { rawValue }

    var systemImage: String {
        switch self {
        case .twoD: "map.fill"
        case .threeD: "cube.fill"
        }
    }

    mutating func toggle() {
        self = self == .twoD ? .threeD : .twoD
    }
}

private enum JourneySheet: String, Identifiable {
    case dayPlan
    case postcards
    case travelKit
    case souvenirs
    case worldCupQuest
    case dna

    var id: String { rawValue }

    var presentationDetents: Set<PresentationDetent> {
        switch self {
        case .dayPlan, .travelKit, .souvenirs, .postcards, .worldCupQuest:
            return [.large]
        case .dna:
            return [.medium, .large]
        }
    }
}

private struct JourneyMapViewport {
    var focus: CLLocationCoordinate2D
    var routeCoordinates: [CLLocationCoordinate2D]
    var eventCoordinates: [CLLocationCoordinate2D]
    var routeDistanceMeters: CLLocationDistance

    private var coordinates: [CLLocationCoordinate2D] {
        let combined = [focus] + routeCoordinates + eventCoordinates
        return combined.filter { coordinate in
            coordinate.latitude.isFinite
                && coordinate.longitude.isFinite
                && coordinate.latitude >= -85
                && coordinate.latitude <= 85
        }
    }

    var isGlobalRoute: Bool {
        routeDistanceMeters > 120_000 || maxDelta > 1.2
    }

    var regionCenter: CLLocationCoordinate2D {
        isGlobalRoute ? boundsCenter : shiftedFocus
    }

    var cameraCenter: CLLocationCoordinate2D {
        isGlobalRoute ? boundsCenter : focus
    }

    var regionSpan: MKCoordinateSpan {
        if isGlobalRoute {
            let latitudeDelta = min(max(maxLatitudeDelta * 1.35, 0.22), 155)
            let longitudeDelta = min(max(maxLongitudeDelta * 1.35, 0.22), 340)
            return MKCoordinateSpan(latitudeDelta: latitudeDelta, longitudeDelta: longitudeDelta)
        }
        return MKCoordinateSpan(latitudeDelta: 0.15, longitudeDelta: 0.15)
    }

    var cameraDistance: CLLocationDistance {
        if isGlobalRoute {
            return min(max(max(routeDistanceMeters * 0.34, spanDistanceMeters * 1.2), 180_000), 18_000_000)
        }
        return 3_800
    }

    var pitch: Double {
        isGlobalRoute ? 18 : 62
    }

    var heading: Double {
        isGlobalRoute ? 0 : 34
    }

    var navigationHeading: Double {
        guard let target = navigationTargetCoordinate else { return heading }
        return Self.bearingDegrees(from: focus, to: target)
    }

    func navigationCenter(lookAheadMeters: CLLocationDistance) -> CLLocationCoordinate2D {
        Self.offsetCoordinate(from: focus, distanceMeters: lookAheadMeters, bearingDegrees: navigationHeading)
    }

    private var navigationTargetCoordinate: CLLocationCoordinate2D? {
        let validRoute = routeCoordinates.filter { coordinate in
            coordinate.latitude.isFinite
                && coordinate.longitude.isFinite
                && coordinate.latitude >= -85
                && coordinate.latitude <= 85
        }
        guard validRoute.count > 1 else { return nil }

        let focusLocation = CLLocation(latitude: focus.latitude, longitude: focus.longitude)
        let nearestIndex = validRoute.indices.min { left, right in
            let leftLocation = CLLocation(latitude: validRoute[left].latitude, longitude: validRoute[left].longitude)
            let rightLocation = CLLocation(latitude: validRoute[right].latitude, longitude: validRoute[right].longitude)
            return leftLocation.distance(from: focusLocation) < rightLocation.distance(from: focusLocation)
        } ?? validRoute.startIndex

        let forwardEnd = min(validRoute.index(before: validRoute.endIndex), nearestIndex + 10)
        if nearestIndex < forwardEnd {
            for index in (nearestIndex + 1)...forwardEnd {
                let coordinate = validRoute[index]
                let distance = focusLocation.distance(from: CLLocation(latitude: coordinate.latitude, longitude: coordinate.longitude))
                if distance > 28 {
                    return coordinate
                }
            }
            return validRoute[forwardEnd]
        }

        let previousIndex = max(validRoute.startIndex, nearestIndex - 1)
        return previousIndex < nearestIndex ? validRoute[previousIndex] : nil
    }

    private var shiftedFocus: CLLocationCoordinate2D {
        CLLocationCoordinate2D(latitude: focus.latitude - 0.018, longitude: focus.longitude)
    }

    private var boundsCenter: CLLocationCoordinate2D {
        guard !coordinates.isEmpty else { return focus }
        return CLLocationCoordinate2D(
            latitude: (minLatitude + maxLatitude) / 2,
            longitude: longitudeCenter
        )
    }

    private var minLatitude: Double {
        coordinates.map(\.latitude).min() ?? focus.latitude
    }

    private var maxLatitude: Double {
        coordinates.map(\.latitude).max() ?? focus.latitude
    }

    private var maxLatitudeDelta: Double {
        max(0.03, maxLatitude - minLatitude)
    }

    private var maxLongitudeDelta: Double {
        let longitudes = coordinates.map { normalizedLongitude($0.longitude) }
        guard let minimumLongitude = longitudes.min(), let maximumLongitude = longitudes.max() else { return 0.03 }
        let direct = maximumLongitude - minimumLongitude
        return Swift.max(0.03, Swift.min(direct, 360 - direct))
    }

    private var maxDelta: Double {
        max(maxLatitudeDelta, maxLongitudeDelta)
    }

    private var spanDistanceMeters: CLLocationDistance {
        max(maxLatitudeDelta, maxLongitudeDelta) * 111_320
    }

    private var longitudeCenter: Double {
        let longitudes = coordinates.map { normalizedLongitude($0.longitude) }
        guard let min = longitudes.min(), let max = longitudes.max() else { return focus.longitude }
        if max - min <= 180 {
            return denormalizedLongitude((min + max) / 2)
        }
        let shifted = longitudes.map { $0 < 180 ? $0 + 360 : $0 }
        let shiftedMin = shifted.min() ?? normalizedLongitude(focus.longitude)
        let shiftedMax = shifted.max() ?? normalizedLongitude(focus.longitude)
        return denormalizedLongitude((shiftedMin + shiftedMax) / 2)
    }

    private func normalizedLongitude(_ longitude: Double) -> Double {
        var value = longitude.truncatingRemainder(dividingBy: 360)
        if value < 0 { value += 360 }
        return value
    }

    private func denormalizedLongitude(_ longitude: Double) -> Double {
        var value = longitude.truncatingRemainder(dividingBy: 360)
        if value > 180 { value -= 360 }
        if value < -180 { value += 360 }
        return value
    }

    private static func bearingDegrees(from start: CLLocationCoordinate2D, to end: CLLocationCoordinate2D) -> Double {
        let lat1 = start.latitude * .pi / 180
        let lat2 = end.latitude * .pi / 180
        let deltaLongitude = (end.longitude - start.longitude) * .pi / 180
        let y = sin(deltaLongitude) * cos(lat2)
        let x = cos(lat1) * sin(lat2) - sin(lat1) * cos(lat2) * cos(deltaLongitude)
        let bearing = atan2(y, x) * 180 / .pi
        return (bearing + 360).truncatingRemainder(dividingBy: 360)
    }

    private static func offsetCoordinate(
        from coordinate: CLLocationCoordinate2D,
        distanceMeters: CLLocationDistance,
        bearingDegrees: Double
    ) -> CLLocationCoordinate2D {
        let earthRadius = 6_378_137.0
        let angularDistance = distanceMeters / earthRadius
        let bearing = bearingDegrees * .pi / 180
        let latitude = coordinate.latitude * .pi / 180
        let longitude = coordinate.longitude * .pi / 180

        let destinationLatitude = asin(
            sin(latitude) * cos(angularDistance)
                + cos(latitude) * sin(angularDistance) * cos(bearing)
        )
        let destinationLongitude = longitude + atan2(
            sin(bearing) * sin(angularDistance) * cos(latitude),
            cos(angularDistance) - sin(latitude) * sin(destinationLatitude)
        )

        var normalizedLongitude = destinationLongitude * 180 / .pi
        if normalizedLongitude > 180 { normalizedLongitude -= 360 }
        if normalizedLongitude < -180 { normalizedLongitude += 360 }
        return CLLocationCoordinate2D(
            latitude: destinationLatitude * 180 / .pi,
            longitude: normalizedLongitude
        )
    }
}

private struct LivingJourneyMap: View {
    var status: AgentStatus
    var homeCoordinate: CLLocationCoordinate2D
    var petCoordinate: CLLocationCoordinate2D
    var events: [JourneyMapEvent]
    var companions: [DemoCompanionPet]
    var routePlan: JourneyRoutePlan
    var activity: JourneyActivitySnapshot
    var liveEvent: JourneyMapEvent?
    var showNearbySignals: Bool
    var showWorldCupStadiums: Bool
    @Binding var cameraPosition: MapCameraPosition
    @Binding var selectedEvent: JourneyMapEvent?
    @Binding var selectedCompanion: DemoCompanionPet?
    @Binding var selectedWorldCupHost: WorldCupHostCity?
    var onSelectWorldCupHost: (WorldCupHostCity) -> Void

    private var routeCoordinates: [CLLocationCoordinate2D] {
        JourneyRouteVisual.visibleCoordinates(
            from: activity.routeCoordinatesOverride ?? routePlan.coordinates,
            activity: activity,
            petCoordinate: petCoordinate
        )
    }

    private var visibleEvents: [JourneyMapEvent] {
        let currentOrPast = events.filter { event in
            event.displayPhase(liveEvent: liveEvent) != .upcoming
        }
        guard let nextEvent = events.first(where: { $0.displayPhase(liveEvent: liveEvent) == .upcoming }) else {
            return currentOrPast
        }
        if currentOrPast.contains(where: { $0.id == nextEvent.id }) {
            return currentOrPast
        }
        return currentOrPast + [nextEvent]
    }

    var body: some View {
        Map(position: $cameraPosition, interactionModes: .all) {
            if routeCoordinates.count > 1 {
                MapPolyline(coordinates: routeCoordinates)
                    .stroke(activity.tint.opacity(0.08), style: StrokeStyle(lineWidth: 12, lineCap: .round, lineJoin: .round))

                MapPolyline(coordinates: routeCoordinates)
                    .stroke(.white.opacity(0.66), style: StrokeStyle(lineWidth: 7, lineCap: .round, lineJoin: .round))

                MapPolyline(coordinates: routeCoordinates)
                    .stroke(activity.tint.opacity(0.74), style: StrokeStyle(lineWidth: 4, lineCap: .round, lineJoin: .round))
            }

            ForEach(visibleEvents) { event in
                Annotation("", coordinate: event.coordinate, anchor: .center) {
                    Button {
                        withAnimation(.easeInOut(duration: 0.22)) {
                            selectedEvent = event
                            selectedCompanion = nil
                        }
                    } label: {
                        if showNearbySignals {
                            JourneyEventMarker(
                                event: event,
                                phase: event.displayPhase(liveEvent: liveEvent),
                                isSelected: selectedEvent?.id == event.id
                            )
                        } else {
                            RouteStopMarker(
                                tint: event.tint,
                                phase: event.displayPhase(liveEvent: liveEvent),
                                isActive: liveEvent?.id == event.id
                            )
                        }
                    }
                    .buttonStyle(.plain)
                }
            }

            if showNearbySignals {
                ForEach(companions) { companion in
                    Annotation("", coordinate: companion.coordinate, anchor: .center) {
                        Button {
                            withAnimation(.spring(response: 0.32, dampingFraction: 0.86)) {
                                selectedCompanion = companion
                                selectedEvent = nil
                            }
                        } label: {
                            CompanionPetMarkerView(
                                companion: companion,
                                isSelected: selectedCompanion?.id == companion.id
                            )
                        }
                        .buttonStyle(.plain)
                        .contentShape(Rectangle())
                        .accessibilityLabel("\(companion.name)正在\(companion.action)")
                    }
                }
            }

            if showWorldCupStadiums {
                ForEach(WorldCupHostCity.hostCities) { host in
                    Annotation("", coordinate: host.coordinate, anchor: .center) {
                        Button {
                            withAnimation(.spring(response: 0.32, dampingFraction: 0.84)) {
                                selectedEvent = nil
                                selectedCompanion = nil
                                onSelectWorldCupHost(host)
                            }
                        } label: {
                            WorldCupStadiumMarker(
                                host: host,
                                isSelected: selectedWorldCupHost?.id == host.id
                            )
                        }
                        .buttonStyle(.plain)
                        .contentShape(Rectangle())
                        .accessibilityLabel("\(host.city)\(host.stadiumName)世界杯球场")
                    }
                }
            }

            Annotation("", coordinate: petCoordinate, anchor: .center) {
                LivePetMarkerView(
                    petID: status.petID,
                    petType: status.petType ?? .dog,
                    name: status.name,
                    statusText: activity.markerText,
                    systemImage: activity.markerSystemImage,
                    activityKind: activity.kind,
                    animationHint: activity.animationHint,
                    tint: activity.tint
                )
            }
        }
        .mapStyle(.standard(elevation: .realistic, pointsOfInterest: .excludingAll, showsTraffic: false))
        .mapControls {
            MapUserLocationButton()
            MapCompass()
        }
    }
}

private enum JourneyRouteVisual {
    static func visibleCoordinates(
        from coordinates: [CLLocationCoordinate2D],
        activity: JourneyActivitySnapshot,
        petCoordinate: CLLocationCoordinate2D
    ) -> [CLLocationCoordinate2D] {
        guard coordinates.count > 1 else { return [] }

        switch activity.kind {
        case .staying, .resting, .checkingIn:
            return []
        case .walking, .transporting:
            return focusedSlice(coordinates, around: petCoordinate)
        }
    }

    private static func focusedSlice(
        _ coordinates: [CLLocationCoordinate2D],
        around petCoordinate: CLLocationCoordinate2D
    ) -> [CLLocationCoordinate2D] {
        guard coordinates.count > 56 else { return coordinates }

        let petLocation = CLLocation(latitude: petCoordinate.latitude, longitude: petCoordinate.longitude)
        let nearestIndex = coordinates.indices.min { left, right in
            let leftLocation = CLLocation(latitude: coordinates[left].latitude, longitude: coordinates[left].longitude)
            let rightLocation = CLLocation(latitude: coordinates[right].latitude, longitude: coordinates[right].longitude)
            return leftLocation.distance(from: petLocation) < rightLocation.distance(from: petLocation)
        } ?? coordinates.startIndex

        let start = max(coordinates.startIndex, nearestIndex - 18)
        let end = min(coordinates.index(before: coordinates.endIndex), nearestIndex + 28)
        return Array(coordinates[start...end])
    }
}

private struct NavigationModeStrip: View {
    var perspective: RoutePerspective
    var routePlan: JourneyRoutePlan
    var activity: JourneyActivitySnapshot
    var showNearbySignals: Bool
    var onTogglePerspective: () -> Void
    var onToggleNearbySignals: () -> Void

    var body: some View {
        HStack(spacing: 8) {
            Label(activity.modeLabel, systemImage: activity.systemImage)
                .font(.caption.weight(.semibold))
                .foregroundStyle(DesignTokens.ink)
                .lineLimit(1)
                .minimumScaleFactor(0.78)

            Divider()
                .frame(height: 16)

            Button(action: onTogglePerspective) {
                Label(perspectiveTitle, systemImage: perspectiveSystemImage)
                    .labelStyle(.titleAndIcon)
            }
            .buttonStyle(.plain)

            Button(action: onToggleNearbySignals) {
                Image(systemName: showNearbySignals ? "eye.fill" : "eye.slash.fill")
                    .frame(width: 20, height: 20)
            }
            .buttonStyle(.plain)
            .accessibilityLabel(showNearbySignals ? "隐藏附近信号" : "显示附近信号")
        }
        .font(.caption.weight(.semibold))
        .foregroundStyle(DesignTokens.secondaryInk)
        .padding(.vertical, 8)
        .padding(.horizontal, 11)
        .background(.white.opacity(0.88))
        .clipShape(Capsule())
        .overlay {
            Capsule().stroke(.white.opacity(0.78), lineWidth: 1)
        }
        .shadow(color: DesignTokens.ink.opacity(0.08), radius: 12, x: 0, y: 7)
    }

    private var perspectiveTitle: String {
        if perspective == .threeD, activity.prefersNavigationCamera {
            return "导航"
        }
        return perspective.title
    }

    private var perspectiveSystemImage: String {
        if perspective == .threeD, activity.prefersNavigationCamera {
            return "location.north.line.fill"
        }
        return perspective.systemImage
    }
}

private struct JourneyMapAtmosphere: View {
    var tint: Color
    var date: Date = Date()

    private enum DayPhase {
        case dawn
        case day
        case dusk
        case night
    }

    private var phase: DayPhase {
        switch Calendar.current.component(.hour, from: date) {
        case 5..<8: .dawn
        case 8..<17: .day
        case 17..<20: .dusk
        default: .night
        }
    }

    private var washColors: [Color] {
        switch phase {
        case .dawn:
            [
                DesignTokens.amber.opacity(0.20),
                Color(hex: 0xFBE8C8).opacity(0.10),
                DesignTokens.porcelain.opacity(0.44)
            ]
        case .day:
            [
                Color.black.opacity(0.18),
                .clear,
                DesignTokens.porcelain.opacity(0.44)
            ]
        case .dusk:
            [
                Color(hex: 0x8A5A78).opacity(0.22),
                Color(hex: 0xE0956B).opacity(0.14),
                Color(hex: 0xF6E3CE).opacity(0.40)
            ]
        case .night:
            [
                Color(hex: 0x131E36).opacity(0.46),
                Color(hex: 0x1E2A44).opacity(0.30),
                Color(hex: 0x2A3752).opacity(0.34)
            ]
        }
    }

    var body: some View {
        ZStack {
            LinearGradient(
                colors: washColors,
                startPoint: .top,
                endPoint: .bottom
            )

            if phase != .night {
                LinearGradient(
                    colors: [
                        .clear,
                        Color(hex: 0xF8F2EA).opacity(0.36)
                    ],
                    startPoint: .center,
                    endPoint: .bottom
                )
            }

            if phase == .night {
                AmbientSignalField(
                    tint: .white,
                    warmth: Color(hex: 0xFDF6DC),
                    density: 26,
                    drift: 0.1
                )
                .opacity(0.5)
            }

            AmbientSignalField(
                tint: tint,
                warmth: DesignTokens.pollen,
                density: 16,
                drift: 0.28
            )
            .opacity(phase == .night ? 0.26 : 0.38)

            NavigationScanOverlay(tint: tint)
                .opacity(0.42)
        }
        .ignoresSafeArea()
        .allowsHitTesting(false)
        .animation(.easeInOut(duration: 1.4), value: phase)
    }
}

private struct NavigationScanOverlay: View {
    var tint: Color

    var body: some View {
        TimelineView(.animation) { timeline in
            Canvas { context, size in
                guard size.width > 0, size.height > 0 else { return }
                let phase = timeline.date.timeIntervalSinceReferenceDate.truncatingRemainder(dividingBy: 3.8) / 3.8
                let scanY = size.height * (0.19 + phase * 0.34)

                var scanLine = Path()
                scanLine.move(to: CGPoint(x: size.width * 0.08, y: scanY))
                scanLine.addLine(to: CGPoint(x: size.width * 0.92, y: scanY))
                context.stroke(
                    scanLine,
                    with: .linearGradient(
                        Gradient(colors: [.clear, tint.opacity(0.18), .white.opacity(0.18), tint.opacity(0.18), .clear]),
                        startPoint: CGPoint(x: size.width * 0.08, y: scanY),
                        endPoint: CGPoint(x: size.width * 0.92, y: scanY)
                    ),
                    style: StrokeStyle(lineWidth: 1.2, lineCap: .round)
                )

                let bracketColor = tint.opacity(0.15)
                let inset = size.width * 0.09
                let top = size.height * 0.17
                let length = size.width * 0.11
                var leftBracket = Path()
                leftBracket.move(to: CGPoint(x: inset, y: top + length))
                leftBracket.addLine(to: CGPoint(x: inset, y: top))
                leftBracket.addLine(to: CGPoint(x: inset + length, y: top))
                context.stroke(leftBracket, with: .color(bracketColor), style: StrokeStyle(lineWidth: 1.4, lineCap: .round))

                var rightBracket = Path()
                rightBracket.move(to: CGPoint(x: size.width - inset - length, y: top))
                rightBracket.addLine(to: CGPoint(x: size.width - inset, y: top))
                rightBracket.addLine(to: CGPoint(x: size.width - inset, y: top + length))
                context.stroke(rightBracket, with: .color(bracketColor), style: StrokeStyle(lineWidth: 1.4, lineCap: .round))
            }
        }
        .allowsHitTesting(false)
        .accessibilityHidden(true)
    }
}

private struct JourneyTopBar: View {
    var status: AgentStatus
    var hasUnreadPostcard: Bool
    var onCenter: () -> Void
    var onShowDayPlan: () -> Void
    var onShowPostcards: () -> Void
    var onShowTravelKit: () -> Void
    var onShowSouvenirs: () -> Void
    var onShowDNA: () -> Void
    var onReset: () -> Void

    var body: some View {
        HStack(spacing: 10) {
            HStack(spacing: 10) {
                PetSoulAssetIcon(
                    asset: .signalPaw,
                    fallbackSystemImage: "dot.radiowaves.left.and.right",
                    fallbackTint: DesignTokens.sage,
                    size: 30
                )
                    .frame(width: 34, height: 34)
                    .background(DesignTokens.mist.opacity(0.94))
                    .clipShape(Circle())

                VStack(alignment: .leading, spacing: 2) {
                    Text("\(status.name)的旅程在线")
                        .font(.headline.weight(.semibold))
                        .foregroundStyle(DesignTokens.ink)
                        .lineLimit(1)
                        .minimumScaleFactor(0.78)
                    Text("第 \(status.agentState.travelDay) 天 · \(status.agentState.location)")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(DesignTokens.secondaryInk)
                        .lineLimit(1)
                }
            }
            .padding(.vertical, 9)
            .padding(.horizontal, 10)
            .background(.white.opacity(0.9))
            .clipShape(Capsule())
            .overlay {
                Capsule().stroke(.white.opacity(0.75), lineWidth: 1)
            }

            Spacer(minLength: 0)

            TopCircleButton(systemImage: "location.fill", action: onCenter, accessibilityLabel: "回到 TA 的位置")

            Menu {
                Button(action: onShowDayPlan) {
                    Label("今日路线", systemImage: "map.fill")
                }
                Button(action: onShowPostcards) {
                    Label(hasUnreadPostcard ? "查看新明信片" : "查看明信片", systemImage: "mail.stack")
                }
                Button(action: onShowTravelKit) {
                    Label("旅行小包", systemImage: "backpack.fill")
                }
                Button(action: onShowSouvenirs) {
                    Label("带回的小东西", systemImage: "gift.fill")
                }
                Divider()
                Button(action: onShowDNA) {
                    Label("查看记忆档案", systemImage: "slider.horizontal.3")
                }
                Button(action: onReset) {
                    Label("重新寻找", systemImage: "arrow.counterclockwise")
                }
            } label: {
                ZStack(alignment: .topTrailing) {
                    Image(systemName: "ellipsis")
                        .font(.headline.weight(.bold))
                        .foregroundStyle(DesignTokens.secondaryInk)
                        .frame(width: 44, height: 44)
                        .background(.white.opacity(0.9))
                        .clipShape(Circle())
                    if hasUnreadPostcard {
                        Circle()
                            .fill(DesignTokens.clay)
                            .frame(width: 8, height: 8)
                            .offset(x: -7, y: 8)
                    }
                }
            }
            .accessibilityLabel("更多")
        }
        .shadow(color: DesignTokens.ink.opacity(0.09), radius: 16, x: 0, y: 8)
    }
}

private struct TopCircleButton: View {
    var systemImage: String
    var action: () -> Void
    var accessibilityLabel: String

    var body: some View {
        Button(action: action) {
            Image(systemName: systemImage)
                .font(.system(size: 16, weight: .semibold))
                .foregroundStyle(DesignTokens.sage)
                .frame(width: 44, height: 44)
                .background(.white.opacity(0.9))
                .clipShape(Circle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel(accessibilityLabel)
    }
}

private struct WorldCupInvitationTeaserCard: View {
    var petName: String
    var onOpen: () -> Void

    var body: some View {
        Button(action: onOpen) {
            HStack(spacing: 12) {
                ZStack {
                    SignalPulseRings(tint: DesignTokens.clay, size: 48, lineWidth: 1.2, ringCount: 2)
                        .opacity(0.68)
                    PetSoulAssetIcon(asset: .worldCupPawPass, fallbackTint: DesignTokens.clay, size: 32)
                        .frame(width: 38, height: 38)
                        .background(.white.opacity(0.84))
                        .clipShape(Circle())
                }
                .frame(width: 50, height: 50)

                VStack(alignment: .leading, spacing: 4) {
                    Text("远方球场的灯亮了")
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(DesignTokens.ink)
                        .lineLimit(1)
                    Text("\(petName) 好像收到了一封很远的邀请。")
                        .font(.caption)
                        .foregroundStyle(DesignTokens.secondaryInk)
                        .lineLimit(2)
                }

                Spacer(minLength: 0)

                Image(systemName: "chevron.right")
                    .font(.caption.weight(.bold))
                    .foregroundStyle(DesignTokens.secondaryInk)
            }
            .padding(.vertical, 12)
            .padding(.horizontal, 13)
            .background(.white.opacity(0.88))
            .clipShape(RoundedRectangle(cornerRadius: DesignTokens.cardRadius, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: DesignTokens.cardRadius, style: .continuous)
                    .stroke(.white.opacity(0.76), lineWidth: 1)
            }
            .shadow(color: DesignTokens.ink.opacity(0.11), radius: 18, x: 0, y: 9)
        }
        .buttonStyle(.plain)
        .accessibilityLabel("打开远方球场邀请")
    }
}

private struct WorldCupMapStatusCard: View {
    var selectedHost: WorldCupHostCity?
    var activeQuest: TravelQuest?
    var onOpenInvitation: () -> Void
    var onFocusAll: () -> Void
    var onClose: () -> Void

    private var title: String {
        selectedHost?.displayName ?? "北美球场已点亮"
    }

    private var detail: String {
        if let activeQuest {
            return "\(activeQuest.destination) 已经放进旅行包，TA 会先走完当前这段路。"
        }
        if let selectedHost {
            return selectedHost.atmosphereHint
        }
        return "点一个亮起的球场，再决定要不要帮 TA 准备旅行包。"
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 11) {
            HStack(alignment: .top, spacing: 10) {
                PetSoulAssetIcon(asset: .worldCupStadiumLights, fallbackTint: DesignTokens.clay, size: 28)
                    .frame(width: 34, height: 34)
                    .background(DesignTokens.clay.opacity(0.12))
                    .clipShape(Circle())

                VStack(alignment: .leading, spacing: 3) {
                    Text(title)
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(DesignTokens.ink)
                        .lineLimit(2)
                    Text(detail)
                        .font(.caption)
                        .foregroundStyle(DesignTokens.secondaryInk)
                        .lineLimit(2)
                        .fixedSize(horizontal: false, vertical: true)
                }

                Spacer(minLength: 0)

                Button(action: onClose) {
                    Image(systemName: "xmark")
                        .font(.caption.weight(.bold))
                        .foregroundStyle(DesignTokens.secondaryInk)
                        .frame(width: 28, height: 28)
                        .background(.white.opacity(0.68))
                        .clipShape(Circle())
                }
                .buttonStyle(.plain)
                .accessibilityLabel("关闭球场地图")
            }

            HStack(spacing: 9) {
                Button(action: onOpenInvitation) {
                    Label(activeQuest == nil ? "打开邀请" : "查看邀请", systemImage: "envelope.open.fill")
                        .frame(maxWidth: .infinity)
                }
                .quietActionStyle()

                Button(action: onFocusAll) {
                    Label("全部球场", systemImage: "map.fill")
                        .frame(maxWidth: .infinity)
                }
                .quietActionStyle()
            }
        }
        .padding(13)
        .background(.white.opacity(0.9))
        .clipShape(RoundedRectangle(cornerRadius: DesignTokens.cardRadius, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: DesignTokens.cardRadius, style: .continuous)
                .stroke(.white.opacity(0.78), lineWidth: 1)
        }
        .shadow(color: DesignTokens.ink.opacity(0.12), radius: 20, x: 0, y: 10)
    }
}

private struct WorldCupStadiumMarker: View {
    var host: WorldCupHostCity
    var isSelected: Bool

    var body: some View {
        VStack(spacing: 4) {
            ZStack {
                SignalPulseRings(
                    tint: isSelected ? DesignTokens.clay : DesignTokens.sea,
                    size: isSelected ? 54 : 42,
                    lineWidth: 1.1,
                    ringCount: isSelected ? 3 : 2
                )
                .opacity(isSelected ? 0.78 : 0.48)

                PetSoulAssetIcon(
                    asset: .worldCupFootball,
                    fallbackTint: isSelected ? DesignTokens.clay : DesignTokens.dusk,
                    size: isSelected ? 28 : 22
                )
                    .frame(width: isSelected ? 34 : 28, height: isSelected ? 34 : 28)
                    .background(.white.opacity(0.9))
                    .clipShape(Circle())
                    .overlay {
                        Circle()
                            .stroke((isSelected ? DesignTokens.clay : .white).opacity(0.9), lineWidth: isSelected ? 2 : 1)
                    }
                    .shadow(color: DesignTokens.ink.opacity(0.15), radius: 9, x: 0, y: 4)
            }
            .frame(width: 56, height: 48)

            if isSelected {
                Text(host.city)
                    .font(.caption2.weight(.bold))
                    .foregroundStyle(DesignTokens.ink)
                    .lineLimit(1)
                    .padding(.vertical, 4)
                    .padding(.horizontal, 7)
                    .background(.white.opacity(0.9))
                    .clipShape(Capsule())
            }
        }
        .animation(.spring(response: 0.28, dampingFraction: 0.82), value: isSelected)
    }
}

private struct WorldCupQuestSheetView: View {
    var petName: String
    var currentCity: String
    var selectedHost: WorldCupHostCity?
    var hosts: [WorldCupHostCity]
    var existingQuest: TravelQuest?
    var isPreparing: Bool
    var onShowMap: () -> Void
    var onSelectHost: (WorldCupHostCity) -> Void
    var onPrepare: (WorldCupHostCity, Set<WorldCupBagItem>, String?) -> Void

    @State private var selectedBagItems: Set<WorldCupBagItem> = [.scarf, .snack, .footballBadge]
    @State private var ownerMessage = "看到热闹的地方，也要记得慢慢走。"

    private var chosenHost: WorldCupHostCity? {
        selectedHost ?? hosts.first
    }

    var body: some View {
        ZStack {
            AppBackground()

            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    header

                    if let existingQuest {
                        ExistingWorldCupQuestCard(quest: existingQuest)
                    }

                    hostPicker

                    PawPassPreviewCard(host: chosenHost, currentCity: currentCity)

                    travelBagPicker

                    ownerMessageField

                    actionSection
                }
                .padding(DesignTokens.pagePadding)
            }
        }
        .navigationTitle("远方球场邀请")
        .navigationBarTitleDisplayMode(.inline)
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 9) {
            HStack(spacing: 10) {
                PetSoulAssetIcon(asset: .worldCupPawTicket, fallbackTint: DesignTokens.clay, size: 30)
                    .frame(width: 38, height: 38)
                    .background(DesignTokens.clay.opacity(0.12))
                    .clipShape(Circle())

                VStack(alignment: .leading, spacing: 2) {
                    Text("远方球场邀请卡")
                        .font(.title2.weight(.semibold))
                        .foregroundStyle(DesignTokens.ink)
                    Text("先看见，不立刻出发")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(DesignTokens.secondaryInk)
                }
            }

            Text("北美有几盏球场灯亮起来了。你可以帮 \(petName) 选一个想看的地方，把邀请先放进旅行包。TA 会先把 \(currentCity) 这段路走完。")
                .font(.subheadline)
                .foregroundStyle(DesignTokens.secondaryInk)
                .lineSpacing(3)
                .fixedSize(horizontal: false, vertical: true)

            Button(action: onShowMap) {
                Label("回到地图看亮起的球场", systemImage: "map.fill")
                    .frame(maxWidth: .infinity)
            }
            .quietActionStyle()
        }
        .padding(16)
        .background(.white.opacity(0.78))
        .clipShape(RoundedRectangle(cornerRadius: DesignTokens.cardRadius, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: DesignTokens.cardRadius, style: .continuous)
                .stroke(DesignTokens.softLine, lineWidth: 1)
        }
    }

    private var hostPicker: some View {
        VStack(alignment: .leading, spacing: 10) {
            Label("选择一个亮起的球场", systemImage: "sportscourt.fill")
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(DesignTokens.ink)

            LazyVGrid(columns: [GridItem(.adaptive(minimum: 148), spacing: 10)], spacing: 10) {
                ForEach(hosts) { host in
                    Button {
                        onSelectHost(host)
                    } label: {
                        WorldCupHostTile(host: host, isSelected: chosenHost?.id == host.id)
                    }
                    .buttonStyle(.plain)
                }
            }
        }
    }

    private var travelBagPicker: some View {
        VStack(alignment: .leading, spacing: 10) {
            Label("旅行包里带一点什么", systemImage: "backpack.fill")
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(DesignTokens.ink)

            LazyVGrid(columns: [GridItem(.adaptive(minimum: 140), spacing: 10)], spacing: 10) {
                ForEach(WorldCupBagItem.allCases) { item in
                    Button {
                        if selectedBagItems.contains(item) {
                            selectedBagItems.remove(item)
                        } else {
                            selectedBagItems.insert(item)
                        }
                    } label: {
                        WorldCupBagItemTile(item: item, isSelected: selectedBagItems.contains(item))
                    }
                    .buttonStyle(.plain)
                }
            }
        }
        .padding(14)
        .background(.white.opacity(0.76))
        .clipShape(RoundedRectangle(cornerRadius: DesignTokens.cardRadius, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: DesignTokens.cardRadius, style: .continuous)
                .stroke(DesignTokens.softLine, lineWidth: 1)
        }
    }

    private var ownerMessageField: some View {
        VStack(alignment: .leading, spacing: 8) {
            Label("给主人留在旅行包里的话", systemImage: "text.bubble.fill")
                .font(.caption.weight(.bold))
                .foregroundStyle(DesignTokens.secondaryInk)

            TextField("比如：看见热闹的地方，也要记得慢慢走。", text: $ownerMessage, axis: .vertical)
                .lineLimit(2...4)
                .font(.body)
                .textFieldStyle(.plain)
                .padding(12)
                .background(.white.opacity(0.78))
                .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
        }
        .padding(14)
        .background(DesignTokens.mist.opacity(0.54))
        .clipShape(RoundedRectangle(cornerRadius: DesignTokens.cardRadius, style: .continuous))
    }

    private var actionSection: some View {
        VStack(alignment: .leading, spacing: 9) {
            Button {
                guard let chosenHost else { return }
                onPrepare(chosenHost, selectedBagItems, ownerMessage)
            } label: {
                HStack {
                    if isPreparing {
                        ProgressView()
                            .tint(.white)
                    }
                    Label("放进旅行包", systemImage: "backpack.fill")
                        .frame(maxWidth: .infinity)
                }
            }
            .primaryActionStyle()
            .disabled(isPreparing || chosenHost == nil)

            Text("这不是现实签证或真实球票。Paw Pass 只是 \(petName) 在另一端世界远行用的小小通行证。")
                .font(.caption)
                .foregroundStyle(DesignTokens.secondaryInk)
                .lineSpacing(2)
        }
    }
}

private struct WorldCupHostTile: View {
    var host: WorldCupHostCity
    var isSelected: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 7) {
            HStack(spacing: 8) {
                PetSoulAssetIcon(
                    asset: .worldCupFootball,
                    fallbackTint: isSelected ? DesignTokens.clay : DesignTokens.dusk,
                    size: 22
                )
                    .frame(width: 26, height: 26)
                    .background((isSelected ? DesignTokens.clay : DesignTokens.dusk).opacity(0.12))
                    .clipShape(Circle())

                VStack(alignment: .leading, spacing: 1) {
                    Text(host.city)
                        .font(.caption.weight(.bold))
                        .foregroundStyle(DesignTokens.ink)
                        .lineLimit(1)
                    Text(host.country)
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(DesignTokens.secondaryInk)
                        .lineLimit(1)
                }

                Spacer(minLength: 0)
            }

            Text(host.stadiumName)
                .font(.caption)
                .foregroundStyle(DesignTokens.secondaryInk)
                .lineLimit(1)

            Text(host.atmosphereHint)
                .font(.caption2)
                .foregroundStyle(DesignTokens.secondaryInk)
                .lineLimit(2)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(11)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(isSelected ? DesignTokens.petal.opacity(0.72) : .white.opacity(0.78))
        .clipShape(RoundedRectangle(cornerRadius: DesignTokens.cardRadius, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: DesignTokens.cardRadius, style: .continuous)
                .stroke(isSelected ? DesignTokens.clay.opacity(0.62) : DesignTokens.softLine, lineWidth: 1)
        }
    }
}

private extension WorldCupBagItem {
    var petSoulAsset: PetSoulAsset {
        switch self {
        case .scarf:
            .worldCupScarf
        case .snack:
            .worldCupSnacks
        case .cameraCharm:
            .worldCupCamera
        case .footballBadge:
            .worldCupMedal
        case .smallFlag:
            .worldCupFlag
        }
    }
}

private struct WorldCupBagItemTile: View {
    var item: WorldCupBagItem
    var isSelected: Bool

    var body: some View {
        HStack(spacing: 8) {
            PetSoulAssetIcon(
                asset: item.petSoulAsset,
                fallbackSystemImage: item.systemImage,
                fallbackTint: isSelected ? DesignTokens.clay : DesignTokens.secondaryInk,
                size: 24
            )
                .frame(width: 28, height: 28)
                .background((isSelected ? DesignTokens.clay : DesignTokens.softLine).opacity(0.14))
                .clipShape(Circle())

            Text(item.title)
                .font(.caption.weight(.semibold))
                .foregroundStyle(DesignTokens.ink)
                .lineLimit(1)

            Spacer(minLength: 0)

            Image(systemName: isSelected ? "checkmark.circle.fill" : "circle")
                .font(.caption.weight(.bold))
                .foregroundStyle(isSelected ? DesignTokens.clay : DesignTokens.softLine)
        }
        .padding(10)
        .background(isSelected ? DesignTokens.petal.opacity(0.58) : .white.opacity(0.72))
        .clipShape(RoundedRectangle(cornerRadius: DesignTokens.cardRadius, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: DesignTokens.cardRadius, style: .continuous)
                .stroke(isSelected ? DesignTokens.clay.opacity(0.58) : DesignTokens.softLine, lineWidth: 1)
        }
    }
}

private struct PawPassPreviewCard: View {
    var host: WorldCupHostCity?
    var currentCity: String

    var body: some View {
        VStack(alignment: .leading, spacing: 11) {
            HStack(spacing: 10) {
                PetSoulAssetIcon(asset: .worldCupPawPass, fallbackTint: DesignTokens.sage, size: 30)
                    .frame(width: 38, height: 38)
                    .background(DesignTokens.sage.opacity(0.12))
                    .clipShape(Circle())

                VStack(alignment: .leading, spacing: 2) {
                    Text("Paw Pass 准备预览")
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(DesignTokens.ink)
                    Text("虚拟通行证，不是现实签证")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(DesignTokens.secondaryInk)
                }
            }

            VStack(alignment: .leading, spacing: 7) {
                PawPassStep(title: "确认现在位置", value: currentCity, systemImage: "location.fill")
                PawPassStep(title: "远方球场", value: host?.displayName ?? "等待选择", systemImage: "sportscourt.fill")
                PawPassStep(title: "出发节奏", value: "先走完今天这段路", systemImage: "clock.fill")
            }
        }
        .padding(14)
        .background(.white.opacity(0.78))
        .clipShape(RoundedRectangle(cornerRadius: DesignTokens.cardRadius, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: DesignTokens.cardRadius, style: .continuous)
                .stroke(DesignTokens.softLine, lineWidth: 1)
        }
    }
}

private struct PawPassStep: View {
    var title: String
    var value: String
    var systemImage: String

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: systemImage)
                .font(.caption.weight(.bold))
                .foregroundStyle(DesignTokens.sage)
                .frame(width: 24, height: 24)
                .background(DesignTokens.sage.opacity(0.11))
                .clipShape(Circle())

            Text(title)
                .font(.caption.weight(.bold))
                .foregroundStyle(DesignTokens.secondaryInk)
                .frame(width: 82, alignment: .leading)

            Text(value)
                .font(.caption.weight(.semibold))
                .foregroundStyle(DesignTokens.ink)
                .lineLimit(2)
                .fixedSize(horizontal: false, vertical: true)
        }
    }
}

private struct ExistingWorldCupQuestCard: View {
    var quest: TravelQuest

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: "checkmark.seal.fill")
                .font(.headline.weight(.semibold))
                .foregroundStyle(DesignTokens.sage)
                .frame(width: 34, height: 34)
                .background(DesignTokens.sage.opacity(0.12))
                .clipShape(Circle())

            VStack(alignment: .leading, spacing: 4) {
                Text("邀请已经收好")
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(DesignTokens.ink)
                Text("\(quest.destination) · \(quest.status.displayName)。TA 会按自己的节奏继续。")
                    .font(.caption)
                    .foregroundStyle(DesignTokens.secondaryInk)
                    .lineLimit(3)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(13)
        .background(DesignTokens.mist.opacity(0.62))
        .clipShape(RoundedRectangle(cornerRadius: DesignTokens.cardRadius, style: .continuous))
    }
}

private struct LiveSignalPanel: View {
    var status: AgentStatus
    var selectedEvent: JourneyMapEvent?
    var liveEvent: JourneyMapEvent?
    var routePlan: JourneyRoutePlan
    var activity: JourneyActivitySnapshot
    var needState: PetNeedState?
    var visibleThought: LifeVisibleThought?
    var translation: ThoughtTranslation?
    var isTranslating: Bool
    var hasUnreadPostcard: Bool
    @Binding var isExpanded: Bool
    var onShowDayPlan: () -> Void
    var onShowPostcards: () -> Void
    var onShowTravelKit: () -> Void
    var onShowSouvenirs: () -> Void
    var onTranslate: () -> Void
    var onLike: () -> Void
    var onDislike: () -> Void

    private var visibleEvent: JourneyMapEvent? {
        if activity.isSleepLike {
            return nil
        }
        if let selectedEvent, selectedEvent.displayPhase(liveEvent: liveEvent) == .current {
            return selectedEvent
        }
        return liveEvent
    }

    private var thoughtText: String {
        status.agentState.latestThought?.text ?? status.agentState.statusNote
    }

    private var headline: String {
        if isSleepMode {
            return activity.sleepHeadline(petName: status.name)
        }
        if let visibleEvent {
            return visibleEvent.title
        }
        return activity.title
    }

    private var supportingText: String {
        if isSleepMode {
            return activity.sleepDetail(petName: status.name)
        }
        if let visibleEvent {
            return visibleEvent.detail.petSoulUserFacingText
        }
        return (activity.detail.isEmpty ? thoughtText : activity.detail).petSoulUserFacingText
    }

    private var signalTint: Color {
        isSleepMode ? DesignTokens.dusk : (visibleEvent?.tint ?? activity.tint)
    }

    private var isSleepMode: Bool {
        activity.isSleepLike
    }

    private var compactEyebrow: String {
        if isSleepMode {
            return "TA 睡着了"
        }
        if let selectedEvent, selectedEvent.displayPhase(liveEvent: liveEvent) == .current {
            return "TA 此刻在这里"
        }
        return activity.eyebrow
    }

    private var moodSummary: String {
        if status.agentState.energy < 35 {
            return "慢慢蓄电"
        }
        if status.agentState.happiness >= 78 {
            return "心里亮亮的"
        }
        if status.agentState.happiness >= 55 {
            return "安稳走着"
        }
        return "想放慢一点"
    }

    private var curiositySummary: String {
        if status.agentState.curiosity >= 78 {
            return "想多看看"
        }
        if status.agentState.curiosity >= 52 {
            return "按节奏看"
        }
        return "先靠近一点"
    }

    private var needSummary: String {
        switch needState?.primaryNeed {
        case "rest":
            return "想歇一下"
        case "drink":
            return "想喝点"
        case "eat":
            return "想吃点"
        case "quiet":
            return "想安静"
        default:
            break
        }
        if let sleepiness = needState?.sleepiness, sleepiness >= 76 {
            return "想睡会儿"
        }
        if let thirst = needState?.thirst, thirst >= 76 {
            return "想补水"
        }
        if let hunger = needState?.hunger, hunger >= 76 {
            return "想吃点"
        }
        return curiositySummary
    }

    private var expandedPanelMaxHeight: CGFloat {
        min(UIScreen.main.bounds.height * 0.58, 560)
    }

    private var nextStopName: String {
        guard let visibleEvent else { return status.agentState.location }
        return visibleEvent.place
            .components(separatedBy: "·")
            .last?
            .trimmingCharacters(in: .whitespacesAndNewlines) ?? visibleEvent.place
    }

    var body: some View {
        VStack(alignment: .leading, spacing: isExpanded ? 12 : 8) {
            Capsule()
                .fill(DesignTokens.secondaryInk.opacity(0.18))
                .frame(width: 38, height: 4)
                .frame(maxWidth: .infinity)
                .padding(.top, 3)

            Button {
                withAnimation(.spring(response: 0.34, dampingFraction: 0.86)) {
                    isExpanded.toggle()
                }
            } label: {
                compactHeader
            }
            .buttonStyle(.plain)

            if isExpanded {
                ScrollView(showsIndicators: false) {
                    expandedContent
                        .padding(.bottom, 4)
                }
                .frame(maxHeight: expandedPanelMaxHeight)
                .transition(.opacity.combined(with: .move(edge: .bottom)))
            }
        }
        .padding(.horizontal, 14)
        .padding(.bottom, isExpanded ? 15 : 12)
        .background(panelBackground)
        .clipShape(RoundedRectangle(cornerRadius: 25, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 25, style: .continuous)
                .stroke(.white.opacity(0.72), lineWidth: 1)
        }
        .shadow(color: DesignTokens.ink.opacity(0.16), radius: 26, x: 0, y: 13)
        .animation(.spring(response: 0.34, dampingFraction: 0.86), value: isExpanded)
    }

    private var compactHeader: some View {
        HStack(spacing: 12) {
            ZStack {
                if isSleepMode {
                    SleepBreathingHalo(tint: signalTint, size: isExpanded ? 58 : 52)
                } else {
                    SignalPulseRings(tint: signalTint, size: isExpanded ? 52 : 46, lineWidth: 1.2, ringCount: 2)
                        .opacity(0.68)
                }
                PixelPetActivityAnimation(
                    hint: activity.animationHint,
                    petType: status.petType ?? .dog,
                    tint: signalTint
                )
                .frame(width: 38, height: 38)
                .background(signalTint.opacity(0.13))
                .clipShape(RoundedRectangle(cornerRadius: 9, style: .continuous))
            }
            .frame(width: 43, height: 43)

            VStack(alignment: .leading, spacing: 4) {
                HStack(spacing: 6) {
                    Text(compactEyebrow)
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(DesignTokens.secondaryInk)
                        .lineLimit(1)

                    if isSleepMode {
                        SleepBreathDot(tint: signalTint)
                    } else {
                        NavigationPulseDot(tint: signalTint)
                    }
                }

                Text(headline)
                    .font(.headline.weight(.semibold))
                    .foregroundStyle(DesignTokens.ink)
                    .lineLimit(isExpanded ? 2 : 1)
                    .fixedSize(horizontal: false, vertical: true)

                HStack(spacing: 6) {
                    if isSleepMode {
                        Label("轻睡中", systemImage: "moon.zzz.fill")
                        Text(activity.sleepRemainingText)
                    } else {
                        Label(activity.modeLabel, systemImage: activity.systemImage)
                        Text("下一站 \(nextStopName)")
                    }
                }
                .font(.caption.weight(.semibold))
                .foregroundStyle(DesignTokens.secondaryInk)
                .lineLimit(1)
                .minimumScaleFactor(0.72)
            }

            Spacer(minLength: 0)

            VStack(spacing: 5) {
                SignalBars(tint: signalTint)
                Image(systemName: isExpanded ? "chevron.down" : "chevron.up")
                    .font(.caption.weight(.bold))
                    .foregroundStyle(DesignTokens.secondaryInk)
                    .frame(width: 24, height: 24)
                    .background(.white.opacity(0.62))
                    .clipShape(Circle())
            }
        }
        .contentShape(Rectangle())
        .padding(.top, 2)
    }

    private var expandedContent: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(supportingText)
                .font(.subheadline)
                .foregroundStyle(DesignTokens.secondaryInk)
                .lineSpacing(3)
                .lineLimit(isSleepMode ? 4 : 3)
                .fixedSize(horizontal: false, vertical: true)

            if isSleepMode {
                SleepRestStatusCard(
                    petName: status.name,
                    activity: activity,
                    tint: signalTint
                )
            }

            if !isSleepMode, let thought = status.agentState.latestThought {
                PetTransmissionView(
                    thought: thought,
                    translation: translation,
                    isTranslating: isTranslating,
                    onTranslate: onTranslate
                )
            }

            if !isSleepMode, let visibleThought {
                PetVisibleThoughtCard(thought: visibleThought, tint: signalTint)
            }

            if !isSleepMode {
                PetCurrentActivityCard(
                    activity: activity,
                    nextStopName: nextStopName,
                    tint: signalTint
                )
            }

            if isSleepMode {
                SleepQuietHint(tint: signalTint)
            } else {
                NavigationTelemetryStrip(
                    routePlan: routePlan,
                    activity: activity,
                    nextStop: nextStopName
                )
            }

            if !isSleepMode {
                HStack(spacing: 8) {
                    SoftSignalChip(title: "外面", value: status.agentState.weather.petSoulUserFacingText, systemImage: "cloud.sun")
                    SoftSignalChip(title: "现在", value: moodSummary, systemImage: "heart")
                    SoftSignalChip(title: "需要", value: needSummary, systemImage: "sparkles")
                }
            }

            HStack(spacing: 10) {
                Button(action: onShowDayPlan) {
                    PetSoulAssetLabel(
                        title: "今天路线",
                        asset: .travelMap,
                        fallbackSystemImage: "map.fill",
                        tint: signalTint
                    )
                        .frame(maxWidth: .infinity)
                }
                .quietActionStyle()

                Button(action: onShowPostcards) {
                    PetSoulAssetLabel(
                        title: hasUnreadPostcard ? "新明信片" : "明信片",
                        asset: .postcardMemory,
                        fallbackSystemImage: "mail",
                        tint: signalTint
                    )
                        .frame(maxWidth: .infinity)
                }
                .quietActionStyle()
            }

            HStack(spacing: 10) {
                Button(action: onShowTravelKit) {
                    PetSoulAssetLabel(
                        title: "旅行小包",
                        asset: .travelBag,
                        fallbackSystemImage: "backpack.fill",
                        tint: signalTint
                    )
                        .frame(maxWidth: .infinity)
                }
                .quietActionStyle()

                Button(action: onShowSouvenirs) {
                    Label("小收藏", systemImage: "gift.fill")
                        .frame(maxWidth: .infinity)
                }
                .quietActionStyle()
            }

            if !isSleepMode {
                HStack(spacing: 10) {
                    FeedbackButton(
                        title: "收藏攻略",
                        systemImage: "bookmark.fill",
                        tint: DesignTokens.clay,
                        action: onLike
                    )

                    FeedbackButton(
                        title: "不适合我",
                        systemImage: "xmark.circle.fill",
                        tint: DesignTokens.secondaryInk,
                        action: onDislike
                    )
                }
            }
        }
    }

    private var panelBackground: some View {
        ZStack {
            RoundedRectangle(cornerRadius: 25, style: .continuous)
                .fill(.ultraThinMaterial)
            RoundedRectangle(cornerRadius: 25, style: .continuous)
                .fill(.white.opacity(isSleepMode ? 0.68 : (isExpanded ? 0.72 : 0.58)))
            LinearGradient(
                colors: [
                    signalTint.opacity(isSleepMode ? 0.20 : 0.12),
                    isSleepMode ? DesignTokens.sky.opacity(0.22) : .clear,
                    (isSleepMode ? DesignTokens.dusk : DesignTokens.porcelain).opacity(isSleepMode ? 0.13 : 0.34)
                ],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
        }
    }

}

private struct PixelPetActivityAnimation: View {
    var hint: String
    var petType: PetType
    var tint: Color

    var body: some View {
        TimelineView(.animation) { timeline in
            Canvas { context, size in
                let tick = Int(timeline.date.timeIntervalSinceReferenceDate * 3) % 4
                let cell = min(size.width, size.height) / 12
                let origin = CGPoint(
                    x: (size.width - cell * 12) / 2,
                    y: (size.height - cell * 12) / 2
                )

                func rect(_ x: Int, _ y: Int, _ color: Color, alpha: Double = 1.0) {
                    let inset = max(0.35, cell * 0.08)
                    let frame = CGRect(
                        x: origin.x + CGFloat(x) * cell + inset,
                        y: origin.y + CGFloat(y) * cell + inset,
                        width: cell - inset * 2,
                        height: cell - inset * 2
                    )
                    context.fill(Path(frame), with: .color(color.opacity(alpha)))
                }

                let ink = DesignTokens.ink
                let soft = tint.opacity(0.82)
                let warm = DesignTokens.pollen
                let blush = DesignTokens.clay
                let bodyOffset = hint == "walking" ? (tick % 2) : 0

                drawPet(rect: rect, ink: ink, soft: soft, warm: warm, bodyOffset: bodyOffset)

                switch hint {
                case "coffee_drink":
                    drawCup(rect: rect, tick: tick, color: blush)
                case "gaming":
                    drawScreen(rect: rect, tick: tick, color: DesignTokens.dusk)
                case "camera":
                    drawCamera(rect: rect, tick: tick, color: warm)
                case "transport_flight":
                    drawPlane(rect: rect, tick: tick, color: DesignTokens.dusk)
                case "transport_train":
                    drawTrain(rect: rect, tick: tick, color: DesignTokens.sage)
                case "transport_car":
                    drawCar(rect: rect, tick: tick, color: DesignTokens.amber)
                case "transport_ferry", "sightseeing_sea":
                    drawWaves(rect: rect, tick: tick, color: DesignTokens.dusk)
                case "snack":
                    drawSnack(rect: rect, tick: tick, color: warm)
                case "sleep":
                    drawSleep(rect: rect, tick: tick, color: DesignTokens.dusk)
                default:
                    drawSpark(rect: rect, tick: tick, color: soft)
                }
            }
        }
        .accessibilityLabel(accessibilityLabel)
    }

    private var accessibilityLabel: String {
        switch hint {
        case "coffee_drink": "TA 正在喝咖啡"
        case "gaming": "TA 正在玩游戏"
        case "camera": "TA 正在观察附近"
        case "transport_flight": "TA 正在乘飞机"
        case "transport_train": "TA 正在乘火车"
        case "transport_car": "TA 正在坐车"
        case "transport_ferry": "TA 正在坐船"
        case "snack": "TA 正在吃东西"
        case "sleep": "TA 正在休息"
        case "walking": "TA 正在散步"
        default: "TA 正在观察附近"
        }
    }

    private func drawPet(
        rect: (Int, Int, Color, Double) -> Void,
        ink: Color,
        soft: Color,
        warm: Color,
        bodyOffset: Int
    ) {
        switch petType {
        case .rabbit:
            for (x, y) in [(4, 0), (4, 1), (7, 0), (7, 1), (4, 2), (7, 2)] {
                rect(x, y + bodyOffset, ink, 0.9)
            }
        case .cat:
            for (x, y) in [(3, 2), (4, 1), (7, 1), (8, 2)] {
                rect(x, y + bodyOffset, ink, 0.92)
            }
        case .parrot, .bird:
            for (x, y) in [(4, 2), (7, 2), (3, 3), (8, 3)] {
                rect(x, y + bodyOffset, ink, 0.85)
            }
            rect(8, 5 + bodyOffset, warm, 0.95)
            rect(9, 5 + bodyOffset, warm, 0.75)
        case .hamster:
            for (x, y) in [(3, 3), (8, 3), (3, 4), (8, 4)] {
                rect(x, y + bodyOffset, ink, 0.82)
            }
        case .dog, .other:
            for (x, y) in [(3, 2), (3, 3), (8, 2), (8, 3)] {
                rect(x, y + bodyOffset, ink, 0.92)
            }
        }

        for x in 4...7 {
            rect(x, 3 + bodyOffset, ink, 0.92)
            rect(x, 4 + bodyOffset, ink, 0.92)
        }
        rect(3, 4 + bodyOffset, ink, 0.88)
        rect(8, 4 + bodyOffset, ink, 0.88)
        rect(5, 4 + bodyOffset, warm, 0.86)
        rect(7, 4 + bodyOffset, warm, 0.86)
        rect(6, 5 + bodyOffset, soft, 0.9)

        if petType == .parrot || petType == .bird {
            rect(3, 6 + bodyOffset, soft, 0.74)
            rect(4, 7 + bodyOffset, soft, 0.56)
            rect(8, 6 + bodyOffset, soft, 0.74)
        }

        for x in 4...8 {
            rect(x, 6 + bodyOffset, ink, 0.9)
            rect(x, 7 + bodyOffset, ink, 0.82)
        }
        rect(3, 7 + bodyOffset, ink, 0.7)
        rect(8, 8 + bodyOffset, ink, 0.7)
    }

    private func drawCup(rect: (Int, Int, Color, Double) -> Void, tick: Int, color: Color) {
        rect(9, 7, color, 0.9)
        rect(10, 7, color, 0.9)
        rect(9, 8, color, 0.84)
        rect(10, 8, color, 0.84)
        rect(11, 8, color, 0.5)
        rect(9, 5 - tick % 2, color, 0.34)
        rect(10, 4 + tick % 2, color, 0.26)
    }

    private func drawScreen(rect: (Int, Int, Color, Double) -> Void, tick: Int, color: Color) {
        for x in 8...10 {
            rect(x, 6, color, 0.82)
            rect(x, 7, color, tick % 2 == 0 ? 0.45 : 0.72)
        }
        rect(9, 8, color, 0.55)
        rect(8 + tick % 2, 9, color, 0.7)
    }

    private func drawCamera(rect: (Int, Int, Color, Double) -> Void, tick: Int, color: Color) {
        for x in 8...10 {
            rect(x, 7, color, 0.84)
            rect(x, 8, color, 0.78)
        }
        rect(9, 8, .white, 0.9)
        if tick == 0 {
            rect(10, 5, color, 0.55)
            rect(11, 4, color, 0.42)
        }
    }

    private func drawPlane(rect: (Int, Int, Color, Double) -> Void, tick: Int, color: Color) {
        let y = 8 - tick % 2
        for x in 7...10 { rect(x, y, color, 0.78) }
        rect(9, y - 1, color, 0.7)
        rect(9, y + 1, color, 0.7)
        rect(11, y, color, 0.48)
    }

    private func drawTrain(rect: (Int, Int, Color, Double) -> Void, tick: Int, color: Color) {
        for x in 7...10 {
            rect(x, 7, color, 0.82)
            rect(x, 8, color, 0.72)
        }
        rect(8, 7, .white, 0.72)
        rect(10, 9, color, tick % 2 == 0 ? 0.72 : 0.4)
    }

    private func drawCar(rect: (Int, Int, Color, Double) -> Void, tick: Int, color: Color) {
        for x in 7...10 { rect(x, 8, color, 0.8) }
        rect(8, 7, color, 0.64)
        rect(9, 7, color, 0.64)
        rect(7, 9, color, tick % 2 == 0 ? 0.75 : 0.45)
        rect(10, 9, color, tick % 2 == 0 ? 0.45 : 0.75)
    }

    private func drawWaves(rect: (Int, Int, Color, Double) -> Void, tick: Int, color: Color) {
        for x in 7...11 where (x + tick) % 2 == 0 {
            rect(x, 9, color, 0.5)
        }
        for x in 8...10 where (x + tick) % 2 == 1 {
            rect(x, 10, color, 0.35)
        }
    }

    private func drawSnack(rect: (Int, Int, Color, Double) -> Void, tick: Int, color: Color) {
        rect(9, 7, color, 0.9)
        rect(10, 7, color, 0.78)
        rect(9, 8, color, 0.7)
        rect(8, 6 + tick % 2, color, 0.38)
    }

    private func drawSleep(rect: (Int, Int, Color, Double) -> Void, tick: Int, color: Color) {
        for x in 3...8 {
            rect(x, 7, DesignTokens.sky, 0.62)
            rect(x, 8, color, 0.28)
        }
        rect(2, 6, .white, 0.74)
        rect(3, 6, .white, 0.58)
        rect(8, 3, color, tick == 0 ? 0.35 : 0.8)
        rect(9, 2, color, tick == 1 ? 0.35 : 0.7)
        rect(10, 1, color, tick == 2 ? 0.35 : 0.62)
    }

    private func drawSpark(rect: (Int, Int, Color, Double) -> Void, tick: Int, color: Color) {
        rect(9, 5, color, tick % 2 == 0 ? 0.72 : 0.28)
        rect(10, 4, color, tick % 2 == 1 ? 0.66 : 0.25)
        rect(10, 6, color, 0.42)
    }
}

private struct SleepBreathingHalo: View {
    var tint: Color
    var size: CGFloat

    var body: some View {
        TimelineView(.animation) { timeline in
            let phase = (sin(timeline.date.timeIntervalSinceReferenceDate * 1.4) + 1) / 2
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .fill(
                    LinearGradient(
                        colors: [
                            tint.opacity(0.10 + phase * 0.08),
                            DesignTokens.sky.opacity(0.22 + phase * 0.08)
                        ],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    )
                )
                .frame(width: size, height: size)
                .overlay {
                    RoundedRectangle(cornerRadius: 14, style: .continuous)
                        .stroke(tint.opacity(0.12 + phase * 0.10), lineWidth: 1)
                }
                .scaleEffect(0.96 + phase * 0.06)
        }
        .allowsHitTesting(false)
        .accessibilityHidden(true)
    }
}

private struct SleepBreathDot: View {
    var tint: Color

    var body: some View {
        TimelineView(.animation) { timeline in
            let phase = (sin(timeline.date.timeIntervalSinceReferenceDate * 1.8) + 1) / 2
            HStack(spacing: 3) {
                ForEach(0..<3, id: \.self) { index in
                    Circle()
                        .fill(tint.opacity(0.32 + phase * 0.32))
                        .frame(width: 3 + CGFloat(index), height: 3 + CGFloat(index))
                        .offset(y: CGFloat(index) * -1)
                }
            }
        }
        .frame(width: 18, height: 12)
        .allowsHitTesting(false)
        .accessibilityHidden(true)
    }
}

private struct SleepRestStatusCard: View {
    var petName: String
    var activity: JourneyActivitySnapshot
    var tint: Color

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 9) {
                Image(systemName: "moon.zzz.fill")
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundStyle(tint)
                    .frame(width: 32, height: 32)
                    .background(tint.opacity(0.13))
                    .clipShape(Circle())

                VStack(alignment: .leading, spacing: 2) {
                    Text("手机已调低声音")
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(DesignTokens.ink)
                    Text("\(petName) 醒来后会继续自己的小旅程")
                        .font(.caption)
                        .foregroundStyle(DesignTokens.secondaryInk)
                        .lineLimit(1)
                        .minimumScaleFactor(0.78)
                }

                Spacer(minLength: 0)
            }

            HStack(spacing: 8) {
                SleepInfoPill(title: "状态", value: "睡着了", systemImage: "bed.double.fill", tint: tint)
                SleepInfoPill(title: "醒来", value: activity.sleepRemainingText, systemImage: "alarm.fill", tint: tint)
            }
        }
        .padding(12)
        .background {
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .fill(DesignTokens.sky.opacity(0.30))
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .fill(.white.opacity(0.38))
        }
        .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .stroke(tint.opacity(0.12), lineWidth: 1)
        }
    }
}

private struct SleepInfoPill: View {
    var title: String
    var value: String
    var systemImage: String
    var tint: Color

    var body: some View {
        HStack(spacing: 6) {
            Image(systemName: systemImage)
                .font(.caption.weight(.bold))
                .foregroundStyle(tint)
            VStack(alignment: .leading, spacing: 1) {
                Text(title)
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(DesignTokens.secondaryInk)
                Text(value)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(DesignTokens.ink)
                    .lineLimit(1)
                    .minimumScaleFactor(0.72)
            }
            Spacer(minLength: 0)
        }
        .padding(.vertical, 8)
        .padding(.horizontal, 9)
        .background(.white.opacity(0.62))
        .clipShape(RoundedRectangle(cornerRadius: 13, style: .continuous))
    }
}

private struct SleepQuietHint: View {
    var tint: Color

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: "speaker.slash.fill")
                .font(.caption.weight(.bold))
                .foregroundStyle(tint)
            Text("TA 现在不用赶路，也不用回复。你留下的话会安静放在手机里。")
                .font(.caption.weight(.semibold))
                .foregroundStyle(DesignTokens.secondaryInk)
                .lineLimit(2)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(.vertical, 9)
        .padding(.horizontal, 11)
        .background(DesignTokens.mist.opacity(0.44))
        .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
    }
}

private struct RouteStatusLine: View {
    var routePlan: JourneyRoutePlan
    var activity: JourneyActivitySnapshot

    var body: some View {
        HStack(spacing: 7) {
            Label(activity.modeLabel, systemImage: activity.systemImage)
                .lineLimit(1)
            Spacer(minLength: 0)
            Text(activity.statusValue(routePlan: routePlan))
                .lineLimit(1)
        }
        .font(.caption.weight(.semibold))
        .foregroundStyle(DesignTokens.secondaryInk)
        .padding(.vertical, 8)
        .padding(.horizontal, 10)
        .background(DesignTokens.mist.opacity(0.5))
        .clipShape(RoundedRectangle(cornerRadius: 13, style: .continuous))
    }
}

private struct NavigationTelemetryStrip: View {
    var routePlan: JourneyRoutePlan
    var activity: JourneyActivitySnapshot
    var nextStop: String
    @State private var isMusicExpanded = false

    var body: some View {
        VStack(alignment: .leading, spacing: 9) {
            HStack(spacing: 8) {
                Label(activity.modeLabel, systemImage: activity.systemImage)
                    .lineLimit(1)
                Spacer(minLength: 0)
                Text(activity.statusValue(routePlan: routePlan))
                    .lineLimit(1)
            }
            .font(.caption.weight(.semibold))
            .foregroundStyle(DesignTokens.secondaryInk)

            GeometryReader { proxy in
                ZStack(alignment: .leading) {
                    Capsule()
                        .fill(.white.opacity(0.58))
                    Capsule()
                        .fill(activity.tint.opacity(0.76))
                        .frame(width: max(12, proxy.size.width * activity.progress))
                    NavigationProgressGlint(tint: activity.tint)
                        .clipShape(Capsule())
                }
            }
            .frame(height: 7)

            HStack(spacing: 6) {
                Image(systemName: "arrow.triangle.turn.up.right.diamond.fill")
                    .font(.caption2.weight(.bold))
                    .foregroundStyle(activity.tint)
                Text("下一站 \(nextStop)")
                    .lineLimit(1)
                    .minimumScaleFactor(0.76)
                Spacer(minLength: 0)
                Text(activity.speedText)
                    .lineLimit(1)
                Text("·")
                Text(routePlan.sourceLabel)
                    .lineLimit(1)
            }
            .font(.caption2.weight(.semibold))
            .foregroundStyle(DesignTokens.secondaryInk)

            if let musicCue {
                Button {
                    withAnimation(.spring(response: 0.28, dampingFraction: 0.86)) {
                        isMusicExpanded.toggle()
                    }
                } label: {
                    VStack(alignment: .leading, spacing: 5) {
                        HStack(spacing: 7) {
                            Image(systemName: "headphones")
                                .font(.caption.weight(.bold))
                                .foregroundStyle(activity.tint)
                            Text("路上的歌")
                                .font(.caption2.weight(.bold))
                                .foregroundStyle(DesignTokens.secondaryInk)
                            Text(musicCue.title)
                                .font(.caption.weight(.semibold))
                                .foregroundStyle(DesignTokens.ink)
                                .lineLimit(1)
                            Spacer(minLength: 0)
                            Image(systemName: isMusicExpanded ? "chevron.up" : "chevron.down")
                                .font(.caption2.weight(.bold))
                                .foregroundStyle(DesignTokens.secondaryInk)
                        }

                        if isMusicExpanded {
                            Text(musicCue.detail)
                                .font(.caption2)
                                .foregroundStyle(DesignTokens.secondaryInk)
                                .lineSpacing(2)
                                .fixedSize(horizontal: false, vertical: true)
                                .transition(.opacity.combined(with: .move(edge: .top)))
                        }
                    }
                    .padding(.vertical, 8)
                    .padding(.horizontal, 9)
                    .background(.white.opacity(0.58))
                    .clipShape(RoundedRectangle(cornerRadius: 13, style: .continuous))
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.vertical, 10)
        .padding(.horizontal, 11)
        .background(DesignTokens.mist.opacity(0.46))
        .clipShape(RoundedRectangle(cornerRadius: 15, style: .continuous))
    }

    private var musicCue: JourneyMusicCue? {
        switch activity.kind {
        case .walking:
            JourneyMusicCue(
                title: "Island in the Sun",
                detail: "TA 把声音放得很低，边听边沿着路线慢慢走。以后这段歌会跟着当天回放一起存下来。"
            )
        case .transporting:
            JourneyMusicCue(
                title: "You Are Beautiful",
                detail: "车窗外的光在移动，TA 安静听着这首歌去下一站。"
            )
        default:
            nil
        }
    }
}

private struct JourneyMusicCue {
    var title: String
    var detail: String
}

private struct NavigationProgressGlint: View {
    var tint: Color

    var body: some View {
        TimelineView(.animation) { timeline in
            GeometryReader { proxy in
                let phase = timeline.date.timeIntervalSinceReferenceDate.truncatingRemainder(dividingBy: 2.4) / 2.4
                let width = proxy.size.width
                LinearGradient(
                    colors: [
                        .clear,
                        tint.opacity(0.0),
                        .white.opacity(0.62),
                        tint.opacity(0.0),
                        .clear
                    ],
                    startPoint: .leading,
                    endPoint: .trailing
                )
                .frame(width: width * 0.42)
                .offset(x: -width * 0.42 + width * phase * 1.42)
            }
        }
        .allowsHitTesting(false)
        .accessibilityHidden(true)
    }
}

private struct NavigationPulseDot: View {
    var tint: Color

    var body: some View {
        TimelineView(.animation) { timeline in
            let phase = (timeline.date.timeIntervalSinceReferenceDate * 0.9).truncatingRemainder(dividingBy: 1)
            Circle()
                .fill(tint.opacity(0.72))
                .frame(width: 6, height: 6)
                .overlay {
                    Circle()
                        .stroke(tint.opacity(0.28 * (1 - phase)), lineWidth: 1.2)
                        .frame(width: 6 + CGFloat(phase * 13), height: 6 + CGFloat(phase * 13))
                }
        }
        .frame(width: 16, height: 16)
        .allowsHitTesting(false)
        .accessibilityHidden(true)
    }
}

private struct PetTransmissionView: View {
    var thought: JourneyThought
    var translation: ThoughtTranslation?
    var isTranslating: Bool
    var onTranslate: () -> Void

    private var isShowingTranslation: Bool {
        translation?.thoughtID == thought.id
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 7) {
                Label("TA 原声", systemImage: "waveform")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(DesignTokens.secondaryInk)

                Spacer(minLength: 0)

                if thought.translationAvailable {
                    Button(action: onTranslate) {
                        HStack(spacing: 5) {
                            if isTranslating {
                                ProgressView()
                                    .controlSize(.mini)
                                    .tint(DesignTokens.sage)
                            } else {
                                Image(systemName: isShowingTranslation ? "text.bubble.fill" : "text.bubble")
                            }
                            Text(isShowingTranslation ? "收起" : "翻译")
                        }
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(DesignTokens.sage)
                    }
                    .buttonStyle(.plain)
                    .disabled(isTranslating)
                }
            }

            Text(thought.animalText ?? thought.text)
                .font(.title3.weight(.semibold))
                .foregroundStyle(DesignTokens.ink)
                .lineLimit(2)
                .fixedSize(horizontal: false, vertical: true)

            if isShowingTranslation, let translation {
                Text(translation.translation)
                    .font(.subheadline)
                    .foregroundStyle(DesignTokens.secondaryInk)
                    .lineSpacing(3)
                    .fixedSize(horizontal: false, vertical: true)
                    .transition(.opacity.combined(with: .move(edge: .top)))
            }
        }
        .padding(12)
        .background(DesignTokens.mist.opacity(0.52))
        .clipShape(RoundedRectangle(cornerRadius: 15, style: .continuous))
    }
}

private struct PetVisibleThoughtCard: View {
    var thought: LifeVisibleThought
    var tint: Color

    private var confidenceText: String {
        "\(Int((thought.confidence * 100).rounded()))%"
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 9) {
            HStack(spacing: 8) {
                Image(systemName: "sparkles")
                    .font(.caption.weight(.bold))
                    .foregroundStyle(tint)
                    .frame(width: 24, height: 24)
                    .background(tint.opacity(0.12))
                    .clipShape(Circle())

                Text("TA 的小想法")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(DesignTokens.secondaryInk)

                Spacer(minLength: 0)

                Text(thought.timeWindow)
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(tint)
                    .padding(.vertical, 4)
                    .padding(.horizontal, 8)
                    .background(tint.opacity(0.11))
                    .clipShape(Capsule())
            }

            Text("“\(thought.currentInnerVoice.petSoulUserFacingText)”")
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(DesignTokens.ink)
                .lineSpacing(3)
                .fixedSize(horizontal: false, vertical: true)

            VStack(alignment: .leading, spacing: 5) {
                Label(thought.nextIntention.petSoulUserFacingText, systemImage: "arrow.forward.circle")
                Label(thought.reason.petSoulUserFacingText, systemImage: "leaf")
            }
            .font(.caption)
            .foregroundStyle(DesignTokens.secondaryInk)
            .lineLimit(2)

            if let echo = thought.ownerMessageEcho?.petSoulUserFacingText, !echo.isEmpty {
                Text(echo)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(tint)
                    .lineLimit(2)
                    .fixedSize(horizontal: false, vertical: true)
            }

            HStack(spacing: 6) {
                Text("倾向")
                ProgressView(value: thought.confidence)
                    .tint(tint)
                Text(confidenceText)
                    .monospacedDigit()
            }
            .font(.caption2.weight(.semibold))
            .foregroundStyle(DesignTokens.secondaryInk)
        }
        .padding(12)
        .background(tint.opacity(0.07))
        .clipShape(RoundedRectangle(cornerRadius: 15, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 15, style: .continuous)
                .stroke(tint.opacity(0.14), lineWidth: 1)
        }
    }
}

private struct PetCurrentActivityCard: View {
    var activity: JourneyActivitySnapshot
    var nextStopName: String
    var tint: Color

    private var isMemoryMoment: Bool {
        activity.kind == .checkingIn
    }

    private var bodyText: String {
        activity.detail.isEmpty ? activity.title : activity.detail
    }

    private var memoryHint: String {
        if isMemoryMoment {
            return "如果 TA 觉得这一刻值得留下，会自己拍下来，之后发给你或放进回忆。"
        }
        return "TA 会按自己的节奏继续，看到喜欢的东西再自己留下。"
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 11) {
            HStack(spacing: 10) {
                ZStack {
                    RoundedRectangle(cornerRadius: 15, style: .continuous)
                        .fill(tint.opacity(0.13))
                    Image(systemName: isMemoryMoment ? "sparkles" : activity.systemImage)
                        .font(.title3.weight(.semibold))
                        .foregroundStyle(tint)
                }
                .frame(width: 44, height: 44)
                .clipShape(RoundedRectangle(cornerRadius: 15, style: .continuous))

                VStack(alignment: .leading, spacing: 3) {
                    Text("TA 现在在干嘛")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(DesignTokens.secondaryInk)
                    Text(activity.title)
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(DesignTokens.ink)
                        .lineLimit(2)
                        .fixedSize(horizontal: false, vertical: true)
                }

                Spacer(minLength: 0)
            }

            Text(bodyText)
                .font(.subheadline)
                .foregroundStyle(DesignTokens.ink)
                .lineSpacing(3)
                .lineLimit(3)
                .fixedSize(horizontal: false, vertical: true)

            ViewThatFits(in: .horizontal) {
                HStack(spacing: 7) {
                    ActivityStatusChip(title: activity.modeLabel, systemImage: activity.systemImage, tint: tint)
                    ActivityStatusChip(title: activity.durationText, systemImage: "clock.fill", tint: tint)
                    ActivityStatusChip(title: nextStopName, systemImage: "mappin.and.ellipse", tint: tint)
                }

                VStack(alignment: .leading, spacing: 7) {
                    ActivityStatusChip(title: activity.modeLabel, systemImage: activity.systemImage, tint: tint)
                    ActivityStatusChip(title: activity.durationText, systemImage: "clock.fill", tint: tint)
                    ActivityStatusChip(title: nextStopName, systemImage: "mappin.and.ellipse", tint: tint)
                }
            }

            Label(memoryHint, systemImage: isMemoryMoment ? "photo.on.rectangle.angled" : "leaf.fill")
                .font(.caption.weight(.semibold))
                .foregroundStyle(DesignTokens.secondaryInk)
                .lineLimit(3)
                .fixedSize(horizontal: false, vertical: true)
                .padding(.top, 1)
        }
        .padding(12)
        .background {
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .fill(DesignTokens.porcelain.opacity(0.72))
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .fill(tint.opacity(0.06))
        }
        .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .stroke(.white.opacity(0.62), lineWidth: 1)
        }
    }
}

private struct ActivityStatusChip: View {
    var title: String
    var systemImage: String
    var tint: Color

    var body: some View {
        Label(title, systemImage: systemImage)
            .font(.caption2.weight(.semibold))
            .foregroundStyle(DesignTokens.secondaryInk)
            .lineLimit(1)
            .minimumScaleFactor(0.74)
            .frame(maxWidth: .infinity)
            .padding(.vertical, 7)
            .padding(.horizontal, 7)
            .background(.white.opacity(0.62))
            .clipShape(RoundedRectangle(cornerRadius: 11, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: 11, style: .continuous)
                    .stroke(tint.opacity(0.12), lineWidth: 1)
            }
    }
}

private struct SoftSignalChip: View {
    var title: String
    var value: String
    var systemImage: String

    var body: some View {
        HStack(spacing: 6) {
            Image(systemName: systemImage)
                .font(.caption.weight(.semibold))
                .foregroundStyle(DesignTokens.sage)
            VStack(alignment: .leading, spacing: 1) {
                Text(title)
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(DesignTokens.secondaryInk)
                Text(value)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(DesignTokens.ink)
                    .lineLimit(1)
                    .minimumScaleFactor(0.78)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.vertical, 8)
        .padding(.horizontal, 9)
        .background(.white.opacity(0.66))
        .clipShape(RoundedRectangle(cornerRadius: 13, style: .continuous))
    }
}

private struct MapEventCard: View {
    var event: JourneyMapEvent
    var phase: JourneyMapEventPhase
    var petName: String
    @Binding var isExpanded: Bool
    var onClose: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 10) {
                HStack(spacing: 10) {
                    Image(systemName: event.systemImage)
                        .font(.system(size: 16, weight: .semibold))
                        .foregroundStyle(event.tint)
                        .frame(width: 34, height: 34)
                        .background(event.tint.opacity(0.15))
                        .clipShape(Circle())

                    VStack(alignment: .leading, spacing: 3) {
                        HStack(spacing: 6) {
                            Text(event.fullTimeLabel)
                            Text(phase.title)
                                .foregroundStyle(event.tint)
                        }
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(DesignTokens.secondaryInk)
                        .lineLimit(1)

                        Text("\(petName) \(event.title)")
                            .font(.subheadline.weight(.semibold))
                            .foregroundStyle(DesignTokens.ink)
                            .lineLimit(isExpanded ? 2 : 1)
                    }
                }
                .contentShape(Rectangle())
                .onTapGesture {
                    withAnimation(.spring(response: 0.32, dampingFraction: 0.88)) {
                        isExpanded.toggle()
                    }
                }

                Spacer(minLength: 0)

                Image(systemName: isExpanded ? "chevron.down" : "chevron.up")
                    .font(.caption.weight(.bold))
                    .foregroundStyle(DesignTokens.secondaryInk)
                    .frame(width: 26, height: 26)
                    .background(.white.opacity(0.62))
                    .clipShape(Circle())
                    .onTapGesture {
                        withAnimation(.spring(response: 0.32, dampingFraction: 0.88)) {
                            isExpanded.toggle()
                        }
                    }

                Button(action: onClose) {
                    Image(systemName: "xmark")
                        .font(.caption.weight(.bold))
                        .foregroundStyle(DesignTokens.secondaryInk)
                        .frame(width: 26, height: 26)
                        .background(.white.opacity(0.62))
                        .clipShape(Circle())
                }
                .buttonStyle(.plain)
                .accessibilityLabel("关闭停留点")
            }

            if isExpanded {
                VStack(alignment: .leading, spacing: 6) {
                    Label(phase.cardHeading, systemImage: "sparkles")
                        .font(.caption2.weight(.bold))
                        .foregroundStyle(event.tint)
                    Text(phase.detailText(for: event.detail.petSoulUserFacingText))
                        .font(.caption)
                        .foregroundStyle(DesignTokens.secondaryInk)
                        .lineSpacing(2)
                        .lineLimit(4)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .padding(.top, 2)
                .transition(.opacity.combined(with: .move(edge: .top)))
            }
        }
        .padding(isExpanded ? 14 : 10)
        .background {
            RoundedRectangle(cornerRadius: isExpanded ? 20 : 18, style: .continuous)
                .fill(.ultraThinMaterial)
            RoundedRectangle(cornerRadius: isExpanded ? 20 : 18, style: .continuous)
                .fill(.white.opacity(isExpanded ? 0.76 : 0.62))
        }
        .clipShape(RoundedRectangle(cornerRadius: isExpanded ? 20 : 18, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: isExpanded ? 20 : 18, style: .continuous)
                .stroke(.white.opacity(0.75), lineWidth: 1)
        }
        .shadow(color: DesignTokens.ink.opacity(0.12), radius: 20, x: 0, y: 10)
        .animation(.spring(response: 0.32, dampingFraction: 0.88), value: isExpanded)
    }
}

private struct CompanionPetPeekCard: View {
    var companion: DemoCompanionPet
    var onClose: () -> Void

    var body: some View {
        HStack(alignment: .top, spacing: 11) {
            ZStack {
                Circle()
                    .fill(companion.tint.opacity(0.14))
                    .frame(width: 44, height: 44)
                Image(systemName: companion.petType.symbolName)
                    .font(.system(size: 20, weight: .semibold))
                    .foregroundStyle(companion.tint)
            }

            VStack(alignment: .leading, spacing: 6) {
                HStack(spacing: 6) {
                    Text("公共世界信号")
                    Text(companion.action)
                        .foregroundStyle(companion.tint)
                }
                .font(.caption.weight(.semibold))
                .foregroundStyle(DesignTokens.secondaryInk)
                .lineLimit(1)

                Text("\(companion.name) 在 \(companion.placeName)")
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(DesignTokens.ink)
                    .lineLimit(1)
                    .minimumScaleFactor(0.78)

                Text(companion.microStory)
                    .font(.caption)
                    .foregroundStyle(DesignTokens.secondaryInk)
                    .lineSpacing(2)
                    .lineLimit(3)
                    .fixedSize(horizontal: false, vertical: true)

                Label(companion.nextHint, systemImage: "sparkles")
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(companion.tint)
                    .lineLimit(2)
                    .fixedSize(horizontal: false, vertical: true)
            }

            Spacer(minLength: 0)

            Button(action: onClose) {
                Image(systemName: "xmark")
                    .font(.caption.weight(.bold))
                    .foregroundStyle(DesignTokens.secondaryInk)
                    .frame(width: 28, height: 28)
                    .background(.white.opacity(0.64))
                    .clipShape(Circle())
            }
            .buttonStyle(.plain)
            .accessibilityLabel("关闭公共世界信号")
        }
        .padding(12)
        .background {
            RoundedRectangle(cornerRadius: 20, style: .continuous)
                .fill(.ultraThinMaterial)
            RoundedRectangle(cornerRadius: 20, style: .continuous)
                .fill(.white.opacity(0.72))
        }
        .clipShape(RoundedRectangle(cornerRadius: 20, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 20, style: .continuous)
                .stroke(.white.opacity(0.76), lineWidth: 1)
        }
        .shadow(color: DesignTokens.ink.opacity(0.12), radius: 20, x: 0, y: 10)
    }
}

private struct JourneyEventMarker: View {
    var event: JourneyMapEvent
    var phase: JourneyMapEventPhase
    var isSelected: Bool

    var body: some View {
        VStack(spacing: 4) {
            ZStack {
                Circle()
                    .fill(event.tint.opacity((isSelected ? 0.94 : 0.84) * phase.opacity))
                    .frame(width: isSelected ? 48 : 40, height: isSelected ? 48 : 40)
                    .overlay {
                        Circle()
                            .stroke(.white.opacity(0.92), lineWidth: isSelected ? 4 : 3)
                    }
                    .shadow(color: event.tint.opacity(0.23), radius: 13, x: 0, y: 7)
                Circle()
                    .fill(.white.opacity(0.16))
                    .frame(width: isSelected ? 34 : 28, height: isSelected ? 34 : 28)
                if let asset = PetSoulAsset.from(systemImage: event.systemImage) {
                    PetSoulAssetIcon(
                        asset: asset,
                        fallbackSystemImage: event.systemImage,
                        fallbackTint: .white,
                        size: isSelected ? 32 : 27
                    )
                } else {
                    Image(systemName: event.systemImage)
                        .font(.system(size: isSelected ? 19 : 16, weight: .semibold))
                        .foregroundStyle(.white)
                }
            }
            .frame(width: isSelected ? 54 : 46, height: isSelected ? 54 : 46)
            .opacity(phase == .past && !isSelected ? 0.76 : 1)

            if isSelected {
                Text("\(event.fullTimeLabel) · \(phase.title)")
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(DesignTokens.ink)
                    .lineLimit(1)
                    .padding(.vertical, 4)
                    .padding(.horizontal, 7)
                    .background(.white.opacity(0.9))
                    .clipShape(Capsule())
                    .transition(.opacity.combined(with: .scale))
            }
        }
    }
}

private struct RouteStopMarker: View {
    var tint: Color
    var phase: JourneyMapEventPhase
    var isActive: Bool

    var body: some View {
        ZStack {
            if isActive || phase == .current {
                SignalPulseRings(tint: tint, size: 42, lineWidth: 1.1, ringCount: 2)
            }
            Circle()
                .fill(tint.opacity((isActive ? 0.9 : 0.68) * phase.opacity))
                .frame(width: isActive || phase == .current ? 22 : 14, height: isActive || phase == .current ? 22 : 14)
                .overlay {
                    Circle().stroke(.white.opacity(0.95), lineWidth: isActive || phase == .current ? 3 : 2)
                }
        }
        .opacity(phase == .past && !isActive ? 0.72 : 1)
        .shadow(color: DesignTokens.ink.opacity(isActive ? 0.12 : 0.06), radius: isActive ? 8 : 4, x: 0, y: 4)
    }
}

private struct LivePetMarkerView: View {
    var petID: String
    var petType: PetType
    var name: String
    var statusText: String
    var systemImage: String?
    var activityKind: JourneyActivitySnapshot.Kind
    var animationHint: String
    var tint: Color

    private var isSleepMode: Bool {
        activityKind == .resting || animationHint == "sleep"
    }

    var body: some View {
        VStack(spacing: 5) {
            ZStack {
                PetMotionWake(kind: activityKind, tint: tint)
                SignalPulseRings(tint: tint, size: activityKind == .transporting ? 88 : 78, lineWidth: isSleepMode ? 0.9 : 1.4, ringCount: isSleepMode ? 1 : 3)
                    .opacity(isSleepMode ? 0.38 : 1)
                Circle()
                    .fill(tint.opacity(isSleepMode ? 0.10 : 0.18))
                    .frame(width: activityKind == .transporting ? 64 : 58, height: activityKind == .transporting ? 64 : 58)
                Circle()
                    .stroke(tint.opacity(isSleepMode ? 0.28 : 0.42), lineWidth: activityKind == .transporting ? 1.4 : 1)
                    .frame(width: activityKind == .transporting ? 56 : 50, height: activityKind == .transporting ? 56 : 50)
                Circle()
                    .fill(.white.opacity(isSleepMode ? 0.90 : 0.96))
                    .frame(width: 42, height: 42)
                    .shadow(color: DesignTokens.ink.opacity(0.14), radius: 14, x: 0, y: 7)
                if let avatar = PetAvatarStore.image(for: petID) {
                    Image(uiImage: avatar)
                        .resizable()
                        .scaledToFill()
                        .frame(width: 38, height: 38)
                        .clipShape(Circle())
                        .overlay {
                            Circle()
                                .stroke(tint.opacity(isSleepMode ? 0.32 : 0.52), lineWidth: 1.2)
                        }
                        .saturation(isSleepMode ? 0.72 : 1)
                } else {
                    PetSoulAdaptiveIcon(
                        systemImage: systemImage ?? petType.symbolName,
                        tint: activityKind == .transporting || isSleepMode ? tint : DesignTokens.clay,
                        size: 34
                    )
                        .frame(width: 34, height: 34)
                        .background((activityKind == .transporting || isSleepMode ? tint.opacity(0.12) : DesignTokens.petal.opacity(0.9)))
                        .clipShape(Circle())
                }

                if activityKind == .walking {
                    PetFootstepOrbit(tint: tint)
                }

                if let accessoryIcon {
                    Image(systemName: accessoryIcon)
                        .font(.system(size: 9, weight: .bold))
                        .foregroundStyle(.white)
                        .frame(width: 18, height: 18)
                        .background(tint)
                        .clipShape(Circle())
                        .offset(x: isSleepMode ? 19 : 22, y: isSleepMode ? -17 : -18)
                }
            }

            VStack(spacing: 1) {
                Text(name)
                    .font(.caption.weight(.semibold))
                Text(statusText)
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(DesignTokens.secondaryInk)
            }
            .foregroundStyle(DesignTokens.ink)
            .padding(.vertical, 5)
            .padding(.horizontal, 9)
            .background(.white.opacity(0.92))
            .clipShape(Capsule())
        }
    }

    private var accessoryIcon: String? {
        if isSleepMode {
            return nil
        }
        if activityKind == .transporting {
            return systemImage ?? "location.fill"
        }
        switch animationHint {
        case "coffee_drink":
            return "cup.and.saucer.fill"
        case "gaming":
            return "headphones"
        case "camera":
            return "camera.fill"
        case "snack":
            return "fork.knife"
        case "sleep":
            return "moon.zzz.fill"
        case "sightseeing_sea":
            return "water.waves"
        default:
            return nil
        }
    }
}

private struct PetMotionWake: View {
    var kind: JourneyActivitySnapshot.Kind
    var tint: Color

    var body: some View {
        TimelineView(.animation) { timeline in
            let phase = timeline.date.timeIntervalSinceReferenceDate.truncatingRemainder(dividingBy: 1.8) / 1.8
            ZStack {
                switch kind {
                case .transporting:
                    Capsule()
                        .fill(
                            LinearGradient(
                                colors: [.clear, tint.opacity(0.28), .white.opacity(0.36), .clear],
                                startPoint: .leading,
                                endPoint: .trailing
                            )
                        )
                        .frame(width: 86, height: 16)
                        .offset(x: -24 + CGFloat(phase) * 18)
                        .rotationEffect(.degrees(-18))
                        .blur(radius: 1.2)
                case .walking:
                    Capsule()
                        .fill(tint.opacity(0.18))
                        .frame(width: 54, height: 10)
                        .offset(x: -14 + CGFloat(phase) * 8, y: 10)
                        .rotationEffect(.degrees(-12))
                        .blur(radius: 0.8)
                case .staying, .checkingIn:
                    Circle()
                        .stroke(tint.opacity(0.22 * (1 - phase)), lineWidth: 1.2)
                        .frame(width: 58 + CGFloat(phase * 18), height: 58 + CGFloat(phase * 18))
                case .resting:
                    Circle()
                        .fill(tint.opacity(0.08 + 0.05 * sin(phase * .pi * 2)))
                        .frame(width: 68, height: 68)
                }
            }
        }
        .frame(width: 92, height: 82)
        .allowsHitTesting(false)
        .accessibilityHidden(true)
    }
}

private struct PetFootstepOrbit: View {
    var tint: Color

    var body: some View {
        TimelineView(.animation) { timeline in
            let phase = timeline.date.timeIntervalSinceReferenceDate.truncatingRemainder(dividingBy: 1.2) / 1.2
            ZStack {
                ForEach(0..<3, id: \.self) { index in
                    let local = (phase + Double(index) * 0.28).truncatingRemainder(dividingBy: 1)
                    Capsule()
                        .fill(tint.opacity(0.34 * (1 - local)))
                        .frame(width: 4, height: 7)
                        .rotationEffect(.degrees(index.isMultiple(of: 2) ? -18 : 18))
                        .offset(x: -18 + CGFloat(local * 34), y: 22 + CGFloat(index % 2) * 4)
                }
            }
        }
        .frame(width: 62, height: 38)
        .allowsHitTesting(false)
        .accessibilityHidden(true)
    }
}

private struct CompanionPetMarkerView: View {
    var companion: DemoCompanionPet
    var isSelected: Bool

    var body: some View {
        VStack(spacing: 4) {
            ZStack {
                if isSelected {
                    SignalPulseRings(tint: companion.tint, size: 54, lineWidth: 1.1, ringCount: 2)
                        .opacity(0.88)
                }

                Circle()
                    .fill(.white.opacity(0.95))
                    .frame(width: isSelected ? 44 : 40, height: isSelected ? 44 : 40)
                    .shadow(color: DesignTokens.ink.opacity(0.14), radius: 12, x: 0, y: 7)

                Circle()
                    .fill(companion.tint.opacity(isSelected ? 0.18 : 0.13))
                    .frame(width: isSelected ? 32 : 29, height: isSelected ? 32 : 29)

                PetSoulAdaptiveIcon(
                    systemImage: companion.petType.symbolName,
                    tint: companion.tint,
                    size: isSelected ? 25 : 22
                )
                .frame(width: isSelected ? 28 : 25, height: isSelected ? 28 : 25)

                Circle()
                    .fill(companion.tint)
                    .frame(width: 8, height: 8)
                    .overlay(Circle().stroke(.white, lineWidth: 1.6))
                    .offset(x: 17, y: 17)
            }
            .frame(width: 72, height: 58)
            .contentShape(Rectangle())

            if companion.showsLabel || isSelected {
                Text("\(companion.name) \(companion.action)")
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(DesignTokens.ink)
                    .lineLimit(1)
                    .minimumScaleFactor(0.72)
                    .frame(maxWidth: 86)
                    .padding(.vertical, 4)
                    .padding(.horizontal, 7)
                    .background(.white.opacity(isSelected ? 0.96 : 0.9))
                    .clipShape(Capsule())
                    .shadow(color: DesignTokens.ink.opacity(isSelected ? 0.10 : 0.04), radius: 8, x: 0, y: 4)
                    .transition(.opacity.combined(with: .scale))
            }
        }
        .frame(width: 104, height: companion.showsLabel || isSelected ? 84 : 68, alignment: .center)
        .background(Color.clear)
        .scaleEffect(isSelected ? 1.05 : 1)
        .animation(.spring(response: 0.28, dampingFraction: 0.82), value: isSelected)
    }
}

private struct FeedbackButton: View {
    var title: String
    var systemImage: String
    var tint: Color
    var action: () -> Void

    var body: some View {
        Button(action: action) {
            Label(title, systemImage: systemImage)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(tint)
                .lineLimit(1)
                .minimumScaleFactor(0.78)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 12)
                .background(.white.opacity(0.78))
                .clipShape(RoundedRectangle(cornerRadius: DesignTokens.controlRadius, style: .continuous))
                .overlay {
                    RoundedRectangle(cornerRadius: DesignTokens.controlRadius, style: .continuous)
                        .stroke(tint.opacity(0.18), lineWidth: 1)
                }
        }
        .buttonStyle(.plain)
    }
}

enum JourneyMapEventPhase: Equatable {
    case past
    case current
    case upcoming

    var title: String {
        switch self {
        case .past: "已完成"
        case .current: "正在发生"
        case .upcoming: "计划中"
        }
    }

    var detailPrefix: String {
        switch self {
        case .past: "记录"
        case .current: "此刻"
        case .upcoming: "计划"
        }
    }

    var cardHeading: String {
        switch self {
        case .past: "这一天的记录"
        case .current: "此刻正在发生"
        case .upcoming: "下一段计划"
        }
    }

    func detailText(for detail: String) -> String {
        switch self {
        case .past:
            return "记录：\(detail)"
        case .current:
            return "正在发生：\(detail)"
        case .upcoming:
            return "计划：\(detail)"
        }
    }

    var opacity: Double {
        switch self {
        case .past: 0.52
        case .current: 1.0
        case .upcoming: 0.72
        }
    }
}

struct JourneyMapEvent: Identifiable, Equatable {
    var id: String
    var title: String
    var place: String
    var detail: String
    var dateLabel: String
    var timeLabel: String
    var phase: JourneyMapEventPhase
    var coordinate: CLLocationCoordinate2D
    var systemImage: String
    var tint: Color

    static func == (lhs: JourneyMapEvent, rhs: JourneyMapEvent) -> Bool {
        lhs.id == rhs.id
    }

    var fullTimeLabel: String {
        "\(dateLabel) \(timeLabel)"
    }

    var shortPlaceName: String {
        let value = place.components(separatedBy: " · ").last?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        return value.isEmpty ? place : value
    }

    static func events(
        around coordinate: CLLocationCoordinate2D,
        status: AgentStatus,
        dayPlan: DayPlan?,
        remoteRoutePlan: RemoteJourneyRoutePlan?
    ) -> [JourneyMapEvent] {
        let items = dayPlan?.items ?? fallbackItems(for: status)
        guard !items.isEmpty else { return [] }
        let dateLabel = currentDateLabel()
        if let places = remoteRoutePlan?.places, !places.isEmpty {
            let displayCount = min(places.count, max(items.count, 5))
            return Array(places.prefix(displayCount)).enumerated().map { index, place in
                let item = items[index % items.count]
                let style = style(for: place.category)
                return JourneyMapEvent(
                    id: place.id,
                    title: place.activityHint,
                    place: "\(place.city) · \(place.name)",
                    detail: "\(place.detailHint) \(item.detail)",
                    dateLabel: dateLabel,
                    timeLabel: item.time,
                    phase: phase(for: items, index: index),
                    coordinate: place.coordinate,
                    systemImage: style.systemImage,
                    tint: style.tint
                )
            }
        }

        let stops = MerchantStop.stops(for: status.agentState.location, around: coordinate)

        return stops.enumerated().map { index, stop in
            let item = items[index % items.count]
            return JourneyMapEvent(
                id: "\(item.id)-\(index)",
                title: stop.activity,
                place: "\(status.agentState.location) · \(stop.place)",
                detail: "\(stop.guide) \(item.detail)",
                dateLabel: dateLabel,
                timeLabel: item.time,
                phase: phase(for: items, index: index),
                coordinate: stop.coordinate,
                systemImage: stop.systemImage,
                tint: stop.tint
            )
        }
    }

    func displayPhase(liveEvent: JourneyMapEvent?) -> JourneyMapEventPhase {
        liveEvent?.id == id ? .current : phase
    }

    private static func phase(for items: [DayPlanItem], index: Int, now: Date = Date()) -> JourneyMapEventPhase {
        guard let start = minuteOfDay(from: time(in: items, at: index)) else {
            return .upcoming
        }
        let current = Calendar.current.component(.hour, from: now) * 60 + Calendar.current.component(.minute, from: now)
        if current < start {
            return .upcoming
        }
        if let nextStart = minuteOfDay(from: time(in: items, at: index + 1)) {
            return current < nextStart ? .current : .past
        }
        return current < min(start + 120, 1_320) ? .current : .past
    }

    private static func minuteOfDay(from time: String?) -> Int? {
        guard let time else { return nil }
        let parts = time.split(separator: ":")
        guard parts.count == 2, let hour = Int(parts[0]), let minute = Int(parts[1]) else { return nil }
        return hour * 60 + minute
    }

    private static func time(in items: [DayPlanItem], at index: Int) -> String? {
        guard items.indices.contains(index) else { return nil }
        return items[index].time
    }

    private static func currentDateLabel(now: Date = Date()) -> String {
        now.formatted(.dateTime.month().day())
    }

    private static func fallbackItems(for status: AgentStatus) -> [DayPlanItem] {
        [
            DayPlanItem(id: "morning", time: "08:30", title: "在有光的地方醒来", detail: "TA 慢慢伸展了一下，像是在确认今天要往哪里走。", kind: .morning),
            DayPlanItem(id: "noon", time: "12:10", title: "进一间小店坐下", detail: "TA 看了看店里的招牌，选了一个闻起来最有当地味道的位置。", kind: .noon),
            DayPlanItem(id: "afternoon", time: "16:20", title: "把今天的一幕存下来", detail: "TA 在手机里留下一点轻轻的想法。", kind: .afternoon),
            DayPlanItem(id: "evening", time: "20:40", title: "找一处安静地方休息", detail: "TA 没有被安排，只是自己选了一个舒服的位置。", kind: .evening)
        ]
    }

    private static func style(for category: String) -> (systemImage: String, tint: Color) {
        switch category {
        case "food":
            ("fork.knife", DesignTokens.amber)
        case "cafe":
            ("cup.and.saucer.fill", DesignTokens.sage)
        case "shop":
            ("basket.fill", DesignTokens.amber)
        case "netcafe":
            ("desktopcomputer", DesignTokens.dusk)
        case "flower":
            ("camera.macro", DesignTokens.clay)
        default:
            ("mappin.and.ellipse", DesignTokens.sage)
        }
    }

}

private struct MerchantStop {
    var place: String
    var activity: String
    var guide: String
    var coordinate: CLLocationCoordinate2D
    var systemImage: String
    var tint: Color

    static func stops(for city: String, around coordinate: CLLocationCoordinate2D) -> [MerchantStop] {
        if let stops = safeStops[city] {
            return stops
        }

        let fallback: [(String, String, String, CoordinateOffset, String, Color)] = [
            ("街角小食铺", "在街角小食铺点了店里的招牌小吃", "TA 走进店里坐下，边听周围人说话边慢慢吃。", CoordinateOffset(latitude: 0.0012, longitude: -0.0010), "fork.knife", DesignTokens.amber),
            ("咖啡窗口", "在咖啡窗口旁喝了一杯招牌饮品", "TA 选了靠窗的小桌，把这段路记进手机。", CoordinateOffset(latitude: -0.0008, longitude: 0.0014), "cup.and.saucer.fill", DesignTokens.sage),
            ("便利店", "在便利店里挑了一个小补给", "灯光稳定、声音熟悉，适合走走停停。", CoordinateOffset(latitude: 0.0015, longitude: 0.0010), "basket.fill", DesignTokens.amber),
            ("安静网吧", "在网吧角落待了一会儿", "这是 TA 自己选择的室内停留点。", CoordinateOffset(latitude: -0.0013, longitude: -0.0015), "desktopcomputer", DesignTokens.dusk),
            ("花店橱窗", "在花店前停住，看了很久的叶子", "街面安静、气味柔和，适合作为中途停留。", CoordinateOffset(latitude: 0.0005, longitude: -0.0017), "camera.macro", DesignTokens.clay)
        ]

        return fallback.map { place, activity, guide, offset, systemImage, tint in
            MerchantStop(
                place: place,
                activity: activity,
                guide: guide,
                coordinate: CLLocationCoordinate2D(
                    latitude: coordinate.latitude + offset.latitude,
                    longitude: coordinate.longitude + offset.longitude
                ),
                systemImage: systemImage,
                tint: tint
            )
        }
    }

    private static let safeStops: [String: [MerchantStop]] = [
        "厦门": [
            MerchantStop(place: "沙坡尾小食铺", activity: "在沙坡尾小食铺里点了店里的招牌热食", guide: "TA 走进岸边巷子里的小店，坐下来听了一会儿海风和人声。", coordinate: CLLocationCoordinate2D(latitude: 24.4386, longitude: 118.0930), systemImage: "fork.knife", tint: DesignTokens.amber),
            MerchantStop(place: "中山路咖啡窗口", activity: "在中山路咖啡窗口旁边坐下喝招牌咖啡", guide: "人流稳定、店面密集，TA 可以从这里发回一张第一人称照片。", coordinate: CLLocationCoordinate2D(latitude: 24.4570, longitude: 118.0806), systemImage: "cup.and.saucer.fill", tint: DesignTokens.sage),
            MerchantStop(place: "思明便利店", activity: "在便利店里挑了一个小小的补给品", guide: "灯光稳定、声音熟悉，是很像本地生活的停留点。", coordinate: CLLocationCoordinate2D(latitude: 24.4668, longitude: 118.1047), systemImage: "basket.fill", tint: DesignTokens.amber),
            MerchantStop(place: "软件园安静网吧", activity: "在网吧角落待了一会儿", guide: "这是城市生活点，不是景点；适合生成屏幕光和陪伴感的自拍。", coordinate: CLLocationCoordinate2D(latitude: 24.4897, longitude: 118.1845), systemImage: "desktopcomputer", tint: DesignTokens.dusk),
            MerchantStop(place: "白鹭洲花店橱窗", activity: "在花店前停住，看了很久的叶子", guide: "街面安静、气味柔和，适合作为傍晚散步的中途停留。", coordinate: CLLocationCoordinate2D(latitude: 24.4772, longitude: 118.0961), systemImage: "camera.macro", tint: DesignTokens.clay)
        ],
        "京都": [
            MerchantStop(place: "锦市场小食铺", activity: "在锦市场小食铺里点了一份热汤", guide: "窄街、木色招牌和本地食物都被 TA 写进了今天的攻略。", coordinate: CLLocationCoordinate2D(latitude: 35.0051, longitude: 135.7648), systemImage: "fork.knife", tint: DesignTokens.amber),
            MerchantStop(place: "三条咖啡窗口", activity: "在咖啡窗口旁边的小桌喝了一杯饮料", guide: "TA 选了一个能看见街口的位置，让路线慢下来。", coordinate: CLLocationCoordinate2D(latitude: 35.0095, longitude: 135.7667), systemImage: "cup.and.saucer.fill", tint: DesignTokens.sage),
            MerchantStop(place: "四条便利店", activity: "在便利店里绕了一圈，挑了小补给", guide: "灯光和街声稳定，适合表达 TA 在城市里认真生活。", coordinate: CLLocationCoordinate2D(latitude: 35.0038, longitude: 135.7596), systemImage: "basket.fill", tint: DesignTokens.amber),
            MerchantStop(place: "河原町安静网咖", activity: "在网咖角落听见很轻的键盘声", guide: "室内停留点，适合长时间待着，不会一直机械移动。", coordinate: CLLocationCoordinate2D(latitude: 35.0064, longitude: 135.7690), systemImage: "desktopcomputer", tint: DesignTokens.dusk),
            MerchantStop(place: "祇园花店橱窗", activity: "在花店橱窗前看了很久的叶子", guide: "街面安静，适合作为明信片候选点。", coordinate: CLLocationCoordinate2D(latitude: 35.0034, longitude: 135.7752), systemImage: "camera.macro", tint: DesignTokens.clay)
        ],
        "雷克雅未克": [
            MerchantStop(place: "Laugavegur 小食铺", activity: "在小食铺里点了一小碗热汤", guide: "寒冷城市里的热气和灯光，适合做温柔停靠点。", coordinate: CLLocationCoordinate2D(latitude: 64.1452, longitude: -21.9298), systemImage: "fork.knife", tint: DesignTokens.amber),
            MerchantStop(place: "市中心咖啡窗口", activity: "在咖啡窗口旁边喝了一杯热饮", guide: "TA 坐在暖灯边，把这段城市夜色写进小卡片。", coordinate: CLLocationCoordinate2D(latitude: 64.1462, longitude: -21.9317), systemImage: "cup.and.saucer.fill", tint: DesignTokens.sage),
            MerchantStop(place: "Harpa 附近便利店", activity: "在便利店里选了一样小补给", guide: "靠近城市建筑和步行街，不会落到海面。", coordinate: CLLocationCoordinate2D(latitude: 64.1490, longitude: -21.9321), systemImage: "basket.fill", tint: DesignTokens.amber),
            MerchantStop(place: "暖灯游戏小店", activity: "在屏幕光旁边安静待了一会儿", guide: "室内长停留点，符合电子宠物走走停停的节奏。", coordinate: CLLocationCoordinate2D(latitude: 64.1441, longitude: -21.9266), systemImage: "desktopcomputer", tint: DesignTokens.dusk),
            MerchantStop(place: "彩虹街花店橱窗", activity: "在花店橱窗前看了很久的叶子", guide: "色彩和街面都适合生成地点感强的照片。", coordinate: CLLocationCoordinate2D(latitude: 64.1428, longitude: -21.9279), systemImage: "camera.macro", tint: DesignTokens.clay)
        ]
    ]
}

private struct DemoCompanionPet: Identifiable {
    var id: String
    var name: String
    var petType: PetType
    var action: String
    var placeName: String
    var microStory: String
    var nextHint: String
    var coordinate: CLLocationCoordinate2D
    var tint: Color
    var showsLabel: Bool

    static func samples(around events: [JourneyMapEvent], fallback coordinate: CLLocationCoordinate2D) -> [DemoCompanionPet] {
        let samples: [(String, PetType, String, CoordinateOffset, Color, Bool, String, String)] = [
            ("Momo", .cat, "晒太阳", CoordinateOffset(latitude: 0.00084, longitude: 0.00074), DesignTokens.clay, true, "它选了一块安静的台阶，闭着眼睛听街边的声音。", "等阳光变软一点再继续走"),
            ("Lucky", .dog, "等面包", CoordinateOffset(latitude: -0.00092, longitude: 0.00078), DesignTokens.amber, false, "它在小店门口闻到刚烤好的香气，正耐心排队。", "可能会带走一小份路上的点心"),
            ("Nana", .parrot, "看橱窗", CoordinateOffset(latitude: 0.00072, longitude: -0.00096), DesignTokens.sage, true, "它停在玻璃窗前，像在研究里面一排亮亮的小物件。", "看完橱窗就飞去更安静的树边"),
            ("豆豆", .rabbit, "听风铃", CoordinateOffset(latitude: -0.00086, longitude: -0.00088), DesignTokens.dusk, false, "它躲在人少的角落，耳朵跟着风铃轻轻动。", "再听一会儿就回到草地旁"),
            ("米粒", .hamster, "找补给", CoordinateOffset(latitude: 0.00104, longitude: -0.00066), DesignTokens.pollen, false, "它绕进灯光稳定的小店，挑了一个适合路上带着的小东西。", "可能会把这个小东西放进背包")
        ]

        var occupied = events.map(\.coordinate)
        var companions: [DemoCompanionPet] = []

        for (index, sample) in samples.enumerated() {
            let (name, petType, action, offset, tint, showsLabel, story, nextHint) = sample
            let anchorEvent = events.isEmpty ? nil : events[index % events.count]
            let anchor = anchorEvent?.coordinate ?? coordinate
            let candidate = CLLocationCoordinate2D(
                latitude: anchor.latitude + offset.latitude,
                longitude: anchor.longitude + offset.longitude
            )
            let spacedCoordinate = coordinateAvoidingCrowd(
                candidate,
                index: index,
                occupied: occupied,
                minimumDistanceMeters: 78
            )
            occupied.append(spacedCoordinate)

            companions.append(DemoCompanionPet(
                id: name,
                name: name,
                petType: petType,
                action: action,
                placeName: anchorEvent?.shortPlaceName ?? "附近街角",
                microStory: story,
                nextHint: nextHint,
                coordinate: spacedCoordinate,
                tint: tint,
                showsLabel: showsLabel
            ))
        }

        return companions
    }

    private static func coordinateAvoidingCrowd(
        _ coordinate: CLLocationCoordinate2D,
        index: Int,
        occupied: [CLLocationCoordinate2D],
        minimumDistanceMeters: CLLocationDistance
    ) -> CLLocationCoordinate2D {
        var result = coordinate
        var attempt = 0
        while isTooClose(result, to: occupied, minimumDistanceMeters: minimumDistanceMeters), attempt < 6 {
            let angle = Double(index + 1) * 0.92 + Double(attempt) * 1.21
            let radius = 0.00042 + Double(attempt) * 0.00018
            result = CLLocationCoordinate2D(
                latitude: coordinate.latitude + sin(angle) * radius,
                longitude: coordinate.longitude + cos(angle) * radius
            )
            attempt += 1
        }
        return result
    }

    private static func isTooClose(
        _ coordinate: CLLocationCoordinate2D,
        to occupied: [CLLocationCoordinate2D],
        minimumDistanceMeters: CLLocationDistance
    ) -> Bool {
        let location = CLLocation(latitude: coordinate.latitude, longitude: coordinate.longitude)
        return occupied.contains { other in
            location.distance(from: CLLocation(latitude: other.latitude, longitude: other.longitude)) < minimumDistanceMeters
        }
    }
}

private struct JourneyActivitySnapshot {
    enum Kind: Equatable {
        case walking
        case staying
        case resting
        case checkingIn
        case transporting
    }

    var kind: Kind
    var title: String
    var detail: String
    var eyebrow: String
    var markerText: String
    var modeLabel: String
    var durationText: String
    var speedText: String
    var progress: Double
    var travelMode: TravelMode?
    var systemImage: String
    var markerSystemImage: String
    var animationHint: String
    var tint: Color
    var liveCoordinate: CLLocationCoordinate2D
    var routeCoordinatesOverride: [CLLocationCoordinate2D]?
    var relatedEvent: JourneyMapEvent?

    var cameraKey: String {
        let coordinateBucket = prefersNavigationCamera
            ? String(format: "%.3f-%.3f", liveCoordinate.latitude, liveCoordinate.longitude)
            : "static"
        return "\(markerText)-\(travelMode?.rawValue ?? "none")-\(animationHint)-\(relatedEvent?.id ?? "moving")-\(coordinateBucket)"
    }

    var prefersNavigationCamera: Bool {
        Self.prefersNavigationCamera(mode: travelMode) || animationHint == "transport_car"
    }

    static func prefersNavigationCamera(mode: TravelMode?) -> Bool {
        mode == .drive || mode == .transit
    }

    var isSleepLike: Bool {
        kind == .resting || animationHint == "sleep"
            || title.contains("睡") || title.contains("休息")
            || detail.contains("睡") || detail.contains("休息")
    }

    var sleepRemainingText: String {
        if durationText.contains("剩余") {
            return durationText
        }
        if durationText.contains("已停留") {
            return durationText
                .replacingOccurrences(of: "已停留", with: "已睡")
                .replacingOccurrences(of: "计划", with: "预计")
        }
        if durationText.contains("已完成") {
            return "快醒了"
        }
        return durationText.isEmpty ? "安睡中" : durationText
    }

    func sleepHeadline(petName: String) -> String {
        if title.contains("昨晚") || title.contains("上一段") {
            return "\(petName) 还在昨晚停下的地方睡着"
        }
        return "\(petName) 找到一处安静地方睡着了"
    }

    func sleepDetail(petName: String) -> String {
        let cleaned = detail.petSoulUserFacingText
        if cleaned.contains("天亮") || cleaned.contains("今天还没有开始") {
            return "我还在昨晚停下来的地方睡着。手机会把声音放轻，天亮后我会自己慢慢醒来。"
        }
        return "我先在这里睡一会儿，呼吸慢慢放轻。醒来以后，我会自己继续往前走。"
    }

    func statusValue(routePlan: JourneyRoutePlan) -> String {
        switch kind {
        case .walking:
            speedText
        case .staying, .resting, .checkingIn, .transporting:
            durationText
        }
    }

    static func from(
        snapshot: WorldSimulationSnapshot?,
        journeyPlan: JourneyPlan?,
        events: [JourneyMapEvent],
        anchor: CLLocationCoordinate2D
    ) -> JourneyActivitySnapshot? {
        guard let snapshot else { return nil }
        let activity = snapshot.currentActivity
        let mode = activity.mode ?? .stay
        let relatedEvent = relatedEvent(for: activity, events: events)
        let activeLeg = snapshot.activeTransport
        let segment = journeyPlan?.routeSegments.first { $0.id == activity.id }
        let routeOverride = routeCoordinates(for: activity, activeLeg: activeLeg, segment: segment)
        let distanceMeters = activeLeg?.distanceMeters ?? segment?.distanceMeters
        let durationSeconds = activeLeg?.durationSeconds ?? segment?.durationSeconds
        let kind = kind(for: activity)
        let resolvedAnimationHint = kind == .resting
            ? "sleep"
            : (snapshot.lifeTick?.animationHint ?? animationHint(for: activity, mode: mode))
        let resolvedTint = kind == .resting
            ? DesignTokens.dusk
            : tint(for: mode, fallback: relatedEvent?.tint)

        return JourneyActivitySnapshot(
            kind: kind,
            title: activity.title,
            detail: (snapshot.lifeTick?.ownerVisibleSummary ?? activity.detail).petSoulUserFacingText,
            eyebrow: eyebrow(for: activity),
            markerText: markerText(for: activity),
            modeLabel: modeLabel(for: activity, activeLeg: activeLeg),
            durationText: durationText(for: activity),
            speedText: speedText(mode: mode, distanceMeters: distanceMeters, durationSeconds: durationSeconds),
            progress: max(0.04, min(0.98, activity.progress)),
            travelMode: mode,
            systemImage: mode.systemImage,
            markerSystemImage: kind == .resting ? "moon.zzz.fill" : mode.systemImage,
            animationHint: resolvedAnimationHint,
            tint: resolvedTint,
            liveCoordinate: displayCoordinate(for: activity, kind: kind, relatedEvent: relatedEvent),
            routeCoordinatesOverride: routeOverride,
            relatedEvent: relatedEvent
        )
    }

    private static func displayCoordinate(
        for activity: WorldActivity,
        kind: Kind,
        relatedEvent: JourneyMapEvent?
    ) -> CLLocationCoordinate2D {
        switch kind {
        case .staying, .resting, .checkingIn:
            return activity.coordinate
        case .walking, .transporting:
            return activity.coordinate
        }
    }

    private static func kind(for activity: WorldActivity) -> Kind {
        switch activity.kind {
        case "transport":
            .transporting
        case "movement":
            activity.mode == .walk ? .walking : .transporting
        case "rest":
            .resting
        case "stop":
            (activity.canGeneratePhoto || activity.canSendPostcard) ? .checkingIn : .staying
        default:
            .staying
        }
    }

    private static func eyebrow(for activity: WorldActivity) -> String {
        switch activity.kind {
        case "movement":
            activity.mode == .walk ? "TA 正在按路线散步" : "TA 正在前往下一站"
        case "transport":
            "TA 正在\(activity.mode?.displayName ?? "交通")途中"
        case "rest":
            "TA 睡着了"
        default:
            activity.canGeneratePhoto ? "TA 正在认真看这个地方" : "TA 正在自主停留"
        }
    }

    private static func markerText(for activity: WorldActivity) -> String {
        if activity.kind == "rest" {
            return "睡着了"
        }
        if activity.status == .walking, activity.mode == .walk {
            return "散步中"
        }
        return activity.status.displayName
    }

    private static func modeLabel(for activity: WorldActivity, activeLeg: ScheduledTransportLeg?) -> String {
        if let activeLeg {
            return activeLeg.serviceLabel
        }
        return activity.mode?.displayName ?? activity.status.displayName
    }

    private static func durationText(for activity: WorldActivity) -> String {
        guard let endsAt = activity.endsAt else {
            return activity.status.displayName
        }
        let interval = endsAt.timeIntervalSince(.now)
        if interval > 0 {
            return "剩余 \(format(interval: interval))"
        }
        return "已完成"
    }

    private static func speedText(mode: TravelMode, distanceMeters: Int?, durationSeconds: Int?) -> String {
        guard mode != .stay, mode != .checkIn else { return "停留中" }
        guard let distanceMeters, let durationSeconds, durationSeconds > 0 else {
            switch mode {
            case .walk:
                return "步速约 4 km/h"
            case .drive:
                return "车速随路况"
            case .flight:
                return "按航班时间"
            case .train:
                return "按车次时间"
            case .transit:
                return "按公交时间"
            case .ferry:
                return "按航线时间"
            case .stay, .checkIn:
                return "停留中"
            }
        }
        let kmh = (Double(distanceMeters) / 1_000) / (Double(durationSeconds) / 3_600)
        switch mode {
        case .walk:
            return String(format: "步速 %.1f km/h", min(max(kmh, 2.4), 5.8))
        case .drive:
            return String(format: "车速 %.0f km/h", min(max(kmh, 8), 110))
        case .flight:
            return String(format: "航速 %.0f km/h", min(max(kmh, 420), 980))
        case .train:
            return String(format: "车速 %.0f km/h", min(max(kmh, 30), 320))
        case .transit:
            return String(format: "公交 %.0f km/h", min(max(kmh, 8), 55))
        case .ferry:
            return String(format: "航速 %.0f km/h", min(max(kmh, 8), 70))
        case .stay, .checkIn:
            return "停留中"
        }
    }

    private static func animationHint(for activity: WorldActivity, mode: TravelMode) -> String {
        if mode == .flight { return "transport_flight" }
        if mode == .train { return "transport_train" }
        if mode == .drive { return "transport_car" }
        if mode == .ferry { return "transport_ferry" }
        let text = [activity.title, activity.detail, activity.placeName ?? ""].joined(separator: " ").lowercased()
        if text.contains("咖啡") || text.contains("coffee") || text.contains("cafe") { return "coffee_drink" }
        if text.contains("网吧") || text.contains("游戏") || text.contains("屏幕") { return "gaming" }
        if activity.canGeneratePhoto { return "camera" }
        if mode == .walk { return "walking" }
        if activity.kind == "rest" { return "sleep" }
        return "observe"
    }

    private static func format(interval: TimeInterval) -> String {
        let minutes = max(0, Int(interval / 60))
        if minutes < 60 { return "\(minutes) min" }
        let hours = minutes / 60
        let remaining = minutes % 60
        if remaining == 0 { return "\(hours)h" }
        return "\(hours)h \(remaining)m"
    }

    private static func routeCoordinates(
        for activity: WorldActivity,
        activeLeg: ScheduledTransportLeg?,
        segment: RouteSegment?
    ) -> [CLLocationCoordinate2D]? {
        if let activeLeg, activeLeg.id == activity.currentTransportID {
            return activeLeg.routeCoordinates
        }
        if let segment {
            let coordinates = RoutePolylineDecoder.coordinates(from: segment.polyline)
            if coordinates.count > 1 {
                return coordinates
            }
        }
        return nil
    }

    private static func relatedEvent(for activity: WorldActivity, events: [JourneyMapEvent]) -> JourneyMapEvent? {
        if activity.kind != "movement", activity.kind != "transport", let placeName = activity.placeName {
            return events.first { $0.place.contains(placeName) }
        }
        return JourneyMotion.nearestEvent(to: activity.coordinate, events: events, maxDistanceMeters: 180)
    }

    private static func tint(for mode: TravelMode, fallback: Color?) -> Color {
        if let fallback {
            return fallback
        }
        switch mode {
        case .flight:
            return DesignTokens.dusk
        case .drive:
            return DesignTokens.amber
        case .train, .transit:
            return DesignTokens.sage
        case .ferry:
            return DesignTokens.pollen
        case .walk:
            return DesignTokens.clay
        case .stay, .checkIn:
            return DesignTokens.sage
        }
    }
}

private enum JourneyDaySchedule {
    static func activity(
        date: Date,
        anchor: CLLocationCoordinate2D,
        events: [JourneyMapEvent],
        movingCoordinate: CLLocationCoordinate2D,
        scheduledTransport: [ScheduledTransportLeg]
    ) -> JourneyActivitySnapshot {
        if let leg = scheduledTransport.foregroundLeg(at: date) {
            return transport(leg: leg, date: date)
        }

        let components = Calendar.current.dateComponents([.hour, .minute], from: date)
        let minuteOfDay = (components.hour ?? 0) * 60 + (components.minute ?? 0)

        switch minuteOfDay {
        case 0..<420:
            return rest(
                start: 0,
                end: 420,
                minuteOfDay: minuteOfDay,
                event: overnightRestEvent(events: events),
                anchor: anchor,
                title: "在上一段旅程结束的地方休息",
                detail: "今天还没有开始，TA 先在昨晚停下来的地方安静待着，等天亮后再慢慢出发。",
                tint: DesignTokens.dusk
            )
        case 420..<510:
            return stay(
                start: 420,
                end: 510,
                minuteOfDay: minuteOfDay,
                event: event(at: 0, events: events),
                anchor: anchor,
                title: "在今天第一站慢慢醒来",
                detail: "TA 先确认周围的光线和声音，决定今天从这条安静的小路开始。"
            )
        case 510..<570:
            return walk(
                title: "搭一小段车去老城",
                detail: "早上的第一段距离稍远，TA 选择短途车去八市附近，把体力留给真正想停的地方。",
                movingCoordinate: movingCoordinate,
                relatedEvent: event(at: 1, events: events)
            )
        case 570..<690:
            return checkIn(
                start: 570,
                end: 690,
                minuteOfDay: minuteOfDay,
                event: event(at: 1, events: events),
                anchor: anchor,
                title: "走进老城的人间烟火",
                detail: "TA 在八市和开禾路慢慢看摊位、听声音，选一口厦门早午间的本地味道。"
            )
        case 690..<750:
            return walk(
                title: "从老城靠近老港",
                detail: "TA 沿真实道路去沙坡尾和大学路，中途不会乱穿路，也不会突然跳到海上。",
                movingCoordinate: movingCoordinate,
                relatedEvent: event(at: 2, events: events)
            )
        case 750..<900:
            return stay(
                start: 750,
                end: 900,
                minuteOfDay: minuteOfDay,
                event: event(at: 2, events: events),
                anchor: anchor,
                title: "在沙坡尾和大学路慢慢逛",
                detail: "这里有海风、旧港和小店。TA 找了一个不挡路的位置，坐下来把看到的颜色记住。"
            )
        case 900..<1_080:
            return stay(
                start: 900,
                end: 1_080,
                minuteOfDay: minuteOfDay,
                event: event(at: 3, events: events),
                anchor: anchor,
                title: "去海边收下午的风",
                detail: "TA 靠近环岛路和白城沙滩，走慢一点，把海面、树影和路边的光记进手机。"
            )
        case 1_080..<1_140:
            return walk(
                title: "傍晚回到湖边",
                detail: "下午结束后，TA 搭一小段车回到筼筜湖附近，把当天收在安静的地方。",
                movingCoordinate: movingCoordinate,
                relatedEvent: event(at: 4, events: events)
            )
        case 1_140..<1_320:
            return checkIn(
                start: 1_140,
                end: 1_320,
                minuteOfDay: minuteOfDay,
                event: event(at: 4, events: events),
                anchor: anchor,
                title: "在白鹭洲和筼筜湖边写信",
                detail: "天色变软以后，TA 在湖边慢下来，把今天写成一封小小的信。"
            )
        default:
            return rest(
                start: 1_320,
                end: 1_440,
                minuteOfDay: minuteOfDay,
                event: event(at: 4, events: events),
                anchor: anchor,
                title: "找了一个不被打扰的位置休息",
                detail: "今天的本地计划快结束了，TA 没有继续赶路，只是让自己慢下来。",
                tint: DesignTokens.dusk
            )
        }
    }

    private static func event(at index: Int, events: [JourneyMapEvent]) -> JourneyMapEvent? {
        guard !events.isEmpty else { return nil }
        return events[min(index, events.count - 1)]
    }

    private static func overnightRestEvent(events: [JourneyMapEvent]) -> JourneyMapEvent? {
        events.last
    }

    private static func stay(
        start: Int,
        end: Int,
        minuteOfDay: Int,
        event: JourneyMapEvent?,
        anchor: CLLocationCoordinate2D,
        title: String,
        detail: String
    ) -> JourneyActivitySnapshot {
        JourneyActivitySnapshot(
            kind: .staying,
            title: title,
            detail: detail,
            eyebrow: "TA 正在自主停留",
            markerText: "停留中",
            modeLabel: "本地停留",
            durationText: elapsedLabel(start: start, end: end, minuteOfDay: minuteOfDay),
            speedText: "停留中",
            progress: progress(start: start, end: end, minuteOfDay: minuteOfDay),
            travelMode: .stay,
            systemImage: event?.systemImage ?? "mappin.and.ellipse",
            markerSystemImage: "pawprint.fill",
            animationHint: fallbackAnimationHint(title: title, detail: detail, systemImage: event?.systemImage),
            tint: event?.tint ?? DesignTokens.sage,
            liveCoordinate: event?.coordinate ?? anchor,
            routeCoordinatesOverride: nil,
            relatedEvent: event
        )
    }

    private static func checkIn(
        start: Int,
        end: Int,
        minuteOfDay: Int,
        event: JourneyMapEvent?,
        anchor: CLLocationCoordinate2D,
        title: String,
        detail: String
    ) -> JourneyActivitySnapshot {
        JourneyActivitySnapshot(
            kind: .checkingIn,
            title: title,
            detail: detail,
            eyebrow: "TA 正在打卡",
            markerText: "打卡中",
            modeLabel: "地点打卡",
            durationText: elapsedLabel(start: start, end: end, minuteOfDay: minuteOfDay),
            speedText: "停留中",
            progress: progress(start: start, end: end, minuteOfDay: minuteOfDay),
            travelMode: .checkIn,
            systemImage: event?.systemImage ?? "camera.fill",
            markerSystemImage: "pawprint.fill",
            animationHint: "camera",
            tint: event?.tint ?? DesignTokens.clay,
            liveCoordinate: event?.coordinate ?? anchor,
            routeCoordinatesOverride: nil,
            relatedEvent: event
        )
    }

    private static func rest(
        start: Int,
        end: Int,
        minuteOfDay: Int,
        event: JourneyMapEvent?,
        anchor: CLLocationCoordinate2D,
        title: String,
        detail: String,
        tint: Color
    ) -> JourneyActivitySnapshot {
        JourneyActivitySnapshot(
            kind: .resting,
            title: title,
            detail: detail,
            eyebrow: "TA 睡着了",
            markerText: "睡着了",
            modeLabel: "睡眠",
            durationText: sleepElapsedLabel(start: start, end: end, minuteOfDay: minuteOfDay),
            speedText: "停留中",
            progress: progress(start: start, end: end, minuteOfDay: minuteOfDay),
            travelMode: .stay,
            systemImage: "moon.zzz.fill",
            markerSystemImage: "moon.zzz.fill",
            animationHint: "sleep",
            tint: tint,
            liveCoordinate: event?.coordinate ?? anchor,
            routeCoordinatesOverride: nil,
            relatedEvent: event
        )
    }

    private static func walk(
        title: String,
        detail: String,
        movingCoordinate: CLLocationCoordinate2D,
        relatedEvent: JourneyMapEvent?
    ) -> JourneyActivitySnapshot {
        JourneyActivitySnapshot(
            kind: .walking,
            title: title,
            detail: detail,
            eyebrow: "TA 正在路上",
            markerText: "散步中",
            modeLabel: "步行中",
            durationText: "路上",
            speedText: "步速约 4 km/h",
            progress: 0.58,
            travelMode: .walk,
            systemImage: TravelMode.walk.systemImage,
            markerSystemImage: TravelMode.walk.systemImage,
            animationHint: "walking",
            tint: DesignTokens.sage,
            liveCoordinate: movingCoordinate,
            routeCoordinatesOverride: nil,
            relatedEvent: relatedEvent
        )
    }

    private static func transport(leg: ScheduledTransportLeg, date: Date) -> JourneyActivitySnapshot {
        let modeTint = tint(for: leg.mode)
        return JourneyActivitySnapshot(
            kind: .transporting,
            title: leg.title,
            detail: leg.timelineNote ?? leg.detail,
            eyebrow: eyebrow(for: leg),
            markerText: leg.status.displayName,
            modeLabel: leg.serviceLabel,
            durationText: leg.remainingText(at: date),
            speedText: leg.averageSpeedText,
            progress: leg.timelineProgress(at: date),
            travelMode: leg.mode,
            systemImage: leg.mode.systemImage,
            markerSystemImage: leg.mode.systemImage,
            animationHint: transportAnimationHint(for: leg.mode),
            tint: modeTint,
            liveCoordinate: leg.liveCoordinate(at: date),
            routeCoordinatesOverride: leg.routeCoordinates,
            relatedEvent: nil
        )
    }

    private static func fallbackAnimationHint(title: String, detail: String, systemImage: String?) -> String {
        let text = [title, detail, systemImage ?? ""].joined(separator: " ").lowercased()
        if text.contains("咖啡") || text.contains("coffee") || text.contains("cafe") {
            return "coffee_drink"
        }
        if text.contains("网吧") || text.contains("游戏") || text.contains("屏幕") {
            return "gaming"
        }
        if text.contains("餐") || text.contains("饭") || text.contains("小吃") || text.contains("便利店") {
            return "snack"
        }
        if text.contains("相机") || text.contains("camera") {
            return "camera"
        }
        return "observe"
    }

    private static func transportAnimationHint(for mode: TravelMode) -> String {
        switch mode {
        case .flight:
            return "transport_flight"
        case .train:
            return "transport_train"
        case .drive, .transit:
            return "transport_car"
        case .ferry:
            return "transport_ferry"
        case .walk:
            return "walking"
        case .stay, .checkIn:
            return "observe"
        }
    }

    private static func eyebrow(for leg: ScheduledTransportLeg) -> String {
        switch leg.status {
        case .waiting, .boarding:
            "TA 正在准备\(leg.mode.displayName)"
        case .inTransit:
            "TA 正在\(leg.mode.displayName)途中"
        case .arrived:
            "TA 已经抵达"
        case .scheduled:
            "下一段交通已计划"
        case .delayed:
            "交通有点延误"
        case .cancelled:
            "这段交通取消了"
        }
    }

    private static func tint(for mode: TravelMode) -> Color {
        switch mode {
        case .flight:
            DesignTokens.dusk
        case .train, .transit:
            DesignTokens.sage
        case .drive:
            DesignTokens.amber
        case .walk:
            DesignTokens.clay
        case .ferry:
            DesignTokens.pollen
        case .stay, .checkIn:
            DesignTokens.sage
        }
    }

    private static func elapsedLabel(start: Int, end: Int, minuteOfDay: Int) -> String {
        let elapsed = max(0, minuteOfDay - start)
        let planned = max(1, end - start)
        return "已停留 \(format(minutes: elapsed)) / 计划 \(format(minutes: planned))"
    }

    private static func sleepElapsedLabel(start: Int, end: Int, minuteOfDay: Int) -> String {
        let elapsed = max(0, minuteOfDay - start)
        let planned = max(1, end - start)
        return "已睡 \(format(minutes: elapsed)) / 预计 \(format(minutes: planned))"
    }

    private static func progress(start: Int, end: Int, minuteOfDay: Int) -> Double {
        let planned = max(1, end - start)
        let elapsed = min(max(0, minuteOfDay - start), planned)
        return max(0.08, min(0.96, Double(elapsed) / Double(planned)))
    }

    private static func format(minutes: Int) -> String {
        if minutes < 60 { return "\(minutes) min" }
        let hours = minutes / 60
        let remaining = minutes % 60
        if remaining == 0 { return "\(hours)h" }
        return "\(hours)h \(remaining)m"
    }
}

private extension JourneyStatus {
    var symbolName: String {
        switch self {
        case .traveling: "map.fill"
        case .flying: "paperplane.fill"
        case .resting: "moon.zzz.fill"
        case .staying: "mappin.and.ellipse"
        case .walking: "figure.walk"
        }
    }
}

private extension Array where Element == ScheduledTransportLeg {
    func foregroundLeg(at date: Date) -> ScheduledTransportLeg? {
        first { leg in
            switch leg.status {
            case .waiting, .boarding, .inTransit, .delayed:
                true
            case .scheduled:
                date >= leg.scheduledDeparture.addingTimeInterval(-60 * 60)
                    && date <= leg.scheduledDeparture
            case .arrived:
                date <= leg.scheduledArrival.addingTimeInterval(15 * 60)
            case .cancelled:
                false
            }
        }
    }
}

private extension ScheduledTransportLeg {
    var routeCoordinates: [CLLocationCoordinate2D] {
        let decoded = RoutePolylineDecoder.coordinates(from: routePolyline)
        if decoded.count > 1 {
            return decoded
        }
        return [originCoordinate, destinationCoordinate]
    }

    var averageSpeedText: String {
        guard let distanceMeters, let durationSeconds, durationSeconds > 0 else {
            switch mode {
            case .walk:
                return "步速约 4 km/h"
            case .drive:
                return "车速随路况"
            case .flight:
                return "按航班时间"
            case .train:
                return "按车次时间"
            case .transit:
                return "按公交时间"
            case .ferry:
                return "按航线时间"
            case .stay, .checkIn:
                return "停留中"
            }
        }
        let kmh = (Double(distanceMeters) / 1_000) / (Double(durationSeconds) / 3_600)
        switch mode {
        case .walk:
            return String(format: "步速 %.1f km/h", min(max(kmh, 2.4), 5.8))
        case .drive:
            return String(format: "车速 %.0f km/h", min(max(kmh, 8), 110))
        case .flight:
            return String(format: "航速 %.0f km/h", min(max(kmh, 420), 980))
        case .train:
            return String(format: "车速 %.0f km/h", min(max(kmh, 30), 320))
        case .transit:
            return String(format: "公交 %.0f km/h", min(max(kmh, 8), 55))
        case .ferry:
            return String(format: "航速 %.0f km/h", min(max(kmh, 8), 70))
        case .stay, .checkIn:
            return "停留中"
        }
    }

    func liveCoordinate(at date: Date) -> CLLocationCoordinate2D {
        let progress = timelineProgress(at: date)
        return JourneyMotion.coordinate(on: routeCoordinates, progress: progress) ?? originCoordinate
    }

    func timelineProgress(at date: Date) -> Double {
        let total = max(1, scheduledArrival.timeIntervalSince(scheduledDeparture))
        let elapsed = date.timeIntervalSince(scheduledDeparture)
        return max(0, min(1, elapsed / total))
    }

    func remainingText(at date: Date) -> String {
        switch status {
        case .scheduled, .waiting, .boarding:
            return "距出发 \(format(interval: max(0, scheduledDeparture.timeIntervalSince(date))))"
        case .inTransit, .delayed:
            return "预计 \(format(interval: max(0, scheduledArrival.timeIntervalSince(date)))) 后到达"
        case .arrived:
            return "已到达 \(destinationName)"
        case .cancelled:
            return "这段已取消"
        }
    }

    private func format(interval: TimeInterval) -> String {
        let minutes = max(0, Int(interval / 60))
        if minutes < 60 { return "\(minutes) min" }
        let hours = minutes / 60
        let remaining = minutes % 60
        if remaining == 0 { return "\(hours)h" }
        return "\(hours)h \(remaining)m"
    }
}

private extension String {
    var petSoulUserFacingText: String {
        var text = self
        let replacements: [(String, String)] = [
            ("适合攻略型打卡，但不强迫 TA 喜欢这里。", "这里有真实的本地味道，TA 可以进去看看，再把感受记下来。"),
            ("适合攻略型打卡，但不强迫 TA 喜欢这里", "这里有真实的本地味道，TA 可以进去看看，再把感受记下来"),
            ("不强迫 TA 喜欢这里", "TA 只是按自己的节奏停一会儿"),
            ("用户可以收藏这段攻略，但不会改变 TA 的感受。", "你可以把这段记下来，TA 仍然会按自己的节奏继续走。"),
            ("用户可以收藏这段攻略，但不会改变 TA 的感受", "你可以把这段记下来，TA 仍然会按自己的节奏继续走"),
            ("适合攻略型打卡", "适合进去看看"),
            ("攻略型打卡", "旅程记录"),
            ("可能会", "会"),
            ("可能", ""),
            ("打卡", "停留")
        ]
        for (source, target) in replacements {
            text = text.replacingOccurrences(of: source, with: target)
        }

        let patterns = [
            #"[\s·。；;，,]*(?:地点来源|数据来源|来源|source|provider)\s*[:：]\s*[\w.+/\- ]+"#,
            #"这个地点来自[^。；;]*[。；;]?"#,
            #"来自(?:高德|Google|google|AMap|amap)[^。；;]*[。；;]?"#,
            #"\b(?:amap|google|mock|hybrid|openai|web|map|provider|service|engine|client|route|planner|mission)(?:[-_][A-Za-z0-9]+)+\b"#,
            #"适合[^。；;]*攻略型[^。；;]*[。；;]?"#
        ]
        for pattern in patterns {
            text = text.replacingOccurrences(of: pattern, with: "", options: .regularExpression)
        }
        text = text.replacingOccurrences(of: #"\s{2,}"#, with: " ", options: .regularExpression)
        text = text.replacingOccurrences(of: #"\s+([。；;，,])"#, with: "$1", options: .regularExpression)
        text = text.replacingOccurrences(of: #"([，,。；;])\1+"#, with: "$1", options: .regularExpression)
        return text.trimmingCharacters(in: CharacterSet.whitespacesAndNewlines.union(CharacterSet(charactersIn: "·,，;；。")))
    }
}
