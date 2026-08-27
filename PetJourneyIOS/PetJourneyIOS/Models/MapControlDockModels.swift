import SwiftUI

/// 控制坞的动作集合，让 MapControlDock 与地图页解耦。
struct MapDockActions {
    var onCenter: () -> Void = {}
    var onTogglePerspective: () -> Void = {}
    var onToggleNearbySignals: () -> Void = {}
    var onShowDayPlan: () -> Void = {}
    var onShowRecap: () -> Void = {}
    var onShowPostcards: () -> Void = {}
    var onShowTravelKit: () -> Void = {}
    var onShowSouvenirs: () -> Void = {}
    var onShowStreetRank: () -> Void = {}
    var onShowDNA: () -> Void = {}
    var onShowAccount: () -> Void = {}
    var onReset: () -> Void = {}
}
