import PhotosUI
import SwiftUI
import UIKit

struct WalletProgressPill: View {
    var title: String
    var value: String
    var tint: Color

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(value)
                .font(.subheadline.weight(.bold))
                .foregroundStyle(DesignTokens.ink)
                .lineLimit(1)
                .minimumScaleFactor(0.76)
            Text(title)
                .font(.caption2.weight(.semibold))
                .foregroundStyle(DesignTokens.secondaryInk)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(10)
        .background(tint.opacity(0.1))
        .clipShape(RoundedRectangle(cornerRadius: DesignTokens.cardRadius, style: .continuous))
    }
}

struct CredentialWalletTile: View {
    var credential: PetCredentialSnapshot
    var isSelected: Bool

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: credential.isUnlocked ? credential.kind.systemImage : "lock.fill")
                .font(.caption.weight(.bold))
                .foregroundStyle(isSelected ? .white : credential.kind.tint)
                .frame(width: 28, height: 28)
                .background((isSelected ? .white : credential.kind.tint).opacity(isSelected ? 0.16 : 0.1))
                .clipShape(Circle())

            VStack(alignment: .leading, spacing: 2) {
                Text(credential.kind.subtitle)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(isSelected ? .white : DesignTokens.ink)
                    .lineLimit(1)
                    .minimumScaleFactor(0.78)
                Text(credential.isUnlocked ? credential.statusLine : credential.unlockHint)
                    .font(.caption2)
                    .foregroundStyle(isSelected ? .white.opacity(0.76) : DesignTokens.secondaryInk)
                    .lineLimit(1)
                    .minimumScaleFactor(0.72)
            }

            Spacer(minLength: 0)
        }
        .padding(10)
        .frame(minHeight: 54)
        .background(isSelected ? credential.kind.tint : DesignTokens.surface.opacity(0.74))
        .clipShape(RoundedRectangle(cornerRadius: DesignTokens.cardRadius, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: DesignTokens.cardRadius, style: .continuous)
                .stroke(isSelected ? .white.opacity(0.26) : credential.kind.tint.opacity(0.16), lineWidth: 1)
        }
        .opacity(credential.isUnlocked ? 1 : 0.62)
    }
}

struct CredentialComingSoonTile: View {
    var title: String
    var detail: String
    var systemImage: String
    var tint: Color

    var body: some View {
        HStack(spacing: 9) {
            Image(systemName: systemImage)
                .font(.caption.weight(.bold))
                .foregroundStyle(tint)
                .frame(width: 30, height: 30)
                .background(tint.opacity(0.11))
                .clipShape(Circle())

            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(DesignTokens.ink)
                Text(detail)
                    .font(.caption2)
                    .foregroundStyle(DesignTokens.secondaryInk)
                    .lineLimit(1)
                    .minimumScaleFactor(0.74)
            }

            Spacer(minLength: 0)

            Text("未解锁")
                .font(.caption2.weight(.bold))
                .foregroundStyle(tint)
                .padding(.vertical, 5)
                .padding(.horizontal, 8)
                .background(tint.opacity(0.1))
                .clipShape(Capsule())
        }
        .padding(11)
        .background(DesignTokens.surface.opacity(0.68))
        .clipShape(RoundedRectangle(cornerRadius: DesignTokens.cardRadius, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: DesignTokens.cardRadius, style: .continuous)
                .stroke(tint.opacity(0.14), lineWidth: 1)
        }
    }
}

struct PetCredentialCard: View {
    var credential: PetCredentialSnapshot

    var body: some View {
        ZStack(alignment: .topLeading) {
            documentImage
                .opacity(credential.isUnlocked ? 1 : 0.54)

            if !credential.isUnlocked {
                VStack(spacing: 8) {
                    Image(systemName: "lock.fill")
                        .font(.headline.weight(.bold))
                        .foregroundStyle(.white)
                        .frame(width: 38, height: 38)
                        .background(.black.opacity(0.2))
                        .clipShape(Circle())
                    Text(credential.unlockHint)
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.white)
                        .multilineTextAlignment(.center)
                        .lineLimit(2)
                        .minimumScaleFactor(0.76)
                        .padding(.horizontal, 18)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .background(.black.opacity(0.16))
            }
        }
        .frame(maxWidth: .infinity)
        .aspectRatio(credential.kind.documentAspectRatio, contentMode: .fit)
        .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .stroke(DesignTokens.surfaceStroke.opacity(0.38), lineWidth: 1)
        }
        .overlay(alignment: .top) {
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .stroke(
                    LinearGradient(
                        colors: [.white.opacity(0.58), .white.opacity(0.05)],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    ),
                    lineWidth: 1
                )
                .allowsHitTesting(false)
        }
        .shadow(color: credential.kind.tint.opacity(0.24), radius: 24, x: 0, y: 12)
    }

    var documentImage: some View {
        ZStack {
            LinearGradient(
                colors: credential.kind.gradientColors,
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )

            CredentialCardTexture(tint: .white)

            VStack(alignment: .leading, spacing: 0) {
                HStack(alignment: .top, spacing: 10) {
                    VStack(alignment: .leading, spacing: 2) {
                        Text("PETSOUL REPUBLIC")
                            .font(.system(size: 9, weight: .heavy, design: .rounded))
                            .foregroundStyle(.white.opacity(0.72))
                            .kerning(1.4)
                        Text(credential.kind.title)
                            .font(.headline.weight(.bold))
                            .foregroundStyle(.white)
                            .lineLimit(1)
                            .minimumScaleFactor(0.7)
                        Text(credential.kind.subtitle)
                            .font(.caption2.weight(.semibold))
                            .foregroundStyle(.white.opacity(0.78))
                            .lineLimit(1)
                    }

                    Spacer(minLength: 8)

                    CredentialSeal(text: credential.kind.rarity)
                }

                Spacer(minLength: 10)

                HStack(alignment: .bottom, spacing: 12) {
                    if credential.kind.category == .documents {
                        CredentialPortraitGlyph(
                            petID: credential.petID,
                            petType: credential.petType,
                            tint: credential.kind.tint
                        )
                    }

                    VStack(alignment: .leading, spacing: 6) {
                        ForEach(credential.cardDisplayFields, id: \.0) { field in
                            CredentialTinyField(title: field.0, value: field.1)
                        }
                    }

                    Spacer(minLength: 0)
                }
            }
            .padding(15)
        }
    }
}

struct CredentialCardTexture: View {
    var tint: Color

    var body: some View {
        Canvas { context, size in
            guard size.width > 0, size.height > 0 else { return }
            for index in 0..<5 {
                let y = size.height * (0.15 + CGFloat(index) * 0.18)
                var path = Path()
                path.move(to: CGPoint(x: -20, y: y))
                path.addCurve(
                    to: CGPoint(x: size.width + 20, y: y + CGFloat(index % 2 == 0 ? 34 : -28)),
                    control1: CGPoint(x: size.width * 0.28, y: y - 36),
                    control2: CGPoint(x: size.width * 0.72, y: y + 42)
                )
                context.stroke(path, with: .color(tint.opacity(0.16)), style: StrokeStyle(lineWidth: 1.1, lineCap: .round))
            }

            let sealRect = CGRect(x: size.width - 124, y: size.height - 124, width: 160, height: 160)
            context.stroke(Path(ellipseIn: sealRect), with: .color(tint.opacity(0.18)), lineWidth: 1.4)
            context.stroke(Path(ellipseIn: sealRect.insetBy(dx: 18, dy: 18)), with: .color(tint.opacity(0.13)), lineWidth: 1)

            let step: CGFloat = 18
            var x: CGFloat = 14
            while x < size.width - 14 {
                var y: CGFloat = 18
                while y < size.height - 18 {
                    let offset = sin(Double(x * 0.21 + y * 0.13)) * 1.6
                    let rect = CGRect(x: x + CGFloat(offset), y: y, width: 1.4, height: 1.4)
                    context.fill(Path(ellipseIn: rect), with: .color(tint.opacity(0.075)))
                    y += step
                }
                x += step
            }
        }
        .allowsHitTesting(false)
        .accessibilityHidden(true)
    }
}

struct CredentialPetPhoto: View {
    var petID: String
    var petType: PetType
    var contentMode: ContentMode = .fill

    var body: some View {
        if let image = PetAvatarStore.image(for: petID) {
            Image(uiImage: image)
                .resizable()
                .aspectRatio(contentMode: contentMode)
        } else {
            ZStack {
                DesignTokens.petal
                Image(systemName: petType.symbolName)
                    .font(.system(size: 56, weight: .semibold))
                    .foregroundStyle(DesignTokens.clay)
            }
            .aspectRatio(3.0 / 4.0, contentMode: contentMode)
        }
    }
}

struct CredentialPortraitGlyph: View {
    var petID: String
    var petType: PetType
    var tint: Color
    var width: CGFloat = 76
    var height: CGFloat = 82

    var body: some View {
        ZStack(alignment: .bottom) {
            Group {
                if let image = PetAvatarStore.image(for: petID) {
                    Image(uiImage: image)
                        .resizable()
                        .scaledToFill()
                } else {
                    ZStack {
                        tint.opacity(0.4)
                        Image(systemName: petType.symbolName)
                            .font(.system(size: width * 0.38, weight: .semibold))
                            .foregroundStyle(.white.opacity(0.92))
                    }
                }
            }
            .frame(width: width, height: height)
            .clipped()

            Text(petType.displayName)
                .font(.system(size: 8, weight: .heavy, design: .rounded))
                .foregroundStyle(.white)
                .lineLimit(1)
                .minimumScaleFactor(0.62)
                .padding(.vertical, 4)
                .padding(.horizontal, 7)
                .frame(maxWidth: .infinity)
                .background(.black.opacity(0.32))
        }
        .frame(width: width, height: height)
        .background(DesignTokens.surface.opacity(0.15))
        .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .stroke(DesignTokens.surfaceStroke.opacity(0.25), lineWidth: 1)
        }
    }
}

struct CredentialTinyField: View {
    var title: String
    var value: String

    var body: some View {
        VStack(alignment: .leading, spacing: 1) {
            Text(title.uppercased())
                .font(.system(size: 8, weight: .bold))
                .foregroundStyle(.white.opacity(0.62))
            Text(value)
                .font(.caption.weight(.semibold))
                .foregroundStyle(.white)
                .lineLimit(1)
                .minimumScaleFactor(0.72)
        }
    }
}

struct CredentialSeal: View {
    var text: String

    var body: some View {
        ZStack {
            Circle()
                .stroke(DesignTokens.surfaceStroke.opacity(0.56), lineWidth: 1.2)
            Circle()
                .stroke(DesignTokens.surfaceStroke.opacity(0.28), lineWidth: 1)
                .padding(5)
            Text(text.uppercased())
                .font(.system(size: 9, weight: .heavy, design: .rounded))
                .foregroundStyle(.white.opacity(0.86))
                .lineLimit(1)
                .minimumScaleFactor(0.55)
                .padding(9)
        }
        .frame(width: 48, height: 48)
    }
}

struct CredentialDetailPanel: View {
    var credential: PetCredentialSnapshot
    var onNotice: (String) -> Void

    var body: some View {
        SoftCard {
            VStack(alignment: .leading, spacing: 13) {
                HStack(spacing: 10) {
                    Image(systemName: credential.kind.systemImage)
                        .font(.headline.weight(.semibold))
                        .foregroundStyle(credential.kind.tint)
                        .frame(width: 34, height: 34)
                        .background(credential.kind.tint.opacity(0.12))
                        .clipShape(Circle())

                    VStack(alignment: .leading, spacing: 2) {
                        Text(detailTitle)
                            .font(.headline.weight(.semibold))
                            .foregroundStyle(DesignTokens.ink)
                        Text(detailSubtitle)
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(DesignTokens.secondaryInk)
                            .lineLimit(2)
                    }

                    Spacer(minLength: 0)

                    Text(credential.isUnlocked ? "已解锁" : "未解锁")
                        .font(.caption2.weight(.bold))
                        .foregroundStyle(credential.isUnlocked ? credential.kind.tint : DesignTokens.secondaryInk)
                        .padding(.vertical, 5)
                        .padding(.horizontal, 8)
                        .background((credential.isUnlocked ? credential.kind.tint : DesignTokens.secondaryInk).opacity(0.1))
                        .clipShape(Capsule())
                }

                Text(credential.detailDescription)
                    .font(.subheadline)
                    .foregroundStyle(DesignTokens.ink)
                    .lineSpacing(3)
                    .fixedSize(horizontal: false, vertical: true)

                LazyVGrid(columns: [GridItem(.adaptive(minimum: 96), spacing: 8)], spacing: 8) {
                    ForEach(Array(credential.keyDetailFields.enumerated()), id: \.offset) { _, field in
                        CredentialInfoTile(title: field.0, value: field.1, tint: credential.kind.tint)
                    }
                }

                if !credential.isUnlocked {
                    HStack(spacing: 8) {
                        Image(systemName: "lock.fill")
                            .font(.caption.weight(.bold))
                            .foregroundStyle(credential.kind.tint)
                        Text(credential.unlockHint)
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(DesignTokens.secondaryInk)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    .padding(10)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(credential.kind.tint.opacity(0.09))
                    .clipShape(RoundedRectangle(cornerRadius: DesignTokens.cardRadius, style: .continuous))
                }

                VStack(alignment: .leading, spacing: 9) {
                    Text(credential.kind == .healthRecord ? "基本信息" : "字段信息")
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(DesignTokens.ink)

                    LazyVGrid(columns: [GridItem(.adaptive(minimum: 132), spacing: 9)], spacing: 9) {
                        ForEach(Array(detailFields.enumerated()), id: \.offset) { _, field in
                            CredentialInfoTile(title: field.0, value: field.1, tint: credential.kind.tint)
                        }
                    }
                }

                if let careNote = credential.careNote, credential.kind == .healthRecord {
                    VStack(alignment: .leading, spacing: 5) {
                        Text("照护备注")
                            .font(.caption.weight(.bold))
                            .foregroundStyle(DesignTokens.secondaryInk)
                        Text(careNote)
                            .font(.subheadline.weight(.semibold))
                            .foregroundStyle(DesignTokens.ink)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    .padding(11)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(credential.kind.tint.opacity(0.09))
                    .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
                }

                HStack(spacing: 7) {
                    ForEach(credential.stamps, id: \.self) { stamp in
                        Label(stamp, systemImage: "seal.fill")
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(credential.kind.tint)
                            .padding(.vertical, 7)
                            .padding(.horizontal, 9)
                            .background(credential.kind.tint.opacity(0.1))
                            .clipShape(Capsule())
                    }
                }

                Text(credential.requirementNote)
                    .font(.subheadline)
                    .foregroundStyle(DesignTokens.secondaryInk)
                    .lineSpacing(3)
                    .fixedSize(horizontal: false, vertical: true)

                Text(credential.safetyLine)
                    .font(.caption)
                    .foregroundStyle(DesignTokens.secondaryInk)
                    .lineSpacing(2)
                    .padding(10)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(DesignTokens.mist.opacity(0.58))
                    .clipShape(RoundedRectangle(cornerRadius: DesignTokens.cardRadius, style: .continuous))

                LazyVGrid(columns: [GridItem(.adaptive(minimum: 110), spacing: 8)], spacing: 8) {
                    ShareLink(item: credential.shareText) {
                        CredentialActionLabel(
                            title: "分享",
                            systemImage: "square.and.arrow.up",
                            tint: credential.kind.tint
                        )
                    }
                    .buttonStyle(.plain)

                    Button {
                        onNotice(credential.isUnlocked ? "高清卡片保存会在模板导出后开放。" : "先解锁这张证件，再保存高清卡片。")
                    } label: {
                        CredentialActionLabel(
                            title: "保存",
                            systemImage: "square.and.arrow.down.fill",
                            tint: credential.kind.tint
                        )
                    }
                    .buttonStyle(.plain)

                    Button {
                        onNotice("\(credential.kind.subtitle) 已设为当前卡包预览。")
                    } label: {
                        CredentialActionLabel(
                            title: "设封面",
                            systemImage: "rectangle.on.rectangle.angled.fill",
                            tint: credential.kind.tint
                        )
                    }
                    .buttonStyle(.plain)
                }
            }
        }
    }

    var detailTitle: String {
        credential.kind == .healthRecord ? "\(credential.holderName) 的健康档案" : credential.kind.subtitle
    }

    var detailSubtitle: String {
        if credential.kind == .healthRecord {
            let health = credential.keyDetailFields.first { $0.0 == "健康状态" }?.1 ?? "稳定"
            let vaccine = credential.keyDetailFields.first { $0.0 == "疫苗记录" }?.1 ?? "已记录"
            return "\(health) · 疫苗\(vaccine)"
        }
        return credential.statusLine
    }

    var detailFields: [(String, String)] {
        if credential.kind == .healthRecord {
            return credential.basicInfoFields
        }
        return credential.fields
    }
}

struct CredentialActionLabel: View {
    var title: String
    var systemImage: String
    var tint: Color

    var body: some View {
        Label(title, systemImage: systemImage)
            .font(.caption.weight(.semibold))
            .foregroundStyle(tint)
            .frame(maxWidth: .infinity)
            .padding(.vertical, 9)
            .padding(.horizontal, 10)
            .background(tint.opacity(0.1))
            .clipShape(RoundedRectangle(cornerRadius: DesignTokens.cardRadius, style: .continuous))
    }
}

struct CredentialInfoTile: View {
    var title: String
    var value: String
    var tint: Color

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title)
                .font(.caption.weight(.bold))
                .foregroundStyle(DesignTokens.secondaryInk)
            Text(value)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(DesignTokens.ink)
                .lineLimit(2)
                .minimumScaleFactor(0.78)
                .fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity, minHeight: 58, alignment: .topLeading)
        .padding(10)
        .background(tint.opacity(0.09))
        .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
    }
}
