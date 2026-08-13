import CoreLocation
import Foundation

struct RemoteJourneyRoutePlan: Codable, Equatable, Sendable {
    var petID: String
    var city: String
    var generatedAt: Date
    var provider: String
    var steps: [RemoteRouteStep]
    var places: [PlaceSignal]

    enum CodingKeys: String, CodingKey {
        case petID = "pet_id"
        case city
        case generatedAt = "generated_at"
        case provider
        case steps
        case places
    }
}

extension JourneyPlan {
    var compatibilityRoutePlan: RemoteJourneyRoutePlan {
        let stopSteps = stops.map { stop in
            RemoteRouteStep(
                id: "\(stop.id)-stay",
                mode: TravelMode.stay.rawValue,
                title: stop.title,
                detail: stop.detail,
                startTime: nil,
                endTime: nil,
                fromPlace: stop.name,
                toPlace: nil
            )
        }
        let segmentSteps = routeSegments.map { segment in
            RemoteRouteStep(
                id: segment.id,
                mode: segment.mode.rawValue,
                title: segment.title,
                detail: segment.detail,
                startTime: segment.startTime,
                endTime: segment.endTime,
                fromPlace: segment.fromPlace,
                toPlace: segment.toPlace
            )
        }
        return RemoteJourneyRoutePlan(
            petID: petID,
            city: city,
            generatedAt: generatedAt,
            provider: provider,
            steps: stopSteps + segmentSteps,
            places: places
        )
    }
}

struct RemoteRouteStep: Codable, Identifiable, Equatable, Sendable {
    var id: String
    var mode: String
    var title: String
    var detail: String
    var startTime: Date?
    var endTime: Date?
    var fromPlace: String?
    var toPlace: String?

    enum CodingKeys: String, CodingKey {
        case id
        case mode
        case title
        case detail
        case startTime = "start_time"
        case endTime = "end_time"
        case fromPlace = "from_place"
        case toPlace = "to_place"
    }
}

struct PlaceSignal: Codable, Identifiable, Equatable, Sendable {
    var id: String
    var name: String
    var category: String
    var city: String
    var latitude: Double
    var longitude: Double
    var activityHint: String
    var detailHint: String
    var source: String
    var rating: Double? = nil
    var cost: String? = nil
    var photoURL: URL? = nil
    var businessArea: String? = nil
    var distanceMeters: Int? = nil
    var guideScore: Double? = nil
    var guideReason: String? = nil
    var raw: [String: JSONValue]? = nil

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
        case activityHint = "activity_hint"
        case detailHint = "detail_hint"
        case source
        case rating
        case cost
        case photoURL = "photo_url"
        case businessArea = "business_area"
        case distanceMeters = "distance_meters"
        case guideScore = "guide_score"
        case guideReason = "guide_reason"
        case raw
    }
}

