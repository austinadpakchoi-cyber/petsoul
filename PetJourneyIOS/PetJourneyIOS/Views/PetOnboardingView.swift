import PhotosUI
import SwiftUI
import UIKit

struct PetOnboardingView: View {
    @StateObject private var viewModel = OnboardingViewModel()
    @State private var selectedPhotoItem: PhotosPickerItem?
    @State private var step: FindPetStep = .photo
    @State private var scanLineOffset: CGFloat = -0.42
    @State private var scanPhaseIndex = 0

    var onBack: () -> Void
    var onComplete: (OnboardingDraft) -> Void

    private let scanPhases = ["辨认轮廓", "读取熟悉表情", "匹配记忆锚点"]

    var body: some View {
        NavigationStack {
            ZStack {
                AppBackground()
                AmbientSignalField(
                    tint: step == .photo ? DesignTokens.sea : DesignTokens.sage,
                    warmth: DesignTokens.pollen,
                    density: 16,
                    drift: 0.58
                )
                .opacity(0.42)

                VStack(spacing: 0) {
                    ProgressHeader(step: step)
                        .padding(.horizontal, DesignTokens.pagePadding)
                        .padding(.top, 8)

                    ScrollView {
                        VStack(alignment: .leading, spacing: 18) {
                            switch step {
                            case .photo:
                                photoStep
                            case .identity:
                                identityStep
                            case .memory:
                                memoryStep
                            }
                        }
                        .padding(.horizontal, DesignTokens.pagePadding)
                        .padding(.top, 16)
                        .padding(.bottom, 24)
                    }

                    bottomControls
                }
            }
            .navigationTitle("寻找 TA")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button(action: handleBack) {
                        Label("返回", systemImage: "chevron.left")
                    }
                }
            }
            .task(id: selectedPhotoItem) {
                guard let selectedPhotoItem else { return }
                if let data = try? await selectedPhotoItem.loadTransferable(type: Data.self) {
                    withAnimation(.easeInOut(duration: 0.25)) {
                        viewModel.selectedPhotoData = data
                    }
                    startScanAnimation()
                }
            }
            .onAppear {
                startScanAnimation()
            }
            .task {
                await cycleScanPhases()
            }
        }
    }

    private var photoStep: some View {
        let petType = viewModel.petType
        let selectedPhotoData = viewModel.selectedPhotoData
        let hasPhoto = viewModel.hasPhoto

        return VStack(alignment: .leading, spacing: 18) {
            StepTitle(
                eyebrow: "第一步",
                title: "先让手机看见 TA。",
                detail: "上传一张你最熟悉的照片。手机会把这张脸作为寻找 TA 的第一个锚点。"
            )

            PhotosPicker(selection: $selectedPhotoItem, matching: .images) {
                PhotoRecognitionCard(
                    petType: petType,
                    photoData: selectedPhotoData,
                    scanLineOffset: scanLineOffset,
                    scanPhase: scanPhases[scanPhaseIndex]
                )
                .contentShape(RoundedRectangle(cornerRadius: 26, style: .continuous))
            }
            .buttonStyle(.plain)

            PhotosPicker(selection: $selectedPhotoItem, matching: .images) {
                Label(hasPhoto ? "重新选择照片" : "从相册选择照片", systemImage: "photo.on.rectangle.angled")
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(DesignTokens.ink)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 12)
                    .background(DesignTokens.surface.opacity(0.82))
                    .clipShape(RoundedRectangle(cornerRadius: DesignTokens.controlRadius, style: .continuous))
                    .overlay {
                        RoundedRectangle(cornerRadius: DesignTokens.controlRadius, style: .continuous)
                            .stroke(DesignTokens.softLine, lineWidth: 1)
                    }
            }
            .buttonStyle(.plain)

            SoftCard(padding: 16) {
                HStack(alignment: .top, spacing: 12) {
                    Image(systemName: "faceid")
                        .font(.title3.weight(.semibold))
                        .foregroundStyle(DesignTokens.dusk)
                    Text("照片会和你写下的称呼、性格、记忆一起，组成 TA 在另一端世界的通讯卡。")
                        .font(.footnote)
                        .foregroundStyle(DesignTokens.secondaryInk)
                        .lineSpacing(4)
                }
            }
        }
    }

    private var identityStep: some View {
        VStack(alignment: .leading, spacing: 18) {
            StepTitle(
                eyebrow: "第二步",
                title: "告诉我 TA 平时怎么叫你。",
                detail: "这是 TA 对你的称呼，不是给 TA 贴标签。之后的讯息会按这个关系来翻译。"
            )

            SoftCard(padding: 18) {
                HStack(alignment: .center, spacing: 14) {
                    PhotoThumb(photoData: viewModel.selectedPhotoData, petType: viewModel.petType)

                    VStack(alignment: .leading, spacing: 10) {
                        TextField("TA 的名字", text: $viewModel.name)
                            .font(.title3.weight(.semibold))
                            .textInputAutocapitalization(.never)
                            .softInputBackground()

                        PetTypeSwitch(selectedPetType: $viewModel.petType)
                    }
                }

                StoryTextField(
                    title: "TA 会怎么称呼你？",
                    placeholder: "比如：妈妈、爸爸、主人、姐姐，也可以写你们自己的称呼",
                    text: $viewModel.ownerTitle
                )

                SuggestionStrip(items: viewModel.ownerTitleSuggestions) { item in
                    viewModel.useOwnerTitleSuggestion(item)
                }
            }
        }
    }

    private var memoryStep: some View {
        VStack(alignment: .leading, spacing: 18) {
            StepTitle(
                eyebrow: "第三步",
                title: "把 TA 的性格和记忆留下来。",
                detail: "这些文字会变成 TA 在另一端世界里的语气、明信片和偏好。写得越像 TA，后面越有感觉。"
            )

            SoftCard(padding: 18) {
                StoryEditor(
                    title: "TA 是什么性格？",
                    placeholder: "比如：它很黏人，睡前一定要靠着我；胆子小，但听到我回家会马上跑过来。",
                    text: $viewModel.personalityDescription,
                    minHeight: 118
                )

                SuggestionColumn(items: viewModel.personalitySuggestions) { item in
                    viewModel.usePersonalitySuggestion(item)
                }

                Divider()
                    .overlay(DesignTokens.softLine)

                StoryTextField(
                    title: "TA 喜欢哪些地方？",
                    placeholder: "海边、草地、家门口、阳台……",
                    text: $viewModel.favoritePlacesText
                )

                SuggestionStrip(items: viewModel.placeSuggestions) { item in
                    viewModel.addPlaceSuggestion(item)
                }

                StoryTextField(
                    title: "你最想让手机记住的一句话",
                    placeholder: "比如：慢慢走，我在",
                    text: $viewModel.catchphrase
                )
            }

            CommunicationCardPreview(viewModel: viewModel)
        }
    }

    private var bottomControls: some View {
        VStack(spacing: 10) {
            Button(action: handlePrimaryAction) {
                Label(primaryTitle, systemImage: primaryIcon)
            }
            .primaryActionStyle()
            .disabled(!canUsePrimaryAction)
            .opacity(canUsePrimaryAction ? 1 : 0.45)

            if step == .photo && !viewModel.hasPhoto {
                Button {
                    withAnimation(.easeInOut(duration: 0.25)) {
                        step = .identity
                    }
                } label: {
                    Text("暂时没有照片，先用记忆寻找")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(DesignTokens.secondaryInk)
                }
                .buttonStyle(.plain)
            } else {
                Text(helperText)
                    .font(.caption)
                    .foregroundStyle(DesignTokens.secondaryInk)
                    .multilineTextAlignment(.center)
            }
        }
        .padding(.horizontal, DesignTokens.pagePadding)
        .padding(.top, 12)
        .padding(.bottom, 18)
        .background(.ultraThinMaterial)
    }

    private var primaryTitle: String {
        switch step {
        case .photo: "开始照片识别"
        case .identity: "继续写下 TA 的记忆"
        case .memory: "生成通讯卡并寻找 TA"
        }
    }

    private var primaryIcon: String {
        switch step {
        case .photo: "camera.viewfinder"
        case .identity: "text.bubble"
        case .memory: "dot.radiowaves.left.and.right"
        }
    }

    private var helperText: String {
        switch step {
        case .photo:
            viewModel.hasPhoto ? "照片已经成为这次寻找的第一个锚点。" : "先上传一张照片，会让寻找仪式更像 TA。"
        case .identity:
            viewModel.canContinueIdentity ? "很好，手机已经知道 TA 会怎么叫你。" : "写下名字和 TA 对你的称呼，就能继续。"
        case .memory:
            viewModel.canContinue ? "准备好了，下一步会开始连接。" : "至少写下一句性格描述，让 TA 的声音更像 TA。"
        }
    }

    private var canUsePrimaryAction: Bool {
        switch step {
        case .photo: viewModel.hasPhoto
        case .identity: viewModel.canContinueIdentity
        case .memory: viewModel.canContinue
        }
    }

    private func handlePrimaryAction() {
        switch step {
        case .photo:
            withAnimation(.easeInOut(duration: 0.25)) { step = .identity }
        case .identity:
            withAnimation(.easeInOut(duration: 0.25)) { step = .memory }
        case .memory:
            if let draft = viewModel.draft {
                onComplete(draft)
            }
        }
    }

    private func handleBack() {
        switch step {
        case .photo:
            onBack()
        case .identity:
            withAnimation(.easeInOut(duration: 0.25)) { step = .photo }
        case .memory:
            withAnimation(.easeInOut(duration: 0.25)) { step = .identity }
        }
    }

    private func startScanAnimation() {
        withAnimation(.easeInOut(duration: 1.5).repeatForever(autoreverses: true)) {
            scanLineOffset = 0.42
        }
    }

    private func cycleScanPhases() async {
        while !Task.isCancelled {
            try? await Task.sleep(for: .seconds(1.1))
            if !Task.isCancelled {
                withAnimation(.easeInOut(duration: 0.2)) {
                    scanPhaseIndex = (scanPhaseIndex + 1) % scanPhases.count
                }
            }
        }
    }
}

private enum FindPetStep: Int, CaseIterable {
    case photo
    case identity
    case memory

    var title: String {
        switch self {
        case .photo: "照片"
        case .identity: "身份"
        case .memory: "记忆"
        }
    }
}

private struct ProgressHeader: View {
    var step: FindPetStep

    var body: some View {
        VStack(spacing: 10) {
            HStack {
                ForEach(FindPetStep.allCases, id: \.self) { item in
                    VStack(spacing: 6) {
                        Capsule()
                            .fill(item.rawValue <= step.rawValue ? DesignTokens.sage : DesignTokens.softLine)
                            .frame(height: 5)
                        Text(item.title)
                            .font(.caption2.weight(.semibold))
                            .foregroundStyle(item == step ? DesignTokens.ink : DesignTokens.secondaryInk)
                    }
                }
            }
        }
        .padding(.vertical, 10)
    }
}

private struct StepTitle: View {
    var eyebrow: String
    var title: String
    var detail: String

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(eyebrow)
                .font(.caption.weight(.semibold))
                .foregroundStyle(DesignTokens.sage)
            Text(title)
                .font(.title.weight(.semibold))
                .foregroundStyle(DesignTokens.ink)
                .fixedSize(horizontal: false, vertical: true)
            Text(detail)
                .font(.subheadline)
                .foregroundStyle(DesignTokens.secondaryInk)
                .lineSpacing(3)
                .fixedSize(horizontal: false, vertical: true)
        }
    }
}

private struct PhotoRecognitionCard: View {
    var petType: PetType
    var photoData: Data?
    var scanLineOffset: CGFloat
    var scanPhase: String

    var body: some View {
        SoftCard(padding: 14) {
            ZStack {
                photoSurface
                    .frame(height: 360)
                    .clipShape(RoundedRectangle(cornerRadius: 22, style: .continuous))

                if photoData != nil {
                    scanOverlay
                } else {
                    SignalPulseRings(tint: DesignTokens.clay, size: 178, lineWidth: 1.3, ringCount: 2)
                        .opacity(0.54)
                }

                VStack {
                    Spacer()
                    HStack {
                        Label(photoData == nil ? "上传 TA 的照片" : scanPhase, systemImage: photoData == nil ? "photo.badge.plus" : "faceid")
                            .font(.subheadline.weight(.semibold))
                            .foregroundStyle(photoData == nil ? DesignTokens.ink : .white)
                            .padding(.vertical, 10)
                            .padding(.horizontal, 14)
                            .background(photoData == nil ? .white.opacity(0.86) : DesignTokens.ink.opacity(0.68))
                            .clipShape(Capsule())
                        Spacer()
                    }
                    .padding(14)
                }
            }
            .overlay {
                RoundedRectangle(cornerRadius: 22, style: .continuous)
                    .stroke(DesignTokens.surfaceStroke.opacity(0.82), lineWidth: 1)
            }

            HStack(spacing: 10) {
                RecognitionBadge(title: "轮廓", isActive: photoData != nil)
                RecognitionBadge(title: "表情", isActive: photoData != nil)
                RecognitionBadge(title: "记忆锚点", isActive: photoData != nil)
            }
        }
    }

    @ViewBuilder
    private var photoSurface: some View {
        if let photoData, let image = UIImage(data: photoData) {
            Image(uiImage: image)
                .resizable()
                .scaledToFill()
        } else {
            ZStack {
                LinearGradient(
                    colors: [DesignTokens.petal, DesignTokens.sky, DesignTokens.mist],
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                )
                VStack(spacing: 16) {
                    Image(systemName: petType.symbolName)
                        .font(.system(size: 56, weight: .semibold))
                        .foregroundStyle(DesignTokens.clay)
                    Text("点这里选择一张照片")
                        .font(.headline)
                        .foregroundStyle(DesignTokens.ink)
                    Text("最好是你一眼就觉得：这就是 TA。")
                        .font(.subheadline)
                        .foregroundStyle(DesignTokens.secondaryInk)
                }
            }
        }
    }

    private var scanOverlay: some View {
        GeometryReader { proxy in
            let y = proxy.size.height * (0.5 + scanLineOffset)
            ZStack {
                Rectangle()
                    .fill(.black.opacity(0.08))
                Rectangle()
                    .fill(
                        LinearGradient(
                            colors: [.clear, DesignTokens.sea.opacity(0.76), DesignTokens.pollen.opacity(0.72), .clear],
                            startPoint: .leading,
                            endPoint: .trailing
                        )
                    )
                    .frame(height: 3)
                    .position(x: proxy.size.width / 2, y: y)
                Rectangle()
                    .fill(
                        LinearGradient(
                            colors: [.clear, DesignTokens.sage.opacity(0.32), .clear],
                            startPoint: .top,
                            endPoint: .bottom
                        )
                    )
                    .frame(width: 2, height: proxy.size.height * 0.62)
                    .position(x: proxy.size.width * 0.5, y: proxy.size.height * 0.47)
                RoundedRectangle(cornerRadius: 28, style: .continuous)
                    .stroke(DesignTokens.sage.opacity(0.9), lineWidth: 2)
                    .frame(width: proxy.size.width * 0.54, height: proxy.size.height * 0.48)
                    .position(x: proxy.size.width / 2, y: proxy.size.height * 0.46)
                ForEach(0..<6, id: \.self) { index in
                    let xFactor: CGFloat = [0.31, 0.42, 0.63, 0.70, 0.38, 0.58][index]
                    let yFactor: CGFloat = [0.30, 0.43, 0.36, 0.57, 0.63, 0.70][index]
                    Circle()
                        .fill((index.isMultiple(of: 2) ? DesignTokens.pollen : DesignTokens.sea).opacity(0.86))
                        .frame(width: 7, height: 7)
                        .overlay {
                            Circle().stroke(DesignTokens.surfaceStroke.opacity(0.92), lineWidth: 1.2)
                        }
                        .position(x: proxy.size.width * xFactor, y: proxy.size.height * yFactor)
                }
            }
        }
    }
}

private struct RecognitionBadge: View {
    var title: String
    var isActive: Bool

    var body: some View {
        Label(title, systemImage: isActive ? "checkmark.circle.fill" : "circle")
            .font(.caption.weight(.semibold))
            .foregroundStyle(isActive ? DesignTokens.sage : DesignTokens.secondaryInk)
            .frame(maxWidth: .infinity)
            .padding(.vertical, 9)
            .background(DesignTokens.surface.opacity(0.72))
            .clipShape(Capsule())
    }
}

private struct PhotoThumb: View {
    var photoData: Data?
    var petType: PetType

    var body: some View {
        ZStack {
            if let photoData, let image = UIImage(data: photoData) {
                Image(uiImage: image)
                    .resizable()
                    .scaledToFill()
            } else {
                DesignTokens.petal
                Image(systemName: petType.symbolName)
                    .font(.system(size: 28, weight: .semibold))
                    .foregroundStyle(DesignTokens.clay)
            }
        }
        .frame(width: 84, height: 96)
        .clipShape(RoundedRectangle(cornerRadius: DesignTokens.cardRadius, style: .continuous))
    }
}

private struct PetTypeSwitch: View {
    @Binding var selectedPetType: PetType
    private let columns = [
        GridItem(.flexible(), spacing: 8),
        GridItem(.flexible(), spacing: 8),
        GridItem(.flexible(), spacing: 8)
    ]

    var body: some View {
        LazyVGrid(columns: columns, spacing: 8) {
            ForEach(PetType.allCases) { type in
                Button {
                    selectedPetType = type
                } label: {
                    VStack(spacing: 5) {
                        Image(systemName: type.symbolName)
                            .font(.system(size: 15, weight: .semibold))
                        Text(type.displayName)
                            .font(.caption2.weight(.semibold))
                            .lineLimit(1)
                            .minimumScaleFactor(0.78)
                    }
                    .foregroundStyle(selectedPetType == type ? .white : DesignTokens.ink)
                    .frame(maxWidth: .infinity)
                    .frame(height: 52)
                    .background(selectedPetType == type ? DesignTokens.ink : DesignTokens.mist)
                    .clipShape(RoundedRectangle(cornerRadius: DesignTokens.controlRadius, style: .continuous))
                }
                .buttonStyle(.plain)
                .accessibilityLabel(type.displayName)
            }
        }
    }
}

private struct StoryTextField: View {
    var title: String
    var placeholder: String
    @Binding var text: String

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(DesignTokens.ink)
            TextField(placeholder, text: $text, axis: .vertical)
                .lineLimit(2...4)
                .softInputBackground()
        }
    }
}

private struct StoryEditor: View {
    var title: String
    var placeholder: String
    @Binding var text: String
    var minHeight: CGFloat

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(DesignTokens.ink)

            ZStack(alignment: .topLeading) {
                if text.isEmpty {
                    Text(placeholder)
                        .font(.subheadline)
                        .foregroundStyle(DesignTokens.secondaryInk.opacity(0.68))
                        .padding(.top, 13)
                        .padding(.horizontal, 14)
                }

                TextEditor(text: $text)
                    .font(.subheadline)
                    .foregroundStyle(DesignTokens.ink)
                    .scrollContentBackground(.hidden)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 5)
                    .frame(minHeight: minHeight)
            }
            .background(DesignTokens.mist)
            .clipShape(RoundedRectangle(cornerRadius: DesignTokens.controlRadius, style: .continuous))
        }
    }
}

private struct SuggestionStrip: View {
    var items: [String]
    var onTap: (String) -> Void

    var body: some View {
        ScrollView(.horizontal) {
            HStack(spacing: 8) {
                ForEach(items, id: \.self) { item in
                    Button(item) {
                        onTap(item)
                    }
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(DesignTokens.secondaryInk)
                    .padding(.vertical, 8)
                    .padding(.horizontal, 10)
                    .background(DesignTokens.surface.opacity(0.78))
                    .clipShape(Capsule())
                }
            }
        }
        .scrollIndicators(.hidden)
    }
}

private struct SuggestionColumn: View {
    var items: [String]
    var onTap: (String) -> Void

    var body: some View {
        VStack(spacing: 8) {
            ForEach(items, id: \.self) { item in
                Button {
                    onTap(item)
                } label: {
                    HStack(alignment: .top, spacing: 8) {
                        Image(systemName: "quote.opening")
                            .font(.caption.weight(.bold))
                            .foregroundStyle(DesignTokens.sage)
                        Text(item)
                            .font(.caption)
                            .foregroundStyle(DesignTokens.secondaryInk)
                            .lineLimit(2)
                        Spacer()
                    }
                    .padding(10)
                    .background(DesignTokens.surface.opacity(0.68))
                    .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
                }
                .buttonStyle(.plain)
            }
        }
    }
}

private struct CommunicationCardPreview: View {
    @ObservedObject var viewModel: OnboardingViewModel

    var body: some View {
        SoftCard(padding: 16) {
            HStack(alignment: .center, spacing: 12) {
                Image(systemName: "rectangle.connected.to.line.below")
                    .font(.title3.weight(.semibold))
                    .foregroundStyle(DesignTokens.sage)
                    .frame(width: 40, height: 40)
                    .background(DesignTokens.mist)
                    .clipShape(Circle())

                VStack(alignment: .leading, spacing: 5) {
                    Text(viewModel.name.isEmpty ? "通讯卡预览" : "\(viewModel.name) 的通讯卡")
                        .font(.headline)
                        .foregroundStyle(DesignTokens.ink)
                    Text(viewModel.ownerTitle.isEmpty ? "称呼和记忆会在这里变成 TA 的旅程 DNA。" : "\(viewModel.ownerTitle) · \(viewModel.petType.displayName)")
                        .font(.footnote)
                        .foregroundStyle(DesignTokens.secondaryInk)
                        .lineLimit(2)
                }
            }
        }
    }
}

private extension View {
    func softInputBackground() -> some View {
        self
            .padding(.vertical, 12)
            .padding(.horizontal, 14)
            .background(DesignTokens.mist)
            .clipShape(RoundedRectangle(cornerRadius: DesignTokens.controlRadius, style: .continuous))
    }
}
