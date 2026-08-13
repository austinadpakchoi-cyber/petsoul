import Foundation

@MainActor
extension JourneyViewModel {
    func collectSouvenirsForActiveQuest() async {
        guard let quest = activeTravelQuest, !isCollectingSouvenir else { return }
        isCollectingSouvenir = true
        defer { isCollectingSouvenir = false }
        do {
            let response = try await service.collectTravelQuestSouvenirsWithEconomy(petID: petID, questID: quest.id)
            mergeSouvenirs(response.items)
            await refreshEconomy()
            toastMessage = "TA 带回了一点小东西。"
        } catch {
            toastMessage = "带回物还没有同步成功。"
        }
    }

    func sellSouvenir(_ souvenir: SouvenirItem) async {
        guard souvenir.isSellable, !mutatingInventoryItemIDs.contains(souvenir.id) else { return }
        mutatingInventoryItemIDs.insert(souvenir.id)
        defer { mutatingInventoryItemIDs.remove(souvenir.id) }
        do {
            let response = try await service.sellItem(
                petID: petID,
                itemID: souvenir.id,
                request: SellItemRequest(
                    clientRequestID: UUID().uuidString,
                    expectedItemVersion: souvenir.effectiveVersion
                )
            )
            replaceSouvenir(response.item)
            await refreshEconomy()
            toastMessage = "TA 把这件小收藏换成了 \(response.transaction.amounts.travelCoin) 旅贝。"
        } catch {
            toastMessage = "这件小收藏暂时没有卖出去。"
        }
    }

    func archiveSouvenir(_ souvenir: SouvenirItem) async {
        guard souvenir.effectiveStatus == .owned, !mutatingInventoryItemIDs.contains(souvenir.id) else { return }
        mutatingInventoryItemIDs.insert(souvenir.id)
        defer { mutatingInventoryItemIDs.remove(souvenir.id) }
        do {
            let response = try await service.archiveItem(
                petID: petID,
                itemID: souvenir.id,
                request: ArchiveItemRequest(
                    clientRequestID: UUID().uuidString,
                    expectedItemVersion: souvenir.effectiveVersion
                )
            )
            replaceSouvenir(response.item)
            await refreshEconomy()
            toastMessage = "已经放进珍藏里。"
        } catch {
            toastMessage = "这件小收藏暂时没有归档。"
        }
    }

    func refreshEconomy() async {
        if let nextEconomy = try? await service.fetchEconomy(petID: petID) {
            economy = nextEconomy
        }
    }

    func mergeSouvenirs(_ items: [SouvenirItem]) {
        var seen = Set<String>()
        souvenirs = (items + souvenirs)
            .filter { seen.insert($0.id).inserted }
            .sorted(by: { $0.obtainedAt > $1.obtainedAt })
    }

    func replaceSouvenir(_ item: SouvenirItem) {
        if let index = souvenirs.firstIndex(where: { $0.id == item.id }) {
            souvenirs[index] = item
        } else {
            souvenirs.insert(item, at: 0)
        }
        souvenirs.sort(by: { $0.obtainedAt > $1.obtainedAt })
    }
}
