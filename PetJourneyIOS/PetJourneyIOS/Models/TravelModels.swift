import CoreLocation
import Foundation

enum TravelMode: String, Codable, Equatable, Sendable {
    case stay
    case walk
    case drive
    case transit
    case train
    case flight
    case ferry
    case checkIn = "check_in"
}

extension TravelMode {
    var displayName: String {
        switch self {
        case .stay: "停留"
        case .walk: "步行"
        case .drive: "汽车"
        case .transit: "公共交通"
        case .train: "火车"
        case .flight: "飞机"
        case .ferry: "轮渡"
        case .checkIn: "打卡"
        }
    }

    var systemImage: String {
        switch self {
        case .stay: "mappin.and.ellipse"
        case .walk: "pawprint.fill"
        case .drive: "car.fill"
        case .transit: "bus.fill"
        case .train: "tram.fill"
        case .flight: "airplane"
        case .ferry: "ferry.fill"
        case .checkIn: "camera.fill"
        }
    }

    var navigationLookAheadMeters: CLLocationDistance {
        switch self {
        case .drive:
            180
        case .transit:
            140
        default:
            100
        }
    }

    var navigationCameraDistance: CLLocationDistance {
        switch self {
        case .drive:
            920
        case .transit:
            840
        default:
            760
        }
    }

    var navigationPitch: Double {
        switch self {
        case .drive:
            76
        case .transit:
            72
        default:
            68
        }
    }
}

enum TransportLegStatus: String, Codable, Equatable, Sendable {
    case scheduled
    case waiting
    case boarding
    case inTransit = "in_transit"
    case arrived
    case delayed
    case cancelled

    var displayName: String {
        switch self {
        case .scheduled: "已计划"
        case .waiting: "等待中"
        case .boarding: "准备出发"
        case .inTransit: "进行中"
        case .arrived: "已抵达"
        case .delayed: "延误"
        case .cancelled: "已取消"
        }
    }
}

struct RouteSegment: Codable, Identifiable, Equatable, Sendable {
    var id: String
    var mode: TravelMode
    var title: String
    var detail: String
    var fromPlace: String
    var toPlace: String
    var distanceMeters: Int?
    var durationSeconds: Int?
    var provider: String
    var polyline: String?
    var startTime: Date?
    var endTime: Date?
    var isSimulated: Bool

    enum CodingKeys: String, CodingKey {
        case id
        case mode
        case title
        case detail
        case fromPlace = "from_place"
        case toPlace = "to_place"
        case distanceMeters = "distance_meters"
        case durationSeconds = "duration_seconds"
        case provider
        case polyline
        case startTime = "start_time"
        case endTime = "end_time"
        case isSimulated = "is_simulated"
    }
}

struct ScheduledTransportLeg: Codable, Identifiable, Equatable, Sendable {
    var id: String
    var mode: TravelMode
    var status: TransportLegStatus
    var title: String
    var detail: String
    var originName: String
    var destinationName: String
    var originLatitude: Double
    var originLongitude: Double
    var destinationLatitude: Double
    var destinationLongitude: Double
    var scheduledDeparture: Date
    var scheduledArrival: Date
    var actualDeparture: Date?
    var actualArrival: Date?
    var carrier: String?
    var serviceNumber: String?
    var terminalOrPlatform: String?
    var distanceMeters: Int?
    var durationSeconds: Int?
    var routePolyline: String?
    var progress: Double
    var provider: String
    var realityLevel: String
    var isSimulated: Bool
    var timelineNote: String?

    var originCoordinate: CLLocationCoordinate2D {
        CLLocationCoordinate2D(latitude: originLatitude, longitude: originLongitude)
    }

    var destinationCoordinate: CLLocationCoordinate2D {
        CLLocationCoordinate2D(latitude: destinationLatitude, longitude: destinationLongitude)
    }

    var serviceLabel: String {
        let parts = [carrier, serviceNumber]
            .compactMap { $0?.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
        return parts.isEmpty ? mode.displayName : parts.joined(separator: " ")
    }

    enum CodingKeys: String, CodingKey {
        case id
        case mode
        case status
        case title
        case detail
        case originName = "origin_name"
        case destinationName = "destination_name"
        case originLatitude = "origin_lat"
        case originLongitude = "origin_lng"
        case destinationLatitude = "destination_lat"
        case destinationLongitude = "destination_lng"
        case scheduledDeparture = "scheduled_departure"
        case scheduledArrival = "scheduled_arrival"
        case actualDeparture = "actual_departure"
        case actualArrival = "actual_arrival"
        case carrier
        case serviceNumber = "service_number"
        case terminalOrPlatform = "terminal_or_platform"
        case distanceMeters = "distance_meters"
        case durationSeconds = "duration_seconds"
        case routePolyline = "route_polyline"
        case progress
        case provider
        case realityLevel = "reality_level"
        case isSimulated = "is_simulated"
        case timelineNote = "timeline_note"
    }
}

struct ItineraryStop: Codable, Identifiable, Equatable, Sendable {
    var id: String
    var name: String
    var category: String
    var city: String
    var latitude: Double
    var longitude: Double
    var title: String
    var detail: String
    var plannedTime: String?
    var dwellMinutes: Int
    var postcardCandidate: Bool
    var photoCandidate: Bool
    var source: String

    var coordinate: CLLocationCoordinate2D {
        CLLocationCoordinate2D(latitude: latitude, longitude: longitude)
    }

    enum CodingKeys: String, CodingKey {
        case id
        case name
        case category
        case city
        case latitude = "lat"
        case longitude = "lng"
        case title
        case detail
        case plannedTime = "planned_time"
        case dwellMinutes = "dwell_minutes"
        case postcardCandidate = "postcard_candidate"
        case photoCandidate = "photo_candidate"
        case source
    }
}

struct TransportDecision: Codable, Equatable, Sendable {
    var selectedMode: TravelMode
    var reason: String
    var rejectedModes: [TravelMode]
    var autonomyNote: String

    enum CodingKeys: String, CodingKey {
        case selectedMode = "selected_mode"
        case reason
        case rejectedModes = "rejected_modes"
        case autonomyNote = "autonomy_note"
    }
}

struct JourneyPlan: Codable, Equatable, Sendable {
    var petID: String
    var city: String
    var generatedAt: Date
    var provider: String
    var horizonHours: Int
    var summary: String
    var currentActivity: String
    var transportDecision: TransportDecision
    var routeSegments: [RouteSegment]
    var scheduledTransport: [ScheduledTransportLeg] = []
    var stops: [ItineraryStop]
    var places: [PlaceSignal]
    var nextPostcardHint: String?
    var worldcupEvent: Bool

    enum CodingKeys: String, CodingKey {
        case petID = "pet_id"
        case city
        case generatedAt = "generated_at"
        case provider
        case horizonHours = "horizon_hours"
        case summary
        case currentActivity = "current_activity"
        case transportDecision = "transport_decision"
        case routeSegments = "route_segments"
        case scheduledTransport = "scheduled_transport"
        case stops
        case places
        case nextPostcardHint = "next_postcard_hint"
        case worldcupEvent = "worldcup_event"
    }
}

