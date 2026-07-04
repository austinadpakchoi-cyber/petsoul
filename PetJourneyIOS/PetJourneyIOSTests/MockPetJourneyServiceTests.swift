import XCTest
@testable import PetJourneyIOS

@MainActor
final class MockPetJourneyServiceTests: XCTestCase {
    func testCreatePetAndFetchStatus() async throws {
        let service = MockPetJourneyService()
        let response = try await service.createPet(request: CreatePetRequest(
            name: "小黑",
            petType: .dog,
            photoData: nil,
            photoFilename: nil,
            dna: .fallback
        ))

        let status = try await service.fetchAgentStatus(petID: response.petID)

        XCTAssertTrue(response.success)
        XCTAssertEqual(status.name, "小黑")
        XCTAssertEqual(status.agentState.location, "厦门")
        XCTAssertFalse(status.agentState.thoughts.isEmpty)
        XCTAssertNotNil(response.photoURL)
    }

    func testFeedbackStoresUserGuidePreferenceWithoutOwningPetMood() async throws {
        let service = MockPetJourneyService()
        let response = try await service.createPet(request: CreatePetRequest(
            name: "团团",
            petType: .cat,
            photoData: nil,
            photoFilename: nil,
            dna: .fallback
        ))

        let before = try await service.fetchAgentStatus(petID: response.petID)
        let feedback = try await service.sendFeedback(FeedbackRequest(
            petID: response.petID,
            city: before.agentState.location,
            liked: true
        ))

        XCTAssertTrue(feedback.success)
        XCTAssertTrue(feedback.message.contains("攻略"))
        XCTAssertTrue(feedback.message.contains("自己的节奏"))
        XCTAssertEqual(feedback.updatedStatus?.agentState.latestThought?.tone, "guide_saved")
    }

    func testMockPostcardArrivesAfterElapsedTime() async throws {
        let service = MockPetJourneyService()
        let response = try await service.createPet(request: CreatePetRequest(
            name: "阿布",
            petType: .dog,
            photoData: nil,
            photoFilename: nil,
            dna: .fallback
        ))

        service.simulateElapsedTime(50, for: response.petID)
        let status = try await service.fetchAgentStatus(petID: response.petID)

        XCTAssertEqual(status.postcards.count, 1)
        XCTAssertTrue(status.postcards.first?.location.contains(status.agentState.location) == true)
        XCTAssertNotNil(status.postcards.first?.imageURL)
    }

    func testCommunicatorAcknowledgementFeelsNatural() async throws {
        let service = MockPetJourneyService()
        let response = try await service.createPet(request: CreatePetRequest(
            name: "小福",
            petType: .dog,
            photoData: nil,
            photoFilename: nil,
            dna: .fallback
        ))

        let reply = try await service.sendCommunicatorMessage(
            petID: response.petID,
            request: CommunicatorSendRequest(text: "好滴 我看看")
        )
        let text = reply.messages.map(\.text).joined(separator: " ")

        XCTAssertEqual(reply.intent, .confirmPendingPhoto)
        XCTAssertTrue(
            reply.messages.flatMap { $0.attachments }.contains { $0.type == .photoPlaceholder },
            "确认看照片应该展示照片准备卡，而不是只回一段文字"
        )
        XCTAssertFalse(text.contains("我听见你说"))
        XCTAssertFalse(text.contains("通讯器"))
        XCTAssertFalse(text.contains("自己的节奏"))
        XCTAssertTrue(text.contains("嗯嗯") || text.contains("照片"))
    }

    func testCommunicatorPhotoShareCreatesOwnerPhotoMessage() async throws {
        let service = MockPetJourneyService()
        let response = try await service.createPet(request: CreatePetRequest(
            name: "小福",
            petType: .dog,
            photoData: nil,
            photoFilename: nil,
            dna: .fallback
        ))

        let reply = try await service.sendCommunicatorPhoto(
            petID: response.petID,
            imageData: Data([0xFF, 0xD8, 0xFF, 0xD9]),
            caption: "给你看一下今天的光"
        )

        XCTAssertEqual(reply.intent, .ownerPhotoShare)
        XCTAssertEqual(reply.ownerMessage.sender, .owner)
        XCTAssertTrue(reply.ownerMessage.attachments.contains { $0.type == .ownerPhoto && $0.photoURL != nil })
        XCTAssertTrue(reply.messages.map(\.text).joined(separator: " ").contains("我看到啦"))
    }

    func testMockTranslationAndRoutePlanAreAvailable() async throws {
        let service = MockPetJourneyService()
        let response = try await service.createPet(request: CreatePetRequest(
            name: "小黑",
            petType: .dog,
            photoData: nil,
            photoFilename: nil,
            dna: .fallback
        ))

        let status = try await service.fetchAgentStatus(petID: response.petID)
        let thought = try XCTUnwrap(status.agentState.latestThought)
        let translation = try await service.fetchThoughtTranslation(petID: response.petID, thoughtID: thought.id)
        let journeyPlan = try await service.fetchJourneyPlan(petID: response.petID)
        let routePlan = try await service.fetchRoutePlan(petID: response.petID)

        XCTAssertTrue(thought.translationAvailable)
        XCTAssertEqual(translation.thoughtID, thought.id)
        XCTAssertFalse(translation.translation.isEmpty)
        XCTAssertEqual(journeyPlan.transportDecision.selectedMode, .walk)
        XCTAssertTrue(journeyPlan.stops.contains { $0.photoCandidate })
        XCTAssertEqual(routePlan.provider, journeyPlan.provider)
        XCTAssertTrue(routePlan.places.count >= 5)
        XCTAssertEqual(routePlan.city, status.agentState.location)
    }
}
