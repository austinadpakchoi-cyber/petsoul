import CoreLocation
import Foundation

struct WorldCupHostCity: Identifiable, Hashable, Sendable {
    var id: String
    var city: String
    var region: String
    var country: String
    var stadiumName: String
    var latitude: Double
    var longitude: Double
    var atmosphereHint: String

    var coordinate: CLLocationCoordinate2D {
        CLLocationCoordinate2D(latitude: latitude, longitude: longitude)
    }

    var displayName: String {
        "\(city) · \(stadiumName)"
    }

    var questDestination: String {
        "\(country) · \(city)"
    }

    var shortLocation: String {
        "\(country) · \(city)"
    }

    static let recommended = hostCities.first { $0.id == "los-angeles" } ?? hostCities[0]

    static let hostCities: [WorldCupHostCity] = [
        WorldCupHostCity(
            id: "vancouver",
            city: "温哥华",
            region: "Canada",
            country: "加拿大",
            stadiumName: "BC Place",
            latitude: 49.2767,
            longitude: -123.1119,
            atmosphereHint: "海风、山影和球场灯"
        ),
        WorldCupHostCity(
            id: "toronto",
            city: "多伦多",
            region: "Canada",
            country: "加拿大",
            stadiumName: "BMO Field",
            latitude: 43.6328,
            longitude: -79.4186,
            atmosphereHint: "湖边风和红色围巾"
        ),
        WorldCupHostCity(
            id: "seattle",
            city: "西雅图",
            region: "United States",
            country: "美国",
            stadiumName: "Lumen Field",
            latitude: 47.5952,
            longitude: -122.3316,
            atmosphereHint: "港口、雨后街道和低低欢呼"
        ),
        WorldCupHostCity(
            id: "san-francisco-bay",
            city: "旧金山湾区",
            region: "United States",
            country: "美国",
            stadiumName: "Levi's Stadium",
            latitude: 37.4032,
            longitude: -121.9698,
            atmosphereHint: "湾区傍晚和球迷广场"
        ),
        WorldCupHostCity(
            id: "los-angeles",
            city: "洛杉矶",
            region: "United States",
            country: "美国",
            stadiumName: "SoFi Stadium",
            latitude: 33.9535,
            longitude: -118.3392,
            atmosphereHint: "很亮的夜、棕榈树和远方球场"
        ),
        WorldCupHostCity(
            id: "guadalajara",
            city: "瓜达拉哈拉",
            region: "Mexico",
            country: "墨西哥",
            stadiumName: "Estadio Akron",
            latitude: 20.6819,
            longitude: -103.4621,
            atmosphereHint: "暖色街道和小旗子"
        ),
        WorldCupHostCity(
            id: "mexico-city",
            city: "墨西哥城",
            region: "Mexico",
            country: "墨西哥",
            stadiumName: "Estadio Azteca",
            latitude: 19.3029,
            longitude: -99.1505,
            atmosphereHint: "高处城市、古老球场和人群声"
        ),
        WorldCupHostCity(
            id: "monterrey",
            city: "蒙特雷",
            region: "Mexico",
            country: "墨西哥",
            stadiumName: "Estadio BBVA",
            latitude: 25.6687,
            longitude: -100.2447,
            atmosphereHint: "山影和热闹入口"
        ),
        WorldCupHostCity(
            id: "houston",
            city: "休斯敦",
            region: "United States",
            country: "美国",
            stadiumName: "NRG Stadium",
            latitude: 29.6847,
            longitude: -95.4107,
            atmosphereHint: "热空气、车灯和球迷广场"
        ),
        WorldCupHostCity(
            id: "dallas",
            city: "达拉斯",
            region: "United States",
            country: "美国",
            stadiumName: "AT&T Stadium",
            latitude: 32.7473,
            longitude: -97.0945,
            atmosphereHint: "宽阔公路和银色球场"
        ),
        WorldCupHostCity(
            id: "kansas-city",
            city: "堪萨斯城",
            region: "United States",
            country: "美国",
            stadiumName: "Arrowhead Stadium",
            latitude: 39.049,
            longitude: -94.4839,
            atmosphereHint: "红色人潮和长长尾声"
        ),
        WorldCupHostCity(
            id: "atlanta",
            city: "亚特兰大",
            region: "United States",
            country: "美国",
            stadiumName: "Mercedes-Benz Stadium",
            latitude: 33.7554,
            longitude: -84.4008,
            atmosphereHint: "城市灯光和室内球场声"
        ),
        WorldCupHostCity(
            id: "miami",
            city: "迈阿密",
            region: "United States",
            country: "美国",
            stadiumName: "Hard Rock Stadium",
            latitude: 25.958,
            longitude: -80.2389,
            atmosphereHint: "热带夜风和颜色很亮的人群"
        ),
        WorldCupHostCity(
            id: "philadelphia",
            city: "费城",
            region: "United States",
            country: "美国",
            stadiumName: "Lincoln Financial Field",
            latitude: 39.9008,
            longitude: -75.1675,
            atmosphereHint: "老城故事和赛前灯光"
        ),
        WorldCupHostCity(
            id: "new-york-new-jersey",
            city: "纽约新泽西",
            region: "United States",
            country: "美国",
            stadiumName: "MetLife Stadium",
            latitude: 40.8135,
            longitude: -74.0745,
            atmosphereHint: "很大的城市风和远处看台"
        ),
        WorldCupHostCity(
            id: "boston",
            city: "波士顿",
            region: "United States",
            country: "美国",
            stadiumName: "Gillette Stadium",
            latitude: 42.0909,
            longitude: -71.2643,
            atmosphereHint: "郊外球场和清凉空气"
        )
    ]
}

enum WorldCupBagItem: String, CaseIterable, Identifiable, Hashable, Sendable {
    case scarf
    case snack
    case cameraCharm
    case footballBadge
    case smallFlag

    var id: String { rawValue }

    var title: String {
        switch self {
        case .scarf: "小围巾"
        case .snack: "小零食"
        case .cameraCharm: "拍照小挂件"
        case .footballBadge: "小足球徽章"
        case .smallFlag: "小旗子"
        }
    }

    var systemImage: String {
        switch self {
        case .scarf: "scarf.fill"
        case .snack: "takeoutbag.and.cup.and.straw.fill"
        case .cameraCharm: "camera.fill"
        case .footballBadge: "seal.fill"
        case .smallFlag: "flag.fill"
        }
    }

    var sortOrder: Int {
        switch self {
        case .scarf: 0
        case .snack: 1
        case .cameraCharm: 2
        case .footballBadge: 3
        case .smallFlag: 4
        }
    }

    var travelBagInput: TravelBagItemInput {
        switch self {
        case .scarf:
            TravelBagItemInput(
                itemType: .comfortItem,
                title: "小围巾",
                note: "去远方球场时可以轻轻搭在小包边上。",
                influenceTags: ["worldcup", "scarf", "warmth"]
            )
        case .snack:
            TravelBagItemInput(
                itemType: .snack,
                title: "长途小零食",
                note: "路很远，先放一点不会太甜的小零食。",
                influenceTags: ["worldcup", "energy", "long_trip"]
            )
        case .cameraCharm:
            TravelBagItemInput(
                itemType: .luckyCharm,
                title: "拍照小挂件",
                note: "看到球场灯光时，提醒 TA 拍给你看。",
                influenceTags: ["worldcup", "photo", "current_status"]
            )
        case .footballBadge:
            TravelBagItemInput(
                itemType: .luckyCharm,
                title: "小足球徽章",
                note: "这不是球票，只是一枚远方邀请的标记。",
                influenceTags: ["worldcup", "invitation", "paw_pass"]
            )
        case .smallFlag:
            TravelBagItemInput(
                itemType: .toy,
                title: "小旗子",
                note: "到了球迷广场，可以跟着风轻轻晃一下。",
                influenceTags: ["worldcup", "fan_zone", "color"]
            )
        }
    }
}

