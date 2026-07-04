import Foundation

/// 账户体系的接缝：将来接入登录后，换成携带 token 的实现即可，网络层与业务协议不用改。
protocol AuthProviding: Sendable {
    func authHeaders() async -> [String: String]
}

struct NoAuthProvider: AuthProviding {
    func authHeaders() async -> [String: String] { [:] }
}
