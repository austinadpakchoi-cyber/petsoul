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

    // MARK: - 自然运动

    /// 把线性时间进度重映射为带节奏的位移进度。
    /// 步行有确定性的"走-停-走"节奏,车船机有起步/到站缓动;同一 seed 在任何设备、任何时刻回放结果一致。
    static func pacedProgress(
        elapsed: TimeInterval,
        duration: TimeInterval,
        mode: TravelMode?,
        seed: UInt64
    ) -> Double {
        guard duration > 0 else { return 1 }
        let t = min(max(elapsed / duration, 0), 1)
        switch mode {
        case .walk, nil:
            return walkCadence(t, duration: duration, seed: seed)
        case .drive, .transit:
            return trapezoidEase(t, ramp: 0.16)
        case .flight, .train, .ferry:
            return trapezoidEase(t, ramp: 0.08)
        case .stay, .checkIn:
            return t
        }
    }

    /// 停留时的小范围踱步:两组不可通约频率的正弦叠加,慢速、不重复、确定性。
    static func wanderedCoordinate(
        around coordinate: CLLocationCoordinate2D,
        date: Date,
        seed: UInt64,
        radiusMeters: Double = 13
    ) -> CLLocationCoordinate2D {
        let time = date.timeIntervalSinceReferenceDate
        let phase = Double(seed % 977) * 0.618
        let east = sin(time / 19 + phase) * 0.62 + sin(time / 47 + phase * 2.3) * 0.38
        let north = sin(time / 23 + phase * 1.7) * 0.58 + sin(time / 41 + phase * 3.1) * 0.42
        let latDelta = (north * radiusMeters) / 111_320
        let metersPerLonDegree = 111_320 * cos(coordinate.latitude * .pi / 180)
        let lonDelta = metersPerLonDegree > 1 ? (east * radiusMeters) / metersPerLonDegree : 0
        return CLLocationCoordinate2D(
            latitude: coordinate.latitude + latDelta,
            longitude: coordinate.longitude + lonDelta
        )
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

    static func seed(_ text: String) -> UInt64 {
        text.utf8.reduce(0xCBF2_9CE4_8422_2325 as UInt64) { ($0 ^ UInt64($1)) &* 0x0000_0100_0000_01B3 }
    }

    /// 梯形速度曲线:头尾 ramp 段匀加/减速,中段匀速,总位移归一。
    private static func trapezoidEase(_ t: Double, ramp: Double) -> Double {
        let e = min(max(ramp, 0.01), 0.5)
        let peak = 1 / (1 - e)
        if t < e {
            return peak * t * t / (2 * e)
        }
        if t > 1 - e {
            let remaining = 1 - t
            return 1 - peak * remaining * remaining / (2 * e)
        }
        return peak * (e / 2 + (t - e))
    }

    private static func walkCadence(_ t: Double, duration: TimeInterval, seed: UInt64) -> Double {
        guard duration > 90 else { return trapezoidEase(t, ramp: 0.2) }
        let cycleCount = max(2, min(14, Int(duration / 50)))
        var generator = SplitMix64(seed: seed)
        var moveWeights: [Double] = []
        var pauseWeights: [Double] = []
        for _ in 0..<cycleCount {
            moveWeights.append(0.7 + generator.nextUnit() * 0.9)
            pauseWeights.append(0.12 + generator.nextUnit() * 0.3)
        }
        pauseWeights[cycleCount - 1] = 0

        let totalTime = zip(moveWeights, pauseWeights).reduce(0.0) { $0 + $1.0 + $1.1 }
        let totalMove = moveWeights.reduce(0, +)
        let target = min(max(t, 0), 1) * totalTime

        var timeCursor = 0.0
        var moveCursor = 0.0
        for index in 0..<cycleCount {
            let move = moveWeights[index]
            let pause = pauseWeights[index]
            if target < timeCursor + move {
                let local = (target - timeCursor) / move
                return (moveCursor + move * trapezoidEase(local, ramp: 0.3)) / totalMove
            }
            timeCursor += move
            moveCursor += move
            if target < timeCursor + pause {
                return moveCursor / totalMove
            }
            timeCursor += pause
        }
        return 1
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

struct SplitMix64 {
    private var state: UInt64

    init(seed: UInt64) {
        state = seed &+ 0x9E37_79B9_7F4A_7C15
    }

    mutating func next() -> UInt64 {
        state &+= 0x9E37_79B9_7F4A_7C15
        var z = state
        z = (z ^ (z >> 30)) &* 0xBF58_476D_1CE4_E5B9
        z = (z ^ (z >> 27)) &* 0x94D0_49BB_1331_11EB
        return z ^ (z >> 31)
    }

    mutating func nextUnit() -> Double {
        Double(next() >> 11) * (1.0 / 9_007_199_254_740_992.0)
    }
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
