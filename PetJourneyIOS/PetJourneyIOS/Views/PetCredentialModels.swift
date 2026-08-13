import PhotosUI
import SwiftUI
import UIKit

enum PetCredentialCategory: String, CaseIterable, Identifiable {
    case documents
    case travel

    var id: String { rawValue }

    var title: String {
        switch self {
        case .documents: "基础证件"
        case .travel: "旅行票据"
        }
    }

    var subtitle: String {
        switch self {
        case .documents: "身份卡、护照、健康证和爪爪驾驶证"
        case .travel: "长途路上和入住休息时生成"
        }
    }
}

enum PetCredentialPhotoRole: String, CaseIterable, Identifiable {
    case officialIDPortrait
    case realPortrait

    var id: String { rawValue }

    var title: String {
        switch self {
        case .officialIDPortrait: "电子证件照"
        case .realPortrait: "原始照片"
        }
    }

    var subtitle: String {
        switch self {
        case .officialIDPortrait: "护照规范生成"
        case .realPortrait: "生活原图保存"
        }
    }

    var systemImage: String {
        switch self {
        case .officialIDPortrait: "person.crop.square.fill"
        case .realPortrait: "camera.fill"
        }
    }
}

enum PetCredentialKind: String, CaseIterable, Identifiable {
    case identity
    case passport
    case healthRecord
    case driverLicense
    case boardingPass
    case hotelKey

    var id: String { rawValue }

    var title: String {
        switch self {
        case .identity: "Pet ID"
        case .passport: "Companion Passport"
        case .healthRecord: "Health Record"
        case .driverLicense: "Paw Driver License"
        case .boardingPass: "Boarding Pass"
        case .hotelKey: "Hotel Key Card"
        }
    }

    var subtitle: String {
        switch self {
        case .identity: "宠物身份卡"
        case .passport: "宠物旅伴护照"
        case .healthRecord: "健康证 / 疫苗本"
        case .driverLicense: "爪爪驾驶证"
        case .boardingPass: "登机牌"
        case .hotelKey: "酒店房卡"
        }
    }

    var systemImage: String {
        switch self {
        case .identity: "person.text.rectangle.fill"
        case .passport: "book.closed.fill"
        case .healthRecord: "heart.text.square.fill"
        case .driverLicense: "car.fill"
        case .boardingPass: "airplane.departure"
        case .hotelKey: "key.fill"
        }
    }

    // 这些内置素材只是证件卡面的风格示例,
    // 不允许作为任何宠物的卡面/照片直接展示在 UI 上。
    var promptExampleImageName: String {
        switch self {
        case .identity: "PetCredentialDogIdentity"
        case .passport: "PetCredentialDogPassport"
        case .healthRecord: "PetCredentialDogHealthRecord"
        case .driverLicense: "PetCredentialDogDriverLicense"
        case .boardingPass: "PetCredentialDogBoardingPass"
        case .hotelKey: "PetCredentialDogHotelKey"
        }
    }

    var documentAspectRatio: CGFloat {
        switch self {
        case .passport:
            1448.0 / 1086.0
        default:
            1536.0 / 1024.0
        }
    }

    var tint: Color {
        switch self {
        case .identity: DesignTokens.sage
        case .passport: DesignTokens.dusk
        case .healthRecord: DesignTokens.sea
        case .driverLicense: DesignTokens.amber
        case .boardingPass: DesignTokens.dusk
        case .hotelKey: DesignTokens.clay
        }
    }

    var category: PetCredentialCategory {
        switch self {
        case .identity, .passport, .healthRecord, .driverLicense:
            .documents
        case .boardingPass, .hotelKey:
            .travel
        }
    }

    var rarity: String {
        switch self {
        case .identity: "ID"
        case .passport, .boardingPass, .hotelKey: "Travel"
        case .healthRecord: "Care"
        case .driverLicense: "Fun"
        }
    }

    var gradientColors: [Color] {
        switch self {
        case .identity:
            [DesignTokens.credential.identityDeep, DesignTokens.credential.identityLight]
        case .passport:
            [DesignTokens.credential.passportDeep, DesignTokens.credential.passportLight]
        case .healthRecord:
            [DesignTokens.credential.healthDeep, DesignTokens.credential.healthLight]
        case .driverLicense:
            [DesignTokens.credential.driverDeep, DesignTokens.credential.driverLight]
        case .boardingPass:
            [DesignTokens.credential.boardingDeep, DesignTokens.credential.boardingLight]
        case .hotelKey:
            [DesignTokens.credential.hotelDeep, DesignTokens.credential.hotelLight]
        }
    }

    var note: String {
        switch self {
        case .identity:
            "PetSoul 世界里的宠物身份 ID，只记录用户 DNA 和星球档案。"
        case .passport:
            "宠物旅行与身份记录的主证件，是平行世界纪念护照。"
        case .healthRecord:
            "PetSoul 温柔照护档案，记录星球护理和安抚备注。"
        case .driverLicense:
            "趣味爪爪驾驶证，只允许云朵慢行、看风景优先。"
        case .boardingPass:
            "长途故事展开时生成的 PetSoul 平行航线票据。"
        case .hotelKey:
            "休息片段出现时生成的平行房卡，记录 TA 的生活感。"
        }
    }
}

struct PetSoulCredentialProfile {
    let petID: String
    let name: String
    let petType: PetType
    let dna: PetDNA

    var archiveName: String {
        "SOUL-\(String(petID.suffix(4)).uppercased())"
    }

    var speciesLine: String {
        "\(petType.displayName) · 星球显形态"
    }

    var originWorld: String {
        "\(petType.searchWorldName) / \(pick(from: Self.originWorldAliases, salt: 3))"
    }

    var reappearancePlace: String {
        pick(from: [
            "彩虹桥东侧",
            "晨雾草地",
            "云边窗台",
            "软风小站",
            "月光口袋",
            "回声花园"
        ], salt: 7)
    }

    var reappearanceDate: String {
        let month = 1 + seed(salt: 11) % 12
        let day = 1 + seed(salt: 19) % 28
        return "2021-\(String(format: "%02d", month))-\(String(format: "%02d", day))"
    }

    var favoritePlace: String {
        clean(dna.favoritePlaces.first) ?? pick(from: ["窗边", "草地", "安静小店", "有风的地方"], salt: 23)
    }

    var hobby: String {
        clean(dna.hobbies.first) ?? pick(from: ["晒太阳", "慢慢走", "看云", "听人说话"], salt: 29)
    }

    var careDesk: String {
        pick(from: ["软光照护站", "星尘护理室", "云边小诊台", "彩虹桥照护所"], salt: 31)
    }

    var careStatus: String {
        pick(from: ["状态稳定，适合慢慢生活", "精神柔软，适合安静陪伴", "已归档，等待下一次晒太阳"], salt: 37)
    }

    var careRitual: String {
        "\(hobby) / 轻轻梳理 / 听见\(dna.ownerTitle.isEmpty ? "守护人" : dna.ownerTitle)的声音"
    }

    var transitDesk: String {
        pick(from: ["云朵慢行所", "窗边交通桌", "软风车站", "小爪车管室"], salt: 41)
    }

    var ridePreference: String {
        pick(from: ["靠窗慢行", "不赶路，只看风景", "先确认声音，再出发", "坐稳再靠近光"], salt: 43)
    }

    var softDestination: String {
        pick(from: ["下一束暖光", "安静窗边座", "软草地停靠点", "小太阳登机口", "陪伴云层"], salt: 47)
    }

    var cloudGate: String {
        "Cloud \(1 + seed(salt: 53) % 9)"
    }

    var softLodging: String {
        pick(from: ["软毯小旅店", "窗光休息所", "小爪夜宿处", "彩虹午睡房", "云枕房"], salt: 59)
    }

    static let originWorldAliases = [
        "Pawland",
        "Moonburrow",
        "Softpaw",
        "Chirpland",
        "Companionland",
        "Rainbow Field"
    ]

    func pick(from values: [String], salt: Int) -> String {
        values[seed(salt: salt) % max(values.count, 1)]
    }

    func clean(_ value: String?) -> String? {
        let trimmed = (value ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
    }

    func seed(salt: Int) -> Int {
        let text = "\(petID)|\(name)|\(petType.rawValue)|\(dna.personality)|\(salt)"
        return text.unicodeScalars.reduce(0) { partial, scalar in
            (partial &* 31 &+ Int(scalar.value)) & 0x7fffffff
        }
    }
}

struct PetCredentialSnapshot {
    var kind: PetCredentialKind
    var serial: String
    var holderName: String
    var species: String
    var originWorld: String
    var currentLocation: String
    var issuePlace: String
    var issueDate: String
    var statusLine: String
    var fields: [(String, String)]
    var stamps: [String]
    var isActive: Bool
    var isUnlocked: Bool = true
    var unlockHint: String = "已解锁"
    var requirementNote: String
    var petID: String = ""
    var petType: PetType = .other

    var detailDescription: String {
        kind.note
    }

    var cardDisplayFields: [(String, String)] {
        switch kind {
        case .identity:
            [
                ("Name", holderName),
                ("Species", species),
                ("ID No.", serial)
            ]
        case .passport:
            [
                ("Holder", holderName),
                ("Passport", serial),
                ("Status", isActive ? "跨境启用" : "国内暂不需要")
            ]
        case .healthRecord:
            [
                ("Name", holderName),
                ("Health", value(for: "健康状态") ?? "稳定"),
                ("Vaccine", value(for: "疫苗记录") ?? value(for: "疫苗状态") ?? "已记录")
            ]
        case .driverLicense:
            [
                ("Holder", holderName),
                ("Class", value(for: "准驾类型") ?? "慢行小车"),
                ("Style", value(for: "驾驶风格") ?? "看风景优先")
            ]
        case .boardingPass:
            [
                ("Passenger", holderName),
                ("From", value(for: "From") ?? "同步中"),
                ("To", value(for: "To") ?? currentLocation)
            ]
        case .hotelKey:
            [
                ("Guest", holderName),
                ("City", value(for: "City") ?? currentLocation),
                ("Room", value(for: "Room") ?? serial)
            ]
        }
    }

    var keyDetailFields: [(String, String)] {
        switch kind {
        case .healthRecord:
            [
                ("健康状态", value(for: "健康状态") ?? "稳定"),
                ("疫苗记录", value(for: "疫苗记录") ?? "已记录"),
                ("最近护理", value(for: "最近护理") ?? "梳毛 / 晒太阳")
            ]
        case .driverLicense:
            [
                ("准驾类型", value(for: "准驾类型") ?? "慢行小车"),
                ("驾驶风格", value(for: "驾驶风格") ?? "看风景优先"),
                ("状态", statusLine)
            ]
        default:
            Array(fields.prefix(3))
        }
    }

    var basicInfoFields: [(String, String)] {
        fields.filter { field in
            !["健康状态", "疫苗记录", "疫苗状态", "最近护理", "照护备注", "备注"].contains(field.0)
        }
    }

    var careNote: String? {
        value(for: "照护备注") ?? value(for: "备注")
    }

    var safetyLine: String {
        "这是 PetSoul 世界里的宠物旅伴证件，不代表任何现实法律或医疗证件。"
    }

    var shareText: String {
        "\(holderName) 的 \(kind.subtitle) · \(serial)\n\(safetyLine)"
    }

    func value(for title: String) -> String? {
        fields.first { $0.0 == title }?.1
    }

    static func all(status: AgentStatus?, dna: PetDNA?, souvenirCount: Int, travelQuests: [TravelQuest]) -> [PetCredentialSnapshot] {
        PetCredentialKind.allCases.map {
            snapshot(kind: $0, status: status, dna: dna, souvenirCount: souvenirCount, travelQuests: travelQuests)
        }
    }

    static func snapshot(
        kind: PetCredentialKind,
        status: AgentStatus?,
        dna: PetDNA?,
        souvenirCount: Int,
        travelQuests: [TravelQuest]
    ) -> PetCredentialSnapshot {
        let petID = status?.petID ?? "PET-SOUL"
        let shortID = String(petID.suffix(6)).uppercased()
        let name = status?.name ?? "TA"
        let petType = status?.petType ?? .dog
        let trustedDNA = dna ?? .fallback
        let profile = PetSoulCredentialProfile(petID: petID, name: name, petType: petType, dna: trustedDNA)
        let location = profile.reappearancePlace
        let issueDate = Date().formatted(.dateTime.year().month(.twoDigits).day(.twoDigits))
        let activeQuest = travelQuests.first { !isClosedQuest($0.status) } ?? travelQuests.first
        let hasBoardingMoment = activeQuest.map { isBoardingStatus($0.status) || isBoardingStatus($0.currentPhase) } ?? false
        let passportActive = activeQuest.map { quest in
            let questText = [
                quest.destination,
                quest.eventName ?? "",
                quest.ownerMessage,
                quest.currentPhaseMessage
            ].joined(separator: " ")
            return quest.worldcupEvent || isInternationalText(questText)
        } ?? false
        let favoritePlace = profile.favoritePlace
        let hobby = profile.hobby
        let latinName = profile.archiveName
        let birthday = profile.reappearanceDate
        let guardian = trustedDNA.ownerTitle.isEmpty ? "守护人" : trustedDNA.ownerTitle
        let isCheckedIn = status.map { isHotelStatus($0.agentState.status) || isHotelStatus($0.status) } ?? false

        var snapshot: PetCredentialSnapshot
        switch kind {
        case .identity:
            snapshot = PetCredentialSnapshot(
                kind: kind,
                serial: "PJ-ID-\(shortID)",
                holderName: name,
                species: profile.speciesLine,
                originWorld: profile.originWorld,
                currentLocation: location,
                issuePlace: "PetSoul Identity Desk",
                issueDate: issueDate,
                statusLine: "星球身份档案已归档",
                fields: [
                    ("姓名", "\(name) / \(latinName)"),
                    ("物种", petType.displayName),
                    ("显形态", profile.speciesLine),
                    ("初现日", birthday),
                    ("身份编号", "PS-\(shortID)"),
                    ("故乡星球", profile.originWorld),
                    ("初现地点", profile.reappearancePlace),
                    ("性格 DNA", trustedDNA.personality),
                    ("喜欢的地方", favoritePlace),
                    ("守护人", guardian)
                ],
                stamps: ["Identity", "PetSoul", "照片归档"],
                isActive: true,
                requirementNote: "身份卡只记录用户给的 DNA 和 PetSoul 生成的星球档案，不同步真实地址。"
            )
        case .passport:
            snapshot = PetCredentialSnapshot(
                kind: kind,
                serial: "PJ-PASS-\(shortID)",
                holderName: name,
                species: profile.speciesLine,
                originWorld: profile.originWorld,
                currentLocation: location,
                issuePlace: "PetSoul Republic Desk",
                issueDate: issueDate,
                statusLine: passportActive ? "旅伴护照已随身归档" : "星球旅伴护照已归档",
                fields: [
                    ("姓名", "\(name) / \(latinName)"),
                    ("物种", petType.displayName),
                    ("显形态", profile.speciesLine),
                    ("出生日期", birthday),
                    ("护照编号", "PASS-\(shortID)"),
                    ("故乡星球", profile.originWorld),
                    ("初现地点", profile.reappearancePlace),
                    ("旅程状态", "平行世界纪念通行"),
                    ("适用场景", "灵魂旅伴 / 星球重现")
                ],
                stamps: passportActive ? ["旅伴", "随身", "待盖章"] : ["星球", "纪念", "已归档"],
                isActive: passportActive,
                isUnlocked: true,
                unlockHint: "纪念护照已归档",
                requirementNote: "护照是 PetSoul 世界的旅伴证件，不代表真实跨境或现实地址。"
            )
        case .healthRecord:
            snapshot = PetCredentialSnapshot(
                kind: kind,
                serial: "PJ-HEALTH-\(shortID)",
                holderName: name,
                species: profile.speciesLine,
                originWorld: "PetSoul Care Clinic",
                currentLocation: location,
                issuePlace: profile.careDesk,
                issueDate: issueDate,
                statusLine: "星球照护档案已记录",
                fields: [
                    ("姓名", name),
                    ("物种", petType.displayName),
                    ("显形态", profile.speciesLine),
                    ("初现日", birthday),
                    ("健康状态", profile.careStatus),
                    ("疫苗记录", "PetSoul 星尘印记已点亮"),
                    ("最近护理", profile.careRitual),
                    ("照护备注", "\(trustedDNA.personality)，喜欢\(favoritePlace)，安抚词：\(trustedDNA.catchphrase)")
                ],
                stamps: ["Health", "Care", "Soul"],
                isActive: true,
                requirementNote: "健康证是 PetSoul 生成的温柔照护档案，不代表真实医疗或疫苗记录。"
            )
        case .boardingPass:
            snapshot = PetCredentialSnapshot(
                kind: kind,
                serial: "PJ-AIR-\(shortID)",
                holderName: name,
                species: profile.speciesLine,
                originWorld: "PetSoul Airways",
                currentLocation: profile.softDestination,
                issuePlace: profile.cloudGate,
                issueDate: issueDate,
                statusLine: hasBoardingMoment ? "On the way · 平行航线" : "长途故事展开时生成",
                fields: [
                    ("From", profile.reappearancePlace),
                    ("To", profile.softDestination),
                    ("Passenger", latinName),
                    ("Flight", "PS-\(String(shortID.suffix(4)))"),
                    ("Seat", "PAW-\(String(shortID.suffix(2)))"),
                    ("Gate", profile.cloudGate),
                    ("Status", hasBoardingMoment ? "On the way" : "Waiting for story")
                ],
                stamps: hasBoardingMoment ? ["Boarding", "Window", "On Way"] : ["Locked", "Long Trip", "Later"],
                isActive: hasBoardingMoment,
                isUnlocked: hasBoardingMoment,
                unlockHint: "长途故事展开后生成平行航线票据",
                requirementNote: "登机牌是 PetSoul 旅行票据，不代表真实航班、机票或登机凭证。"
            )
        case .driverLicense:
            snapshot = PetCredentialSnapshot(
                kind: kind,
                serial: "PJ-DL-\(shortID)",
                holderName: name,
                species: profile.speciesLine,
                originWorld: "Parallel Transit",
                currentLocation: location,
                issuePlace: profile.transitDesk,
                issueDate: issueDate,
                statusLine: "慢慢开，看风景优先",
                fields: [
                    ("姓名", "\(name) / \(latinName)"),
                    ("准驾类型", "云朵慢行车"),
                    ("驾驶风格", "\(hobby)，看风景优先"),
                    ("签发日期", issueDate),
                    ("证件编号", "DL-\(shortID)"),
                    ("星球规则", "不控制真实路线"),
                    ("乘坐偏好", profile.ridePreference)
                ],
                stamps: ["乘车", "靠窗", "星球"],
                isActive: true,
                requirementNote: "驾驶证是 PetSoul 趣味证件，不使用真实交管样式，也不代表任何现实驾驶资格。"
            )
        case .hotelKey:
            snapshot = PetCredentialSnapshot(
                kind: kind,
                serial: "PJ-STAY-\(shortID)",
                holderName: name,
                species: profile.speciesLine,
                originWorld: "PetSoul Check-in",
                currentLocation: profile.softLodging,
                issuePlace: profile.softLodging,
                issueDate: issueDate,
                statusLine: isCheckedIn ? "已入住平行小房间" : "休息故事展开时生成",
                fields: [
                    ("Guest", latinName),
                    ("Stay", profile.softLodging),
                    ("Room", "SOUL-\(String(shortID.suffix(4)))"),
                    ("Check-in", issueDate),
                    ("Status", isCheckedIn ? "1 night" : "Waiting"),
                    ("Preference", "靠窗 / 安静 / \(favoritePlace)"),
                    ("Care Note", trustedDNA.catchphrase)
                ],
                stamps: isCheckedIn ? ["Check-in", "Window", "Quiet"] : ["Locked", "Rest", "Later"],
                isActive: isCheckedIn,
                isUnlocked: isCheckedIn,
                unlockHint: "休息片段出现后生成平行房卡",
                requirementNote: "酒店房卡记录 PetSoul 平行休息点，不代表真实住宿订单或现实地址。"
            )
        }
        snapshot.petID = petID
        snapshot.petType = petType
        return snapshot
    }

    static func isClosedQuest(_ status: TravelQuestStatus) -> Bool {
        switch status {
        case .declined, .completed, .returned, .continuedElsewhere:
            true
        default:
            false
        }
    }

    static func isBoardingStatus(_ status: TravelQuestStatus) -> Bool {
        switch status {
        case .outbound, .traveling, .returnTraveling:
            true
        default:
            false
        }
    }

    static func isHotelStatus(_ status: JourneyStatus) -> Bool {
        switch status {
        case .resting, .staying:
            true
        default:
            false
        }
    }

    static func isInternationalText(_ text: String) -> Bool {
        let markers = [
            "美国", "加拿大", "墨西哥", "洛杉矶", "西雅图", "纽约", "新泽西", "达拉斯",
            "迈阿密", "温哥华", "多伦多", "瓜达拉哈拉", "蒙特雷", "墨西哥城",
            "United States", "Canada", "Mexico", "Los Angeles", "Seattle", "New York"
        ]
        return markers.contains { text.localizedCaseInsensitiveContains($0) }
    }
}
