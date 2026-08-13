import AuthenticationServices
import MapKit
import SwiftUI
import UIKit

struct WorldCupInvitationTeaserCard: View {
    var petName: String
    var onOpen: () -> Void

    var body: some View {
        Button(action: onOpen) {
            HStack(spacing: 12) {
                ZStack {
                    SignalPulseRings(tint: DesignTokens.clay, size: 48, lineWidth: 1.2, ringCount: 2)
                        .opacity(0.68)
                    PetSoulAssetIcon(asset: .worldCupPawPass, fallbackTint: DesignTokens.clay, size: 32)
                        .frame(width: 38, height: 38)
                        .background(DesignTokens.surface.opacity(0.84))
                        .clipShape(Circle())
                }
                .frame(width: 50, height: 50)

                VStack(alignment: .leading, spacing: 4) {
                    Text("远方球场的灯亮了")
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(DesignTokens.ink)
                        .lineLimit(1)
                    Text("\(petName) 好像收到了一封很远的邀请。")
                        .font(.caption)
                        .foregroundStyle(DesignTokens.secondaryInk)
                        .lineLimit(2)
                }

                Spacer(minLength: 0)

                Image(systemName: "chevron.right")
                    .font(.caption.weight(.bold))
                    .foregroundStyle(DesignTokens.secondaryInk)
            }
            .padding(.vertical, 12)
            .padding(.horizontal, 13)
            .background(DesignTokens.surface.opacity(0.88))
            .clipShape(RoundedRectangle(cornerRadius: DesignTokens.cardRadius, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: DesignTokens.cardRadius, style: .continuous)
                    .stroke(DesignTokens.surfaceStroke.opacity(0.76), lineWidth: 1)
            }
            .shadow(color: DesignTokens.deepInk.opacity(0.11), radius: 18, x: 0, y: 9)
        }
        .buttonStyle(.plain)
        .accessibilityLabel("打开远方球场邀请")
    }
}

struct WorldCupMapStatusCard: View {
    var selectedHost: WorldCupHostCity?
    var activeQuest: TravelQuest?
    var onOpenInvitation: () -> Void
    var onFocusAll: () -> Void
    var onClose: () -> Void

    var title: String {
        selectedHost?.displayName ?? "北美球场已点亮"
    }

    var detail: String {
        if let activeQuest {
            return "\(activeQuest.destination) 已经放进旅行包，TA 会先走完当前这段路。"
        }
        if let selectedHost {
            return selectedHost.atmosphereHint
        }
        return "点一个亮起的球场，再决定要不要帮 TA 准备旅行包。"
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 11) {
            HStack(alignment: .top, spacing: 10) {
                PetSoulAssetIcon(asset: .worldCupStadiumLights, fallbackTint: DesignTokens.clay, size: 28)
                    .frame(width: 34, height: 34)
                    .background(DesignTokens.clay.opacity(0.12))
                    .clipShape(Circle())

                VStack(alignment: .leading, spacing: 3) {
                    Text(title)
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(DesignTokens.ink)
                        .lineLimit(2)
                    Text(detail)
                        .font(.caption)
                        .foregroundStyle(DesignTokens.secondaryInk)
                        .lineLimit(2)
                        .fixedSize(horizontal: false, vertical: true)
                }

                Spacer(minLength: 0)

                Button(action: onClose) {
                    Image(systemName: "xmark")
                        .font(.caption.weight(.bold))
                        .foregroundStyle(DesignTokens.secondaryInk)
                        .frame(width: 28, height: 28)
                        .background(DesignTokens.surface.opacity(0.68))
                        .clipShape(Circle())
                }
                .buttonStyle(.plain)
                .accessibilityLabel("关闭球场地图")
            }

            HStack(spacing: 9) {
                Button(action: onOpenInvitation) {
                    Label(activeQuest == nil ? "打开邀请" : "查看邀请", systemImage: "envelope.open.fill")
                        .frame(maxWidth: .infinity)
                }
                .quietActionStyle()

                Button(action: onFocusAll) {
                    Label("全部球场", systemImage: "map.fill")
                        .frame(maxWidth: .infinity)
                }
                .quietActionStyle()
            }
        }
        .padding(13)
        .background(DesignTokens.surface.opacity(0.9))
        .clipShape(RoundedRectangle(cornerRadius: DesignTokens.cardRadius, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: DesignTokens.cardRadius, style: .continuous)
                .stroke(DesignTokens.surfaceStroke.opacity(0.78), lineWidth: 1)
        }
        .shadow(color: DesignTokens.deepInk.opacity(0.12), radius: 20, x: 0, y: 10)
    }
}

struct WorldCupStadiumMarker: View {
    var host: WorldCupHostCity
    var isSelected: Bool

    var body: some View {
        VStack(spacing: 4) {
            ZStack {
                SignalPulseRings(
                    tint: isSelected ? DesignTokens.clay : DesignTokens.sea,
                    size: isSelected ? 54 : 42,
                    lineWidth: 1.1,
                    ringCount: isSelected ? 3 : 2
                )
                .opacity(isSelected ? 0.78 : 0.48)

                PetSoulAssetIcon(
                    asset: .worldCupFootball,
                    fallbackTint: isSelected ? DesignTokens.clay : DesignTokens.dusk,
                    size: isSelected ? 28 : 22
                )
                    .frame(width: isSelected ? 34 : 28, height: isSelected ? 34 : 28)
                    .background(DesignTokens.surface.opacity(0.9))
                    .clipShape(Circle())
                    .overlay {
                        Circle()
                            .stroke((isSelected ? DesignTokens.clay : DesignTokens.surfaceStroke).opacity(0.9), lineWidth: isSelected ? 2 : 1)
                    }
                    .shadow(color: DesignTokens.deepInk.opacity(0.15), radius: 9, x: 0, y: 4)
            }
            .frame(width: 56, height: 48)

            if isSelected {
                Text(host.city)
                    .font(.caption2.weight(.bold))
                    .foregroundStyle(DesignTokens.ink)
                    .lineLimit(1)
                    .padding(.vertical, 4)
                    .padding(.horizontal, 7)
                    .background(DesignTokens.surface.opacity(0.9))
                    .clipShape(Capsule())
            }
        }
        .animation(.spring(response: 0.28, dampingFraction: 0.82), value: isSelected)
    }
}

struct WorldCupQuestSheetView: View {
    var petName: String
    var currentCity: String
    var selectedHost: WorldCupHostCity?
    var hosts: [WorldCupHostCity]
    var existingQuest: TravelQuest?
    var isPreparing: Bool
    var onShowMap: () -> Void
    var onSelectHost: (WorldCupHostCity) -> Void
    var onPrepare: (WorldCupHostCity, Set<WorldCupBagItem>, String?) -> Void

    @State var selectedBagItems: Set<WorldCupBagItem> = [.scarf, .snack, .footballBadge]
    @State var ownerMessage = "看到热闹的地方，也要记得慢慢走。"

    var chosenHost: WorldCupHostCity? {
        selectedHost ?? hosts.first
    }

    var body: some View {
        ZStack {
            AppBackground()

            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    header

                    if let existingQuest {
                        ExistingWorldCupQuestCard(quest: existingQuest)
                    }

                    hostPicker

                    PawPassPreviewCard(host: chosenHost, currentCity: currentCity)

                    travelBagPicker

                    ownerMessageField

                    actionSection
                }
                .padding(DesignTokens.pagePadding)
            }
        }
        .navigationTitle("远方球场邀请")
        .navigationBarTitleDisplayMode(.inline)
    }

    var header: some View {
        VStack(alignment: .leading, spacing: 9) {
            HStack(spacing: 10) {
                PetSoulAssetIcon(asset: .worldCupPawTicket, fallbackTint: DesignTokens.clay, size: 30)
                    .frame(width: 38, height: 38)
                    .background(DesignTokens.clay.opacity(0.12))
                    .clipShape(Circle())

                VStack(alignment: .leading, spacing: 2) {
                    Text("远方球场邀请卡")
                        .font(.title2.weight(.semibold))
                        .foregroundStyle(DesignTokens.ink)
                    Text("先看见，不立刻出发")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(DesignTokens.secondaryInk)
                }
            }

            Text("北美有几盏球场灯亮起来了。你可以帮 \(petName) 选一个想看的地方，把邀请先放进旅行包。TA 会先把 \(currentCity) 这段路走完。")
                .font(.subheadline)
                .foregroundStyle(DesignTokens.secondaryInk)
                .lineSpacing(3)
                .fixedSize(horizontal: false, vertical: true)

            Button(action: onShowMap) {
                Label("回到地图看亮起的球场", systemImage: "map.fill")
                    .frame(maxWidth: .infinity)
            }
            .quietActionStyle()
        }
        .padding(16)
        .background(DesignTokens.surface.opacity(0.78))
        .clipShape(RoundedRectangle(cornerRadius: DesignTokens.cardRadius, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: DesignTokens.cardRadius, style: .continuous)
                .stroke(DesignTokens.softLine, lineWidth: 1)
        }
    }

    var hostPicker: some View {
        VStack(alignment: .leading, spacing: 10) {
            Label("选择一个亮起的球场", systemImage: "sportscourt.fill")
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(DesignTokens.ink)

            LazyVGrid(columns: [GridItem(.adaptive(minimum: 148), spacing: 10)], spacing: 10) {
                ForEach(hosts) { host in
                    Button {
                        onSelectHost(host)
                    } label: {
                        WorldCupHostTile(host: host, isSelected: chosenHost?.id == host.id)
                    }
                    .buttonStyle(.plain)
                }
            }
        }
    }

    var travelBagPicker: some View {
        VStack(alignment: .leading, spacing: 10) {
            Label("旅行包里带一点什么", systemImage: "backpack.fill")
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(DesignTokens.ink)

            LazyVGrid(columns: [GridItem(.adaptive(minimum: 140), spacing: 10)], spacing: 10) {
                ForEach(WorldCupBagItem.allCases) { item in
                    Button {
                        if selectedBagItems.contains(item) {
                            selectedBagItems.remove(item)
                        } else {
                            selectedBagItems.insert(item)
                        }
                    } label: {
                        WorldCupBagItemTile(item: item, isSelected: selectedBagItems.contains(item))
                    }
                    .buttonStyle(.plain)
                }
            }
        }
        .padding(14)
        .background(DesignTokens.surface.opacity(0.76))
        .clipShape(RoundedRectangle(cornerRadius: DesignTokens.cardRadius, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: DesignTokens.cardRadius, style: .continuous)
                .stroke(DesignTokens.softLine, lineWidth: 1)
        }
    }

    var ownerMessageField: some View {
        VStack(alignment: .leading, spacing: 8) {
            Label("给主人留在旅行包里的话", systemImage: "text.bubble.fill")
                .font(.caption.weight(.bold))
                .foregroundStyle(DesignTokens.secondaryInk)

            TextField("比如：看见热闹的地方，也要记得慢慢走。", text: $ownerMessage, axis: .vertical)
                .lineLimit(2...4)
                .font(.body)
                .textFieldStyle(.plain)
                .padding(12)
                .background(DesignTokens.surface.opacity(0.78))
                .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
        }
        .padding(14)
        .background(DesignTokens.mist.opacity(0.54))
        .clipShape(RoundedRectangle(cornerRadius: DesignTokens.cardRadius, style: .continuous))
    }

    var actionSection: some View {
        VStack(alignment: .leading, spacing: 9) {
            Button {
                guard let chosenHost else { return }
                onPrepare(chosenHost, selectedBagItems, ownerMessage)
            } label: {
                HStack {
                    if isPreparing {
                        ProgressView()
                            .tint(.white)
                    }
                    Label("放进旅行包", systemImage: "backpack.fill")
                        .frame(maxWidth: .infinity)
                }
            }
            .primaryActionStyle()
            .disabled(isPreparing || chosenHost == nil)

            Text("这不是现实签证或真实球票。Paw Pass 只是 \(petName) 在另一端世界远行用的小小通行证。")
                .font(.caption)
                .foregroundStyle(DesignTokens.secondaryInk)
                .lineSpacing(2)
        }
    }
}

struct WorldCupHostTile: View {
    var host: WorldCupHostCity
    var isSelected: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 7) {
            HStack(spacing: 8) {
                PetSoulAssetIcon(
                    asset: .worldCupFootball,
                    fallbackTint: isSelected ? DesignTokens.clay : DesignTokens.dusk,
                    size: 22
                )
                    .frame(width: 26, height: 26)
                    .background((isSelected ? DesignTokens.clay : DesignTokens.dusk).opacity(0.12))
                    .clipShape(Circle())

                VStack(alignment: .leading, spacing: 1) {
                    Text(host.city)
                        .font(.caption.weight(.bold))
                        .foregroundStyle(DesignTokens.ink)
                        .lineLimit(1)
                    Text(host.country)
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(DesignTokens.secondaryInk)
                        .lineLimit(1)
                }

                Spacer(minLength: 0)
            }

            Text(host.stadiumName)
                .font(.caption)
                .foregroundStyle(DesignTokens.secondaryInk)
                .lineLimit(1)

            Text(host.atmosphereHint)
                .font(.caption2)
                .foregroundStyle(DesignTokens.secondaryInk)
                .lineLimit(2)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(11)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(isSelected ? DesignTokens.petal.opacity(0.72) : DesignTokens.surface.opacity(0.78))
        .clipShape(RoundedRectangle(cornerRadius: DesignTokens.cardRadius, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: DesignTokens.cardRadius, style: .continuous)
                .stroke(isSelected ? DesignTokens.clay.opacity(0.62) : DesignTokens.softLine, lineWidth: 1)
        }
    }
}

extension WorldCupBagItem {
    var petSoulAsset: PetSoulAsset {
        switch self {
        case .scarf:
            .worldCupScarf
        case .snack:
            .worldCupSnacks
        case .cameraCharm:
            .worldCupCamera
        case .footballBadge:
            .worldCupMedal
        case .smallFlag:
            .worldCupFlag
        }
    }
}

struct WorldCupBagItemTile: View {
    var item: WorldCupBagItem
    var isSelected: Bool

    var body: some View {
        HStack(spacing: 8) {
            PetSoulAssetIcon(
                asset: item.petSoulAsset,
                fallbackSystemImage: item.systemImage,
                fallbackTint: isSelected ? DesignTokens.clay : DesignTokens.secondaryInk,
                size: 24
            )
                .frame(width: 28, height: 28)
                .background((isSelected ? DesignTokens.clay : DesignTokens.softLine).opacity(0.14))
                .clipShape(Circle())

            Text(item.title)
                .font(.caption.weight(.semibold))
                .foregroundStyle(DesignTokens.ink)
                .lineLimit(1)

            Spacer(minLength: 0)

            Image(systemName: isSelected ? "checkmark.circle.fill" : "circle")
                .font(.caption.weight(.bold))
                .foregroundStyle(isSelected ? DesignTokens.clay : DesignTokens.softLine)
        }
        .padding(10)
        .background(isSelected ? DesignTokens.petal.opacity(0.58) : DesignTokens.surface.opacity(0.72))
        .clipShape(RoundedRectangle(cornerRadius: DesignTokens.cardRadius, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: DesignTokens.cardRadius, style: .continuous)
                .stroke(isSelected ? DesignTokens.clay.opacity(0.58) : DesignTokens.softLine, lineWidth: 1)
        }
    }
}

struct PawPassPreviewCard: View {
    var host: WorldCupHostCity?
    var currentCity: String

    var body: some View {
        VStack(alignment: .leading, spacing: 11) {
            HStack(spacing: 10) {
                PetSoulAssetIcon(asset: .worldCupPawPass, fallbackTint: DesignTokens.sage, size: 30)
                    .frame(width: 38, height: 38)
                    .background(DesignTokens.sage.opacity(0.12))
                    .clipShape(Circle())

                VStack(alignment: .leading, spacing: 2) {
                    Text("Paw Pass 准备预览")
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(DesignTokens.ink)
                    Text("虚拟通行证，不是现实签证")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(DesignTokens.secondaryInk)
                }
            }

            VStack(alignment: .leading, spacing: 7) {
                PawPassStep(title: "确认现在位置", value: currentCity, systemImage: "location.fill")
                PawPassStep(title: "远方球场", value: host?.displayName ?? "等待选择", systemImage: "sportscourt.fill")
                PawPassStep(title: "出发节奏", value: "先走完今天这段路", systemImage: "clock.fill")
            }
        }
        .padding(14)
        .background(DesignTokens.surface.opacity(0.78))
        .clipShape(RoundedRectangle(cornerRadius: DesignTokens.cardRadius, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: DesignTokens.cardRadius, style: .continuous)
                .stroke(DesignTokens.softLine, lineWidth: 1)
        }
    }
}

struct PawPassStep: View {
    var title: String
    var value: String
    var systemImage: String

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: systemImage)
                .font(.caption.weight(.bold))
                .foregroundStyle(DesignTokens.sage)
                .frame(width: 24, height: 24)
                .background(DesignTokens.sage.opacity(0.11))
                .clipShape(Circle())

            Text(title)
                .font(.caption.weight(.bold))
                .foregroundStyle(DesignTokens.secondaryInk)
                .frame(width: 82, alignment: .leading)

            Text(value)
                .font(.caption.weight(.semibold))
                .foregroundStyle(DesignTokens.ink)
                .lineLimit(2)
                .fixedSize(horizontal: false, vertical: true)
        }
    }
}

struct ExistingWorldCupQuestCard: View {
    var quest: TravelQuest

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: "checkmark.seal.fill")
                .font(.headline.weight(.semibold))
                .foregroundStyle(DesignTokens.sage)
                .frame(width: 34, height: 34)
                .background(DesignTokens.sage.opacity(0.12))
                .clipShape(Circle())

            VStack(alignment: .leading, spacing: 4) {
                Text("邀请已经收好")
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(DesignTokens.ink)
                Text("\(quest.destination) · \(quest.status.displayName)。TA 会按自己的节奏继续。")
                    .font(.caption)
                    .foregroundStyle(DesignTokens.secondaryInk)
                    .lineLimit(3)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(13)
        .background(DesignTokens.mist.opacity(0.62))
        .clipShape(RoundedRectangle(cornerRadius: DesignTokens.cardRadius, style: .continuous))
    }
}
