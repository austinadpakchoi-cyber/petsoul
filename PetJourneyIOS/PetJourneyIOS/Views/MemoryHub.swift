import PhotosUI
import SwiftUI
import UIKit

struct MemoryArchiveHighlight {
    var title: String
    var detail: String
    var systemImage: String
    var tint: Color
    var date: Date
}

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

struct MemoryHubView: View {
    let petID: String
    let service: any PetJourneyService
    @StateObject var viewModel: MemoryHubViewModel

    init(petID: String, service: any PetJourneyService) {
        self.petID = petID
        self.service = service
        _viewModel = StateObject(wrappedValue: MemoryHubViewModel(petID: petID, service: service))
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    MemoryOverviewCard(
                        petName: viewModel.petName,
                        location: viewModel.location,
                        lifeMomentCount: viewModel.readyMoments.count,
                        memoryCount: viewModel.memories.count,
                        postcardCount: viewModel.postcards.count,
                        souvenirCount: viewModel.souvenirs.count,
                        credentialCount: PetCredentialKind.allCases.count,
                        latestHighlight: viewModel.latestHighlight,
                        isLoading: viewModel.isLoading && viewModel.status == nil
                    )

                    NavigationLink {
                        MemoryMomentArchiveView(viewModel: viewModel)
                    } label: {
                        CommunicatorEntryCard(
                            title: "生活片段",
                            detail: viewModel.latestMoment?.text ?? "朋友圈里公开过的片段会同步收进这里",
                            footnote: viewModel.readyMoments.isEmpty ? "等待 TA 自己留下第一段" : "\(viewModel.readyMoments.count) 条片段已归档",
                            systemImage: "sparkles",
                            asset: .moments,
                            tint: DesignTokens.amber
                        )
                    }
                    .buttonStyle(.plain)

                    NavigationLink {
                        EditableMemoryArchiveView(viewModel: viewModel)
                    } label: {
                        CommunicatorEntryCard(
                            title: "记忆档案",
                            detail: viewModel.latestMemory?.content ?? "DNA、偏好、地点情绪和主人补充都会沉淀在这里",
                            footnote: viewModel.memories.isEmpty ? "等待第一条可编辑记忆" : "\(viewModel.memories.count) 条档案可编辑",
                            systemImage: "archivebox.fill",
                            asset: .memoryTray,
                            tint: DesignTokens.sea
                        )
                    }
                    .buttonStyle(.plain)

                    NavigationLink {
                        PetCredentialWalletView(
                            status: viewModel.status,
                            dna: viewModel.dna,
                            souvenirCount: viewModel.souvenirs.count,
                            travelQuests: viewModel.travelQuests
                        )
                    } label: {
                        CommunicatorEntryCard(
                            title: "证件卡包",
                            detail: "证件照、身份信息和远行凭证都收在这里",
                            footnote: "\(PetCredentialKind.allCases.count) 张平行世界证件",
                            systemImage: "wallet.pass.fill",
                            asset: .luckyCharm,
                            tint: DesignTokens.dusk
                        )
                    }
                    .buttonStyle(.plain)

                    NavigationLink {
                        PostcardsView(postcards: viewModel.postcards)
                    } label: {
                        CommunicatorEntryCard(
                            title: "明信片",
                            detail: viewModel.latestPostcard?.text ?? "正式、私密、适合收藏的纪念",
                            footnote: "\(viewModel.postcards.count) 张正式纪念",
                            systemImage: "mail.stack.fill",
                            asset: .postcardMemory,
                            tint: DesignTokens.clay
                        )
                    }
                    .buttonStyle(.plain)

                    NavigationLink {
                        SouvenirsView(souvenirs: viewModel.souvenirs)
                    } label: {
                        CommunicatorEntryCard(
                            title: "小收藏",
                            detail: viewModel.latestSouvenir?.story ?? "TA 在路上带回来的小东西会收在这里",
                            footnote: "\(viewModel.souvenirs.count) 件小收藏",
                            systemImage: "gift.fill",
                            asset: .souvenirGift,
                            tint: DesignTokens.amber
                        )
                    }
                    .buttonStyle(.plain)
                }
                .padding(DesignTokens.pagePadding)
            }
            .background(AppBackground())
            .navigationTitle("回忆")
            .task { await viewModel.load() }
            .refreshable { await viewModel.load() }
            .overlay(alignment: .bottom) {
                if let toast = viewModel.toastMessage {
                    ToastView(message: toast)
                        .padding(.bottom, 12)
                        .onAppear {
                            DispatchQueue.main.asyncAfter(deadline: .now() + 2.2) {
                                viewModel.toastMessage = nil
                            }
                        }
                }
            }
        }
    }
}

struct MemoryMomentArchiveView: View {
    @ObservedObject var viewModel: MemoryHubViewModel

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                if viewModel.readyMoments.isEmpty {
                    SoftCard {
                        VStack(alignment: .leading, spacing: 8) {
                            PetSoulAdaptiveIcon(systemImage: "sparkles", tint: DesignTokens.amber, size: 30)
                            Text("还没有生活片段")
                                .font(.headline.weight(.semibold))
                                .foregroundStyle(DesignTokens.ink)
                            Text("TA 发到朋友圈的公开动态，会自动归档到这里。")
                                .font(.subheadline)
                                .foregroundStyle(DesignTokens.secondaryInk)
                                .lineSpacing(3)
                        }
                    }
                } else {
                    ForEach(viewModel.readyMoments) { moment in
                        MomentCard(
                            moment: moment,
                            petName: viewModel.petName,
                            petType: viewModel.status?.petType,
                            onReact: { reaction in
                                Task { await viewModel.react(to: moment, reaction: reaction) }
                            }
                        )
                    }
                }
            }
            .padding(DesignTokens.pagePadding)
        }
        .background(AppBackground())
        .navigationTitle("生活片段")
        .task {
            if viewModel.readyMoments.isEmpty {
                await viewModel.load()
            }
        }
        .refreshable { await viewModel.load() }
    }
}

struct MemoryEditorValues {
    var kind: String
    var title: String
    var content: String
    var salience: Double
    var source: String
    var metadata: [String: JSONValue]
    var memoryType: String
    var importance: Double
    var emotionalValence: Double
    var confidence: Double
    var sourceEventID: String?
    var structuredPayload: [String: JSONValue]
}

struct MemoryEditorDraft: Identifiable {
    let id = UUID()
    var memory: MemoryRecord?
}

enum MemoryArchiveFilter: String, CaseIterable, Identifiable {
    case all
    case relationship
    case preference
    case place
    case episodic
    case manual

    var id: String { rawValue }

    var title: String {
        switch self {
        case .all: "全部"
        case .relationship: "关系"
        case .preference: "偏好"
        case .place: "地点"
        case .episodic: "片段"
        case .manual: "手写"
        }
    }

    func matches(_ memory: MemoryRecord) -> Bool {
        let kind = memory.kind.lowercased()
        let type = (memory.memoryType ?? memory.kind).lowercased()
        switch self {
        case .all:
            return true
        case .relationship:
            return type.contains("relationship") || kind.contains("identity") || kind.contains("owner")
        case .preference:
            return type.contains("preference") || kind.contains("preference") || kind.contains("feedback")
        case .place:
            return type.contains("place") || kind.contains("place") || kind.contains("postcard") || kind.contains("souvenir")
        case .episodic:
            return type.contains("episodic") || type.contains("recent")
        case .manual:
            return memory.source.lowercased().contains("manual") || memory.source.lowercased().contains("owner")
        }
    }
}
