import SwiftUI
import UIKit

enum PetSoulAsset: String {
    case signalPaw = "PetSoulSignalPaw"
    case postcardMemory = "PetSoulPostcardMemory"
    case travelMap = "PetSoulTravelMap"
    case cameraMission = "PetSoulCameraMission"
    case travelBag = "PetSoulTravelBag"
    case carRide = "PetSoulCarRide"
    case busRide = "PetSoulBusRide"
    case trainRide = "PetSoulTrainRide"
    case flight = "PetSoulFlight"
    case ferryRide = "PetSoulFerryRide"
    case walkPaws = "PetSoulWalkPaws"
    case stayPin = "PetSoulStayPin"
    case communicator = "PetSoulCommunicator"
    case messageBubble = "PetSoulMessageBubble"
    case moments = "PetSoulMoments"
    case memoryTray = "PetSoulMemoryTray"
    case souvenirGift = "PetSoulSouvenirGift"
    case snack = "PetSoulSnack"
    case luckyCharm = "PetSoulLuckyCharm"
    case musicNote = "PetSoulMusicNote"
    case worldCupPawPass = "PetSoulWorldCupPawPass"
    case worldCupFootball = "PetSoulWorldCupFootball"
    case worldCupTicket = "PetSoulWorldCupTicket"
    case worldCupScarf = "PetSoulWorldCupScarf"
    case worldCupFlag = "PetSoulWorldCupFlag"
    case worldCupAccessPass = "PetSoulWorldCupAccessPass"
    case worldCupSuitcase = "PetSoulWorldCupSuitcase"
    case worldCupBoardingPass = "PetSoulWorldCupBoardingPass"
    case worldCupStadiumLights = "PetSoulWorldCupStadiumLights"
    case worldCupMedal = "PetSoulWorldCupMedal"
    case worldCupWhistle = "PetSoulWorldCupWhistle"
    case worldCupFoamFinger = "PetSoulWorldCupFoamFinger"
    case worldCupSnacks = "PetSoulWorldCupSnacks"
    case worldCupCamera = "PetSoulWorldCupCamera"
    case worldCupGlobeBall = "PetSoulWorldCupGlobeBall"
    case worldCupPawTicket = "PetSoulWorldCupPawTicket"
    case worldCupBackpack = "PetSoulWorldCupBackpack"
    case worldCupShoppingBag = "PetSoulWorldCupShoppingBag"
    case worldCupBanner = "PetSoulWorldCupBanner"
    case worldCupConfettiBall = "PetSoulWorldCupConfettiBall"
    case travelPropFoldedMap = "PetSoulTravelPropFoldedMap"
    case travelPropCompass = "PetSoulTravelPropCompass"
    case travelPropWaterBottle = "PetSoulTravelPropWaterBottle"
    case travelPropUmbrella = "PetSoulTravelPropUmbrella"
    case travelPropBackpack = "PetSoulTravelPropBackpack"
    case travelPropHotelKeyCard = "PetSoulTravelPropHotelKeyCard"
    case travelPropBlanket = "PetSoulTravelPropBlanket"
    case travelPropInstantCamera = "PetSoulTravelPropInstantCamera"
    case travelPropSeashell = "PetSoulTravelPropSeashell"
    case travelPropPinwheel = "PetSoulTravelPropPinwheel"
    case travelPropPaperBag = "PetSoulTravelPropPaperBag"
    case travelPropWovenBasket = "PetSoulTravelPropWovenBasket"
    case travelPropPaperFan = "PetSoulTravelPropPaperFan"
    case travelPropLantern = "PetSoulTravelPropLantern"
    case travelPropCoffeeCup = "PetSoulTravelPropCoffeeCup"
    case travelPropDessertPlate = "PetSoulTravelPropDessertPlate"
    case travelPropLeaf = "PetSoulTravelPropLeaf"
    case travelPropPinecone = "PetSoulTravelPropPinecone"
    case travelPropBinoculars = "PetSoulTravelPropBinoculars"
    case travelPropPostcard = "PetSoulTravelPropPostcard"
    case travelPropStamp = "PetSoulTravelPropStamp"
    case travelPropBell = "PetSoulTravelPropBell"
    case travelPropPetScarf = "PetSoulTravelPropPetScarf"
    case travelPropPhotoCharm = "PetSoulTravelPropPhotoCharm"

    var fallbackSystemImage: String {
        switch self {
        case .signalPaw:
            "pawprint.fill"
        case .postcardMemory:
            "mail.stack"
        case .travelMap:
            "map.fill"
        case .cameraMission:
            "camera.fill"
        case .travelBag:
            "backpack.fill"
        case .carRide:
            "car.fill"
        case .busRide:
            "bus.fill"
        case .trainRide:
            "tram.fill"
        case .flight:
            "airplane"
        case .ferryRide:
            "ferry.fill"
        case .walkPaws:
            "pawprint.fill"
        case .stayPin:
            "mappin.and.ellipse"
        case .communicator:
            "antenna.radiowaves.left.and.right"
        case .messageBubble:
            "bubble.left.and.text.bubble.right.fill"
        case .moments:
            "sparkles"
        case .memoryTray:
            "tray.full.fill"
        case .souvenirGift:
            "gift.fill"
        case .snack:
            "takeoutbag.and.cup.and.straw.fill"
        case .luckyCharm:
            "sparkles"
        case .musicNote:
            "headphones"
        case .worldCupPawPass:
            "pawprint.fill"
        case .worldCupFootball, .worldCupConfettiBall:
            "soccerball"
        case .worldCupTicket, .worldCupPawTicket:
            "ticket.fill"
        case .worldCupScarf:
            "scarf.fill"
        case .worldCupFlag:
            "flag.fill"
        case .worldCupAccessPass:
            "lanyardcard.fill"
        case .worldCupSuitcase:
            "suitcase.fill"
        case .worldCupBoardingPass:
            "airplane"
        case .worldCupStadiumLights:
            "sportscourt.fill"
        case .worldCupMedal:
            "medal.fill"
        case .worldCupWhistle:
            "whistle.fill"
        case .worldCupFoamFinger:
            "hand.point.up.left.fill"
        case .worldCupSnacks:
            "takeoutbag.and.cup.and.straw.fill"
        case .worldCupCamera:
            "camera.fill"
        case .worldCupGlobeBall:
            "globe.americas.fill"
        case .worldCupBackpack:
            "backpack.fill"
        case .worldCupShoppingBag:
            "bag.fill"
        case .worldCupBanner:
            "flag.2.crossed.fill"
        case .travelPropFoldedMap:
            "map.fill"
        case .travelPropCompass:
            "safari.fill"
        case .travelPropWaterBottle:
            "waterbottle.fill"
        case .travelPropUmbrella:
            "umbrella.fill"
        case .travelPropBackpack:
            "backpack.fill"
        case .travelPropHotelKeyCard:
            "keycard.fill"
        case .travelPropBlanket:
            "rectangle.compress.vertical"
        case .travelPropInstantCamera:
            "camera.fill"
        case .travelPropSeashell:
            "fossil.shell.fill"
        case .travelPropPinwheel:
            "fan.fill"
        case .travelPropPaperBag:
            "takeoutbag.and.cup.and.straw.fill"
        case .travelPropWovenBasket:
            "basket.fill"
        case .travelPropPaperFan:
            "fan.fill"
        case .travelPropLantern:
            "lightbulb.fill"
        case .travelPropCoffeeCup:
            "cup.and.saucer.fill"
        case .travelPropDessertPlate:
            "birthday.cake.fill"
        case .travelPropLeaf:
            "leaf.fill"
        case .travelPropPinecone:
            "tree.fill"
        case .travelPropBinoculars:
            "binoculars.fill"
        case .travelPropPostcard:
            "mail.fill"
        case .travelPropStamp:
            "seal.fill"
        case .travelPropBell:
            "bell.fill"
        case .travelPropPetScarf:
            "scarf.fill"
        case .travelPropPhotoCharm:
            "photo.fill"
        }
    }

    static func from(systemImage: String) -> PetSoulAsset? {
        switch systemImage {
        case "dot.radiowaves.left.and.right", "sparkles":
            .signalPaw
        case "mail", "mail.fill", "mail.stack", "mail.stack.fill", "heart.text.square", "heart.text.square.fill":
            .postcardMemory
        case "map", "map.fill":
            .travelMap
        case "camera.fill", "camera.viewfinder", "camera.macro", "camera.metering.none", "photo", "photo.fill":
            .cameraMission
        case "backpack.fill", "bag.fill":
            .travelBag
        case "car.fill":
            .carRide
        case "bus.fill":
            .busRide
        case "tram.fill", "train.side.front.car":
            .trainRide
        case "airplane":
            .flight
        case "ferry.fill", "sailboat.fill", "water.waves":
            .ferryRide
        case "pawprint.fill":
            .walkPaws
        case "mappin.and.ellipse", "location.fill":
            .stayPin
        case "antenna.radiowaves.left.and.right", "rectangle.connected.to.line.below":
            .communicator
        case "bubble.left.and.text.bubble.right", "bubble.left.and.text.bubble.right.fill", "text.bubble", "text.bubble.fill":
            .messageBubble
        case "tray.full.fill":
            .memoryTray
        case "gift", "gift.fill", "sparkles.square.filled.on.square":
            .souvenirGift
        case "takeoutbag.and.cup.and.straw", "takeoutbag.and.cup.and.straw.fill":
            .snack
        case "headphones":
            .musicNote
        case "seal.fill":
            .luckyCharm
        case "ticket.fill":
            .worldCupTicket
        case "photo.on.rectangle.angled":
            .postcardMemory
        case "soccerball":
            .worldCupFootball
        case "sportscourt.fill":
            .worldCupStadiumLights
        case "flag.fill":
            .worldCupFlag
        case "scarf.fill":
            .worldCupScarf
        case "lanyardcard.fill":
            .worldCupAccessPass
        case "suitcase.fill":
            .worldCupSuitcase
        case "medal.fill":
            .worldCupMedal
        case "whistle.fill":
            .worldCupWhistle
        case "hand.point.up.left.fill":
            .worldCupFoamFinger
        case "globe.americas.fill":
            .worldCupGlobeBall
        case "flag.2.crossed.fill":
            .worldCupBanner
        case "umbrella", "umbrella.fill":
            .travelPropUmbrella
        case "waterbottle", "waterbottle.fill":
            .travelPropWaterBottle
        case "keycard", "keycard.fill":
            .travelPropHotelKeyCard
        case "basket", "basket.fill":
            .travelPropWovenBasket
        case "binoculars", "binoculars.fill":
            .travelPropBinoculars
        case "bell", "bell.fill":
            .travelPropBell
        case "cup.and.saucer", "cup.and.saucer.fill":
            .travelPropCoffeeCup
        case "birthday.cake", "birthday.cake.fill":
            .travelPropDessertPlate
        case "leaf", "leaf.fill":
            .travelPropLeaf
        case "fan", "fan.fill":
            .travelPropPaperFan
        case "fossil.shell", "fossil.shell.fill":
            .travelPropSeashell
        default:
            nil
        }
    }
}

struct PetSoulAssetIcon: View {
    var asset: PetSoulAsset
    var fallbackSystemImage: String?
    var fallbackTint: Color = DesignTokens.sage
    var size: CGFloat

    var body: some View {
        if UIImage(named: asset.rawValue) != nil {
            Image(asset.rawValue)
                .resizable()
                .scaledToFit()
                .frame(width: size, height: size)
                .accessibilityHidden(true)
        } else {
            Image(systemName: fallbackSystemImage ?? asset.fallbackSystemImage)
                .font(.system(size: size * 0.58, weight: .semibold))
                .foregroundStyle(fallbackTint)
                .frame(width: size, height: size)
                .accessibilityHidden(true)
        }
    }
}

struct PetSoulAdaptiveIcon: View {
    var systemImage: String
    var tint: Color
    var size: CGFloat

    var body: some View {
        if let asset = PetSoulAsset.from(systemImage: systemImage) {
            PetSoulAssetIcon(
                asset: asset,
                fallbackSystemImage: systemImage,
                fallbackTint: tint,
                size: size
            )
        } else {
            Image(systemName: systemImage)
                .font(.system(size: size * 0.58, weight: .semibold))
                .foregroundStyle(tint)
                .frame(width: size, height: size)
                .accessibilityHidden(true)
        }
    }
}

struct PetSoulAssetLabel: View {
    var title: String
    var asset: PetSoulAsset
    var fallbackSystemImage: String?
    var tint: Color = DesignTokens.sage
    var iconSize: CGFloat = 24

    var body: some View {
        HStack(spacing: 8) {
            PetSoulAssetIcon(
                asset: asset,
                fallbackSystemImage: fallbackSystemImage,
                fallbackTint: tint,
                size: iconSize
            )
            Text(title)
        }
        .lineLimit(1)
        .minimumScaleFactor(0.78)
    }
}
