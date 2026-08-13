import MapKit
import SwiftUI
import UIKit

final class WorldAnimalBadgeView: UIControl {
    var event: WorldLifeEvent

    let container = UIVisualEffectView(effect: UIBlurEffect(style: .systemThinMaterialLight))
    let compactContainer = UIVisualEffectView(effect: UIBlurEffect(style: .systemThinMaterialLight))
    let iconCircle = UIView()
    let iconView = UIImageView()
    let compactIconCircle = UIView()
    let compactIconView = UIImageView()
    let compactDot = UIView()
    let titleLabel = UILabel()
    let subtitleLabel = UILabel()
    let dot = UIView()
    var isCompact = false

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

    func applyPresentation(compact: Bool) {
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

    func setup() {
        container.frame = bounds
        container.layer.cornerRadius = 22
        container.layer.cornerCurve = .continuous
        container.clipsToBounds = true
        container.contentView.backgroundColor = DesignTokens.annotation.cardSurface.withAlphaComponent(0.40)
        container.isUserInteractionEnabled = false
        addSubview(container)

        compactContainer.frame = CGRect(x: 0, y: 0, width: 44, height: 44)
        compactContainer.layer.cornerRadius = 22
        compactContainer.layer.cornerCurve = .continuous
        compactContainer.clipsToBounds = true
        compactContainer.contentView.backgroundColor = DesignTokens.annotation.cardSurface.withAlphaComponent(0.44)
        compactContainer.isUserInteractionEnabled = false
        compactContainer.isHidden = true
        addSubview(compactContainer)

        layer.shadowColor = DesignTokens.annotation.shadowBrown.cgColor
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
        titleLabel.textColor = DesignTokens.annotation.titleInk

        subtitleLabel.translatesAutoresizingMaskIntoConstraints = false
        subtitleLabel.font = .systemFont(ofSize: 8.8, weight: .semibold)
        subtitleLabel.textColor = DesignTokens.annotation.subtitleInk
        subtitleLabel.lineBreakMode = .byTruncatingTail

        dot.translatesAutoresizingMaskIntoConstraints = false
        dot.layer.cornerRadius = 4
        dot.layer.borderColor = DesignTokens.annotation.cardSurface.cgColor
        dot.layer.borderWidth = 1.4

        compactDot.translatesAutoresizingMaskIntoConstraints = false
        compactDot.layer.cornerRadius = 3.5
        compactDot.layer.borderColor = DesignTokens.annotation.cardSurface.cgColor
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

final class WorldEventAnnotationView: MKAnnotationView {
    static let reuseIdentifier = "WorldEventAnnotationView"

    let container = UIVisualEffectView(effect: UIBlurEffect(style: .systemThinMaterialLight))
    let iconCircle = UIView()
    let iconView = UIImageView()
    let titleLabel = UILabel()
    let subtitleLabel = UILabel()
    let dot = UIView()

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
        subtitleLabel.textColor = event.isGenerated ? DesignTokens.annotation.generatedInk : DesignTokens.annotation.subtitleInk
        accessibilityLabel = "\(event.city)，\(event.activity)"
    }

    override var isSelected: Bool {
        didSet {
            UIView.animate(withDuration: 0.2) {
                self.transform = self.isSelected ? CGAffineTransform(scaleX: 1.08, y: 1.08) : .identity
                self.container.contentView.backgroundColor = self.isSelected
                    ? DesignTokens.annotation.cardSurface.withAlphaComponent(0.58)
                    : DesignTokens.annotation.cardSurface.withAlphaComponent(0.36)
            }
        }
    }

    func setup() {
        container.frame = bounds
        container.layer.cornerRadius = 22
        container.layer.cornerCurve = .continuous
        container.clipsToBounds = true
        container.contentView.backgroundColor = DesignTokens.annotation.cardSurface.withAlphaComponent(0.40)
        addSubview(container)

        layer.shadowColor = DesignTokens.annotation.shadowBrown.cgColor
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
        titleLabel.textColor = DesignTokens.annotation.titleInk

        subtitleLabel.translatesAutoresizingMaskIntoConstraints = false
        subtitleLabel.font = .systemFont(ofSize: 8.8, weight: .semibold)
        subtitleLabel.textColor = DesignTokens.annotation.subtitleInk
        subtitleLabel.lineBreakMode = .byTruncatingTail

        dot.translatesAutoresizingMaskIntoConstraints = false
        dot.layer.cornerRadius = 5
        dot.layer.borderColor = DesignTokens.annotation.cardSurface.cgColor
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
