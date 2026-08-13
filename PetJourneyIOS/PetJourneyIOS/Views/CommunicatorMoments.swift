import PhotosUI
import SwiftUI
import UIKit

struct MomentsView: View {
    @ObservedObject var viewModel: CommunicatorViewModel

    var body: some View {
        ScrollView {
            LazyVStack(spacing: 12) {
                if viewModel.friendsCircleMoments.isEmpty {
                    ChatEmptyState(
                        title: "朋友圈还很安静",
                        detail: "\(viewModel.petName) 遇到想分享的一刻时，会自己发一条动态。",
                        systemImage: "sparkles"
                    )
                }
                ForEach(viewModel.friendsCircleMoments) { moment in
                    MomentCard(moment: moment, petName: viewModel.petName, petType: viewModel.petType) { reaction in
                        Task { await viewModel.react(to: moment, reaction: reaction) }
                    }
                }
            }
            .padding(DesignTokens.pagePadding)
        }
        .background(AppBackground())
        .navigationTitle("朋友圈")
        .navigationBarTitleDisplayMode(.inline)
        .task {
            if viewModel.friendsCircleMoments.isEmpty {
                await viewModel.load()
            }
        }
    }
}

struct MomentCard: View {
    var moment: CommunicatorMoment
    var petName: String
    var petType: PetType?
    var onReact: (MomentReaction) -> Void

    var body: some View {
        SoftCard {
            VStack(alignment: .leading, spacing: 10) {
                HStack(spacing: 9) {
                    PetChatAvatar(petID: moment.petID, petType: petType, size: 34)
                    VStack(alignment: .leading, spacing: 2) {
                        Text(petName)
                            .font(.subheadline.weight(.semibold))
                            .foregroundStyle(DesignTokens.ink)
                        Text(headerLine)
                            .font(.caption)
                            .foregroundStyle(DesignTokens.secondaryInk)
                    }
                    Spacer(minLength: 0)
                }

                Text(moment.text)
                    .font(.subheadline)
                    .foregroundStyle(DesignTokens.ink)
                    .lineSpacing(3)

                ForEach(moment.friendsCircleAttachments) { attachment in
                    CommunicatorAttachmentView(attachment: attachment)
                }

                MomentSocialReactorRow(reactors: moment.socialReactors ?? [])

                HStack(spacing: 8) {
                    ForEach(MomentReaction.allCases) { reaction in
                        Button {
                            onReact(reaction)
                        } label: {
                            Label(reactionTitle(for: reaction), systemImage: reaction.systemImage)
                                .font(.caption.weight(.semibold))
                                .foregroundStyle(moment.ownerReaction == reaction ? .white : DesignTokens.secondaryInk)
                                .padding(.vertical, 7)
                                .padding(.horizontal, 9)
                                .background(moment.ownerReaction == reaction ? DesignTokens.sage : DesignTokens.mist.opacity(0.64))
                                .clipShape(Capsule())
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
        }
    }

    var headerLine: String {
        let place = [moment.location?.city, moment.location?.placeName].compactMap { $0 }.joined(separator: " · ")
        let time = moment.createdAt.formatted(date: .omitted, time: .shortened)
        return place.isEmpty ? time : "\(time) · \(place)"
    }

    func reactionTitle(for reaction: MomentReaction) -> String {
        let count = moment.reactions[reaction.rawValue] ?? 0
        return count > 0 ? "\(reaction.displayName) \(count)" : reaction.displayName
    }
}

extension CommunicatorMoment {
    var friendsCircleAttachments: [CommunicatorAttachment] {
        attachments.filter { $0.isVisibleInFriendsCircle }
    }

    var isReadyForFriendsCircle: Bool {
        let photoAttachments = attachments.filter { $0.isPhotoLike }
        if !photoAttachments.isEmpty {
            return photoAttachments.contains { $0.hasReadyPhoto }
        }
        return !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || !friendsCircleAttachments.isEmpty
    }
}

extension CommunicatorAttachment {
    var isPhotoLike: Bool {
        type == .photo || type == .photoPlaceholder || type == .pendingPhotoRequest
    }

    var hasReadyPhoto: Bool {
        type == .photo && photoURL != nil && state != "placeholder"
    }

    var isVisibleInFriendsCircle: Bool {
        switch type {
        case .photo:
            hasReadyPhoto
        case .photoPlaceholder, .pendingPhotoRequest, .photoStatusCard:
            false
        default:
            true
        }
    }
}

struct MomentSocialReactorRow: View {
    var reactors: [MomentSocialReactor]

    var body: some View {
        if !reactors.isEmpty {
            HStack(spacing: 9) {
                avatarStack
                    .frame(width: min(CGFloat(reactors.count) * 18 + 18, 72), height: 28, alignment: .leading)

                Text(summary)
                    .font(.caption.weight(.medium))
                    .foregroundStyle(DesignTokens.secondaryInk)
                    .lineLimit(2)

                Spacer(minLength: 0)
            }
            .padding(.vertical, 7)
            .padding(.horizontal, 9)
            .background(DesignTokens.mist.opacity(0.48))
            .clipShape(Capsule())
        }
    }

    var avatarStack: some View {
        ZStack(alignment: .leading) {
            ForEach(Array(reactors.prefix(4).enumerated()), id: \.element.id) { index, reactor in
                Text(reactor.avatarEmoji)
                    .font(.caption)
                    .frame(width: 26, height: 26)
                    .background(DesignTokens.surface.opacity(0.86))
                    .clipShape(Circle())
                    .overlay(Circle().stroke(DesignTokens.surfaceStroke, lineWidth: 1))
                    .offset(x: CGFloat(index) * 17)
            }
        }
    }

    var summary: String {
        let names = reactors.prefix(2).map(\.name).joined(separator: "、")
        let extraCount = max(0, reactors.count - 2)
        if extraCount > 0 {
            return "\(names) 和 \(extraCount) 位朋友回应了这一刻"
        }
        return "\(names) 回应了这一刻"
    }
}
