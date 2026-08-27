import SwiftUI
import UIKit

struct JourneyDateStrip: View {
    var activeDate: Date
    var city: String

    var days: [JourneyDateChipModel] {
        let calendar = Calendar.current
        return [
            JourneyDateChipModel(
                date: calendar.date(byAdding: .day, value: -1, to: activeDate) ?? activeDate,
                title: "昨天",
                subtitle: "已归档",
                isActive: false
            ),
            JourneyDateChipModel(
                date: activeDate,
                title: "今天",
                subtitle: city,
                isActive: true
            ),
            JourneyDateChipModel(
                date: calendar.date(byAdding: .day, value: 1, to: activeDate) ?? activeDate,
                title: "明天",
                subtitle: "准备中",
                isActive: false
            )
        ]
    }

    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                ForEach(days) { day in
                    JourneyDateChip(day: day)
                }
            }
            .padding(.vertical, 2)
        }
        .accessibilityLabel("按日期查看旅程")
    }
}

struct JourneyDateChip: View {
    var day: JourneyDateChipModel

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(spacing: 5) {
                Text(day.title)
                    .font(.caption.weight(.bold))
                Text(day.dateText)
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(day.isActive ? DesignTokens.sage : DesignTokens.secondaryInk)
            }

            Text(day.subtitle)
                .font(.caption2.weight(.semibold))
                .foregroundStyle(day.isActive ? DesignTokens.ink : DesignTokens.secondaryInk)
                .lineLimit(1)
        }
        .foregroundStyle(day.isActive ? DesignTokens.ink : DesignTokens.secondaryInk)
        .padding(.vertical, 9)
        .padding(.horizontal, 12)
        .frame(minWidth: 112, alignment: .leading)
        .background(day.isActive ? DesignTokens.mist.opacity(0.78) : DesignTokens.surface.opacity(0.56))
        .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .stroke(day.isActive ? DesignTokens.sage.opacity(0.24) : DesignTokens.softLine, lineWidth: 1)
        }
    }
}


