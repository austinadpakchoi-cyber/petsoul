import Foundation

/// 网络层的类型化错误。业务层与 UI 只见 PetJourneyError，HTTP 细节止步于此。
enum APIError: Error, Equatable {
    case offline
    case timeout
    case server(status: Int, message: String)
    case unauthorized
    case decoding
    case transport(String)
}

extension APIError {
    /// 归一到业务层已有的 PetJourneyError，保持所有调用点无感。
    /// 连接类问题统一收敛为 offline：文案走信号语言，不暴露传输机制。
    var asPetJourneyError: PetJourneyError {
        switch self {
        case .offline, .timeout, .transport:
            return .offline
        case .unauthorized:
            return .sessionExpired
        case .server(_, let message):
            return .requestFailed(message)
        case .decoding:
            return .invalidResponse
        }
    }
}
