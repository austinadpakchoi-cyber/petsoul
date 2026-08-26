import AuthenticationServices
import MapKit
import SwiftUI
import UIKit

extension Date {
    /// 当天分钟数（0-1439）：多个视图的时间相位判定共用，避免重复计算。
    var petSoulMinuteOfDay: Int {
        let calendar = Calendar.current
        return calendar.component(.hour, from: self) * 60 + calendar.component(.minute, from: self)
    }
}

enum JourneyMapEventPhase: Equatable {
    case past
    case current
    case upcoming

    var title: String {
        switch self {
        case .past: "已完成"
        case .current: "正在发生"
        case .upcoming: "计划中"
        }
    }

    var detailPrefix: String {
        switch self {
        case .past: "记录"
        case .current: "此刻"
        case .upcoming: "计划"
        }
    }

    var cardHeading: String {
        switch self {
        case .past: "这一天的记录"
        case .current: "此刻正在发生"
        case .upcoming: "下一段计划"
        }
    }

    func detailText(for detail: String) -> String {
        switch self {
        case .past:
            return "记录：\(detail)"
        case .current:
            return "正在发生：\(detail)"
        case .upcoming:
            return "计划：\(detail)"
        }
    }

    var opacity: Double {
        switch self {
        case .past: 0.52
        case .current: 1.0
        case .upcoming: 0.72
        }
    }
}

struct JourneyMapEvent: Identifiable, Equatable {
    var id: String
    var title: String
    var place: String
    var detail: String
    var dateLabel: String
    var timeLabel: String
    var phase: JourneyMapEventPhase
    var coordinate: CLLocationCoordinate2D
    var systemImage: String
    var tint: Color

    static func == (lhs: JourneyMapEvent, rhs: JourneyMapEvent) -> Bool {
        lhs.id == rhs.id
    }

    var fullTimeLabel: String {
        "\(dateLabel) \(timeLabel)"
    }

    var shortPlaceName: String {
        let value = place.components(separatedBy: " · ").last?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        return value.isEmpty ? place : value
    }

    static func events(
        around coordinate: CLLocationCoordinate2D,
        status: AgentStatus,
        dayPlan: DayPlan?,
        remoteRoutePlan: RemoteJourneyRoutePlan?
    ) -> [JourneyMapEvent] {
        let items = dayPlan?.items ?? fallbackItems(for: status)
        guard !items.isEmpty else { return [] }
        let dateLabel = currentDateLabel()
        if let places = remoteRoutePlan?.places, !places.isEmpty {
            let displayCount = min(places.count, max(items.count, 5))
            return Array(places.prefix(displayCount)).enumerated().map { index, place in
                let item = items[index % items.count]
                let style = style(for: place.category)
                return JourneyMapEvent(
                    id: place.id,
                    title: place.activityHint,
                    place: "\(place.city) · \(place.name)",
                    detail: "\(place.detailHint) \(item.detail)",
                    dateLabel: dateLabel,
                    timeLabel: item.time,
                    phase: phase(for: items, index: index),
                    coordinate: place.coordinate,
                    systemImage: style.systemImage,
                    tint: style.tint
                )
            }
        }

        let stops = MerchantStop.stops(for: status.agentState.location, around: coordinate)

        return stops.enumerated().map { index, stop in
            let item = items[index % items.count]
            return JourneyMapEvent(
                id: "\(item.id)-\(index)",
                title: stop.activity,
                place: "\(status.agentState.location) · \(stop.place)",
                detail: "\(stop.guide) \(item.detail)",
                dateLabel: dateLabel,
                timeLabel: item.time,
                phase: phase(for: items, index: index),
                coordinate: stop.coordinate,
                systemImage: stop.systemImage,
                tint: stop.tint
            )
        }
    }

    func displayPhase(liveEvent: JourneyMapEvent?) -> JourneyMapEventPhase {
        liveEvent?.id == id ? .current : phase
    }

    static func phase(for items: [DayPlanItem], index: Int, now: Date = Date()) -> JourneyMapEventPhase {
        guard let start = minuteOfDay(from: time(in: items, at: index)) else {
            return .upcoming
        }
        let current = now.petSoulMinuteOfDay
        if current < start {
            return .upcoming
        }
        if let nextStart = minuteOfDay(from: time(in: items, at: index + 1)) {
            return current < nextStart ? .current : .past
        }
        return current < min(start + 120, 1_320) ? .current : .past
    }

    static func minuteOfDay(from time: String?) -> Int? {
        guard let time else { return nil }
        let parts = time.split(separator: ":")
        guard parts.count == 2, let hour = Int(parts[0]), let minute = Int(parts[1]) else { return nil }
        return hour * 60 + minute
    }

    static func time(in items: [DayPlanItem], at index: Int) -> String? {
        guard items.indices.contains(index) else { return nil }
        return items[index].time
    }

    static func currentDateLabel(now: Date = Date()) -> String {
        now.formatted(.dateTime.month().day())
    }

    static func fallbackItems(for status: AgentStatus) -> [DayPlanItem] {
        [
            DayPlanItem(id: "morning", time: "08:30", title: "在有光的地方醒来", detail: "TA 慢慢伸展了一下，像是在确认今天要往哪里走。", kind: .morning),
            DayPlanItem(id: "noon", time: "12:10", title: "进一间小店坐下", detail: "TA 看了看店里的招牌，选了一个闻起来最有当地味道的位置。", kind: .noon),
            DayPlanItem(id: "afternoon", time: "16:20", title: "把今天的一幕存下来", detail: "TA 在通讯器里留下一点轻轻的想法。", kind: .afternoon),
            DayPlanItem(id: "evening", time: "20:40", title: "找一处安静地方休息", detail: "TA 没有被安排，只是自己选了一个舒服的位置。", kind: .evening)
        ]
    }

    static func style(for category: String) -> (systemImage: String, tint: Color) {
        switch category {
        case "food":
            ("fork.knife", DesignTokens.amber)
        case "cafe":
            ("cup.and.saucer.fill", DesignTokens.sage)
        case "shop":
            ("basket.fill", DesignTokens.amber)
        case "netcafe":
            ("desktopcomputer", DesignTokens.dusk)
        case "flower":
            ("camera.macro", DesignTokens.clay)
        default:
            ("mappin.and.ellipse", DesignTokens.sage)
        }
    }

}

struct MerchantStop {
    var place: String
    var activity: String
    var guide: String
    var coordinate: CLLocationCoordinate2D
    var systemImage: String
    var tint: Color

    static func stops(for city: String, around coordinate: CLLocationCoordinate2D) -> [MerchantStop] {
        if let stops = safeStops[city] {
            return stops
        }

        let fallback: [(String, String, String, CoordinateOffset, String, Color)] = [
            ("街角小食铺", "在街角小食铺点了店里的招牌小吃", "TA 走进店里坐下，边听周围人说话边慢慢吃。", CoordinateOffset(latitude: 0.0012, longitude: -0.0010), "fork.knife", DesignTokens.amber),
            ("咖啡窗口", "在咖啡窗口旁喝了一杯招牌饮品", "TA 选了靠窗的小桌，把这段路记进通讯器。", CoordinateOffset(latitude: -0.0008, longitude: 0.0014), "cup.and.saucer.fill", DesignTokens.sage),
            ("便利店", "在便利店里挑了一个小补给", "灯光稳定、声音熟悉，适合走走停停。", CoordinateOffset(latitude: 0.0015, longitude: 0.0010), "basket.fill", DesignTokens.amber),
            ("安静网吧", "在网吧角落待了一会儿", "这是 TA 自己选择的室内停留点。", CoordinateOffset(latitude: -0.0013, longitude: -0.0015), "desktopcomputer", DesignTokens.dusk),
            ("花店橱窗", "在花店前停住，看了很久的叶子", "街面安静、气味柔和，适合作为中途停留。", CoordinateOffset(latitude: 0.0005, longitude: -0.0017), "camera.macro", DesignTokens.clay)
        ]

        return fallback.map { place, activity, guide, offset, systemImage, tint in
            MerchantStop(
                place: place,
                activity: activity,
                guide: guide,
                coordinate: CLLocationCoordinate2D(
                    latitude: coordinate.latitude + offset.latitude,
                    longitude: coordinate.longitude + offset.longitude
                ),
                systemImage: systemImage,
                tint: tint
            )
        }
    }

    static let safeStops: [String: [MerchantStop]] = [
        "厦门": [
            MerchantStop(place: "沙坡尾小食铺", activity: "在沙坡尾小食铺里点了店里的招牌热食", guide: "TA 走进岸边巷子里的小店，坐下来听了一会儿海风和人声。", coordinate: CLLocationCoordinate2D(latitude: 24.4386, longitude: 118.0930), systemImage: "fork.knife", tint: DesignTokens.amber),
            MerchantStop(place: "中山路咖啡窗口", activity: "在中山路咖啡窗口旁边坐下喝招牌咖啡", guide: "人流稳定、店面密集，TA 可以从这里发回一张第一人称照片。", coordinate: CLLocationCoordinate2D(latitude: 24.4570, longitude: 118.0806), systemImage: "cup.and.saucer.fill", tint: DesignTokens.sage),
            MerchantStop(place: "思明便利店", activity: "在便利店里挑了一个小小的补给品", guide: "灯光稳定、声音熟悉，是很像本地生活的停留点。", coordinate: CLLocationCoordinate2D(latitude: 24.4668, longitude: 118.1047), systemImage: "basket.fill", tint: DesignTokens.amber),
            MerchantStop(place: "软件园安静网吧", activity: "在网吧角落待了一会儿", guide: "这是城市生活点，不是景点；适合生成屏幕光和陪伴感的自拍。", coordinate: CLLocationCoordinate2D(latitude: 24.4897, longitude: 118.1845), systemImage: "desktopcomputer", tint: DesignTokens.dusk),
            MerchantStop(place: "白鹭洲花店橱窗", activity: "在花店前停住，看了很久的叶子", guide: "街面安静、气味柔和，适合作为傍晚散步的中途停留。", coordinate: CLLocationCoordinate2D(latitude: 24.4772, longitude: 118.0961), systemImage: "camera.macro", tint: DesignTokens.clay)
        ],
        "京都": [
            MerchantStop(place: "锦市场小食铺", activity: "在锦市场小食铺里点了一份热汤", guide: "窄街、木色招牌和本地食物都被 TA 写进了今天的攻略。", coordinate: CLLocationCoordinate2D(latitude: 35.0051, longitude: 135.7648), systemImage: "fork.knife", tint: DesignTokens.amber),
            MerchantStop(place: "三条咖啡窗口", activity: "在咖啡窗口旁边的小桌喝了一杯饮料", guide: "TA 选了一个能看见街口的位置，让路线慢下来。", coordinate: CLLocationCoordinate2D(latitude: 35.0095, longitude: 135.7667), systemImage: "cup.and.saucer.fill", tint: DesignTokens.sage),
            MerchantStop(place: "四条便利店", activity: "在便利店里绕了一圈，挑了小补给", guide: "灯光和街声稳定，适合表达 TA 在城市里认真生活。", coordinate: CLLocationCoordinate2D(latitude: 35.0038, longitude: 135.7596), systemImage: "basket.fill", tint: DesignTokens.amber),
            MerchantStop(place: "河原町安静网咖", activity: "在网咖角落听见很轻的键盘声", guide: "室内停留点，适合长时间待着，不会一直机械移动。", coordinate: CLLocationCoordinate2D(latitude: 35.0064, longitude: 135.7690), systemImage: "desktopcomputer", tint: DesignTokens.dusk),
            MerchantStop(place: "祇园花店橱窗", activity: "在花店橱窗前看了很久的叶子", guide: "街面安静，适合作为明信片候选点。", coordinate: CLLocationCoordinate2D(latitude: 35.0034, longitude: 135.7752), systemImage: "camera.macro", tint: DesignTokens.clay)
        ],
        "雷克雅未克": [
            MerchantStop(place: "Laugavegur 小食铺", activity: "在小食铺里点了一小碗热汤", guide: "寒冷城市里的热气和灯光，适合做温柔停靠点。", coordinate: CLLocationCoordinate2D(latitude: 64.1452, longitude: -21.9298), systemImage: "fork.knife", tint: DesignTokens.amber),
            MerchantStop(place: "市中心咖啡窗口", activity: "在咖啡窗口旁边喝了一杯热饮", guide: "TA 坐在暖灯边，把这段城市夜色写进小卡片。", coordinate: CLLocationCoordinate2D(latitude: 64.1462, longitude: -21.9317), systemImage: "cup.and.saucer.fill", tint: DesignTokens.sage),
            MerchantStop(place: "Harpa 附近便利店", activity: "在便利店里选了一样小补给", guide: "靠近城市建筑和步行街，不会落到海面。", coordinate: CLLocationCoordinate2D(latitude: 64.1490, longitude: -21.9321), systemImage: "basket.fill", tint: DesignTokens.amber),
            MerchantStop(place: "暖灯游戏小店", activity: "在屏幕光旁边安静待了一会儿", guide: "室内长停留点，符合电子宠物走走停停的节奏。", coordinate: CLLocationCoordinate2D(latitude: 64.1441, longitude: -21.9266), systemImage: "desktopcomputer", tint: DesignTokens.dusk),
            MerchantStop(place: "彩虹街花店橱窗", activity: "在花店橱窗前看了很久的叶子", guide: "色彩和街面都适合生成地点感强的照片。", coordinate: CLLocationCoordinate2D(latitude: 64.1428, longitude: -21.9279), systemImage: "camera.macro", tint: DesignTokens.clay)
        ]
    ]
}

struct DemoCompanionPet: Identifiable {
    var id: String
    var name: String
    var petType: PetType
    var action: String
    var placeName: String
    var microStory: String
    var nextHint: String
    var coordinate: CLLocationCoordinate2D
    var tint: Color
    var showsLabel: Bool

    static func samples(around events: [JourneyMapEvent], fallback coordinate: CLLocationCoordinate2D) -> [DemoCompanionPet] {
        // 身份来自 NPCSociety.cast（与后端 npc_society.py 同一批），
        // 展示元数据统一登记在 CompanionCastPresentation；缺条目时兜底显示，不丢人。
        let presentation = CompanionCastPresentation.map

        // 每天轮换出场 5 位,街上的邻居有自己的生活,而不是永远同一张合影
        let dayIndex = Calendar.current.ordinality(of: .day, in: .year, for: Date()) ?? 0
        let cast = NPCSociety.cast
        let samples = (0..<5).map { cast[(dayIndex + $0) % cast.count] }

        var occupied = events.map(\.coordinate)
        var companions: [DemoCompanionPet] = []

        for (index, identity) in samples.enumerated() {
            let name = identity.name
            let meta = presentation[name] ?? CompanionCastPresentation.mapFallback
            let anchorEvent = events.isEmpty ? nil : events[index % events.count]
            let anchor = anchorEvent?.coordinate ?? coordinate
            let candidate = CLLocationCoordinate2D(
                latitude: anchor.latitude + meta.offset.latitude,
                longitude: anchor.longitude + meta.offset.longitude
            )
            let spacedCoordinate = coordinateAvoidingCrowd(
                candidate,
                index: index,
                occupied: occupied,
                minimumDistanceMeters: 78
            )
            occupied.append(spacedCoordinate)

            companions.append(DemoCompanionPet(
                id: identity.id,
                name: name,
                petType: meta.petType,
                action: meta.action,
                placeName: anchorEvent?.shortPlaceName ?? "附近街角",
                microStory: meta.story,
                nextHint: meta.nextHint,
                coordinate: spacedCoordinate,
                tint: meta.tint,
                showsLabel: meta.showsLabel
            ))
        }

        return companions
    }

    static func coordinateAvoidingCrowd(
        _ coordinate: CLLocationCoordinate2D,
        index: Int,
        occupied: [CLLocationCoordinate2D],
        minimumDistanceMeters: CLLocationDistance
    ) -> CLLocationCoordinate2D {
        var result = coordinate
        var attempt = 0
        while isTooClose(result, to: occupied, minimumDistanceMeters: minimumDistanceMeters), attempt < 6 {
            let angle = Double(index + 1) * 0.92 + Double(attempt) * 1.21
            let radius = 0.00042 + Double(attempt) * 0.00018
            result = CLLocationCoordinate2D(
                latitude: coordinate.latitude + sin(angle) * radius,
                longitude: coordinate.longitude + cos(angle) * radius
            )
            attempt += 1
        }
        return result
    }

    static func isTooClose(
        _ coordinate: CLLocationCoordinate2D,
        to occupied: [CLLocationCoordinate2D],
        minimumDistanceMeters: CLLocationDistance
    ) -> Bool {
        let location = CLLocation(latitude: coordinate.latitude, longitude: coordinate.longitude)
        return occupied.contains { other in
            location.distance(from: CLLocation(latitude: other.latitude, longitude: other.longitude)) < minimumDistanceMeters
        }
    }
}

struct JourneyActivitySnapshot {
    enum Kind: Equatable {
        case walking
        case staying
        case resting
        case checkingIn
        case transporting
    }

    var kind: Kind
    var title: String
    var detail: String
    var eyebrow: String
    var markerText: String
    var modeLabel: String
    var durationText: String
    var speedText: String
    var progress: Double
    var travelMode: TravelMode?
    var systemImage: String
    var markerSystemImage: String
    var animationHint: String
    var tint: Color
    var liveCoordinate: CLLocationCoordinate2D
    var routeCoordinatesOverride: [CLLocationCoordinate2D]?
    var relatedEvent: JourneyMapEvent?

    var cameraKey: String {
        let coordinateBucket = prefersNavigationCamera
            ? String(format: "%.3f-%.3f", liveCoordinate.latitude, liveCoordinate.longitude)
            : "static"
        return "\(markerText)-\(travelMode?.rawValue ?? "none")-\(animationHint)-\(relatedEvent?.id ?? "moving")-\(coordinateBucket)"
    }

    var prefersNavigationCamera: Bool {
        Self.prefersNavigationCamera(mode: travelMode) || animationHint == "transport_car"
    }

    static func prefersNavigationCamera(mode: TravelMode?) -> Bool {
        mode == .drive || mode == .transit
    }

    var isSleepLike: Bool {
        kind == .resting || animationHint == "sleep"
            || title.contains("睡") || title.contains("休息")
            || detail.contains("睡") || detail.contains("休息")
    }

    var sleepRemainingText: String {
        if durationText.contains("剩余") {
            return durationText
        }
        if durationText.contains("已停留") {
            return durationText
                .replacingOccurrences(of: "已停留", with: "已睡")
                .replacingOccurrences(of: "计划", with: "预计")
        }
        if durationText.contains("已完成") {
            return "快醒了"
        }
        return durationText.isEmpty ? "安睡中" : durationText
    }

    func sleepHeadline(petName: String) -> String {
        if title.contains("昨晚") || title.contains("上一段") {
            return "\(petName) 还在昨晚停下的地方睡着"
        }
        return "\(petName) 找到一处安静地方睡着了"
    }

    func sleepDetail(petName: String) -> String {
        let cleaned = detail.petSoulUserFacingText
        if cleaned.contains("天亮") || cleaned.contains("今天还没有开始") {
            return "我还在昨晚停下来的地方睡着。通讯器会把声音放轻，天亮后我会自己慢慢醒来。"
        }
        return "我先在这里睡一会儿，呼吸慢慢放轻。醒来以后，我会自己继续往前走。"
    }

    func statusValue(routePlan: JourneyRoutePlan) -> String {
        switch kind {
        case .walking:
            speedText
        case .staying, .resting, .checkingIn, .transporting:
            durationText
        }
    }

    static func from(
        snapshot: WorldSimulationSnapshot?,
        journeyPlan: JourneyPlan?,
        events: [JourneyMapEvent],
        anchor: CLLocationCoordinate2D
    ) -> JourneyActivitySnapshot? {
        guard let snapshot else { return nil }
        let activity = snapshot.currentActivity
        let mode = activity.mode ?? .stay
        let relatedEvent = relatedEvent(for: activity, events: events)
        let activeLeg = snapshot.activeTransport
        let segment = journeyPlan?.routeSegments.first { $0.id == activity.id }
        let routeOverride = routeCoordinates(for: activity, activeLeg: activeLeg, segment: segment)
        let distanceMeters = activeLeg?.distanceMeters ?? segment?.distanceMeters
        let durationSeconds = activeLeg?.durationSeconds ?? segment?.durationSeconds
        let kind = kind(for: activity)
        let resolvedAnimationHint = kind == .resting
            ? "sleep"
            : (snapshot.lifeTick?.animationHint ?? animationHint(for: activity, mode: mode))
        let resolvedTint = kind == .resting
            ? DesignTokens.dusk
            : tint(for: mode, fallback: relatedEvent?.tint)

        return JourneyActivitySnapshot(
            kind: kind,
            title: activity.title,
            detail: (snapshot.lifeTick?.ownerVisibleSummary ?? activity.detail).petSoulUserFacingText,
            eyebrow: eyebrow(for: activity),
            markerText: markerText(for: activity),
            modeLabel: modeLabel(for: activity, activeLeg: activeLeg),
            durationText: durationText(for: activity),
            speedText: speedText(mode: mode, distanceMeters: distanceMeters, durationSeconds: durationSeconds),
            progress: max(0.04, min(0.98, activity.progress)),
            travelMode: mode,
            systemImage: mode.systemImage,
            markerSystemImage: kind == .resting ? "moon.zzz.fill" : mode.systemImage,
            animationHint: resolvedAnimationHint,
            tint: resolvedTint,
            liveCoordinate: displayCoordinate(for: activity, kind: kind, relatedEvent: relatedEvent),
            routeCoordinatesOverride: routeOverride,
            relatedEvent: relatedEvent
        )
    }

    static func displayCoordinate(
        for activity: WorldActivity,
        kind: Kind,
        relatedEvent: JourneyMapEvent?
    ) -> CLLocationCoordinate2D {
        switch kind {
        case .staying, .resting, .checkingIn:
            return activity.coordinate
        case .walking, .transporting:
            return activity.coordinate
        }
    }

    static func kind(for activity: WorldActivity) -> Kind {
        switch activity.kind {
        case "transport":
            .transporting
        case "movement":
            activity.mode == .walk ? .walking : .transporting
        case "rest":
            .resting
        case "stop":
            (activity.canGeneratePhoto || activity.canSendPostcard) ? .checkingIn : .staying
        default:
            .staying
        }
    }

    static func eyebrow(for activity: WorldActivity) -> String {
        switch activity.kind {
        case "movement":
            activity.mode == .walk ? "TA 正在按路线散步" : "TA 正在前往下一站"
        case "transport":
            "TA 正在\(activity.mode?.displayName ?? "交通")途中"
        case "rest":
            "TA 睡着了"
        default:
            activity.canGeneratePhoto ? "TA 正在认真看这个地方" : "TA 正在自主停留"
        }
    }

    static func markerText(for activity: WorldActivity) -> String {
        if activity.kind == "rest" {
            return "睡着了"
        }
        if activity.status == .walking, activity.mode == .walk {
            return "散步中"
        }
        return activity.status.displayName
    }

    static func modeLabel(for activity: WorldActivity, activeLeg: ScheduledTransportLeg?) -> String {
        if let activeLeg {
            return activeLeg.serviceLabel
        }
        return activity.mode?.displayName ?? activity.status.displayName
    }

    static func durationText(for activity: WorldActivity) -> String {
        guard let endsAt = activity.endsAt else {
            return activity.status.displayName
        }
        let interval = endsAt.timeIntervalSince(.now)
        if interval > 0 {
            return "剩余 \(format(interval: interval))"
        }
        return "已完成"
    }

    static func speedText(mode: TravelMode, distanceMeters: Int?, durationSeconds: Int?) -> String {
        guard mode != .stay, mode != .checkIn else { return "停留中" }
        guard let distanceMeters, let durationSeconds, durationSeconds > 0 else {
            switch mode {
            case .walk:
                return "步速约 4 km/h"
            case .drive:
                return "车速随路况"
            case .flight:
                return "按航班时间"
            case .train:
                return "按车次时间"
            case .transit:
                return "按公交时间"
            case .ferry:
                return "按航线时间"
            case .stay, .checkIn:
                return "停留中"
            }
        }
        let kmh = (Double(distanceMeters) / 1_000) / (Double(durationSeconds) / 3_600)
        switch mode {
        case .walk:
            return String(format: "步速 %.1f km/h", min(max(kmh, 2.4), 5.8))
        case .drive:
            return String(format: "车速 %.0f km/h", min(max(kmh, 8), 110))
        case .flight:
            return String(format: "航速 %.0f km/h", min(max(kmh, 420), 980))
        case .train:
            return String(format: "车速 %.0f km/h", min(max(kmh, 30), 320))
        case .transit:
            return String(format: "公交 %.0f km/h", min(max(kmh, 8), 55))
        case .ferry:
            return String(format: "航速 %.0f km/h", min(max(kmh, 8), 70))
        case .stay, .checkIn:
            return "停留中"
        }
    }

    static func animationHint(for activity: WorldActivity, mode: TravelMode) -> String {
        if mode == .flight { return "transport_flight" }
        if mode == .train { return "transport_train" }
        if mode == .drive { return "transport_car" }
        if mode == .ferry { return "transport_ferry" }
        let text = [activity.title, activity.detail, activity.placeName ?? ""].joined(separator: " ").lowercased()
        if text.contains("咖啡") || text.contains("coffee") || text.contains("cafe") { return "coffee_drink" }
        if text.contains("网吧") || text.contains("游戏") || text.contains("屏幕") { return "gaming" }
        if activity.canGeneratePhoto { return "camera" }
        if mode == .walk { return "walking" }
        if activity.kind == "rest" { return "sleep" }
        return "observe"
    }

    static func format(interval: TimeInterval) -> String {
        let minutes = max(0, Int(interval / 60))
        if minutes < 60 { return "\(minutes) min" }
        let hours = minutes / 60
        let remaining = minutes % 60
        if remaining == 0 { return "\(hours)h" }
        return "\(hours)h \(remaining)m"
    }

    static func routeCoordinates(
        for activity: WorldActivity,
        activeLeg: ScheduledTransportLeg?,
        segment: RouteSegment?
    ) -> [CLLocationCoordinate2D]? {
        if let activeLeg, activeLeg.id == activity.currentTransportID {
            return activeLeg.routeCoordinates
        }
        if let segment {
            let coordinates = RoutePolylineDecoder.coordinates(from: segment.polyline)
            if coordinates.count > 1 {
                return coordinates
            }
        }
        return nil
    }

    static func relatedEvent(for activity: WorldActivity, events: [JourneyMapEvent]) -> JourneyMapEvent? {
        if activity.kind != "movement", activity.kind != "transport", let placeName = activity.placeName {
            return events.first { $0.place.contains(placeName) }
        }
        return JourneyMotion.nearestEvent(to: activity.coordinate, events: events, maxDistanceMeters: 180)
    }

    static func tint(for mode: TravelMode, fallback: Color?) -> Color {
        if let fallback {
            return fallback
        }
        switch mode {
        case .flight:
            return DesignTokens.dusk
        case .drive:
            return DesignTokens.amber
        case .train, .transit:
            return DesignTokens.sage
        case .ferry:
            return DesignTokens.pollen
        case .walk:
            return DesignTokens.clay
        case .stay, .checkIn:
            return DesignTokens.sage
        }
    }
}
