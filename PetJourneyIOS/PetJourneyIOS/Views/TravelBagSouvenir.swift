import SwiftUI
import UIKit

struct TravelBagCard: View {
    var bag: TravelBag?
    @Binding var message: String
    var isPacking: Bool
    var onPackPreset: (TravelBagItemInput) -> Void

    var body: some View {
        SoftCard {
            PetSoulAssetLabel(
                title: "小包里现在有",
                asset: .travelBag,
                fallbackSystemImage: "bag.fill",
                tint: DesignTokens.clay,
                iconSize: 22
            )
                .font(.caption.weight(.bold))
                .foregroundStyle(DesignTokens.clay)

            Text(bag?.petVisibleNote ?? "这只小包还空着。出发前可以放一点小零食、护身符，或一句想让 TA 带着走的话。")
                .font(.subheadline)
                .foregroundStyle(DesignTokens.secondaryInk)
                .lineSpacing(3)

            if let bag, !bag.items.isEmpty {
                LazyVGrid(columns: [GridItem(.adaptive(minimum: 138), spacing: 8)], spacing: 8) {
                    ForEach(bag.items.suffix(8)) { item in
                        TravelBagItemChip(item: item)
                    }
                }
            }

            TextField("留一句装进小包的话", text: $message)
                .font(.subheadline)
                .textFieldStyle(.plain)
                .padding(12)
                .background(DesignTokens.surface.opacity(0.72))
                .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))

            LazyVGrid(columns: [GridItem(.adaptive(minimum: 142), spacing: 8)], spacing: 8) {
                ForEach(TravelBagPreset.allCases) { preset in
                    Button {
                        onPackPreset(preset.itemInput)
                    } label: {
                        PetSoulAssetLabel(
                            title: preset.title,
                            asset: preset.asset,
                            fallbackSystemImage: preset.systemImage,
                            tint: DesignTokens.sage,
                            iconSize: 22
                        )
                            .font(.caption.weight(.semibold))
                            .frame(maxWidth: .infinity, minHeight: 34)
                    }
                    .quietActionStyle()
                    .disabled(isPacking)
                }
            }
        }
    }
}

struct TravelBagItemChip: View {
    var item: TravelBagItem

    var body: some View {
        HStack(spacing: 7) {
            PetSoulAssetIcon(
                asset: item.itemType.petSoulAsset,
                fallbackSystemImage: item.itemType.systemImage,
                fallbackTint: DesignTokens.sage,
                size: 22
            )
            VStack(alignment: .leading, spacing: 1) {
                Text(item.title)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(DesignTokens.ink)
                    .lineLimit(1)
                Text(item.itemType.displayName)
                    .font(.caption2)
                    .foregroundStyle(DesignTokens.secondaryInk)
            }
        }
        .padding(.vertical, 8)
        .padding(.horizontal, 9)
        .background(DesignTokens.surface.opacity(0.62))
        .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
    }
}

extension TravelBagItemType {
    var petSoulAsset: PetSoulAsset {
        switch self {
        case .snack:
            .travelPropPaperBag
        case .comfortItem:
            .travelPropBlanket
        case .guideHint:
            .travelPropFoldedMap
        case .luckyCharm:
            .travelPropBell
        case .musicHint:
            .musicNote
        case .toy:
            .travelPropPetScarf
        }
    }
}

enum TravelBagPreset: String, CaseIterable, Identifiable {
    case snack
    case charm
    case guide
    case music

    var id: String { rawValue }

    var title: String {
        switch self {
        case .snack: "放小零食"
        case .charm: "放护身符"
        case .guide: "放想看的地方"
        case .music: "放一首歌"
        }
    }

    var systemImage: String {
        switch self {
        case .snack: "takeoutbag.and.cup.and.straw.fill"
        case .charm: "sparkles"
        case .guide: "map.fill"
        case .music: "headphones"
        }
    }

    var asset: PetSoulAsset {
        switch self {
        case .snack: .travelPropPaperBag
        case .charm: .travelPropBell
        case .guide: .travelPropFoldedMap
        case .music: .musicNote
        }
    }

    var itemInput: TravelBagItemInput {
        switch self {
        case .snack:
            TravelBagItemInput(
                itemType: .snack,
                title: "路上小零食",
                note: "累的时候闻一闻就好",
                influenceTags: ["comfort", "slow_travel"]
            )
        case .charm:
            TravelBagItemInput(
                itemType: .luckyCharm,
                title: "小小护身符",
                note: "提醒 TA 不要赶路",
                influenceTags: ["return_home", "rare_photo"]
            )
        case .guide:
            TravelBagItemInput(
                itemType: .guideHint,
                title: "想看的街角",
                note: "如果路过就看一眼",
                influenceTags: ["local_life", "souvenir"]
            )
        case .music:
            TravelBagItemInput(
                itemType: .musicHint,
                title: "路上的歌",
                note: "让旅程安静一点",
                influenceTags: ["rest", "soft_mood"]
            )
        }
    }
}

extension SouvenirItemType {
    var petSoulAsset: PetSoulAsset {
        switch self {
        case .toy:
            .travelPropPetScarf
        case .culturalCreative:
            .travelPropStamp
        case .foundObject:
            .travelPropSeashell
        case .ticketStub:
            .travelPropPostcard
        case .charm:
            .travelPropPhotoCharm
        case .snackPack:
            .travelPropPaperBag
        case .photoPrint:
            .travelPropPostcard
        }
    }
}

struct SouvenirCard: View {
    var souvenir: SouvenirItem
    var allowsActions = false
    var isMutating = false
    var onSell: () -> Void = {}
    var onArchive: () -> Void = {}

    var body: some View {
        SoftCard {
            HStack(alignment: .top, spacing: 12) {
                PetSoulAssetIcon(
                    asset: souvenir.itemType.petSoulAsset,
                    fallbackSystemImage: souvenir.itemType.systemImage,
                    fallbackTint: tint,
                    size: 38
                )
                    .frame(width: 42, height: 42)
                    .background(tint.opacity(0.14))
                    .clipShape(Circle())

                VStack(alignment: .leading, spacing: 5) {
                    Text(souvenir.itemType.displayName)
                        .font(.caption.weight(.bold))
                        .foregroundStyle(DesignTokens.secondaryInk)
                    Text(souvenir.title)
                        .font(.headline.weight(.semibold))
                        .foregroundStyle(DesignTokens.ink)
                    Text("\(souvenir.city) · \(souvenir.placeName)")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(DesignTokens.sage)
                }
                Spacer(minLength: 0)
                Text(statusBadge)
                    .font(.caption2.weight(.bold))
                    .foregroundStyle(tint)
                    .padding(.vertical, 5)
                    .padding(.horizontal, 8)
                    .background(tint.opacity(0.12))
                    .clipShape(Capsule())
            }

            if let imageURL = souvenir.imageURL {
                PostcardImageView(url: imageURL, height: 172)
            }

            Text(souvenir.subtitle)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(DesignTokens.ink)

            Text(souvenir.story.petSoulPetVoiceText)
                .font(.footnote)
                .foregroundStyle(DesignTokens.secondaryInk)
                .lineSpacing(3)

            Text("“\(souvenir.petVoice.petSoulPetVoiceText)”")
                .font(.subheadline)
                .foregroundStyle(DesignTokens.ink)
                .lineSpacing(3)
                .padding(12)
                .background(DesignTokens.mist.opacity(0.62))
                .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))

            HStack(spacing: 8) {
                SouvenirValuePill(title: "可出售", value: "\(souvenir.resaleValue) 旅贝", tint: DesignTokens.amber)
                SouvenirValuePill(title: "收藏", value: "\(souvenir.displayEmotionalValue)", tint: DesignTokens.clay)
                if souvenir.displayHonorValue > 0 {
                    SouvenirValuePill(title: "荣誉", value: "\(souvenir.displayHonorValue)", tint: DesignTokens.dusk)
                }
            }

            Text(originLine)
                .font(.caption)
                .foregroundStyle(DesignTokens.secondaryInk)
                .lineLimit(2)

            if allowsActions && souvenir.effectiveStatus == .owned {
                HStack(spacing: 10) {
                    Button(action: onArchive) {
                        Label("珍藏", systemImage: "archivebox.fill")
                            .frame(maxWidth: .infinity)
                    }
                    .quietActionStyle()
                    .disabled(isMutating)

                    Button(action: onSell) {
                        if isMutating {
                            ProgressView()
                                .tint(DesignTokens.amber)
                                .frame(maxWidth: .infinity)
                        } else {
                            Label("出售", systemImage: "shell.fill")
                                .frame(maxWidth: .infinity)
                        }
                    }
                    .quietActionStyle()
                    .disabled(!souvenir.isSellable || isMutating)
                }
            }
        }
    }

    var statusBadge: String {
        switch souvenir.effectiveStatus {
        case .sold:
            "已出售"
        case .archived:
            "珍藏"
        default:
            souvenir.rarity == "rare" ? "少见" : "小物"
        }
    }

    var originLine: String {
        let city = souvenir.originCity ?? souvenir.city
        let place = souvenir.originPOIName ?? souvenir.placeName
        if let weather = souvenir.originWeather, !weather.isEmpty {
            return "\(city) · \(place) · \(weather)"
        }
        return "\(city) · \(place)"
    }

    var tint: Color {
        switch souvenir.itemType {
        case .ticketStub:
            DesignTokens.clay
        case .photoPrint:
            DesignTokens.dusk
        case .culturalCreative, .charm:
            DesignTokens.sage
        case .snackPack:
            DesignTokens.amber
        case .toy:
            DesignTokens.pollen
        case .foundObject:
            DesignTokens.secondaryInk
        }
    }
}

struct SouvenirValuePill: View {
    var title: String
    var value: String
    var tint: Color

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(value)
                .font(.caption.weight(.bold))
                .foregroundStyle(DesignTokens.ink)
                .lineLimit(1)
                .minimumScaleFactor(0.75)
            Text(title)
                .font(.caption2.weight(.semibold))
                .foregroundStyle(DesignTokens.secondaryInk)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.vertical, 7)
        .padding(.horizontal, 9)
        .background(tint.opacity(0.12))
        .clipShape(RoundedRectangle(cornerRadius: 13, style: .continuous))
    }
}
