import SwiftUI
import UIKit

struct PostcardsView: View {
    var postcards: [Postcard]

    var visiblePostcards: [Postcard] {
        var seenKeys = Set<String>()
        return postcards
            .sorted(by: { $0.timestamp > $1.timestamp })
            .filter { postcard in
                let normalizedText = postcard.text
                    .replacingOccurrences(of: #"\s+"#, with: " ", options: .regularExpression)
                    .trimmingCharacters(in: .whitespacesAndNewlines)
                let key = [
                    postcard.location,
                    normalizedText,
                    postcard.imageURL?.absoluteString ?? ""
                ].joined(separator: "|")
                return seenKeys.insert(key).inserted
            }
    }

    var body: some View {
        ZStack {
            AppBackground()

            if visiblePostcards.isEmpty {
                EmptyStateView(
                    title: "还没有明信片",
                    detail: "TA 可能正在路上。第一张明信片通常会在一段安静的停留后抵达。",
                    systemImage: "mail"
                )
            } else {
                ScrollView {
                    VStack(alignment: .leading, spacing: 16) {
                        VStack(alignment: .leading, spacing: 6) {
                            Text("明信片")
                                .font(.title2.weight(.semibold))
                                .foregroundStyle(DesignTokens.ink)
                            Text("TA 从另一端世界寄来的片段。")
                                .font(.subheadline)
                                .foregroundStyle(DesignTokens.secondaryInk)
                        }

                        ForEach(Array(visiblePostcards.enumerated()), id: \.element.id) { index, postcard in
                            PostcardCard(postcard: postcard)
                                .rotationEffect(.degrees(index.isMultiple(of: 2) ? 0.5 : -0.5))
                                .scrollTransition(.animated(.spring(response: 0.5, dampingFraction: 0.85))) { content, phase in
                                    content
                                        .opacity(phase.isIdentity ? 1 : 0.55)
                                        .scaleEffect(phase.isIdentity ? 1 : 0.965)
                                        .offset(y: phase == .bottomTrailing ? 14 : 0)
                                }
                        }
                    }
                    .padding(DesignTokens.pagePadding)
                }
            }
        }
        .navigationTitle("明信片")
        .navigationBarTitleDisplayMode(.inline)
    }
}

struct TravelKitSheetView: View {
    var petName: String
    var travelQuests: [TravelQuest]
    var travelBag: TravelBag?
    var souvenirs: [SouvenirItem]
    var economy: EconomyResponse?
    var isCreatingQuest: Bool
    var isPackingBag: Bool
    var isCollectingSouvenir: Bool
    var mutatingInventoryItemIDs: Set<String>
    @Binding var questMessage: String
    @Binding var bagMessage: String
    var onCreateQuest: () -> Void
    var onPackPreset: (TravelBagItemInput) -> Void
    var onPrepareDeparture: () -> Void
    var onCollectSouvenir: () -> Void
    var onShowSouvenirs: () -> Void
    var onSellSouvenir: (SouvenirItem) -> Void
    var onArchiveSouvenir: (SouvenirItem) -> Void

    var activeQuest: TravelQuest? {
        travelQuests.first
    }

    var body: some View {
        ZStack {
            AppBackground()

            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    VStack(alignment: .leading, spacing: 6) {
                        Text("旅行小包")
                            .font(.title2.weight(.semibold))
                            .foregroundStyle(DesignTokens.ink)
                        Text("你可以轻轻准备，TA 会自己决定怎么走。")
                            .font(.subheadline)
                            .foregroundStyle(DesignTokens.secondaryInk)
                    }

                    TravelWishComposer(
                        text: $questMessage,
                        isLoading: isCreatingQuest,
                        onSubmit: onCreateQuest
                    )

                    if let activeQuest {
                        TravelQuestCard(
                            petName: petName,
                            quest: activeQuest,
                            isPreparing: isCreatingQuest,
                            isCollecting: isCollectingSouvenir,
                            onPrepareDeparture: onPrepareDeparture,
                            onCollectSouvenir: onCollectSouvenir
                        )
                    } else {
                        EmptyStateView(
                            title: "还没有支线旅行",
                            detail: "可以先告诉 TA 想去哪。TA 会先做攻略，不会立刻被推着出发。",
                            systemImage: "map"
                        )
                    }

                    TravelBagCard(
                        bag: travelBag,
                        message: $bagMessage,
                        isPacking: isPackingBag,
                        onPackPreset: onPackPreset
                    )

                    EconomySummaryCard(economy: economy)

                    Button(action: onShowSouvenirs) {
                        HStack(spacing: 10) {
                            Image(systemName: "gift.fill")
                                .font(.headline.weight(.semibold))
                            VStack(alignment: .leading, spacing: 2) {
                                Text("带回的小东西")
                                    .font(.subheadline.weight(.semibold))
                                Text(souvenirs.isEmpty ? "还没有收藏，等 TA 走完一段路。" : "\(souvenirs.count) 件小收藏已经放好")
                                    .font(.caption)
                            }
                            Spacer()
                            Image(systemName: "chevron.right")
                                .font(.caption.weight(.bold))
                        }
                        .foregroundStyle(DesignTokens.ink)
                    }
                    .buttonStyle(.plain)
                    .padding(14)
                    .background(DesignTokens.surface.opacity(0.78))
                    .clipShape(RoundedRectangle(cornerRadius: DesignTokens.cardRadius, style: .continuous))
                    .overlay {
                        RoundedRectangle(cornerRadius: DesignTokens.cardRadius, style: .continuous)
                            .stroke(DesignTokens.softLine, lineWidth: 1)
                    }
                }
                .padding(DesignTokens.pagePadding)
            }
        }
        .navigationTitle("旅行小包")
        .navigationBarTitleDisplayMode(.inline)
    }
}

struct SouvenirsView: View {
    var souvenirs: [SouvenirItem]
    var economy: EconomyResponse? = nil
    var allowsActions = false
    var mutatingItemIDs: Set<String> = []
    var onSell: (SouvenirItem) -> Void = { _ in }
    var onArchive: (SouvenirItem) -> Void = { _ in }

    var body: some View {
        ZStack {
            AppBackground()

            if souvenirs.isEmpty {
                EmptyStateView(
                    title: "还没有带回物",
                    detail: "等 TA 完成一小段旅行，会带回玩具、票根、文创或一张小照片。",
                    systemImage: "gift"
                )
            } else {
                ScrollView {
                    VStack(alignment: .leading, spacing: 16) {
                        VStack(alignment: .leading, spacing: 6) {
                            Text("带回的小东西")
                                .font(.title2.weight(.semibold))
                                .foregroundStyle(DesignTokens.ink)
                            Text("不是商品，是 TA 从另一端世界带回来的记忆。")
                                .font(.subheadline)
                                .foregroundStyle(DesignTokens.secondaryInk)
                        }

                        EconomySummaryCard(economy: economy)

                        ForEach(souvenirs) { souvenir in
                            SouvenirCard(
                                souvenir: souvenir,
                                allowsActions: allowsActions,
                                isMutating: mutatingItemIDs.contains(souvenir.id),
                                onSell: { onSell(souvenir) },
                                onArchive: { onArchive(souvenir) }
                            )
                        }
                    }
                    .padding(DesignTokens.pagePadding)
                }
            }
        }
        .navigationTitle("小收藏")
        .navigationBarTitleDisplayMode(.inline)
    }
}

struct EconomySummaryCard: View {
    var economy: EconomyResponse?

    var body: some View {
        SoftCard {
            HStack(alignment: .top, spacing: 12) {
                PetSoulAssetIcon(
                    asset: .memoryTray,
                    fallbackSystemImage: "bag.fill",
                    fallbackTint: DesignTokens.sage,
                    size: 34
                )
                VStack(alignment: .leading, spacing: 4) {
                    Text("小背包")
                        .font(.headline.weight(.semibold))
                        .foregroundStyle(DesignTokens.ink)
                    Text(walletLine)
                        .font(.caption)
                        .foregroundStyle(DesignTokens.secondaryInk)
                }
                Spacer(minLength: 0)
            }

            LazyVGrid(columns: [GridItem(.adaptive(minimum: 108), spacing: 8)], spacing: 8) {
                EconomyMetricTile(title: "背包价值", value: valueText(economy?.snapshot.totalDisplayValue), tint: DesignTokens.sage)
                EconomyMetricTile(title: "可出售", value: valueText(economy?.snapshot.sellableValue), tint: DesignTokens.amber)
                EconomyMetricTile(title: "收藏", value: valueText(economy?.snapshot.collectionValue), tint: DesignTokens.clay)
                EconomyMetricTile(title: "荣誉", value: valueText(economy?.snapshot.honorValue), tint: DesignTokens.dusk)
            }

            if let latest = economy?.recentTransactions.first {
                Label(latest.reason, systemImage: "clock.fill")
                    .font(.caption)
                    .foregroundStyle(DesignTokens.secondaryInk)
                    .lineLimit(2)
            }
        }
    }

    var walletLine: String {
        guard let wallet = economy?.wallet else {
            return "旅贝 0 · 星尘 0 · 功勋 0"
        }
        return "旅贝 \(wallet.travelCoin) · 星尘 \(wallet.starDust) · 功勋 \(wallet.merit)"
    }

    func valueText(_ value: Int?) -> String {
        "\(value ?? 0)"
    }
}

struct EconomyMetricTile: View {
    var title: String
    var value: String
    var tint: Color

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(value)
                .font(.subheadline.weight(.bold))
                .foregroundStyle(DesignTokens.ink)
                .lineLimit(1)
                .minimumScaleFactor(0.75)
            Text(title)
                .font(.caption2.weight(.semibold))
                .foregroundStyle(DesignTokens.secondaryInk)
                .lineLimit(1)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.vertical, 9)
        .padding(.horizontal, 10)
        .background(tint.opacity(0.12))
        .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
    }
}

struct TravelWishComposer: View {
    @Binding var text: String
    var isLoading: Bool
    var onSubmit: () -> Void

    var body: some View {
        SoftCard {
            Label("告诉 TA 一个想去的地方", systemImage: "paperplane.fill")
                .font(.caption.weight(.bold))
                .foregroundStyle(DesignTokens.sage)

            TextField("比如：明天去世界杯看德国队比赛，先做攻略", text: $text, axis: .vertical)
                .lineLimit(2...4)
                .font(.body)
                .textFieldStyle(.plain)
                .padding(12)
                .background(DesignTokens.surface.opacity(0.76))
                .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))

            Button(action: onSubmit) {
                HStack {
                    if isLoading {
                        ProgressView()
                            .tint(.white)
                    }
                    Label("让 TA 先做攻略", systemImage: "sparkles")
                        .frame(maxWidth: .infinity)
                }
            }
            .buttonStyle(.borderedProminent)
            .tint(DesignTokens.sage)
            .disabled(text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || isLoading)
        }
    }
}

struct TravelQuestCard: View {
    var petName: String
    var quest: TravelQuest
    var isPreparing: Bool
    var isCollecting: Bool
    var onPrepareDeparture: () -> Void
    var onCollectSouvenir: () -> Void
    @State var isGuideExpanded = true

    var body: some View {
        SoftCard {
            HStack(alignment: .top, spacing: 10) {
                Image(systemName: quest.worldcupEvent ? "sportscourt.fill" : "map.fill")
                    .font(.headline.weight(.bold))
                    .foregroundStyle(quest.worldcupEvent ? DesignTokens.clay : DesignTokens.sage)
                    .frame(width: 38, height: 38)
                    .background((quest.worldcupEvent ? DesignTokens.clay : DesignTokens.sage).opacity(0.13))
                    .clipShape(Circle())

                VStack(alignment: .leading, spacing: 4) {
                    Text(quest.questType.displayName)
                        .font(.caption.weight(.bold))
                        .foregroundStyle(DesignTokens.secondaryInk)
                    Text(quest.guide?.title ?? "\(petName) 的旅行愿望")
                        .font(.headline.weight(.semibold))
                        .foregroundStyle(DesignTokens.ink)
                        .fixedSize(horizontal: false, vertical: true)
                    Text(quest.status.displayName)
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(DesignTokens.sage)
                }
                Spacer(minLength: 0)
            }

            Text((quest.guide?.petVoice ?? quest.currentPhaseMessage).petSoulPetVoiceText)
                .font(.subheadline)
                .foregroundStyle(DesignTokens.secondaryInk)
                .lineSpacing(3)

            if let guide = quest.guide {
                TravelQuestGuideSnapshot(guide: guide)

                DisclosureGroup(isExpanded: $isGuideExpanded) {
                    VStack(alignment: .leading, spacing: 9) {
                        Text(guide.summary.petSoulPetVoiceText)
                            .font(.footnote)
                            .foregroundStyle(DesignTokens.secondaryInk)
                            .lineSpacing(3)
                        ForEach(guide.stops.prefix(4)) { stop in
                            TravelQuestStopRow(stop: stop)
                        }
                    }
                    .padding(.top, 8)
                } label: {
                    Label("TA 整理的路线", systemImage: "list.bullet.rectangle")
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(DesignTokens.ink)
                }
            }

            HStack(spacing: 10) {
                Button(action: onPrepareDeparture) {
                    if isPreparing {
                        ProgressView()
                            .tint(DesignTokens.sage)
                            .frame(maxWidth: .infinity)
                    } else {
                        Label("准备出发", systemImage: "figure.walk")
                            .frame(maxWidth: .infinity)
                    }
                }
                .quietActionStyle()
                .disabled(isPreparing)

                Button(action: onCollectSouvenir) {
                    if isCollecting {
                        ProgressView()
                            .tint(DesignTokens.clay)
                            .frame(maxWidth: .infinity)
                    } else {
                        Label("看看带回物", systemImage: "gift.fill")
                            .frame(maxWidth: .infinity)
                    }
                }
                .quietActionStyle()
                .disabled(isCollecting)
            }
        }
    }
}

struct TravelQuestGuideSnapshot: View {
    var guide: TravelQuestGuide

    var body: some View {
        VStack(alignment: .leading, spacing: 11) {
            HStack(alignment: .top, spacing: 10) {
                Image(systemName: "map.circle.fill")
                    .font(.title3.weight(.semibold))
                    .foregroundStyle(DesignTokens.sage)
                VStack(alignment: .leading, spacing: 4) {
                    Text("TA 先替你查了一遍")
                        .font(.caption.weight(.bold))
                        .foregroundStyle(DesignTokens.secondaryInk)
                    Text(guide.routeTheme.petSoulUserFacingText)
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(DesignTokens.ink)
                        .fixedSize(horizontal: false, vertical: true)
                }
                Spacer(minLength: 0)
            }

            HStack(spacing: 8) {
                TravelQuestGuidePill(title: "\(guide.cities.joined(separator: " → "))", systemImage: "mappin.and.ellipse")
                TravelQuestGuidePill(title: "\(guide.stops.count) 站", systemImage: "list.number")
            }

            if !guide.transportOutline.isEmpty {
                VStack(alignment: .leading, spacing: 7) {
                    Text("怎么过去")
                        .font(.caption.weight(.bold))
                        .foregroundStyle(DesignTokens.secondaryInk)
                    ForEach(guide.transportOutline.prefix(3)) { leg in
                        HStack(alignment: .top, spacing: 8) {
                            Image(systemName: leg.mode.systemImage)
                                .font(.caption.weight(.bold))
                                .foregroundStyle(transportTint(leg.mode))
                                .frame(width: 24, height: 24)
                                .background(transportTint(leg.mode).opacity(0.12))
                                .clipShape(Circle())
                            VStack(alignment: .leading, spacing: 2) {
                                Text("\(leg.fromPlace) → \(leg.toPlace)")
                                    .font(.caption.weight(.semibold))
                                    .foregroundStyle(DesignTokens.ink)
                                    .lineLimit(2)
                                Text("\(leg.mode.displayName) · \(leg.estimatedDuration) · \(leg.note.petSoulUserFacingText)")
                                    .font(.caption2)
                                    .foregroundStyle(DesignTokens.secondaryInk)
                                    .lineLimit(3)
                                    .fixedSize(horizontal: false, vertical: true)
                            }
                        }
                    }
                }
            }

            if let research = guide.research, hasResearchFindings(research) {
                VStack(alignment: .leading, spacing: 7) {
                    Text("攻略线索")
                        .font(.caption.weight(.bold))
                        .foregroundStyle(DesignTokens.secondaryInk)
                    if let socialFindings = research.socialFindings, !socialFindings.isEmpty {
                        ForEach(Array(socialFindings.prefix(3).enumerated()), id: \.offset) { _, finding in
                            VStack(alignment: .leading, spacing: 3) {
                                Label(finding.claim.petSoulUserFacingText, systemImage: socialFindingIcon(finding.evidenceType))
                                    .font(.caption)
                                    .foregroundStyle(DesignTokens.secondaryInk)
                                    .lineLimit(2)
                                if let risk = finding.risk?.petSoulUserFacingText, !risk.isEmpty {
                                    Text(risk)
                                        .font(.caption2)
                                        .foregroundStyle(DesignTokens.secondaryInk.opacity(0.78))
                                        .lineLimit(1)
                                }
                            }
                        }
                    } else {
                        ForEach(Array(research.findings.prefix(3).enumerated()), id: \.offset) { _, finding in
                            Label(finding.petSoulUserFacingText, systemImage: "magnifyingglass")
                                .font(.caption)
                                .foregroundStyle(DesignTokens.secondaryInk)
                                .lineLimit(2)
                        }
                    }
                }
            }

            if !guide.preparationNotes.isEmpty {
                VStack(alignment: .leading, spacing: 7) {
                    Text("出发前先确认")
                        .font(.caption.weight(.bold))
                        .foregroundStyle(DesignTokens.secondaryInk)
                    ForEach(Array(guide.preparationNotes.prefix(3).enumerated()), id: \.offset) { _, note in
                        Label(note.petSoulUserFacingText, systemImage: "checkmark.circle.fill")
                            .font(.caption)
                            .foregroundStyle(DesignTokens.secondaryInk)
                            .lineLimit(2)
                    }
                }
            }
        }
        .padding(12)
        .background(DesignTokens.mist.opacity(0.54))
        .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
    }

    func transportTint(_ mode: TravelMode) -> Color {
        switch mode {
        case .flight, .train, .transit:
            DesignTokens.dusk
        case .drive, .ferry:
            DesignTokens.amber
        case .walk:
            DesignTokens.sage
        case .stay, .checkIn:
            DesignTokens.clay
        }
    }

    func hasResearchFindings(_ research: TravelGuideResearch) -> Bool {
        !(research.socialFindings?.isEmpty ?? true) || !research.findings.isEmpty
    }

    func socialFindingIcon(_ type: String?) -> String {
        switch type {
        case "photo_anchor":
            "camera.viewfinder"
        case "local_food":
            "fork.knife"
        case "avoid_note":
            "exclamationmark.triangle"
        case "time_window":
            "clock"
        default:
            "magnifyingglass"
        }
    }
}

struct TravelQuestGuidePill: View {
    var title: String
    var systemImage: String

    var body: some View {
        Label(title, systemImage: systemImage)
            .font(.caption.weight(.semibold))
            .foregroundStyle(DesignTokens.ink)
            .lineLimit(1)
            .minimumScaleFactor(0.72)
            .frame(maxWidth: .infinity)
            .padding(.vertical, 8)
            .padding(.horizontal, 9)
            .background(DesignTokens.surface.opacity(0.58))
            .clipShape(RoundedRectangle(cornerRadius: 13, style: .continuous))
    }
}

struct TravelQuestStopRow: View {
    var stop: TravelQuestStop

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Text(stop.plannedTime ?? "途中")
                .font(.caption.weight(.bold))
                .foregroundStyle(DesignTokens.dusk)
                .frame(width: 58, alignment: .leading)

            VStack(alignment: .leading, spacing: 4) {
                Text(stop.name)
                    .font(.footnote.weight(.semibold))
                    .foregroundStyle(DesignTokens.ink)
                Text(stop.petVoice.petSoulPetVoiceText)
                    .font(.caption)
                    .foregroundStyle(DesignTokens.secondaryInk)
                    .lineLimit(3)
            }
        }
        .padding(.vertical, 8)
        .padding(.horizontal, 10)
        .background(DesignTokens.surface.opacity(0.56))
        .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
    }
}
