import AuthenticationServices
import MapKit
import SwiftUI
import UIKit


struct LivingJourneyMap: View {
    var status: AgentStatus
    var homeCoordinate: CLLocationCoordinate2D
    var petCoordinate: CLLocationCoordinate2D
    var now: Date
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

    @State var smoothedLatitude: Double?
    @State var smoothedLongitude: Double?

    var displayedPetCoordinate: CLLocationCoordinate2D {
        guard let smoothedLatitude, let smoothedLongitude else { return petCoordinate }
        return CLLocationCoordinate2D(latitude: smoothedLatitude, longitude: smoothedLongitude)
    }

    var petHeadingDegrees: Double? {
        guard activity.kind == .walking || activity.kind == .transporting else { return nil }
        let route = routeCoordinates
        guard route.count > 1 else { return nil }
        let petLocation = CLLocation(latitude: petCoordinate.latitude, longitude: petCoordinate.longitude)
        let nearestIndex = route.indices.min { left, right in
            CLLocation(latitude: route[left].latitude, longitude: route[left].longitude).distance(from: petLocation)
                < CLLocation(latitude: route[right].latitude, longitude: route[right].longitude).distance(from: petLocation)
        } ?? route.startIndex
        let nextIndex = min(nearestIndex + 1, route.index(before: route.endIndex))
        guard nextIndex > nearestIndex else { return nil }
        return JourneyMotion.bearingDegrees(from: route[nearestIndex], to: route[nextIndex])
    }

    var routeCoordinates: [CLLocationCoordinate2D] {
        JourneyRouteVisual.visibleCoordinates(
            from: activity.routeCoordinatesOverride ?? routePlan.coordinates,
            activity: activity,
            petCoordinate: petCoordinate
        )
    }

    var visibleEvents: [JourneyMapEvent] {
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
                    .stroke(DesignTokens.surfaceStroke.opacity(0.66), style: StrokeStyle(lineWidth: 7, lineCap: .round, lineJoin: .round))

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

            Annotation("", coordinate: displayedPetCoordinate, anchor: .center) {
                LivePetMarkerView(
                    petID: status.petID,
                    petType: status.petType ?? .dog,
                    name: status.name,
                    statusText: activity.markerText,
                    systemImage: activity.markerSystemImage,
                    activityKind: activity.kind,
                    animationHint: activity.animationHint,
                    tint: activity.tint,
                    headingDegrees: petHeadingDegrees
                )
            }
        }
        .mapStyle(.standard(elevation: .realistic, pointsOfInterest: .excludingAll, showsTraffic: false))
        .mapControls {
            MapUserLocationButton()
            MapCompass()
        }
        .onChange(of: now) { _, _ in
            advanceSmoothedPet()
        }
        .onAppear {
            smoothedLatitude = petCoordinate.latitude
            smoothedLongitude = petCoordinate.longitude
        }
    }

    /// 软纠偏:只平滑行走中的小幅服务端纠偏(45~260 米);更大的跳变是换场景/初次定位,直接贴上。
    func advanceSmoothedPet() {
        guard let latitude = smoothedLatitude, let longitude = smoothedLongitude else {
            smoothedLatitude = petCoordinate.latitude
            smoothedLongitude = petCoordinate.longitude
            return
        }
        let current = CLLocation(latitude: latitude, longitude: longitude)
        let target = CLLocation(latitude: petCoordinate.latitude, longitude: petCoordinate.longitude)
        let distance = current.distance(from: target)
        if distance >= 45, distance <= 260 {
            smoothedLatitude = latitude + (petCoordinate.latitude - latitude) * 0.5
            smoothedLongitude = longitude + (petCoordinate.longitude - longitude) * 0.5
        } else {
            smoothedLatitude = petCoordinate.latitude
            smoothedLongitude = petCoordinate.longitude
        }
    }
}

struct JourneyMapAtmosphere: View {
    var tint: Color
    var date: Date = Date()
    /// TA 所在地的当地时间（后端 local_time，墙上时间按 GMT 解析）：
    /// 地图昼夜必须跟着 TA 走，而不是主人的设备时区（UI/UX 审计 P0-2）。
    var localTime: Date?

    enum DayPhase: CaseIterable {
        case dawn
        case day
        case dusk
        case night
    }

    /// 读墙上时间的日历：local_time 按 GMT 解析，小时分量即 TA 所在地的小时。
    static let petLocalCalendar: Calendar = {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(secondsFromGMT: 0) ?? .gmt
        return calendar
    }()

    static func phase(for date: Date, calendar: Calendar) -> DayPhase {
        #if DEBUG
        if let override = ProcessInfo.processInfo.environment["PETJOURNEY_MAP_PHASE"] {
            if let matched = DayPhase.allCases.first(where: { String(describing: $0) == override }) {
                return matched
            }
        }
        #endif
        switch calendar.component(.hour, from: date) {
        case 5..<8: return .dawn
        case 8..<17: return .day
        case 17..<20: return .dusk
        default: return .night
        }
    }

    private var phaseDate: Date { localTime ?? date }
    private var phaseCalendar: Calendar { localTime == nil ? Calendar.current : Self.petLocalCalendar }

    var phase: DayPhase {
        Self.phase(for: phaseDate, calendar: phaseCalendar)
    }

    var washColors: [Color] {
        switch phase {
        case .dawn:
            [
                DesignTokens.amber.opacity(0.30),
                DesignTokens.mapWash.dawnCream.opacity(0.18),
                DesignTokens.porcelain.opacity(0.52)
            ]
        case .day:
            [
                Color.black.opacity(0.14),
                .clear,
                DesignTokens.porcelain.opacity(0.44)
            ]
        case .dusk:
            [
                DesignTokens.mapWash.duskMauve.opacity(0.36),
                DesignTokens.mapWash.duskEmber.opacity(0.24),
                DesignTokens.mapWash.duskCream.opacity(0.48)
            ]
        case .night:
            // UI/UX 审计 P0-1：夜间 wash 此前落到屏上约 0.08–0.12，约等于没有。
            // 提高强度让暖夜性格可见，同时保留路网可读性。
            [
                DesignTokens.mapWash.nightDeep.opacity(0.78),
                DesignTokens.mapWash.nightMid.opacity(0.58),
                DesignTokens.mapWash.nightSoft.opacity(0.62)
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
                        DesignTokens.mapWash.horizonGlow.opacity(0.36)
                    ],
                    startPoint: .center,
                    endPoint: .bottom
                )
            }

            if phase == .night {
                AmbientSignalField(
                    tint: .white,
                    warmth: DesignTokens.mapWash.nightStarlight,
                    density: 26,
                    drift: 0.1
                )
                .opacity(0.68)
            }

            AmbientSignalField(
                tint: tint,
                warmth: DesignTokens.pollen,
                density: 16,
                drift: 0.28
            )
            .opacity(phase == .night ? 0.5 : 0.55)

            NavigationScanOverlay(tint: tint)
                .opacity(0.42)
        }
        .ignoresSafeArea()
        .allowsHitTesting(false)
        .animation(.easeInOut(duration: 1.4), value: phase)
    }
}

struct NavigationScanOverlay: View {
    var tint: Color
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        TimelineView(.animation(minimumInterval: 1 / 30, paused: reduceMotion)) { timeline in
            let time = reduceMotion ? 0 : timeline.date.timeIntervalSinceReferenceDate
            Canvas { context, size in
                guard size.width > 0, size.height > 0 else { return }
                let phase = time.truncatingRemainder(dividingBy: 3.8) / 3.8
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
