import Foundation

@MainActor
extension JourneyViewModel {
    func refreshTravelTools() async {
        do {
            async let quests = service.fetchTravelQuests(petID: petID, limit: 8)
            async let souvenirs = service.fetchSouvenirs(petID: petID, limit: 40)
            travelQuests = try await quests
            self.souvenirs = try await souvenirs
            await refreshTravelBag()
        } catch {
            toastMessage = "旅行小包还没有同步完整。"
        }
    }

    func createTravelQuest(message: String) async {
        let clean = message.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !clean.isEmpty, !isCreatingTravelQuest else { return }
        isCreatingTravelQuest = true
        defer { isCreatingTravelQuest = false }
        do {
            let quest = try await service.createTravelQuest(
                petID: petID,
                request: TravelWishRequest(
                    message: clean,
                    destination: nil,
                    eventName: nil,
                    preferredStartDate: nil
                )
            )
            travelQuests.insertOrReplaceFirst(quest)
            await refreshTravelBag()
            toastMessage = "TA 先整理好了一份小攻略。"
        } catch {
            toastMessage = "这份旅行愿望暂时没有送到。"
        }
    }

    func openWorldCupQuest(
        host: WorldCupHostCity,
        bagItems: Set<WorldCupBagItem>,
        ownerMessage: String?
    ) async {
        guard !isOpeningWorldCupQuest else { return }
        isOpeningWorldCupQuest = true
        defer { isOpeningWorldCupQuest = false }

        let cleanMessage = ownerMessage?.trimmingCharacters(in: .whitespacesAndNewlines)
        let invitationMessage = "收到一封远方球场邀请。想先看看 \(host.questDestination) 的世界杯球场灯光，但不要打断现在的旅程，先放进旅行包，等今天这段路走完再决定。"

        do {
            let quest = try await service.createTravelQuest(
                petID: petID,
                request: TravelWishRequest(
                    message: invitationMessage,
                    destination: host.questDestination,
                    eventName: "世界杯特别旅程",
                    preferredStartDate: nil
                )
            )
            travelQuests.insertOrReplaceFirst(quest)

            let packedItems = bagItems
                .sorted { $0.sortOrder < $1.sortOrder }
                .map(\.travelBagInput)
            if !packedItems.isEmpty || cleanMessage?.isEmpty == false {
                let bag = try await service.packTravelBag(
                    petID: petID,
                    request: TravelBagPackRequest(
                        questID: quest.id,
                        items: packedItems,
                        ownerMessage: cleanMessage?.isEmpty == false ? cleanMessage : nil
                    )
                )
                travelBag = bag
                attachTravelBagToQuest(bag)
            }

            toastMessage = "远方球场邀请已放进旅行包，TA 会先走完今天这段路。"
        } catch {
            toastMessage = "这封远方邀请暂时没有放好。"
        }
    }

    func prepareActiveTravelQuest() async {
        guard let quest = activeTravelQuest, !isCreatingTravelQuest else { return }
        isCreatingTravelQuest = true
        defer { isCreatingTravelQuest = false }
        do {
            let updated = try await service.prepareTravelQuest(petID: petID, questID: quest.id)
            travelQuests.insertOrReplaceFirst(updated)
            if let plan = updated.journeyPlan {
                journeyPlan = plan
                remoteRoutePlan = plan.compatibilityRoutePlan
            }
            toastMessage = "TA 开始检查小包和路线。"
        } catch {
            toastMessage = "这段出发准备还没有同步成功。"
        }
    }

    func packTravelBag(items: [TravelBagItemInput], ownerMessage: String? = nil) async {
        guard !isPackingTravelBag else { return }
        let cleanMessage = ownerMessage?.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !items.isEmpty || cleanMessage?.isEmpty == false else { return }
        isPackingTravelBag = true
        defer { isPackingTravelBag = false }
        do {
            let bag = try await service.packTravelBag(
                petID: petID,
                request: TravelBagPackRequest(
                    questID: activeTravelQuest?.id,
                    items: items,
                    ownerMessage: cleanMessage?.isEmpty == false ? cleanMessage : nil
                )
            )
            travelBag = bag
            attachTravelBagToQuest(bag)
            toastMessage = "小包已经收好。"
        } catch {
            toastMessage = "小包暂时没有装好。"
        }
    }

    func attachTravelBagToQuest(_ bag: TravelBag) {
        guard let questID = bag.questID,
              let index = travelQuests.firstIndex(where: { $0.id == questID }) else { return }
        let quest = travelQuests[index]
        travelQuests[index] = TravelQuest(
            id: quest.id,
            petID: quest.petID,
            questType: quest.questType,
            status: quest.status,
            currentPhase: quest.currentPhase,
            tripType: quest.tripType,
            returnPolicy: quest.returnPolicy,
            originAnchor: quest.originAnchor,
            ownerMessage: quest.ownerMessage,
            destination: quest.destination,
            eventName: quest.eventName,
            preferredStartDate: quest.preferredStartDate,
            autonomyDecision: quest.autonomyDecision,
            currentPhaseMessage: quest.currentPhaseMessage,
            guide: quest.guide,
            travelBag: bag,
            journeyPlan: quest.journeyPlan,
            postEventOptions: quest.postEventOptions,
            souvenirPreview: quest.souvenirPreview,
            selectedNextOptionID: quest.selectedNextOptionID,
            worldcupEvent: quest.worldcupEvent,
            createdAt: quest.createdAt,
            updatedAt: Date()
        )
    }

    func refreshTravelBag() async {
        do {
            travelBag = try await service.fetchTravelBag(petID: petID, questID: activeTravelQuest?.id)
        } catch {
            travelBag = nil
        }
    }
}
