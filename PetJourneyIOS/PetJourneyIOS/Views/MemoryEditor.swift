import PhotosUI
import SwiftUI
import UIKit

struct EditableMemoryArchiveView: View {
    @ObservedObject var viewModel: MemoryHubViewModel
    @State var searchText = ""
    @State var selectedFilter: MemoryArchiveFilter = .all
    @State var editorDraft: MemoryEditorDraft?
    @State var memoryPendingDelete: MemoryRecord?

    var filteredMemories: [MemoryRecord] {
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

    var deleteDialogPresented: Binding<Bool> {
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

    var archiveContent: some View {
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
    var addButtonToolbar: some ToolbarContent {
        ToolbarItem(placement: .topBarTrailing) {
            Button {
                editorDraft = MemoryEditorDraft(memory: nil)
            } label: {
                Image(systemName: "plus")
            }
            .accessibilityLabel("新增记忆")
        }
    }

    var filterChips: some View {
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

    var searchField: some View {
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
    var memoryList: some View {
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

struct MemoryArchiveFilterChip: View {
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

struct MemoryArchiveEmptyState: View {
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

struct MemoryArchiveSummaryCard: View {
    var memories: [MemoryRecord]

    var relationshipCount: Int {
        memories.filter { ($0.memoryType ?? $0.kind).contains("relationship") || $0.kind.contains("identity") }.count
    }

    var highImportanceCount: Int {
        memories.filter { ($0.importance ?? $0.salience) >= 0.75 }.count
    }

    var positiveCount: Int {
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

struct EditableMemoryCard: View {
    var memory: MemoryRecord
    var onEdit: () -> Void
    var onDelete: () -> Void

    var tint: Color {
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
                    MemoryChip(text: friendlyKindLabel, tint: tint)
                }

                HStack(spacing: 8) {
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

    func normalizedValence(_ value: Double) -> Double {
        min(max((value + 1) / 2, 0), 1)
    }

    /// 数据层的 kind/memoryType 是内部字段，展示层统一翻成 TA 世界里的说法
    var friendlyKindLabel: String {
        let raw = "\(memory.kind) \(memory.memoryType ?? "")".lowercased()
        if raw.contains("postcard") { return "明信片" }
        if raw.contains("souvenir") { return "纪念品" }
        if raw.contains("message") || raw.contains("agent_turn") || raw.contains("thought") { return "来信" }
        if raw.contains("relationship") { return "你们的约定" }
        if raw.contains("preference") { return "TA 的喜好" }
        if raw.contains("place") { return "去过的地方" }
        if raw.contains("identity") { return "TA 是谁" }
        return "小片段"
    }
}

struct MemoryChip: View {
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

struct MemorySignalBar: View {
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

struct MemoryEditorSheet: View {
    @Environment(\.dismiss) var dismiss
    let memory: MemoryRecord?
    let onSave: (MemoryEditorValues) -> Void

    @State var kind: String
    @State var title: String
    @State var content: String
    @State var source: String
    @State var memoryType: String
    @State var salience: Double
    @State var importance: Double
    @State var emotionalValence: Double
    @State var confidence: Double
    @State var sourceEventID: String

    let memoryTypeOptions = ["episodic", "recent_episodic", "relationship", "preference", "place_affect", "photo", "souvenir"]
    let kindOptions = ["owner_note", "identity", "owner_preference", "feedback", "place_affect", "postcard", "souvenir", "manual"]

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

    var canSave: Bool {
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

struct SliderValueRow: View {
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

struct MemoryOverviewCard: View {
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
                        Text(isLoading ? "正在同步通讯器里的收藏" : "最近停在 \(location)")
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
                    Text(isLoading ? "正在把通讯器、朋友圈和旅行包里的内容放到同一个回忆盒里。" : "等 TA 真正寄来或带回什么，这里才会慢慢变厚。")
                        .font(.subheadline)
                        .foregroundStyle(DesignTokens.secondaryInk)
                        .lineSpacing(3)
                }
            }
        }
    }
}

struct MemoryStatTile: View {
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

struct MemoryLatestRow: View {
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
