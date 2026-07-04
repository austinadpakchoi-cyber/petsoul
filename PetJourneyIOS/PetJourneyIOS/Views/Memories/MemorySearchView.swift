import SwiftUI

/// 记忆语义搜索：让主人用一句话在 TA 的生活痕迹里找回某个瞬间。
struct MemorySearchView: View {
    let petID: String
    let service: any PetJourneyService

    @State private var query = ""
    @State private var results: [MemoryRecord] = []
    @State private var isSearching = false
    @State private var hasSearched = false
    @State private var errorMessage: String?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                searchField

                if isSearching {
                    HStack(spacing: 10) {
                        ProgressView()
                        Text("正在轻轻翻 TA 的记忆…")
                            .font(.subheadline)
                            .foregroundStyle(DesignTokens.secondaryInk)
                    }
                    .frame(maxWidth: .infinity, alignment: .center)
                    .padding(.top, 24)
                } else if let errorMessage {
                    Text(errorMessage)
                        .font(.subheadline)
                        .foregroundStyle(DesignTokens.secondaryInk)
                        .frame(maxWidth: .infinity, alignment: .center)
                        .padding(.top, 24)
                } else if hasSearched && results.isEmpty {
                    Text("这句话还没有对上 TA 的记忆，换个说法试试。")
                        .font(.subheadline)
                        .foregroundStyle(DesignTokens.secondaryInk)
                        .frame(maxWidth: .infinity, alignment: .center)
                        .padding(.top, 24)
                } else {
                    ForEach(results) { memory in
                        MemorySearchResultCard(memory: memory)
                    }
                }
            }
            .padding(DesignTokens.pagePadding)
        }
        .background(DesignTokens.porcelain)
        .navigationTitle("找一段记忆")
        .navigationBarTitleDisplayMode(.inline)
    }

    private var searchField: some View {
        HStack(spacing: 10) {
            Image(systemName: "sparkle.magnifyingglass")
                .foregroundStyle(DesignTokens.sage)
            TextField("比如：那家有屏幕光的小店", text: $query)
                .submitLabel(.search)
                .onSubmit { Task { await search() } }
            if !query.isEmpty {
                Button {
                    query = ""
                } label: {
                    Image(systemName: "xmark.circle.fill")
                        .foregroundStyle(DesignTokens.secondaryInk)
                }
                .accessibilityLabel("清空搜索")
            }
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 12)
        .background(DesignTokens.surface.opacity(0.86))
        .clipShape(RoundedRectangle(cornerRadius: DesignTokens.controlRadius, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: DesignTokens.controlRadius, style: .continuous)
                .stroke(DesignTokens.surfaceStroke.opacity(0.8), lineWidth: 1)
        }
    }

    private func search() async {
        let clean = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !clean.isEmpty, !isSearching else { return }
        isSearching = true
        errorMessage = nil
        defer {
            isSearching = false
            hasSearched = true
        }
        do {
            let response = try await service.searchMemories(
                petID: petID,
                request: MemorySearchRequest(query: clean, limit: 12)
            )
            results = response.items
        } catch {
            results = []
            errorMessage = "信号有点弱，这次没有翻到，稍后再试。"
        }
    }
}

private struct MemorySearchResultCard: View {
    let memory: MemoryRecord

    var body: some View {
        SoftCard {
            VStack(alignment: .leading, spacing: 6) {
                Text(memory.title)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(DesignTokens.ink)
                Text(memory.content)
                    .font(.footnote)
                    .foregroundStyle(DesignTokens.secondaryInk)
                    .lineLimit(4)
                Text(memory.createdAt.formatted(date: .abbreviated, time: .shortened))
                    .font(.caption2)
                    .foregroundStyle(DesignTokens.secondaryInk.opacity(0.8))
            }
        }
    }
}
