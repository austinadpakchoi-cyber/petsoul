import AuthenticationServices
import MapKit
import SwiftUI
import UIKit

struct JourneyMapViewport {
    var focus: CLLocationCoordinate2D
    var routeCoordinates: [CLLocationCoordinate2D]
    var eventCoordinates: [CLLocationCoordinate2D]
    var routeDistanceMeters: CLLocationDistance

    var coordinates: [CLLocationCoordinate2D] {
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

    var navigationTargetCoordinate: CLLocationCoordinate2D? {
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

    var shiftedFocus: CLLocationCoordinate2D {
        CLLocationCoordinate2D(latitude: focus.latitude - 0.018, longitude: focus.longitude)
    }

    var boundsCenter: CLLocationCoordinate2D {
        guard !coordinates.isEmpty else { return focus }
        return CLLocationCoordinate2D(
            latitude: (minLatitude + maxLatitude) / 2,
            longitude: longitudeCenter
        )
    }

    var minLatitude: Double {
        coordinates.map(\.latitude).min() ?? focus.latitude
    }

    var maxLatitude: Double {
        coordinates.map(\.latitude).max() ?? focus.latitude
    }

    var maxLatitudeDelta: Double {
        max(0.03, maxLatitude - minLatitude)
    }

    var maxLongitudeDelta: Double {
        let longitudes = coordinates.map { normalizedLongitude($0.longitude) }
        guard let minimumLongitude = longitudes.min(), let maximumLongitude = longitudes.max() else { return 0.03 }
        let direct = maximumLongitude - minimumLongitude
        return Swift.max(0.03, Swift.min(direct, 360 - direct))
    }

    var maxDelta: Double {
        max(maxLatitudeDelta, maxLongitudeDelta)
    }

    var spanDistanceMeters: CLLocationDistance {
        max(maxLatitudeDelta, maxLongitudeDelta) * 111_320
    }

    var longitudeCenter: Double {
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

    func normalizedLongitude(_ longitude: Double) -> Double {
        var value = longitude.truncatingRemainder(dividingBy: 360)
        if value < 0 { value += 360 }
        return value
    }

    func denormalizedLongitude(_ longitude: Double) -> Double {
        var value = longitude.truncatingRemainder(dividingBy: 360)
        if value > 180 { value -= 360 }
        if value < -180 { value += 360 }
        return value
    }

    static func bearingDegrees(from start: CLLocationCoordinate2D, to end: CLLocationCoordinate2D) -> Double {
        let lat1 = start.latitude * .pi / 180
        let lat2 = end.latitude * .pi / 180
        let deltaLongitude = (end.longitude - start.longitude) * .pi / 180
        let y = sin(deltaLongitude) * cos(lat2)
        let x = cos(lat1) * sin(lat2) - sin(lat1) * cos(lat2) * cos(deltaLongitude)
        let bearing = atan2(y, x) * 180 / .pi
        return (bearing + 360).truncatingRemainder(dividingBy: 360)
    }

    static func offsetCoordinate(
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

enum JourneyRouteVisual {
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

    static func focusedSlice(
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

struct JourneyMapAtmosphere: View {
    var tint: Color
    var date: Date = Date()

    enum DayPhase {
        case dawn
        case day
        case dusk
        case night
    }

    var phase: DayPhase {
        switch Calendar.current.component(.hour, from: date) {
        case 5..<8: .dawn
        case 8..<17: .day
        case 17..<20: .dusk
        default: .night
        }
    }

    var washColors: [Color] {
        switch phase {
        case .dawn:
            [
                DesignTokens.amber.opacity(0.20),
                DesignTokens.mapWash.dawnCream.opacity(0.10),
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
                DesignTokens.mapWash.duskMauve.opacity(0.22),
                DesignTokens.mapWash.duskEmber.opacity(0.14),
                DesignTokens.mapWash.duskCream.opacity(0.40)
            ]
        case .night:
            [
                DesignTokens.mapWash.nightDeep.opacity(0.46),
                DesignTokens.mapWash.nightMid.opacity(0.30),
                DesignTokens.mapWash.nightSoft.opacity(0.34)
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

struct NavigationScanOverlay: View {
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
