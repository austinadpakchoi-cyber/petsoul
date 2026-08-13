import Foundation

/// 「世界故事条」：拉取世界故事 ticker，成功则替换本地样本；失败时本地样本兜底，界面无感。
/// 原 WorldLiveStoryTicker 直接在 View 里 URLSession 拉取并 decode，下沉到 VM。
@MainActor
final class WorldStoryViewModel: ObservableObject {
    @Published private(set) var remoteEvents: [WorldLifeEvent] = []

    var storyPool: [WorldLifeEvent] {
        remoteEvents.isEmpty ? WorldLifeEvent.samples : remoteEvents
    }

    func loadRemoteStories(serviceMode: AppSessionStore.ServiceMode, baseURLString: String) async {
        guard serviceMode == .remote,
              let base = URL(string: baseURLString) else { return }

        struct TickerItem: Decodable {
            let id: String
            let text: String
            let city: String
        }
        struct TickerResponse: Decodable {
            let items: [TickerItem]
        }

        let url = base.appendingPathComponent("api/v1/world/story_ticker")
        guard let (data, response) = try? await URLSession.shared.data(from: url),
              let http = response as? HTTPURLResponse,
              http.statusCode == 200,
              let payload = try? JSONDecoder().decode(TickerResponse.self, from: data),
              !payload.items.isEmpty else { return }

        remoteEvents = payload.items.map { item in
            WorldLifeEvent(
                id: item.id,
                city: item.city,
                place: item.city,
                petName: "平行世界",
                petType: .cat,
                activity: item.text,
                detail: item.text,
                latitude: 0,
                longitude: 0,
                tintHex: 0xD6AA63,
                sceneIcon: "sparkles"
            )
        }
    }
}
