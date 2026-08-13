import Foundation
import SwiftUI

@MainActor
final class MemoryHubViewModel: ObservableObject {
    @Published var status: AgentStatus?
    @Published var dna: PetDNA?
    @Published var moments: [CommunicatorMoment] = []
    @Published var memories: [MemoryRecord] = []
    @Published var souvenirs: [SouvenirItem] = []
    @Published var travelQuests: [TravelQuest] = []
    @Published var isLoading = false
    @Published var toastMessage: String?

    let petID: String
    let service: any PetJourneyService

    init(petID: String, service: any PetJourneyService) {
        self.petID = petID
        self.service = service
    }

    var petName: String {
        status?.name ?? "TA"
    }

    var location: String {
        status?.agentState.location ?? "旅途中"
    }

    var postcards: [Postcard] {
        status?.postcards ?? []
    }

    var readyMoments: [CommunicatorMoment] {
        moments.filter { $0.isReadyForFriendsCircle }
    }

    var latestMoment: CommunicatorMoment? {
        readyMoments.sorted { $0.createdAt > $1.createdAt }.first
    }

    var latestPostcard: Postcard? {
        postcards.sorted { $0.timestamp > $1.timestamp }.first
    }

    var latestSouvenir: SouvenirItem? {
        souvenirs.sorted { $0.obtainedAt > $1.obtainedAt }.first
    }

    var latestMemory: MemoryRecord? {
        memories.sorted { lhs, rhs in
            if lhs.lastSeenAt == rhs.lastSeenAt {
                return (lhs.importance ?? lhs.salience) > (rhs.importance ?? rhs.salience)
            }
            return lhs.lastSeenAt > rhs.lastSeenAt
        }.first
    }

    var latestHighlight: MemoryArchiveHighlight? {
        var items: [MemoryArchiveHighlight] = []
        if let latestMemory {
            items.append(
                MemoryArchiveHighlight(
                    title: "最近档案",
                    detail: latestMemory.title,
                    systemImage: "archivebox.fill",
                    tint: DesignTokens.sea,
                    date: latestMemory.lastSeenAt
                )
            )
        }
        if let latestMoment {
            items.append(
                MemoryArchiveHighlight(
                    title: "最近生活片段",
                    detail: latestMoment.text,
                    systemImage: "sparkles",
                    tint: DesignTokens.amber,
                    date: latestMoment.createdAt
                )
            )
        }
        if let latestPostcard {
            items.append(
                MemoryArchiveHighlight(
                    title: "最近明信片",
                    detail: latestPostcard.location,
                    systemImage: "mail.fill",
                    tint: DesignTokens.clay,
                    date: latestPostcard.timestamp
                )
            )
        }
        if let latestSouvenir {
            items.append(
                MemoryArchiveHighlight(
                    title: "最近收藏",
                    detail: latestSouvenir.title,
                    systemImage: "gift.fill",
                    tint: DesignTokens.amber,
                    date: latestSouvenir.obtainedAt
                )
            )
        }
        return items.sorted { $0.date > $1.date }.first
    }

    func load() async {
        isLoading = true
        defer { isLoading = false }

        async let nextStatus = service.fetchAgentStatus(petID: petID)
        async let nextDNA = service.fetchDNA(petID: petID)
        async let nextMoments = service.fetchMoments(petID: petID, limit: 60)
        async let nextMemories = service.fetchMemories(petID: petID, limit: 100)
        async let nextSouvenirs = service.fetchSouvenirs(petID: petID, limit: 40)
        async let nextTravelQuests = service.fetchTravelQuests(petID: petID, limit: 8)

        let loadedStatus = try? await nextStatus
        let loadedDNA = try? await nextDNA
        let loadedMoments = try? await nextMoments
        let loadedMemories = try? await nextMemories
        let loadedSouvenirs = try? await nextSouvenirs
        let loadedTravelQuests = try? await nextTravelQuests

        if let loadedStatus {
            status = loadedStatus
        }
        if let loadedDNA {
            dna = loadedDNA
        }
        if let loadedMoments {
            moments = loadedMoments
        }
        if let loadedMemories {
            memories = loadedMemories
        }
        if let loadedSouvenirs {
            souvenirs = loadedSouvenirs
        }
        if let loadedTravelQuests {
            travelQuests = loadedTravelQuests
        }

        if loadedStatus == nil && loadedMoments == nil && loadedMemories == nil && loadedSouvenirs == nil && loadedTravelQuests == nil {
            toastMessage = "回忆盒暂时没有同步好，稍后再试。"
        }
    }

    func saveMemory(memoryID: String?, values: MemoryEditorValues) async {
        do {
            let saved: MemoryRecord
            if let memoryID {
                saved = try await service.updateMemory(
                    petID: petID,
                    memoryID: memoryID,
                    request: MemoryUpdateRequest(
                        kind: values.kind,
                        title: values.title,
                        content: values.content,
                        salience: values.salience,
                        source: values.source,
                        metadata: values.metadata,
                        memoryType: values.memoryType,
                        importance: values.importance,
                        emotionalValence: values.emotionalValence,
                        confidence: values.confidence,
                        sourceEventID: values.sourceEventID,
                        structuredPayload: values.structuredPayload
                    )
                )
                toastMessage = "记忆档案已更新。"
            } else {
                saved = try await service.addMemory(
                    petID: petID,
                    request: MemoryCreateRequest(
                        kind: values.kind,
                        title: values.title,
                        content: values.content,
                        salience: values.salience,
                        source: values.source,
                        metadata: values.metadata,
                        memoryType: values.memoryType,
                        importance: values.importance,
                        emotionalValence: values.emotionalValence,
                        confidence: values.confidence,
                        sourceEventID: values.sourceEventID,
                        structuredPayload: values.structuredPayload
                    )
                )
                toastMessage = "记忆档案已写入。"
            }
            upsertMemory(saved)
        } catch {
            toastMessage = "这条记忆暂时保存失败。"
        }
    }

    func deleteMemory(_ memory: MemoryRecord) async {
        do {
            try await service.deleteMemory(petID: petID, memoryID: memory.id)
            memories.removeAll { $0.id == memory.id }
            toastMessage = "记忆档案已删除。"
        } catch {
            toastMessage = "这条记忆暂时删不掉。"
        }
    }

    func upsertMemory(_ memory: MemoryRecord) {
        if let index = memories.firstIndex(where: { $0.id == memory.id }) {
            memories[index] = memory
        } else {
            memories.insert(memory, at: 0)
        }
        memories.sort { lhs, rhs in
            if lhs.lastSeenAt == rhs.lastSeenAt {
                return (lhs.importance ?? lhs.salience) > (rhs.importance ?? rhs.salience)
            }
            return lhs.lastSeenAt > rhs.lastSeenAt
        }
    }

    func react(to moment: CommunicatorMoment, reaction: MomentReaction) async {
        do {
            let response = try await service.reactToMoment(
                petID: petID,
                momentID: moment.id,
                request: MomentReactionRequest(reaction: reaction)
            )
            if let index = moments.firstIndex(where: { $0.id == moment.id }) {
                var updated = moments[index]
                if let previous = updated.ownerReaction {
                    updated.reactions[previous.rawValue] = max(0, (updated.reactions[previous.rawValue] ?? 0) - 1)
                }
                updated.ownerReaction = reaction
                updated.reactions[reaction.rawValue] = (updated.reactions[reaction.rawValue] ?? 0) + 1
                updated.updatedAt = Date()
                moments[index] = updated
            }
            toastMessage = response.message
        } catch {
            toastMessage = "这次回应没有送达。"
        }
    }
}
