import CoreLocation
import Foundation

// MARK: - 账号与登录

struct AppleSignInRequest: Codable, Equatable, Sendable {
    var identityToken: String
    var displayName: String?

    enum CodingKeys: String, CodingKey {
        case identityToken = "identity_token"
        case displayName = "display_name"
    }
}

struct AuthPetSummary: Codable, Identifiable, Equatable, Sendable {
    var id: String { petID }

    var petID: String
    var name: String
    var petType: PetType
    var photoURL: URL?

    enum CodingKeys: String, CodingKey {
        case petID = "pet_id"
        case name
        case petType = "pet_type"
        case photoURL = "photo_url"
    }
}

struct AuthSessionResponse: Codable, Equatable, Sendable {
    var accessToken: String
    var userID: String
    var displayName: String?
    var isNewUser: Bool
    var pets: [AuthPetSummary]

    enum CodingKeys: String, CodingKey {
        case accessToken = "access_token"
        case userID = "user_id"
        case displayName = "display_name"
        case isNewUser = "is_new_user"
        case pets
    }
}

struct ClaimPetRequest: Codable, Equatable, Sendable {
    var petID: String

    enum CodingKeys: String, CodingKey {
        case petID = "pet_id"
    }
}

struct MeResponse: Codable, Equatable, Sendable {
    var userID: String
    var displayName: String?
    var email: String?
    var pets: [AuthPetSummary]

    enum CodingKeys: String, CodingKey {
        case userID = "user_id"
        case displayName = "display_name"
        case email
        case pets
    }
}
