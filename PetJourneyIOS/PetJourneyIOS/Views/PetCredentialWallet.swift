import PhotosUI
import SwiftUI
import UIKit

struct PetCredentialWalletView: View {
    var status: AgentStatus?
    var dna: PetDNA?
    var souvenirCount: Int
    var travelQuests: [TravelQuest]

    @State var selectedKind: PetCredentialKind = .identity
    @State var walletNotice: String?

    var credentials: [PetCredentialSnapshot] {
        PetCredentialSnapshot.all(status: status, dna: dna, souvenirCount: souvenirCount, travelQuests: travelQuests)
    }

    var selectedCredential: PetCredentialSnapshot {
        credentials.first { $0.kind == selectedKind } ?? credentials[0]
    }

    var unlockedCredentials: [PetCredentialSnapshot] {
        credentials.filter(\.isUnlocked)
    }

    var carouselCredentials: [PetCredentialSnapshot] {
        unlockedCredentials.isEmpty ? credentials : unlockedCredentials
    }

    var body: some View {
        ZStack {
            AppBackground()

            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    walletHeader

                    walletProgress

                    credentialPager

                    credentialSections
                }
                .padding(DesignTokens.pagePadding)
                .padding(.bottom, 120)
            }
        }
        .overlay(alignment: .bottom) {
            if let walletNotice {
                ToastView(message: walletNotice)
                    .padding(.horizontal, DesignTokens.pagePadding)
                    .padding(.bottom, 18)
                    .transition(.move(edge: .bottom).combined(with: .opacity))
            }
        }
        .navigationTitle("PetSoul Wallet")
        .navigationBarTitleDisplayMode(.inline)
    }

    var walletHeader: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 10) {
                PetSoulAssetIcon(
                    asset: .luckyCharm,
                    fallbackSystemImage: "wallet.pass.fill",
                    fallbackTint: DesignTokens.dusk,
                    size: 36
                )
                .frame(width: 42, height: 42)
                .background(DesignTokens.dusk.opacity(0.12))
                .clipShape(Circle())

                VStack(alignment: .leading, spacing: 2) {
                    Text("PetSoul Wallet")
                        .font(.title2.weight(.bold))
                        .foregroundStyle(DesignTokens.ink)
                    Text("\(status?.name ?? "TA") 的卡包")
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(DesignTokens.secondaryInk)
                }
            }

            Text("这里保存着 TA 在 PetSoul 世界里的身份、健康和旅途票据。像翻钱包一样，一张张拿出来看。")
                .font(.subheadline)
                .foregroundStyle(DesignTokens.secondaryInk)
                .lineSpacing(3)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(.top, 4)
    }

    var walletProgress: some View {
        HStack(spacing: 9) {
            WalletProgressPill(
                title: "已解锁",
                value: "\(unlockedCredentials.count)/\(credentials.count)",
                tint: DesignTokens.sage
            )
            WalletProgressPill(
                title: "主证",
                value: selectedCredential.kind.subtitle,
                tint: selectedCredential.kind.tint
            )
            WalletProgressPill(
                title: "照片档案",
                value: "双照片",
                tint: DesignTokens.clay
            )
        }
    }

    var credentialPager: some View {
        TabView(selection: $selectedKind) {
            ForEach(carouselCredentials, id: \.kind) { credential in
                NavigationLink {
                    WalletCardDetailView(credential: credential)
                } label: {
                    PetCredentialCard(credential: credential)
                        .padding(.horizontal, 2)
                }
                .buttonStyle(.plain)
                .tag(credential.kind)
            }
        }
        .tabViewStyle(.page(indexDisplayMode: .always))
        .frame(height: selectedKind == .passport ? 286 : 252)
    }

    var credentialSections: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("全部证件")
                .font(.headline.weight(.semibold))
                .foregroundStyle(DesignTokens.ink)

            ForEach(PetCredentialCategory.allCases) { category in
                let categoryCredentials = credentials.filter { $0.kind.category == category }
                if !categoryCredentials.isEmpty {
                    VStack(alignment: .leading, spacing: 8) {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(category.title)
                                .font(.subheadline.weight(.semibold))
                                .foregroundStyle(DesignTokens.ink)
                            Text(category.subtitle)
                                .font(.caption)
                                .foregroundStyle(DesignTokens.secondaryInk)
                        }

                        LazyVGrid(columns: [GridItem(.adaptive(minimum: 145), spacing: 9)], spacing: 9) {
                            ForEach(categoryCredentials, id: \.kind) { credential in
                                NavigationLink {
                                    WalletCardDetailView(credential: credential)
                                } label: {
                                    CredentialWalletTile(
                                        credential: credential,
                                        isSelected: selectedKind == credential.kind
                                    )
                                }
                                .buttonStyle(.plain)
                                .simultaneousGesture(TapGesture().onEnded {
                                    selectedKind = credential.isUnlocked
                                        ? credential.kind
                                        : (carouselCredentials.first?.kind ?? selectedKind)
                                })
                                .accessibilityLabel(credential.kind.subtitle)
                            }
                        }
                    }
                }
            }

            lockedCardSection
        }
    }

    var lockedCardSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            VStack(alignment: .leading, spacing: 2) {
                Text("未解锁")
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(DesignTokens.ink)
                Text("旅程继续展开后，会陆续收进更多票据")
                    .font(.caption)
                    .foregroundStyle(DesignTokens.secondaryInk)
            }

            VStack(spacing: 8) {
                Button {
                    showNotice("高铁票会在城市间铁路旅行时收进卡包。")
                } label: {
                    CredentialComingSoonTile(
                        title: "高铁票 / 车票",
                        detail: "铁路或长途交通支线点亮后出现",
                        systemImage: "tram.fill",
                        tint: DesignTokens.dusk
                    )
                }
                .buttonStyle(.plain)

                Button {
                    showNotice("世界杯 Fan Pass 会在球场支线开启后收进卡包。")
                } label: {
                    CredentialComingSoonTile(
                        title: "世界杯 Fan Pass",
                        detail: "美加墨球场支线点亮后出现",
                        systemImage: "sportscourt.fill",
                        tint: DesignTokens.sea
                    )
                }
                .buttonStyle(.plain)

                Button {
                    showNotice("景点票根会在 TA 到达特别地点后收进卡包。")
                } label: {
                    CredentialComingSoonTile(
                        title: "景点票根",
                        detail: "城市纪念地点解锁后出现",
                        systemImage: "ticket.fill",
                        tint: DesignTokens.amber
                    )
                }
                .buttonStyle(.plain)
            }
        }
    }

    func showNotice(_ message: String) {
        withAnimation(.spring(response: 0.28, dampingFraction: 0.9)) {
            walletNotice = message
        }
        Task {
            try? await Task.sleep(nanoseconds: 1_800_000_000)
            await MainActor.run {
                if walletNotice == message {
                    withAnimation(.easeOut(duration: 0.2)) {
                        walletNotice = nil
                    }
                }
            }
        }
    }
}

struct WalletCardDetailView: View {
    var credential: PetCredentialSnapshot
    @State var walletNotice: String?
    @State var selectedPhotoRole: PetCredentialPhotoRole = .officialIDPortrait
    @State var photoViewerRole: PetCredentialPhotoRole?

    var body: some View {
        ZStack {
            AppBackground()

            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    PetCredentialCard(credential: credential)

                    CredentialPortraitArchiveSection(
                        credential: credential,
                        selectedRole: $selectedPhotoRole,
                        onOpen: { role in
                            photoViewerRole = role
                        },
                        onNotice: { message in
                            showNotice(message)
                        }
                    )

                    CredentialDetailPanel(credential: credential) { message in
                        showNotice(message)
                    }
                }
                .padding(DesignTokens.pagePadding)
                .padding(.bottom, 120)
            }
        }
        .fullScreenCover(item: $photoViewerRole) { role in
            PetCredentialPortraitViewer(
                credential: credential,
                initialRole: role
            )
        }
        .overlay(alignment: .bottom) {
            if let walletNotice {
                ToastView(message: walletNotice)
                    .padding(.horizontal, DesignTokens.pagePadding)
                    .padding(.bottom, 18)
                    .transition(.move(edge: .bottom).combined(with: .opacity))
            }
        }
        .navigationTitle(credential.kind.subtitle)
        .navigationBarTitleDisplayMode(.inline)
    }

    func showNotice(_ message: String) {
        withAnimation(.spring(response: 0.28, dampingFraction: 0.9)) {
            walletNotice = message
        }
        Task {
            try? await Task.sleep(nanoseconds: 1_800_000_000)
            await MainActor.run {
                if walletNotice == message {
                    withAnimation(.easeOut(duration: 0.2)) {
                        walletNotice = nil
                    }
                }
            }
        }
    }
}

struct CredentialPortraitArchiveSection: View {
    var credential: PetCredentialSnapshot
    @Binding var selectedRole: PetCredentialPhotoRole
    var onOpen: (PetCredentialPhotoRole) -> Void
    var onNotice: (String) -> Void

    var body: some View {
        SoftCard {
            VStack(alignment: .leading, spacing: 13) {
                HStack(spacing: 10) {
                    Image(systemName: "photo.stack.fill")
                        .font(.headline.weight(.semibold))
                        .foregroundStyle(credential.kind.tint)
                        .frame(width: 34, height: 34)
                        .background(credential.kind.tint.opacity(0.12))
                        .clipShape(Circle())

                    VStack(alignment: .leading, spacing: 2) {
                        Text("照片档案")
                            .font(.headline.weight(.semibold))
                            .foregroundStyle(DesignTokens.ink)
                        Text("证件照和原始照片分开保存")
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(DesignTokens.secondaryInk)
                    }

                    Spacer(minLength: 0)
                }

                Picker("照片档案", selection: $selectedRole) {
                    ForEach(PetCredentialPhotoRole.allCases) { role in
                        Text(role.title).tag(role)
                    }
                }
                .pickerStyle(.segmented)

                Button {
                    onOpen(selectedRole)
                } label: {
                    CredentialPhotoArchivePreview(
                        credential: credential,
                        role: selectedRole
                    )
                }
                .buttonStyle(.plain)

                LazyVGrid(columns: [GridItem(.adaptive(minimum: 132), spacing: 9)], spacing: 9) {
                    ForEach(PetCredentialPhotoRole.allCases) { role in
                        Button {
                            selectedRole = role
                        } label: {
                            CredentialPhotoAssetTile(
                                role: role,
                                isSelected: selectedRole == role,
                                tint: credential.kind.tint
                            )
                        }
                        .buttonStyle(.plain)
                    }
                }

                HStack(spacing: 8) {
                    Button {
                        onOpen(selectedRole)
                    } label: {
                        CredentialActionLabel(
                            title: "查看照片",
                            systemImage: "arrow.up.left.and.arrow.down.right",
                            tint: credential.kind.tint
                        )
                    }
                    .buttonStyle(.plain)

                    Button {
                        onNotice("照片保存会在高清导出链路接入后开放。")
                    } label: {
                        CredentialActionLabel(
                            title: "保存照片",
                            systemImage: "square.and.arrow.down.fill",
                            tint: credential.kind.tint
                        )
                    }
                    .buttonStyle(.plain)
                }
            }
        }
    }
}

struct CredentialPhotoArchivePreview: View {
    var credential: PetCredentialSnapshot
    var role: PetCredentialPhotoRole

    var body: some View {
        ZStack(alignment: .bottomLeading) {
            previewImage

            LinearGradient(
                colors: [.black.opacity(0), .black.opacity(0.58)],
                startPoint: .top,
                endPoint: .bottom
            )

            VStack(alignment: .leading, spacing: 5) {
                Label(role.title, systemImage: role.systemImage)
                    .font(.caption.weight(.bold))
                    .foregroundStyle(.white.opacity(0.9))
                Text(role == .officialIDPortrait ? "按证件规范生成的正面证件照，用于身份卡、护照、驾驶证和健康证。" : "保留上传时的原始生活照，用于详情页和档案查看。")
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(.white)
                    .lineSpacing(2)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .padding(14)
        }
        .frame(maxWidth: .infinity)
        .background(credential.kind.tint.opacity(0.1))
        .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .stroke(DesignTokens.surfaceStroke.opacity(0.7), lineWidth: 1)
        }
        .shadow(color: credential.kind.tint.opacity(0.14), radius: 18, x: 0, y: 8)
    }

    @ViewBuilder
    var previewImage: some View {
        if role == .officialIDPortrait {
            ZStack {
                LinearGradient(
                    colors: [
                        DesignTokens.credential.passportPhotoTop,
                        DesignTokens.credential.passportPhotoBottom
                    ],
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                )

                CredentialPassportPhotoPattern(tint: credential.kind.tint.opacity(0.15))

                CredentialPetPhoto(petID: credential.petID, petType: credential.petType, contentMode: .fit)
                    .frame(height: 286)
                    .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
                    .padding(.vertical, 12)
                    .shadow(color: DesignTokens.deepInk.opacity(0.12), radius: 16, x: 0, y: 8)
            }
            .frame(maxWidth: .infinity)
            .frame(height: 330)
        } else {
            CredentialPetPhoto(petID: credential.petID, petType: credential.petType, contentMode: .fill)
                .frame(maxWidth: .infinity)
                .frame(height: 286)
                .clipped()
        }
    }
}

struct CredentialPassportPhotoPattern: View {
    var tint: Color

    var body: some View {
        Canvas { context, size in
            guard size.width > 0, size.height > 0 else { return }

            for index in 0..<7 {
                let y = size.height * (0.12 + CGFloat(index) * 0.12)
                var path = Path()
                path.move(to: CGPoint(x: -16, y: y))
                path.addCurve(
                    to: CGPoint(x: size.width + 16, y: y + CGFloat(index % 2 == 0 ? 22 : -18)),
                    control1: CGPoint(x: size.width * 0.28, y: y - 26),
                    control2: CGPoint(x: size.width * 0.72, y: y + 30)
                )
                context.stroke(path, with: .color(tint.opacity(0.5)), style: StrokeStyle(lineWidth: 0.9, lineCap: .round))
            }

            let sealRect = CGRect(x: size.width - 112, y: 26, width: 86, height: 86)
            context.stroke(Path(ellipseIn: sealRect), with: .color(tint.opacity(0.42)), lineWidth: 1.2)
            context.stroke(Path(ellipseIn: sealRect.insetBy(dx: 12, dy: 12)), with: .color(tint.opacity(0.28)), lineWidth: 0.9)
        }
        .allowsHitTesting(false)
        .accessibilityHidden(true)
    }
}

struct CredentialPhotoAssetTile: View {
    var role: PetCredentialPhotoRole
    var isSelected: Bool
    var tint: Color

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: role.systemImage)
                .font(.caption.weight(.bold))
                .foregroundStyle(isSelected ? .white : tint)
                .frame(width: 28, height: 28)
                .background(isSelected ? .white.opacity(0.18) : tint.opacity(0.1))
                .clipShape(Circle())

            VStack(alignment: .leading, spacing: 2) {
                Text(role.title)
                    .font(.caption.weight(.bold))
                    .foregroundStyle(isSelected ? .white : DesignTokens.ink)
                Text(role.subtitle)
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(isSelected ? .white.opacity(0.76) : DesignTokens.secondaryInk)
                    .lineLimit(1)
                    .minimumScaleFactor(0.78)
            }

            Spacer(minLength: 0)
        }
        .padding(10)
        .frame(minHeight: 54)
        .background(isSelected ? tint : DesignTokens.mist.opacity(0.5))
        .clipShape(RoundedRectangle(cornerRadius: DesignTokens.cardRadius, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: DesignTokens.cardRadius, style: .continuous)
                .stroke(isSelected ? .white.opacity(0.2) : tint.opacity(0.12), lineWidth: 1)
        }
    }
}

struct PetCredentialPortraitViewer: View {
    var credential: PetCredentialSnapshot
    @Environment(\.dismiss) var dismiss
    @State var selectedRole: PetCredentialPhotoRole

    init(credential: PetCredentialSnapshot, initialRole: PetCredentialPhotoRole) {
        self.credential = credential
        _selectedRole = State(initialValue: initialRole)
    }

    var body: some View {
        ZStack {
            Color.black.opacity(0.88)
                .ignoresSafeArea()

            VStack(spacing: 16) {
                HStack {
                    VStack(alignment: .leading, spacing: 3) {
                        Text(selectedRole.title)
                            .font(.headline.weight(.semibold))
                            .foregroundStyle(.white)
                        Text(credential.kind.subtitle)
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(.white.opacity(0.68))
                    }

                    Spacer()

                    Button {
                        dismiss()
                    } label: {
                        Image(systemName: "xmark")
                            .font(.headline.weight(.bold))
                            .foregroundStyle(.white)
                            .frame(width: 38, height: 38)
                            .background(DesignTokens.surface.opacity(0.14))
                            .clipShape(Circle())
                    }
                    .buttonStyle(.plain)
                }
                .padding(.horizontal, DesignTokens.pagePadding)
                .padding(.top, 20)

                Spacer(minLength: 0)

                CredentialPetPhoto(petID: credential.petID, petType: credential.petType, contentMode: .fit)
                    .frame(maxWidth: .infinity)
                    .frame(maxHeight: 560)
                    .clipShape(RoundedRectangle(cornerRadius: 24, style: .continuous))
                    .overlay {
                        RoundedRectangle(cornerRadius: 24, style: .continuous)
                            .stroke(DesignTokens.surfaceStroke.opacity(0.16), lineWidth: 1)
                    }
                    .shadow(color: DesignTokens.deepInk.opacity(0.38), radius: 28, x: 0, y: 16)
                    .padding(.horizontal, DesignTokens.pagePadding)

                Spacer(minLength: 0)

                VStack(spacing: 12) {
                    Picker("照片档案", selection: $selectedRole) {
                        ForEach(PetCredentialPhotoRole.allCases) { role in
                            Text(role.title).tag(role)
                        }
                    }
                    .pickerStyle(.segmented)

                    HStack(spacing: 8) {
                        ShareLink(item: credential.shareText) {
                            CredentialActionLabel(
                                title: "分享",
                                systemImage: "square.and.arrow.up",
                                tint: .white
                            )
                        }
                        .buttonStyle(.plain)

                        Button {
                            dismiss()
                        } label: {
                            CredentialActionLabel(
                                title: "完成",
                                systemImage: "checkmark",
                                tint: .white
                            )
                        }
                        .buttonStyle(.plain)
                    }
                }
                .padding(DesignTokens.pagePadding)
                .background(.black.opacity(0.2))
            }
        }
    }
}
