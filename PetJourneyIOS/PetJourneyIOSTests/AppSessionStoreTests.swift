import XCTest
@testable import PetJourneyIOS

@MainActor
final class AppSessionStoreTests: XCTestCase {
    func testCompletesRestoresAndResetsSession() {
        let suiteName = "PetJourneyIOS.AppSessionStoreTests.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suiteName)!
        defaults.removePersistentDomain(forName: suiteName)

        let store = AppSessionStore(userDefaults: defaults)
        XCTAssertFalse(store.onboardingCompleted)
        XCTAssertNil(store.petID)

        store.completeOnboarding(petID: "PJ-TEST")

        let restored = AppSessionStore(userDefaults: defaults)
        XCTAssertTrue(restored.onboardingCompleted)
        XCTAssertEqual(restored.petID, "PJ-TEST")
        XCTAssertEqual(restored.serviceMode, .mock)

        restored.resetJourney()

        let reset = AppSessionStore(userDefaults: defaults)
        XCTAssertFalse(reset.onboardingCompleted)
        XCTAssertNil(reset.petID)
    }

    func testStoresAuthSessionAndSignsOut() {
        let suiteName = "PetJourneyIOS.AppSessionStoreTests.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suiteName)!
        defaults.removePersistentDomain(forName: suiteName)

        let store = AppSessionStore(userDefaults: defaults)
        XCTAssertFalse(store.isSignedIn)

        store.storeAuthSession(token: "token-1", userID: "user-1", displayName: "本地旅人")
        XCTAssertTrue(store.isSignedIn)
        XCTAssertEqual(store.userDisplayName, "本地旅人")

        let restored = AppSessionStore(userDefaults: defaults)
        XCTAssertTrue(restored.isSignedIn)
        XCTAssertEqual(restored.userDisplayName, "本地旅人")

        restored.signOut()

        let signedOut = AppSessionStore(userDefaults: defaults)
        XCTAssertFalse(signedOut.isSignedIn)
        XCTAssertNil(signedOut.authToken)
        XCTAssertNil(signedOut.userID)
    }

    func testSignOutClearsLocalJourney() {
        let suiteName = "PetJourneyIOS.AppSessionStoreTests.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suiteName)!
        defaults.removePersistentDomain(forName: suiteName)

        let store = AppSessionStore(userDefaults: defaults)
        store.completeOnboarding(petID: "PJ-TEST", petName: "小福")
        store.storeAuthSession(token: "token-1", userID: "user-1", displayName: nil)

        store.signOut()

        XCTAssertNil(store.petID)
        XCTAssertNil(store.petName)
        XCTAssertFalse(store.onboardingCompleted)
    }

    func testCompleteOnboardingStoresPetName() {
        let suiteName = "PetJourneyIOS.AppSessionStoreTests.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suiteName)!
        defaults.removePersistentDomain(forName: suiteName)

        let store = AppSessionStore(userDefaults: defaults)
        store.completeOnboarding(petID: "PJ-TEST", petName: "小黑")

        let restored = AppSessionStore(userDefaults: defaults)
        XCTAssertEqual(restored.petID, "PJ-TEST")
        XCTAssertEqual(restored.petName, "小黑")
    }
}
