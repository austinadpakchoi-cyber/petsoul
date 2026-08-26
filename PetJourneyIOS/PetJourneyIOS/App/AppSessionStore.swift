import Foundation
import UIKit

/// 当前宠物形象的本地存储。头像等 UI 必须围绕“当前宠物”动态生成，不允许内置某只测试宠物的素材。
@MainActor
enum PetAvatarStore {
    private static var cache: [String: UIImage] = [:]

    static func save(_ data: Data, petID: String) {
        guard let image = UIImage(data: data) else { return }
        let normalized = image.petSoulAvatarNormalized(maxDimension: 512)
        cache[petID] = normalized
        guard let jpeg = normalized.jpegData(compressionQuality: 0.86),
              let url = try? fileURL(for: petID, createDirectory: true) else { return }
        try? jpeg.write(to: url, options: .atomic)
    }

    static func image(for petID: String) -> UIImage? {
        if let cached = cache[petID] { return cached }
        guard let url = try? fileURL(for: petID, createDirectory: false),
              let data = try? Data(contentsOf: url),
              let image = UIImage(data: data) else { return nil }
        cache[petID] = image
        return image
    }

    private static func fileURL(for petID: String, createDirectory: Bool) throws -> URL {
        let base = try FileManager.default.url(
            for: .applicationSupportDirectory,
            in: .userDomainMask,
            appropriateFor: nil,
            create: createDirectory
        )
        let directory = base.appendingPathComponent("PetAvatars", isDirectory: true)
        if createDirectory {
            try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        }
        let safeID = petID.replacingOccurrences(of: "/", with: "_")
        return directory.appendingPathComponent("\(safeID).jpg")
    }
}

private extension UIImage {
    func petSoulAvatarNormalized(maxDimension: CGFloat) -> UIImage {
        let largest = max(size.width, size.height)
        guard largest > maxDimension, largest > 0 else { return self }
        let scaleFactor = maxDimension / largest
        let newSize = CGSize(width: size.width * scaleFactor, height: size.height * scaleFactor)
        let renderer = UIGraphicsImageRenderer(size: newSize)
        return renderer.image { _ in
            draw(in: CGRect(origin: .zero, size: newSize))
        }
    }
}

@MainActor
final class AppSessionStore: ObservableObject {
    enum ServiceMode: String, CaseIterable {
        case mock
        case remote
    }

    private enum Key {
        static let petID = "pet_id"
        static let petName = "pet_name"
        static let onboardingCompleted = "onboarding_completed"
        static let serviceMode = "service_mode"
        static let baseURL = "base_url"
        static let authToken = "auth_token"
        static let userID = "auth_user_id"
        static let userDisplayName = "auth_user_display_name"
    }

    private static let productionBackendBaseURLString = "https://api.petsoul.games"
    /// 旧的本地开发地址：后端已迁移到云端，启动时自动替换存量配置
    private static let legacyBaseURLStrings: Set<String> = [
        "http://192.168.31.237:8000",
        "http://127.0.0.1:8000"
    ]

    private let defaults: UserDefaults

    @Published private(set) var petID: String? {
        didSet {
            defaults.set(petID, forKey: Key.petID)
        }
    }

    @Published private(set) var petName: String? {
        didSet {
            defaults.set(petName, forKey: Key.petName)
        }
    }

    @Published private(set) var onboardingCompleted: Bool {
        didSet {
            defaults.set(onboardingCompleted, forKey: Key.onboardingCompleted)
        }
    }

    @Published var serviceMode: ServiceMode {
        didSet {
            defaults.set(serviceMode.rawValue, forKey: Key.serviceMode)
        }
    }

    @Published var baseURLString: String {
        didSet {
            defaults.set(baseURLString, forKey: Key.baseURL)
        }
    }

    @Published private(set) var authToken: String? {
        didSet {
            defaults.set(authToken, forKey: Key.authToken)
        }
    }

    @Published private(set) var userID: String? {
        didSet {
            defaults.set(userID, forKey: Key.userID)
        }
    }

    @Published private(set) var userDisplayName: String? {
        didSet {
            defaults.set(userDisplayName, forKey: Key.userDisplayName)
        }
    }

    init(userDefaults: UserDefaults = .standard) {
        defaults = userDefaults
        petID = userDefaults.string(forKey: Key.petID)
        petName = userDefaults.string(forKey: Key.petName)
        onboardingCompleted = userDefaults.bool(forKey: Key.onboardingCompleted)
        serviceMode = ServiceMode(rawValue: userDefaults.string(forKey: Key.serviceMode) ?? "") ?? Self.defaultServiceMode(for: userDefaults)
        let storedBaseURL = userDefaults.string(forKey: Key.baseURL)
        if let storedBaseURL, !Self.legacyBaseURLStrings.contains(storedBaseURL) {
            baseURLString = storedBaseURL
        } else {
            baseURLString = Self.defaultBaseURLString(for: userDefaults)
        }
        authToken = userDefaults.string(forKey: Key.authToken)
        userID = userDefaults.string(forKey: Key.userID)
        userDisplayName = userDefaults.string(forKey: Key.userDisplayName)
    }

    var isSignedIn: Bool {
        authToken != nil && userID != nil
    }

    func storeAuthSession(token: String, userID: String, displayName: String?) {
        authToken = token
        self.userID = userID
        if let displayName, !displayName.isEmpty {
            userDisplayName = displayName
        }
    }

    func signOut() {
        authToken = nil
        userID = nil
        userDisplayName = nil
        resetJourney()
    }

    var useMockData: Bool {
        serviceMode == .mock
    }

    func completeOnboarding(petID: String, petName: String? = nil) {
        self.petID = petID
        if let petName, !petName.isEmpty {
            self.petName = petName
        }
        onboardingCompleted = true
    }

    func updateBaseURL(_ value: String) {
        baseURLString = value
    }

    func switchToMock() {
        serviceMode = .mock
    }

    func switchToRemote() {
        serviceMode = .remote
    }

    func resetJourney() {
        if let petID {
            JourneyCacheRepository.purge(petID: petID)
            OutboundMessageQueue.purge(petID: petID)
            MediaCache.purge(petID: petID)
        }
        petID = nil
        petName = nil
        onboardingCompleted = false
    }

    private static func defaultServiceMode(for userDefaults: UserDefaults) -> ServiceMode {
        #if DEBUG
        // 测试/预览环境（非 standard 的 UserDefaults suite）默认 Mock，避免测试碰网络
        if userDefaults !== UserDefaults.standard {
            return .mock
        }
        #endif
        // Release 与 DEBUG 真机一律默认 remote：TestFlight/App Store 包
        // 必须直连生产账号体系，不允许首发即样板数据。
        return .remote
    }

    private static func defaultBaseURLString(for userDefaults: UserDefaults) -> String {
        #if DEBUG
        if userDefaults !== UserDefaults.standard {
            // 仅测试环境占位，Mock 服务不会真正发起请求
            return "http://127.0.0.1:8000"
        }
        // 本地联调：可用 PETJOURNEY_BASE_URL 环境变量指向本机后端
        if let override = ProcessInfo.processInfo.environment["PETJOURNEY_BASE_URL"],
           !override.isEmpty {
            return override
        }
        #endif
        return productionBackendBaseURLString
    }
}

@MainActor
final class ServiceContainer: ObservableObject {
    let journeyService: any PetJourneyService
    let networkMonitor: NetworkMonitor

    init(session: AppSessionStore, networkMonitor: NetworkMonitor? = nil) {
        self.networkMonitor = networkMonitor ?? NetworkMonitor()
        if session.serviceMode == .remote, let baseURL = URL(string: session.baseURLString) {
            let remote = RemotePetJourneyService(baseURL: baseURL)
            remote.authTokenProvider = { [weak session] in session?.authToken }
            journeyService = remote
        } else {
            journeyService = MockPetJourneyService()
        }
    }
}
