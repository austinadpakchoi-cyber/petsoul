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
