import Foundation

/// 统一 HTTP 客户端：负责重试、错误归一与 JSON 编解码。业务服务只组请求，不碰传输细节。
@MainActor
final class APIClient {
    let baseURL: URL
    let decoder: JSONDecoder
    let encoder: JSONEncoder

    private let session: URLSession
    private let authProvider: AuthProviding
    private let sleeper: (TimeInterval) async -> Void

    /// sleeper 可注入以便测试中跳过真实退避等待。
    init(
        baseURL: URL,
        session: URLSession = .shared,
        authProvider: AuthProviding = NoAuthProvider(),
        sleeper: @escaping (TimeInterval) async -> Void = { seconds in
            try? await Task.sleep(nanoseconds: UInt64(seconds * 1_000_000_000))
        }
    ) {
        self.baseURL = baseURL
        self.session = session
        self.authProvider = authProvider
        self.sleeper = sleeper
        decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .custom { decoder in
            try RemoteDateDecoding.decodeFlexibleISO8601Date(from: decoder)
        }
        encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
    }

    func endpoint(_ path: String) -> URL {
        let base = baseURL.absoluteString.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        return URL(string: base + path)!
    }

    func send<T: Decodable>(_ type: T.Type, request: URLRequest, retry: RetryPolicy = .none) async throws -> T {
        let data = try await sendData(request: request, retry: retry)
        do {
            return try decoder.decode(T.self, from: data)
        } catch {
            throw APIError.decoding
        }
    }

    func sendData(request: URLRequest, retry: RetryPolicy = .none) async throws -> Data {
        var request = request
        for (header, value) in await authProvider.authHeaders() {
            request.setValue(value, forHTTPHeaderField: header)
        }

        var attempt = 1
        while true {
            do {
                return try await performOnce(request)
            } catch let error as APIError {
                guard attempt < retry.maxAttempts, RetryPolicy.isRetryable(error) else {
                    throw error
                }
                attempt += 1
                await sleeper(retry.delay(beforeAttempt: attempt))
            }
        }
    }

    private func performOnce(_ request: URLRequest) async throws -> Data {
        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await session.data(for: request)
        } catch let urlError as URLError {
            switch urlError.code {
            case .notConnectedToInternet, .networkConnectionLost, .dataNotAllowed,
                 .cannotConnectToHost, .cannotFindHost, .dnsLookupFailed:
                throw APIError.offline
            case .timedOut:
                throw APIError.timeout
            case .cancelled:
                throw CancellationError()
            default:
                throw APIError.transport(urlError.localizedDescription)
            }
        }
        guard let httpResponse = response as? HTTPURLResponse else {
            throw APIError.transport("非 HTTP 响应")
        }
        if httpResponse.statusCode == 401 {
            throw APIError.unauthorized
        }
        guard (200..<300).contains(httpResponse.statusCode) else {
            let message = String(data: data, encoding: .utf8) ?? "请求失败"
            throw APIError.server(status: httpResponse.statusCode, message: message)
        }
        return data
    }
}

enum RemoteDateDecoding {
    static func decodeFlexibleISO8601Date(from decoder: Decoder) throws -> Date {
        let container = try decoder.singleValueContainer()
        let value = try container.decode(String.self)

        let fractionalFormatter = ISO8601DateFormatter()
        fractionalFormatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let date = fractionalFormatter.date(from: value) {
            return date
        }

        let plainFormatter = ISO8601DateFormatter()
        plainFormatter.formatOptions = [.withInternetDateTime]
        if let date = plainFormatter.date(from: value) {
            return date
        }

        throw DecodingError.dataCorruptedError(
            in: container,
            debugDescription: "Invalid ISO8601 date: \(value)"
        )
    }
}
