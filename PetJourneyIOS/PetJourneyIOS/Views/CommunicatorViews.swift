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
                    Label("手机", systemImage: "bubble.left.and.text.bubble.right.fill")
                }

            MemoryHubView(petID: petID, service: service)
                .tabItem {
                    Label("回忆", systemImage: "tray.full.fill")
                }
        }
        .tint(DesignTokens.sage)
    }
}

@MainActor
final class CommunicatorViewModel: ObservableObject {
    @Published private(set) var status: AgentStatus?
    @Published private(set) var messages: [CommunicatorMessage] = []
    @Published private(set) var moments: [CommunicatorMoment] = []
    @Published private(set) var isLoading = false
    @Published private(set) var isSending = false
    @Published var toastMessage: String?

    let petID: String
    private let service: any PetJourneyService

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

    private static func normalizedImageData(_ data: Data) -> Data {
        guard let image = UIImage(data: data), let jpeg = image.jpegData(compressionQuality: 0.82) else {
            return data
        }
        return jpeg
    }

    private static func persistLocalCommunicatorPhoto(_ data: Data) throws -> URL {
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
    @StateObject private var viewModel: CommunicatorViewModel

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

    private var communicatorHeader: some View {
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

private struct CommunicatorEntryCard: View {
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

private struct CommunicatorCompactEntry: View {
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

private struct CommunicatorSignalChip: View {
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

private struct CommunicatorPreviewPanel: View {
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
        .background(.white.opacity(0.66))
        .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 8, style: .continuous)
                .stroke(DesignTokens.softLine.opacity(0.72), lineWidth: 1)
        }
    }
}

struct PetChatView: View {
    @ObservedObject var viewModel: CommunicatorViewModel
    @State private var draft = ""
    @State private var selectedPhotoItem: PhotosPickerItem?
    private let quickPrompts = ["看看你现在", "给我拍一张", "你在哪呀", "今天开心吗"]

    var body: some View {
        VStack(spacing: 0) {
            ChatStatusStrip(
                petID: viewModel.petID,
                petName: viewModel.petName,
                petType: viewModel.petType,
                statusLine: viewModel.chatHeaderSubtitle,
                availability: viewModel.chatAvailabilityText
            )
            .padding(.horizontal, DesignTokens.pagePadding)
            .padding(.top, 8)
            .padding(.bottom, 8)

            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(spacing: 10) {
                        if viewModel.chatMessages.isEmpty {
                            ChatEmptyState()
                        } else if let first = viewModel.chatMessages.first {
                            ChatTimeSeparator(date: first.createdAt)
                        }
                        ForEach(viewModel.chatMessages) { message in
                            CommunicatorMessageRow(
                                message: message,
                                petName: viewModel.petName,
                                petType: viewModel.petType,
                                onRetry: message.sender == .owner && message.messageState == "failed"
                                    ? { Task { await viewModel.resend(message) } }
                                    : nil
                            )
                            .id(message.id)
                        }
                    }
                    .padding(DesignTokens.pagePadding)
                }
                .onChange(of: viewModel.chatMessages.count) { _, _ in
                    if let last = viewModel.chatMessages.last {
                        withAnimation(.easeOut(duration: 0.2)) {
                            proxy.scrollTo(last.id, anchor: .bottom)
                        }
                    }
                }
            }
            chatComposer
                .padding(.horizontal, DesignTokens.pagePadding)
                .padding(.top, 8)
                .padding(.bottom, 10)
                .background(.ultraThinMaterial)
        }
        .background(AppBackground())
        .navigationTitle("")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .principal) {
                VStack(spacing: 1) {
                    Text(viewModel.petName)
                        .font(.headline.weight(.semibold))
                        .foregroundStyle(DesignTokens.ink)
                    Text(viewModel.chatAvailabilityText)
                        .font(.caption2)
                        .foregroundStyle(DesignTokens.secondaryInk)
                }
            }
            ToolbarItem(placement: .topBarTrailing) {
                Button {} label: {
                    Image(systemName: "ellipsis")
                        .font(.system(size: 17, weight: .semibold))
                        .foregroundStyle(DesignTokens.ink)
                        .frame(width: 34, height: 34)
                        .background(.white.opacity(0.7))
                        .clipShape(Circle())
                }
                .buttonStyle(.plain)
            }
        }
        .toolbar(.hidden, for: .tabBar)
        .task {
            if viewModel.messages.isEmpty {
                await viewModel.load()
            }
        }
        .task(id: selectedPhotoItem) {
            guard let selectedPhotoItem else { return }
            if let data = try? await selectedPhotoItem.loadTransferable(type: Data.self) {
                let caption = draft.trimmingCharacters(in: .whitespacesAndNewlines)
                draft = ""
                await viewModel.sendPhoto(data, caption: caption.isEmpty ? nil : caption)
            } else {
                viewModel.toastMessage = "这张照片暂时读不到。"
            }
            self.selectedPhotoItem = nil
        }
    }

    private var chatComposer: some View {
        VStack(spacing: 8) {
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 8) {
                    ForEach(quickPrompts, id: \.self) { prompt in
                        Button {
                            Task { await viewModel.send(prompt) }
                        } label: {
                            Text(prompt)
                                .font(.caption.weight(.medium))
                                .foregroundStyle(DesignTokens.ink)
                                .padding(.vertical, 7)
                                .padding(.horizontal, 11)
                                .background(.white.opacity(0.82))
                                .clipShape(Capsule())
                        }
                        .buttonStyle(.plain)
                        .disabled(viewModel.isSending)
                    }
                }
            }

            HStack(spacing: 9) {
                PhotosPicker(selection: $selectedPhotoItem, matching: .images) {
                    Image(systemName: "plus")
                        .font(.system(size: 17, weight: .semibold))
                        .foregroundStyle(DesignTokens.ink)
                        .frame(width: 36, height: 36)
                        .background(.white.opacity(0.82))
                        .clipShape(Circle())
                }
                .buttonStyle(.plain)
                .disabled(viewModel.isSending)

                TextField("给 \(viewModel.petName) 说一句话", text: $draft, axis: .vertical)
                    .font(.body)
                    .lineLimit(1...3)
                    .padding(.vertical, 10)
                    .padding(.horizontal, 12)
                    .background(.white.opacity(0.86))
                    .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))

                Button {
                    let text = draft
                    draft = ""
                    Task { await viewModel.send(text) }
                } label: {
                    Image(systemName: viewModel.isSending ? "hourglass" : "paperplane.fill")
                        .font(.system(size: 15, weight: .bold))
                        .foregroundStyle(.white)
                        .frame(width: 38, height: 38)
                        .background(draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? DesignTokens.secondaryInk.opacity(0.28) : DesignTokens.sage)
                        .clipShape(Circle())
                }
                .buttonStyle(.plain)
                .disabled(draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || viewModel.isSending)
            }
        }
    }
}

private struct ChatStatusStrip: View {
    var petID: String
    var petName: String
    var petType: PetType?
    var statusLine: String
    var availability: String

    var body: some View {
        HStack(spacing: 10) {
            PetChatAvatar(petID: petID, petType: petType, size: 42)

            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 6) {
                    Text(petName)
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(DesignTokens.ink)
                    Text(availability)
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(DesignTokens.sage)
                        .padding(.vertical, 3)
                        .padding(.horizontal, 7)
                        .background(DesignTokens.sage.opacity(0.12))
                        .clipShape(Capsule())
                }
                Text(statusLine)
                    .font(.caption)
                    .foregroundStyle(DesignTokens.secondaryInk)
                    .lineLimit(1)
            }

            Spacer(minLength: 0)
        }
        .padding(10)
        .background(.white.opacity(0.68))
        .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .stroke(.white.opacity(0.72), lineWidth: 1)
        }
    }
}

private struct ChatTimeSeparator: View {
    var date: Date

    var body: some View {
        Text(date.petSoulChatTimeLabel)
            .font(.caption2.weight(.medium))
            .foregroundStyle(DesignTokens.secondaryInk)
            .padding(.vertical, 4)
            .padding(.horizontal, 8)
            .background(.white.opacity(0.52))
            .clipShape(Capsule())
            .padding(.bottom, 2)
    }
}

private struct PetChatAvatar: View {
    var petID: String
    var petType: PetType?
    var size: CGFloat = 34

    var body: some View {
        Group {
            if let image = PetAvatarStore.image(for: petID) {
                Image(uiImage: image)
                    .resizable()
                    .scaledToFill()
            } else {
                ZStack {
                    DesignTokens.petal
                    Image(systemName: (petType ?? .other).symbolName)
                        .font(.system(size: size * 0.46, weight: .semibold))
                        .foregroundStyle(DesignTokens.clay)
                }
            }
        }
        .frame(width: size, height: size)
        .clipShape(Circle())
        .overlay {
            Circle()
                .stroke(.white.opacity(0.9), lineWidth: 1)
        }
        .shadow(color: .black.opacity(0.05), radius: 5, x: 0, y: 2)
    }
}

private struct ChatEmptyState: View {
    var title: String = "还没有消息"
    var detail: String = "你可以问问 TA 现在在干嘛，或者轻轻说一句想念。"
    var systemImage: String = "bubble.left.and.text.bubble.right"

    var body: some View {
        VStack(spacing: 8) {
            PetSoulAdaptiveIcon(systemImage: systemImage, tint: DesignTokens.sage, size: 40)
            Text(title)
                .font(.headline.weight(.semibold))
                .foregroundStyle(DesignTokens.ink)
            Text(detail)
                .font(.subheadline)
                .foregroundStyle(DesignTokens.secondaryInk)
                .multilineTextAlignment(.center)
        }
        .padding(22)
    }
}

private struct CommunicatorMessageRow: View {
    var message: CommunicatorMessage
    var petName: String
    var petType: PetType?
    var onRetry: (() -> Void)?

    private var bubbleColor: Color {
        switch message.sender {
        case .owner: DesignTokens.sage.opacity(0.86)
        case .pet: .white.opacity(0.9)
        case .system: DesignTokens.mist.opacity(0.76)
        }
    }

    private var visibleAttachments: [CommunicatorAttachment] {
        message.attachments.filter { $0.type != .text }
    }

    var body: some View {
        switch message.sender {
        case .owner:
            ownerRow
        case .pet:
            petRow
        case .system:
            systemRow
        }
    }

    private var ownerRow: some View {
        HStack(alignment: .bottom, spacing: 8) {
            Spacer(minLength: 46)
            VStack(alignment: .trailing, spacing: 4) {
                ForEach(visibleAttachments) { attachment in
                    CommunicatorAttachmentView(attachment: attachment)
                        .frame(maxWidth: 240, alignment: .trailing)
                }

                if !displayText.isEmpty {
                    Text(displayText)
                        .font(.body)
                        .foregroundStyle(.white)
                        .lineSpacing(2)
                        .padding(.vertical, 10)
                        .padding(.horizontal, 13)
                        .frame(maxWidth: min(UIScreen.main.bounds.width * 0.72, 310), alignment: .trailing)
                        .background(bubbleColor)
                        .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
                }

                if message.messageState == "failed", let onRetry {
                    Button(action: onRetry) {
                        Label("未送达 · 点按重发", systemImage: "arrow.clockwise")
                            .font(.caption2.weight(.semibold))
                            .foregroundStyle(DesignTokens.clay)
                    }
                    .buttonStyle(.plain)
                } else {
                    Text(deliveryText)
                        .font(.caption2)
                        .foregroundStyle(DesignTokens.secondaryInk.opacity(0.78))
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .trailing)
    }

    private var petRow: some View {
        HStack(alignment: .top, spacing: 8) {
            PetChatAvatar(petID: message.petID, petType: petType)
            VStack(alignment: .leading, spacing: 6) {
                Text(displayText)
                    .font(.body)
                    .foregroundStyle(DesignTokens.ink)
                    .lineSpacing(2)
                    .padding(.vertical, 10)
                    .padding(.horizontal, 13)
                    .frame(maxWidth: min(UIScreen.main.bounds.width * 0.72, 310), alignment: .leading)
                    .background(bubbleColor)
                    .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))

                ForEach(visibleAttachments) { attachment in
                    CommunicatorAttachmentView(attachment: attachment)
                        .frame(maxWidth: 288, alignment: .leading)
                }
            }
            Spacer(minLength: 34)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var systemRow: some View {
        VStack(spacing: 7) {
            Text(displayText)
                .font(.caption)
                .foregroundStyle(DesignTokens.secondaryInk)
                .lineSpacing(2)
                .multilineTextAlignment(.center)
                .padding(.vertical, 7)
                .padding(.horizontal, 11)
                .background(bubbleColor)
                .clipShape(Capsule())

            ForEach(visibleAttachments) { attachment in
                CommunicatorAttachmentView(attachment: attachment)
                    .frame(maxWidth: 292, alignment: .center)
            }
        }
        .frame(maxWidth: .infinity, alignment: .center)
    }

    private var displayText: String {
        guard message.sender != .owner else { return message.text }
        return message.text.petSoulNaturalizedChatText
    }

    private var deliveryText: String {
        switch message.messageState {
        case "created":
            return "发送中"
        case "failed":
            return "未送达"
        default:
            return "已送达"
        }
    }
}

private extension String {
    var petSoulNaturalizedChatText: String {
        var text = self
        if text.hasPrefix("刚刚看到你的消息。") {
            text = text.replacingOccurrences(of: "刚刚看到你的消息。", with: "")
        }
        if text.contains("我听见你说「"), let start = text.range(of: "我听见你说「"), let end = text.range(of: "」。") {
            let quoted = String(text[start.upperBound..<end.lowerBound])
            let compact = quoted.replacingOccurrences(of: " ", with: "")
            if compact.count <= 8 && ["好", "好滴", "好的", "嗯", "嗯嗯", "行", "可以", "收到", "看", "看看"].contains(where: { compact.contains($0) }) {
                return compact.contains("看") ? "嗯嗯，等照片好了我发你。" : "嗯嗯。"
            }
            return "我看到啦。"
        }
        text = text.replacingOccurrences(of: "我先把它放进通讯器里，等自己的节奏合适时再慢慢回应。", with: "我看到啦。")
        text = text.replacingOccurrences(of: "我会按自己的节奏慢慢回应。", with: "我看到啦。")
        text = text.replacingOccurrences(of: "被我收进通讯器里", with: "被我收好了")
        text = text.replacingOccurrences(of: "通讯器把位置轻轻标出来了", with: "位置给你发过来了")
        return text.trimmingCharacters(in: .whitespacesAndNewlines)
    }
}

private extension Date {
    var petSoulChatTimeLabel: String {
        let calendar = Calendar.current
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "zh_CN")
        formatter.dateFormat = calendar.isDateInToday(self) ? "今天 HH:mm" : "M月d日 HH:mm"
        return formatter.string(from: self)
    }
}

private struct CommunicatorAttachmentView: View {
    var attachment: CommunicatorAttachment

    var body: some View {
        if attachment.type == .sticker {
            Text(attachment.title)
                .font(.title3)
                .padding(.vertical, 8)
                .padding(.horizontal, 11)
                .background(.white.opacity(0.62))
                .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
        } else if attachment.type == .photo || attachment.type == .photoPlaceholder || attachment.type == .ownerPhoto {
            CommunicatorPhotoAttachmentView(attachment: attachment)
        } else {
        HStack(alignment: .top, spacing: 9) {
            PetSoulAdaptiveIcon(systemImage: systemImage, tint: tint, size: 24)
                .frame(width: 28, height: 28)
                .background(tint.opacity(0.13))
                .clipShape(Circle())

            VStack(alignment: .leading, spacing: 3) {
                Text(attachment.title)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(DesignTokens.ink)
                Text(attachment.text)
                    .font(.caption)
                    .foregroundStyle(DesignTokens.secondaryInk)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(10)
        .background(.white.opacity(0.72))
        .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
        }
    }

    private var systemImage: String {
        switch attachment.type {
        case .sticker: "pawprint.fill"
        case .locationCard: "mappin.and.ellipse"
        case .photoStatusCard: "camera.metering.none"
        case .photoPlaceholder, .photo, .ownerPhoto: "photo.fill"
        case .pendingPhotoRequest: "clock.arrow.circlepath"
        case .postcardCandidate: "mail.fill"
        case .text: "text.bubble.fill"
        }
    }

    private var tint: Color {
        switch attachment.type {
        case .postcardCandidate: DesignTokens.clay
        case .locationCard: DesignTokens.sea
        case .sticker: DesignTokens.amber
        case .ownerPhoto: DesignTokens.sage
        default: DesignTokens.sage
        }
    }
}

private struct CommunicatorPhotoAttachmentView: View {
    var attachment: CommunicatorAttachment

    private var isPendingGeneration: Bool {
        attachment.photoURL == nil && (
            attachment.type == .photoPlaceholder
                || attachment.type == .pendingPhotoRequest
                || attachment.state == "placeholder"
                || attachment.state == "planned"
        )
    }

    private var statusBadgeText: String? {
        if isPendingGeneration {
            return "生成中"
        }
        if attachment.photoURL == nil {
            return "未取得照片"
        }
        return nil
    }

    var body: some View {
        if attachment.type == .ownerPhoto {
            photoFrame
                .frame(height: 188)
                .frame(maxWidth: .infinity)
                .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
                .overlay {
                    RoundedRectangle(cornerRadius: 14, style: .continuous)
                        .stroke(.white.opacity(0.72), lineWidth: 1)
                }
        } else {
        VStack(alignment: .leading, spacing: 9) {
            photoFrame
                .frame(height: 168)
                .frame(maxWidth: .infinity)
                .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
                .overlay(
                    RoundedRectangle(cornerRadius: 14, style: .continuous)
                        .stroke(.white.opacity(0.72), lineWidth: 1)
                )

            HStack(spacing: 7) {
                Image(systemName: isPendingGeneration ? "photo.on.rectangle.angled" : "camera.fill")
                    .font(.caption.weight(.bold))
                    .foregroundStyle(DesignTokens.sage)
                Text(attachment.title)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(DesignTokens.ink)
                Spacer(minLength: 0)
                if let statusBadgeText {
                    Text(statusBadgeText)
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(DesignTokens.secondaryInk)
                        .padding(.vertical, 4)
                        .padding(.horizontal, 7)
                        .background(DesignTokens.mist.opacity(0.7))
                        .clipShape(Capsule())
                }
            }

            Text(attachment.text)
                .font(.caption)
                .foregroundStyle(DesignTokens.secondaryInk)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(10)
        .background(.white.opacity(0.74))
        .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
        }
    }

    @ViewBuilder
    private var photoFrame: some View {
        if let url = attachment.photoURL {
            if url.isFileURL, let image = UIImage(contentsOfFile: url.path) {
                Image(uiImage: image)
                    .resizable()
                    .scaledToFill()
            } else if url.isFileURL {
                unavailablePhotoPlaceholder(title: "本地照片无法读取", systemImage: "photo.badge.exclamationmark")
            } else {
                AsyncImage(url: url) { phase in
                    switch phase {
                    case .success(let image):
                        image
                            .resizable()
                            .scaledToFill()
                    case .failure:
                        unavailablePhotoPlaceholder(title: "照片暂时加载失败", systemImage: "wifi.exclamationmark")
                    case .empty:
                        loadingPhotoPlaceholder
                    @unknown default:
                        unavailablePhotoPlaceholder(title: "照片暂时无法显示", systemImage: "photo.badge.exclamationmark")
                    }
                }
            }
        } else {
            pendingPhotoPlaceholder
        }
    }

    private var pendingPhotoPlaceholder: some View {
        photoPlaceholder(title: isPendingGeneration ? "这一刻的照片正在生成" : "这条照片没有拿到地址", systemImage: "photo.on.rectangle.angled")
    }

    private var loadingPhotoPlaceholder: some View {
        ZStack {
            placeholderBackground
            VStack(spacing: 8) {
                ProgressView()
                    .tint(DesignTokens.sage)
                Text("正在加载已有照片")
                    .font(.footnote.weight(.semibold))
            }
            .foregroundStyle(DesignTokens.secondaryInk)
        }
    }

    private func unavailablePhotoPlaceholder(title: String, systemImage: String) -> some View {
        photoPlaceholder(title: title, systemImage: systemImage)
    }

    private func photoPlaceholder(title: String, systemImage: String) -> some View {
        ZStack {
            placeholderBackground
            VStack(spacing: 8) {
                Image(systemName: systemImage)
                    .font(.system(size: 28, weight: .semibold))
                Text(title)
                    .font(.footnote.weight(.semibold))
                    .multilineTextAlignment(.center)
            }
            .foregroundStyle(DesignTokens.secondaryInk)
        }
    }

    private var placeholderBackground: some View {
        LinearGradient(
            colors: [
                DesignTokens.mist.opacity(0.94),
                DesignTokens.sage.opacity(0.16),
                DesignTokens.amber.opacity(0.12)
            ],
            startPoint: .topLeading,
            endPoint: .bottomTrailing
        )
    }
}

struct MomentsView: View {
    @ObservedObject var viewModel: CommunicatorViewModel

    var body: some View {
        ScrollView {
            LazyVStack(spacing: 12) {
                if viewModel.friendsCircleMoments.isEmpty {
                    ChatEmptyState(
                        title: "朋友圈还很安静",
                        detail: "\(viewModel.petName) 遇到想分享的一刻时，会自己发一条动态。",
                        systemImage: "sparkles"
                    )
                }
                ForEach(viewModel.friendsCircleMoments) { moment in
                    MomentCard(moment: moment, petName: viewModel.petName, petType: viewModel.petType) { reaction in
                        Task { await viewModel.react(to: moment, reaction: reaction) }
                    }
                }
            }
            .padding(DesignTokens.pagePadding)
        }
        .background(AppBackground())
        .navigationTitle("朋友圈")
        .navigationBarTitleDisplayMode(.inline)
        .task {
            if viewModel.friendsCircleMoments.isEmpty {
                await viewModel.load()
            }
        }
    }
}

private struct MomentCard: View {
    var moment: CommunicatorMoment
    var petName: String
    var petType: PetType?
    var onReact: (MomentReaction) -> Void

    var body: some View {
        SoftCard {
            VStack(alignment: .leading, spacing: 10) {
                HStack(spacing: 9) {
                    PetChatAvatar(petID: moment.petID, petType: petType, size: 34)
                    VStack(alignment: .leading, spacing: 2) {
                        Text(petName)
                            .font(.subheadline.weight(.semibold))
                            .foregroundStyle(DesignTokens.ink)
                        Text(headerLine)
                            .font(.caption)
                            .foregroundStyle(DesignTokens.secondaryInk)
                    }
                    Spacer(minLength: 0)
                }

                Text(moment.text)
                    .font(.subheadline)
                    .foregroundStyle(DesignTokens.ink)
                    .lineSpacing(3)

                ForEach(moment.friendsCircleAttachments) { attachment in
                    CommunicatorAttachmentView(attachment: attachment)
                }

                MomentSocialReactorRow(reactors: moment.socialReactors ?? [])

                HStack(spacing: 8) {
                    ForEach(MomentReaction.allCases) { reaction in
                        Button {
                            onReact(reaction)
                        } label: {
                            Label(reactionTitle(for: reaction), systemImage: reaction.systemImage)
                                .font(.caption.weight(.semibold))
                                .foregroundStyle(moment.ownerReaction == reaction ? .white : DesignTokens.secondaryInk)
                                .padding(.vertical, 7)
                                .padding(.horizontal, 9)
                                .background(moment.ownerReaction == reaction ? DesignTokens.sage : DesignTokens.mist.opacity(0.64))
                                .clipShape(Capsule())
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
        }
    }

    private var headerLine: String {
        let place = [moment.location?.city, moment.location?.placeName].compactMap { $0 }.joined(separator: " · ")
        let time = moment.createdAt.formatted(date: .omitted, time: .shortened)
        return place.isEmpty ? time : "\(time) · \(place)"
    }

    private func reactionTitle(for reaction: MomentReaction) -> String {
        let count = moment.reactions[reaction.rawValue] ?? 0
        return count > 0 ? "\(reaction.displayName) \(count)" : reaction.displayName
    }
}

private extension CommunicatorMoment {
    var friendsCircleAttachments: [CommunicatorAttachment] {
        attachments.filter { $0.isVisibleInFriendsCircle }
    }

    var isReadyForFriendsCircle: Bool {
        let photoAttachments = attachments.filter { $0.isPhotoLike }
        if !photoAttachments.isEmpty {
            return photoAttachments.contains { $0.hasReadyPhoto }
        }
        return !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || !friendsCircleAttachments.isEmpty
    }
}

private extension CommunicatorAttachment {
    var isPhotoLike: Bool {
        type == .photo || type == .photoPlaceholder || type == .pendingPhotoRequest
    }

    var hasReadyPhoto: Bool {
        type == .photo && photoURL != nil && state != "placeholder"
    }

    var isVisibleInFriendsCircle: Bool {
        switch type {
        case .photo:
            hasReadyPhoto
        case .photoPlaceholder, .pendingPhotoRequest, .photoStatusCard:
            false
        default:
            true
        }
    }
}

private struct MomentSocialReactorRow: View {
    var reactors: [MomentSocialReactor]

    var body: some View {
        if !reactors.isEmpty {
            HStack(spacing: 9) {
                avatarStack
                    .frame(width: min(CGFloat(reactors.count) * 18 + 18, 72), height: 28, alignment: .leading)

                Text(summary)
                    .font(.caption.weight(.medium))
                    .foregroundStyle(DesignTokens.secondaryInk)
                    .lineLimit(2)

                Spacer(minLength: 0)
            }
            .padding(.vertical, 7)
            .padding(.horizontal, 9)
            .background(DesignTokens.mist.opacity(0.48))
            .clipShape(Capsule())
        }
    }

    private var avatarStack: some View {
        ZStack(alignment: .leading) {
            ForEach(Array(reactors.prefix(4).enumerated()), id: \.element.id) { index, reactor in
                Text(reactor.avatarEmoji)
                    .font(.caption)
                    .frame(width: 26, height: 26)
                    .background(.white.opacity(0.86))
                    .clipShape(Circle())
                    .overlay(Circle().stroke(.white, lineWidth: 1))
                    .offset(x: CGFloat(index) * 17)
            }
        }
    }

    private var summary: String {
        let names = reactors.prefix(2).map(\.name).joined(separator: "、")
        let extraCount = max(0, reactors.count - 2)
        if extraCount > 0 {
            return "\(names) 和 \(extraCount) 位朋友回应了这一刻"
        }
        return "\(names) 回应了这一刻"
    }
}

struct MemoryArchiveHighlight {
    var title: String
    var detail: String
    var systemImage: String
    var tint: Color
    var date: Date
}

@MainActor
final class MemoryHubViewModel: ObservableObject {
    @Published private(set) var status: AgentStatus?
    @Published private(set) var dna: PetDNA?
    @Published private(set) var moments: [CommunicatorMoment] = []
    @Published private(set) var memories: [MemoryRecord] = []
    @Published private(set) var souvenirs: [SouvenirItem] = []
    @Published private(set) var travelQuests: [TravelQuest] = []
    @Published private(set) var isLoading = false
    @Published var toastMessage: String?

    private let petID: String
    private let service: any PetJourneyService

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

    private func upsertMemory(_ memory: MemoryRecord) {
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
    @StateObject private var viewModel: MemoryHubViewModel

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

private struct MemoryMomentArchiveView: View {
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

private struct MemoryEditorDraft: Identifiable {
    let id = UUID()
    var memory: MemoryRecord?
}

private enum MemoryArchiveFilter: String, CaseIterable, Identifiable {
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

private struct EditableMemoryArchiveView: View {
    @ObservedObject var viewModel: MemoryHubViewModel
    @State private var searchText = ""
    @State private var selectedFilter: MemoryArchiveFilter = .all
    @State private var editorDraft: MemoryEditorDraft?
    @State private var memoryPendingDelete: MemoryRecord?

    private var filteredMemories: [MemoryRecord] {
        let query = searchText.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        return viewModel.memories
            .filter { selectedFilter.matches($0) }
            .filter { memory in
                guard !query.isEmpty else { return true }
                return memory.title.lowercased().contains(query)
                    || memory.content.lowercased().contains(query)
                    || memory.kind.lowercased().contains(query)
                    || (memory.memoryType ?? "").lowercased().contains(query)
            }
            .sorted { lhs, rhs in
                let lhsScore = lhs.importance ?? lhs.salience
                let rhsScore = rhs.importance ?? rhs.salience
                if abs(lhsScore - rhsScore) > 0.001 {
                    return lhsScore > rhsScore
                }
                return lhs.lastSeenAt > rhs.lastSeenAt
            }
    }

    private var deleteDialogPresented: Binding<Bool> {
        Binding(
            get: { memoryPendingDelete != nil },
            set: { isPresented in
                if !isPresented {
                    memoryPendingDelete = nil
                }
            }
        )
    }

    var body: some View {
        archiveContent
            .background(AppBackground())
            .navigationTitle("记忆档案")
            .toolbar { addButtonToolbar }
            .sheet(item: $editorDraft) { draft in
                MemoryEditorSheet(memory: draft.memory) { values in
                    Task {
                        await viewModel.saveMemory(memoryID: draft.memory?.id, values: values)
                        editorDraft = nil
                    }
                }
            }
            .confirmationDialog("删除这条记忆？", isPresented: deleteDialogPresented, titleVisibility: .visible) {
                if let memory = memoryPendingDelete {
                    Button("删除", role: .destructive) {
                        Task {
                            await viewModel.deleteMemory(memory)
                            memoryPendingDelete = nil
                        }
                    }
                }
                Button("取消", role: .cancel) {
                    memoryPendingDelete = nil
                }
            } message: {
                Text(memoryPendingDelete?.title ?? "")
            }
            .task {
                if viewModel.memories.isEmpty {
                    await viewModel.load()
                }
            }
            .refreshable { await viewModel.load() }
    }

    private var archiveContent: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                MemoryArchiveSummaryCard(memories: viewModel.memories)
                filterChips
                searchField
                memoryList
            }
            .padding(DesignTokens.pagePadding)
        }
    }

    @ToolbarContentBuilder
    private var addButtonToolbar: some ToolbarContent {
        ToolbarItem(placement: .topBarTrailing) {
            Button {
                editorDraft = MemoryEditorDraft(memory: nil)
            } label: {
                Image(systemName: "plus")
            }
            .accessibilityLabel("新增记忆")
        }
    }

    private var filterChips: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                ForEach(MemoryArchiveFilter.allCases) { filter in
                    Button {
                        selectedFilter = filter
                    } label: {
                        MemoryArchiveFilterChip(
                            title: filter.title,
                            isSelected: selectedFilter == filter
                        )
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.vertical, 2)
        }
    }

    private var searchField: some View {
        HStack(spacing: 9) {
            Image(systemName: "magnifyingglass")
                .foregroundStyle(DesignTokens.secondaryInk)
            TextField("搜索标题、内容、类型", text: $searchText)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()
        }
        .font(.subheadline)
        .padding(12)
        .background(DesignTokens.mist.opacity(0.62))
        .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
    }

    @ViewBuilder
    private var memoryList: some View {
        if filteredMemories.isEmpty {
            MemoryArchiveEmptyState(hasAnyMemory: !viewModel.memories.isEmpty)
        } else {
            LazyVStack(spacing: 10) {
                ForEach(filteredMemories) { memory in
                    EditableMemoryCard(
                        memory: memory,
                        onEdit: { editorDraft = MemoryEditorDraft(memory: memory) },
                        onDelete: { memoryPendingDelete = memory }
                    )
                }
            }
        }
    }
}

private struct MemoryArchiveFilterChip: View {
    var title: String
    var isSelected: Bool

    var body: some View {
        Text(title)
            .font(.caption.weight(.semibold))
            .foregroundStyle(isSelected ? .white : DesignTokens.ink)
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .background(isSelected ? DesignTokens.sage : DesignTokens.mist.opacity(0.7))
            .clipShape(Capsule())
    }
}

private struct MemoryArchiveEmptyState: View {
    var hasAnyMemory: Bool

    var body: some View {
        SoftCard {
            VStack(alignment: .leading, spacing: 8) {
                PetSoulAdaptiveIcon(systemImage: "archivebox.fill", tint: DesignTokens.sea, size: 30)
                Text(hasAnyMemory ? "没有匹配的档案" : "还没有记忆档案")
                    .font(.headline.weight(.semibold))
                    .foregroundStyle(DesignTokens.ink)
                Text(hasAnyMemory ? "换一个分类或关键词再看看。" : "可以先手动写入一条主人补充、偏好或地点情绪。")
                    .font(.subheadline)
                    .foregroundStyle(DesignTokens.secondaryInk)
                    .lineSpacing(3)
            }
        }
    }
}

private struct MemoryArchiveSummaryCard: View {
    var memories: [MemoryRecord]

    private var relationshipCount: Int {
        memories.filter { ($0.memoryType ?? $0.kind).contains("relationship") || $0.kind.contains("identity") }.count
    }

    private var highImportanceCount: Int {
        memories.filter { ($0.importance ?? $0.salience) >= 0.75 }.count
    }

    private var positiveCount: Int {
        memories.filter { ($0.emotionalValence ?? 0) > 0.2 }.count
    }

    var body: some View {
        SoftCard {
            VStack(alignment: .leading, spacing: 12) {
                HStack(spacing: 10) {
                    PetSoulAdaptiveIcon(systemImage: "brain.head.profile", tint: DesignTokens.sea, size: 30)
                    VStack(alignment: .leading, spacing: 2) {
                        Text("可编辑记忆档案")
                            .font(.headline.weight(.semibold))
                            .foregroundStyle(DesignTokens.ink)
                        Text("用于校准 TA 在 PetSoul 世界里的偏好、关系和地点情绪")
                            .font(.subheadline)
                            .foregroundStyle(DesignTokens.secondaryInk)
                            .lineLimit(2)
                    }
                }

                LazyVGrid(columns: [GridItem(.flexible(), spacing: 8), GridItem(.flexible(), spacing: 8), GridItem(.flexible(), spacing: 8)], spacing: 8) {
                    MemoryStatTile(title: "总档案", value: "\(memories.count)", tint: DesignTokens.sea)
                    MemoryStatTile(title: "高重要", value: "\(highImportanceCount)", tint: DesignTokens.amber)
                    MemoryStatTile(title: "关系", value: "\(relationshipCount)", tint: DesignTokens.sage)
                    MemoryStatTile(title: "正向", value: "\(positiveCount)", tint: DesignTokens.clay)
                    MemoryStatTile(title: "可编辑", value: "\(memories.count)", tint: DesignTokens.dusk)
                    MemoryStatTile(title: "筛选", value: "\(MemoryArchiveFilter.allCases.count)", tint: DesignTokens.sea)
                }
            }
        }
    }
}

private struct EditableMemoryCard: View {
    var memory: MemoryRecord
    var onEdit: () -> Void
    var onDelete: () -> Void

    private var tint: Color {
        let type = (memory.memoryType ?? memory.kind).lowercased()
        if type.contains("relationship") { return DesignTokens.sage }
        if type.contains("preference") { return DesignTokens.amber }
        if type.contains("place") { return DesignTokens.sea }
        if memory.kind.contains("postcard") || memory.kind.contains("souvenir") { return DesignTokens.clay }
        return DesignTokens.dusk
    }

    var body: some View {
        SoftCard(padding: 14) {
            VStack(alignment: .leading, spacing: 10) {
                HStack(alignment: .top, spacing: 10) {
                    PetSoulAdaptiveIcon(systemImage: "archivebox.fill", tint: tint, size: 28)
                        .frame(width: 34, height: 34)
                        .background(tint.opacity(0.12))
                        .clipShape(Circle())

                    VStack(alignment: .leading, spacing: 4) {
                        HStack(spacing: 6) {
                            Text(memory.title)
                                .font(.headline.weight(.semibold))
                                .foregroundStyle(DesignTokens.ink)
                                .lineLimit(2)
                            Spacer(minLength: 0)
                        }
                        Text(memory.content)
                            .font(.subheadline)
                            .foregroundStyle(DesignTokens.secondaryInk)
                            .lineSpacing(3)
                            .lineLimit(4)
                    }
                }

                HStack(spacing: 7) {
                    MemoryChip(text: memory.memoryType ?? memory.kind, tint: tint)
                    MemoryChip(text: memory.kind, tint: DesignTokens.dusk)
                    MemoryChip(text: "重要 \(Int((memory.importance ?? memory.salience) * 100))", tint: DesignTokens.amber)
                }

                HStack(spacing: 8) {
                    Label(memory.source, systemImage: "tray.and.arrow.down.fill")
                    Spacer(minLength: 0)
                    Text(memory.lastSeenAt, style: .date)
                }
                .font(.caption.weight(.medium))
                .foregroundStyle(DesignTokens.secondaryInk)

                Divider()
                    .overlay(DesignTokens.softLine.opacity(0.55))

                HStack(spacing: 12) {
                    MemorySignalBar(title: "情绪", value: normalizedValence(memory.emotionalValence ?? 0), tint: DesignTokens.clay)
                    MemorySignalBar(title: "信心", value: memory.confidence ?? 1, tint: DesignTokens.sage)
                    Spacer(minLength: 0)
                    Button(action: onEdit) {
                        Image(systemName: "pencil")
                            .frame(width: 34, height: 34)
                    }
                    .buttonStyle(.plain)
                    .foregroundStyle(DesignTokens.ink)
                    .background(DesignTokens.mist.opacity(0.72))
                    .clipShape(Circle())
                    .accessibilityLabel("编辑记忆")

                    Button(role: .destructive, action: onDelete) {
                        Image(systemName: "trash")
                            .frame(width: 34, height: 34)
                    }
                    .buttonStyle(.plain)
                    .foregroundStyle(DesignTokens.clay)
                    .background(DesignTokens.clay.opacity(0.1))
                    .clipShape(Circle())
                    .accessibilityLabel("删除记忆")
                }
            }
        }
    }

    private func normalizedValence(_ value: Double) -> Double {
        min(max((value + 1) / 2, 0), 1)
    }
}

private struct MemoryChip: View {
    var text: String
    var tint: Color

    var body: some View {
        Text(text.isEmpty ? "unknown" : text)
            .font(.caption2.weight(.bold))
            .foregroundStyle(tint)
            .lineLimit(1)
            .padding(.horizontal, 8)
            .padding(.vertical, 5)
            .background(tint.opacity(0.11))
            .clipShape(Capsule())
    }
}

private struct MemorySignalBar: View {
    var title: String
    var value: Double
    var tint: Color

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title)
                .font(.caption2.weight(.bold))
                .foregroundStyle(DesignTokens.secondaryInk)
            GeometryReader { proxy in
                ZStack(alignment: .leading) {
                    Capsule()
                        .fill(DesignTokens.mist.opacity(0.72))
                    Capsule()
                        .fill(tint.opacity(0.72))
                        .frame(width: max(6, proxy.size.width * min(max(value, 0), 1)))
                }
            }
            .frame(width: 56, height: 6)
        }
    }
}

private struct MemoryEditorSheet: View {
    @Environment(\.dismiss) private var dismiss
    private let memory: MemoryRecord?
    private let onSave: (MemoryEditorValues) -> Void

    @State private var kind: String
    @State private var title: String
    @State private var content: String
    @State private var source: String
    @State private var memoryType: String
    @State private var salience: Double
    @State private var importance: Double
    @State private var emotionalValence: Double
    @State private var confidence: Double
    @State private var sourceEventID: String

    private let memoryTypeOptions = ["episodic", "recent_episodic", "relationship", "preference", "place_affect", "photo", "souvenir"]
    private let kindOptions = ["owner_note", "identity", "owner_preference", "feedback", "place_affect", "postcard", "souvenir", "manual"]

    init(memory: MemoryRecord?, onSave: @escaping (MemoryEditorValues) -> Void) {
        self.memory = memory
        self.onSave = onSave
        _kind = State(initialValue: memory?.kind ?? "owner_note")
        _title = State(initialValue: memory?.title ?? "")
        _content = State(initialValue: memory?.content ?? "")
        _source = State(initialValue: memory?.source ?? "manual")
        _memoryType = State(initialValue: memory?.memoryType ?? "episodic")
        _salience = State(initialValue: memory?.salience ?? 0.62)
        _importance = State(initialValue: memory?.importance ?? memory?.salience ?? 0.62)
        _emotionalValence = State(initialValue: memory?.emotionalValence ?? 0)
        _confidence = State(initialValue: memory?.confidence ?? 0.82)
        _sourceEventID = State(initialValue: memory?.sourceEventID ?? "")
    }

    private var canSave: Bool {
        !title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            && !content.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    var body: some View {
        NavigationStack {
            Form {
                Section("核心内容") {
                    TextField("标题", text: $title)
                    TextEditor(text: $content)
                        .frame(minHeight: 118)
                }

                Section("分类") {
                    Picker("Kind", selection: $kind) {
                        ForEach(kindOptions, id: \.self) { option in
                            Text(option).tag(option)
                        }
                    }
                    Picker("Memory Type", selection: $memoryType) {
                        ForEach(memoryTypeOptions, id: \.self) { option in
                            Text(option).tag(option)
                        }
                    }
                    TextField("来源", text: $source)
                    TextField("来源事件 ID", text: $sourceEventID)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                }

                Section("权重") {
                    SliderValueRow(title: "显著度", value: $salience, range: 0...1)
                    SliderValueRow(title: "重要度", value: $importance, range: 0...1)
                    SliderValueRow(title: "情绪值", value: $emotionalValence, range: -1...1)
                    SliderValueRow(title: "信心值", value: $confidence, range: 0...1)
                }
            }
            .navigationTitle(memory == nil ? "新增记忆" : "编辑记忆")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("取消") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("保存") {
                        onSave(
                            MemoryEditorValues(
                                kind: kind,
                                title: title.trimmingCharacters(in: .whitespacesAndNewlines),
                                content: content.trimmingCharacters(in: .whitespacesAndNewlines),
                                salience: salience,
                                source: source.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? "manual" : source.trimmingCharacters(in: .whitespacesAndNewlines),
                                metadata: memory?.metadata ?? ["edited_in": .string("ios_memory_archive")],
                                memoryType: memoryType,
                                importance: importance,
                                emotionalValence: emotionalValence,
                                confidence: confidence,
                                sourceEventID: sourceEventID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? nil : sourceEventID.trimmingCharacters(in: .whitespacesAndNewlines),
                                structuredPayload: memory?.structuredPayload ?? ["edited_in": .string("ios_memory_archive")]
                            )
                        )
                    }
                    .disabled(!canSave)
                }
            }
        }
    }
}

private struct SliderValueRow: View {
    var title: String
    @Binding var value: Double
    var range: ClosedRange<Double>

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(title)
                Spacer()
                Text(String(format: "%.2f", value))
                    .foregroundStyle(DesignTokens.secondaryInk)
                    .monospacedDigit()
            }
            Slider(value: $value, in: range)
                .tint(DesignTokens.sage)
        }
    }
}

private struct MemoryOverviewCard: View {
    var petName: String
    var location: String
    var lifeMomentCount: Int
    var memoryCount: Int
    var postcardCount: Int
    var souvenirCount: Int
    var credentialCount: Int
    var latestHighlight: MemoryArchiveHighlight?
    var isLoading: Bool

    var body: some View {
        SoftCard {
            VStack(alignment: .leading, spacing: 13) {
                HStack(spacing: 12) {
                    PetSoulAssetIcon(
                        asset: .memoryTray,
                        fallbackSystemImage: "tray.full.fill",
                        fallbackTint: DesignTokens.clay,
                        size: 40
                    )
                        .frame(width: 44, height: 44)
                        .background(DesignTokens.clay.opacity(0.12))
                        .clipShape(Circle())

                    VStack(alignment: .leading, spacing: 4) {
                        Text("\(petName) 的回忆盒")
                            .font(.headline.weight(.semibold))
                            .foregroundStyle(DesignTokens.ink)
                        Text(isLoading ? "正在同步手机里的收藏" : "最近停在 \(location)")
                            .font(.subheadline)
                            .foregroundStyle(DesignTokens.secondaryInk)
                            .lineLimit(1)
                    }
                    Spacer(minLength: 0)
                }

                LazyVGrid(columns: [GridItem(.flexible(), spacing: 8), GridItem(.flexible(), spacing: 8)], spacing: 8) {
                    MemoryStatTile(title: "生活片段", value: isLoading ? "..." : "\(lifeMomentCount)", tint: DesignTokens.amber)
                    MemoryStatTile(title: "记忆档案", value: isLoading ? "..." : "\(memoryCount)", tint: DesignTokens.sea)
                    MemoryStatTile(title: "明信片", value: isLoading ? "..." : "\(postcardCount)", tint: DesignTokens.clay)
                    MemoryStatTile(title: "小收藏", value: isLoading ? "..." : "\(souvenirCount)", tint: DesignTokens.sage)
                    MemoryStatTile(title: "证件", value: "\(credentialCount)", tint: DesignTokens.dusk)
                }

                if let latestHighlight {
                    MemoryLatestRow(
                        title: latestHighlight.title,
                        detail: latestHighlight.detail,
                        systemImage: latestHighlight.systemImage,
                        tint: latestHighlight.tint
                    )
                } else {
                    Text(isLoading ? "正在把手机、朋友圈和旅行包里的内容放到同一个回忆盒里。" : "等 TA 真正寄来或带回什么，这里才会慢慢变厚。")
                        .font(.subheadline)
                        .foregroundStyle(DesignTokens.secondaryInk)
                        .lineSpacing(3)
                }
            }
        }
    }
}

private struct MemoryStatTile: View {
    var title: String
    var value: String
    var tint: Color

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(value)
                .font(.title3.weight(.bold))
                .foregroundStyle(DesignTokens.ink)
            Text(title)
                .font(.caption.weight(.semibold))
                .foregroundStyle(DesignTokens.secondaryInk)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(11)
        .background(tint.opacity(0.1))
        .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
    }
}

private struct MemoryLatestRow: View {
    var title: String
    var detail: String
    var systemImage: String
    var tint: Color

    var body: some View {
        HStack(spacing: 9) {
            PetSoulAdaptiveIcon(systemImage: systemImage, tint: tint, size: 24)
                .frame(width: 28, height: 28)
                .background(tint.opacity(0.13))
                .clipShape(Circle())
            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(DesignTokens.secondaryInk)
                Text(detail)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(DesignTokens.ink)
                    .lineLimit(1)
            }
            Spacer(minLength: 0)
        }
        .padding(10)
        .background(DesignTokens.mist.opacity(0.48))
        .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
    }
}

private enum PetCredentialCategory: String, CaseIterable, Identifiable {
    case documents
    case travel

    var id: String { rawValue }

    var title: String {
        switch self {
        case .documents: "基础证件"
        case .travel: "旅行票据"
        }
    }

    var subtitle: String {
        switch self {
        case .documents: "身份卡、护照、健康证和爪爪驾驶证"
        case .travel: "长途路上和入住休息时生成"
        }
    }
}

private enum PetCredentialPhotoRole: String, CaseIterable, Identifiable {
    case officialIDPortrait
    case realPortrait

    var id: String { rawValue }

    var title: String {
        switch self {
        case .officialIDPortrait: "电子证件照"
        case .realPortrait: "原始照片"
        }
    }

    var subtitle: String {
        switch self {
        case .officialIDPortrait: "护照规范生成"
        case .realPortrait: "生活原图保存"
        }
    }

    var systemImage: String {
        switch self {
        case .officialIDPortrait: "person.crop.square.fill"
        case .realPortrait: "camera.fill"
        }
    }
}

private enum PetCredentialKind: String, CaseIterable, Identifiable {
    case identity
    case passport
    case healthRecord
    case driverLicense
    case boardingPass
    case hotelKey

    var id: String { rawValue }

    var title: String {
        switch self {
        case .identity: "Pet ID"
        case .passport: "Companion Passport"
        case .healthRecord: "Health Record"
        case .driverLicense: "Paw Driver License"
        case .boardingPass: "Boarding Pass"
        case .hotelKey: "Hotel Key Card"
        }
    }

    var subtitle: String {
        switch self {
        case .identity: "宠物身份卡"
        case .passport: "宠物旅伴护照"
        case .healthRecord: "健康证 / 疫苗本"
        case .driverLicense: "爪爪驾驶证"
        case .boardingPass: "登机牌"
        case .hotelKey: "酒店房卡"
        }
    }

    var systemImage: String {
        switch self {
        case .identity: "person.text.rectangle.fill"
        case .passport: "book.closed.fill"
        case .healthRecord: "heart.text.square.fill"
        case .driverLicense: "car.fill"
        case .boardingPass: "airplane.departure"
        case .hotelKey: "key.fill"
        }
    }

    // 这些内置素材只是 PetCredentialPromptTemplate 生成卡面的风格示例,
    // 不允许作为任何宠物的卡面/照片直接展示在 UI 上。
    var promptExampleImageName: String {
        switch self {
        case .identity: "PetCredentialDogIdentity"
        case .passport: "PetCredentialDogPassport"
        case .healthRecord: "PetCredentialDogHealthRecord"
        case .driverLicense: "PetCredentialDogDriverLicense"
        case .boardingPass: "PetCredentialDogBoardingPass"
        case .hotelKey: "PetCredentialDogHotelKey"
        }
    }

    var documentAspectRatio: CGFloat {
        switch self {
        case .passport:
            1448.0 / 1086.0
        default:
            1536.0 / 1024.0
        }
    }

    var tint: Color {
        switch self {
        case .identity: DesignTokens.sage
        case .passport: DesignTokens.dusk
        case .healthRecord: DesignTokens.sea
        case .driverLicense: DesignTokens.amber
        case .boardingPass: DesignTokens.dusk
        case .hotelKey: DesignTokens.clay
        }
    }

    var category: PetCredentialCategory {
        switch self {
        case .identity, .passport, .healthRecord, .driverLicense:
            .documents
        case .boardingPass, .hotelKey:
            .travel
        }
    }

    var rarity: String {
        switch self {
        case .identity: "ID"
        case .passport, .boardingPass, .hotelKey: "Travel"
        case .healthRecord: "Care"
        case .driverLicense: "Fun"
        }
    }

    var gradientColors: [Color] {
        switch self {
        case .identity:
            [Color(hex: 0x4E8074), Color(hex: 0x9BC3B4)]
        case .passport:
            [Color(hex: 0x33445E), Color(hex: 0x6C7F9E)]
        case .healthRecord:
            [Color(hex: 0x6797A4), Color(hex: 0xB7D8D7)]
        case .driverLicense:
            [Color(hex: 0xAF8441), Color(hex: 0xE3C878)]
        case .boardingPass:
            [Color(hex: 0x526D86), Color(hex: 0x9BB4C9)]
        case .hotelKey:
            [Color(hex: 0xA46658), Color(hex: 0xE1A590)]
        }
    }

    var note: String {
        switch self {
        case .identity:
            "PetSoul 世界里的宠物身份 ID，只记录用户 DNA 和星球档案。"
        case .passport:
            "宠物旅行与身份记录的主证件，是平行世界纪念护照。"
        case .healthRecord:
            "PetSoul 温柔照护档案，记录星球护理和安抚备注。"
        case .driverLicense:
            "趣味爪爪驾驶证，只允许云朵慢行、看风景优先。"
        case .boardingPass:
            "长途故事展开时生成的 PetSoul 平行航线票据。"
        case .hotelKey:
            "休息片段出现时生成的平行房卡，记录 TA 的生活感。"
        }
    }
}

private struct PetSoulCredentialProfile {
    let petID: String
    let name: String
    let petType: PetType
    let dna: PetDNA

    var archiveName: String {
        "SOUL-\(String(petID.suffix(4)).uppercased())"
    }

    var speciesLine: String {
        "\(petType.displayName) · 星球显形态"
    }

    var originWorld: String {
        "\(petType.searchWorldName) / \(pick(from: Self.originWorldAliases, salt: 3))"
    }

    var reappearancePlace: String {
        pick(from: [
            "彩虹桥东侧",
            "晨雾草地",
            "云边窗台",
            "软风小站",
            "月光口袋",
            "回声花园"
        ], salt: 7)
    }

    var reappearanceDate: String {
        let month = 1 + seed(salt: 11) % 12
        let day = 1 + seed(salt: 19) % 28
        return "2021-\(String(format: "%02d", month))-\(String(format: "%02d", day))"
    }

    var favoritePlace: String {
        clean(dna.favoritePlaces.first) ?? pick(from: ["窗边", "草地", "安静小店", "有风的地方"], salt: 23)
    }

    var hobby: String {
        clean(dna.hobbies.first) ?? pick(from: ["晒太阳", "慢慢走", "看云", "听人说话"], salt: 29)
    }

    var careDesk: String {
        pick(from: ["软光照护站", "星尘护理室", "云边小诊台", "彩虹桥照护所"], salt: 31)
    }

    var careStatus: String {
        pick(from: ["状态稳定，适合慢慢生活", "精神柔软，适合安静陪伴", "已归档，等待下一次晒太阳"], salt: 37)
    }

    var careRitual: String {
        "\(hobby) / 轻轻梳理 / 听见\(dna.ownerTitle.isEmpty ? "守护人" : dna.ownerTitle)的声音"
    }

    var transitDesk: String {
        pick(from: ["云朵慢行所", "窗边交通桌", "软风车站", "小爪车管室"], salt: 41)
    }

    var ridePreference: String {
        pick(from: ["靠窗慢行", "不赶路，只看风景", "先确认声音，再出发", "坐稳再靠近光"], salt: 43)
    }

    var softDestination: String {
        pick(from: ["下一束暖光", "安静窗边座", "软草地停靠点", "小太阳登机口", "陪伴云层"], salt: 47)
    }

    var cloudGate: String {
        "Cloud \(1 + seed(salt: 53) % 9)"
    }

    var softLodging: String {
        pick(from: ["软毯小旅店", "窗光休息所", "小爪夜宿处", "彩虹午睡房", "云枕房"], salt: 59)
    }

    private static let originWorldAliases = [
        "Pawland",
        "Moonburrow",
        "Softpaw",
        "Chirpland",
        "Companionland",
        "Rainbow Field"
    ]

    private func pick(from values: [String], salt: Int) -> String {
        values[seed(salt: salt) % max(values.count, 1)]
    }

    private func clean(_ value: String?) -> String? {
        let trimmed = (value ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
    }

    private func seed(salt: Int) -> Int {
        let text = "\(petID)|\(name)|\(petType.rawValue)|\(dna.personality)|\(salt)"
        return text.unicodeScalars.reduce(0) { partial, scalar in
            (partial &* 31 &+ Int(scalar.value)) & 0x7fffffff
        }
    }
}

private struct PetCredentialSnapshot {
    var kind: PetCredentialKind
    var serial: String
    var holderName: String
    var species: String
    var originWorld: String
    var currentLocation: String
    var issuePlace: String
    var issueDate: String
    var statusLine: String
    var fields: [(String, String)]
    var stamps: [String]
    var isActive: Bool
    var isUnlocked: Bool = true
    var unlockHint: String = "已解锁"
    var requirementNote: String
    var petID: String = ""
    var petType: PetType = .other

    var detailDescription: String {
        kind.note
    }

    var documentImagePrompt: String {
        PetCredentialPromptTemplate.prompt(for: self)
    }

    var cardDisplayFields: [(String, String)] {
        switch kind {
        case .identity:
            [
                ("Name", holderName),
                ("Species", species),
                ("ID No.", serial)
            ]
        case .passport:
            [
                ("Holder", holderName),
                ("Passport", serial),
                ("Status", isActive ? "跨境启用" : "国内暂不需要")
            ]
        case .healthRecord:
            [
                ("Name", holderName),
                ("Health", value(for: "健康状态") ?? "稳定"),
                ("Vaccine", value(for: "疫苗记录") ?? value(for: "疫苗状态") ?? "已记录")
            ]
        case .driverLicense:
            [
                ("Holder", holderName),
                ("Class", value(for: "准驾类型") ?? "慢行小车"),
                ("Style", value(for: "驾驶风格") ?? "看风景优先")
            ]
        case .boardingPass:
            [
                ("Passenger", holderName),
                ("From", value(for: "From") ?? "同步中"),
                ("To", value(for: "To") ?? currentLocation)
            ]
        case .hotelKey:
            [
                ("Guest", holderName),
                ("City", value(for: "City") ?? currentLocation),
                ("Room", value(for: "Room") ?? serial)
            ]
        }
    }

    var keyDetailFields: [(String, String)] {
        switch kind {
        case .healthRecord:
            [
                ("健康状态", value(for: "健康状态") ?? "稳定"),
                ("疫苗记录", value(for: "疫苗记录") ?? "已记录"),
                ("最近护理", value(for: "最近护理") ?? "梳毛 / 晒太阳")
            ]
        case .driverLicense:
            [
                ("准驾类型", value(for: "准驾类型") ?? "慢行小车"),
                ("驾驶风格", value(for: "驾驶风格") ?? "看风景优先"),
                ("状态", statusLine)
            ]
        default:
            Array(fields.prefix(3))
        }
    }

    var basicInfoFields: [(String, String)] {
        fields.filter { field in
            !["健康状态", "疫苗记录", "疫苗状态", "最近护理", "照护备注", "备注"].contains(field.0)
        }
    }

    var careNote: String? {
        value(for: "照护备注") ?? value(for: "备注")
    }

    var safetyLine: String {
        "这是 PetSoul 世界里的宠物旅伴证件，不代表任何现实法律或医疗证件。"
    }

    var shareText: String {
        "\(holderName) 的 \(kind.subtitle) · \(serial)\n\(safetyLine)"
    }

    private func value(for title: String) -> String? {
        fields.first { $0.0 == title }?.1
    }

    static func all(status: AgentStatus?, dna: PetDNA?, souvenirCount: Int, travelQuests: [TravelQuest]) -> [PetCredentialSnapshot] {
        PetCredentialKind.allCases.map {
            snapshot(kind: $0, status: status, dna: dna, souvenirCount: souvenirCount, travelQuests: travelQuests)
        }
    }

    private static func snapshot(
        kind: PetCredentialKind,
        status: AgentStatus?,
        dna: PetDNA?,
        souvenirCount: Int,
        travelQuests: [TravelQuest]
    ) -> PetCredentialSnapshot {
        let petID = status?.petID ?? "PET-SOUL"
        let shortID = String(petID.suffix(6)).uppercased()
        let name = status?.name ?? "TA"
        let petType = status?.petType ?? .dog
        let trustedDNA = dna ?? .fallback
        let profile = PetSoulCredentialProfile(petID: petID, name: name, petType: petType, dna: trustedDNA)
        let location = profile.reappearancePlace
        let issueDate = Date().formatted(.dateTime.year().month(.twoDigits).day(.twoDigits))
        let activeQuest = travelQuests.first { !isClosedQuest($0.status) } ?? travelQuests.first
        let hasBoardingMoment = activeQuest.map { isBoardingStatus($0.status) || isBoardingStatus($0.currentPhase) } ?? false
        let passportActive = activeQuest.map { quest in
            let questText = [
                quest.destination,
                quest.eventName ?? "",
                quest.ownerMessage,
                quest.currentPhaseMessage
            ].joined(separator: " ")
            return quest.worldcupEvent || isInternationalText(questText)
        } ?? false
        let favoritePlace = profile.favoritePlace
        let hobby = profile.hobby
        let latinName = profile.archiveName
        let birthday = profile.reappearanceDate
        let guardian = trustedDNA.ownerTitle.isEmpty ? "守护人" : trustedDNA.ownerTitle
        let isCheckedIn = status.map { isHotelStatus($0.agentState.status) || isHotelStatus($0.status) } ?? false

        var snapshot: PetCredentialSnapshot
        switch kind {
        case .identity:
            snapshot = PetCredentialSnapshot(
                kind: kind,
                serial: "PJ-ID-\(shortID)",
                holderName: name,
                species: profile.speciesLine,
                originWorld: profile.originWorld,
                currentLocation: location,
                issuePlace: "PetSoul Identity Desk",
                issueDate: issueDate,
                statusLine: "星球身份档案已归档",
                fields: [
                    ("姓名", "\(name) / \(latinName)"),
                    ("物种", petType.displayName),
                    ("显形态", profile.speciesLine),
                    ("初现日", birthday),
                    ("身份编号", "PS-\(shortID)"),
                    ("故乡星球", profile.originWorld),
                    ("初现地点", profile.reappearancePlace),
                    ("性格 DNA", trustedDNA.personality),
                    ("喜欢的地方", favoritePlace),
                    ("守护人", guardian)
                ],
                stamps: ["Identity", "PetSoul", "照片归档"],
                isActive: true,
                requirementNote: "身份卡只记录用户给的 DNA 和 PetSoul 生成的星球档案，不同步真实地址。"
            )
        case .passport:
            snapshot = PetCredentialSnapshot(
                kind: kind,
                serial: "PJ-PASS-\(shortID)",
                holderName: name,
                species: profile.speciesLine,
                originWorld: profile.originWorld,
                currentLocation: location,
                issuePlace: "PetSoul Republic Desk",
                issueDate: issueDate,
                statusLine: passportActive ? "旅伴护照已随身归档" : "星球旅伴护照已归档",
                fields: [
                    ("姓名", "\(name) / \(latinName)"),
                    ("物种", petType.displayName),
                    ("显形态", profile.speciesLine),
                    ("出生日期", birthday),
                    ("护照编号", "PASS-\(shortID)"),
                    ("故乡星球", profile.originWorld),
                    ("初现地点", profile.reappearancePlace),
                    ("旅程状态", "平行世界纪念通行"),
                    ("适用场景", "灵魂旅伴 / 星球重现")
                ],
                stamps: passportActive ? ["旅伴", "随身", "待盖章"] : ["星球", "纪念", "已归档"],
                isActive: passportActive,
                isUnlocked: true,
                unlockHint: "纪念护照已归档",
                requirementNote: "护照是 PetSoul 世界的旅伴证件，不代表真实跨境或现实地址。"
            )
        case .healthRecord:
            snapshot = PetCredentialSnapshot(
                kind: kind,
                serial: "PJ-HEALTH-\(shortID)",
                holderName: name,
                species: profile.speciesLine,
                originWorld: "PetSoul Care Clinic",
                currentLocation: location,
                issuePlace: profile.careDesk,
                issueDate: issueDate,
                statusLine: "星球照护档案已记录",
                fields: [
                    ("姓名", name),
                    ("物种", petType.displayName),
                    ("显形态", profile.speciesLine),
                    ("初现日", birthday),
                    ("健康状态", profile.careStatus),
                    ("疫苗记录", "PetSoul 星尘印记已点亮"),
                    ("最近护理", profile.careRitual),
                    ("照护备注", "\(trustedDNA.personality)，喜欢\(favoritePlace)，安抚词：\(trustedDNA.catchphrase)")
                ],
                stamps: ["Health", "Care", "Soul"],
                isActive: true,
                requirementNote: "健康证是 PetSoul 生成的温柔照护档案，不代表真实医疗或疫苗记录。"
            )
        case .boardingPass:
            snapshot = PetCredentialSnapshot(
                kind: kind,
                serial: "PJ-AIR-\(shortID)",
                holderName: name,
                species: profile.speciesLine,
                originWorld: "PetSoul Airways",
                currentLocation: profile.softDestination,
                issuePlace: profile.cloudGate,
                issueDate: issueDate,
                statusLine: hasBoardingMoment ? "On the way · 平行航线" : "长途故事展开时生成",
                fields: [
                    ("From", profile.reappearancePlace),
                    ("To", profile.softDestination),
                    ("Passenger", latinName),
                    ("Flight", "PS-\(String(shortID.suffix(4)))"),
                    ("Seat", "PAW-\(String(shortID.suffix(2)))"),
                    ("Gate", profile.cloudGate),
                    ("Status", hasBoardingMoment ? "On the way" : "Waiting for story")
                ],
                stamps: hasBoardingMoment ? ["Boarding", "Window", "On Way"] : ["Locked", "Long Trip", "Later"],
                isActive: hasBoardingMoment,
                isUnlocked: hasBoardingMoment,
                unlockHint: "长途故事展开后生成平行航线票据",
                requirementNote: "登机牌是 PetSoul 旅行票据，不代表真实航班、机票或登机凭证。"
            )
        case .driverLicense:
            snapshot = PetCredentialSnapshot(
                kind: kind,
                serial: "PJ-DL-\(shortID)",
                holderName: name,
                species: profile.speciesLine,
                originWorld: "Parallel Transit",
                currentLocation: location,
                issuePlace: profile.transitDesk,
                issueDate: issueDate,
                statusLine: "慢慢开，看风景优先",
                fields: [
                    ("姓名", "\(name) / \(latinName)"),
                    ("准驾类型", "云朵慢行车"),
                    ("驾驶风格", "\(hobby)，看风景优先"),
                    ("签发日期", issueDate),
                    ("证件编号", "DL-\(shortID)"),
                    ("星球规则", "不控制真实路线"),
                    ("乘坐偏好", profile.ridePreference)
                ],
                stamps: ["乘车", "靠窗", "星球"],
                isActive: true,
                requirementNote: "驾驶证是 PetSoul 趣味证件，不使用真实交管样式，也不代表任何现实驾驶资格。"
            )
        case .hotelKey:
            snapshot = PetCredentialSnapshot(
                kind: kind,
                serial: "PJ-STAY-\(shortID)",
                holderName: name,
                species: profile.speciesLine,
                originWorld: "PetSoul Check-in",
                currentLocation: profile.softLodging,
                issuePlace: profile.softLodging,
                issueDate: issueDate,
                statusLine: isCheckedIn ? "已入住平行小房间" : "休息故事展开时生成",
                fields: [
                    ("Guest", latinName),
                    ("Stay", profile.softLodging),
                    ("Room", "SOUL-\(String(shortID.suffix(4)))"),
                    ("Check-in", issueDate),
                    ("Status", isCheckedIn ? "1 night" : "Waiting"),
                    ("Preference", "靠窗 / 安静 / \(favoritePlace)"),
                    ("Care Note", trustedDNA.catchphrase)
                ],
                stamps: isCheckedIn ? ["Check-in", "Window", "Quiet"] : ["Locked", "Rest", "Later"],
                isActive: isCheckedIn,
                isUnlocked: isCheckedIn,
                unlockHint: "休息片段出现后生成平行房卡",
                requirementNote: "酒店房卡记录 PetSoul 平行休息点，不代表真实住宿订单或现实地址。"
            )
        }
        snapshot.petID = petID
        snapshot.petType = petType
        return snapshot
    }

    private static func isClosedQuest(_ status: TravelQuestStatus) -> Bool {
        switch status {
        case .declined, .completed, .returned, .continuedElsewhere:
            true
        default:
            false
        }
    }

    private static func isBoardingStatus(_ status: TravelQuestStatus) -> Bool {
        switch status {
        case .outbound, .traveling, .returnTraveling:
            true
        default:
            false
        }
    }

    private static func isHotelStatus(_ status: JourneyStatus) -> Bool {
        switch status {
        case .resting, .staying:
            true
        default:
            false
        }
    }

    private static func isInternationalText(_ text: String) -> Bool {
        let markers = [
            "美国", "加拿大", "墨西哥", "洛杉矶", "西雅图", "纽约", "新泽西", "达拉斯",
            "迈阿密", "温哥华", "多伦多", "瓜达拉哈拉", "蒙特雷", "墨西哥城",
            "United States", "Canada", "Mexico", "Los Angeles", "Seattle", "New York"
        ]
        return markers.contains { text.localizedCaseInsensitiveContains($0) }
    }
}

private enum PetCredentialPromptTemplate {
    static func prompt(for credential: PetCredentialSnapshot) -> String {
        let fields = credential.fields
            .map { "- \($0.0): \($0.1)" }
            .joined(separator: "\n")
        let documentDirection = direction(for: credential)
        let visibleContent = visibleContent(for: credential, fields: fields)
        let petIdentityGuidance = petIdentityGuidance(for: credential)
        let visualSystem = visualSystem(for: credential)
        let safetyGuards = safetyGuards(for: credential)
        return """
        Create one polished full-document image for a fictional PetSoul credential.

        Document type:
        - \(title(for: credential.kind))
        - Serial: \(credential.serial)
        - Issued: \(credential.issueDate)
        - PetSoul reappearance context: \(credential.currentLocation)
        - \(documentDirection)

        Pet identity:
        - Subject is \(credential.holderName), species/breed: \(credential.species).
        - Only user-entered DNA and pet type/name are factual inputs. All other dates, desks, rooms, seats, routes, care records, and planet lore are fictional PetSoul/GPT generated content for a soul that reappeared on this planet.
        - Do not synchronize, infer, or display any real current address, GPS location, route, city stay, medical record, airline, hotel, DMV, or legal status.
        \(petIdentityGuidance)

        \(visibleContent)

        \(visualSystem)

        Safety guards:
        \(safetyGuards)
        """
    }

    private static func title(for kind: PetCredentialKind) -> String {
        switch kind {
        case .identity: "PETSOUL IDENTITY CARD / 宠物身份卡"
        case .passport: "PETSOUL PASSPORT / 宠物灵魂护照"
        case .driverLicense: "PAW DRIVER LICENSE / 爪爪驾驶证"
        case .healthRecord: "PETSOUL HEALTH RECORD / 健康证"
        case .boardingPass: "PETSOUL BOARDING PASS / 登机牌"
        case .hotelKey: "PETSOUL HOTEL KEY CARD / 酒店房卡"
        }
    }

    private static func direction(for credential: PetCredentialSnapshot) -> String {
        switch credential.kind {
        case .passport:
            return "Wide passport information page: large portrait panel on the left, PETS type, PSR issuing country, passport number, soul-country fields, expiry date, paw seal watermark, and MRZ-like decorative line that is clearly fictional."
        case .identity:
            return "Wide Pet ID identity card: portrait panel on the left, identity fields on the right, compact PET ID badge, soft sage/cream base, paw seal, identity desk stamp, and a clean wallet-card feeling."
        case .driverLicense:
            return "Wide Paw Driver License: premium amber/cream card, small slow-car silhouette, wheel and road-line motifs, permitted class for slow scenic rides, window-seat rider stamp, and clear non-legal fantasy wording."
        case .healthRecord:
            return "Warm health record card: caring clinic style, vaccination and care fields, gentle blue-green accents, and soft medical-file structure without real medical authority."
        case .boardingPass:
            return "Real-world boarding pass layout, paper or e-boarding pass style: wide ticket, detachable stub, airline color strip, route codes, flight, seat, gate, boarding time, zone, and a decorative non-scannable ticket code area. Do not make it look like the PetSoul passport."
        case .hotelKey:
            return "Real-world hotel key card layout: one clean physical card with minimal branding, subtle contactless icon, soft material texture, and no guest information, room number, date, field table, portrait, signature, or document layout."
        }
    }

    private static func petIdentityGuidance(for credential: PetCredentialSnapshot) -> String {
        switch credential.kind {
        case .boardingPass:
            return "- Do not include a pet portrait or ID photo. Use the pet only as the passenger name on the ticket."
        case .hotelKey:
            return "- Do not include a pet portrait, guest name, room number, date, or ID photo. The output is just a hotel key card."
        default:
            return """
            - Use the pet_identity reference only to preserve the exact pet identity, coat or feather colors, face shape, markings, ears, eyes, expression, collar, and body details.
            - Put the pet portrait inside the credential as an official-looking document portrait, not a pasted sticker or cutout.
            """
        }
    }

    private static func visibleContent(for credential: PetCredentialSnapshot, fields: String) -> String {
        switch credential.kind {
        case .boardingPass:
            return """
            Required visible ticket content:
            \(fields)
            - Use these as boarding-pass fields, not as a passport or certificate table.
            - Include a decorative non-scannable barcode or QR-like ticket area labeled fictional / not for real travel.
            """
        case .hotelKey:
            return """
            Visible content:
            - Minimal branding only, such as PETSOUL STAY, SOFT BLANKET INN, LITTLE SOUL REST KEY, FICTIONAL KEEPSAKE.
            - Do not print the metadata fields as visible text. Do not show guest name, room number, stay dates, serial number, or care notes on the card face.
            """
        default:
            return """
            Required visible field content:
            \(fields)
            """
        }
    }

    private static func visualSystem(for credential: PetCredentialSnapshot) -> String {
        switch credential.kind {
        case .boardingPass:
            return """
            Visual system:
            - Clean realistic airline boarding pass, English-dominant, short Chinese labels allowed.
            - White paper base with PetSoul amber/teal accent strip, crisp typography, rounded corners, light paper shadow.
            - Full ticket visible in frame, front-facing flat lay, no crop, no phone UI.
            - Avoid passport guilloche borders, ceremonial seals, MRZ lines, signatures, or large decorative document stamps.
            """
        case .hotelKey:
            return """
            Visual system:
            - Premium physical hotel key card, credit-card proportions, rounded corners, subtle plastic/paper texture, soft shadow.
            - Warm cream base with sage/clay accents, abstract window-light or soft lodging illustration, tiny paw emblem.
            - Full card visible in frame, no crop, no phone UI.
            - Avoid passport guilloche borders, ceremonial seals, field rows, signatures, barcodes, QR codes, or ticket layout.
            """
        default:
            return """
            Unified PetSoul visual system:
            - Premium fictional travel-document design, warm cream paper, soft rose, sage, amber, and dusty blue accents.
            - Fine guilloche linework, subtle paw seals, soft security-pattern texture, rounded card/page corners, gentle paper grain.
            - Bilingual Chinese/English labels where space allows; polished but warm, not childish.
            - Full document visible in frame, front-facing flat lay or clean scanned-document perspective, no crop, no phone UI.
            - Make the layout feel related to the PetSoul passport: PETSOUL REPUBLIC, paw emblem, commemorative edition stamp, and tender companion-world details.
            """
        }
    }

    private static func safetyGuards(for credential: PetCredentialSnapshot) -> String {
        switch credential.kind {
        case .boardingPass:
            return """
            - Fictional PetSoul travel keepsake only.
            - Use a common boarding-pass structure, but do not copy any real airline brand, logo, ticket, airport system, or boarding credential exactly.
            - No real scannable QR code or machine-readable barcode; decorative non-scannable ticket marks are allowed.
            - No real address, no private human face, no official travel authority, and no claim of real boarding permission.
            """
        case .hotelKey:
            return """
            - Fictional PetSoul hotel key keepsake only.
            - Do not copy any real hotel brand, access card, booking confirmation, or room key exactly.
            - No guest name, room number, stay date, barcode, QR code, magnetic stripe data, or real access claim.
            - No official authority, no private human face, and no real address.
            """
        default:
            return """
            - Fictional commemorative PetSoul document only.
            - Do not copy or imitate any real government ID, passport, DMV, driver license, medical card, flag, seal, airline ticket, or legal document.
            - No scannable QR code, no barcode, no real address or current city, no real license plate, no watermark, no brand logo, no private human face.
            """
        }
    }
}

private struct PetCredentialWalletView: View {
    var status: AgentStatus?
    var dna: PetDNA?
    var souvenirCount: Int
    var travelQuests: [TravelQuest]

    @State private var selectedKind: PetCredentialKind = .identity
    @State private var walletNotice: String?

    private var credentials: [PetCredentialSnapshot] {
        PetCredentialSnapshot.all(status: status, dna: dna, souvenirCount: souvenirCount, travelQuests: travelQuests)
    }

    private var selectedCredential: PetCredentialSnapshot {
        credentials.first { $0.kind == selectedKind } ?? credentials[0]
    }

    private var unlockedCredentials: [PetCredentialSnapshot] {
        credentials.filter(\.isUnlocked)
    }

    private var carouselCredentials: [PetCredentialSnapshot] {
        unlockedCredentials.isEmpty ? credentials : unlockedCredentials
    }

    var body: some View {
        ZStack {
            AppBackground()

            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    walletHeader

                    walletProgress

                    credentialPager

                    credentialSections
                }
                .padding(DesignTokens.pagePadding)
                .padding(.bottom, 120)
            }
        }
        .overlay(alignment: .bottom) {
            if let walletNotice {
                ToastView(message: walletNotice)
                    .padding(.horizontal, DesignTokens.pagePadding)
                    .padding(.bottom, 18)
                    .transition(.move(edge: .bottom).combined(with: .opacity))
            }
        }
        .navigationTitle("PetSoul Wallet")
        .navigationBarTitleDisplayMode(.inline)
    }

    private var walletHeader: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 10) {
                PetSoulAssetIcon(
                    asset: .luckyCharm,
                    fallbackSystemImage: "wallet.pass.fill",
                    fallbackTint: DesignTokens.dusk,
                    size: 36
                )
                .frame(width: 42, height: 42)
                .background(DesignTokens.dusk.opacity(0.12))
                .clipShape(Circle())

                VStack(alignment: .leading, spacing: 2) {
                    Text("PetSoul Wallet")
                        .font(.title2.weight(.bold))
                        .foregroundStyle(DesignTokens.ink)
                    Text("\(status?.name ?? "TA") 的卡包")
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(DesignTokens.secondaryInk)
                }
            }

            Text("这里保存着 TA 在 PetSoul 世界里的身份、健康和旅途票据。像翻钱包一样，一张张拿出来看。")
                .font(.subheadline)
                .foregroundStyle(DesignTokens.secondaryInk)
                .lineSpacing(3)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(.top, 4)
    }

    private var walletProgress: some View {
        HStack(spacing: 9) {
            WalletProgressPill(
                title: "已解锁",
                value: "\(unlockedCredentials.count)/\(credentials.count)",
                tint: DesignTokens.sage
            )
            WalletProgressPill(
                title: "主证",
                value: selectedCredential.kind.subtitle,
                tint: selectedCredential.kind.tint
            )
            WalletProgressPill(
                title: "照片档案",
                value: "双照片",
                tint: DesignTokens.clay
            )
        }
    }

    private var credentialPager: some View {
        TabView(selection: $selectedKind) {
            ForEach(carouselCredentials, id: \.kind) { credential in
                NavigationLink {
                    WalletCardDetailView(credential: credential)
                } label: {
                    PetCredentialCard(credential: credential)
                        .padding(.horizontal, 2)
                }
                .buttonStyle(.plain)
                .tag(credential.kind)
            }
        }
        .tabViewStyle(.page(indexDisplayMode: .always))
        .frame(height: selectedKind == .passport ? 286 : 252)
    }

    private var credentialSections: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("全部证件")
                .font(.headline.weight(.semibold))
                .foregroundStyle(DesignTokens.ink)

            ForEach(PetCredentialCategory.allCases) { category in
                let categoryCredentials = credentials.filter { $0.kind.category == category }
                if !categoryCredentials.isEmpty {
                    VStack(alignment: .leading, spacing: 8) {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(category.title)
                                .font(.subheadline.weight(.semibold))
                                .foregroundStyle(DesignTokens.ink)
                            Text(category.subtitle)
                                .font(.caption)
                                .foregroundStyle(DesignTokens.secondaryInk)
                        }

                        LazyVGrid(columns: [GridItem(.adaptive(minimum: 145), spacing: 9)], spacing: 9) {
                            ForEach(categoryCredentials, id: \.kind) { credential in
                                NavigationLink {
                                    WalletCardDetailView(credential: credential)
                                } label: {
                                    CredentialWalletTile(
                                        credential: credential,
                                        isSelected: selectedKind == credential.kind
                                    )
                                }
                                .buttonStyle(.plain)
                                .simultaneousGesture(TapGesture().onEnded {
                                    selectedKind = credential.isUnlocked
                                        ? credential.kind
                                        : (carouselCredentials.first?.kind ?? selectedKind)
                                })
                                .accessibilityLabel(credential.kind.subtitle)
                            }
                        }
                    }
                }
            }

            lockedCardSection
        }
    }

    private var lockedCardSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            VStack(alignment: .leading, spacing: 2) {
                Text("未解锁")
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(DesignTokens.ink)
                Text("旅程继续展开后，会陆续收进更多票据")
                    .font(.caption)
                    .foregroundStyle(DesignTokens.secondaryInk)
            }

            VStack(spacing: 8) {
                Button {
                    showNotice("高铁票会在城市间铁路旅行时收进卡包。")
                } label: {
                    CredentialComingSoonTile(
                        title: "高铁票 / 车票",
                        detail: "铁路或长途交通支线点亮后出现",
                        systemImage: "tram.fill",
                        tint: DesignTokens.dusk
                    )
                }
                .buttonStyle(.plain)

                Button {
                    showNotice("世界杯 Fan Pass 会在球场支线开启后收进卡包。")
                } label: {
                    CredentialComingSoonTile(
                        title: "世界杯 Fan Pass",
                        detail: "美加墨球场支线点亮后出现",
                        systemImage: "sportscourt.fill",
                        tint: DesignTokens.sea
                    )
                }
                .buttonStyle(.plain)

                Button {
                    showNotice("景点票根会在 TA 到达特别地点后收进卡包。")
                } label: {
                    CredentialComingSoonTile(
                        title: "景点票根",
                        detail: "城市纪念地点解锁后出现",
                        systemImage: "ticket.fill",
                        tint: DesignTokens.amber
                    )
                }
                .buttonStyle(.plain)
            }
        }
    }

    private func showNotice(_ message: String) {
        withAnimation(.spring(response: 0.28, dampingFraction: 0.9)) {
            walletNotice = message
        }
        Task {
            try? await Task.sleep(nanoseconds: 1_800_000_000)
            await MainActor.run {
                if walletNotice == message {
                    withAnimation(.easeOut(duration: 0.2)) {
                        walletNotice = nil
                    }
                }
            }
        }
    }
}

private struct WalletCardDetailView: View {
    var credential: PetCredentialSnapshot
    @State private var walletNotice: String?
    @State private var selectedPhotoRole: PetCredentialPhotoRole = .officialIDPortrait
    @State private var photoViewerRole: PetCredentialPhotoRole?

    var body: some View {
        ZStack {
            AppBackground()

            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    PetCredentialCard(credential: credential)

                    CredentialPortraitArchiveSection(
                        credential: credential,
                        selectedRole: $selectedPhotoRole,
                        onOpen: { role in
                            photoViewerRole = role
                        },
                        onNotice: { message in
                            showNotice(message)
                        }
                    )

                    CredentialDetailPanel(credential: credential) { message in
                        showNotice(message)
                    }
                }
                .padding(DesignTokens.pagePadding)
                .padding(.bottom, 120)
            }
        }
        .fullScreenCover(item: $photoViewerRole) { role in
            PetCredentialPortraitViewer(
                credential: credential,
                initialRole: role
            )
        }
        .overlay(alignment: .bottom) {
            if let walletNotice {
                ToastView(message: walletNotice)
                    .padding(.horizontal, DesignTokens.pagePadding)
                    .padding(.bottom, 18)
                    .transition(.move(edge: .bottom).combined(with: .opacity))
            }
        }
        .navigationTitle(credential.kind.subtitle)
        .navigationBarTitleDisplayMode(.inline)
    }

    private func showNotice(_ message: String) {
        withAnimation(.spring(response: 0.28, dampingFraction: 0.9)) {
            walletNotice = message
        }
        Task {
            try? await Task.sleep(nanoseconds: 1_800_000_000)
            await MainActor.run {
                if walletNotice == message {
                    withAnimation(.easeOut(duration: 0.2)) {
                        walletNotice = nil
                    }
                }
            }
        }
    }
}

private struct CredentialPortraitArchiveSection: View {
    var credential: PetCredentialSnapshot
    @Binding var selectedRole: PetCredentialPhotoRole
    var onOpen: (PetCredentialPhotoRole) -> Void
    var onNotice: (String) -> Void

    var body: some View {
        SoftCard {
            VStack(alignment: .leading, spacing: 13) {
                HStack(spacing: 10) {
                    Image(systemName: "photo.stack.fill")
                        .font(.headline.weight(.semibold))
                        .foregroundStyle(credential.kind.tint)
                        .frame(width: 34, height: 34)
                        .background(credential.kind.tint.opacity(0.12))
                        .clipShape(Circle())

                    VStack(alignment: .leading, spacing: 2) {
                        Text("照片档案")
                            .font(.headline.weight(.semibold))
                            .foregroundStyle(DesignTokens.ink)
                        Text("证件照和原始照片分开保存")
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(DesignTokens.secondaryInk)
                    }

                    Spacer(minLength: 0)
                }

                Picker("照片档案", selection: $selectedRole) {
                    ForEach(PetCredentialPhotoRole.allCases) { role in
                        Text(role.title).tag(role)
                    }
                }
                .pickerStyle(.segmented)

                Button {
                    onOpen(selectedRole)
                } label: {
                    CredentialPhotoArchivePreview(
                        credential: credential,
                        role: selectedRole
                    )
                }
                .buttonStyle(.plain)

                LazyVGrid(columns: [GridItem(.adaptive(minimum: 132), spacing: 9)], spacing: 9) {
                    ForEach(PetCredentialPhotoRole.allCases) { role in
                        Button {
                            selectedRole = role
                        } label: {
                            CredentialPhotoAssetTile(
                                role: role,
                                isSelected: selectedRole == role,
                                tint: credential.kind.tint
                            )
                        }
                        .buttonStyle(.plain)
                    }
                }

                HStack(spacing: 8) {
                    Button {
                        onOpen(selectedRole)
                    } label: {
                        CredentialActionLabel(
                            title: "查看照片",
                            systemImage: "arrow.up.left.and.arrow.down.right",
                            tint: credential.kind.tint
                        )
                    }
                    .buttonStyle(.plain)

                    Button {
                        onNotice("照片保存会在高清导出链路接入后开放。")
                    } label: {
                        CredentialActionLabel(
                            title: "保存照片",
                            systemImage: "square.and.arrow.down.fill",
                            tint: credential.kind.tint
                        )
                    }
                    .buttonStyle(.plain)
                }
            }
        }
    }
}

private struct CredentialPhotoArchivePreview: View {
    var credential: PetCredentialSnapshot
    var role: PetCredentialPhotoRole

    var body: some View {
        ZStack(alignment: .bottomLeading) {
            previewImage

            LinearGradient(
                colors: [.black.opacity(0), .black.opacity(0.58)],
                startPoint: .top,
                endPoint: .bottom
            )

            VStack(alignment: .leading, spacing: 5) {
                Label(role.title, systemImage: role.systemImage)
                    .font(.caption.weight(.bold))
                    .foregroundStyle(.white.opacity(0.9))
                Text(role == .officialIDPortrait ? "按证件规范生成的正面证件照，用于身份卡、护照、驾驶证和健康证。" : "保留上传时的原始生活照，用于详情页和档案查看。")
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(.white)
                    .lineSpacing(2)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .padding(14)
        }
        .frame(maxWidth: .infinity)
        .background(credential.kind.tint.opacity(0.1))
        .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .stroke(.white.opacity(0.7), lineWidth: 1)
        }
        .shadow(color: credential.kind.tint.opacity(0.14), radius: 18, x: 0, y: 8)
    }

    @ViewBuilder
    private var previewImage: some View {
        if role == .officialIDPortrait {
            ZStack {
                LinearGradient(
                    colors: [
                        Color(hex: 0xEAF4F7),
                        Color(hex: 0xF8F2E6)
                    ],
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                )

                CredentialPassportPhotoPattern(tint: credential.kind.tint.opacity(0.15))

                CredentialPetPhoto(petID: credential.petID, petType: credential.petType, contentMode: .fit)
                    .frame(height: 286)
                    .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
                    .padding(.vertical, 12)
                    .shadow(color: .black.opacity(0.12), radius: 16, x: 0, y: 8)
            }
            .frame(maxWidth: .infinity)
            .frame(height: 330)
        } else {
            CredentialPetPhoto(petID: credential.petID, petType: credential.petType, contentMode: .fill)
                .frame(maxWidth: .infinity)
                .frame(height: 286)
                .clipped()
        }
    }
}

private struct CredentialPassportPhotoPattern: View {
    var tint: Color

    var body: some View {
        Canvas { context, size in
            guard size.width > 0, size.height > 0 else { return }

            for index in 0..<7 {
                let y = size.height * (0.12 + CGFloat(index) * 0.12)
                var path = Path()
                path.move(to: CGPoint(x: -16, y: y))
                path.addCurve(
                    to: CGPoint(x: size.width + 16, y: y + CGFloat(index % 2 == 0 ? 22 : -18)),
                    control1: CGPoint(x: size.width * 0.28, y: y - 26),
                    control2: CGPoint(x: size.width * 0.72, y: y + 30)
                )
                context.stroke(path, with: .color(tint.opacity(0.5)), style: StrokeStyle(lineWidth: 0.9, lineCap: .round))
            }

            let sealRect = CGRect(x: size.width - 112, y: 26, width: 86, height: 86)
            context.stroke(Path(ellipseIn: sealRect), with: .color(tint.opacity(0.42)), lineWidth: 1.2)
            context.stroke(Path(ellipseIn: sealRect.insetBy(dx: 12, dy: 12)), with: .color(tint.opacity(0.28)), lineWidth: 0.9)
        }
        .allowsHitTesting(false)
        .accessibilityHidden(true)
    }
}

private struct CredentialPhotoAssetTile: View {
    var role: PetCredentialPhotoRole
    var isSelected: Bool
    var tint: Color

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: role.systemImage)
                .font(.caption.weight(.bold))
                .foregroundStyle(isSelected ? .white : tint)
                .frame(width: 28, height: 28)
                .background(isSelected ? .white.opacity(0.18) : tint.opacity(0.1))
                .clipShape(Circle())

            VStack(alignment: .leading, spacing: 2) {
                Text(role.title)
                    .font(.caption.weight(.bold))
                    .foregroundStyle(isSelected ? .white : DesignTokens.ink)
                Text(role.subtitle)
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(isSelected ? .white.opacity(0.76) : DesignTokens.secondaryInk)
                    .lineLimit(1)
                    .minimumScaleFactor(0.78)
            }

            Spacer(minLength: 0)
        }
        .padding(10)
        .frame(minHeight: 54)
        .background(isSelected ? tint : DesignTokens.mist.opacity(0.5))
        .clipShape(RoundedRectangle(cornerRadius: DesignTokens.cardRadius, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: DesignTokens.cardRadius, style: .continuous)
                .stroke(isSelected ? .white.opacity(0.2) : tint.opacity(0.12), lineWidth: 1)
        }
    }
}

private struct PetCredentialPortraitViewer: View {
    var credential: PetCredentialSnapshot
    @Environment(\.dismiss) private var dismiss
    @State private var selectedRole: PetCredentialPhotoRole

    init(credential: PetCredentialSnapshot, initialRole: PetCredentialPhotoRole) {
        self.credential = credential
        _selectedRole = State(initialValue: initialRole)
    }

    var body: some View {
        ZStack {
            Color.black.opacity(0.88)
                .ignoresSafeArea()

            VStack(spacing: 16) {
                HStack {
                    VStack(alignment: .leading, spacing: 3) {
                        Text(selectedRole.title)
                            .font(.headline.weight(.semibold))
                            .foregroundStyle(.white)
                        Text(credential.kind.subtitle)
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(.white.opacity(0.68))
                    }

                    Spacer()

                    Button {
                        dismiss()
                    } label: {
                        Image(systemName: "xmark")
                            .font(.headline.weight(.bold))
                            .foregroundStyle(.white)
                            .frame(width: 38, height: 38)
                            .background(.white.opacity(0.14))
                            .clipShape(Circle())
                    }
                    .buttonStyle(.plain)
                }
                .padding(.horizontal, DesignTokens.pagePadding)
                .padding(.top, 20)

                Spacer(minLength: 0)

                CredentialPetPhoto(petID: credential.petID, petType: credential.petType, contentMode: .fit)
                    .frame(maxWidth: .infinity)
                    .frame(maxHeight: 560)
                    .clipShape(RoundedRectangle(cornerRadius: 24, style: .continuous))
                    .overlay {
                        RoundedRectangle(cornerRadius: 24, style: .continuous)
                            .stroke(.white.opacity(0.16), lineWidth: 1)
                    }
                    .shadow(color: .black.opacity(0.38), radius: 28, x: 0, y: 16)
                    .padding(.horizontal, DesignTokens.pagePadding)

                Spacer(minLength: 0)

                VStack(spacing: 12) {
                    Picker("照片档案", selection: $selectedRole) {
                        ForEach(PetCredentialPhotoRole.allCases) { role in
                            Text(role.title).tag(role)
                        }
                    }
                    .pickerStyle(.segmented)

                    HStack(spacing: 8) {
                        ShareLink(item: credential.shareText) {
                            CredentialActionLabel(
                                title: "分享",
                                systemImage: "square.and.arrow.up",
                                tint: .white
                            )
                        }
                        .buttonStyle(.plain)

                        Button {
                            dismiss()
                        } label: {
                            CredentialActionLabel(
                                title: "完成",
                                systemImage: "checkmark",
                                tint: .white
                            )
                        }
                        .buttonStyle(.plain)
                    }
                }
                .padding(DesignTokens.pagePadding)
                .background(.black.opacity(0.2))
            }
        }
    }
}

private struct WalletProgressPill: View {
    var title: String
    var value: String
    var tint: Color

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(value)
                .font(.subheadline.weight(.bold))
                .foregroundStyle(DesignTokens.ink)
                .lineLimit(1)
                .minimumScaleFactor(0.76)
            Text(title)
                .font(.caption2.weight(.semibold))
                .foregroundStyle(DesignTokens.secondaryInk)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(10)
        .background(tint.opacity(0.1))
        .clipShape(RoundedRectangle(cornerRadius: DesignTokens.cardRadius, style: .continuous))
    }
}

private struct CredentialWalletTile: View {
    var credential: PetCredentialSnapshot
    var isSelected: Bool

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: credential.isUnlocked ? credential.kind.systemImage : "lock.fill")
                .font(.caption.weight(.bold))
                .foregroundStyle(isSelected ? .white : credential.kind.tint)
                .frame(width: 28, height: 28)
                .background((isSelected ? .white : credential.kind.tint).opacity(isSelected ? 0.16 : 0.1))
                .clipShape(Circle())

            VStack(alignment: .leading, spacing: 2) {
                Text(credential.kind.subtitle)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(isSelected ? .white : DesignTokens.ink)
                    .lineLimit(1)
                    .minimumScaleFactor(0.78)
                Text(credential.isUnlocked ? credential.statusLine : credential.unlockHint)
                    .font(.caption2)
                    .foregroundStyle(isSelected ? .white.opacity(0.76) : DesignTokens.secondaryInk)
                    .lineLimit(1)
                    .minimumScaleFactor(0.72)
            }

            Spacer(minLength: 0)
        }
        .padding(10)
        .frame(minHeight: 54)
        .background(isSelected ? credential.kind.tint : .white.opacity(0.74))
        .clipShape(RoundedRectangle(cornerRadius: DesignTokens.cardRadius, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: DesignTokens.cardRadius, style: .continuous)
                .stroke(isSelected ? .white.opacity(0.26) : credential.kind.tint.opacity(0.16), lineWidth: 1)
        }
        .opacity(credential.isUnlocked ? 1 : 0.62)
    }
}

private struct CredentialComingSoonTile: View {
    var title: String
    var detail: String
    var systemImage: String
    var tint: Color

    var body: some View {
        HStack(spacing: 9) {
            Image(systemName: systemImage)
                .font(.caption.weight(.bold))
                .foregroundStyle(tint)
                .frame(width: 30, height: 30)
                .background(tint.opacity(0.11))
                .clipShape(Circle())

            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(DesignTokens.ink)
                Text(detail)
                    .font(.caption2)
                    .foregroundStyle(DesignTokens.secondaryInk)
                    .lineLimit(1)
                    .minimumScaleFactor(0.74)
            }

            Spacer(minLength: 0)

            Text("未解锁")
                .font(.caption2.weight(.bold))
                .foregroundStyle(tint)
                .padding(.vertical, 5)
                .padding(.horizontal, 8)
                .background(tint.opacity(0.1))
                .clipShape(Capsule())
        }
        .padding(11)
        .background(.white.opacity(0.68))
        .clipShape(RoundedRectangle(cornerRadius: DesignTokens.cardRadius, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: DesignTokens.cardRadius, style: .continuous)
                .stroke(tint.opacity(0.14), lineWidth: 1)
        }
    }
}

private struct PetCredentialCard: View {
    var credential: PetCredentialSnapshot

    var body: some View {
        ZStack(alignment: .topLeading) {
            documentImage
                .opacity(credential.isUnlocked ? 1 : 0.54)

            if !credential.isUnlocked {
                VStack(spacing: 8) {
                    Image(systemName: "lock.fill")
                        .font(.headline.weight(.bold))
                        .foregroundStyle(.white)
                        .frame(width: 38, height: 38)
                        .background(.black.opacity(0.2))
                        .clipShape(Circle())
                    Text(credential.unlockHint)
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.white)
                        .multilineTextAlignment(.center)
                        .lineLimit(2)
                        .minimumScaleFactor(0.76)
                        .padding(.horizontal, 18)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .background(.black.opacity(0.16))
            }
        }
        .frame(maxWidth: .infinity)
        .aspectRatio(credential.kind.documentAspectRatio, contentMode: .fit)
        .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .stroke(.white.opacity(0.38), lineWidth: 1)
        }
        .overlay(alignment: .top) {
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .stroke(
                    LinearGradient(
                        colors: [.white.opacity(0.58), .white.opacity(0.05)],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    ),
                    lineWidth: 1
                )
                .allowsHitTesting(false)
        }
        .shadow(color: credential.kind.tint.opacity(0.24), radius: 24, x: 0, y: 12)
    }

    private var documentImage: some View {
        ZStack {
            LinearGradient(
                colors: credential.kind.gradientColors,
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )

            CredentialCardTexture(tint: .white)

            VStack(alignment: .leading, spacing: 0) {
                HStack(alignment: .top, spacing: 10) {
                    VStack(alignment: .leading, spacing: 2) {
                        Text("PETSOUL REPUBLIC")
                            .font(.system(size: 9, weight: .heavy, design: .rounded))
                            .foregroundStyle(.white.opacity(0.72))
                            .kerning(1.4)
                        Text(credential.kind.title)
                            .font(.headline.weight(.bold))
                            .foregroundStyle(.white)
                            .lineLimit(1)
                            .minimumScaleFactor(0.7)
                        Text(credential.kind.subtitle)
                            .font(.caption2.weight(.semibold))
                            .foregroundStyle(.white.opacity(0.78))
                            .lineLimit(1)
                    }

                    Spacer(minLength: 8)

                    CredentialSeal(text: credential.kind.rarity)
                }

                Spacer(minLength: 10)

                HStack(alignment: .bottom, spacing: 12) {
                    if credential.kind.category == .documents {
                        CredentialPortraitGlyph(
                            petID: credential.petID,
                            petType: credential.petType,
                            tint: credential.kind.tint
                        )
                    }

                    VStack(alignment: .leading, spacing: 6) {
                        ForEach(credential.cardDisplayFields, id: \.0) { field in
                            CredentialTinyField(title: field.0, value: field.1)
                        }
                    }

                    Spacer(minLength: 0)
                }
            }
            .padding(15)
        }
    }
}

private struct CredentialCardTexture: View {
    var tint: Color

    var body: some View {
        Canvas { context, size in
            guard size.width > 0, size.height > 0 else { return }
            for index in 0..<5 {
                let y = size.height * (0.15 + CGFloat(index) * 0.18)
                var path = Path()
                path.move(to: CGPoint(x: -20, y: y))
                path.addCurve(
                    to: CGPoint(x: size.width + 20, y: y + CGFloat(index % 2 == 0 ? 34 : -28)),
                    control1: CGPoint(x: size.width * 0.28, y: y - 36),
                    control2: CGPoint(x: size.width * 0.72, y: y + 42)
                )
                context.stroke(path, with: .color(tint.opacity(0.16)), style: StrokeStyle(lineWidth: 1.1, lineCap: .round))
            }

            let sealRect = CGRect(x: size.width - 124, y: size.height - 124, width: 160, height: 160)
            context.stroke(Path(ellipseIn: sealRect), with: .color(tint.opacity(0.18)), lineWidth: 1.4)
            context.stroke(Path(ellipseIn: sealRect.insetBy(dx: 18, dy: 18)), with: .color(tint.opacity(0.13)), lineWidth: 1)

            let step: CGFloat = 18
            var x: CGFloat = 14
            while x < size.width - 14 {
                var y: CGFloat = 18
                while y < size.height - 18 {
                    let offset = sin(Double(x * 0.21 + y * 0.13)) * 1.6
                    let rect = CGRect(x: x + CGFloat(offset), y: y, width: 1.4, height: 1.4)
                    context.fill(Path(ellipseIn: rect), with: .color(tint.opacity(0.075)))
                    y += step
                }
                x += step
            }
        }
        .allowsHitTesting(false)
        .accessibilityHidden(true)
    }
}

private struct CredentialPetPhoto: View {
    var petID: String
    var petType: PetType
    var contentMode: ContentMode = .fill

    var body: some View {
        if let image = PetAvatarStore.image(for: petID) {
            Image(uiImage: image)
                .resizable()
                .aspectRatio(contentMode: contentMode)
        } else {
            ZStack {
                DesignTokens.petal
                Image(systemName: petType.symbolName)
                    .font(.system(size: 56, weight: .semibold))
                    .foregroundStyle(DesignTokens.clay)
            }
            .aspectRatio(3.0 / 4.0, contentMode: contentMode)
        }
    }
}

private struct CredentialPortraitGlyph: View {
    var petID: String
    var petType: PetType
    var tint: Color
    var width: CGFloat = 76
    var height: CGFloat = 82

    var body: some View {
        ZStack(alignment: .bottom) {
            Group {
                if let image = PetAvatarStore.image(for: petID) {
                    Image(uiImage: image)
                        .resizable()
                        .scaledToFill()
                } else {
                    ZStack {
                        tint.opacity(0.4)
                        Image(systemName: petType.symbolName)
                            .font(.system(size: width * 0.38, weight: .semibold))
                            .foregroundStyle(.white.opacity(0.92))
                    }
                }
            }
            .frame(width: width, height: height)
            .clipped()

            Text(petType.displayName)
                .font(.system(size: 8, weight: .heavy, design: .rounded))
                .foregroundStyle(.white)
                .lineLimit(1)
                .minimumScaleFactor(0.62)
                .padding(.vertical, 4)
                .padding(.horizontal, 7)
                .frame(maxWidth: .infinity)
                .background(.black.opacity(0.32))
        }
        .frame(width: width, height: height)
        .background(.white.opacity(0.15))
        .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .stroke(.white.opacity(0.25), lineWidth: 1)
        }
    }
}

private struct CredentialTinyField: View {
    var title: String
    var value: String

    var body: some View {
        VStack(alignment: .leading, spacing: 1) {
            Text(title.uppercased())
                .font(.system(size: 8, weight: .bold))
                .foregroundStyle(.white.opacity(0.62))
            Text(value)
                .font(.caption.weight(.semibold))
                .foregroundStyle(.white)
                .lineLimit(1)
                .minimumScaleFactor(0.72)
        }
    }
}

private struct CredentialSeal: View {
    var text: String

    var body: some View {
        ZStack {
            Circle()
                .stroke(.white.opacity(0.56), lineWidth: 1.2)
            Circle()
                .stroke(.white.opacity(0.28), lineWidth: 1)
                .padding(5)
            Text(text.uppercased())
                .font(.system(size: 9, weight: .heavy, design: .rounded))
                .foregroundStyle(.white.opacity(0.86))
                .lineLimit(1)
                .minimumScaleFactor(0.55)
                .padding(9)
        }
        .frame(width: 48, height: 48)
    }
}

private struct CredentialDetailPanel: View {
    var credential: PetCredentialSnapshot
    var onNotice: (String) -> Void

    var body: some View {
        SoftCard {
            VStack(alignment: .leading, spacing: 13) {
                HStack(spacing: 10) {
                    Image(systemName: credential.kind.systemImage)
                        .font(.headline.weight(.semibold))
                        .foregroundStyle(credential.kind.tint)
                        .frame(width: 34, height: 34)
                        .background(credential.kind.tint.opacity(0.12))
                        .clipShape(Circle())

                    VStack(alignment: .leading, spacing: 2) {
                        Text(detailTitle)
                            .font(.headline.weight(.semibold))
                            .foregroundStyle(DesignTokens.ink)
                        Text(detailSubtitle)
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(DesignTokens.secondaryInk)
                            .lineLimit(2)
                    }

                    Spacer(minLength: 0)

                    Text(credential.isUnlocked ? "已解锁" : "未解锁")
                        .font(.caption2.weight(.bold))
                        .foregroundStyle(credential.isUnlocked ? credential.kind.tint : DesignTokens.secondaryInk)
                        .padding(.vertical, 5)
                        .padding(.horizontal, 8)
                        .background((credential.isUnlocked ? credential.kind.tint : DesignTokens.secondaryInk).opacity(0.1))
                        .clipShape(Capsule())
                }

                Text(credential.detailDescription)
                    .font(.subheadline)
                    .foregroundStyle(DesignTokens.ink)
                    .lineSpacing(3)
                    .fixedSize(horizontal: false, vertical: true)

                LazyVGrid(columns: [GridItem(.adaptive(minimum: 96), spacing: 8)], spacing: 8) {
                    ForEach(Array(credential.keyDetailFields.enumerated()), id: \.offset) { _, field in
                        CredentialInfoTile(title: field.0, value: field.1, tint: credential.kind.tint)
                    }
                }

                if !credential.isUnlocked {
                    HStack(spacing: 8) {
                        Image(systemName: "lock.fill")
                            .font(.caption.weight(.bold))
                            .foregroundStyle(credential.kind.tint)
                        Text(credential.unlockHint)
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(DesignTokens.secondaryInk)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    .padding(10)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(credential.kind.tint.opacity(0.09))
                    .clipShape(RoundedRectangle(cornerRadius: DesignTokens.cardRadius, style: .continuous))
                }

                VStack(alignment: .leading, spacing: 9) {
                    Text(credential.kind == .healthRecord ? "基本信息" : "字段信息")
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(DesignTokens.ink)

                    LazyVGrid(columns: [GridItem(.adaptive(minimum: 132), spacing: 9)], spacing: 9) {
                        ForEach(Array(detailFields.enumerated()), id: \.offset) { _, field in
                            CredentialInfoTile(title: field.0, value: field.1, tint: credential.kind.tint)
                        }
                    }
                }

                if let careNote = credential.careNote, credential.kind == .healthRecord {
                    VStack(alignment: .leading, spacing: 5) {
                        Text("照护备注")
                            .font(.caption.weight(.bold))
                            .foregroundStyle(DesignTokens.secondaryInk)
                        Text(careNote)
                            .font(.subheadline.weight(.semibold))
                            .foregroundStyle(DesignTokens.ink)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    .padding(11)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(credential.kind.tint.opacity(0.09))
                    .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
                }

                HStack(spacing: 7) {
                    ForEach(credential.stamps, id: \.self) { stamp in
                        Label(stamp, systemImage: "seal.fill")
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(credential.kind.tint)
                            .padding(.vertical, 7)
                            .padding(.horizontal, 9)
                            .background(credential.kind.tint.opacity(0.1))
                            .clipShape(Capsule())
                    }
                }

                Text(credential.requirementNote)
                    .font(.subheadline)
                    .foregroundStyle(DesignTokens.secondaryInk)
                    .lineSpacing(3)
                    .fixedSize(horizontal: false, vertical: true)

                Text(credential.safetyLine)
                    .font(.caption)
                    .foregroundStyle(DesignTokens.secondaryInk)
                    .lineSpacing(2)
                    .padding(10)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(DesignTokens.mist.opacity(0.58))
                    .clipShape(RoundedRectangle(cornerRadius: DesignTokens.cardRadius, style: .continuous))

                LazyVGrid(columns: [GridItem(.adaptive(minimum: 110), spacing: 8)], spacing: 8) {
                    ShareLink(item: credential.shareText) {
                        CredentialActionLabel(
                            title: "分享",
                            systemImage: "square.and.arrow.up",
                            tint: credential.kind.tint
                        )
                    }
                    .buttonStyle(.plain)

                    Button {
                        onNotice(credential.isUnlocked ? "高清卡片保存会在模板导出后开放。" : "先解锁这张证件，再保存高清卡片。")
                    } label: {
                        CredentialActionLabel(
                            title: "保存",
                            systemImage: "square.and.arrow.down.fill",
                            tint: credential.kind.tint
                        )
                    }
                    .buttonStyle(.plain)

                    Button {
                        onNotice("\(credential.kind.subtitle) 已设为当前卡包预览。")
                    } label: {
                        CredentialActionLabel(
                            title: "设封面",
                            systemImage: "rectangle.on.rectangle.angled.fill",
                            tint: credential.kind.tint
                        )
                    }
                    .buttonStyle(.plain)
                }
            }
        }
    }

    private var detailTitle: String {
        credential.kind == .healthRecord ? "\(credential.holderName) 的健康档案" : credential.kind.subtitle
    }

    private var detailSubtitle: String {
        if credential.kind == .healthRecord {
            let health = credential.keyDetailFields.first { $0.0 == "健康状态" }?.1 ?? "稳定"
            let vaccine = credential.keyDetailFields.first { $0.0 == "疫苗记录" }?.1 ?? "已记录"
            return "\(health) · 疫苗\(vaccine)"
        }
        return credential.statusLine
    }

    private var detailFields: [(String, String)] {
        if credential.kind == .healthRecord {
            return credential.basicInfoFields
        }
        return credential.fields
    }
}

private struct CredentialActionLabel: View {
    var title: String
    var systemImage: String
    var tint: Color

    var body: some View {
        Label(title, systemImage: systemImage)
            .font(.caption.weight(.semibold))
            .foregroundStyle(tint)
            .frame(maxWidth: .infinity)
            .padding(.vertical, 9)
            .padding(.horizontal, 10)
            .background(tint.opacity(0.1))
            .clipShape(RoundedRectangle(cornerRadius: DesignTokens.cardRadius, style: .continuous))
    }
}

private struct CredentialInfoTile: View {
    var title: String
    var value: String
    var tint: Color

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title)
                .font(.caption.weight(.bold))
                .foregroundStyle(DesignTokens.secondaryInk)
            Text(value)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(DesignTokens.ink)
                .lineLimit(2)
                .minimumScaleFactor(0.78)
                .fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity, minHeight: 58, alignment: .topLeading)
        .padding(10)
        .background(tint.opacity(0.09))
        .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
    }
}
