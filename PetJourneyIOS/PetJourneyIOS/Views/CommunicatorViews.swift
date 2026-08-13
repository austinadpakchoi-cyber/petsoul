import PhotosUI
import SwiftUI
import UIKit

struct JourneyHomeTabs: View {
    let petID: String
    let service: any PetJourneyService
    var onReset: () -> Void

    var body: some View {
        TabView {
            JourneyMapView(petID: petID, service: service, onReset: onReset)
                .tabItem {
                    Label("地图", systemImage: "map.fill")
                }

            CommunicatorHomeView(petID: petID, service: service)
                .tabItem {
                    Label("通讯器", systemImage: "antenna.radiowaves.left.and.right")
                }

            MemoryHubView(petID: petID, service: service)
                .tabItem {
                    Label("回忆", systemImage: "tray.full.fill")
                }
        }
        .tint(DesignTokens.sage)
    }
}

final class CommunicatorViewModel: ObservableObject {
    @Published var status: AgentStatus?
    @Published var messages: [CommunicatorMessage] = []
    @Published var moments: [CommunicatorMoment] = []
    @Published var isLoading = false
    @Published var isSending = false
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

    var petType: PetType? {
        status?.petType
    }

    var statusLine: String {
        guard let status else { return "手机正在接收信号" }
        return "\(status.agentState.location) · \(status.agentState.status.displayName)"
    }

    var signalSummary: String {
        guard let status else { return "正在同步 TA 那边的生活节奏。" }
        return status.agentState.statusNote
    }

    var chatHeaderSubtitle: String {
        guard let status else { return "通讯器在线" }
        return "\(status.agentState.location) · \(status.agentState.status.displayName)"
    }

    var chatAvailabilityText: String {
        guard let status else { return "正在连接" }
        switch status.agentState.status {
        case .flying:
            return "信号不稳定"
        case .traveling, .walking:
            return "可能会晚一点回"
        case .resting:
            return "休息中"
        case .staying:
            return "可以拍照"
        }
    }

    var messageEntryDetail: String {
        guard let latest = chatMessages.last else { return "问问现在在干嘛，或者轻轻留一句话" }
        switch latest.sender {
        case .owner:
            return "你刚刚说：\(latest.text)"
        case .pet:
            return "\(petName)：\(latest.text)"
        case .system:
            return latest.text
        }
    }

    var chatMessages: [CommunicatorMessage] {
        messages
    }

    var friendsCircleMoments: [CommunicatorMoment] {
        moments.filter { $0.isReadyForFriendsCircle }
    }

    var momentEntryDetail: String {
        guard let moment = friendsCircleMoments.first else { return "\(petName) 会在合适的时候更新" }
        return moment.text
    }

    var postcardEntryDetail: String {
        let count = status?.postcards.count ?? 0
        guard count > 0 else { return "正式、私密、适合收藏的纪念" }
        return "\(count) 张专门寄给你的纪念"
    }

    func load() async {
        isLoading = true
        defer { isLoading = false }
        do {
            async let status = service.fetchAgentStatus(petID: petID)
            async let messages = service.fetchCommunicatorMessages(petID: petID, limit: 80)
            async let moments = service.fetchMoments(petID: petID, limit: 40)
            self.status = try await status
            self.messages = try await messages
            self.moments = try await moments
        } catch {
            toastMessage = "手机信号有点弱，稍后再试。"
        }
    }

    func send(_ text: String) async {
        let clean = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !clean.isEmpty, !isSending else { return }
        let local = CommunicatorMessage(
            id: "local-\(UUID().uuidString)",
            petID: petID,
            sender: .owner,
            text: clean,
            intent: nil,
            messageState: "created",
            replyPolicy: nil,
            attachments: [],
            relatedMessageID: nil,
            createdAt: Date(),
            updatedAt: nil
        )
        messages.append(local)
        isSending = true
        defer { isSending = false }
        do {
            let response = try await service.sendCommunicatorMessage(
                petID: petID,
                request: CommunicatorSendRequest(text: clean)
            )
            messages.removeAll { $0.id == local.id }
            messages.append(response.ownerMessage)
            messages.append(contentsOf: response.messages)
            PetPushRegistrationCoordinator.shared.requestAuthorizationForUserMoment()
            async let refreshedStatus = service.fetchAgentStatus(petID: petID)
            async let refreshedMoments = service.fetchMoments(petID: petID, limit: 40)
            status = try? await refreshedStatus
            moments = (try? await refreshedMoments) ?? moments
        } catch {
            if let index = messages.firstIndex(where: { $0.id == local.id }) {
                messages[index].messageState = "failed"
                messages[index].updatedAt = Date()
            }
            toastMessage = "这句话暂时没有送到。"
        }
    }

    func resend(_ message: CommunicatorMessage) async {
        guard message.sender == .owner, message.messageState == "failed" else { return }
        messages.removeAll { $0.id == message.id }
        if let attachment = message.attachments.first(where: { $0.type == .ownerPhoto }),
           let url = attachment.photoURL,
           let data = try? Data(contentsOf: url) {
            await sendPhoto(data, caption: message.text.isEmpty ? nil : message.text)
        } else {
            await send(message.text)
        }
    }

    func sendPhoto(_ imageData: Data, caption: String? = nil) async {
        guard !isSending else { return }
        let clean = caption?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        let uploadData = Self.normalizedImageData(imageData)
        guard let localURL = try? Self.persistLocalCommunicatorPhoto(uploadData) else {
            toastMessage = "这张照片暂时读不到。"
            return
        }
        let localAttachment = CommunicatorAttachment(
            type: .ownerPhoto,
            title: "你发来的照片",
            text: clean.isEmpty ? "给 TA 看的一张照片。" : clean,
            state: "ready",
            photoURL: localURL,
            location: nil,
            photoMissionID: nil,
            availableAfter: nil
        )
        let local = CommunicatorMessage(
            id: "local-photo-\(UUID().uuidString)",
            petID: petID,
            sender: .owner,
            text: clean,
            intent: .ownerPhotoShare,
            messageState: "created",
            replyPolicy: nil,
            attachments: [localAttachment],
            relatedMessageID: nil,
            createdAt: Date(),
            updatedAt: nil
        )
        messages.append(local)
        isSending = true
        defer { isSending = false }
        do {
            let response = try await service.sendCommunicatorPhoto(
                petID: petID,
                imageData: uploadData,
                caption: clean.isEmpty ? nil : clean
            )
            messages.removeAll { $0.id == local.id }
            messages.append(response.ownerMessage)
            messages.append(contentsOf: response.messages)
            PetPushRegistrationCoordinator.shared.requestAuthorizationForUserMoment()
            async let refreshedStatus = service.fetchAgentStatus(petID: petID)
            async let refreshedMoments = service.fetchMoments(petID: petID, limit: 40)
            status = try? await refreshedStatus
            moments = (try? await refreshedMoments) ?? moments
        } catch {
            if let index = messages.firstIndex(where: { $0.id == local.id }) {
                messages[index].messageState = "failed"
                messages[index].updatedAt = Date()
            }
            toastMessage = "这张照片暂时没有送到。"
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

    static func normalizedImageData(_ data: Data) -> Data {
        guard let image = UIImage(data: data), let jpeg = image.jpegData(compressionQuality: 0.82) else {
            return data
        }
        return jpeg
    }

    static func persistLocalCommunicatorPhoto(_ data: Data) throws -> URL {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("petsoul-communicator", isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let fileURL = directory.appendingPathComponent("owner-photo-\(UUID().uuidString).jpg")
        try data.write(to: fileURL)
        return fileURL
    }
}

struct CommunicatorHomeView: View {
    let petID: String
    let service: any PetJourneyService
    @StateObject var viewModel: CommunicatorViewModel

    init(petID: String, service: any PetJourneyService) {
        self.petID = petID
        self.service = service
        _viewModel = StateObject(wrappedValue: CommunicatorViewModel(petID: petID, service: service))
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    communicatorHeader

                    NavigationLink {
                        PetChatView(viewModel: viewModel)
                    } label: {
                        CommunicatorEntryCard(
                            title: "消息",
                            detail: viewModel.messageEntryDetail,
                            footnote: "\(viewModel.messages.count) 条通讯记录",
                            systemImage: "bubble.left.and.text.bubble.right.fill",
                            asset: .messageBubble,
                            tint: DesignTokens.sea
                        )
                    }
                    .buttonStyle(.plain)

                    NavigationLink {
                        MomentsView(viewModel: viewModel)
                    } label: {
                        CommunicatorEntryCard(
                            title: "朋友圈",
                            detail: viewModel.momentEntryDetail,
                            footnote: viewModel.friendsCircleMoments.isEmpty ? "等待 TA 自己更新" : "\(viewModel.friendsCircleMoments.count) 条公开动态",
                            systemImage: "sparkles",
                            asset: .moments,
                            tint: DesignTokens.amber
                        )
                    }
                    .buttonStyle(.plain)

                    CommunicatorPreviewPanel(
                        title: "最近的生活信号",
                        detail: viewModel.momentEntryDetail,
                        systemImage: "dot.radiowaves.left.and.right",
                        tint: DesignTokens.sage
                    )
                }
                .padding(DesignTokens.pagePadding)
            }
            .background(AppBackground())
            .navigationTitle("手机")
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

    var communicatorHeader: some View {
        SoftCard {
            VStack(alignment: .leading, spacing: 12) {
                HStack(spacing: 12) {
                    PetSoulAssetIcon(
                        asset: .communicator,
                        fallbackSystemImage: "antenna.radiowaves.left.and.right",
                        fallbackTint: DesignTokens.sage,
                        size: 40
                    )
                        .frame(width: 44, height: 44)
                        .background(DesignTokens.sage.opacity(0.13))
                        .clipShape(Circle())

                    VStack(alignment: .leading, spacing: 4) {
                        Text("\(viewModel.petName) 的手机")
                            .font(.headline.weight(.semibold))
                            .foregroundStyle(DesignTokens.ink)
                        Text(viewModel.statusLine)
                            .font(.subheadline)
                            .foregroundStyle(DesignTokens.secondaryInk)
                            .lineLimit(1)
                    }
                    Spacer(minLength: 0)
                }

                Text(viewModel.signalSummary)
                    .font(.subheadline)
                    .foregroundStyle(DesignTokens.ink)
                    .lineSpacing(3)
                    .fixedSize(horizontal: false, vertical: true)

                HStack(spacing: 8) {
                    CommunicatorSignalChip(title: "消息", value: "\(viewModel.messages.count)", tint: DesignTokens.sea)
                    CommunicatorSignalChip(title: "朋友圈", value: "\(viewModel.friendsCircleMoments.count)", tint: DesignTokens.amber)
                    CommunicatorSignalChip(title: "状态", value: viewModel.chatAvailabilityText, tint: DesignTokens.clay)
                }
            }
        }
    }
}

struct CommunicatorEntryCard: View {
    var title: String
    var detail: String
    var footnote: String
    var systemImage: String
    var asset: PetSoulAsset?
    var tint: Color

    var body: some View {
        SoftCard {
            HStack(spacing: 12) {
                Group {
                    if let asset {
                        PetSoulAssetIcon(
                            asset: asset,
                            fallbackSystemImage: systemImage,
                            fallbackTint: tint,
                            size: 38
                        )
                    } else {
                        PetSoulAdaptiveIcon(systemImage: systemImage, tint: tint, size: 38)
                    }
                }
                .frame(width: 42, height: 42)
                .background(tint.opacity(0.13))
                .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))

                VStack(alignment: .leading, spacing: 4) {
                    Text(title)
                        .font(.headline.weight(.semibold))
                        .foregroundStyle(DesignTokens.ink)
                    Text(detail)
                        .font(.subheadline)
                        .foregroundStyle(DesignTokens.secondaryInk)
                        .lineLimit(2)
                    Text(footnote)
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(tint)
                }
                Spacer(minLength: 0)
                Image(systemName: "chevron.right")
                    .font(.caption.weight(.bold))
                    .foregroundStyle(DesignTokens.secondaryInk)
            }
        }
    }
}

struct CommunicatorCompactEntry: View {
    var title: String
    var detail: String
    var systemImage: String
    var asset: PetSoulAsset?
    var tint: Color

    var body: some View {
        SoftCard(padding: 14) {
            VStack(alignment: .leading, spacing: 10) {
                Group {
                    if let asset {
                        PetSoulAssetIcon(
                            asset: asset,
                            fallbackSystemImage: systemImage,
                            fallbackTint: tint,
                            size: 32
                        )
                    } else {
                        PetSoulAdaptiveIcon(systemImage: systemImage, tint: tint, size: 32)
                    }
                }
                .frame(width: 36, height: 36)
                .background(tint.opacity(0.13))
                .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))

                VStack(alignment: .leading, spacing: 3) {
                    Text(title)
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(DesignTokens.ink)
                    Text(detail)
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(DesignTokens.secondaryInk)
                        .lineLimit(1)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }
}

struct CommunicatorSignalChip: View {
    var title: String
    var value: String
    var tint: Color

    var body: some View {
        HStack(spacing: 5) {
            Circle()
                .fill(tint)
                .frame(width: 6, height: 6)
            Text(title)
                .lineLimit(1)
            Text(value)
                .fontWeight(.bold)
                .lineLimit(1)
        }
        .font(.caption.weight(.semibold))
        .foregroundStyle(DesignTokens.secondaryInk)
        .padding(.vertical, 7)
        .padding(.horizontal, 9)
        .frame(maxWidth: .infinity)
        .background(DesignTokens.mist.opacity(0.52))
        .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
    }
}

struct CommunicatorPreviewPanel: View {
    var title: String
    var detail: String
    var systemImage: String
    var tint: Color

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            PetSoulAdaptiveIcon(systemImage: systemImage, tint: tint, size: 24)
                .frame(width: 30, height: 30)
                .background(tint.opacity(0.12))
                .clipShape(Circle())

            VStack(alignment: .leading, spacing: 4) {
                Text(title)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(DesignTokens.secondaryInk)
                Text(detail)
                    .font(.subheadline)
                    .foregroundStyle(DesignTokens.ink)
                    .lineSpacing(3)
                    .lineLimit(3)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Spacer(minLength: 0)
        }
        .padding(12)
        .background(DesignTokens.surface.opacity(0.66))
        .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 8, style: .continuous)
                .stroke(DesignTokens.softLine.opacity(0.72), lineWidth: 1)
        }
    }
}
