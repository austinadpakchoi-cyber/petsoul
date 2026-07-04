import UIKit
import UserNotifications

final class PetJourneyAppDelegate: NSObject, UIApplicationDelegate, UNUserNotificationCenterDelegate {
    func application(
        _ application: UIApplication,
        didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil
    ) -> Bool {
        UNUserNotificationCenter.current().delegate = self
        return true
    }

    func application(
        _ application: UIApplication,
        didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data
    ) {
        let token = deviceToken.map { String(format: "%02x", $0) }.joined()
        Task { @MainActor in
            PetPushRegistrationCoordinator.shared.didRegister(deviceToken: token)
        }
    }

    func application(
        _ application: UIApplication,
        didFailToRegisterForRemoteNotificationsWithError error: Error
    ) {
        Task { @MainActor in
            PetPushRegistrationCoordinator.shared.didFailToRegister(error)
        }
    }

    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        willPresent notification: UNNotification
    ) async -> UNNotificationPresentationOptions {
        [.banner, .sound, .badge]
    }
}

@MainActor
final class PetPushRegistrationCoordinator: ObservableObject {
    static let shared = PetPushRegistrationCoordinator()

    private var service: (any PetJourneyService)?
    private var petID: String?
    private var currentDeviceToken: String?
    private var lastRegisteredKey: String?
    private var authorizationRequested = false
    private var registrationTask: Task<Void, Never>?

    private init() {}

    func configure(petID: String?, service: any PetJourneyService) {
        self.petID = petID
        self.service = service

        guard petID != nil else {
            registrationTask?.cancel()
            return
        }

        if let currentDeviceToken {
            register(deviceToken: currentDeviceToken)
        }
    }

    func requestAuthorizationForUserMoment() {
        guard petID != nil else { return }
        requestAuthorizationIfNeeded()
    }

    func didRegister(deviceToken: String) {
        currentDeviceToken = deviceToken
        register(deviceToken: deviceToken)
    }

    func didFailToRegister(_ error: Error) {
        registrationTask?.cancel()
    }

    private func requestAuthorizationIfNeeded() {
        guard !authorizationRequested else { return }
        authorizationRequested = true

        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound, .badge]) { granted, _ in
            guard granted else { return }
            DispatchQueue.main.async {
                UIApplication.shared.registerForRemoteNotifications()
            }
        }
    }

    private func register(deviceToken: String) {
        guard let petID, let service else { return }
        let registrationKey = "\(petID):\(deviceToken)"
        guard lastRegisteredKey != registrationKey else { return }

        registrationTask?.cancel()
        registrationTask = Task {
            do {
                _ = try await service.registerPushDevice(
                    DeviceRegistrationRequest(
                        petID: petID,
                        deviceToken: deviceToken,
                        platform: "ios",
                        environment: Self.apnsEnvironment
                    )
                )
                lastRegisteredKey = registrationKey
            } catch {
                return
            }
        }
    }

    private static var apnsEnvironment: String {
        #if DEBUG
        "sandbox"
        #else
        "production"
        #endif
    }
}
