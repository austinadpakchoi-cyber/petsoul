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
}
