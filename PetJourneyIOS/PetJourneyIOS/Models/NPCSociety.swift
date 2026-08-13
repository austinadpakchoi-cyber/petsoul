import Foundation

/// 常驻 NPC 阵容：与后端 communicator/npc_society.py 是同一批身份。
/// View 的演示与 Mock 服务都从这里取身份，展示元数据（动作/表情/颜色/文案）由各消费方自行携带。
/// 朋友圈里点赞的邻居和地图上遇到的同伴必须是同一批，世界才是同一个。
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
