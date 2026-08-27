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
