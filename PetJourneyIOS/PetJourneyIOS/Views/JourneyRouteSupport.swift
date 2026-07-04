import CoreLocation
import MapKit

struct JourneyRoutePlan {
    enum Source {
        case empty
        case mapKitWalking
        case backendPolyline
        case mockStreet
    }

    var key: String
    var coordinates: [CLLocationCoordinate2D]
    var source: Source
    var distanceMeters: CLLocationDistance
    var expectedTravelTime: TimeInterval?

    static let empty = JourneyRoutePlan(
        key: "",
        coordinates: [],
        source: .empty,
        distanceMeters: 0,
        expectedTravelTime: nil
    )

    var hasRoute: Bool {
        coordinates.count > 1
    }

    var sourceLabel: String {
        switch source {
        case .empty:
            "正在看路"
        case .mapKitWalking:
            "沿步行路走"
        case .backendPolyline:
            "沿真实道路走"
        case .mockStreet:
            "沿街慢慢走"
        }
    }

    var distanceLabel: String {
        guard distanceMeters > 0 else { return "看路中" }
        if distanceMeters >= 1_000 {
            return String(format: "%.1f km", distanceMeters / 1_000)
        }
        return "\(Int(distanceMeters)) m"
    }

    static func fallback(key: String, stops: [CLLocationCoordinate2D]) -> JourneyRoutePlan {
        let coordinates = JourneyMotion.fallbackStreetRoute(through: stops)
        return JourneyRoutePlan(
            key: key,
            coordinates: coordinates,
            source: .mockStreet,
            distanceMeters: JourneyMotion.totalDistance(of: coordinates),
            expectedTravelTime: nil
        )
    }

    static func backendPlan(from journeyPlan: JourneyPlan?) -> JourneyRoutePlan? {
        guard let journeyPlan else { return nil }
        let stopsByName = Dictionary(uniqueKeysWithValues: journeyPlan.stops.map { ($0.name, $0.coordinate) })
        var coordinates: [CLLocationCoordinate2D] = []

        for segment in journeyPlan.routeSegments {
            let segmentCoordinates = RoutePolylineDecoder.coordinates(from: segment.polyline)
            let resolvedCoordinates: [CLLocationCoordinate2D]
            if segmentCoordinates.count > 1 {
                resolvedCoordinates = segmentCoordinates
            } else if let start = stopsByName[segment.fromPlace], let end = stopsByName[segment.toPlace] {
                switch segment.mode {
                case .walk, .drive, .transit:
                    resolvedCoordinates = JourneyMotion.fallbackStreetRoute(through: [start, end])
                case .flight, .train, .ferry:
                    resolvedCoordinates = [start, end]
                case .stay, .checkIn:
                    resolvedCoordinates = [start]
                }
            } else {
                continue
            }

            guard !resolvedCoordinates.isEmpty else { continue }
            if coordinates.isEmpty {
                coordinates.append(contentsOf: resolvedCoordinates)
            } else {
                coordinates.append(contentsOf: resolvedCoordinates.dropFirst())
            }
        }

        guard coordinates.count > 1 else { return nil }
        let providerDistance = journeyPlan.routeSegments.compactMap(\.distanceMeters).reduce(0, +)
        let providerDuration = journeyPlan.routeSegments.compactMap(\.durationSeconds).reduce(0, +)
        return JourneyRoutePlan(
            key: "backend-\(journeyPlan.generatedAt.timeIntervalSinceReferenceDate)-\(coordinates.count)",
            coordinates: coordinates,
            source: .backendPolyline,
            distanceMeters: providerDistance > 0 ? CLLocationDistance(providerDistance) : JourneyMotion.totalDistance(of: coordinates),
            expectedTravelTime: providerDuration > 0 ? TimeInterval(providerDuration) : nil
        )
    }
}

enum JourneyRoutePlanner {
    static func walkingPlan(through stops: [CLLocationCoordinate2D], key: String) async -> JourneyRoutePlan? {
        guard stops.count > 1 else { return nil }

        var coordinates: [CLLocationCoordinate2D] = []
        var distanceMeters: CLLocationDistance = 0
        var expectedTravelTime: TimeInterval = 0

        for index in 0..<(stops.count - 1) {
            guard !Task.isCancelled else { return nil }

            let request = MKDirections.Request()
            request.source = MKMapItem(placemark: MKPlacemark(coordinate: stops[index]))
            request.destination = MKMapItem(placemark: MKPlacemark(coordinate: stops[index + 1]))
            request.transportType = .walking
            request.requestsAlternateRoutes = false

            do {
                let response = try await MKDirections(request: request).calculate()
                guard let route = response.routes.min(by: { $0.expectedTravelTime < $1.expectedTravelTime }) else {
                    return nil
                }
                let segmentCoordinates = route.polyline.coordinateArray
                if coordinates.isEmpty {
                    coordinates.append(contentsOf: segmentCoordinates)
                } else {
                    coordinates.append(contentsOf: segmentCoordinates.dropFirst())
                }
                distanceMeters += route.distance
                expectedTravelTime += route.expectedTravelTime
            } catch {
                return nil
            }
        }

        guard coordinates.count > stops.count else { return nil }
        return JourneyRoutePlan(
            key: key,
            coordinates: coordinates,
            source: .mapKitWalking,
            distanceMeters: distanceMeters,
            expectedTravelTime: expectedTravelTime
        )
    }
}

struct JourneyMotion {
    static func stopCoordinates(anchor: CLLocationCoordinate2D, events: [JourneyMapEvent]) -> [CLLocationCoordinate2D] {
        guard !events.isEmpty else { return [anchor] }
        return events.map(\.coordinate)
    }

    static func routeKey(stops: [CLLocationCoordinate2D]) -> String {
        stops
            .map { coordinate in
                "\(String(format: "%.5f", coordinate.latitude)),\(String(format: "%.5f", coordinate.longitude))"
            }
            .joined(separator: "|")
    }

    static func fallbackStreetRoute(through stops: [CLLocationCoordinate2D]) -> [CLLocationCoordinate2D] {
        guard stops.count > 1 else { return stops }

        var route: [CLLocationCoordinate2D] = [stops[0]]
        for index in 0..<(stops.count - 1) {
            let start = stops[index]
            let end = stops[index + 1]
            let midLongitude = start.longitude + (end.longitude - start.longitude) * 0.58
            route.append(CLLocationCoordinate2D(latitude: start.latitude, longitude: midLongitude))
            route.append(CLLocationCoordinate2D(latitude: end.latitude, longitude: midLongitude))
            route.append(end)
        }
        return route
    }

    static func liveCoordinate(route: [CLLocationCoordinate2D], date: Date) -> CLLocationCoordinate2D {
        guard route.count > 1 else { return route.first ?? CityPosition.xiamen.coordinate }

        let totalDistance = totalDistance(of: route)
        guard totalDistance > 0 else { return route[0] }

        let cycleDuration: TimeInterval = 42
        let elapsed = date.timeIntervalSinceReferenceDate.truncatingRemainder(dividingBy: cycleDuration)
        let targetDistance = totalDistance * (elapsed / cycleDuration)

        var walkedDistance: CLLocationDistance = 0
        for index in 0..<(route.count - 1) {
            let start = route[index]
            let end = route[index + 1]
            let segmentDistance = distance(from: start, to: end)
            if walkedDistance + segmentDistance >= targetDistance {
                let progress = segmentDistance == 0 ? 0 : (targetDistance - walkedDistance) / segmentDistance
                return interpolate(from: start, to: end, progress: smoothStep(progress))
            }
            walkedDistance += segmentDistance
        }

        return route.last ?? route[0]
    }

    static func stablePreviewCoordinate(
        route: [CLLocationCoordinate2D],
        fallback: CLLocationCoordinate2D
    ) -> CLLocationCoordinate2D {
        route.first ?? fallback
    }

    static func coordinate(on route: [CLLocationCoordinate2D], progress: Double) -> CLLocationCoordinate2D? {
        guard route.count > 1 else { return route.first }

        let totalDistance = totalDistance(of: route)
        guard totalDistance > 0 else { return route[0] }

        let targetDistance = totalDistance * min(max(progress, 0), 1)
        var walkedDistance: CLLocationDistance = 0
        for index in 0..<(route.count - 1) {
            let start = route[index]
            let end = route[index + 1]
            let segmentDistance = distance(from: start, to: end)
            if walkedDistance + segmentDistance >= targetDistance {
                let localProgress = segmentDistance == 0 ? 0 : (targetDistance - walkedDistance) / segmentDistance
                return interpolate(from: start, to: end, progress: localProgress)
            }
            walkedDistance += segmentDistance
        }

        return route.last
    }

    static func totalDistance(of route: [CLLocationCoordinate2D]) -> CLLocationDistance {
        guard route.count > 1 else { return 0 }
        return (0..<(route.count - 1)).reduce(CLLocationDistance(0)) { partialResult, index in
            partialResult + distance(from: route[index], to: route[index + 1])
        }
    }

    static func nearestEvent(
        to coordinate: CLLocationCoordinate2D,
        events: [JourneyMapEvent],
        maxDistanceMeters: CLLocationDistance = 180
    ) -> JourneyMapEvent? {
        guard let nearest = events.min(by: { first, second in
            distance(from: coordinate, to: first.coordinate) < distance(from: coordinate, to: second.coordinate)
        }) else {
            return nil
        }
        return distance(from: coordinate, to: nearest.coordinate) <= maxDistanceMeters ? nearest : nil
    }

    private static func interpolate(
        from start: CLLocationCoordinate2D,
        to end: CLLocationCoordinate2D,
        progress: Double
    ) -> CLLocationCoordinate2D {
        CLLocationCoordinate2D(
            latitude: start.latitude + (end.latitude - start.latitude) * progress,
            longitude: start.longitude + (end.longitude - start.longitude) * progress
        )
    }

    private static func smoothStep(_ value: Double) -> Double {
        let clamped = min(max(value, 0), 1)
        return clamped * clamped * (3 - 2 * clamped)
    }

    private static func distance(from lhs: CLLocationCoordinate2D, to rhs: CLLocationCoordinate2D) -> CLLocationDistance {
        CLLocation(latitude: lhs.latitude, longitude: lhs.longitude)
            .distance(from: CLLocation(latitude: rhs.latitude, longitude: rhs.longitude))
    }
}

enum RoutePolylineDecoder {
    static func coordinates(from raw: String?) -> [CLLocationCoordinate2D] {
        guard let raw, !raw.isEmpty else { return [] }
        let lngLatCoordinates = decodeLngLatPolyline(raw)
        if lngLatCoordinates.count > 1 {
            return lngLatCoordinates
        }
        return decodeGooglePolyline(raw)
    }

    private static func decodeLngLatPolyline(_ raw: String) -> [CLLocationCoordinate2D] {
        let chunks = raw.split(separator: ";")
        guard !chunks.isEmpty else { return [] }
        var coordinates: [CLLocationCoordinate2D] = []
        for chunk in chunks {
            let parts = chunk.split(separator: ",")
            guard parts.count == 2, let longitude = Double(parts[0]), let latitude = Double(parts[1]) else {
                return []
            }
            coordinates.append(CLLocationCoordinate2D(latitude: latitude, longitude: longitude))
        }
        return coordinates
    }

    private static func decodeGooglePolyline(_ raw: String) -> [CLLocationCoordinate2D] {
        let scalars = Array(raw.unicodeScalars)
        var index = 0
        var latitude = 0
        var longitude = 0
        var coordinates: [CLLocationCoordinate2D] = []

        while index < scalars.count {
            guard let latitudeDelta = decodeValue(scalars, index: &index),
                  let longitudeDelta = decodeValue(scalars, index: &index) else {
                return []
            }
            latitude += latitudeDelta
            longitude += longitudeDelta
            coordinates.append(
                CLLocationCoordinate2D(
                    latitude: Double(latitude) / 100_000,
                    longitude: Double(longitude) / 100_000
                )
            )
        }

        return coordinates
    }

    private static func decodeValue(_ scalars: [Unicode.Scalar], index: inout Int) -> Int? {
        var result = 0
        var shift = 0

        while index < scalars.count {
            let byte = Int(scalars[index].value) - 63
            index += 1
            result |= (byte & 0x1F) << shift
            shift += 5
            if byte < 0x20 {
                return (result & 1) != 0 ? ~(result >> 1) : (result >> 1)
            }
        }

        return nil
    }
}

struct CoordinateOffset {
    var latitude: Double
    var longitude: Double
}

extension MKPolyline {
    var coordinateArray: [CLLocationCoordinate2D] {
        var coordinates = Array(
            repeating: CLLocationCoordinate2D(latitude: 0, longitude: 0),
            count: pointCount
        )
        getCoordinates(&coordinates, range: NSRange(location: 0, length: pointCount))
        return coordinates
    }
}
