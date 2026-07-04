import SwiftUI

/// "这条街 TA 最想去哪"：把街区排行讲成 TA 的心愿清单，而不是排行榜。
struct StreetRankSheet: View {
    let petID: String
    let service: any PetJourneyService
    var theme: String = "street"

    @State private var response: StreetRankResponse?
    @State private var isLoading = true
    @State private var errorMessage: String?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                if isLoading {
                    HStack(spacing: 10) {
                        ProgressView()
                        Text("正在听 TA 数这条街的心愿…")
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
                } else if let response {
                    Text("\(response.city) · \(response.weather)")
                        .font(.caption)
                        .foregroundStyle(DesignTokens.secondaryInk)

                    ForEach(response.items) { item in
                        StreetWishCard(item: item)
                    }
                }
            }
            .padding(DesignTokens.pagePadding)
        }
        .background(DesignTokens.porcelain)
        .navigationTitle("这条街 TA 最想去哪")
        .navigationBarTitleDisplayMode(.inline)
        .task { await load() }
    }

    private func load() async {
        defer { isLoading = false }
        do {
            response = try await service.fetchStreetRank(petID: petID, theme: theme)
        } catch {
            errorMessage = "这条街的信号还没接通，稍后再来听。"
        }
    }
}

private struct StreetWishCard: View {
    let item: StreetRankItem

    var body: some View {
        SoftCard {
            VStack(alignment: .leading, spacing: 8) {
                HStack(alignment: .firstTextBaseline, spacing: 10) {
                    Text("\(item.rank)")
                        .font(.callout.weight(.bold).monospacedDigit())
                        .foregroundStyle(DesignTokens.sage)
                        .frame(width: 24, height: 24)
                        .background(DesignTokens.mist)
                        .clipShape(Circle())
                        .accessibilityLabel("第 \(item.rank) 个想去的地方")
                    Text(item.place.name)
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(DesignTokens.ink)
                }
                Text(item.reason)
                    .font(.footnote)
                    .foregroundStyle(DesignTokens.secondaryInk)
                Text(item.petAction)
                    .font(.footnote)
                    .foregroundStyle(DesignTokens.ink.opacity(0.9))
                Text(item.ownerTip)
                    .font(.caption)
                    .foregroundStyle(DesignTokens.dusk)
            }
        }
    }
}
