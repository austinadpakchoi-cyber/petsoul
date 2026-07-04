import Foundation

struct OnboardingDraft: Equatable, Sendable {
    var name: String
    var petType: PetType
    var photoData: Data?
    var ownerTitle: String
    var personality: String
    var favoritePlaces: [String]
    var catchphrase: String

    var dna: PetDNA {
        PetDNA(
            ownerTitle: ownerTitle,
            personality: personality,
            favoritePlaces: favoritePlaces,
            hobbies: ["散步", "晒太阳"],
            catchphrase: catchphrase.isEmpty ? "我在路上，也在想你" : catchphrase,
            emojiPreference: "soft",
            voiceStyle: "轻轻的、像寄信"
        )
    }

    var createRequest: CreatePetRequest {
        CreatePetRequest(
            name: name,
            petType: petType,
            photoData: photoData,
            photoFilename: photoData == nil ? nil : "pet-photo.jpg",
            dna: dna
        )
    }
}

@MainActor
final class OnboardingViewModel: ObservableObject {
    let ownerTitleSuggestions = ["妈妈", "爸爸", "主人", "姐姐", "哥哥", "铲屎官"]
    let personalitySuggestions = [
        "很黏人，会等我回家",
        "胆子小，但特别温柔",
        "爱玩，也爱撒娇",
        "安静，喜欢待在我身边"
    ]
    let placeSuggestions = ["海边", "草地", "家门口", "阳台", "床边", "常去的小路"]

    @Published var name = ""
    @Published var petType: PetType = .dog
    @Published var selectedPhotoData: Data?
    @Published var ownerTitle = ""
    @Published var personalityDescription = ""
    @Published var favoritePlacesText = ""
    @Published var catchphrase = ""

    var hasPhoto: Bool {
        selectedPhotoData != nil
    }

    var canContinueIdentity: Bool {
        !name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty &&
        !ownerTitle.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    var canContinue: Bool {
        canContinueIdentity &&
        !personalityDescription.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    var draft: OnboardingDraft? {
        let cleanName = name.trimmingCharacters(in: .whitespacesAndNewlines)
        let cleanOwnerTitle = ownerTitle.trimmingCharacters(in: .whitespacesAndNewlines)
        let cleanPersonality = personalityDescription.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !cleanName.isEmpty, !cleanOwnerTitle.isEmpty, !cleanPersonality.isEmpty else { return nil }

        return OnboardingDraft(
            name: cleanName,
            petType: petType,
            photoData: selectedPhotoData,
            ownerTitle: cleanOwnerTitle,
            personality: cleanPersonality,
            favoritePlaces: parsedFavoritePlaces,
            catchphrase: catchphrase.trimmingCharacters(in: .whitespacesAndNewlines)
        )
    }

    func useOwnerTitleSuggestion(_ suggestion: String) {
        ownerTitle = suggestion
    }

    func usePersonalitySuggestion(_ suggestion: String) {
        personalityDescription = suggestion
    }

    func addPlaceSuggestion(_ suggestion: String) {
        let clean = favoritePlacesText.trimmingCharacters(in: .whitespacesAndNewlines)
        if clean.isEmpty {
            favoritePlacesText = suggestion
        } else if !clean.contains(suggestion) {
            favoritePlacesText = "\(clean)、\(suggestion)"
        }
    }

    private var parsedFavoritePlaces: [String] {
        let separators = CharacterSet(charactersIn: "、,，\n")
        let values = favoritePlacesText
            .components(separatedBy: separators)
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
        return values.isEmpty ? ["家附近"] : values
    }
}
