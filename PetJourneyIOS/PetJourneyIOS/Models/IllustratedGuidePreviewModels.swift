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
