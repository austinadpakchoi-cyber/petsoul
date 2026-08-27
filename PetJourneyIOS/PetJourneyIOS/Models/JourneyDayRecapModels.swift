import AuthenticationServices
import MapKit
import SwiftUI
import UIKit

struct DayRecapChapter: Identifiable, Equatable {
    enum Kind {
        case move
        case stay
    }

    let id: Int
    var kind: Kind
    var title: String
    var subtitle: String
    var route: [CLLocationCoordinate2D]
    var coordinate: CLLocationCoordinate2D
    var tint: Color
    var systemImage: String
    var imageURL: URL?
    var duration: TimeInterval

    static func == (lhs: DayRecapChapter, rhs: DayRecapChapter) -> Bool {
        lhs.id == rhs.id
    }
}

enum DayRecapBuilder {
    static func chapters(
        events: [JourneyMapEvent],
        routePlan: JourneyRoutePlan,
        postcards: [Postcard]
    ) -> [DayRecapChapter] {
        guard !events.isEmpty else { return [] }
        let todayPhotos = postcards.filter { Calendar.current.isDateInToday($0.timestamp) && $0.imageURL != nil }
        let photoPool = todayPhotos.isEmpty ? postcards.filter { $0.imageURL != nil } : todayPhotos

        let hasRealRoute = routePlan.source == .backendPolyline || routePlan.source == .mapKitWalking

        var chapters: [DayRecapChapter] = []
        var stayCount = 0
        for (index, stop) in events.enumerated() {
            if index > 0 {
                let slice = routeSlice(
                    route: hasRealRoute ? routePlan.coordinates : [],
                    from: events[index - 1].coordinate,
                    to: stop.coordinate
                )
                let meters = JourneyMotion.totalDistance(of: slice)
                chapters.append(
                    DayRecapChapter(
                        id: chapters.count,
                        kind: .move,
                        title: "去\(stop.shortPlaceName)",
                        subtitle: stop.timeLabel,
                        route: slice,
                        coordinate: stop.coordinate,
                        tint: stop.tint,
                        systemImage: "pawprint.fill",
                        imageURL: nil,
                        duration: min(6, max(3.2, meters / 900))
                    )
                )
            }
            let photoURL = stayCount < photoPool.count ? photoPool[stayCount].imageURL : nil
            chapters.append(
                DayRecapChapter(
                    id: chapters.count,
                    kind: .stay,
                    title: stop.title,
                    subtitle: "\(stop.timeLabel) · \(stop.shortPlaceName)",
                    route: [],
                    coordinate: stop.coordinate,
                    tint: stop.tint,
                    systemImage: stop.systemImage,
                    imageURL: photoURL,
                    duration: photoURL != nil ? 4.4 : 3.2
                )
            )
            stayCount += 1
        }
        return chapters
    }

    static func routeSlice(
        route: [CLLocationCoordinate2D],
        from start: CLLocationCoordinate2D,
        to end: CLLocationCoordinate2D
    ) -> [CLLocationCoordinate2D] {
        guard route.count > 1 else { return arcRoute(from: start, to: end) }
        let startIndex = nearestIndex(in: route, to: start)
        let endIndex = nearestIndex(in: route, to: end)
        var slice: [CLLocationCoordinate2D]
        if startIndex < endIndex {
            slice = Array(route[startIndex...endIndex])
        } else if endIndex < startIndex {
            slice = Array(route[endIndex...startIndex].reversed())
        } else {
            return arcRoute(from: start, to: end)
        }
        // 端点对齐到站点坐标,章节衔接时宠物不会跳一下
        if let first = slice.first, meters(from: first, to: start) > 4 {
            slice.insert(start, at: 0)
        }
        if let last = slice.last, meters(from: last, to: end) > 4 {
            slice.append(end)
        }
        return slice
    }

    /// 没有真实路网数据时,用一条柔和的二次贝塞尔弧线代替直角折线。
    static func arcRoute(from start: CLLocationCoordinate2D, to end: CLLocationCoordinate2D) -> [CLLocationCoordinate2D] {
        let midLatitude = (start.latitude + end.latitude) / 2
        let midLongitude = (start.longitude + end.longitude) / 2
        let deltaLatitude = end.latitude - start.latitude
        let deltaLongitude = end.longitude - start.longitude
        let control = CLLocationCoordinate2D(
            latitude: midLatitude - deltaLongitude * 0.18,
            longitude: midLongitude + deltaLatitude * 0.18
        )
        let sampleCount = 26
        return (0...sampleCount).map { step in
            let t = Double(step) / Double(sampleCount)
            let a = (1 - t) * (1 - t)
            let b = 2 * t * (1 - t)
            let c = t * t
            return CLLocationCoordinate2D(
                latitude: a * start.latitude + b * control.latitude + c * end.latitude,
                longitude: a * start.longitude + b * control.longitude + c * end.longitude
            )
        }
    }

    static func meters(from lhs: CLLocationCoordinate2D, to rhs: CLLocationCoordinate2D) -> CLLocationDistance {
        CLLocation(latitude: lhs.latitude, longitude: lhs.longitude)
            .distance(from: CLLocation(latitude: rhs.latitude, longitude: rhs.longitude))
    }

    static func nearestIndex(in route: [CLLocationCoordinate2D], to coordinate: CLLocationCoordinate2D) -> Int {
        let target = CLLocation(latitude: coordinate.latitude, longitude: coordinate.longitude)
        return route.indices.min { left, right in
            CLLocation(latitude: route[left].latitude, longitude: route[left].longitude).distance(from: target)
                < CLLocation(latitude: route[right].latitude, longitude: route[right].longitude).distance(from: target)
        } ?? 0
    }
}
