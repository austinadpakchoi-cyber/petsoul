import SwiftUI
import UIKit

struct DNASettingsView: View {
    var dna: PetDNA?
    var isSaving = false
    var onSave: (PetDNA) -> Void = { _ in }

    @State var isEditing = false
    @State var ownerTitle: String
    @State var personality: String
    @State var catchphrase: String
    @State var voiceStyle: String
    @State var emojiPreference: String
    @State var favoritePlaces: [String]
    @State var hobbies: [String]
    @State var favoritePlaceDraft = ""
    @State var hobbyDraft = ""

    init(dna: PetDNA?, isSaving: Bool = false, onSave: @escaping (PetDNA) -> Void = { _ in }) {
        self.dna = dna
        self.isSaving = isSaving
        self.onSave = onSave
        let seed = dna ?? .fallback
        _ownerTitle = State(initialValue: seed.ownerTitle)
        _personality = State(initialValue: seed.personality)
        _catchphrase = State(initialValue: seed.catchphrase)
        _voiceStyle = State(initialValue: seed.voiceStyle)
        _emojiPreference = State(initialValue: seed.emojiPreference)
        _favoritePlaces = State(initialValue: seed.favoritePlaces)
        _hobbies = State(initialValue: seed.hobbies)
    }

    var draftDNA: PetDNA {
        PetDNA(
            ownerTitle: ownerTitle.trimmedNonEmpty(fallback: dna?.ownerTitle ?? PetDNA.fallback.ownerTitle),
            personality: personality.trimmedNonEmpty(fallback: dna?.personality ?? PetDNA.fallback.personality),
            favoritePlaces: favoritePlaces.cleanedTags(fallback: dna?.favoritePlaces ?? PetDNA.fallback.favoritePlaces),
            hobbies: hobbies.cleanedTags(fallback: dna?.hobbies ?? PetDNA.fallback.hobbies),
            catchphrase: catchphrase.trimmedNonEmpty(fallback: dna?.catchphrase ?? PetDNA.fallback.catchphrase),
            emojiPreference: emojiPreference.trimmedNonEmpty(fallback: dna?.emojiPreference ?? PetDNA.fallback.emojiPreference),
            voiceStyle: voiceStyle.trimmedNonEmpty(fallback: dna?.voiceStyle ?? PetDNA.fallback.voiceStyle)
        )
    }

    var canSave: Bool {
        guard let dna else { return false }
        return !isSaving && draftDNA != dna
    }

    var body: some View {
        ZStack {
            AppBackground()

            if let dna {
                ScrollView {
                    VStack(alignment: .leading, spacing: 16) {
                        HStack(alignment: .top, spacing: 12) {
                            VStack(alignment: .leading, spacing: 6) {
                                Text("通讯 DNA")
                                    .font(.title2.weight(.semibold))
                                    .foregroundStyle(DesignTokens.ink)
                                Text(isEditing ? "保存后会影响 TA 的旅程语气，并写入记忆档案。" : "这些偏好会慢慢影响 TA 的旅程语气。")
                                    .font(.subheadline)
                                    .foregroundStyle(DesignTokens.secondaryInk)
                            }
                            Spacer(minLength: 0)
                            HStack(spacing: 8) {
                                Button {
                                    if isEditing {
                                        resetDraft(from: dna)
                                    }
                                    isEditing.toggle()
                                } label: {
                                    Image(systemName: isEditing ? "xmark" : "pencil")
                                        .frame(width: 38, height: 38)
                                }
                                .buttonStyle(.plain)
                                .foregroundStyle(DesignTokens.ink)
                                .background(DesignTokens.mist.opacity(0.7))
                                .clipShape(Circle())
                                .accessibilityLabel(isEditing ? "取消编辑" : "编辑通讯 DNA")

                                if isEditing {
                                    Button {
                                        onSave(draftDNA)
                                        isEditing = false
                                    } label: {
                                        if isSaving {
                                            ProgressView()
                                                .frame(width: 38, height: 38)
                                        } else {
                                            Image(systemName: "checkmark")
                                                .frame(width: 38, height: 38)
                                        }
                                    }
                                    .buttonStyle(.plain)
                                    .foregroundStyle(.white)
                                    .background(canSave ? DesignTokens.sage : DesignTokens.secondaryInk.opacity(0.28))
                                    .clipShape(Circle())
                                    .disabled(!canSave)
                                    .accessibilityLabel("保存通讯 DNA")
                                }
                            }
                        }

                        DNAEditableField(title: "称呼", value: $ownerTitle, systemImage: "person", isEditing: isEditing)
                        DNAEditableField(title: "性格", value: $personality, systemImage: "sparkles", isEditing: isEditing, minHeight: 58)
                        DNAEditableField(title: "口头禅", value: $catchphrase, systemImage: "text.bubble", isEditing: isEditing)
                        DNAEditableField(title: "说话风格", value: $voiceStyle, systemImage: "waveform", isEditing: isEditing, minHeight: 58)
                        DNAEditableField(title: "语气标记", value: $emojiPreference, systemImage: "wand.and.stars", isEditing: isEditing)
                        DNAEditableListField(title: "喜欢的地方", values: $favoritePlaces, draft: $favoritePlaceDraft, systemImage: "mappin.and.ellipse", isEditing: isEditing)
                        DNAEditableListField(title: "爱好", values: $hobbies, draft: $hobbyDraft, systemImage: "sun.max", isEditing: isEditing)
                    }
                    .padding(DesignTokens.pagePadding)
                }
            } else {
                EmptyStateView(
                    title: "DNA 暂未同步",
                    detail: "通讯器还没有读到 TA 的完整偏好。",
                    systemImage: "slider.horizontal.3"
                )
            }
        }
        .navigationTitle("通讯 DNA")
        .navigationBarTitleDisplayMode(.inline)
        .onChange(of: dna) { _, nextDNA in
            if let nextDNA, !isEditing {
                resetDraft(from: nextDNA)
            }
        }
    }

    func resetDraft(from dna: PetDNA) {
        ownerTitle = dna.ownerTitle
        personality = dna.personality
        catchphrase = dna.catchphrase
        voiceStyle = dna.voiceStyle
        emojiPreference = dna.emojiPreference
        favoritePlaces = dna.favoritePlaces
        hobbies = dna.hobbies
        favoritePlaceDraft = ""
        hobbyDraft = ""
    }
}

struct DNAEditableField: View {
    var title: String
    @Binding var value: String
    var systemImage: String
    var isEditing: Bool
    var minHeight: CGFloat = 0

    var body: some View {
        SoftCard {
            Label(title, systemImage: systemImage)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(DesignTokens.secondaryInk)

            if isEditing {
                TextField(title, text: $value, axis: .vertical)
                    .font(.body.weight(.medium))
                    .foregroundStyle(DesignTokens.ink)
                    .lineLimit(1...4)
                    .padding(10)
                    .frame(minHeight: minHeight, alignment: .topLeading)
                    .background(DesignTokens.mist.opacity(0.72))
                    .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
            } else {
                Text(value)
                    .font(.body.weight(.medium))
                    .foregroundStyle(DesignTokens.ink)
                    .frame(maxWidth: .infinity, minHeight: minHeight, alignment: .leading)
            }
        }
    }
}

struct DNAEditableListField: View {
    var title: String
    @Binding var values: [String]
    @Binding var draft: String
    var systemImage: String
    var isEditing: Bool

    var body: some View {
        SoftCard {
            Label(title, systemImage: systemImage)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(DesignTokens.secondaryInk)

            LazyVGrid(columns: [GridItem(.adaptive(minimum: 88), spacing: 8)], alignment: .leading, spacing: 8) {
                ForEach(values.indices, id: \.self) { index in
                    HStack(spacing: 6) {
                        Text(values[index])
                            .font(.subheadline.weight(.medium))
                            .foregroundStyle(DesignTokens.ink)
                            .lineLimit(1)
                        if isEditing {
                            Button {
                                values.remove(at: index)
                            } label: {
                                Image(systemName: "xmark")
                                    .font(.caption2.weight(.bold))
                            }
                            .buttonStyle(.plain)
                            .foregroundStyle(DesignTokens.secondaryInk)
                        }
                    }
                    .padding(.vertical, 8)
                    .padding(.horizontal, 10)
                    .background(DesignTokens.mist)
                    .clipShape(Capsule())
                }
            }

            if isEditing {
                HStack(spacing: 8) {
                    TextField("新增\(title)", text: $draft)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .font(.subheadline)
                        .padding(10)
                        .background(DesignTokens.mist.opacity(0.72))
                        .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
                        .onSubmit(addDraft)

                    Button(action: addDraft) {
                        Image(systemName: "plus")
                            .frame(width: 36, height: 36)
                    }
                    .buttonStyle(.plain)
                    .foregroundStyle(.white)
                    .background(draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? DesignTokens.secondaryInk.opacity(0.28) : DesignTokens.sage)
                    .clipShape(Circle())
                    .disabled(draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                }
            }
        }
    }

    func addDraft() {
        let item = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !item.isEmpty else { return }
        if !values.contains(item) {
            values.append(item)
        }
        draft = ""
    }
}

struct PetGuideSummaryCard: View {
    var guide: PetAuthoredGuide

    var body: some View {
        SoftCard {
            Label("TA 的小想法", systemImage: "sparkles")
                .font(.caption.weight(.bold))
                .foregroundStyle(DesignTokens.clay)

            Text(guide.title)
                .font(.title3.weight(.semibold))
                .foregroundStyle(DesignTokens.ink)

            Text(guide.animalText.petSoulUserFacingText)
                .font(.headline.weight(.semibold))
                .foregroundStyle(DesignTokens.ink)

            Text(guide.translation.petSoulPetVoiceText)
                .font(.subheadline)
                .foregroundStyle(DesignTokens.secondaryInk)
                .lineSpacing(3)

            ForEach(guide.guideStops) { stop in
                VStack(alignment: .leading, spacing: 5) {
                    HStack(alignment: .firstTextBaseline, spacing: 8) {
                        Text(stop.plannedTime ?? "--:--")
                            .font(.caption.weight(.bold))
                            .foregroundStyle(DesignTokens.dusk)
                        Text(stop.name)
                            .font(.subheadline.weight(.semibold))
                            .foregroundStyle(DesignTokens.ink)
                            .lineLimit(1)
                        Spacer(minLength: 0)
                        Label("\(stop.dwellMinutes) 分钟", systemImage: "hourglass")
                            .font(.caption2.weight(.semibold))
                            .foregroundStyle(DesignTokens.secondaryInk)
                    }
                    Text(stop.petReason.petSoulPetVoiceText)
                        .font(.footnote)
                        .foregroundStyle(DesignTokens.secondaryInk)
                        .lineLimit(3)
                }
                .padding(.vertical, 8)
                .padding(.horizontal, 10)
                .background(DesignTokens.surface.opacity(0.52))
                .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
            }
        }
    }
}

struct GuideInfoChip: View {
    var title: String
    var value: String
    var systemImage: String

    var body: some View {
        HStack(spacing: 6) {
            Image(systemName: systemImage)
                .font(.caption.weight(.semibold))
                .foregroundStyle(DesignTokens.sage)
            VStack(alignment: .leading, spacing: 1) {
                Text(title)
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(DesignTokens.secondaryInk)
                Text(value)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(DesignTokens.ink)
                    .lineLimit(2)
                    .minimumScaleFactor(0.78)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.vertical, 8)
        .padding(.horizontal, 9)
        .background(DesignTokens.surface.opacity(0.66))
        .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
    }
}

struct DNAField: View {
    var title: String
    var value: String
    var systemImage: String

    var body: some View {
        SoftCard {
            Label(title, systemImage: systemImage)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(DesignTokens.secondaryInk)
            Text(value)
                .font(.body.weight(.medium))
                .foregroundStyle(DesignTokens.ink)
        }
    }
}

struct DNAListField: View {
    var title: String
    var values: [String]
    var systemImage: String

    var body: some View {
        SoftCard {
            Label(title, systemImage: systemImage)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(DesignTokens.secondaryInk)

            LazyVGrid(columns: [GridItem(.adaptive(minimum: 88), spacing: 8)], alignment: .leading, spacing: 8) {
                ForEach(values, id: \.self) { value in
                    Text(value)
                        .font(.subheadline.weight(.medium))
                        .foregroundStyle(DesignTokens.ink)
                        .padding(.vertical, 8)
                        .padding(.horizontal, 10)
                        .background(DesignTokens.mist)
                        .clipShape(Capsule())
                }
            }
        }
    }
}
