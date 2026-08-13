import MapKit
import SwiftUI
import UIKit

struct WorldLifeEvent: Identifiable, Equatable {
    var id: String
    var city: String
    var place: String
    var petName: String
    var petType: PetType
    var activity: String
    var detail: String
    var latitude: Double
    var longitude: Double
    var tintHex: UInt
    var sceneIcon: String
    var focusDistance: CLLocationDistance = 1_800_000

    var coordinate: CLLocationCoordinate2D {
        CLLocationCoordinate2D(latitude: latitude, longitude: longitude)
    }

    var isGenerated: Bool { id.hasPrefix("field-") }
    var tint: Color { Color(hex: tintHex) }
    var uiTint: UIColor { UIColor(hex: tintHex) }

    static func == (lhs: WorldLifeEvent, rhs: WorldLifeEvent) -> Bool {
        lhs.id == rhs.id
    }

    static let samples: [WorldLifeEvent] = [
        WorldLifeEvent(
            id: "paris-cafe",
            city: "巴黎",
            place: "街角咖啡馆",
            petName: "Luna",
            petType: .cat,
            activity: "在街角晒太阳",
            detail: "阳光落在椅背上，TA 把尾巴轻轻绕成一个圈。",
            latitude: 48.8566,
            longitude: 2.3522,
            tintHex: 0xE0A25E,
            sceneIcon: "cup.and.saucer.fill",
            focusDistance: 900_000
        ),
        WorldLifeEvent(
            id: "lisbon-sea",
            city: "里斯本",
            place: "海边长椅",
            petName: "年年",
            petType: .cat,
            activity: "在海边等风",
            detail: "风从很远的地方吹过来，TA 眯着眼睛听了一会儿。",
            latitude: 38.7223,
            longitude: -9.1393,
            tintHex: 0x69B6A5,
            sceneIcon: "sailboat.fill",
            focusDistance: 1_100_000
        ),
        WorldLifeEvent(
            id: "cairo-lamp",
            city: "开罗",
            place: "夜灯下面",
            petName: "米粒",
            petType: .parrot,
            activity: "在看一盏灯",
            detail: "那盏灯亮得很软，TA 歪着头看了好久，轻轻啾了一声。",
            latitude: 30.0444,
            longitude: 31.2357,
            tintHex: 0xD6B05E,
            sceneIcon: "lightbulb.fill",
            focusDistance: 1_000_000
        ),
        WorldLifeEvent(
            id: "dubai-window",
            city: "迪拜",
            place: "玻璃窗边",
            petName: "Lucky",
            petType: .dog,
            activity: "在窗边看云",
            detail: "TA 贴近窗边，认真看着云影从城市上方慢慢走过。",
            latitude: 25.2048,
            longitude: 55.2708,
            tintHex: 0xC6A66A,
            sceneIcon: "cloud.sun.fill",
            focusDistance: 1_000_000
        ),
        WorldLifeEvent(
            id: "tokyo-shop",
            city: "东京",
            place: "一间小食堂",
            petName: "Momo",
            petType: .dog,
            activity: "在小店吃饭",
            detail: "TA 坐在靠窗的小桌边，慢慢吃一小份热乎食物。",
            latitude: 35.6764,
            longitude: 139.6500,
            tintHex: 0xD98566,
            sceneIcon: "takeoutbag.and.cup.and.straw",
            focusDistance: 900_000
        ),
        WorldLifeEvent(
            id: "seoul-book",
            city: "首尔",
            place: "旧书店窗下",
            petName: "豆豆",
            petType: .rabbit,
            activity: "在窗边发呆",
            detail: "TA 抬头看了一会儿橱窗，耳朵轻轻动了一下。",
            latitude: 37.5665,
            longitude: 126.9780,
            tintHex: 0xA8A45F,
            sceneIcon: "book.closed.fill",
            focusDistance: 900_000
        ),
        WorldLifeEvent(
            id: "capetown-park",
            city: "开普敦",
            place: "公园小路",
            petName: "Coco",
            petType: .dog,
            activity: "在追一片叶子",
            detail: "叶子滚了很远，TA 跟着跑了几步，又轻轻停下。",
            latitude: -33.9249,
            longitude: 18.4241,
            tintHex: 0x92B96D,
            sceneIcon: "leaf.fill",
            focusDistance: 1_100_000
        ),
        WorldLifeEvent(
            id: "reykjavik-window",
            city: "雷克雅未克",
            place: "亮着灯的窗边",
            petName: "小宝",
            petType: .hamster,
            activity: "在窗边看雪",
            detail: "窗外很安静，TA 抱着一点暖光，像一封没有寄出的信。",
            latitude: 64.1466,
            longitude: -21.9426,
            tintHex: 0x87B8DA,
            sceneIcon: "snowflake",
            focusDistance: 1_300_000
        ),
        WorldLifeEvent(
            id: "sydney-flower",
            city: "悉尼",
            place: "花店门口",
            petName: "团团",
            petType: .dog,
            activity: "在花店门口停留",
            detail: "TA 好像认出了一种熟悉的味道，停下来多看了一眼。",
            latitude: -33.8688,
            longitude: 151.2093,
            tintHex: 0xDE8DA0,
            sceneIcon: "camera.macro",
            focusDistance: 1_200_000
        ),
        WorldLifeEvent(
            id: "bangkok-rain",
            city: "曼谷",
            place: "雨后的路口",
            petName: "Nori",
            petType: .dog,
            activity: "在踩小水洼",
            detail: "TA 绕着水洼走了一圈，像发现了一个新的小游戏。",
            latitude: 13.7563,
            longitude: 100.5018,
            tintHex: 0x82A9D3,
            sceneIcon: "cloud.rain.fill",
            focusDistance: 950_000
        ),
        WorldLifeEvent(
            id: "newyork-corner",
            city: "纽约",
            place: "路边咖啡车",
            petName: "Sugar",
            petType: .dog,
            activity: "在路边闻咖啡香",
            detail: "TA 没有真的喝，只是认真闻了很久，像以前等你买早餐。",
            latitude: 40.7128,
            longitude: -74.0060,
            tintHex: 0x7AA8CB,
            sceneIcon: "mug.fill",
            focusDistance: 1_000_000
        ),
        WorldLifeEvent(
            id: "vancouver-pier",
            city: "温哥华",
            place: "码头边",
            petName: "橘子",
            petType: .bird,
            activity: "在听海鸥叫",
            detail: "TA 把头转向风来的地方，像在听一首很远的歌。",
            latitude: 49.2827,
            longitude: -123.1207,
            tintHex: 0x78B7C5,
            sceneIcon: "water.waves",
            focusDistance: 1_100_000
        ),
        WorldLifeEvent(
            id: "buenosaires-market",
            city: "布宜诺斯艾利斯",
            place: "集市入口",
            petName: "小满",
            petType: .dog,
            activity: "在闻面包香",
            detail: "TA 停在摊位旁边，鼻尖轻轻动了一下。",
            latitude: -34.6037,
            longitude: -58.3816,
            tintHex: 0xD99A62,
            sceneIcon: "basket.fill",
            focusDistance: 1_200_000
        )
    ]
}

enum WorldAnimalField {
    enum Habitat: Int {
        case cafe
        case food
        case coast
        case pier
        case park
        case shop
        case window
        case market
        case rain
        case snow
        case boat
        case garden
    }

    struct Story {
        var activity: String
        var detail: String
        var icon: String
        var tintHex: UInt
    }

    struct Anchor {
        var id: String
        var city: String
        var place: String
        var latitude: Double
        var longitude: Double
        var habitat: Habitat

        var coordinate: CLLocationCoordinate2D {
            CLLocationCoordinate2D(latitude: latitude, longitude: longitude)
        }
    }

    static let petNames = [
        "Momo", "Luna", "年年", "小宝", "团团", "Sugar", "豆豆", "Nori", "米粒", "Coco", "橘子", "Lucky"
    ]

    static let anchors: [Anchor] = [
        Anchor(id: "paris-cafe", city: "巴黎", place: "街角咖啡馆", latitude: 48.8566, longitude: 2.3522, habitat: .cafe),
        Anchor(id: "lisbon-pier", city: "里斯本", place: "海边长椅", latitude: 38.7223, longitude: -9.1393, habitat: .coast),
        Anchor(id: "cairo-lamp", city: "开罗", place: "夜灯下面", latitude: 30.0444, longitude: 31.2357, habitat: .window),
        Anchor(id: "dubai-window", city: "迪拜", place: "玻璃窗边", latitude: 25.2048, longitude: 55.2708, habitat: .window),
        Anchor(id: "tokyo-shop", city: "东京", place: "一间小食堂", latitude: 35.6764, longitude: 139.6500, habitat: .food),
        Anchor(id: "seoul-book", city: "首尔", place: "旧书店窗下", latitude: 37.5665, longitude: 126.9780, habitat: .shop),
        Anchor(id: "capetown-park", city: "开普敦", place: "公园小路", latitude: -33.9249, longitude: 18.4241, habitat: .park),
        Anchor(id: "reykjavik-window", city: "雷克雅未克", place: "亮着灯的窗边", latitude: 64.1466, longitude: -21.9426, habitat: .snow),
        Anchor(id: "sydney-flower", city: "悉尼", place: "花店门口", latitude: -33.8688, longitude: 151.2093, habitat: .shop),
        Anchor(id: "bangkok-rain", city: "曼谷", place: "雨后的路口", latitude: 13.7563, longitude: 100.5018, habitat: .rain),
        Anchor(id: "newyork-cart", city: "纽约", place: "路边咖啡车", latitude: 40.7128, longitude: -74.0060, habitat: .cafe),
        Anchor(id: "vancouver-pier", city: "温哥华", place: "码头边", latitude: 49.2827, longitude: -123.1207, habitat: .pier),
        Anchor(id: "buenosaires-market", city: "布宜诺斯艾利斯", place: "集市入口", latitude: -34.6037, longitude: -58.3816, habitat: .market),
        Anchor(id: "london-park", city: "伦敦", place: "公园草地", latitude: 51.5072, longitude: -0.1276, habitat: .park),
        Anchor(id: "amsterdam-canal", city: "阿姆斯特丹", place: "运河边", latitude: 52.3676, longitude: 4.9041, habitat: .coast),
        Anchor(id: "copenhagen-harbor", city: "哥本哈根", place: "港口木栈道", latitude: 55.6761, longitude: 12.5683, habitat: .pier),
        Anchor(id: "istanbul-ferry", city: "伊斯坦布尔", place: "渡船甲板", latitude: 41.0082, longitude: 28.9784, habitat: .boat),
        Anchor(id: "athens-alley", city: "雅典", place: "白墙小巷", latitude: 37.9838, longitude: 23.7275, habitat: .cafe),
        Anchor(id: "rome-fountain", city: "罗马", place: "喷泉旁边", latitude: 41.9028, longitude: 12.4964, habitat: .garden),
        Anchor(id: "barcelona-beach", city: "巴塞罗那", place: "海边步道", latitude: 41.3851, longitude: 2.1734, habitat: .coast),
        Anchor(id: "marrakesh-market", city: "马拉喀什", place: "香料集市", latitude: 31.6295, longitude: -7.9811, habitat: .market),
        Anchor(id: "nairobi-park", city: "内罗毕", place: "树荫路边", latitude: -1.2921, longitude: 36.8219, habitat: .park),
        Anchor(id: "lagos-cafe", city: "拉各斯", place: "街边小店", latitude: 6.5244, longitude: 3.3792, habitat: .food),
        Anchor(id: "rio-beach", city: "里约", place: "海边台阶", latitude: -22.9068, longitude: -43.1729, habitat: .coast),
        Anchor(id: "mexico-park", city: "墨西哥城", place: "树下长椅", latitude: 19.4326, longitude: -99.1332, habitat: .park),
        Anchor(id: "sanfrancisco-pier", city: "旧金山", place: "码头木板路", latitude: 37.7749, longitude: -122.4194, habitat: .pier),
        Anchor(id: "seattle-book", city: "西雅图", place: "旧书店门口", latitude: 47.6062, longitude: -122.3321, habitat: .shop),
        Anchor(id: "toronto-garden", city: "多伦多", place: "湖边花园", latitude: 43.6532, longitude: -79.3832, habitat: .garden),
        Anchor(id: "miami-coast", city: "迈阿密", place: "海边小路", latitude: 25.7617, longitude: -80.1918, habitat: .coast),
        Anchor(id: "anchorage-snow", city: "安克雷奇", place: "雪后的窗边", latitude: 61.2176, longitude: -149.8997, habitat: .snow),
        Anchor(id: "honolulu-shore", city: "檀香山", place: "海边树影下", latitude: 21.3099, longitude: -157.8581, habitat: .coast),
        Anchor(id: "singapore-garden", city: "新加坡", place: "花园步道", latitude: 1.3521, longitude: 103.8198, habitat: .garden),
        Anchor(id: "hongkong-ferry", city: "香港", place: "渡轮窗边", latitude: 22.3193, longitude: 114.1694, habitat: .boat),
        Anchor(id: "taipei-night", city: "台北", place: "夜市巷口", latitude: 25.0330, longitude: 121.5654, habitat: .market),
        Anchor(id: "shanghai-river", city: "上海", place: "河边步道", latitude: 31.2304, longitude: 121.4737, habitat: .coast),
        Anchor(id: "beijing-hutong", city: "北京", place: "胡同门口", latitude: 39.9042, longitude: 116.4074, habitat: .cafe),
        Anchor(id: "mumbai-stall", city: "孟买", place: "小吃摊旁", latitude: 19.0760, longitude: 72.8777, habitat: .food),
        Anchor(id: "delhi-garden", city: "德里", place: "花园阴影里", latitude: 28.6139, longitude: 77.2090, habitat: .garden),
        Anchor(id: "hanoi-cafe", city: "河内", place: "窄巷咖啡店", latitude: 21.0278, longitude: 105.8342, habitat: .cafe),
        Anchor(id: "jakarta-rain", city: "雅加达", place: "雨后街边", latitude: -6.2088, longitude: 106.8456, habitat: .rain),
        Anchor(id: "bali-shore", city: "巴厘岛", place: "海边台阶", latitude: -8.4095, longitude: 115.1889, habitat: .coast),
        Anchor(id: "manila-bay", city: "马尼拉", place: "海湾栏杆边", latitude: 14.5995, longitude: 120.9842, habitat: .pier),
        Anchor(id: "auckland-pier", city: "奥克兰", place: "码头边", latitude: -36.8509, longitude: 174.7645, habitat: .pier),
        Anchor(id: "oslo-snow", city: "奥斯陆", place: "雪地电车站", latitude: 59.9139, longitude: 10.7522, habitat: .snow),
        Anchor(id: "stockholm-window", city: "斯德哥尔摩", place: "亮灯窗边", latitude: 59.3293, longitude: 18.0686, habitat: .window),
        Anchor(id: "helsinki-harbor", city: "赫尔辛基", place: "港口台阶", latitude: 60.1699, longitude: 24.9384, habitat: .pier),
        Anchor(id: "aegean-ferry", city: "爱琴海", place: "渡船甲板", latitude: 37.7200, longitude: 24.1600, habitat: .boat),
        Anchor(id: "baltic-ferry", city: "波罗的海", place: "船舷旁边", latitude: 59.4800, longitude: 19.1200, habitat: .boat)
    ]

    static func events(for mapView: MKMapView) -> [WorldLifeEvent] {
        let distance = mapView.camera.centerCoordinateDistance
        let tier = zoomTier(for: distance)
        let desiredCount = desiredEventCount(for: distance)
        let visibleAnchors = anchors.filter { contains($0.coordinate, in: mapView.visibleMapRect) }
        let primaryEvents = rankedEvents(from: visibleAnchors, mapView: mapView, tier: tier)
        let companionEvents = companionEvents(
            around: visibleAnchors,
            mapView: mapView,
            tier: tier,
            targetCount: desiredCount - primaryEvents.count
        )

        var events = primaryEvents
        events.append(contentsOf: companionEvents)

        var seen = Set<String>()
        return events
            .filter { seen.insert($0.id).inserted }
            .prefix(desiredCount)
            .map { $0 }
    }

    static func rankedEvents(from anchors: [Anchor], mapView: MKMapView, tier: Int) -> [WorldLifeEvent] {
        let center = MKMapPoint(mapView.centerCoordinate)
        let distanceWeight = tier == 1 ? 0.16 : 0.72

        return anchors
            .map { anchor in
                let point = MKMapPoint(anchor.coordinate)
                let mapDistance = hypot(point.x - center.x, point.y - center.y) / MKMapRect.world.size.width
                let seed = seed(for: anchor)
                let score = mapDistance * distanceWeight + unit(seed, salt: UInt64(tier)) * (1 - distanceWeight)
                return (event: event(from: anchor, idSuffix: nil, coordinate: anchor.coordinate, tier: tier), score: score)
            }
            .sorted { $0.score < $1.score }
            .map(\.event)
    }

    static func companionEvents(
        around anchors: [Anchor],
        mapView: MKMapView,
        tier: Int,
        targetCount: Int
    ) -> [WorldLifeEvent] {
        guard tier >= 3, targetCount > 0 else { return [] }

        let companionCount = tier >= 4 ? 4 : 2
        var events: [WorldLifeEvent] = []

        for anchor in anchors {
            let seed = seed(for: anchor)
            let spread = companionSpread(for: anchor.habitat, tier: tier)
            for index in 0..<companionCount {
                let angle = unit(seed, salt: UInt64(20 + index)) * Double.pi * 2
                let radius = spread * (0.35 + unit(seed, salt: UInt64(40 + index)) * 0.65)
                let latitude = clamp(anchor.latitude + sin(angle) * radius, min: -72, max: 72)
                let longitude = normalizedLongitude(anchor.longitude + cos(angle) * radius)
                let coordinate = CLLocationCoordinate2D(latitude: latitude, longitude: longitude)

                guard contains(coordinate, in: mapView.visibleMapRect) else { continue }

                events.append(
                    event(
                        from: anchor,
                        idSuffix: "near-\(index)",
                        coordinate: coordinate,
                        tier: tier,
                        storySalt: UInt64(index + 3)
                    )
                )
            }
        }

        return events
            .sorted { $0.id < $1.id }
            .prefix(targetCount)
            .map { $0 }
    }

    static func companionSpread(for habitat: Habitat, tier: Int) -> Double {
        switch habitat {
        case .boat:
            return tier >= 4 ? 0.014 : 0.026
        case .pier, .coast:
            return tier >= 4 ? 0.006 : 0.012
        default:
            return tier >= 4 ? 0.004 : 0.009
        }
    }

    static func event(
        from anchor: Anchor,
        idSuffix: String?,
        coordinate: CLLocationCoordinate2D,
        tier: Int,
        storySalt: UInt64 = 0
    ) -> WorldLifeEvent {
        let seed = seed(for: anchor) &+ storySalt
        let storyPool = stories(for: anchor.habitat)
        let story = storyPool[Int(seed % UInt64(storyPool.count))]
        let petName = petNames[Int((seed >> 8) % UInt64(petNames.count))]
        let visiblePetTypes: [PetType] = [.dog, .cat, .parrot, .rabbit, .hamster, .bird]
        let petType = visiblePetTypes[Int((seed >> 12) % UInt64(visiblePetTypes.count))]
        let suffix = idSuffix.map { "-\($0)" } ?? ""

        return WorldLifeEvent(
            id: "anchor-\(anchor.id)\(suffix)",
            city: anchor.city,
            place: anchor.place,
            petName: petName,
            petType: petType,
            activity: story.activity,
            detail: story.detail,
            latitude: coordinate.latitude,
            longitude: coordinate.longitude,
            tintHex: story.tintHex,
            sceneIcon: story.icon,
            focusDistance: focusDistance(for: tier)
        )
    }

    static func stories(for habitat: Habitat) -> [Story] {
        switch habitat {
        case .cafe:
            return [
                Story(activity: "在窗边晒太阳", detail: "TA 找到一块很暖的位置，安静地趴了一会儿。", icon: "cup.and.saucer.fill", tintHex: 0xD7A067),
                Story(activity: "在喝招牌饮品", detail: "TA 坐在靠窗的小桌边，慢慢看街上的人经过。", icon: "mug.fill", tintHex: 0xC8956D)
            ]
        case .food:
            return [
                Story(activity: "在吃一小份饭", detail: "TA 没有着急，慢慢吃完一小份适合自己的食物。", icon: "takeoutbag.and.cup.and.straw", tintHex: 0x78A99D),
                Story(activity: "在小店里坐着", detail: "店里传来热乎乎的声音，TA 把耳朵轻轻转了过去。", icon: "fork.knife", tintHex: 0xD98566)
            ]
        case .coast:
            return [
                Story(activity: "在岸边等风", detail: "风从水面吹过来，TA 像听见了很熟悉的声音。", icon: "wind", tintHex: 0x8FB7D0),
                Story(activity: "在海边看浪", detail: "浪花一层一层靠近，TA 安静地坐在栏杆旁边。", icon: "water.waves", tintHex: 0x78B7C5)
            ]
        case .pier:
            return [
                Story(activity: "在码头边听水声", detail: "木板下面传来轻轻的水声，TA 低头看了很久。", icon: "sailboat.fill", tintHex: 0x78B7C5),
                Story(activity: "在栏杆旁看船", detail: "远处有船慢慢经过，TA 的尾巴轻轻晃了一下。", icon: "sailboat.fill", tintHex: 0x6FAFC1)
            ]
        case .boat:
            return [
                Story(activity: "在渡船甲板上吹风", detail: "水面很亮，TA 站在风里，好像正在去一个温柔的地方。", icon: "sailboat.fill", tintHex: 0x6FAFC1),
                Story(activity: "在船舷边看浪", detail: "船慢慢往前走，TA 看着浪花一朵一朵散开。", icon: "sailboat.fill", tintHex: 0x7AA8CB)
            ]
        case .park:
            return [
                Story(activity: "在追一片叶子", detail: "叶子滚了很远，TA 跟着跑了几步，又轻轻停下。", icon: "leaf.fill", tintHex: 0x90B779),
                Story(activity: "在树荫下休息", detail: "树影慢慢移动，TA 把爪子收起来睡了一小会儿。", icon: "tree.fill", tintHex: 0x7FAE74)
            ]
        case .shop:
            return [
                Story(activity: "在小店里挑东西", detail: "TA 好像认出了一种熟悉的小物件，停下来多看了一眼。", icon: "camera.macro", tintHex: 0xD49A9A),
                Story(activity: "在窗边发呆", detail: "TA 抬头看了一会儿橱窗，像在等一封慢慢到来的信。", icon: "book.closed.fill", tintHex: 0xB9A06F)
            ]
        case .window:
            return [
                Story(activity: "在看一盏灯", detail: "那盏灯亮得很软，TA 坐在那里看了好久。", icon: "lightbulb.fill", tintHex: 0xC6B083),
                Story(activity: "在窗边看云", detail: "TA 贴近窗边，认真看着云影从城市上方慢慢走过。", icon: "cloud.sun.fill", tintHex: 0xC6A66A)
            ]
        case .market:
            return [
                Story(activity: "在闻面包香", detail: "TA 停在摊位旁边，鼻尖轻轻动了一下。", icon: "basket.fill", tintHex: 0xD99A62),
                Story(activity: "在集市入口张望", detail: "人声从远处传来，TA 安静地站在不挡路的地方。", icon: "bag.fill", tintHex: 0xC89A68)
            ]
        case .rain:
            return [
                Story(activity: "在踩小水洼", detail: "TA 绕着水洼走了一圈，像发现了一个新的小游戏。", icon: "cloud.rain.fill", tintHex: 0x8FAAC6),
                Story(activity: "在雨棚下等雨停", detail: "雨声落在屋檐上，TA 把身体缩得很小。", icon: "umbrella.fill", tintHex: 0x82A9D3)
            ]
        case .snow:
            return [
                Story(activity: "在窗边看雪", detail: "窗外很安静，TA 把爪子收起来，像一封没有寄出的信。", icon: "snowflake", tintHex: 0x87B8DA),
                Story(activity: "在雪后的小路上走", detail: "TA 每一步都很轻，好像怕踩碎这片安静。", icon: "snowflake", tintHex: 0x91B9D2)
            ]
        case .garden:
            return [
                Story(activity: "在闻一束花", detail: "TA 在门边停了一下，像是认出了某种温柔的味道。", icon: "camera.macro", tintHex: 0xD49A9A),
                Story(activity: "在花园里慢慢走", detail: "草叶碰到脚边，TA 像在记住这条小路。", icon: "leaf.fill", tintHex: 0x90B779)
            ]
        }
    }

    static func contains(_ coordinate: CLLocationCoordinate2D, in mapRect: MKMapRect) -> Bool {
        let point = MKMapPoint(coordinate)
        let worldWidth = MKMapRect.world.size.width

        return [-worldWidth, 0, worldWidth].contains { offset in
            let x = point.x + offset
            return x >= mapRect.minX
                && x <= mapRect.maxX
                && point.y >= mapRect.minY
                && point.y <= mapRect.maxY
        }
    }

    static func desiredEventCount(for distance: CLLocationDistance) -> Int {
        switch distance {
        case 72_000_000...: return 4
        case 28_000_000...: return 4
        case 8_000_000...: return 9
        case 2_200_000...: return 16
        default: return 22
        }
    }

    static func zoomTier(for distance: CLLocationDistance) -> Int {
        switch distance {
        case 28_000_000...: return 1
        case 8_000_000...: return 2
        case 2_200_000...: return 3
        default: return 4
        }
    }

    static func focusDistance(for tier: Int) -> CLLocationDistance {
        switch tier {
        case 1: return 3_200_000
        case 2: return 1_300_000
        case 3: return 520_000
        default: return 180_000
        }
    }

    static func stableSeed(_ latKey: Int, _ lonKey: Int, _ tier: Int) -> UInt64 {
        var value = UInt64(bitPattern: Int64(latKey &* 73_856_093))
        let lonValue = UInt64(bitPattern: Int64(lonKey &* 19_349_663))
        value ^= (lonValue << 17) | (lonValue >> 47)
        value ^= UInt64(tier &* 83_492_791)
        value &+= 0x9E3779B97F4A7C15
        value ^= value >> 30
        value &*= 0xBF58476D1CE4E5B9
        value ^= value >> 27
        value &*= 0x94D049BB133111EB
        value ^= value >> 31
        return value
    }

    static func seed(for anchor: Anchor) -> UInt64 {
        stableSeed(
            Int((anchor.latitude * 1_000).rounded()),
            Int((anchor.longitude * 1_000).rounded()),
            anchor.habitat.rawValue + 1
        )
    }

    static func unit(_ seed: UInt64, salt: UInt64) -> Double {
        let mixed = stableSeed(Int(seed & 0xFFFF), Int((seed >> 16) & 0xFFFF), Int(salt))
        return Double(mixed % 10_000) / 10_000
    }

    static func normalizedLongitude(_ longitude: Double) -> Double {
        var value = longitude
        while value > 180 { value -= 360 }
        while value < -180 { value += 360 }
        return value
    }

    static func clamp(_ value: Double, min: Double, max: Double) -> Double {
        Swift.min(Swift.max(value, min), max)
    }
}

final class WorldLifeAnnotation: NSObject, MKAnnotation {
    let event: WorldLifeEvent
    var coordinate: CLLocationCoordinate2D { event.coordinate }
    var title: String? { event.city }
    var subtitle: String? { event.activity }

    init(event: WorldLifeEvent) {
        self.event = event
        super.init()
    }
}

extension UIColor {
    convenience init(hex: UInt, alpha: CGFloat = 1) {
        self.init(
            red: CGFloat((hex >> 16) & 0xFF) / 255,
            green: CGFloat((hex >> 8) & 0xFF) / 255,
            blue: CGFloat(hex & 0xFF) / 255,
            alpha: alpha
        )
    }
}
