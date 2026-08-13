import Foundation

@MainActor
extension JourneyViewModel {
    func sendOwnerMessage(_ message: String) async {
        let clean = message.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !clean.isEmpty, !isSendingOwnerMessage else { return }
        let receiptID = UUID()
        appendOwnerMessageReceipt(
            OwnerMessageReceipt(
                id: receiptID,
                text: clean,
                timestamp: Date(),
                state: .sending,
                response: nil,
                decision: nil
            )
        )
        isSendingOwnerMessage = true
        defer { isSendingOwnerMessage = false }

        do {
            let response = try await service.sendOwnerMessage(
                petID: petID,
                request: OwnerMessageRequest(message: clean, intentHint: "owner_suggestion_or_companion_message")
            )
            updateOwnerMessageReceipt(
                id: receiptID,
                state: .delivered,
                response: response.message,
                decision: response.decision
            )
            toastMessage = response.message
            if let updatedStatus = response.updatedStatus {
                status = updatedStatus
                visibleThoughtTranslation = nil
                lastPostcardCount = updatedStatus.postcards.count
            } else {
                await refreshStatus()
            }
            await refreshPhotoMission()
        } catch {
            // 断网时不丢话：先收进发件队列，信号恢复后由 drainOutboxIfNeeded 自动送出。
            if case PetJourneyError.offline = error {
                outbox.enqueue(text: clean)
                updateOwnerMessageReceipt(
                    id: receiptID,
                    state: .sending,
                    response: "信号暂时没有接通，这句话已经收好，恢复后会自动送出。",
                    decision: nil
                )
                toastMessage = "这句话已经收好，信号恢复后会自动送出。"
            } else {
                updateOwnerMessageReceipt(
                    id: receiptID,
                    state: .failed,
                    response: "这句话暂时没有送到，等信号好一点可以再发一次。",
                    decision: nil
                )
                toastMessage = "这条讯息没有送达，等信号好一点再试。"
            }
        }
    }

    func sendFeedback(liked: Bool) async {
        guard let city = status?.agentState.location else { return }
        do {
            let response = try await service.sendFeedback(
                FeedbackRequest(petID: petID, city: city, liked: liked)
            )
            toastMessage = response.message
            if let updatedStatus = response.updatedStatus {
                status = updatedStatus
                visibleThoughtTranslation = nil
                lastPostcardCount = updatedStatus.postcards.count
            } else {
                await refreshStatus()
            }
        } catch {
            toastMessage = "这次回应没有送达。"
        }
    }

    func appendOwnerMessageReceipt(_ receipt: OwnerMessageReceipt) {
        ownerMessageReceipts.append(receipt)
        if ownerMessageReceipts.count > 5 {
            ownerMessageReceipts.removeFirst(ownerMessageReceipts.count - 5)
        }
    }

    func updateOwnerMessageReceipt(
        id: UUID,
        state: OwnerMessageReceipt.DeliveryState,
        response: String?,
        decision: String?
    ) {
        guard let index = ownerMessageReceipts.firstIndex(where: { $0.id == id }) else { return }
        ownerMessageReceipts[index].state = state
        ownerMessageReceipts[index].response = response
        ownerMessageReceipts[index].decision = decision
    }
}
