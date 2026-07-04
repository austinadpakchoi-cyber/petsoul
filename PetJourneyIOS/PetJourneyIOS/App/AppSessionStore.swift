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
        static let onboardingCompleted = "onboarding_completed"
        static let serviceMode = "service_mode"
        static let baseURL = "base_url"
    }

    private static let debugBackendBaseURLString = "http://192.168.31.237:8000"

    private let defaults: UserDefaults

    @Published private(set) var petID: String? {
        didSet {
            defaults.set(petID, forKey: Key.petID)
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

    init(userDefaults: UserDefaults = .standard) {
        defaults = userDefaults
        petID = userDefaults.string(forKey: Key.petID)
        onboardingCompleted = userDefaults.bool(forKey: Key.onboardingCompleted)
        serviceMode = ServiceMode(rawValue: userDefaults.string(forKey: Key.serviceMode) ?? "") ?? Self.defaultServiceMode(for: userDefaults)
        baseURLString = userDefaults.string(forKey: Key.baseURL) ?? Self.defaultBaseURLString(for: userDefaults)
    }

    var useMockData: Bool {
        serviceMode == .mock
    }

    func completeOnboarding(petID: String) {
        self.petID = petID
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
        petID = nil
        onboardingCompleted = false
    }

    private static func defaultServiceMode(for userDefaults: UserDefaults) -> ServiceMode {
        #if DEBUG
        if userDefaults === UserDefaults.standard {
            return .remote
        }
        #endif
        return .mock
    }

    private static func defaultBaseURLString(for userDefaults: UserDefaults) -> String {
        #if DEBUG
        if userDefaults === UserDefaults.standard {
            return debugBackendBaseURLString
        }
        #endif
        return "http://127.0.0.1:8000"
    }
}

@MainActor
final class ServiceContainer: ObservableObject {
    let journeyService: any PetJourneyService
    let networkMonitor: NetworkMonitor

    init(session: AppSessionStore, networkMonitor: NetworkMonitor? = nil) {
        self.networkMonitor = networkMonitor ?? NetworkMonitor()
        if session.serviceMode == .remote, let baseURL = URL(string: session.baseURLString) {
            journeyService = RemotePetJourneyService(baseURL: baseURL)
        } else {
            journeyService = MockPetJourneyService()
        }
    }
}
