import AuthenticationServices
import MapKit
import SwiftUI
import UIKit

struct DayRecapView: View {
    var status: AgentStatus
    var chapters: [DayRecapChapter]

    @Environment(\.dismiss) var dismiss
    @State var cameraPosition: MapCameraPosition
    @State var replayTime: Double = 0
    @State var isPaused = false
    @State var isFinished = false
    @State var cameraGlideTask: Task<Void, Never>?

    init(status: AgentStatus, chapters: [DayRecapChapter]) {
        self.status = status
        self.chapters = chapters
        let start = chapters.first?.coordinate ?? CityPosition.xiamen.coordinate
        _cameraPosition = State(initialValue: .camera(
            MapCamera(centerCoordinate: start, distance: 220_000, heading: 0, pitch: 0)
        ))
    }

    var totalDuration: Double {
        chapters.reduce(0) { $0 + $1.duration }
    }

    var currentIndex: Int {
        var cursor = 0.0
        for (index, chapter) in chapters.enumerated() {
            if replayTime < cursor + chapter.duration { return index }
            cursor += chapter.duration
        }
        return max(0, chapters.count - 1)
    }

    var currentChapter: DayRecapChapter? {
        chapters.indices.contains(currentIndex) ? chapters[currentIndex] : nil
    }

    var localProgress: Double {
        guard let chapter = currentChapter, chapter.duration > 0 else { return 0 }
        return min(1, max(0, (replayTime - chapterStart(currentIndex)) / chapter.duration))
    }

    var petPosition: CLLocationCoordinate2D {
        guard let chapter = currentChapter else {
            return chapters.first?.coordinate ?? CityPosition.xiamen.coordinate
        }
        switch chapter.kind {
        case .stay:
            return chapter.coordinate
        case .move:
            let eased = localProgress * localProgress * (3 - 2 * localProgress)
            return JourneyMotion.coordinate(on: chapter.route, progress: eased) ?? chapter.coordinate
        }
    }

    var traveledCoordinates: [CLLocationCoordinate2D] {
        var coordinates: [CLLocationCoordinate2D] = []
        for chapter in chapters.prefix(currentIndex) where chapter.kind == .move {
            coordinates.append(contentsOf: chapter.route)
        }
        if let chapter = currentChapter, chapter.kind == .move {
            coordinates.append(contentsOf: partialRoute(chapter.route, progress: localProgress))
        }
        return coordinates
    }

    var visitedStops: [DayRecapChapter] {
        chapters.prefix(currentIndex + 1).filter { $0.kind == .stay }
    }

    var body: some View {
        ZStack {
            if chapters.isEmpty {
                emptyState
            } else {
                Map(position: $cameraPosition, interactionModes: []) {
                    if traveledCoordinates.count > 1 {
                        MapPolyline(coordinates: traveledCoordinates)
                            .stroke(DesignTokens.surfaceStroke.opacity(0.66), style: StrokeStyle(lineWidth: 7, lineCap: .round, lineJoin: .round))
                        MapPolyline(coordinates: traveledCoordinates)
                            .stroke(DesignTokens.amber.opacity(0.85), style: StrokeStyle(lineWidth: 4, lineCap: .round, lineJoin: .round))
                    }

                    ForEach(visitedStops) { stop in
                        Annotation("", coordinate: stop.coordinate, anchor: .center) {
                            Image(systemName: stop.systemImage)
                                .font(.system(size: 10, weight: .bold))
                                .foregroundStyle(.white)
                                .frame(width: 24, height: 24)
                                .background(stop.tint)
                                .clipShape(Circle())
                                .overlay {
                                    Circle().stroke(DesignTokens.surfaceStroke.opacity(0.9), lineWidth: 1.5)
                                }
                                .shadow(color: DesignTokens.deepInk.opacity(0.18), radius: 6, x: 0, y: 3)
                        }
                    }

                    Annotation("", coordinate: petPosition, anchor: .center) {
                        RecapPetMarker(petID: status.petID, petType: status.petType ?? .dog)
                    }
                }
                .mapStyle(.standard(elevation: .realistic, pointsOfInterest: .excludingAll, showsTraffic: false))
                .ignoresSafeArea()

                JourneyMapAtmosphere(tint: currentChapter?.tint ?? DesignTokens.sage)

                overlayControls

                if isFinished {
                    endCard
                }
            }
        }
        .task { await runClock() }
        .onChange(of: currentIndex) { _, newValue in
            frameCamera(for: newValue)
        }
        .onDisappear {
            cameraGlideTask?.cancel()
        }
    }

    var overlayControls: some View {
        VStack(spacing: 0) {
            HStack {
                Text("\(status.name) 的一天")
                    .font(.headline.weight(.bold))
                    .foregroundStyle(.white)
                    .padding(.vertical, 8)
                    .padding(.horizontal, 14)
                    .background(.black.opacity(0.32))
                    .clipShape(Capsule())

                Spacer()

                Button {
                    dismiss()
                } label: {
                    Image(systemName: "xmark")
                        .font(.subheadline.weight(.bold))
                        .foregroundStyle(.white)
                        .frame(width: 36, height: 36)
                        .background(.black.opacity(0.32))
                        .clipShape(Circle())
                }
                .buttonStyle(.plain)
            }
            .padding(.horizontal, DesignTokens.pagePadding)
            .padding(.top, 14)

            Spacer()

            VStack(spacing: 12) {
                if let chapter = currentChapter {
                    RecapChapterCard(chapter: chapter)
                        .id(chapter.id)
                        .transition(.move(edge: .bottom).combined(with: .opacity))
                }

                HStack(spacing: 6) {
                    ForEach(chapters) { chapter in
                        Capsule()
                            .fill(chapter.id <= currentIndex ? DesignTokens.amber : DesignTokens.softLine.opacity(0.9))
                            .frame(width: chapter.id == currentIndex ? 18 : 7, height: 5)
                    }
                }
                .animation(.easeInOut(duration: 0.3), value: currentIndex)

                HStack(spacing: 14) {
                    RecapControlButton(systemImage: "backward.end.fill") {
                        jump(to: currentIndex - 1)
                    }
                    RecapControlButton(systemImage: isPaused ? "play.fill" : "pause.fill", size: 52) {
                        isPaused.toggle()
                        if isPaused {
                            cameraGlideTask?.cancel()
                        } else if let chapter = currentChapter, chapter.kind == .move {
                            startCameraGlide(for: chapter, fromProgress: localProgress)
                        }
                    }
                    RecapControlButton(systemImage: "forward.end.fill") {
                        jump(to: currentIndex + 1)
                    }
                }
            }
            .padding(.horizontal, DesignTokens.pagePadding)
            .padding(.bottom, 26)
            .animation(.easeInOut(duration: 0.35), value: currentIndex)
        }
    }

    var endCard: some View {
        ZStack {
            Color.black.opacity(0.4)
                .ignoresSafeArea()

            VStack(spacing: 14) {
                RecapPetMarker(petID: status.petID, petType: status.petType ?? .dog, size: 74)

                Text("今天也认真生活过啦")
                    .font(.title3.weight(.bold))
                    .foregroundStyle(DesignTokens.ink)
                Text("\(status.name) 走过 \(visitedStops.count) 个地方,把喜欢的都记下来了。")
                    .font(.subheadline)
                    .foregroundStyle(DesignTokens.secondaryInk)
                    .multilineTextAlignment(.center)

                HStack(spacing: 10) {
                    Button {
                        replayTime = 0
                        isFinished = false
                        isPaused = false
                        frameCamera(for: 0)
                    } label: {
                        Label("再看一遍", systemImage: "arrow.counterclockwise")
                            .font(.subheadline.weight(.semibold))
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 12)
                            .background(DesignTokens.mist.opacity(0.7))
                            .clipShape(Capsule())
                    }
                    .buttonStyle(.plain)

                    Button {
                        dismiss()
                    } label: {
                        Label("晚安", systemImage: "moon.stars.fill")
                            .font(.subheadline.weight(.semibold))
                            .foregroundStyle(.white)
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 12)
                            .background(DesignTokens.dusk)
                            .clipShape(Capsule())
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(22)
            .frame(maxWidth: 330)
            .background(DesignTokens.surface.opacity(0.97))
            .clipShape(RoundedRectangle(cornerRadius: 24, style: .continuous))
            .shadow(color: DesignTokens.deepInk.opacity(0.2), radius: 30, x: 0, y: 14)
        }
        .transition(.opacity)
    }

    var emptyState: some View {
        ZStack {
            AppBackground()
            VStack(spacing: 10) {
                Image(systemName: "sun.horizon.fill")
                    .font(.system(size: 38))
                    .foregroundStyle(DesignTokens.amber)
                Text("今天的故事还没展开")
                    .font(.headline.weight(.semibold))
                    .foregroundStyle(DesignTokens.ink)
                Text("等 TA 出门走过几个地方,晚上再来看这一天。")
                    .font(.subheadline)
                    .foregroundStyle(DesignTokens.secondaryInk)
                Button("好") { dismiss() }
                    .font(.subheadline.weight(.semibold))
                    .padding(.top, 6)
            }
        }
    }

    func chapterStart(_ index: Int) -> Double {
        chapters.prefix(index).reduce(0) { $0 + $1.duration }
    }

    func jump(to index: Int) {
        guard chapters.indices.contains(index) else { return }
        replayTime = chapterStart(index)
        isFinished = false
    }

    func runClock() async {
        try? await Task.sleep(for: .milliseconds(750))
        frameCamera(for: 0)
        var last = Date()
        while !Task.isCancelled {
            try? await Task.sleep(for: .milliseconds(40))
            let now = Date()
            let delta = now.timeIntervalSince(last)
            last = now
            guard !isPaused, !isFinished, !chapters.isEmpty else { continue }
            replayTime += delta
            if replayTime >= totalDuration {
                replayTime = totalDuration
                withAnimation(.easeInOut(duration: 0.5)) {
                    isFinished = true
                }
            }
        }
    }

    func frameCamera(for index: Int) {
        guard chapters.indices.contains(index) else { return }
        let chapter = chapters[index]
        switch chapter.kind {
        case .stay:
            cameraGlideTask?.cancel()
            withAnimation(.easeInOut(duration: 0.9)) {
                cameraPosition = .camera(
                    MapCamera(centerCoordinate: chapter.coordinate, distance: 1_500, heading: 24, pitch: 58)
                )
            }
        case .move:
            startCameraGlide(for: chapter, fromProgress: 0)
        }
    }

    /// 移动章节的滑轨跟拍:先快速切到起点机位,再让镜头以线性速度滑向终点,与沿路线移动的宠物同行。
    func startCameraGlide(for chapter: DayRecapChapter, fromProgress: Double) {
        cameraGlideTask?.cancel()
        cameraGlideTask = Task { @MainActor in
            guard let start = chapter.route.first, let end = chapter.route.last else { return }
            let meters = max(600, JourneyMotion.totalDistance(of: chapter.route))
            let distance = min(max(meters * 2.2, 1_600), 2_400_000)
            let heading = JourneyMotion.bearingDegrees(from: start, to: end)
            let pitch: Double = meters > 80_000 ? 18 : 52
            let anchor = JourneyMotion.coordinate(on: chapter.route, progress: fromProgress) ?? start
            withAnimation(.easeInOut(duration: 0.45)) {
                cameraPosition = .camera(MapCamera(centerCoordinate: anchor, distance: distance, heading: heading, pitch: pitch))
            }
            try? await Task.sleep(for: .milliseconds(480))
            guard !Task.isCancelled else { return }
            let remaining = max(0.6, chapter.duration * (1 - fromProgress) - 0.5)
            withAnimation(.linear(duration: remaining)) {
                cameraPosition = .camera(MapCamera(centerCoordinate: end, distance: distance, heading: heading, pitch: pitch))
            }
        }
    }

    func partialRoute(_ route: [CLLocationCoordinate2D], progress: Double) -> [CLLocationCoordinate2D] {
        guard route.count > 1, progress > 0 else { return [] }
        let total = JourneyMotion.totalDistance(of: route)
        guard total > 0 else { return [] }
        let target = total * min(1, progress)
        var walked = 0.0
        var result: [CLLocationCoordinate2D] = [route[0]]
        for index in 0..<(route.count - 1) {
            let start = route[index]
            let end = route[index + 1]
            let segment = CLLocation(latitude: start.latitude, longitude: start.longitude)
                .distance(from: CLLocation(latitude: end.latitude, longitude: end.longitude))
            if walked + segment >= target {
                let local = segment == 0 ? 0 : (target - walked) / segment
                result.append(
                    CLLocationCoordinate2D(
                        latitude: start.latitude + (end.latitude - start.latitude) * local,
                        longitude: start.longitude + (end.longitude - start.longitude) * local
                    )
                )
                return result
            }
            walked += segment
            result.append(end)
        }
        return result
    }
}

struct RecapControlButton: View {
    var systemImage: String
    var size: CGFloat = 42
    var action: () -> Void

    var body: some View {
        Button(action: action) {
            Image(systemName: systemImage)
                .font(.system(size: size * 0.34, weight: .bold))
                .foregroundStyle(.white)
                .frame(width: size, height: size)
                .background(.black.opacity(0.34))
                .clipShape(Circle())
        }
        .buttonStyle(.plain)
    }
}

struct RecapPetMarker: View {
    var petID: String
    var petType: PetType
    var size: CGFloat = 46

    var body: some View {
        Group {
            if let image = PetAvatarStore.image(for: petID) {
                Image(uiImage: image)
                    .resizable()
                    .scaledToFill()
            } else {
                ZStack {
                    DesignTokens.petal
                    Image(systemName: petType.symbolName)
                        .font(.system(size: size * 0.44, weight: .semibold))
                        .foregroundStyle(DesignTokens.clay)
                }
            }
        }
        .frame(width: size, height: size)
        .clipShape(Circle())
        .overlay {
            Circle().stroke(.white, lineWidth: 2)
        }
        .shadow(color: DesignTokens.deepInk.opacity(0.22), radius: 10, x: 0, y: 5)
    }
}

struct RecapChapterCard: View {
    var chapter: DayRecapChapter

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            if let imageURL = chapter.imageURL {
                AsyncImage(url: imageURL) { phase in
                    switch phase {
                    case .success(let image):
                        image
                            .resizable()
                            .scaledToFill()
                    default:
                        DesignTokens.mist
                    }
                }
                .frame(height: 128)
                .frame(maxWidth: .infinity)
                .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
            }

            HStack(spacing: 10) {
                Image(systemName: chapter.systemImage)
                    .font(.subheadline.weight(.bold))
                    .foregroundStyle(chapter.tint)
                    .frame(width: 32, height: 32)
                    .background(chapter.tint.opacity(0.13))
                    .clipShape(Circle())

                VStack(alignment: .leading, spacing: 2) {
                    Text(chapter.title)
                        .font(.subheadline.weight(.bold))
                        .foregroundStyle(DesignTokens.ink)
                        .lineLimit(1)
                        .minimumScaleFactor(0.8)
                    Text(chapter.subtitle)
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(DesignTokens.secondaryInk)
                        .lineLimit(1)
                }

                Spacer(minLength: 0)
            }
        }
        .padding(12)
        .background(DesignTokens.surface.opacity(0.94))
        .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
        .shadow(color: DesignTokens.deepInk.opacity(0.14), radius: 16, x: 0, y: 8)
    }
}

struct AccountLinkSheet: View {
    @Environment(\.dismiss) var dismiss
    @Environment(\.colorScheme) var colorScheme

    var petName: String
    var isSignedIn: Bool
    var displayName: String?
    var onAuthorized: (String, String?) async -> String?
    var onSignOut: () -> Void

    @State var isWorking = false
    @State var errorMessage: String?
    @State var didLink = false

    var body: some View {
        VStack(spacing: 18) {
            PetSoulAdaptiveIcon(
                systemImage: isSignedIn || didLink ? "checkmark.icloud.fill" : "icloud.and.arrow.up",
                tint: DesignTokens.sage,
                size: 44
            )
            .padding(.top, 26)

            VStack(spacing: 8) {
                Text(isSignedIn || didLink ? "旅程已经连着你" : "把 \(petName) 的旅程保存下来")
                    .font(.title3.weight(.semibold))
                    .foregroundStyle(DesignTokens.ink)
                    .multilineTextAlignment(.center)
                Text(isSignedIn || didLink
                     ? "换手机或重装 App 时，\(petName) 的路线、照片和回忆都会回到你身边。"
                     : "用 Apple 账号一键保存。以后换手机、重装 App，TA 都还在。")
                    .font(.subheadline)
                    .foregroundStyle(DesignTokens.secondaryInk)
                    .multilineTextAlignment(.center)
                    .lineSpacing(3)
            }
            .padding(.horizontal, 30)

            if let errorMessage {
                Text(errorMessage)
                    .font(.footnote)
                    .foregroundStyle(DesignTokens.clay)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 26)
            }

            Spacer(minLength: 0)

            if isSignedIn || didLink {
                VStack(spacing: 10) {
                    if let displayName, !displayName.isEmpty {
                        Text("已登录 · \(displayName)")
                            .font(.footnote.weight(.semibold))
                            .foregroundStyle(DesignTokens.secondaryInk)
                    }
                    Button("好") { dismiss() }
                        .primaryActionStyle()
                        .padding(.horizontal, DesignTokens.pagePadding)
                    Button("退出登录") {
                        onSignOut()
                        dismiss()
                    }
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(DesignTokens.secondaryInk)
                }
                .padding(.bottom, 22)
            } else {
                VStack(spacing: 12) {
                    SignInWithAppleButton(.continue) { request in
                        request.requestedScopes = [.fullName]
                    } onCompletion: { result in
                        handleAuthorization(result)
                    }
                    .signInWithAppleButtonStyle(colorScheme == .dark ? .white : .black)
                    .frame(height: 50)
                    .padding(.horizontal, DesignTokens.pagePadding)
                    .disabled(isWorking)
                    .opacity(isWorking ? 0.55 : 1)

                    Button("先不用，继续旅程") { dismiss() }
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(DesignTokens.secondaryInk)
                }
                .padding(.bottom, 22)
            }
        }
        .background(AppBackground())
    }

    func handleAuthorization(_ result: Result<ASAuthorization, Error>) {
        switch result {
        case .success(let authorization):
            guard let credential = authorization.credential as? ASAuthorizationAppleIDCredential,
                  let tokenData = credential.identityToken,
                  let identityToken = String(data: tokenData, encoding: .utf8) else {
                errorMessage = "没有拿到 Apple 的登录凭证，可以再试一次。"
                return
            }
            let fullName = [credential.fullName?.givenName, credential.fullName?.familyName]
                .compactMap { $0 }
                .joined(separator: " ")
            isWorking = true
            errorMessage = nil
            Task {
                let failure = await onAuthorized(identityToken, fullName.isEmpty ? nil : fullName)
                isWorking = false
                if let failure {
                    errorMessage = failure
                } else {
                    withAnimation(.easeInOut(duration: 0.25)) { didLink = true }
                }
            }
        case .failure:
            // 用户主动取消不提示错误
            break
        }
    }
}
