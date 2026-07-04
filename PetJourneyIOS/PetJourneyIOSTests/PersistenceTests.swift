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
        await queue.drain { text in
            sent.append(text)
        }

        XCTAssertEqual(sent, ["第一句", "第二句"])
        XCTAssertEqual(queue.pendingCount, 0)
    }

    func testOutboxStopsOnFailureAndKeepsRemaining() async {
        let queue = OutboundMessageQueue(petID: "pet-1", container: container)
        queue.enqueue(text: "第一句")
        queue.enqueue(text: "第二句")

        var attempted: [String] = []
        await queue.drain { text in
            attempted.append(text)
            throw PetJourneyError.offline
        }

        XCTAssertEqual(attempted, ["第一句"])
        XCTAssertEqual(queue.pendingCount, 2, "失败的和未尝试的都应留在队列里")
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
