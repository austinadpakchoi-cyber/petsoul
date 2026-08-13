import Foundation

/// 请求重试策略。只有幂等读取用 .idempotent；写请求一律 .none，避免重复副作用。
struct RetryPolicy: Equatable, Sendable {
    var maxAttempts: Int
    var baseDelay: TimeInterval

    static let none = RetryPolicy(maxAttempts: 1, baseDelay: 0)
    static let idempotent = RetryPolicy(maxAttempts: 3, baseDelay: 0.5)

    /// 第 attempt 次尝试前应等待的时长（attempt 从 1 计，首次不等待）。
    /// 指数退避 0.5s/1s/2s… 外加最多 25% 抖动，避免同时重连。
    func delay(beforeAttempt attempt: Int) -> TimeInterval {
        guard attempt > 1, baseDelay > 0 else { return 0 }
        let exponential = baseDelay * pow(2, Double(attempt - 2))
        let jitter = Double.random(in: 0...(exponential * 0.25))
        return exponential + jitter
    }

    static func isRetryable(_ error: APIError) -> Bool {
        switch error {
        case .offline, .timeout, .transport:
            return true
        case .server(let status, _):
            return (500...599).contains(status)
        case .decoding, .unauthorized:
            return false
        }
    }
}
