import MapKit
import SwiftUI
import UIKit

struct PublicWorldView: View {
    var onFindPet: () -> Void

    @State var selectedEvent: WorldLifeEvent?
    @State var pulse = false
    @State var showsWorldNote = false
    @State var resetToken = 0

    var body: some View {
        NavigationStack {
            ZStack(alignment: .bottom) {
                NativeGlobeMapView(
                    selectedID: selectedEvent?.id,
                    resetToken: resetToken,
                    onSelect: select
                )
                .saturation(1.18)
                .contrast(1.06)
                .brightness(0.018)
                .ignoresSafeArea()

                mapMoodOverlay

                VStack(spacing: 0) {
                    worldHeader
                    Spacer()
                }
                .padding(.horizontal, DesignTokens.pagePadding)
                .padding(.top, 12)

                VStack(spacing: 12) {
                    if showsWorldNote {
                        WorldNoteCard()
                            .transition(.move(edge: .bottom).combined(with: .opacity))
                    }

                    if let selectedEvent {
                        WorldEventDetailCard(
                            event: selectedEvent,
                            onClose: {
                                withAnimation(.easeInOut(duration: 0.25)) {
                                    self.selectedEvent = nil
                                }
                            },
                            onResetWorld: zoomToWorld
                        )
                        .transition(.move(edge: .bottom).combined(with: .opacity))
                    }

                    bottomPanel
                }
                .padding(.horizontal, DesignTokens.pagePadding)
                .padding(.bottom, 18)
            }
            .toolbar(.hidden, for: .navigationBar)
            .onAppear {
                withAnimation(.easeInOut(duration: 1.9).repeatForever(autoreverses: true)) {
                    pulse = true
                }
            }
        }
    }

    var mapMoodOverlay: some View {
        ZStack {
            LinearGradient(
                colors: [
                    DesignTokens.welcome.moodTop.opacity(0.05),
                    .clear,
                    DesignTokens.welcome.moodBottom.opacity(0.14)
                ],
                startPoint: .top,
                endPoint: .bottom
            )

            RadialGradient(
                colors: [
                    DesignTokens.welcome.radialBlush.opacity(pulse ? 0.08 : 0.04),
                    DesignTokens.welcome.radialCream.opacity(0.03),
                    .clear
                ],
                center: .center,
                startRadius: 30,
                endRadius: 430
            )
            .scaleEffect(pulse ? 1.04 : 0.97)

            AmbientSignalField(
                tint: DesignTokens.sea,
                warmth: DesignTokens.welcome.signalWarmth,
                density: 24,
                drift: 0.46
            )
            .opacity(0.58)
        }
        .ignoresSafeArea()
        .allowsHitTesting(false)
    }

    var worldHeader: some View {
        HStack(spacing: 10) {
            HStack(spacing: 10) {
                Image(systemName: "globe.europe.africa.fill")
                    .font(.system(size: 17, weight: .semibold))
                    .foregroundStyle(DesignTokens.welcome.warmInk)
                    .frame(width: 34, height: 34)
                    .background(DesignTokens.welcome.chipCream.opacity(0.92))
                    .clipShape(Circle())

                VStack(alignment: .leading, spacing: 2) {
                    Text("PetJourney")
                        .font(.headline.weight(.semibold))
                        .foregroundStyle(DesignTokens.ink)
                    Text("灵魂世界正在旅行")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(DesignTokens.welcome.subInk)
                }
            }
            .padding(.vertical, 9)
            .padding(.horizontal, 10)
            .background(DesignTokens.surface.opacity(0.88))
            .clipShape(Capsule())
            .overlay {
                Capsule().stroke(DesignTokens.surfaceStroke.opacity(0.72), lineWidth: 1)
            }

            Spacer()

            Button(action: zoomToWorld) {
                Image(systemName: "globe.asia.australia")
                    .font(.headline.weight(.semibold))
                    .foregroundStyle(DesignTokens.welcome.warmInk)
                    .frame(width: 52, height: 52)
                    .background(DesignTokens.surface.opacity(0.88))
                    .clipShape(Circle())
                    .overlay {
                        Circle().stroke(DesignTokens.surfaceStroke.opacity(0.72), lineWidth: 1)
                    }
            }
            .buttonStyle(.plain)
            .accessibilityLabel("回到地球视角")
        }
        .shadow(color: DesignTokens.deepInk.opacity(0.08), radius: 16, x: 0, y: 8)
    }

    var bottomPanel: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .center, spacing: 12) {
                PetSoulAssetIcon(
                    asset: .signalPaw,
                    fallbackSystemImage: "sparkles",
                    fallbackTint: DesignTokens.welcome.fallbackTint,
                    size: 30
                )
                    .frame(width: 30, height: 30)
                    .background(DesignTokens.welcome.iconCream)
                    .clipShape(Circle())

                VStack(alignment: .leading, spacing: 5) {
                    Text("也许 TA 正在世界某个角落。")
                        .font(.headline.weight(.semibold))
                        .foregroundStyle(DesignTokens.ink)
                    Text("从一张照片和一点记忆开始，沿着真实地图慢慢寻找属于你的那一个信号。")
                        .font(.caption)
                        .foregroundStyle(DesignTokens.secondaryInk)
                        .lineSpacing(2)
                        .lineLimit(2)
                }

                Spacer(minLength: 0)

                Button {
                    withAnimation(.easeInOut(duration: 0.25)) {
                        showsWorldNote.toggle()
                    }
                } label: {
                    Image(systemName: showsWorldNote ? "xmark" : "info")
                        .font(.caption.weight(.bold))
                        .foregroundStyle(DesignTokens.welcome.infoInk)
                        .frame(width: 30, height: 30)
                        .background(DesignTokens.surface.opacity(0.76))
                        .clipShape(Circle())
                }
                .buttonStyle(.plain)
                .accessibilityLabel(showsWorldNote ? "收起说明" : "查看说明")
            }

            WorldLiveStoryTicker()

            HStack(spacing: 9) {
                WorldPill(title: "小店吃饭", systemImage: "fork.knife")
                WorldPill(title: "街角晒太阳", systemImage: "sun.max")
                WorldPill(title: "海边等风", systemImage: "wind")
            }

            Button(action: onFindPet) {
                Label("寻找我的 TA", systemImage: "camera.viewfinder")
            }
            .primaryActionStyle()
        }
        .padding(14)
        .background(DesignTokens.surface.opacity(0.93))
        .clipShape(RoundedRectangle(cornerRadius: 22, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 22, style: .continuous)
                .stroke(DesignTokens.surfaceStroke.opacity(0.76), lineWidth: 1)
        }
        .shadow(color: DesignTokens.welcome.shadowBrown.opacity(0.14), radius: 24, x: 0, y: 12)
    }

    func select(_ event: WorldLifeEvent) {
        withAnimation(.easeInOut(duration: 0.25)) {
            selectedEvent = event
        }
    }

    func zoomToWorld() {
        withAnimation(.easeInOut(duration: 0.3)) {
            selectedEvent = nil
            resetToken += 1
        }
    }
}

struct NativeGlobeMapView: UIViewRepresentable {
    var selectedID: String?
    var resetToken: Int
    var onSelect: (WorldLifeEvent) -> Void

    func makeCoordinator() -> Coordinator {
        Coordinator(onSelect: onSelect)
    }

    func makeUIView(context: Context) -> MKMapView {
        let mapView = MKMapView(frame: .zero)
        mapView.delegate = context.coordinator
        mapView.isRotateEnabled = false
        mapView.isPitchEnabled = false
        mapView.isZoomEnabled = true
        mapView.isScrollEnabled = true
        mapView.showsCompass = false
        mapView.showsScale = false
        mapView.pointOfInterestFilter = .includingAll
        mapView.cameraZoomRange = MKMapView.CameraZoomRange(
            minCenterCoordinateDistance: 1_000,
            maxCenterCoordinateDistance: 600_000_000
        )
        mapView.cameraBoundary = MKMapView.CameraBoundary(mapRect: .world)

        let configuration = MKStandardMapConfiguration(elevationStyle: .realistic)
        configuration.pointOfInterestFilter = .includingAll
        configuration.showsTraffic = false
        mapView.preferredConfiguration = configuration

        context.coordinator.resetWorld(on: mapView, animated: false)
        context.coordinator.refreshAnimalField(on: mapView)
        DispatchQueue.main.async {
            context.coordinator.resetWorld(on: mapView, animated: false)
            context.coordinator.refreshAnimalField(on: mapView)
        }
        return mapView
    }

    func updateUIView(_ mapView: MKMapView, context: Context) {
        context.coordinator.onSelect = onSelect
        context.coordinator.updateSelection(selectedID, on: mapView)

        if context.coordinator.lastResetToken != resetToken {
            context.coordinator.lastResetToken = resetToken
            context.coordinator.resetWorld(on: mapView, animated: true)
        }
    }

    final class Coordinator: NSObject, MKMapViewDelegate {
        var onSelect: (WorldLifeEvent) -> Void
        var annotationsByID: [String: WorldLifeAnnotation] = [:]
        var badgeViewsByID: [String: WorldAnimalBadgeView] = [:]
        var eventsByID: [String: WorldLifeEvent] = [:]
        var lastResetToken = 0
        var isProgrammaticSelection = false
        var selectedEvent: WorldLifeEvent?
        weak var mapView: MKMapView?

        init(onSelect: @escaping (WorldLifeEvent) -> Void) {
            self.onSelect = onSelect
        }

        func resetWorld(on mapView: MKMapView, animated: Bool) {
            mapView.deselectAllAnnotations(animated: true)
            let camera = MKMapCamera(
                lookingAtCenter: CLLocationCoordinate2D(latitude: 8, longitude: 38),
                fromDistance: 380_000_000,
                pitch: 0,
                heading: 0
            )
            mapView.setCamera(camera, animated: animated)
        }

        func refreshAnimalField(on mapView: MKMapView) {
            self.mapView = mapView
            var events = WorldAnimalField.events(for: mapView)
            let showsCompactBadges = shouldUseCompactBadges(on: mapView)

            if let selectedEvent, events.contains(where: { $0.id == selectedEvent.id }) == false {
                events.append(selectedEvent)
            }

            let nextIDs = Set(events.map(\.id))
            eventsByID = Dictionary(uniqueKeysWithValues: events.map { ($0.id, $0) })

            Set(badgeViewsByID.keys)
                .subtracting(nextIDs)
                .forEach { id in
                    badgeViewsByID[id]?.removeFromSuperview()
                    badgeViewsByID[id] = nil
                }

            events.forEach { event in
                let badge = badgeViewsByID[event.id] ?? {
                    let view = WorldAnimalBadgeView(event: event)
                    view.addTarget(self, action: #selector(didTapBadge(_:)), for: .touchUpInside)
                    mapView.addSubview(view)
                    badgeViewsByID[event.id] = view
                    return view
                }()
                badge.configure(with: event, compact: showsCompactBadges)
            }

            updateBadgePositions(on: mapView)
        }

        func shouldUseCompactBadges(on mapView: MKMapView) -> Bool {
            let worldSpanRatio = mapView.visibleMapRect.size.width / MKMapRect.world.size.width
            return mapView.camera.centerCoordinateDistance >= 72_000_000 || worldSpanRatio >= 0.22
        }

        func updateSelection(_ selectedID: String?, on mapView: MKMapView) {
            guard let selectedID, let event = eventsByID[selectedID] else { return }
            selectedEvent = event
        }

        func mapView(_ mapView: MKMapView, viewFor annotation: MKAnnotation) -> MKAnnotationView? {
            guard let annotation = annotation as? WorldLifeAnnotation else { return nil }

            let view = mapView.dequeueReusableAnnotationView(
                withIdentifier: WorldEventAnnotationView.reuseIdentifier
            ) as? WorldEventAnnotationView ?? WorldEventAnnotationView(
                annotation: annotation,
                reuseIdentifier: WorldEventAnnotationView.reuseIdentifier
            )
            view.annotation = annotation
            view.configure(with: annotation.event)
            return view
        }

        func mapView(_ mapView: MKMapView, didSelect view: MKAnnotationView) {
            guard let annotation = view.annotation as? WorldLifeAnnotation else { return }
            selectedEvent = annotation.event
            onSelect(annotation.event)

            if !isProgrammaticSelection {
                let camera = MKMapCamera(
                    lookingAtCenter: annotation.coordinate,
                    fromDistance: annotation.event.focusDistance,
                    pitch: 0,
                    heading: mapView.camera.heading
                )
                mapView.setCamera(camera, animated: true)
            }
        }

        func mapView(_ mapView: MKMapView, regionDidChangeAnimated animated: Bool) {
            refreshAnimalField(on: mapView)
        }

        func mapViewDidChangeVisibleRegion(_ mapView: MKMapView) {
            updateBadgePositions(on: mapView)
        }

        func updateBadgePositions(on mapView: MKMapView) {
            badgeViewsByID.values.forEach { badge in
                let point = mapView.convert(badge.event.coordinate, toPointTo: mapView)
                badge.center = CGPoint(x: point.x, y: point.y - 22)
                let horizontalInset = badge.bounds.width * 0.5 + 8
                let compact = badge.bounds.width <= 48
                let topLimit: CGFloat = compact ? 290 : 150
                let bottomLimit = mapView.bounds.height - (compact ? 360 : 300)
                badge.isHidden = point.x < horizontalInset
                    || point.x > mapView.bounds.width - horizontalInset
                    || point.y < topLimit
                    || point.y > bottomLimit
            }
        }

        @objc func didTapBadge(_ sender: WorldAnimalBadgeView) {
            selectedEvent = sender.event
            onSelect(sender.event)

            guard let mapView else { return }
            let camera = MKMapCamera(
                lookingAtCenter: sender.event.coordinate,
                fromDistance: sender.event.focusDistance,
                pitch: 0,
                heading: mapView.camera.heading
            )
            mapView.setCamera(camera, animated: true)
        }
    }
}

extension MKMapView {
    func deselectAllAnnotations(animated: Bool) {
        selectedAnnotations.forEach { deselectAnnotation($0, animated: animated) }
    }
}

struct WorldEventDetailCard: View {
    var event: WorldLifeEvent
    var onClose: () -> Void
    var onResetWorld: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .top, spacing: 12) {
                ZStack {
                    RoundedRectangle(cornerRadius: 18, style: .continuous)
                        .fill(event.tint.opacity(0.16))
                    VStack(spacing: 5) {
                        PetSoulAdaptiveIcon(
                            systemImage: event.sceneIcon,
                            tint: event.tint,
                            size: 38
                        )
                        Image(systemName: event.petType.symbolName)
                            .font(.system(size: 18, weight: .semibold))
                            .foregroundStyle(DesignTokens.ink.opacity(0.78))
                    }
                }
                .frame(width: 72, height: 72)

                VStack(alignment: .leading, spacing: 5) {
                    Text("\(event.city) · \(event.place)")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(DesignTokens.welcome.warmInk)
                    Text(event.activity)
                        .font(.headline.weight(.semibold))
                        .foregroundStyle(DesignTokens.ink)
                    Text("\(event.petName) \(event.detail)")
                        .font(.subheadline)
                        .foregroundStyle(DesignTokens.secondaryInk)
                        .lineSpacing(3)
                        .fixedSize(horizontal: false, vertical: true)
                }

                Spacer(minLength: 0)

                Button(action: onClose) {
                    Image(systemName: "xmark")
                        .font(.caption.weight(.bold))
                        .foregroundStyle(DesignTokens.secondaryInk)
                        .frame(width: 28, height: 28)
                        .background(DesignTokens.surface.opacity(0.78))
                        .clipShape(Circle())
                }
                .buttonStyle(.plain)
                .accessibilityLabel("关闭事件卡")
            }

            HStack(spacing: 10) {
                Button(action: onResetWorld) {
                    Label("回到地球", systemImage: "globe")
                        .frame(maxWidth: .infinity)
                }
                .quietActionStyle()

                Button(action: onClose) {
                    Label("继续放大", systemImage: "plus.magnifyingglass")
                        .frame(maxWidth: .infinity)
                }
                .quietActionStyle()
            }
        }
        .padding(16)
        .background(DesignTokens.surface.opacity(0.94))
        .clipShape(RoundedRectangle(cornerRadius: 22, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 22, style: .continuous)
                .stroke(DesignTokens.surfaceStroke.opacity(0.76), lineWidth: 1)
        }
        .shadow(color: DesignTokens.welcome.shadowBrown.opacity(0.13), radius: 24, x: 0, y: 12)
    }
}

struct WorldLiveStoryTicker: View {
    @EnvironmentObject var session: AppSessionStore
    @Environment(\.accessibilityReduceMotion) var reduceMotion
    @State var remoteEvents: [WorldLifeEvent] = []

    let storyInterval: TimeInterval = 4.2

    var body: some View {
        TimelineView(.periodic(from: .now, by: storyInterval)) { timeline in
            let event = currentEvent(at: timeline.date)

            HStack(spacing: 10) {
                ZStack {
                    SignalPulseRings(tint: event.tint, size: 38, lineWidth: 1.1, ringCount: 2)
                        .opacity(0.62)
                    PetSoulAdaptiveIcon(
                        systemImage: event.sceneIcon,
                        tint: event.tint,
                        size: 24
                    )
                }
                .frame(width: 34, height: 34)

                VStack(alignment: .leading, spacing: 2) {
                    Text("\(event.petName) · \(event.city)")
                        .font(.caption.weight(.bold))
                        .foregroundStyle(DesignTokens.ink)
                        .lineLimit(1)
                    Text(event.activity)
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(DesignTokens.secondaryInk)
                        .lineLimit(1)
                        .minimumScaleFactor(0.75)
                }

                Spacer(minLength: 0)

                HStack(spacing: 4) {
                    Circle()
                        .fill(event.tint)
                        .frame(width: 6, height: 6)
                    Text("刚刚")
                        .font(.caption2.weight(.semibold))
                }
                .foregroundStyle(event.tint)
                .padding(.vertical, 5)
                .padding(.horizontal, 8)
                .background(event.tint.opacity(0.10))
                .clipShape(Capsule())
            }
            .padding(.vertical, 9)
            .padding(.horizontal, 10)
            .background(DesignTokens.welcome.tickerCream.opacity(0.84))
            .clipShape(RoundedRectangle(cornerRadius: 17, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: 17, style: .continuous)
                    .stroke(DesignTokens.surfaceStroke.opacity(0.72), lineWidth: 1)
            }
            .id(event.id)
            .transition(reduceMotion ? .opacity : .opacity.combined(with: .move(edge: .bottom)))
            .animation(reduceMotion ? nil : .easeInOut(duration: 0.35), value: event.id)
        }
        .task { await loadRemoteStories() }
    }

    var storyPool: [WorldLifeEvent] {
        remoteEvents.isEmpty ? WorldLifeEvent.samples : remoteEvents
    }

    func currentEvent(at date: Date) -> WorldLifeEvent {
        let pool = storyPool
        guard !pool.isEmpty else {
            return WorldLifeEvent(
                id: "world-empty",
                city: "世界",
                place: "云层边缘",
                petName: "TA",
                petType: .dog,
                activity: "在等一个熟悉的信号",
                detail: "手机正在寻找。",
                latitude: 0,
                longitude: 0,
                tintHex: 0xD6AA63,
                sceneIcon: "sparkles"
            )
        }

        let index = Int(date.timeIntervalSinceReferenceDate / storyInterval) % pool.count
        return pool[index]
    }

    /// 拉取世界故事条：成功则替换本地样本；失败时本地生成器继续兜底，界面无感。
    func loadRemoteStories() async {
        guard session.serviceMode == .remote,
              let base = URL(string: session.baseURLString) else { return }
        struct TickerItem: Decodable {
            let id: String
            let text: String
            let city: String
        }
        struct TickerResponse: Decodable {
            let items: [TickerItem]
        }
        let url = base.appendingPathComponent("api/v1/world/story_ticker")
        guard let (data, response) = try? await URLSession.shared.data(from: url),
              let http = response as? HTTPURLResponse,
              http.statusCode == 200,
              let payload = try? JSONDecoder().decode(TickerResponse.self, from: data),
              !payload.items.isEmpty else { return }
        remoteEvents = payload.items.map { item in
            WorldLifeEvent(
                id: item.id,
                city: item.city,
                place: item.city,
                petName: "平行世界",
                petType: .cat,
                activity: item.text,
                detail: item.text,
                latitude: 0,
                longitude: 0,
                tintHex: 0xD6AA63,
                sceneIcon: "sparkles"
            )
        }
    }
}

struct WorldPill: View {
    var title: String
    var systemImage: String

    var body: some View {
        Label(title, systemImage: systemImage)
            .font(.caption.weight(.semibold))
            .foregroundStyle(DesignTokens.secondaryInk)
            .lineLimit(1)
            .minimumScaleFactor(0.78)
            .frame(maxWidth: .infinity)
            .padding(.vertical, 9)
            .background(DesignTokens.welcome.pillCream.opacity(0.88))
            .clipShape(Capsule())
    }
}

struct WorldNoteCard: View {
    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: "heart.text.square")
                .font(.title3.weight(.semibold))
                .foregroundStyle(DesignTokens.welcome.noteAccent)
                .frame(width: 32)

            Text("这里是情感陪伴体验，不代表宗教、医疗或真实灵性声明。地图用于营造空间感和旅程感，帮助你继续和 TA 说说话。")
                .font(.footnote)
                .foregroundStyle(DesignTokens.secondaryInk)
                .lineSpacing(4)
        }
        .padding(16)
        .background(DesignTokens.surface.opacity(0.94))
        .clipShape(RoundedRectangle(cornerRadius: DesignTokens.controlRadius, style: .continuous))
        .shadow(color: DesignTokens.welcome.shadowBrown.opacity(0.1), radius: 18, x: 0, y: 9)
    }
}
