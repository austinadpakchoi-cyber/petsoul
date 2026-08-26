import PhotosUI
import SwiftUI
import UIKit

struct JourneyHomeTabs: View {
    @EnvironmentObject private var session: AppSessionStore
    @State private var showsAccountSheet = false

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
                    Label("通讯器", systemImage: "antenna.radiowaves.left.and.right")
                }

            MemoryHubView(petID: petID, service: service)
                .tabItem {
                    Label("回忆", systemImage: "tray.full.fill")
                }
        }
        .tint(DesignTokens.sage)
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button {
                    showsAccountSheet = true
                } label: {
                    Image(systemName: "person.crop.circle")
                        .font(.body.weight(.semibold))
                }
                .foregroundStyle(DesignTokens.ink)
                .accessibilityLabel("账号")
            }
        }
        .sheet(isPresented: $showsAccountSheet) {
            AccountSheetView(currentPetName: session.petName)
                .environmentObject(session)
        }
    }
}

struct CommunicatorHomeView: View {
    let petID: String
    let service: any PetJourneyService
    @StateObject var viewModel: CommunicatorViewModel

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
                            title: "通讯",
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
            .navigationTitle("通讯器")
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

    var communicatorHeader: some View {
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
                        Text("\(viewModel.petName) 的通讯器")
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
                    CommunicatorSignalChip(title: "通讯", value: "\(viewModel.messages.count)", tint: DesignTokens.sea)
                    CommunicatorSignalChip(title: "朋友圈", value: "\(viewModel.friendsCircleMoments.count)", tint: DesignTokens.amber)
                    CommunicatorSignalChip(title: "状态", value: viewModel.chatAvailabilityText, tint: DesignTokens.clay)
                }
            }
        }
    }
}

struct CommunicatorEntryCard: View {
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

struct CommunicatorCompactEntry: View {
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

struct CommunicatorSignalChip: View {
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

struct CommunicatorPreviewPanel: View {
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
        .background(DesignTokens.surface.opacity(0.66))
        .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 8, style: .continuous)
                .stroke(DesignTokens.softLine.opacity(0.72), lineWidth: 1)
        }
    }
}
