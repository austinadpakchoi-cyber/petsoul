import AuthenticationServices
import MapKit
import SwiftUI
import UIKit

enum JourneyDaySchedule {
    static func activity(
        date: Date,
        anchor: CLLocationCoordinate2D,
        events: [JourneyMapEvent],
        movingCoordinate: CLLocationCoordinate2D,
        scheduledTransport: [ScheduledTransportLeg]
    ) -> JourneyActivitySnapshot {
        if let leg = scheduledTransport.foregroundLeg(at: date) {
            return transport(leg: leg, date: date)
        }

        let components = Calendar.current.dateComponents([.hour, .minute], from: date)
        let minuteOfDay = (components.hour ?? 0) * 60 + (components.minute ?? 0)

        switch minuteOfDay {
        case 0..<420:
            return rest(
                start: 0,
                end: 420,
                minuteOfDay: minuteOfDay,
                event: overnightRestEvent(events: events),
                anchor: anchor,
                title: "在上一段旅程结束的地方休息",
                detail: "今天还没有开始，TA 先在昨晚停下来的地方安静待着，等天亮后再慢慢出发。",
                tint: DesignTokens.dusk
            )
        case 420..<510:
            return stay(
                start: 420,
                end: 510,
                minuteOfDay: minuteOfDay,
                event: event(at: 0, events: events),
                anchor: anchor,
                title: "在今天第一站慢慢醒来",
                detail: "TA 先确认周围的光线和声音，决定今天从这条安静的小路开始。"
            )
        case 510..<570:
            return walk(
                title: "搭一小段车去老城",
                detail: "早上的第一段距离稍远，TA 选择短途车去八市附近，把体力留给真正想停的地方。",
                movingCoordinate: movingCoordinate,
                relatedEvent: event(at: 1, events: events)
            )
        case 570..<690:
            return checkIn(
                start: 570,
                end: 690,
                minuteOfDay: minuteOfDay,
                event: event(at: 1, events: events),
                anchor: anchor,
                title: "走进老城的人间烟火",
                detail: "TA 在八市和开禾路慢慢看摊位、听声音，选一口厦门早午间的本地味道。"
            )
        case 690..<750:
            return walk(
                title: "从老城靠近老港",
                detail: "TA 沿真实道路去沙坡尾和大学路，中途不会乱穿路，也不会突然跳到海上。",
                movingCoordinate: movingCoordinate,
                relatedEvent: event(at: 2, events: events)
            )
        case 750..<900:
            return stay(
                start: 750,
                end: 900,
                minuteOfDay: minuteOfDay,
                event: event(at: 2, events: events),
                anchor: anchor,
                title: "在沙坡尾和大学路慢慢逛",
                detail: "这里有海风、旧港和小店。TA 找了一个不挡路的位置，坐下来把看到的颜色记住。"
            )
        case 900..<1_080:
            return stay(
                start: 900,
                end: 1_080,
                minuteOfDay: minuteOfDay,
                event: event(at: 3, events: events),
                anchor: anchor,
                title: "去海边收下午的风",
                detail: "TA 靠近环岛路和白城沙滩，走慢一点，把海面、树影和路边的光记进通讯器。"
            )
        case 1_080..<1_140:
            return walk(
                title: "傍晚回到湖边",
                detail: "下午结束后，TA 搭一小段车回到筼筜湖附近，把当天收在安静的地方。",
                movingCoordinate: movingCoordinate,
                relatedEvent: event(at: 4, events: events)
            )
        case 1_140..<1_320:
            return checkIn(
                start: 1_140,
                end: 1_320,
                minuteOfDay: minuteOfDay,
                event: event(at: 4, events: events),
                anchor: anchor,
                title: "在白鹭洲和筼筜湖边写信",
                detail: "天色变软以后，TA 在湖边慢下来，把今天写成一封小小的信。"
            )
        default:
            return rest(
                start: 1_320,
                end: 1_440,
                minuteOfDay: minuteOfDay,
                event: event(at: 4, events: events),
                anchor: anchor,
                title: "找了一个不被打扰的位置休息",
                detail: "今天的本地计划快结束了，TA 没有继续赶路，只是让自己慢下来。",
                tint: DesignTokens.dusk
            )
        }
    }

    static func event(at index: Int, events: [JourneyMapEvent]) -> JourneyMapEvent? {
        guard !events.isEmpty else { return nil }
        return events[min(index, events.count - 1)]
    }

    static func overnightRestEvent(events: [JourneyMapEvent]) -> JourneyMapEvent? {
        events.last
    }

    static func stay(
        start: Int,
        end: Int,
        minuteOfDay: Int,
        event: JourneyMapEvent?,
        anchor: CLLocationCoordinate2D,
        title: String,
        detail: String
    ) -> JourneyActivitySnapshot {
        JourneyActivitySnapshot(
            kind: .staying,
            title: title,
            detail: detail,
            eyebrow: "TA 正在自主停留",
            markerText: "停留中",
            modeLabel: "本地停留",
            durationText: elapsedLabel(start: start, end: end, minuteOfDay: minuteOfDay),
            speedText: "停留中",
            progress: progress(start: start, end: end, minuteOfDay: minuteOfDay),
            travelMode: .stay,
            systemImage: event?.systemImage ?? "mappin.and.ellipse",
            markerSystemImage: "pawprint.fill",
            animationHint: fallbackAnimationHint(title: title, detail: detail, systemImage: event?.systemImage),
            tint: event?.tint ?? DesignTokens.sage,
            liveCoordinate: event?.coordinate ?? anchor,
            routeCoordinatesOverride: nil,
            relatedEvent: event
        )
    }

    static func checkIn(
        start: Int,
        end: Int,
        minuteOfDay: Int,
        event: JourneyMapEvent?,
        anchor: CLLocationCoordinate2D,
        title: String,
        detail: String
    ) -> JourneyActivitySnapshot {
        JourneyActivitySnapshot(
            kind: .checkingIn,
            title: title,
            detail: detail,
            eyebrow: "TA 正在打卡",
            markerText: "打卡中",
            modeLabel: "地点打卡",
            durationText: elapsedLabel(start: start, end: end, minuteOfDay: minuteOfDay),
            speedText: "停留中",
            progress: progress(start: start, end: end, minuteOfDay: minuteOfDay),
            travelMode: .checkIn,
            systemImage: event?.systemImage ?? "camera.fill",
            markerSystemImage: "pawprint.fill",
            animationHint: "camera",
            tint: event?.tint ?? DesignTokens.clay,
            liveCoordinate: event?.coordinate ?? anchor,
            routeCoordinatesOverride: nil,
            relatedEvent: event
        )
    }

    static func rest(
        start: Int,
        end: Int,
        minuteOfDay: Int,
        event: JourneyMapEvent?,
        anchor: CLLocationCoordinate2D,
        title: String,
        detail: String,
        tint: Color
    ) -> JourneyActivitySnapshot {
        JourneyActivitySnapshot(
            kind: .resting,
            title: title,
            detail: detail,
            eyebrow: "TA 睡着了",
            markerText: "睡着了",
            modeLabel: "睡眠",
            durationText: sleepElapsedLabel(start: start, end: end, minuteOfDay: minuteOfDay),
            speedText: "停留中",
            progress: progress(start: start, end: end, minuteOfDay: minuteOfDay),
            travelMode: .stay,
            systemImage: "moon.zzz.fill",
            markerSystemImage: "moon.zzz.fill",
            animationHint: "sleep",
            tint: tint,
            liveCoordinate: event?.coordinate ?? anchor,
            routeCoordinatesOverride: nil,
            relatedEvent: event
        )
    }

    static func walk(
        title: String,
        detail: String,
        movingCoordinate: CLLocationCoordinate2D,
        relatedEvent: JourneyMapEvent?
    ) -> JourneyActivitySnapshot {
        JourneyActivitySnapshot(
            kind: .walking,
            title: title,
            detail: detail,
            eyebrow: "TA 正在路上",
            markerText: "散步中",
            modeLabel: "步行中",
            durationText: "路上",
            speedText: "步速约 4 km/h",
            progress: 0.58,
            travelMode: .walk,
            systemImage: TravelMode.walk.systemImage,
            markerSystemImage: TravelMode.walk.systemImage,
            animationHint: "walking",
            tint: DesignTokens.sage,
            liveCoordinate: movingCoordinate,
            routeCoordinatesOverride: nil,
            relatedEvent: relatedEvent
        )
    }

    static func transport(leg: ScheduledTransportLeg, date: Date) -> JourneyActivitySnapshot {
        let modeTint = tint(for: leg.mode)
        return JourneyActivitySnapshot(
            kind: .transporting,
            title: leg.title,
            detail: leg.timelineNote ?? leg.detail,
            eyebrow: eyebrow(for: leg),
            markerText: leg.status.displayName,
            modeLabel: leg.serviceLabel,
            durationText: leg.remainingText(at: date),
            speedText: leg.averageSpeedText,
            progress: leg.timelineProgress(at: date),
            travelMode: leg.mode,
            systemImage: leg.mode.systemImage,
            markerSystemImage: leg.mode.systemImage,
            animationHint: transportAnimationHint(for: leg.mode),
            tint: modeTint,
            liveCoordinate: leg.liveCoordinate(at: date),
            routeCoordinatesOverride: leg.routeCoordinates,
            relatedEvent: nil
        )
    }

    static func fallbackAnimationHint(title: String, detail: String, systemImage: String?) -> String {
        let text = [title, detail, systemImage ?? ""].joined(separator: " ").lowercased()
        if text.contains("咖啡") || text.contains("coffee") || text.contains("cafe") {
            return "coffee_drink"
        }
        if text.contains("网吧") || text.contains("游戏") || text.contains("屏幕") {
            return "gaming"
        }
        if text.contains("餐") || text.contains("饭") || text.contains("小吃") || text.contains("便利店") {
            return "snack"
        }
        if text.contains("相机") || text.contains("camera") {
            return "camera"
        }
        return "observe"
    }

    static func transportAnimationHint(for mode: TravelMode) -> String {
        switch mode {
        case .flight:
            return "transport_flight"
        case .train:
            return "transport_train"
        case .drive, .transit:
            return "transport_car"
        case .ferry:
            return "transport_ferry"
        case .walk:
            return "walking"
        case .stay, .checkIn:
            return "observe"
        }
    }

    static func eyebrow(for leg: ScheduledTransportLeg) -> String {
        switch leg.status {
        case .waiting, .boarding:
            "TA 正在准备\(leg.mode.displayName)"
        case .inTransit:
            "TA 正在\(leg.mode.displayName)途中"
        case .arrived:
            "TA 已经抵达"
        case .scheduled:
            "下一段交通已计划"
        case .delayed:
            "交通有点延误"
        case .cancelled:
            "这段交通取消了"
        }
    }

    static func tint(for mode: TravelMode) -> Color {
        switch mode {
        case .flight:
            DesignTokens.dusk
        case .train, .transit:
            DesignTokens.sage
        case .drive:
            DesignTokens.amber
        case .walk:
            DesignTokens.clay
        case .ferry:
            DesignTokens.pollen
        case .stay, .checkIn:
            DesignTokens.sage
        }
    }

    static func elapsedLabel(start: Int, end: Int, minuteOfDay: Int) -> String {
        let elapsed = max(0, minuteOfDay - start)
        let planned = max(1, end - start)
        return "已停留 \(format(minutes: elapsed)) / 计划 \(format(minutes: planned))"
    }

    static func sleepElapsedLabel(start: Int, end: Int, minuteOfDay: Int) -> String {
        let elapsed = max(0, minuteOfDay - start)
        let planned = max(1, end - start)
        return "已睡 \(format(minutes: elapsed)) / 预计 \(format(minutes: planned))"
    }

    static func progress(start: Int, end: Int, minuteOfDay: Int) -> Double {
        let planned = max(1, end - start)
        let elapsed = min(max(0, minuteOfDay - start), planned)
        return max(0.08, min(0.96, Double(elapsed) / Double(planned)))
    }

    static func format(minutes: Int) -> String {
        if minutes < 60 { return "\(minutes) min" }
        let hours = minutes / 60
        let remaining = minutes % 60
        if remaining == 0 { return "\(hours)h" }
        return "\(hours)h \(remaining)m"
    }
}

extension JourneyStatus {
    var symbolName: String {
        switch self {
        case .traveling: "map.fill"
        case .flying: "paperplane.fill"
        case .resting: "moon.zzz.fill"
        case .staying: "mappin.and.ellipse"
        case .walking: "figure.walk"
        }
    }
}

extension Array where Element == ScheduledTransportLeg {
    func foregroundLeg(at date: Date) -> ScheduledTransportLeg? {
        first { leg in
            switch leg.status {
            case .waiting, .boarding, .inTransit, .delayed:
                true
            case .scheduled:
                date >= leg.scheduledDeparture.addingTimeInterval(-60 * 60)
                    && date <= leg.scheduledDeparture
            case .arrived:
                date <= leg.scheduledArrival.addingTimeInterval(15 * 60)
            case .cancelled:
                false
            }
        }
    }
}

extension ScheduledTransportLeg {
    var routeCoordinates: [CLLocationCoordinate2D] {
        let decoded = RoutePolylineDecoder.coordinates(from: routePolyline)
        if decoded.count > 1 {
            return decoded
        }
        return [originCoordinate, destinationCoordinate]
    }

    var averageSpeedText: String {
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

    func liveCoordinate(at date: Date) -> CLLocationCoordinate2D {
        let total = max(1, scheduledArrival.timeIntervalSince(scheduledDeparture))
        let elapsed = date.timeIntervalSince(scheduledDeparture)
        let progress = JourneyMotion.pacedProgress(
            elapsed: elapsed,
            duration: total,
            mode: mode,
            seed: JourneyMotion.seed(id)
        )
        return JourneyMotion.coordinate(on: routeCoordinates, progress: progress) ?? originCoordinate
    }

    func timelineProgress(at date: Date) -> Double {
        let total = max(1, scheduledArrival.timeIntervalSince(scheduledDeparture))
        let elapsed = date.timeIntervalSince(scheduledDeparture)
        return max(0, min(1, elapsed / total))
    }

    func remainingText(at date: Date) -> String {
        switch status {
        case .scheduled, .waiting, .boarding:
            return "距出发 \(format(interval: max(0, scheduledDeparture.timeIntervalSince(date))))"
        case .inTransit, .delayed:
            return "预计 \(format(interval: max(0, scheduledArrival.timeIntervalSince(date)))) 后到达"
        case .arrived:
            return "已到达 \(destinationName)"
        case .cancelled:
            return "这段已取消"
        }
    }

    func format(interval: TimeInterval) -> String {
        let minutes = max(0, Int(interval / 60))
        if minutes < 60 { return "\(minutes) min" }
        let hours = minutes / 60
        let remaining = minutes % 60
        if remaining == 0 { return "\(hours)h" }
        return "\(hours)h \(remaining)m"
    }
}


