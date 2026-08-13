import SwiftUI
import UIKit

struct IllustratedGuidePreviewStop: Identifiable {
    var id: String
    var index: Int
    var time: String?
    var name: String
    var label: String
    var note: String
    var systemImage: String
}

struct IllustratedGuidePreviewCanvas: View {
    var title: String
    var theme: String
    var petThought: String
    var city: String
    var templateID: String = "spiral_cover_overview"
    var stops: [IllustratedGuidePreviewStop]

    var body: some View {
        ZStack(alignment: .leading) {
            notebookPaper
            IllustratedGuideSpiralBinding()
                .padding(.leading, 6)

            Group {
                switch templateID {
                case "winding_route_map", "route_map":
                    routeMapPage
                case "vertical_timeline_journal", "timeline":
                    timelinePage
                default:
                    coverPage
                }
            }
            .padding(.leading, 26)
            .padding(.trailing, 16)
            .padding(.vertical, 18)
        }
        .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .stroke(Color(hex: 0xD8C8AA).opacity(0.48), lineWidth: 1)
        )
    }

    var notebookPaper: some View {
        ZStack {
            Color(hex: 0xFFF6E5)
            LinearGradient(
                colors: [
                    Color.white.opacity(0.25),
                    DesignTokens.pollen.opacity(0.12),
                    DesignTokens.sky.opacity(0.18)
                ],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
        }
    }

    var coverPage: some View {
        VStack(alignment: .leading, spacing: 11) {
            HStack(alignment: .top, spacing: 10) {
                VStack(alignment: .leading, spacing: 5) {
                    Text(title)
                        .font(.title3.weight(.black))
                        .foregroundStyle(DesignTokens.ink)
                        .lineLimit(2)
                        .minimumScaleFactor(0.72)
                    Text("从山上的风，到老城的烟火，再到傍晚的水边")
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(DesignTokens.dusk)
                        .lineLimit(2)
                        .padding(.vertical, 5)
                        .padding(.horizontal, 8)
                        .background(DesignTokens.sky.opacity(0.58))
                        .clipShape(Capsule())
                }
                Spacer(minLength: 0)
                IllustratedGuideSketchStamp(title: city, systemImage: "photo")
            }

            HStack(alignment: .center, spacing: 10) {
                Image(systemName: "pawprint.fill")
                    .font(.title.weight(.bold))
                    .foregroundStyle(DesignTokens.clay)
                    .frame(width: 50, height: 50)
                    .background(DesignTokens.clay.opacity(0.12))
                    .clipShape(Circle())
                Text(theme)
                    .font(.caption.weight(.medium))
                    .foregroundStyle(DesignTokens.secondaryInk)
                    .lineLimit(3)
                    .lineSpacing(2)
            }
            .padding(10)
            .background(DesignTokens.surface.opacity(0.58))
            .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))

            Text("今日路线")
                .font(.caption.weight(.bold))
                .foregroundStyle(DesignTokens.sage)

            HStack(spacing: 7) {
                ForEach(stops.prefix(5)) { stop in
                    VStack(spacing: 5) {
                        IllustratedGuideMiniScene(stop: stop)
                        Text(stop.name)
                            .font(.caption2.weight(.bold))
                            .foregroundStyle(DesignTokens.ink)
                            .lineLimit(1)
                            .minimumScaleFactor(0.72)
                    }
                    .frame(maxWidth: .infinity)
                }
            }

            HStack(spacing: 6) {
                ForEach(stops.prefix(4)) { stop in
                    Text(stop.label)
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(DesignTokens.secondaryInk)
                        .lineLimit(1)
                        .padding(.vertical, 6)
                        .padding(.horizontal, 8)
                        .background(keywordTint(for: stop).opacity(0.18))
                        .clipShape(Capsule())
                }
            }

            thoughtBubble
        }
    }

    var routeMapPage: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 4) {
                    Text("今日旅程图")
                        .font(.title3.weight(.black))
                        .foregroundStyle(DesignTokens.ink)
                    Text("\(city) · \(stops.count) 站串联")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(DesignTokens.dusk)
                }
                Spacer(minLength: 0)
                IllustratedGuideSketchStamp(title: "路线主题", systemImage: "map")
            }

            Text(theme)
                .font(.caption.weight(.medium))
                .foregroundStyle(DesignTokens.secondaryInk)
                .lineLimit(2)

            ZStack {
                IllustratedGuideWindingPath()
                    .stroke(DesignTokens.amber.opacity(0.42), style: StrokeStyle(lineWidth: 7, lineCap: .round, dash: [6, 8]))
                    .padding(.horizontal, 18)

                VStack(spacing: 8) {
                    ForEach(Array(stops.prefix(5).enumerated()), id: \.element.id) { offset, stop in
                        HStack(spacing: 8) {
                            if offset.isMultiple(of: 2) {
                                routeStopPill(stop)
                                Spacer(minLength: 18)
                            } else {
                                Spacer(minLength: 18)
                                routeStopPill(stop)
                            }
                        }
                    }
                }
            }
            .frame(maxHeight: .infinity)

            thoughtBubble
        }
    }

    var timelinePage: some View {
        VStack(alignment: .leading, spacing: 11) {
            HStack(alignment: .firstTextBaseline) {
                Text("慢慢走的一天")
                    .font(.title3.weight(.black))
                    .foregroundStyle(DesignTokens.ink)
                Spacer(minLength: 0)
                Text(city)
                    .font(.caption.weight(.bold))
                    .foregroundStyle(DesignTokens.clay)
            }

            VStack(alignment: .leading, spacing: 8) {
                ForEach(Array(stops.prefix(5).enumerated()), id: \.element.id) { rowIndex, stop in
                    IllustratedGuidePreviewStopRow(stop: stop, isLast: rowIndex == min(stops.count, 5) - 1)
                }
            }
            .padding(.top, 2)

            Spacer(minLength: 0)
            thoughtBubble
        }
    }

    var thoughtBubble: some View {
        HStack(alignment: .top, spacing: 8) {
            Image(systemName: "sparkles")
                .font(.caption.weight(.bold))
                .foregroundStyle(DesignTokens.clay)
            Text(petThought)
                .font(.caption.weight(.medium))
                .foregroundStyle(DesignTokens.secondaryInk)
                .lineSpacing(3)
                .lineLimit(3)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(10)
        .background(DesignTokens.surface.opacity(0.58))
        .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .stroke(style: StrokeStyle(lineWidth: 1, dash: [5, 5]))
                .foregroundStyle(DesignTokens.clay.opacity(0.22))
        )
    }

    func routeStopPill(_ stop: IllustratedGuidePreviewStop) -> some View {
        HStack(spacing: 7) {
            IllustratedGuideMiniScene(stop: stop)
                .frame(width: 42, height: 42)
            VStack(alignment: .leading, spacing: 2) {
                Text("\(stop.index)  \(stop.name)")
                    .font(.caption.weight(.bold))
                    .foregroundStyle(DesignTokens.ink)
                    .lineLimit(1)
                    .minimumScaleFactor(0.72)
                Text(stop.time ?? stop.label)
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(DesignTokens.secondaryInk)
            }
        }
        .padding(7)
        .frame(width: 190, alignment: .leading)
        .background(DesignTokens.surface.opacity(0.66))
        .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
    }

    func keywordTint(for stop: IllustratedGuidePreviewStop) -> Color {
        if stop.systemImage.contains("tree") { return DesignTokens.sage }
        if stop.systemImage.contains("cup") { return DesignTokens.sea }
        if stop.systemImage.contains("fork") { return DesignTokens.amber }
        return DesignTokens.clay
    }
}

struct IllustratedGuideSpiralBinding: View {
    var body: some View {
        VStack(spacing: 13) {
            ForEach(0..<18, id: \.self) { _ in
                HStack(spacing: 0) {
                    Circle()
                        .stroke(Color(hex: 0x9B8C78).opacity(0.62), lineWidth: 1.4)
                        .frame(width: 9, height: 9)
                    RoundedRectangle(cornerRadius: 1)
                        .fill(Color(hex: 0x9B8C78).opacity(0.42))
                        .frame(width: 10, height: 2)
                }
            }
        }
    }
}

struct IllustratedGuideSketchStamp: View {
    var title: String
    var systemImage: String

    var body: some View {
        VStack(spacing: 4) {
            Image(systemName: systemImage)
                .font(.caption.weight(.bold))
                .foregroundStyle(DesignTokens.dusk)
                .frame(width: 44, height: 34)
                .background(DesignTokens.sky.opacity(0.62))
                .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
            Text(title)
                .font(.system(size: 8, weight: .bold))
                .foregroundStyle(DesignTokens.secondaryInk)
                .lineLimit(1)
        }
        .padding(6)
        .rotationEffect(.degrees(3))
        .background(Color.white.opacity(0.62))
        .clipShape(RoundedRectangle(cornerRadius: 9, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 9, style: .continuous)
                .stroke(DesignTokens.clay.opacity(0.18), lineWidth: 1)
        )
    }
}

struct IllustratedGuideMiniScene: View {
    var stop: IllustratedGuidePreviewStop

    var body: some View {
        ZStack {
            RoundedRectangle(cornerRadius: 10, style: .continuous)
                .fill(
                    LinearGradient(
                        colors: [
                            tint.opacity(0.22),
                            Color.white.opacity(0.7)
                        ],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    )
                )
            Image(systemName: stop.systemImage)
                .font(.caption.weight(.bold))
                .foregroundStyle(tint)
            VStack {
                Spacer()
                HStack {
                    Text("\(stop.index)")
                        .font(.system(size: 8, weight: .black))
                        .foregroundStyle(.white)
                        .frame(width: 14, height: 14)
                        .background(tint)
                        .clipShape(Circle())
                    Spacer()
                }
            }
            .padding(4)
        }
        .frame(height: 48)
    }

    var tint: Color {
        if stop.systemImage.contains("tree") { return DesignTokens.sage }
        if stop.systemImage.contains("cup") { return DesignTokens.sea }
        if stop.systemImage.contains("fork") { return DesignTokens.amber }
        return DesignTokens.clay
    }
}

struct IllustratedGuideWindingPath: Shape {
    func path(in rect: CGRect) -> Path {
        var path = Path()
        path.move(to: CGPoint(x: rect.minX + rect.width * 0.12, y: rect.minY + rect.height * 0.08))
        path.addCurve(
            to: CGPoint(x: rect.maxX - rect.width * 0.18, y: rect.minY + rect.height * 0.28),
            control1: CGPoint(x: rect.maxX - rect.width * 0.2, y: rect.minY + rect.height * 0.04),
            control2: CGPoint(x: rect.minX + rect.width * 0.36, y: rect.minY + rect.height * 0.28)
        )
        path.addCurve(
            to: CGPoint(x: rect.minX + rect.width * 0.22, y: rect.minY + rect.height * 0.56),
            control1: CGPoint(x: rect.maxX - rect.width * 0.06, y: rect.minY + rect.height * 0.42),
            control2: CGPoint(x: rect.minX + rect.width * 0.18, y: rect.minY + rect.height * 0.36)
        )
        path.addCurve(
            to: CGPoint(x: rect.maxX - rect.width * 0.18, y: rect.minY + rect.height * 0.86),
            control1: CGPoint(x: rect.minX + rect.width * 0.28, y: rect.minY + rect.height * 0.78),
            control2: CGPoint(x: rect.maxX - rect.width * 0.28, y: rect.minY + rect.height * 0.62)
        )
        return path
    }
}

struct IllustratedGuidePreviewStopRow: View {
    var stop: IllustratedGuidePreviewStop
    var isLast: Bool

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            VStack(spacing: 4) {
                ZStack {
                    Circle()
                        .fill(DesignTokens.surface.opacity(0.74))
                        .frame(width: 30, height: 30)
                    Text("\(stop.index)")
                        .font(.caption.weight(.black))
                        .foregroundStyle(DesignTokens.sage)
                }

                if !isLast {
                    RoundedRectangle(cornerRadius: 2)
                        .fill(DesignTokens.sage.opacity(0.26))
                        .frame(width: 2, height: 24)
                }
            }

            VStack(alignment: .leading, spacing: 3) {
                HStack(spacing: 6) {
                    if let time = stop.time, !time.isEmpty {
                        Text(time)
                            .font(.caption2.weight(.bold))
                            .foregroundStyle(DesignTokens.sage)
                    }
                    Image(systemName: stop.systemImage)
                        .font(.caption2.weight(.bold))
                        .foregroundStyle(DesignTokens.clay)
                    Text(stop.label)
                        .font(.caption2.weight(.bold))
                        .foregroundStyle(DesignTokens.clay)
                }

                Text(stop.name)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(DesignTokens.ink)
                    .lineLimit(1)

                Text(stop.note)
                    .font(.caption2)
                    .foregroundStyle(DesignTokens.secondaryInk)
                    .lineLimit(2)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }
}
