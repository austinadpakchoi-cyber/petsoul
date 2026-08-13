import PhotosUI
import SwiftUI
import UIKit

struct PetChatView: View {
    @ObservedObject var viewModel: CommunicatorViewModel
    @State var draft = ""
    @State var selectedPhotoItem: PhotosPickerItem?
    let quickPrompts = ["看看你现在", "给我拍一张", "你在哪呀", "今天开心吗"]

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
                Menu {
                    Button {
                        Task { await viewModel.load() }
                    } label: {
                        Label("刷新对话", systemImage: "arrow.clockwise")
                    }
                    Button {
                        Task { await viewModel.send("看看你现在") }
                    } label: {
                        Label("请 TA 拍一张此刻", systemImage: "camera")
                    }
                } label: {
                    Image(systemName: "ellipsis")
                        .font(.system(size: 17, weight: .semibold))
                        .foregroundStyle(DesignTokens.ink)
                        .frame(width: 34, height: 34)
                        .background(DesignTokens.surface.opacity(0.7))
                        .clipShape(Circle())
                }
                .accessibilityLabel("更多操作")
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

    var chatComposer: some View {
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
                                .background(DesignTokens.surface.opacity(0.82))
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
                        .background(DesignTokens.surface.opacity(0.82))
                        .clipShape(Circle())
                }
                .buttonStyle(.plain)
                .disabled(viewModel.isSending)

                TextField("给 \(viewModel.petName) 说一句话", text: $draft, axis: .vertical)
                    .font(.body)
                    .lineLimit(1...3)
                    .padding(.vertical, 10)
                    .padding(.horizontal, 12)
                    .background(DesignTokens.surface.opacity(0.86))
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

struct ChatStatusStrip: View {
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
        .background(DesignTokens.surface.opacity(0.68))
        .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .stroke(DesignTokens.surfaceStroke.opacity(0.72), lineWidth: 1)
        }
    }
}

struct ChatTimeSeparator: View {
    var date: Date

    var body: some View {
        Text(date.petSoulChatTimeLabel)
            .font(.caption2.weight(.medium))
            .foregroundStyle(DesignTokens.secondaryInk)
            .padding(.vertical, 4)
            .padding(.horizontal, 8)
            .background(DesignTokens.surface.opacity(0.52))
            .clipShape(Capsule())
            .padding(.bottom, 2)
    }
}

struct PetChatAvatar: View {
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
                .stroke(DesignTokens.surfaceStroke.opacity(0.9), lineWidth: 1)
        }
        .shadow(color: DesignTokens.deepInk.opacity(0.05), radius: 5, x: 0, y: 2)
    }
}

struct ChatEmptyState: View {
    var title: String = "还没有来信"
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

struct CommunicatorMessageRow: View {
    var message: CommunicatorMessage
    var petName: String
    var petType: PetType?
    var onRetry: (() -> Void)?

    var bubbleColor: Color {
        switch message.sender {
        case .owner: DesignTokens.sage.opacity(0.86)
        case .pet: DesignTokens.surface.opacity(0.9)
        case .system: DesignTokens.mist.opacity(0.76)
        }
    }

    var visibleAttachments: [CommunicatorAttachment] {
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

    var ownerRow: some View {
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
                        .background(bubbleColor)
                        .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
                        .frame(maxWidth: min(UIScreen.main.bounds.width * 0.72, 310), alignment: .trailing)
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

    var petRow: some View {
        HStack(alignment: .top, spacing: 8) {
            PetChatAvatar(petID: message.petID, petType: petType)
            VStack(alignment: .leading, spacing: 6) {
                Text(displayText)
                    .font(.body)
                    .foregroundStyle(DesignTokens.ink)
                    .lineSpacing(2)
                    .padding(.vertical, 10)
                    .padding(.horizontal, 13)
                    .background(bubbleColor)
                    .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
                    .frame(maxWidth: min(UIScreen.main.bounds.width * 0.72, 310), alignment: .leading)

                ForEach(visibleAttachments) { attachment in
                    CommunicatorAttachmentView(attachment: attachment)
                        .frame(maxWidth: 288, alignment: .leading)
                }
            }
            Spacer(minLength: 34)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    var systemRow: some View {
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

    var displayText: String {
        guard message.sender != .owner else { return message.text }
        return message.text.petSoulNaturalizedChatText
    }

    var deliveryText: String {
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

extension String {
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

extension Date {
    var petSoulChatTimeLabel: String {
        let calendar = Calendar.current
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "zh_CN")
        formatter.dateFormat = calendar.isDateInToday(self) ? "今天 HH:mm" : "M月d日 HH:mm"
        return formatter.string(from: self)
    }
}

struct CommunicatorAttachmentView: View {
    var attachment: CommunicatorAttachment

    var body: some View {
        if attachment.type == .sticker {
            Text(attachment.title)
                .font(.title3)
                .padding(.vertical, 8)
                .padding(.horizontal, 11)
                .background(DesignTokens.surface.opacity(0.62))
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
        .background(DesignTokens.surface.opacity(0.72))
        .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
        }
    }

    var systemImage: String {
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

    var tint: Color {
        switch attachment.type {
        case .postcardCandidate: DesignTokens.clay
        case .locationCard: DesignTokens.sea
        case .sticker: DesignTokens.amber
        case .ownerPhoto: DesignTokens.sage
        default: DesignTokens.sage
        }
    }
}

struct CommunicatorPhotoAttachmentView: View {
    var attachment: CommunicatorAttachment

    var isPendingGeneration: Bool {
        attachment.photoURL == nil && (
            attachment.type == .photoPlaceholder
                || attachment.type == .pendingPhotoRequest
                || attachment.state == "placeholder"
                || attachment.state == "planned"
        )
    }

    var statusBadgeText: String? {
        if isPendingGeneration {
            return "洗印中"
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
                        .stroke(DesignTokens.surfaceStroke.opacity(0.72), lineWidth: 1)
                }
        } else {
        VStack(alignment: .leading, spacing: 9) {
            photoFrame
                .frame(height: 168)
                .frame(maxWidth: .infinity)
                .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
                .overlay(
                    RoundedRectangle(cornerRadius: 14, style: .continuous)
                        .stroke(DesignTokens.surfaceStroke.opacity(0.72), lineWidth: 1)
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
        .background(DesignTokens.surface.opacity(0.74))
        .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
        }
    }

    @ViewBuilder
    var photoFrame: some View {
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

    var pendingPhotoPlaceholder: some View {
        photoPlaceholder(title: isPendingGeneration ? "这一刻的照片正在洗出来" : "这条照片没有拿到地址", systemImage: "photo.on.rectangle.angled")
    }

    var loadingPhotoPlaceholder: some View {
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

    func unavailablePhotoPlaceholder(title: String, systemImage: String) -> some View {
        photoPlaceholder(title: title, systemImage: systemImage)
    }

    func photoPlaceholder(title: String, systemImage: String) -> some View {
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

    var placeholderBackground: some View {
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
