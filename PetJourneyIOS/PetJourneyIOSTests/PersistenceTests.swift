import SwiftData
import XCTest
@testable import PetJourneyIOS

@MainActor
final class PersistenceTests: XCTestCase {
    private var container: ModelContainer!

    override func setUp() {
        super.setUp()
        container = try! PetSoulModelContainer.make(inMemory: true)
    }

    override func tearDown() {
        container = nil
        super.tearDown()
    }

    func testStoreAndLoadRoundTrip() {
        let repository = JourneyCacheRepository(petID: "pet-1", container: container)
        let position = CityPosition(city: "京都", latitude: 35.0116, longitude: 135.7681)

        repository.store(position, kind: .cityPosition)
        let snapshot = repository.load(CityPosition.self, kind: .cityPosition)

        XCTAssertEqual(snapshot?.value.city, "京都")
        XCTAssertNotNil(snapshot?.updatedAt)
    }

    func testStoreUpsertsInsteadOfDuplicating() {
        let repository = JourneyCacheRepository(petID: "pet-1", container: container)
        repository.store(CityPosition(city: "京都", latitude: 35.0116, longitude: 135.7681), kind: .cityPosition)
        repository.store(CityPosition(city: "厦门", latitude: 24.4798, longitude: 118.0894), kind: .cityPosition)

        XCTAssertEqual(repository.load(CityPosition.self, kind: .cityPosition)?.value.city, "厦门")
    }

    func testCacheIsIsolatedPerPet() {
        let first = JourneyCacheRepository(petID: "pet-1", container: container)
        let second = JourneyCacheRepository(petID: "pet-2", container: container)
        first.store(CityPosition(city: "京都", latitude: 35.0116, longitude: 135.7681), kind: .cityPosition)

        XCTAssertNil(second.load(CityPosition.self, kind: .cityPosition))
    }

    func testRemoteFirstFallsBackToCacheWhenOffline() async throws {
        let repository = JourneyCacheRepository(petID: "pet-1", container: container)
        repository.store(CityPosition(city: "京都", latitude: 35.0116, longitude: 135.7681), kind: .cityPosition)

        let outcome = try await repository.remoteFirst(.cityPosition) { () throws -> CityPosition in
            throw PetJourneyError.offline
        }

        XCTAssertEqual(outcome.value.city, "京都")
        guard case .stale = outcome.freshness else {
            return XCTFail("离线回退应标记 stale")
        }
    }

    func testRemoteFirstThrowsWhenNoCache() async {
        let repository = JourneyCacheRepository(petID: "pet-1", container: container)
        do {
            _ = try await repository.remoteFirst(.cityPosition) { () throws -> CityPosition in
                throw PetJourneyError.offline
            }
            XCTFail("无缓存时应抛出原错误")
        } catch {
            XCTAssertEqual(error as? PetJourneyError, .offline)
        }
    }

    func testPurgeRemovesAllRowsForPet() {
        let repository = JourneyCacheRepository(petID: "pet-1", container: container)
        repository.store(CityPosition(city: "京都", latitude: 35.0116, longitude: 135.7681), kind: .cityPosition)
        repository.purgeAll()

        XCTAssertNil(repository.load(CityPosition.self, kind: .cityPosition))
    }

    func testOutboxDrainsInOrderAndClears() async {
        let queue = OutboundMessageQueue(petID: "pet-1", container: container)
        queue.enqueue(text: "第一句")
        queue.enqueue(text: "第二句")
        XCTAssertEqual(queue.pendingCount, 2)

        var sent: [String] = []
        let result = await queue.drain { message in
            sent.append(message.text)
        }

        XCTAssertEqual(sent, ["第一句", "第二句"])
        XCTAssertEqual(queue.pendingCount, 0)
        XCTAssertEqual(result.delivered, 2)
        XCTAssertEqual(result.failed, 0)
    }

    func testOutboxFailureKeepsMessagesQueuedAndDoesNotBlockRest() async {
        let queue = OutboundMessageQueue(petID: "pet-1", container: container)
        queue.enqueue(text: "第一句")
        queue.enqueue(text: "第二句")

        var attempted: [String] = []
        let result = await queue.drain { message in
            attempted.append(message.text)
            throw PetJourneyError.offline
        }

        XCTAssertEqual(attempted, ["第一句", "第二句"], "一条消息失败不应阻塞后面的消息")
        XCTAssertEqual(queue.pendingCount, 2, "失败的消息应回到队列等待下次补发")
        XCTAssertEqual(result.delivered, 0, "全部失败时不得报告有送达")
        XCTAssertEqual(result.failed, 0, "未达上限的失败仍算在队，不计入死信")
    }

    func testPoisonMessageIsMarkedFailedAndSkipsOthers() async {
        let queue = OutboundMessageQueue(petID: "pet-1", container: container)
        queue.enqueue(text: "坏消息")
        queue.enqueue(text: "好消息")

        for _ in 0..<OutboundMessageQueue.maxAttempts {
            await queue.drain { message in
                if message.text == "坏消息" { throw PetJourneyError.requestFailed("拒绝") }
            }
        }

        // 坏消息达到上限应转 failed（死信可见）；好消息已送达，但仍有死信残留，
        // 上层必须如实知道「有没送出去的话」，而不是看到 pendingCount == 0 就报「已送达」。
        XCTAssertEqual(queue.pendingCount, 0)
        XCTAssertEqual(queue.failedCount, 1, "死信必须对上层可见")
    }

    func testSendingStateIsRecoveredOnInit() async {
        let queue = OutboundMessageQueue(petID: "pet-1", container: container)
        queue.enqueue(text: "中断中的话")

        // 模拟 drain 进行中被进程回收：消息停在 .sending
        let context = container.mainContext
        let descriptor = FetchDescriptor<OutboundMessage>()
        let messages = try! context.fetch(descriptor)
        messages.first?.stateRaw = OutboundMessageState.sending.rawValue
        try! context.save()

        // 重新初始化（等价于 App 重启）：.sending 必须复位回队列，不能静默消失
        let restored = OutboundMessageQueue(petID: "pet-1", container: container)
        XCTAssertEqual(restored.pendingCount, 1)

        var sent: [String] = []
        let result = await restored.drain { message in sent.append(message.text) }
        XCTAssertEqual(sent, ["中断中的话"])
        XCTAssertEqual(result.delivered, 1)
    }

    func testRetryFailedGivesOneMoreChance() async {
        let queue = OutboundMessageQueue(petID: "pet-1", container: container)
        queue.enqueue(text: "坏消息")
        for _ in 0..<OutboundMessageQueue.maxAttempts {
            await queue.drain { _ in throw PetJourneyError.requestFailed("拒绝") }
        }
        XCTAssertEqual(queue.failedCount, 1)

        // 死信出口：再给一次机会
        queue.retryFailed()
        XCTAssertEqual(queue.pendingCount, 1)
        XCTAssertEqual(queue.failedCount, 0)

        // 毒消息一轮后重新回到死信（有界，不会无限循环）
        await queue.drain { _ in throw PetJourneyError.requestFailed("拒绝") }
        XCTAssertEqual(queue.failedCount, 1)
    }

    func testEnqueueStoresClientMessageID() async {
        let queue = OutboundMessageQueue(petID: "pet-1", container: container)
        queue.enqueue(text: "带上幂等键", clientMessageID: "cmid-1")

        var ids: [String] = []
        await queue.drain { message in
            ids.append(message.clientMessageID)
        }

        XCTAssertEqual(ids, ["cmid-1"], "补发必须复用首次发送的幂等键")
    }

    func testExpiredCacheIsRejected() {
        let repository = JourneyCacheRepository(petID: "pet-1", container: container)
        repository.store(CityPosition(city: "京都", latitude: 35.0116, longitude: 135.7681), kind: .cityPosition)

        // 手动把 updatedAt 拨回 2 小时前（cityPosition TTL 为 1 小时）
        let context = container.mainContext
        let rows = try! context.fetch(FetchDescriptor<CachedPayload>())
        for row in rows {
            row.updatedAt = Date().addingTimeInterval(-2 * 60 * 60)
        }
        try? context.save()

        XCTAssertNil(repository.load(CityPosition.self, kind: .cityPosition), "超龄缓存不应再点亮 UI")
    }

    func testMediaCacheStoresAndPurges() async {
        let remote = URL(string: "http://example.test/photo/kyoto.jpg")!
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [StubURLProtocol.self]
        StubURLProtocol.reset()
        StubURLProtocol.handler = { request in
            let response = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!
            return (response, Data("jpeg-bytes".utf8))
        }
        defer { StubURLProtocol.reset() }

        let petID = "pet-media-\(UUID().uuidString)"
        let local = await MediaCache.fetch(url: remote, petID: petID, session: URLSession(configuration: configuration))
        XCTAssertNotNil(local)
        XCTAssertEqual(MediaCache.localURL(forRemote: remote, petID: petID), local)

        MediaCache.purge(petID: petID)
        XCTAssertNil(MediaCache.localURL(forRemote: remote, petID: petID))
    }
}
