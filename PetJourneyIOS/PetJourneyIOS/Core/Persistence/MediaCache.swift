import CryptoKit
import Foundation

/// 明信片、照片等情感资产的本地落盘缓存：一次收到就永远都在，不随视图折叠或断网丢失。
enum MediaCache {
    /// 已缓存则返回本地文件，否则 nil（调用方回退远端 URL）。
    static func localURL(forRemote url: URL, petID: String) -> URL? {
        guard let target = try? fileURL(for: url, petID: petID, createDirectory: false),
              FileManager.default.fileExists(atPath: target.path) else { return nil }
        return target
    }

    /// 已缓存直接返回；否则下载落盘。失败返回 nil，调用方继续用远端 URL 展示。
    static func fetch(url: URL, petID: String, session: URLSession = .shared) async -> URL? {
        if let local = localURL(forRemote: url, petID: petID) {
            return local
        }
        guard let (data, response) = try? await session.data(from: url),
              let http = response as? HTTPURLResponse,
              (200..<300).contains(http.statusCode),
              let target = try? fileURL(for: url, petID: petID, createDirectory: true) else { return nil }
        do {
            try data.write(to: target, options: .atomic)
            return target
        } catch {
            return nil
        }
    }

    static func purge(petID: String) {
        guard let directory = try? baseDirectory(petID: petID, create: false) else { return }
        try? FileManager.default.removeItem(at: directory)
    }

    private static func baseDirectory(petID: String, create: Bool) throws -> URL {
        let base = try FileManager.default.url(
            for: .applicationSupportDirectory,
            in: .userDomainMask,
            appropriateFor: nil,
            create: create
        )
        let safeID = petID.replacingOccurrences(of: "/", with: "_")
        let directory = base
            .appendingPathComponent("PetMedia", isDirectory: true)
            .appendingPathComponent(safeID, isDirectory: true)
        if create {
            try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        }
        return directory
    }

    private static func fileURL(for url: URL, petID: String, createDirectory: Bool) throws -> URL {
        let digest = SHA256.hash(data: Data(url.absoluteString.utf8))
        let name = digest.map { String(format: "%02x", $0) }.joined()
        let ext = url.pathExtension.isEmpty ? "bin" : url.pathExtension
        return try baseDirectory(petID: petID, create: createDirectory)
            .appendingPathComponent("\(name).\(ext)")
    }
}
