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

        // 走统一 APIClient（重试/错误归一），不直接 URLSession。
        let client = APIClient(baseURL: base.appendingPathComponent("api/v1"), authProvider: NoAuthProvider())
        guard let payload = try? await client.send(
            StoryTickerResponse.self,
            request: URLRequest(url: client.endpoint("/world/story_ticker")),
            retry: .idempotent
        ), !payload.items.isEmpty else { return }

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
