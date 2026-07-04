import MapKit
import SwiftUI
import UIKit

struct PublicWorldView: View {
    var onFindPet: () -> Void

    @State private var selectedEvent: WorldLifeEvent?
    @State private var pulse = false
    @State private var showsWorldNote = false
    @State private var resetToken = 0

    var body: some View {
        NavigationStack {
            ZStack(alignment: .bottom) {
                NativeGlobeMapView(
                    selectedID: selectedEvent?.id,
                    resetToken: resetToken,
                    onSelect: select
                )
                .saturation(1.18)
                .contrast(1.06)
                .brightness(0.018)
                .ignoresSafeArea()

                mapMoodOverlay

                VStack(spacing: 0) {
                    worldHeader
                    Spacer()
                }
                .padding(.horizontal, DesignTokens.pagePadding)
                .padding(.top, 12)

                VStack(spacing: 12) {
                    if showsWorldNote {
                        WorldNoteCard()
                            .transition(.move(edge: .bottom).combined(with: .opacity))
                    }

                    if let selectedEvent {
                        WorldEventDetailCard(
                            event: selectedEvent,
                            onClose: {
                                withAnimation(.easeInOut(duration: 0.25)) {
                                    self.selectedEvent = nil
                                }
                            },
                            onResetWorld: zoomToWorld
                        )
                        .transition(.move(edge: .bottom).combined(with: .opacity))
                    }

                    bottomPanel
                }
                .padding(.horizontal, DesignTokens.pagePadding)
                .padding(.bottom, 18)
            }
            .toolbar(.hidden, for: .navigationBar)
            .onAppear {
                withAnimation(.easeInOut(duration: 1.9).repeatForever(autoreverses: true)) {
                    pulse = true
                }
            }
        }
    }

    private var mapMoodOverlay: some View {
        ZStack {
            LinearGradient(
                colors: [
                    Color(hex: 0xFFF7EF).opacity(0.05),
                    .clear,
                    Color(hex: 0xFFF9F0).opacity(0.14)
                ],
                startPoint: .top,
                endPoint: .bottom
            )

            RadialGradient(
                colors: [
                    Color(hex: 0xF8D9CF).opacity(pulse ? 0.08 : 0.04),
                    Color(hex: 0xF4EBD7).opacity(0.03),
                    .clear
                ],
                center: .center,
                startRadius: 30,
                endRadius: 430
            )
            .scaleEffect(pulse ? 1.04 : 0.97)

            AmbientSignalField(
                tint: DesignTokens.sea,
                warmth: Color(hex: 0xE0A25E),
                density: 24,
                drift: 0.46
            )
            .opacity(0.58)
        }
        .ignoresSafeArea()
        .allowsHitTesting(false)
    }

    private var worldHeader: some View {
        HStack(spacing: 10) {
            HStack(spacing: 10) {
                Image(systemName: "globe.europe.africa.fill")
                    .font(.system(size: 17, weight: .semibold))
                    .foregroundStyle(Color(hex: 0x9E7866))
                    .frame(width: 34, height: 34)
                    .background(Color(hex: 0xFFF4EA).opacity(0.92))
                    .clipShape(Circle())

                VStack(alignment: .leading, spacing: 2) {
                    Text("PetJourney")
                        .font(.headline.weight(.semibold))
                        .foregroundStyle(DesignTokens.ink)
                    Text("灵魂世界正在旅行")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(Color(hex: 0x7B766E))
                }
            }
            .padding(.vertical, 9)
            .padding(.horizontal, 10)
            .background(.white.opacity(0.88))
            .clipShape(Capsule())
            .overlay {
                Capsule().stroke(.white.opacity(0.72), lineWidth: 1)
            }

            Spacer()

            Button(action: zoomToWorld) {
                Image(systemName: "globe.asia.australia")
                    .font(.headline.weight(.semibold))
                    .foregroundStyle(Color(hex: 0x9E7866))
                    .frame(width: 52, height: 52)
                    .background(.white.opacity(0.88))
                    .clipShape(Circle())
                    .overlay {
                        Circle().stroke(.white.opacity(0.72), lineWidth: 1)
                    }
            }
            .buttonStyle(.plain)
            .accessibilityLabel("回到地球视角")
        }
        .shadow(color: DesignTokens.ink.opacity(0.08), radius: 16, x: 0, y: 8)
    }

    private var bottomPanel: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .center, spacing: 12) {
                PetSoulAssetIcon(
                    asset: .signalPaw,
                    fallbackSystemImage: "sparkles",
                    fallbackTint: Color(hex: 0xC8956D),
                    size: 30
                )
                    .frame(width: 30, height: 30)
                    .background(Color(hex: 0xFFF1E8))
                    .clipShape(Circle())

                VStack(alignment: .leading, spacing: 5) {
                    Text("也许 TA 正在世界某个角落。")
                        .font(.headline.weight(.semibold))
                        .foregroundStyle(DesignTokens.ink)
                    Text("从一张照片和一点记忆开始，沿着真实地图慢慢寻找属于你的那一个信号。")
                        .font(.caption)
                        .foregroundStyle(DesignTokens.secondaryInk)
                        .lineSpacing(2)
                        .lineLimit(2)
                }

                Spacer(minLength: 0)

                Button {
                    withAnimation(.easeInOut(duration: 0.25)) {
                        showsWorldNote.toggle()
                    }
                } label: {
                    Image(systemName: showsWorldNote ? "xmark" : "info")
                        .font(.caption.weight(.bold))
                        .foregroundStyle(Color(hex: 0x8C7166))
                        .frame(width: 30, height: 30)
                        .background(.white.opacity(0.76))
                        .clipShape(Circle())
                }
                .buttonStyle(.plain)
                .accessibilityLabel(showsWorldNote ? "收起说明" : "查看说明")
            }

            WorldLiveStoryTicker()

            HStack(spacing: 9) {
                WorldPill(title: "小店吃饭", systemImage: "fork.knife")
                WorldPill(title: "街角晒太阳", systemImage: "sun.max")
                WorldPill(title: "海边等风", systemImage: "wind")
            }

            Button(action: onFindPet) {
                Label("寻找我的 TA", systemImage: "camera.viewfinder")
            }
            .primaryActionStyle()
        }
        .padding(14)
        .background(.white.opacity(0.93))
        .clipShape(RoundedRectangle(cornerRadius: 22, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 22, style: .continuous)
                .stroke(.white.opacity(0.76), lineWidth: 1)
        }
        .shadow(color: Color(hex: 0x7D5F54).opacity(0.14), radius: 24, x: 0, y: 12)
    }

    private func select(_ event: WorldLifeEvent) {
        withAnimation(.easeInOut(duration: 0.25)) {
            selectedEvent = event
        }
    }

    private func zoomToWorld() {
        withAnimation(.easeInOut(duration: 0.3)) {
            selectedEvent = nil
            resetToken += 1
        }
    }
}

private struct NativeGlobeMapView: UIViewRepresentable {
    var selectedID: String?
    var resetToken: Int
    var onSelect: (WorldLifeEvent) -> Void

    func makeCoordinator() -> Coordinator {
        Coordinator(onSelect: onSelect)
    }

    func makeUIView(context: Context) -> MKMapView {
        let mapView = MKMapView(frame: .zero)
        mapView.delegate = context.coordinator
        mapView.isRotateEnabled = false
        mapView.isPitchEnabled = false
        mapView.isZoomEnabled = true
        mapView.isScrollEnabled = true
        mapView.showsCompass = false
        mapView.showsScale = false
        mapView.pointOfInterestFilter = .includingAll
        mapView.cameraZoomRange = MKMapView.CameraZoomRange(
            minCenterCoordinateDistance: 1_000,
            maxCenterCoordinateDistance: 600_000_000
        )
        mapView.cameraBoundary = MKMapView.CameraBoundary(mapRect: .world)

        let configuration = MKStandardMapConfiguration(elevationStyle: .realistic)
        configuration.pointOfInterestFilter = .includingAll
        configuration.showsTraffic = false
        mapView.preferredConfiguration = configuration

        context.coordinator.resetWorld(on: mapView, animated: false)
        context.coordinator.refreshAnimalField(on: mapView)
        DispatchQueue.main.async {
            context.coordinator.resetWorld(on: mapView, animated: false)
            context.coordinator.refreshAnimalField(on: mapView)
        }
        return mapView
    }

    func updateUIView(_ mapView: MKMapView, context: Context) {
        context.coordinator.onSelect = onSelect
        context.coordinator.updateSelection(selectedID, on: mapView)

        if context.coordinator.lastResetToken != resetToken {
            context.coordinator.lastResetToken = resetToken
            context.coordinator.resetWorld(on: mapView, animated: true)
        }
    }

    final class Coordinator: NSObject, MKMapViewDelegate {
        var onSelect: (WorldLifeEvent) -> Void
        var annotationsByID: [String: WorldLifeAnnotation] = [:]
        var badgeViewsByID: [String: WorldAnimalBadgeView] = [:]
        var eventsByID: [String: WorldLifeEvent] = [:]
        var lastResetToken = 0
        var isProgrammaticSelection = false
        var selectedEvent: WorldLifeEvent?
        weak var mapView: MKMapView?

        init(onSelect: @escaping (WorldLifeEvent) -> Void) {
            self.onSelect = onSelect
        }

        func resetWorld(on mapView: MKMapView, animated: Bool) {
            mapView.deselectAllAnnotations(animated: true)
            let camera = MKMapCamera(
                lookingAtCenter: CLLocationCoordinate2D(latitude: 8, longitude: 38),
                fromDistance: 380_000_000,
                pitch: 0,
                heading: 0
            )
            mapView.setCamera(camera, animated: animated)
        }

        func refreshAnimalField(on mapView: MKMapView) {
            self.mapView = mapView
            var events = WorldAnimalField.events(for: mapView)
            let showsCompactBadges = shouldUseCompactBadges(on: mapView)

            if let selectedEvent, events.contains(where: { $0.id == selectedEvent.id }) == false {
                events.append(selectedEvent)
            }

            let nextIDs = Set(events.map(\.id))
            eventsByID = Dictionary(uniqueKeysWithValues: events.map { ($0.id, $0) })

            Set(badgeViewsByID.keys)
                .subtracting(nextIDs)
                .forEach { id in
                    badgeViewsByID[id]?.removeFromSuperview()
                    badgeViewsByID[id] = nil
                }

            events.forEach { event in
                let badge = badgeViewsByID[event.id] ?? {
                    let view = WorldAnimalBadgeView(event: event)
                    view.addTarget(self, action: #selector(didTapBadge(_:)), for: .touchUpInside)
                    mapView.addSubview(view)
                    badgeViewsByID[event.id] = view
                    return view
                }()
                badge.configure(with: event, compact: showsCompactBadges)
            }

            updateBadgePositions(on: mapView)
        }

        private func shouldUseCompactBadges(on mapView: MKMapView) -> Bool {
            let worldSpanRatio = mapView.visibleMapRect.size.width / MKMapRect.world.size.width
            return mapView.camera.centerCoordinateDistance >= 72_000_000 || worldSpanRatio >= 0.22
        }

        func updateSelection(_ selectedID: String?, on mapView: MKMapView) {
            guard let selectedID, let event = eventsByID[selectedID] else { return }
            selectedEvent = event
        }

        func mapView(_ mapView: MKMapView, viewFor annotation: MKAnnotation) -> MKAnnotationView? {
            guard let annotation = annotation as? WorldLifeAnnotation else { return nil }

            let view = mapView.dequeueReusableAnnotationView(
                withIdentifier: WorldEventAnnotationView.reuseIdentifier
            ) as? WorldEventAnnotationView ?? WorldEventAnnotationView(
                annotation: annotation,
                reuseIdentifier: WorldEventAnnotationView.reuseIdentifier
            )
            view.annotation = annotation
            view.configure(with: annotation.event)
            return view
        }

        func mapView(_ mapView: MKMapView, didSelect view: MKAnnotationView) {
            guard let annotation = view.annotation as? WorldLifeAnnotation else { return }
            selectedEvent = annotation.event
            onSelect(annotation.event)

            if !isProgrammaticSelection {
                let camera = MKMapCamera(
                    lookingAtCenter: annotation.coordinate,
                    fromDistance: annotation.event.focusDistance,
                    pitch: 0,
                    heading: mapView.camera.heading
                )
                mapView.setCamera(camera, animated: true)
            }
        }

        func mapView(_ mapView: MKMapView, regionDidChangeAnimated animated: Bool) {
            refreshAnimalField(on: mapView)
        }

        func mapViewDidChangeVisibleRegion(_ mapView: MKMapView) {
            updateBadgePositions(on: mapView)
        }

        func updateBadgePositions(on mapView: MKMapView) {
            badgeViewsByID.values.forEach { badge in
                let point = mapView.convert(badge.event.coordinate, toPointTo: mapView)
                badge.center = CGPoint(x: point.x, y: point.y - 22)
                let horizontalInset = badge.bounds.width * 0.5 + 8
                let compact = badge.bounds.width <= 48
                let topLimit: CGFloat = compact ? 290 : 150
                let bottomLimit = mapView.bounds.height - (compact ? 360 : 300)
                badge.isHidden = point.x < horizontalInset
                    || point.x > mapView.bounds.width - horizontalInset
                    || point.y < topLimit
                    || point.y > bottomLimit
            }
        }

        @objc private func didTapBadge(_ sender: WorldAnimalBadgeView) {
            selectedEvent = sender.event
            onSelect(sender.event)

            guard let mapView else { return }
            let camera = MKMapCamera(
                lookingAtCenter: sender.event.coordinate,
                fromDistance: sender.event.focusDistance,
                pitch: 0,
                heading: mapView.camera.heading
            )
            mapView.setCamera(camera, animated: true)
        }
    }
}

private final class WorldLifeAnnotation: NSObject, MKAnnotation {
    let event: WorldLifeEvent
    var coordinate: CLLocationCoordinate2D { event.coordinate }
    var title: String? { event.city }
    var subtitle: String? { event.activity }

    init(event: WorldLifeEvent) {
        self.event = event
        super.init()
    }
}

private final class WorldAnimalBadgeView: UIControl {
    private(set) var event: WorldLifeEvent

    private let container = UIVisualEffectView(effect: UIBlurEffect(style: .systemThinMaterialLight))
    private let compactContainer = UIVisualEffectView(effect: UIBlurEffect(style: .systemThinMaterialLight))
    private let iconCircle = UIView()
    private let iconView = UIImageView()
    private let compactIconCircle = UIView()
    private let compactIconView = UIImageView()
    private let compactDot = UIView()
    private let titleLabel = UILabel()
    private let subtitleLabel = UILabel()
    private let dot = UIView()
    private var isCompact = false

    init(event: WorldLifeEvent) {
        self.event = event
        super.init(frame: CGRect(x: 0, y: 0, width: 118, height: 44))
        setup()
        configure(with: event, compact: false)
    }

    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    func configure(with event: WorldLifeEvent, compact: Bool) {
        self.event = event
        applyPresentation(compact: compact)
        if let asset = PetSoulAsset.from(systemImage: event.sceneIcon),
           let image = UIImage(named: asset.rawValue)?.withRenderingMode(.alwaysOriginal) {
            iconView.image = image
            iconView.tintColor = nil
            compactIconView.image = image
            compactIconView.tintColor = nil
        } else {
            iconView.image = UIImage(systemName: event.sceneIcon)
            iconView.tintColor = event.uiTint
            compactIconView.image = UIImage(systemName: event.sceneIcon)
            compactIconView.tintColor = event.uiTint
        }
        iconCircle.backgroundColor = event.uiTint.withAlphaComponent(0.16)
        compactIconCircle.backgroundColor = event.uiTint.withAlphaComponent(0.18)
        dot.backgroundColor = event.uiTint
        compactDot.backgroundColor = event.uiTint
        titleLabel.text = event.city
        subtitleLabel.text = event.activity
        accessibilityLabel = "\(event.city)，\(event.activity)"
    }

    override var isHighlighted: Bool {
        didSet {
            UIView.animate(withDuration: 0.16) {
                self.transform = self.isHighlighted ? CGAffineTransform(scaleX: 0.96, y: 0.96) : .identity
                self.alpha = self.isHighlighted ? 0.86 : 1
            }
        }
    }

    override func point(inside point: CGPoint, with event: UIEvent?) -> Bool {
        if isCompact {
            return bounds.insetBy(dx: -8, dy: -8).contains(point)
        }

        let iconHitArea = CGRect(x: 0, y: 0, width: 46, height: bounds.height).insetBy(dx: -4, dy: -6)
        let dotHitArea = CGRect(x: bounds.width - 36, y: 4, width: 36, height: bounds.height - 8)
        return iconHitArea.contains(point) || dotHitArea.contains(point)
    }

    private func applyPresentation(compact: Bool) {
        isCompact = compact
        let size = compact ? CGSize(width: 44, height: 44) : CGSize(width: 118, height: 44)

        if bounds.size != size {
            bounds = CGRect(origin: .zero, size: size)
        }

        if compact {
            compactContainer.frame = bounds
            compactContainer.layer.cornerRadius = 22
        } else {
            container.frame = bounds
            container.layer.cornerRadius = 22
        }

        container.isHidden = compact
        compactContainer.isHidden = !compact
        layer.shadowPath = UIBezierPath(roundedRect: bounds, cornerRadius: 22).cgPath
    }

    private func setup() {
        container.frame = bounds
        container.layer.cornerRadius = 22
        container.layer.cornerCurve = .continuous
        container.clipsToBounds = true
        container.contentView.backgroundColor = UIColor.white.withAlphaComponent(0.40)
        container.isUserInteractionEnabled = false
        addSubview(container)

        compactContainer.frame = CGRect(x: 0, y: 0, width: 44, height: 44)
        compactContainer.layer.cornerRadius = 22
        compactContainer.layer.cornerCurve = .continuous
        compactContainer.clipsToBounds = true
        compactContainer.contentView.backgroundColor = UIColor.white.withAlphaComponent(0.44)
        compactContainer.isUserInteractionEnabled = false
        compactContainer.isHidden = true
        addSubview(compactContainer)

        layer.shadowColor = UIColor(hex: 0x6C554F).cgColor
        layer.shadowOpacity = 0.18
        layer.shadowRadius = 14
        layer.shadowOffset = CGSize(width: 0, height: 8)

        iconCircle.translatesAutoresizingMaskIntoConstraints = false
        iconCircle.layer.cornerRadius = 13
        iconCircle.clipsToBounds = true

        iconView.translatesAutoresizingMaskIntoConstraints = false
        iconView.contentMode = .scaleAspectFit

        compactIconCircle.translatesAutoresizingMaskIntoConstraints = false
        compactIconCircle.layer.cornerRadius = 15
        compactIconCircle.clipsToBounds = true

        compactIconView.translatesAutoresizingMaskIntoConstraints = false
        compactIconView.contentMode = .scaleAspectFit

        titleLabel.translatesAutoresizingMaskIntoConstraints = false
        titleLabel.font = .systemFont(ofSize: 11, weight: .bold)
        titleLabel.textColor = UIColor(hex: 0x26302F)

        subtitleLabel.translatesAutoresizingMaskIntoConstraints = false
        subtitleLabel.font = .systemFont(ofSize: 8.8, weight: .semibold)
        subtitleLabel.textColor = UIColor(hex: 0x697673)
        subtitleLabel.lineBreakMode = .byTruncatingTail

        dot.translatesAutoresizingMaskIntoConstraints = false
        dot.layer.cornerRadius = 4
        dot.layer.borderColor = UIColor.white.cgColor
        dot.layer.borderWidth = 1.4

        compactDot.translatesAutoresizingMaskIntoConstraints = false
        compactDot.layer.cornerRadius = 3.5
        compactDot.layer.borderColor = UIColor.white.cgColor
        compactDot.layer.borderWidth = 1.3

        container.contentView.addSubview(iconCircle)
        iconCircle.addSubview(iconView)
        container.contentView.addSubview(titleLabel)
        container.contentView.addSubview(subtitleLabel)
        container.contentView.addSubview(dot)
        compactContainer.contentView.addSubview(compactIconCircle)
        compactIconCircle.addSubview(compactIconView)
        compactContainer.contentView.addSubview(compactDot)

        NSLayoutConstraint.activate([
            iconCircle.leadingAnchor.constraint(equalTo: container.contentView.leadingAnchor, constant: 6),
            iconCircle.centerYAnchor.constraint(equalTo: container.contentView.centerYAnchor),
            iconCircle.widthAnchor.constraint(equalToConstant: 30),
            iconCircle.heightAnchor.constraint(equalToConstant: 30),

            iconView.centerXAnchor.constraint(equalTo: iconCircle.centerXAnchor),
            iconView.centerYAnchor.constraint(equalTo: iconCircle.centerYAnchor),
            iconView.widthAnchor.constraint(equalToConstant: 16),
            iconView.heightAnchor.constraint(equalToConstant: 16),

            titleLabel.leadingAnchor.constraint(equalTo: iconCircle.trailingAnchor, constant: 8),
            titleLabel.trailingAnchor.constraint(equalTo: container.contentView.trailingAnchor, constant: -10),
            titleLabel.topAnchor.constraint(equalTo: container.contentView.topAnchor, constant: 7),

            subtitleLabel.leadingAnchor.constraint(equalTo: titleLabel.leadingAnchor),
            subtitleLabel.trailingAnchor.constraint(equalTo: titleLabel.trailingAnchor),
            subtitleLabel.topAnchor.constraint(equalTo: titleLabel.bottomAnchor, constant: 1),

            dot.trailingAnchor.constraint(equalTo: container.contentView.trailingAnchor, constant: -7),
            dot.bottomAnchor.constraint(equalTo: container.contentView.bottomAnchor, constant: -6),
            dot.widthAnchor.constraint(equalToConstant: 8),
            dot.heightAnchor.constraint(equalToConstant: 8),

            compactIconCircle.centerXAnchor.constraint(equalTo: compactContainer.contentView.centerXAnchor),
            compactIconCircle.centerYAnchor.constraint(equalTo: compactContainer.contentView.centerYAnchor),
            compactIconCircle.widthAnchor.constraint(equalToConstant: 30),
            compactIconCircle.heightAnchor.constraint(equalToConstant: 30),

            compactIconView.centerXAnchor.constraint(equalTo: compactIconCircle.centerXAnchor),
            compactIconView.centerYAnchor.constraint(equalTo: compactIconCircle.centerYAnchor),
            compactIconView.widthAnchor.constraint(equalToConstant: 16),
            compactIconView.heightAnchor.constraint(equalToConstant: 16),

            compactDot.trailingAnchor.constraint(equalTo: compactContainer.contentView.trailingAnchor, constant: -7),
            compactDot.bottomAnchor.constraint(equalTo: compactContainer.contentView.bottomAnchor, constant: -7),
            compactDot.widthAnchor.constraint(equalToConstant: 7),
            compactDot.heightAnchor.constraint(equalToConstant: 7)
        ])
    }
}

private final class WorldEventAnnotationView: MKAnnotationView {
    static let reuseIdentifier = "WorldEventAnnotationView"

    private let container = UIVisualEffectView(effect: UIBlurEffect(style: .systemThinMaterialLight))
    private let iconCircle = UIView()
    private let iconView = UIImageView()
    private let titleLabel = UILabel()
    private let subtitleLabel = UILabel()
    private let dot = UIView()

    override init(annotation: MKAnnotation?, reuseIdentifier: String?) {
        super.init(annotation: annotation, reuseIdentifier: reuseIdentifier)
        frame = CGRect(x: 0, y: 0, width: 118, height: 44)
        centerOffset = CGPoint(x: 0, y: -22)
        collisionMode = .rectangle
        displayPriority = .required
        canShowCallout = false
        setup()
    }

    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    func configure(with event: WorldLifeEvent) {
        if let asset = PetSoulAsset.from(systemImage: event.sceneIcon),
           let image = UIImage(named: asset.rawValue)?.withRenderingMode(.alwaysOriginal) {
            iconView.image = image
            iconView.tintColor = nil
        } else {
            iconView.image = UIImage(systemName: event.sceneIcon)
            iconView.tintColor = event.uiTint
        }
        iconCircle.backgroundColor = event.uiTint.withAlphaComponent(0.16)
        dot.backgroundColor = event.uiTint
        titleLabel.text = event.city
        subtitleLabel.text = event.activity
        subtitleLabel.textColor = event.isGenerated ? UIColor(hex: 0x5F6C69) : UIColor(hex: 0x697673)
        accessibilityLabel = "\(event.city)，\(event.activity)"
    }

    override var isSelected: Bool {
        didSet {
            UIView.animate(withDuration: 0.2) {
                self.transform = self.isSelected ? CGAffineTransform(scaleX: 1.08, y: 1.08) : .identity
                self.container.contentView.backgroundColor = self.isSelected
                    ? UIColor.white.withAlphaComponent(0.58)
                    : UIColor.white.withAlphaComponent(0.36)
            }
        }
    }

    private func setup() {
        container.frame = bounds
        container.layer.cornerRadius = 22
        container.layer.cornerCurve = .continuous
        container.clipsToBounds = true
        container.contentView.backgroundColor = UIColor.white.withAlphaComponent(0.40)
        addSubview(container)

        layer.shadowColor = UIColor(hex: 0x6C554F).cgColor
        layer.shadowOpacity = 0.18
        layer.shadowRadius = 14
        layer.shadowOffset = CGSize(width: 0, height: 8)

        iconCircle.translatesAutoresizingMaskIntoConstraints = false
        iconCircle.layer.cornerRadius = 13
        iconCircle.clipsToBounds = true

        iconView.translatesAutoresizingMaskIntoConstraints = false
        iconView.contentMode = .scaleAspectFit

        titleLabel.translatesAutoresizingMaskIntoConstraints = false
        titleLabel.font = .systemFont(ofSize: 11, weight: .bold)
        titleLabel.textColor = UIColor(hex: 0x26302F)

        subtitleLabel.translatesAutoresizingMaskIntoConstraints = false
        subtitleLabel.font = .systemFont(ofSize: 8.8, weight: .semibold)
        subtitleLabel.textColor = UIColor(hex: 0x697673)
        subtitleLabel.lineBreakMode = .byTruncatingTail

        dot.translatesAutoresizingMaskIntoConstraints = false
        dot.layer.cornerRadius = 5
        dot.layer.borderColor = UIColor.white.cgColor
        dot.layer.borderWidth = 1.5

        container.contentView.addSubview(iconCircle)
        iconCircle.addSubview(iconView)
        container.contentView.addSubview(titleLabel)
        container.contentView.addSubview(subtitleLabel)
        container.contentView.addSubview(dot)

        NSLayoutConstraint.activate([
            iconCircle.leadingAnchor.constraint(equalTo: container.contentView.leadingAnchor, constant: 6),
            iconCircle.centerYAnchor.constraint(equalTo: container.contentView.centerYAnchor),
            iconCircle.widthAnchor.constraint(equalToConstant: 30),
            iconCircle.heightAnchor.constraint(equalToConstant: 30),

            iconView.centerXAnchor.constraint(equalTo: iconCircle.centerXAnchor),
            iconView.centerYAnchor.constraint(equalTo: iconCircle.centerYAnchor),
            iconView.widthAnchor.constraint(equalToConstant: 17),
            iconView.heightAnchor.constraint(equalToConstant: 17),

            titleLabel.leadingAnchor.constraint(equalTo: iconCircle.trailingAnchor, constant: 8),
            titleLabel.trailingAnchor.constraint(equalTo: container.contentView.trailingAnchor, constant: -10),
            titleLabel.topAnchor.constraint(equalTo: container.contentView.topAnchor, constant: 8),

            subtitleLabel.leadingAnchor.constraint(equalTo: titleLabel.leadingAnchor),
            subtitleLabel.trailingAnchor.constraint(equalTo: titleLabel.trailingAnchor),
            subtitleLabel.topAnchor.constraint(equalTo: titleLabel.bottomAnchor, constant: 1),

            dot.trailingAnchor.constraint(equalTo: container.contentView.trailingAnchor, constant: -7),
            dot.bottomAnchor.constraint(equalTo: container.contentView.bottomAnchor, constant: -6),
            dot.widthAnchor.constraint(equalToConstant: 8),
            dot.heightAnchor.constraint(equalToConstant: 8)
        ])
    }
}

private extension MKMapView {
    func deselectAllAnnotations(animated: Bool) {
        selectedAnnotations.forEach { deselectAnnotation($0, animated: animated) }
    }
}

private struct WorldLifeEvent: Identifiable, Equatable {
    var id: String
    var city: String
    var place: String
    var petName: String
    var petType: PetType
    var activity: String
    var detail: String
    var latitude: Double
    var longitude: Double
    var tintHex: UInt
    var sceneIcon: String
    var focusDistance: CLLocationDistance = 1_800_000

    var coordinate: CLLocationCoordinate2D {
        CLLocationCoordinate2D(latitude: latitude, longitude: longitude)
    }

    var isGenerated: Bool { id.hasPrefix("field-") }
    var tint: Color { Color(hex: tintHex) }
    var uiTint: UIColor { UIColor(hex: tintHex) }

    static func == (lhs: WorldLifeEvent, rhs: WorldLifeEvent) -> Bool {
        lhs.id == rhs.id
    }

    static let samples: [WorldLifeEvent] = [
        WorldLifeEvent(
            id: "paris-cafe",
            city: "巴黎",
            place: "街角咖啡馆",
            petName: "Luna",
            petType: .cat,
            activity: "在街角晒太阳",
            detail: "阳光落在椅背上，TA 把尾巴轻轻绕成一个圈。",
            latitude: 48.8566,
            longitude: 2.3522,
            tintHex: 0xE0A25E,
            sceneIcon: "cup.and.saucer.fill",
            focusDistance: 900_000
        ),
        WorldLifeEvent(
            id: "lisbon-sea",
            city: "里斯本",
            place: "海边长椅",
            petName: "年年",
            petType: .cat,
            activity: "在海边等风",
            detail: "风从很远的地方吹过来，TA 眯着眼睛听了一会儿。",
            latitude: 38.7223,
            longitude: -9.1393,
            tintHex: 0x69B6A5,
            sceneIcon: "sailboat.fill",
            focusDistance: 1_100_000
        ),
        WorldLifeEvent(
            id: "cairo-lamp",
            city: "开罗",
            place: "夜灯下面",
            petName: "米粒",
            petType: .parrot,
            activity: "在看一盏灯",
            detail: "那盏灯亮得很软，TA 歪着头看了好久，轻轻啾了一声。",
            latitude: 30.0444,
            longitude: 31.2357,
            tintHex: 0xD6B05E,
            sceneIcon: "lightbulb.fill",
            focusDistance: 1_000_000
        ),
        WorldLifeEvent(
            id: "dubai-window",
            city: "迪拜",
            place: "玻璃窗边",
            petName: "Lucky",
            petType: .dog,
            activity: "在窗边看云",
            detail: "TA 贴近窗边，认真看着云影从城市上方慢慢走过。",
            latitude: 25.2048,
            longitude: 55.2708,
            tintHex: 0xC6A66A,
            sceneIcon: "cloud.sun.fill",
            focusDistance: 1_000_000
        ),
        WorldLifeEvent(
            id: "tokyo-shop",
            city: "东京",
            place: "一间小食堂",
            petName: "Momo",
            petType: .dog,
            activity: "在小店吃饭",
            detail: "TA 坐在靠窗的小桌边，慢慢吃一小份热乎食物。",
            latitude: 35.6764,
            longitude: 139.6500,
            tintHex: 0xD98566,
            sceneIcon: "takeoutbag.and.cup.and.straw",
            focusDistance: 900_000
        ),
        WorldLifeEvent(
            id: "seoul-book",
            city: "首尔",
            place: "旧书店窗下",
            petName: "豆豆",
            petType: .rabbit,
            activity: "在窗边发呆",
            detail: "TA 抬头看了一会儿橱窗，耳朵轻轻动了一下。",
            latitude: 37.5665,
            longitude: 126.9780,
            tintHex: 0xA8A45F,
            sceneIcon: "book.closed.fill",
            focusDistance: 900_000
        ),
        WorldLifeEvent(
            id: "capetown-park",
            city: "开普敦",
            place: "公园小路",
            petName: "Coco",
            petType: .dog,
            activity: "在追一片叶子",
            detail: "叶子滚了很远，TA 跟着跑了几步，又轻轻停下。",
            latitude: -33.9249,
            longitude: 18.4241,
            tintHex: 0x92B96D,
            sceneIcon: "leaf.fill",
            focusDistance: 1_100_000
        ),
        WorldLifeEvent(
            id: "reykjavik-window",
            city: "雷克雅未克",
            place: "亮着灯的窗边",
            petName: "小宝",
            petType: .hamster,
            activity: "在窗边看雪",
            detail: "窗外很安静，TA 抱着一点暖光，像一封没有寄出的信。",
            latitude: 64.1466,
            longitude: -21.9426,
            tintHex: 0x87B8DA,
            sceneIcon: "snowflake",
            focusDistance: 1_300_000
        ),
        WorldLifeEvent(
            id: "sydney-flower",
            city: "悉尼",
            place: "花店门口",
            petName: "团团",
            petType: .dog,
            activity: "在花店门口停留",
            detail: "TA 好像认出了一种熟悉的味道，停下来多看了一眼。",
            latitude: -33.8688,
            longitude: 151.2093,
            tintHex: 0xDE8DA0,
            sceneIcon: "camera.macro",
            focusDistance: 1_200_000
        ),
        WorldLifeEvent(
            id: "bangkok-rain",
            city: "曼谷",
            place: "雨后的路口",
            petName: "Nori",
            petType: .dog,
            activity: "在踩小水洼",
            detail: "TA 绕着水洼走了一圈，像发现了一个新的小游戏。",
            latitude: 13.7563,
            longitude: 100.5018,
            tintHex: 0x82A9D3,
            sceneIcon: "cloud.rain.fill",
            focusDistance: 950_000
        ),
        WorldLifeEvent(
            id: "newyork-corner",
            city: "纽约",
            place: "路边咖啡车",
            petName: "Sugar",
            petType: .dog,
            activity: "在路边闻咖啡香",
            detail: "TA 没有真的喝，只是认真闻了很久，像以前等你买早餐。",
            latitude: 40.7128,
            longitude: -74.0060,
            tintHex: 0x7AA8CB,
            sceneIcon: "mug.fill",
            focusDistance: 1_000_000
        ),
        WorldLifeEvent(
            id: "vancouver-pier",
            city: "温哥华",
            place: "码头边",
            petName: "橘子",
            petType: .bird,
            activity: "在听海鸥叫",
            detail: "TA 把头转向风来的地方，像在听一首很远的歌。",
            latitude: 49.2827,
            longitude: -123.1207,
            tintHex: 0x78B7C5,
            sceneIcon: "water.waves",
            focusDistance: 1_100_000
        ),
        WorldLifeEvent(
            id: "buenosaires-market",
            city: "布宜诺斯艾利斯",
            place: "集市入口",
            petName: "小满",
            petType: .dog,
            activity: "在闻面包香",
            detail: "TA 停在摊位旁边，鼻尖轻轻动了一下。",
            latitude: -34.6037,
            longitude: -58.3816,
            tintHex: 0xD99A62,
            sceneIcon: "basket.fill",
            focusDistance: 1_200_000
        )
    ]
}

private struct WorldEventDetailCard: View {
    var event: WorldLifeEvent
    var onClose: () -> Void
    var onResetWorld: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .top, spacing: 12) {
                ZStack {
                    RoundedRectangle(cornerRadius: 18, style: .continuous)
                        .fill(event.tint.opacity(0.16))
                    VStack(spacing: 5) {
                        PetSoulAdaptiveIcon(
                            systemImage: event.sceneIcon,
                            tint: event.tint,
                            size: 38
                        )
                        Image(systemName: event.petType.symbolName)
                            .font(.system(size: 18, weight: .semibold))
                            .foregroundStyle(DesignTokens.ink.opacity(0.78))
                    }
                }
                .frame(width: 72, height: 72)

                VStack(alignment: .leading, spacing: 5) {
                    Text("\(event.city) · \(event.place)")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(Color(hex: 0x9E7866))
                    Text(event.activity)
                        .font(.headline.weight(.semibold))
                        .foregroundStyle(DesignTokens.ink)
                    Text("\(event.petName) \(event.detail)")
                        .font(.subheadline)
                        .foregroundStyle(DesignTokens.secondaryInk)
                        .lineSpacing(3)
                        .fixedSize(horizontal: false, vertical: true)
                }

                Spacer(minLength: 0)

                Button(action: onClose) {
                    Image(systemName: "xmark")
                        .font(.caption.weight(.bold))
                        .foregroundStyle(DesignTokens.secondaryInk)
                        .frame(width: 28, height: 28)
                        .background(.white.opacity(0.78))
                        .clipShape(Circle())
                }
                .buttonStyle(.plain)
                .accessibilityLabel("关闭事件卡")
            }

            HStack(spacing: 10) {
                Button(action: onResetWorld) {
                    Label("回到地球", systemImage: "globe")
                        .frame(maxWidth: .infinity)
                }
                .quietActionStyle()

                Button(action: onClose) {
                    Label("继续放大", systemImage: "plus.magnifyingglass")
                        .frame(maxWidth: .infinity)
                }
                .quietActionStyle()
            }
        }
        .padding(16)
        .background(.white.opacity(0.94))
        .clipShape(RoundedRectangle(cornerRadius: 22, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 22, style: .continuous)
                .stroke(.white.opacity(0.76), lineWidth: 1)
        }
        .shadow(color: Color(hex: 0x7D5F54).opacity(0.13), radius: 24, x: 0, y: 12)
    }
}

private struct WorldLiveStoryTicker: View {
    private let storyInterval: TimeInterval = 4.2

    var body: some View {
        TimelineView(.periodic(from: .now, by: storyInterval)) { timeline in
            let event = currentEvent(at: timeline.date)

            HStack(spacing: 10) {
                ZStack {
                    SignalPulseRings(tint: event.tint, size: 38, lineWidth: 1.1, ringCount: 2)
                        .opacity(0.62)
                    PetSoulAdaptiveIcon(
                        systemImage: event.sceneIcon,
                        tint: event.tint,
                        size: 24
                    )
                }
                .frame(width: 34, height: 34)

                VStack(alignment: .leading, spacing: 2) {
                    Text("\(event.petName) · \(event.city)")
                        .font(.caption.weight(.bold))
                        .foregroundStyle(DesignTokens.ink)
                        .lineLimit(1)
                    Text(event.activity)
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(DesignTokens.secondaryInk)
                        .lineLimit(1)
                        .minimumScaleFactor(0.75)
                }

                Spacer(minLength: 0)

                HStack(spacing: 4) {
                    Circle()
                        .fill(event.tint)
                        .frame(width: 6, height: 6)
                    Text("刚刚")
                        .font(.caption2.weight(.semibold))
                }
                .foregroundStyle(event.tint)
                .padding(.vertical, 5)
                .padding(.horizontal, 8)
                .background(event.tint.opacity(0.10))
                .clipShape(Capsule())
            }
            .padding(.vertical, 9)
            .padding(.horizontal, 10)
            .background(Color(hex: 0xFFF9F1).opacity(0.84))
            .clipShape(RoundedRectangle(cornerRadius: 17, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: 17, style: .continuous)
                    .stroke(.white.opacity(0.72), lineWidth: 1)
            }
            .id(event.id)
            .transition(.opacity.combined(with: .move(edge: .bottom)))
            .animation(.easeInOut(duration: 0.35), value: event.id)
        }
    }

    private func currentEvent(at date: Date) -> WorldLifeEvent {
        guard !WorldLifeEvent.samples.isEmpty else {
            return WorldLifeEvent(
                id: "world-empty",
                city: "世界",
                place: "云层边缘",
                petName: "TA",
                petType: .dog,
                activity: "在等一个熟悉的信号",
                detail: "手机正在寻找。",
                latitude: 0,
                longitude: 0,
                tintHex: 0xD6AA63,
                sceneIcon: "sparkles"
            )
        }

        let index = Int(date.timeIntervalSinceReferenceDate / storyInterval) % WorldLifeEvent.samples.count
        return WorldLifeEvent.samples[index]
    }
}

private struct WorldSignalRibbon: View {
    var body: some View {
        HStack(spacing: 8) {
            WorldSignalMetric(title: "活跃信号", value: "128", tint: DesignTokens.sea, systemImage: "dot.radiowaves.left.and.right")
            WorldSignalMetric(title: "正在停留", value: "42", tint: DesignTokens.sage, systemImage: "mappin.and.ellipse")
            WorldSignalMetric(title: "新明信片", value: "7", tint: DesignTokens.clay, systemImage: "mail.stack")
        }
    }
}

private struct WorldSignalMetric: View {
    var title: String
    var value: String
    var tint: Color
    var systemImage: String

    var body: some View {
        HStack(spacing: 7) {
            ZStack {
                SignalPulseRings(tint: tint, size: 36, lineWidth: 1.1, ringCount: 2)
                    .opacity(0.72)
                Image(systemName: systemImage)
                    .font(.caption.weight(.bold))
                    .foregroundStyle(tint)
            }
            .frame(width: 30, height: 30)

            VStack(alignment: .leading, spacing: 1) {
                Text(value)
                    .font(.caption.weight(.bold))
                    .foregroundStyle(DesignTokens.ink)
                Text(title)
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(DesignTokens.secondaryInk)
                    .lineLimit(1)
                    .minimumScaleFactor(0.72)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.vertical, 8)
        .padding(.horizontal, 8)
        .background(.white.opacity(0.62))
        .clipShape(RoundedRectangle(cornerRadius: 15, style: .continuous))
    }
}

private struct WorldPill: View {
    var title: String
    var systemImage: String

    var body: some View {
        Label(title, systemImage: systemImage)
            .font(.caption.weight(.semibold))
            .foregroundStyle(DesignTokens.secondaryInk)
            .lineLimit(1)
            .minimumScaleFactor(0.78)
            .frame(maxWidth: .infinity)
            .padding(.vertical, 9)
            .background(Color(hex: 0xFFF8F1).opacity(0.88))
            .clipShape(Capsule())
    }
}

private enum WorldAnimalField {
    private enum Habitat: Int {
        case cafe
        case food
        case coast
        case pier
        case park
        case shop
        case window
        case market
        case rain
        case snow
        case boat
        case garden
    }

    private struct Story {
        var activity: String
        var detail: String
        var icon: String
        var tintHex: UInt
    }

    private struct Anchor {
        var id: String
        var city: String
        var place: String
        var latitude: Double
        var longitude: Double
        var habitat: Habitat

        var coordinate: CLLocationCoordinate2D {
            CLLocationCoordinate2D(latitude: latitude, longitude: longitude)
        }
    }

    private static let petNames = [
        "Momo", "Luna", "年年", "小宝", "团团", "Sugar", "豆豆", "Nori", "米粒", "Coco", "橘子", "Lucky"
    ]

    private static let anchors: [Anchor] = [
        Anchor(id: "paris-cafe", city: "巴黎", place: "街角咖啡馆", latitude: 48.8566, longitude: 2.3522, habitat: .cafe),
        Anchor(id: "lisbon-pier", city: "里斯本", place: "海边长椅", latitude: 38.7223, longitude: -9.1393, habitat: .coast),
        Anchor(id: "cairo-lamp", city: "开罗", place: "夜灯下面", latitude: 30.0444, longitude: 31.2357, habitat: .window),
        Anchor(id: "dubai-window", city: "迪拜", place: "玻璃窗边", latitude: 25.2048, longitude: 55.2708, habitat: .window),
        Anchor(id: "tokyo-shop", city: "东京", place: "一间小食堂", latitude: 35.6764, longitude: 139.6500, habitat: .food),
        Anchor(id: "seoul-book", city: "首尔", place: "旧书店窗下", latitude: 37.5665, longitude: 126.9780, habitat: .shop),
        Anchor(id: "capetown-park", city: "开普敦", place: "公园小路", latitude: -33.9249, longitude: 18.4241, habitat: .park),
        Anchor(id: "reykjavik-window", city: "雷克雅未克", place: "亮着灯的窗边", latitude: 64.1466, longitude: -21.9426, habitat: .snow),
        Anchor(id: "sydney-flower", city: "悉尼", place: "花店门口", latitude: -33.8688, longitude: 151.2093, habitat: .shop),
        Anchor(id: "bangkok-rain", city: "曼谷", place: "雨后的路口", latitude: 13.7563, longitude: 100.5018, habitat: .rain),
        Anchor(id: "newyork-cart", city: "纽约", place: "路边咖啡车", latitude: 40.7128, longitude: -74.0060, habitat: .cafe),
        Anchor(id: "vancouver-pier", city: "温哥华", place: "码头边", latitude: 49.2827, longitude: -123.1207, habitat: .pier),
        Anchor(id: "buenosaires-market", city: "布宜诺斯艾利斯", place: "集市入口", latitude: -34.6037, longitude: -58.3816, habitat: .market),
        Anchor(id: "london-park", city: "伦敦", place: "公园草地", latitude: 51.5072, longitude: -0.1276, habitat: .park),
        Anchor(id: "amsterdam-canal", city: "阿姆斯特丹", place: "运河边", latitude: 52.3676, longitude: 4.9041, habitat: .coast),
        Anchor(id: "copenhagen-harbor", city: "哥本哈根", place: "港口木栈道", latitude: 55.6761, longitude: 12.5683, habitat: .pier),
        Anchor(id: "istanbul-ferry", city: "伊斯坦布尔", place: "渡船甲板", latitude: 41.0082, longitude: 28.9784, habitat: .boat),
        Anchor(id: "athens-alley", city: "雅典", place: "白墙小巷", latitude: 37.9838, longitude: 23.7275, habitat: .cafe),
        Anchor(id: "rome-fountain", city: "罗马", place: "喷泉旁边", latitude: 41.9028, longitude: 12.4964, habitat: .garden),
        Anchor(id: "barcelona-beach", city: "巴塞罗那", place: "海边步道", latitude: 41.3851, longitude: 2.1734, habitat: .coast),
        Anchor(id: "marrakesh-market", city: "马拉喀什", place: "香料集市", latitude: 31.6295, longitude: -7.9811, habitat: .market),
        Anchor(id: "nairobi-park", city: "内罗毕", place: "树荫路边", latitude: -1.2921, longitude: 36.8219, habitat: .park),
        Anchor(id: "lagos-cafe", city: "拉各斯", place: "街边小店", latitude: 6.5244, longitude: 3.3792, habitat: .food),
        Anchor(id: "rio-beach", city: "里约", place: "海边台阶", latitude: -22.9068, longitude: -43.1729, habitat: .coast),
        Anchor(id: "mexico-park", city: "墨西哥城", place: "树下长椅", latitude: 19.4326, longitude: -99.1332, habitat: .park),
        Anchor(id: "sanfrancisco-pier", city: "旧金山", place: "码头木板路", latitude: 37.7749, longitude: -122.4194, habitat: .pier),
        Anchor(id: "seattle-book", city: "西雅图", place: "旧书店门口", latitude: 47.6062, longitude: -122.3321, habitat: .shop),
        Anchor(id: "toronto-garden", city: "多伦多", place: "湖边花园", latitude: 43.6532, longitude: -79.3832, habitat: .garden),
        Anchor(id: "miami-coast", city: "迈阿密", place: "海边小路", latitude: 25.7617, longitude: -80.1918, habitat: .coast),
        Anchor(id: "anchorage-snow", city: "安克雷奇", place: "雪后的窗边", latitude: 61.2176, longitude: -149.8997, habitat: .snow),
        Anchor(id: "honolulu-shore", city: "檀香山", place: "海边树影下", latitude: 21.3099, longitude: -157.8581, habitat: .coast),
        Anchor(id: "singapore-garden", city: "新加坡", place: "花园步道", latitude: 1.3521, longitude: 103.8198, habitat: .garden),
        Anchor(id: "hongkong-ferry", city: "香港", place: "渡轮窗边", latitude: 22.3193, longitude: 114.1694, habitat: .boat),
        Anchor(id: "taipei-night", city: "台北", place: "夜市巷口", latitude: 25.0330, longitude: 121.5654, habitat: .market),
        Anchor(id: "shanghai-river", city: "上海", place: "河边步道", latitude: 31.2304, longitude: 121.4737, habitat: .coast),
        Anchor(id: "beijing-hutong", city: "北京", place: "胡同门口", latitude: 39.9042, longitude: 116.4074, habitat: .cafe),
        Anchor(id: "mumbai-stall", city: "孟买", place: "小吃摊旁", latitude: 19.0760, longitude: 72.8777, habitat: .food),
        Anchor(id: "delhi-garden", city: "德里", place: "花园阴影里", latitude: 28.6139, longitude: 77.2090, habitat: .garden),
        Anchor(id: "hanoi-cafe", city: "河内", place: "窄巷咖啡店", latitude: 21.0278, longitude: 105.8342, habitat: .cafe),
        Anchor(id: "jakarta-rain", city: "雅加达", place: "雨后街边", latitude: -6.2088, longitude: 106.8456, habitat: .rain),
        Anchor(id: "bali-shore", city: "巴厘岛", place: "海边台阶", latitude: -8.4095, longitude: 115.1889, habitat: .coast),
        Anchor(id: "manila-bay", city: "马尼拉", place: "海湾栏杆边", latitude: 14.5995, longitude: 120.9842, habitat: .pier),
        Anchor(id: "auckland-pier", city: "奥克兰", place: "码头边", latitude: -36.8509, longitude: 174.7645, habitat: .pier),
        Anchor(id: "oslo-snow", city: "奥斯陆", place: "雪地电车站", latitude: 59.9139, longitude: 10.7522, habitat: .snow),
        Anchor(id: "stockholm-window", city: "斯德哥尔摩", place: "亮灯窗边", latitude: 59.3293, longitude: 18.0686, habitat: .window),
        Anchor(id: "helsinki-harbor", city: "赫尔辛基", place: "港口台阶", latitude: 60.1699, longitude: 24.9384, habitat: .pier),
        Anchor(id: "aegean-ferry", city: "爱琴海", place: "渡船甲板", latitude: 37.7200, longitude: 24.1600, habitat: .boat),
        Anchor(id: "baltic-ferry", city: "波罗的海", place: "船舷旁边", latitude: 59.4800, longitude: 19.1200, habitat: .boat)
    ]

    static func events(for mapView: MKMapView) -> [WorldLifeEvent] {
        let distance = mapView.camera.centerCoordinateDistance
        let tier = zoomTier(for: distance)
        let desiredCount = desiredEventCount(for: distance)
        let visibleAnchors = anchors.filter { contains($0.coordinate, in: mapView.visibleMapRect) }
        let primaryEvents = rankedEvents(from: visibleAnchors, mapView: mapView, tier: tier)
        let companionEvents = companionEvents(
            around: visibleAnchors,
            mapView: mapView,
            tier: tier,
            targetCount: desiredCount - primaryEvents.count
        )

        var events = primaryEvents
        events.append(contentsOf: companionEvents)

        var seen = Set<String>()
        return events
            .filter { seen.insert($0.id).inserted }
            .prefix(desiredCount)
            .map { $0 }
    }

    private static func rankedEvents(from anchors: [Anchor], mapView: MKMapView, tier: Int) -> [WorldLifeEvent] {
        let center = MKMapPoint(mapView.centerCoordinate)
        let distanceWeight = tier == 1 ? 0.16 : 0.72

        return anchors
            .map { anchor in
                let point = MKMapPoint(anchor.coordinate)
                let mapDistance = hypot(point.x - center.x, point.y - center.y) / MKMapRect.world.size.width
                let seed = seed(for: anchor)
                let score = mapDistance * distanceWeight + unit(seed, salt: UInt64(tier)) * (1 - distanceWeight)
                return (event: event(from: anchor, idSuffix: nil, coordinate: anchor.coordinate, tier: tier), score: score)
            }
            .sorted { $0.score < $1.score }
            .map(\.event)
    }

    private static func companionEvents(
        around anchors: [Anchor],
        mapView: MKMapView,
        tier: Int,
        targetCount: Int
    ) -> [WorldLifeEvent] {
        guard tier >= 3, targetCount > 0 else { return [] }

        let companionCount = tier >= 4 ? 4 : 2
        var events: [WorldLifeEvent] = []

        for anchor in anchors {
            let seed = seed(for: anchor)
            let spread = companionSpread(for: anchor.habitat, tier: tier)
            for index in 0..<companionCount {
                let angle = unit(seed, salt: UInt64(20 + index)) * Double.pi * 2
                let radius = spread * (0.35 + unit(seed, salt: UInt64(40 + index)) * 0.65)
                let latitude = clamp(anchor.latitude + sin(angle) * radius, min: -72, max: 72)
                let longitude = normalizedLongitude(anchor.longitude + cos(angle) * radius)
                let coordinate = CLLocationCoordinate2D(latitude: latitude, longitude: longitude)

                guard contains(coordinate, in: mapView.visibleMapRect) else { continue }

                events.append(
                    event(
                        from: anchor,
                        idSuffix: "near-\(index)",
                        coordinate: coordinate,
                        tier: tier,
                        storySalt: UInt64(index + 3)
                    )
                )
            }
        }

        return events
            .sorted { $0.id < $1.id }
            .prefix(targetCount)
            .map { $0 }
    }

    private static func companionSpread(for habitat: Habitat, tier: Int) -> Double {
        switch habitat {
        case .boat:
            return tier >= 4 ? 0.014 : 0.026
        case .pier, .coast:
            return tier >= 4 ? 0.006 : 0.012
        default:
            return tier >= 4 ? 0.004 : 0.009
        }
    }

    private static func event(
        from anchor: Anchor,
        idSuffix: String?,
        coordinate: CLLocationCoordinate2D,
        tier: Int,
        storySalt: UInt64 = 0
    ) -> WorldLifeEvent {
        let seed = seed(for: anchor) &+ storySalt
        let storyPool = stories(for: anchor.habitat)
        let story = storyPool[Int(seed % UInt64(storyPool.count))]
        let petName = petNames[Int((seed >> 8) % UInt64(petNames.count))]
        let visiblePetTypes: [PetType] = [.dog, .cat, .parrot, .rabbit, .hamster, .bird]
        let petType = visiblePetTypes[Int((seed >> 12) % UInt64(visiblePetTypes.count))]
        let suffix = idSuffix.map { "-\($0)" } ?? ""

        return WorldLifeEvent(
            id: "anchor-\(anchor.id)\(suffix)",
            city: anchor.city,
            place: anchor.place,
            petName: petName,
            petType: petType,
            activity: story.activity,
            detail: story.detail,
            latitude: coordinate.latitude,
            longitude: coordinate.longitude,
            tintHex: story.tintHex,
            sceneIcon: story.icon,
            focusDistance: focusDistance(for: tier)
        )
    }

    private static func stories(for habitat: Habitat) -> [Story] {
        switch habitat {
        case .cafe:
            return [
                Story(activity: "在窗边晒太阳", detail: "TA 找到一块很暖的位置，安静地趴了一会儿。", icon: "cup.and.saucer.fill", tintHex: 0xD7A067),
                Story(activity: "在喝招牌饮品", detail: "TA 坐在靠窗的小桌边，慢慢看街上的人经过。", icon: "mug.fill", tintHex: 0xC8956D)
            ]
        case .food:
            return [
                Story(activity: "在吃一小份饭", detail: "TA 没有着急，慢慢吃完一小份适合自己的食物。", icon: "takeoutbag.and.cup.and.straw", tintHex: 0x78A99D),
                Story(activity: "在小店里坐着", detail: "店里传来热乎乎的声音，TA 把耳朵轻轻转了过去。", icon: "fork.knife", tintHex: 0xD98566)
            ]
        case .coast:
            return [
                Story(activity: "在岸边等风", detail: "风从水面吹过来，TA 像听见了很熟悉的声音。", icon: "wind", tintHex: 0x8FB7D0),
                Story(activity: "在海边看浪", detail: "浪花一层一层靠近，TA 安静地坐在栏杆旁边。", icon: "water.waves", tintHex: 0x78B7C5)
            ]
        case .pier:
            return [
                Story(activity: "在码头边听水声", detail: "木板下面传来轻轻的水声，TA 低头看了很久。", icon: "sailboat.fill", tintHex: 0x78B7C5),
                Story(activity: "在栏杆旁看船", detail: "远处有船慢慢经过，TA 的尾巴轻轻晃了一下。", icon: "sailboat.fill", tintHex: 0x6FAFC1)
            ]
        case .boat:
            return [
                Story(activity: "在渡船甲板上吹风", detail: "水面很亮，TA 站在风里，好像正在去一个温柔的地方。", icon: "sailboat.fill", tintHex: 0x6FAFC1),
                Story(activity: "在船舷边看浪", detail: "船慢慢往前走，TA 看着浪花一朵一朵散开。", icon: "sailboat.fill", tintHex: 0x7AA8CB)
            ]
        case .park:
            return [
                Story(activity: "在追一片叶子", detail: "叶子滚了很远，TA 跟着跑了几步，又轻轻停下。", icon: "leaf.fill", tintHex: 0x90B779),
                Story(activity: "在树荫下休息", detail: "树影慢慢移动，TA 把爪子收起来睡了一小会儿。", icon: "tree.fill", tintHex: 0x7FAE74)
            ]
        case .shop:
            return [
                Story(activity: "在小店里挑东西", detail: "TA 好像认出了一种熟悉的小物件，停下来多看了一眼。", icon: "camera.macro", tintHex: 0xD49A9A),
                Story(activity: "在窗边发呆", detail: "TA 抬头看了一会儿橱窗，像在等一封慢慢到来的信。", icon: "book.closed.fill", tintHex: 0xB9A06F)
            ]
        case .window:
            return [
                Story(activity: "在看一盏灯", detail: "那盏灯亮得很软，TA 坐在那里看了好久。", icon: "lightbulb.fill", tintHex: 0xC6B083),
                Story(activity: "在窗边看云", detail: "TA 贴近窗边，认真看着云影从城市上方慢慢走过。", icon: "cloud.sun.fill", tintHex: 0xC6A66A)
            ]
        case .market:
            return [
                Story(activity: "在闻面包香", detail: "TA 停在摊位旁边，鼻尖轻轻动了一下。", icon: "basket.fill", tintHex: 0xD99A62),
                Story(activity: "在集市入口张望", detail: "人声从远处传来，TA 安静地站在不挡路的地方。", icon: "bag.fill", tintHex: 0xC89A68)
            ]
        case .rain:
            return [
                Story(activity: "在踩小水洼", detail: "TA 绕着水洼走了一圈，像发现了一个新的小游戏。", icon: "cloud.rain.fill", tintHex: 0x8FAAC6),
                Story(activity: "在雨棚下等雨停", detail: "雨声落在屋檐上，TA 把身体缩得很小。", icon: "umbrella.fill", tintHex: 0x82A9D3)
            ]
        case .snow:
            return [
                Story(activity: "在窗边看雪", detail: "窗外很安静，TA 把爪子收起来，像一封没有寄出的信。", icon: "snowflake", tintHex: 0x87B8DA),
                Story(activity: "在雪后的小路上走", detail: "TA 每一步都很轻，好像怕踩碎这片安静。", icon: "snowflake", tintHex: 0x91B9D2)
            ]
        case .garden:
            return [
                Story(activity: "在闻一束花", detail: "TA 在门边停了一下，像是认出了某种温柔的味道。", icon: "camera.macro", tintHex: 0xD49A9A),
                Story(activity: "在花园里慢慢走", detail: "草叶碰到脚边，TA 像在记住这条小路。", icon: "leaf.fill", tintHex: 0x90B779)
            ]
        }
    }

    private static func contains(_ coordinate: CLLocationCoordinate2D, in mapRect: MKMapRect) -> Bool {
        let point = MKMapPoint(coordinate)
        let worldWidth = MKMapRect.world.size.width

        return [-worldWidth, 0, worldWidth].contains { offset in
            let x = point.x + offset
            return x >= mapRect.minX
                && x <= mapRect.maxX
                && point.y >= mapRect.minY
                && point.y <= mapRect.maxY
        }
    }

    private static func desiredEventCount(for distance: CLLocationDistance) -> Int {
        switch distance {
        case 72_000_000...: return 4
        case 28_000_000...: return 4
        case 8_000_000...: return 9
        case 2_200_000...: return 16
        default: return 22
        }
    }

    private static func zoomTier(for distance: CLLocationDistance) -> Int {
        switch distance {
        case 28_000_000...: return 1
        case 8_000_000...: return 2
        case 2_200_000...: return 3
        default: return 4
        }
    }

    private static func focusDistance(for tier: Int) -> CLLocationDistance {
        switch tier {
        case 1: return 3_200_000
        case 2: return 1_300_000
        case 3: return 520_000
        default: return 180_000
        }
    }

    private static func stableSeed(_ latKey: Int, _ lonKey: Int, _ tier: Int) -> UInt64 {
        var value = UInt64(bitPattern: Int64(latKey &* 73_856_093))
        let lonValue = UInt64(bitPattern: Int64(lonKey &* 19_349_663))
        value ^= (lonValue << 17) | (lonValue >> 47)
        value ^= UInt64(tier &* 83_492_791)
        value &+= 0x9E3779B97F4A7C15
        value ^= value >> 30
        value &*= 0xBF58476D1CE4E5B9
        value ^= value >> 27
        value &*= 0x94D049BB133111EB
        value ^= value >> 31
        return value
    }

    private static func seed(for anchor: Anchor) -> UInt64 {
        stableSeed(
            Int((anchor.latitude * 1_000).rounded()),
            Int((anchor.longitude * 1_000).rounded()),
            anchor.habitat.rawValue + 1
        )
    }

    private static func unit(_ seed: UInt64, salt: UInt64) -> Double {
        let mixed = stableSeed(Int(seed & 0xFFFF), Int((seed >> 16) & 0xFFFF), Int(salt))
        return Double(mixed % 10_000) / 10_000
    }

    private static func normalizedLongitude(_ longitude: Double) -> Double {
        var value = longitude
        while value > 180 { value -= 360 }
        while value < -180 { value += 360 }
        return value
    }

    private static func clamp(_ value: Double, min: Double, max: Double) -> Double {
        Swift.min(Swift.max(value, min), max)
    }
}

private struct WorldNoteCard: View {
    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: "heart.text.square")
                .font(.title3.weight(.semibold))
                .foregroundStyle(Color(hex: 0xC28A70))
                .frame(width: 32)

            Text("这里是情感陪伴体验，不代表宗教、医疗或真实灵性声明。地图用于营造空间感和旅程感，帮助你继续和 TA 说说话。")
                .font(.footnote)
                .foregroundStyle(DesignTokens.secondaryInk)
                .lineSpacing(4)
        }
        .padding(16)
        .background(.white.opacity(0.94))
        .clipShape(RoundedRectangle(cornerRadius: DesignTokens.controlRadius, style: .continuous))
        .shadow(color: Color(hex: 0x7D5F54).opacity(0.1), radius: 18, x: 0, y: 9)
    }
}

private extension UIColor {
    convenience init(hex: UInt, alpha: CGFloat = 1) {
        self.init(
            red: CGFloat((hex >> 16) & 0xFF) / 255,
            green: CGFloat((hex >> 8) & 0xFF) / 255,
            blue: CGFloat(hex & 0xFF) / 255,
            alpha: alpha
        )
    }
}
