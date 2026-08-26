import Foundation
import SwiftUI

/// 常驻 NPC 阵容：与后端 communicator/npc_society.py 是同一批身份。
/// View 的演示与 Mock 服务都从这里取身份，展示元数据（动作/表情/颜色/文案）统一登记在
/// CompanionCastPresentation——朋友圈里点赞的邻居和地图上遇到的同伴必须是同一批，世界才是同一个。
enum NPCSociety {
    struct Identity: Equatable, Sendable {
        let id: String
        let name: String
        let typeRaw: String
    }

    static let cast: [Identity] = [
        Identity(id: "npc-nana-cat", name: "Nana", typeRaw: "cat"),
        Identity(id: "npc-tuanzi-dog", name: "团子", typeRaw: "dog"),
        Identity(id: "npc-jiujiu-parrot", name: "啾啾", typeRaw: "parrot"),
        Identity(id: "npc-momo-rabbit", name: "Momo", typeRaw: "rabbit"),
        Identity(id: "npc-mili-hamster", name: "米粒", typeRaw: "hamster"),
        Identity(id: "npc-lucky-dog", name: "Lucky", typeRaw: "dog"),
    ]
}

/// 单个 NPC 在地图上的展示元数据。
struct CompanionMapMeta: Equatable {
    var petType: PetType
    var action: String
    var offset: CoordinateOffset
    var tint: Color
    var showsLabel: Bool
    var story: String
    var nextHint: String
}

/// 单个 NPC 在朋友圈互动里的展示元数据。
struct CompanionMomentsMeta: Equatable {
    var avatarEmoji: String
    var reaction: MomentReaction
    var note: String
}

/// NPC 展示元数据注册表。
/// 往 NPCSociety.cast 加人时必须同时在这里补条目；缺失时兜底显示，绝不静默丢人
/// （对应测试断言 cast 与两个字典一一覆盖）。
enum CompanionCastPresentation {
    static let map: [String: CompanionMapMeta] = [
        "Nana": CompanionMapMeta(
            petType: .cat, action: "看橱窗",
            offset: CoordinateOffset(latitude: 0.00072, longitude: -0.00096),
            tint: DesignTokens.clay, showsLabel: true,
            story: "它蹲在玻璃窗前，像在研究里面一排亮亮的小物件。",
            nextHint: "看完橱窗就去晒下一段太阳"
        ),
        "团子": CompanionMapMeta(
            petType: .dog, action: "等面包",
            offset: CoordinateOffset(latitude: -0.00092, longitude: 0.00078),
            tint: DesignTokens.amber, showsLabel: true,
            story: "它在小店门口闻到刚烤好的香气，正耐心排队。",
            nextHint: "可能会带走一小份路上的点心"
        ),
        "啾啾": CompanionMapMeta(
            petType: .parrot, action: "学人说话",
            offset: CoordinateOffset(latitude: 0.00084, longitude: 0.00074),
            tint: DesignTokens.sage, showsLabel: false,
            story: "它停在树梢上，把刚听到的一句话小声学了一遍。",
            nextHint: "学会了就飞去更安静的树边"
        ),
        "Momo": CompanionMapMeta(
            petType: .rabbit, action: "听风铃",
            offset: CoordinateOffset(latitude: -0.00086, longitude: -0.00088),
            tint: DesignTokens.dusk, showsLabel: false,
            story: "它躲在人少的角落，耳朵跟着风铃轻轻动。",
            nextHint: "再听一会儿就把这里记进小地图"
        ),
        "米粒": CompanionMapMeta(
            petType: .hamster, action: "找补给",
            offset: CoordinateOffset(latitude: 0.00104, longitude: -0.00066),
            tint: DesignTokens.pollen, showsLabel: false,
            story: "它绕进灯光稳定的小店，挑了一个适合路上带着的小东西。",
            nextHint: "可能会把这个小东西放进背包"
        ),
        "Lucky": CompanionMapMeta(
            petType: .dog, action: "追光斑",
            offset: CoordinateOffset(latitude: 0.00058, longitude: 0.00102),
            tint: DesignTokens.amber, showsLabel: false,
            story: "它追着一块移动的光斑跑了半条街，尾巴摇个不停。",
            nextHint: "追到光就去下一条街巡逻"
        ),
    ]

    static let moments: [String: CompanionMomentsMeta] = [
        "Nana": CompanionMomentsMeta(avatarEmoji: "🐱", reaction: .like, note: "在附近的窗台看见了这一刻"),
        "团子": CompanionMomentsMeta(avatarEmoji: "🐶", reaction: .like, note: "也觉得这里适合慢慢待着"),
        "啾啾": CompanionMomentsMeta(avatarEmoji: "🦜", reaction: .hug, note: "从公共频道轻轻回应了一下"),
        "Momo": CompanionMomentsMeta(avatarEmoji: "🐰", reaction: .like, note: "把这一刻收藏进小地图"),
        "米粒": CompanionMomentsMeta(avatarEmoji: "🐹", reaction: .hug, note: "偷偷把这一刻塞进了腮帮子"),
        "Lucky": CompanionMomentsMeta(avatarEmoji: "🐶", reaction: .like, note: "在街角朝这边汪了一声"),
    ]

    static let mapFallback = CompanionMapMeta(
        petType: .other,
        action: "路过",
        offset: CoordinateOffset(latitude: 0, longitude: 0),
        tint: DesignTokens.clay,
        showsLabel: false,
        story: "它从街的另一头经过，朝这边看了一眼。",
        nextHint: "下一段路它有自己的去处"
    )

    static let momentsFallback = CompanionMomentsMeta(
        avatarEmoji: "🐾",
        reaction: .like,
        note: "轻轻回应了一下"
    )
}
