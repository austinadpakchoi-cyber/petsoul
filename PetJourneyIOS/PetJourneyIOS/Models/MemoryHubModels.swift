import PhotosUI
import SwiftUI
import UIKit

struct MemoryArchiveHighlight {
    var title: String
    var detail: String
    var systemImage: String
    var tint: Color
    var date: Date
}

struct MemoryEditorValues {
    var kind: String
    var title: String
    var content: String
    var salience: Double
    var source: String
    var metadata: [String: JSONValue]
    var memoryType: String
    var importance: Double
    var emotionalValence: Double
    var confidence: Double
    var sourceEventID: String?
    var structuredPayload: [String: JSONValue]
}

struct MemoryEditorDraft: Identifiable {
    let id = UUID()
    var memory: MemoryRecord?
}

enum MemoryArchiveFilter: String, CaseIterable, Identifiable {
    case all
    case relationship
    case preference
    case place
    case episodic
    case manual

    var id: String { rawValue }

    var title: String {
        switch self {
        case .all: "全部"
        case .relationship: "关系"
        case .preference: "偏好"
        case .place: "地点"
        case .episodic: "片段"
        case .manual: "手写"
        }
    }

    func matches(_ memory: MemoryRecord) -> Bool {
        let kind = memory.kind.lowercased()
        let type = (memory.memoryType ?? memory.kind).lowercased()
        switch self {
        case .all:
            return true
        case .relationship:
            return type.contains("relationship") || kind.contains("identity") || kind.contains("owner")
        case .preference:
            return type.contains("preference") || kind.contains("preference") || kind.contains("feedback")
        case .place:
            return type.contains("place") || kind.contains("place") || kind.contains("postcard") || kind.contains("souvenir")
        case .episodic:
            return type.contains("episodic") || type.contains("recent")
        case .manual:
            return memory.source.lowercased().contains("manual") || memory.source.lowercased().contains("owner")
        }
    }
}
