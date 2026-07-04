import XCTest
@testable import PetJourneyIOS

@MainActor
final class PushDeepLinkRouterTests: XCTestCase {
    func testParsesCategoryFromApsPayload() {
        let router = PushDeepLinkRouter()
        router.handle(userInfo: [
            "aps": ["category": "postcard"],
            "pet_id": "pet-1",
            "postcard_id": "pc-9"
        ])
        XCTAssertEqual(router.pending, .postcard(petID: "pet-1"))
    }

    func testParsesMessageAndMomentCategories() {
        let router = PushDeepLinkRouter()
        router.handle(userInfo: ["aps": ["category": "message"], "pet_id": "pet-1"])
        XCTAssertEqual(router.pending, .message(petID: "pet-1"))
        router.handle(userInfo: ["aps": ["category": "moment_created"], "pet_id": "pet-1"])
        XCTAssertEqual(router.pending, .moment(petID: "pet-1"))
    }

    func testConsumeClearsPending() {
        let router = PushDeepLinkRouter()
        router.handle(userInfo: ["aps": ["category": "thought"], "pet_id": "pet-1"])
        XCTAssertEqual(router.consume(), .thought(petID: "pet-1"))
        XCTAssertNil(router.pending)
        XCTAssertNil(router.consume())
    }

    func testUnknownCategoryIsIgnored() {
        let router = PushDeepLinkRouter()
        router.handle(userInfo: ["aps": ["category": "unknown"]])
        XCTAssertNil(router.pending)
    }
}
