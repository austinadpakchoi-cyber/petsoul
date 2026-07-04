import SwiftUI

/// 证件卡包：TA 在 PetSoul 世界的身份物件。证件是"实物"，用固定纸质配色，夜里也不变。
struct CredentialPromptsView: View {
    let petID: String
    let service: any PetJourneyService

    @State private var prompts: [PetCredentialPrompt] = []
    @State private var isLoading = true
    @State private var errorMessage: String?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                if isLoading {
                    HStack(spacing: 10) {
                        ProgressView()
                        Text("正在打开 TA 的卡包…")
                            .font(.subheadline)
                            .foregroundStyle(DesignTokens.secondaryInk)
                    }
                    .frame(maxWidth: .infinity, alignment: .center)
                    .padding(.top, 32)
                } else if let errorMessage {
                    Text(errorMessage)
                        .font(.subheadline)
                        .foregroundStyle(DesignTokens.secondaryInk)
                        .frame(maxWidth: .infinity, alignment: .center)
                        .padding(.top, 32)
                } else {
                    ForEach(prompts) { prompt in
                        CredentialCard(prompt: prompt)
                    }
                }
            }
            .padding(DesignTokens.pagePadding)
        }
        .background(DesignTokens.porcelain)
        .navigationTitle("证件卡包")
        .navigationBarTitleDisplayMode(.inline)
        .task { await load() }
    }

    private func load() async {
        defer { isLoading = false }
        do {
            prompts = try await service.fetchCredentialPrompts(petID: petID)
        } catch {
            errorMessage = "卡包信号还没接通，稍后再看看。"
        }
    }
}

private struct CredentialCard: View {
    let prompt: PetCredentialPrompt

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .firstTextBaseline) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(prompt.title)
                        .font(.headline)
                        .foregroundStyle(DesignTokens.paperInk)
                    Text(prompt.subtitle)
                        .font(.caption)
                        .foregroundStyle(DesignTokens.paperSecondaryInk)
                }
                Spacer()
                Image(systemName: iconName)
                    .font(.title3)
                    .foregroundStyle(DesignTokens.paperAccent)
                    .accessibilityHidden(true)
            }

            if !prompt.fields.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    ForEach(prompt.fields.sorted(by: { $0.key < $1.key }), id: \.key) { field in
                        HStack(alignment: .firstTextBaseline, spacing: 8) {
                            Text(field.key)
                                .font(.caption)
                                .foregroundStyle(DesignTokens.paperSecondaryInk)
                            Text(field.value)
                                .font(.caption.weight(.medium))
                                .foregroundStyle(DesignTokens.paperInk)
                        }
                    }
                }
            }

            Text(prompt.serial)
                .font(.caption2.monospaced())
                .foregroundStyle(DesignTokens.paperSecondaryInk)
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(DesignTokens.paper)
        .clipShape(RoundedRectangle(cornerRadius: DesignTokens.cardRadius, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: DesignTokens.cardRadius, style: .continuous)
                .stroke(DesignTokens.paperShade, lineWidth: 1)
        }
        .shadow(color: DesignTokens.deepInk.opacity(0.1), radius: 12, x: 0, y: 6)
        .accessibilityElement(children: .combine)
    }

    private var iconName: String {
        switch prompt.kind {
        case .identity: "person.text.rectangle"
        case .passport: "airplane"
        case .healthRecord: "heart.text.square"
        case .driverLicense: "car"
        case .boardingPass: "ticket"
        case .hotelKey: "key"
        }
    }
}
