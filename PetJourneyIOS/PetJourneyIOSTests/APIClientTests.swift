import XCTest
@testable import PetJourneyIOS

final class StubURLProtocol: URLProtocol {
    static var handler: ((URLRequest) throws -> (HTTPURLResponse, Data))?
    static var requestCount = 0

    static func reset() {
        handler = nil
        requestCount = 0
    }

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        Self.requestCount += 1
        guard let handler = Self.handler else {
            client?.urlProtocol(self, didFailWithError: URLError(.badServerResponse))
            return
        }
        do {
            let (response, data) = try handler(request)
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: data)
            client?.urlProtocolDidFinishLoading(self)
        } catch {
            client?.urlProtocol(self, didFailWithError: error)
        }
    }

    override func stopLoading() {}
}

private struct Payload: Codable, Equatable {
    var value: String
}

@MainActor
final class APIClientTests: XCTestCase {
    private var client: APIClient!

    override func setUp() {
        super.setUp()
        StubURLProtocol.reset()
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [StubURLProtocol.self]
        client = APIClient(
            baseURL: URL(string: "http://example.test")!,
            session: URLSession(configuration: configuration),
            sleeper: { _ in }
        )
    }

    override func tearDown() {
        StubURLProtocol.reset()
        client = nil
        super.tearDown()
    }

    private func makeResponse(_ url: URL, status: Int) -> HTTPURLResponse {
        HTTPURLResponse(url: url, statusCode: status, httpVersion: nil, headerFields: nil)!
    }

    func testIdempotentRequestRetriesServerErrorThenSucceeds() async throws {
        StubURLProtocol.handler = { request in
            let url = request.url!
            if StubURLProtocol.requestCount < 3 {
                return (self.makeResponse(url, status: 500), Data("暂时不可用".utf8))
            }
            return (self.makeResponse(url, status: 200), Data(#"{"value":"ok"}"#.utf8))
        }

        var request = URLRequest(url: client.endpoint("/ping"))
        request.httpMethod = "GET"
        let payload = try await client.send(Payload.self, request: request, retry: .idempotent)

        XCTAssertEqual(payload, Payload(value: "ok"))
        XCTAssertEqual(StubURLProtocol.requestCount, 3)
    }

    func testNonRetryRequestFailsImmediately() async {
        StubURLProtocol.handler = { request in
            (self.makeResponse(request.url!, status: 500), Data("失败".utf8))
        }

        var request = URLRequest(url: client.endpoint("/write"))
        request.httpMethod = "POST"
        do {
            _ = try await client.send(Payload.self, request: request, retry: .none)
            XCTFail("应当抛出 server 错误")
        } catch let error as APIError {
            XCTAssertEqual(error, .server(status: 500, message: "失败"))
        } catch {
            XCTFail("错误类型不符: \(error)")
        }
        XCTAssertEqual(StubURLProtocol.requestCount, 1)
    }

    func testClientErrorIsNotRetried() async {
        StubURLProtocol.handler = { request in
            (self.makeResponse(request.url!, status: 404), Data("不存在".utf8))
        }

        var request = URLRequest(url: client.endpoint("/missing"))
        request.httpMethod = "GET"
        do {
            _ = try await client.send(Payload.self, request: request, retry: .idempotent)
            XCTFail("应当抛出 server 错误")
        } catch let error as APIError {
            XCTAssertEqual(error, .server(status: 404, message: "不存在"))
        } catch {
            XCTFail("错误类型不符: \(error)")
        }
        XCTAssertEqual(StubURLProtocol.requestCount, 1)
    }

    func testOfflineMapsToSignalLanguage() async {
        StubURLProtocol.handler = { _ in
            throw URLError(.notConnectedToInternet)
        }

        var request = URLRequest(url: client.endpoint("/ping"))
        request.httpMethod = "GET"
        do {
            _ = try await client.send(Payload.self, request: request, retry: .none)
            XCTFail("应当抛出 offline")
        } catch let error as APIError {
            XCTAssertEqual(error, .offline)
            XCTAssertEqual(error.asPetJourneyError, .offline)
            let description = error.asPetJourneyError.errorDescription ?? ""
            XCTAssertTrue(description.contains("信号"), "离线文案要用信号语言: \(description)")
        } catch {
            XCTFail("错误类型不符: \(error)")
        }
    }

    func testUnauthorizedMapsToSessionExpired() async {
        StubURLProtocol.handler = { request in
            (self.makeResponse(request.url!, status: 401), Data("expired".utf8))
        }

        var request = URLRequest(url: client.endpoint("/ping"))
        request.httpMethod = "GET"
        do {
            _ = try await client.send(Payload.self, request: request, retry: .none)
            XCTFail("应当抛出 unauthorized")
        } catch let error as APIError {
            XCTAssertEqual(error, .unauthorized)
            XCTAssertEqual(error.asPetJourneyError, .sessionExpired)
            let description = error.asPetJourneyError.errorDescription ?? ""
            XCTAssertTrue(description.contains("重新登录"), "401 文案要提示重新登录: \(description)")
        } catch {
            XCTFail("错误类型不符: \(error)")
        }
        XCTAssertEqual(StubURLProtocol.requestCount, 1)
    }

    func testDecodingFailureMapsToInvalidResponse() async {
        StubURLProtocol.handler = { request in
            (self.makeResponse(request.url!, status: 200), Data("not-json".utf8))
        }

        var request = URLRequest(url: client.endpoint("/ping"))
        request.httpMethod = "GET"
        do {
            _ = try await client.send(Payload.self, request: request, retry: .none)
            XCTFail("应当抛出 decoding")
        } catch let error as APIError {
            XCTAssertEqual(error, .decoding)
            XCTAssertEqual(error.asPetJourneyError, .invalidResponse)
        } catch {
            XCTFail("错误类型不符: \(error)")
        }
    }

    func testRetryPolicyDelaysGrowExponentially() {
        let policy = RetryPolicy.idempotent
        XCTAssertEqual(policy.delay(beforeAttempt: 1), 0)
        let second = policy.delay(beforeAttempt: 2)
        let third = policy.delay(beforeAttempt: 3)
        XCTAssertTrue((0.5...0.625).contains(second), "第二次尝试应在 0.5s 基础上加抖动: \(second)")
        XCTAssertTrue((1.0...1.25).contains(third), "第三次尝试应在 1s 基础上加抖动: \(third)")
    }

    func testNetworkMonitorPublishesChanges() {
        let monitor = NetworkMonitor(startsMonitoring: false)
        XCTAssertTrue(monitor.isOnline)
        monitor.apply(isOnline: false)
        XCTAssertFalse(monitor.isOnline)
        monitor.apply(isOnline: true)
        XCTAssertTrue(monitor.isOnline)
    }

    // MARK: - 地图昼夜相位与墙上时间（UI/UX 审计 P0-2）

    func testNaiveWallTimeDecodesAsGMTHour() throws {
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .custom { decoder in
            try RemoteDateDecoding.decodeFlexibleISO8601Date(from: decoder)
        }
        struct Payload: Decodable { var localTime: Date }
        let json = Data(#"{"localTime":"2026-08-27T01:23:45"}"#.utf8)
        let payload = try decoder.decode(Payload.self, from: json)
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(secondsFromGMT: 0)!
        let hour = calendar.component(.hour, from: payload.localTime)
        XCTAssertEqual(hour, 1, "墙上时间必须按 GMT 解析，小时分量即 TA 所在地小时")
    }

    func testMapPhaseFollowsPetLocalWallTime() {
        let petCalendar = JourneyMapAtmosphere.petLocalCalendar
        var date = DateComponents(calendar: petCalendar, year: 2026, month: 8, day: 27, hour: 1, minute: 30)
        let nightLocal = petCalendar.date(from: date)!
        date.hour = 10
        let dayLocal = petCalendar.date(from: date)!

        XCTAssertEqual(JourneyMapAtmosphere.phase(for: nightLocal, calendar: petCalendar), .night)
        XCTAssertEqual(JourneyMapAtmosphere.phase(for: dayLocal, calendar: petCalendar), .day)
        // 同一 UTC 时刻下，TA 当地时间不同 → 相位不同（这正是审计验收第 3 条）
        XCTAssertNotEqual(
            JourneyMapAtmosphere.phase(for: nightLocal, calendar: petCalendar),
            JourneyMapAtmosphere.phase(for: dayLocal, calendar: petCalendar)
        )
    }
}
