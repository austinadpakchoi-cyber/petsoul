import SwiftUI
import UIKit

struct ConnectingView: View {
    var draft: OnboardingDraft
    let service: any PetJourneyService
    var onBack: () -> Void
    var onEnterJourney: (String) -> Void

    @State private var stageIndex = 0
    @State private var response: CreatePetResponse?
    @State private var errorMessage: String?
    @State private var hasStarted = false
    @State private var dialRotates = false

    private var stages: [(title: String, detail: String, icon: String)] {
        [
            ("调频中", "给 \(draft.name) 留出一个可以抵达的位置", "waveform.path"),
            ("寻找中", "正在 \(draft.petType.searchWorldName) 里辨认熟悉的信号", "dot.radiowaves.left.and.right"),
            ("已连接", "手机已经收到第一段回声", "checkmark.seal.fill")
        ]
    }

    var body: some View {
        ZStack {
            AppBackground()
            AmbientSignalField(
                tint: response == nil ? DesignTokens.sea : DesignTokens.sage,
                warmth: DesignTokens.pollen,
                density: response == nil ? 30 : 18,
                drift: response == nil ? 0.9 : 0.34
            )
            .opacity(response == nil ? 0.82 : 0.48)

            VStack(spacing: 22) {
                Spacer(minLength: 24)

                connectionDial

                VStack(spacing: 8) {
                    Text(stages[stageIndex].title)
                        .font(.system(size: 36, weight: .semibold, design: .rounded))
                        .foregroundStyle(DesignTokens.ink)
                    Text(stages[stageIndex].detail)
                        .font(.body)
                        .foregroundStyle(DesignTokens.secondaryInk)
                        .multilineTextAlignment(.center)
                        .lineSpacing(3)
                }
                .padding(.horizontal, 26)

                StageDots(count: stages.count, activeIndex: stageIndex)
                stageTimeline

                if let response {
                    communicatorCard(response: response)
                        .transition(.move(edge: .bottom).combined(with: .opacity))

                    Button {
                        onEnterJourney(response.petID)
                    } label: {
                        Label("打开手机", systemImage: "rectangle.connected.to.line.below")
                    }
                    .primaryActionStyle()
                    .padding(.horizontal, DesignTokens.pagePadding)
                } else if let errorMessage {
                    errorCard(message: errorMessage)
                } else {
                    Text("请稍等片刻")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(DesignTokens.secondaryInk)
                        .padding(.vertical, 9)
                        .padding(.horizontal, 14)
                        .background(DesignTokens.surface.opacity(0.72))
                        .clipShape(Capsule())
                }

                Spacer(minLength: 24)
            }
        }
        .task {
            guard !hasStarted else { return }
            hasStarted = true
            await runConnection()
        }
        .onAppear {
            withAnimation(.linear(duration: 12).repeatForever(autoreverses: false)) {
                dialRotates = true
            }
        }
    }

    private var connectionDial: some View {
        SoulSearchDial(
            draft: draft,
            icon: stages[stageIndex].icon,
            stageIndex: stageIndex,
            isConnected: response != nil,
            rotates: dialRotates
        )
    }

    private var stageTimeline: some View {
        HStack(spacing: 8) {
            ForEach(stages.indices, id: \.self) { index in
                let isActive = index == stageIndex
                let isFinished = index < stageIndex

                HStack(spacing: 6) {
                    Image(systemName: isFinished ? "checkmark" : stages[index].icon)
                        .font(.caption.weight(.bold))
                    Text(["留位", "辨认", "回声"][index])
                        .font(.caption.weight(.semibold))
                }
                .foregroundStyle(isActive || isFinished ? DesignTokens.ink : DesignTokens.secondaryInk)
                .padding(.vertical, 8)
                .padding(.horizontal, 10)
                .background((isActive ? DesignTokens.pollen.opacity(0.24) : DesignTokens.surface.opacity(0.62)))
                .clipShape(Capsule())
                .overlay {
                    Capsule()
                        .stroke((isActive ? DesignTokens.pollen : DesignTokens.softLine).opacity(0.58), lineWidth: 1)
                }
            }
        }
    }

    private func errorCard(message: String) -> some View {
        SoftCard {
            Text(message)
                .font(.subheadline)
                .foregroundStyle(DesignTokens.secondaryInk)

            HStack {
                Button(action: onBack) {
                    Label("返回", systemImage: "chevron.left")
                }
                .quietActionStyle()

                Button {
                    Task { await runConnection() }
                } label: {
                    Label("重试", systemImage: "arrow.clockwise")
                }
                .quietActionStyle()
            }
        }
        .padding(.horizontal, DesignTokens.pagePadding)
    }

    private func runConnection() async {
        errorMessage = nil
        response = nil
        do {
            withAnimation(.easeInOut(duration: 0.25)) { stageIndex = 0 }
            try await Task.sleep(for: .seconds(1))
            withAnimation(.easeInOut(duration: 0.25)) { stageIndex = 1 }
            try await Task.sleep(for: .seconds(1.2))
            let created = try await service.createPet(request: draft.createRequest)
            if let photoData = draft.photoData {
                PetAvatarStore.save(photoData, petID: created.petID)
            }
            withAnimation(.easeInOut(duration: 0.25)) {
                response = created
                stageIndex = 2
            }
        } catch {
            errorMessage = "这次连接没有稳定下来，可以稍后再试。"
        }
    }

    private func communicatorCard(response: CreatePetResponse) -> some View {
        SoftCard(padding: 18) {
            HStack(spacing: 14) {
                petImage

                VStack(alignment: .leading, spacing: 7) {
                    Text("\(response.name) 的通讯卡")
                        .font(.title3.weight(.semibold))
                        .foregroundStyle(DesignTokens.ink)
                    Text(response.petID)
                        .font(.caption.monospaced())
                        .foregroundStyle(DesignTokens.secondaryInk)
                    Text("第一站：\(response.location)。TA 的旅程已经开始。")
                        .font(.footnote)
                        .foregroundStyle(DesignTokens.secondaryInk)
                        .lineLimit(2)
                }
            }
        }
        .padding(.horizontal, DesignTokens.pagePadding)
    }

    @ViewBuilder
    private var petImage: some View {
        if let data = draft.photoData, let image = UIImage(data: data) {
            Image(uiImage: image)
                .resizable()
                .scaledToFill()
                .frame(width: 76, height: 90)
                .clipShape(RoundedRectangle(cornerRadius: DesignTokens.cardRadius, style: .continuous))
        } else {
            ZStack {
                RoundedRectangle(cornerRadius: DesignTokens.cardRadius, style: .continuous)
                    .fill(DesignTokens.petal)
                Image(systemName: draft.petType.symbolName)
                    .font(.system(size: 28, weight: .semibold))
                    .foregroundStyle(DesignTokens.clay)
            }
            .frame(width: 76, height: 90)
        }
    }
}

private struct SoulSearchDial: View {
    var draft: OnboardingDraft
    var icon: String
    var stageIndex: Int
    var isConnected: Bool
    var rotates: Bool

    private var stageTint: Color {
        switch stageIndex {
        case 0: DesignTokens.sea
        case 1: DesignTokens.pollen
        default: DesignTokens.sage
        }
    }

    var body: some View {
        ZStack {
            SignalPulseRings(tint: stageTint, size: 286, lineWidth: 1.8, ringCount: isConnected ? 2 : 4)
                .opacity(isConnected ? 0.74 : 1)

            Circle()
                .stroke(stageTint.opacity(0.15), lineWidth: 18)
                .frame(width: 232, height: 232)

            Circle()
                .trim(from: 0.06, to: 0.36)
                .stroke(stageTint.opacity(0.72), style: StrokeStyle(lineWidth: 3, lineCap: .round))
                .frame(width: 244, height: 244)
                .rotationEffect(.degrees(rotates ? 360 : 0))

            Circle()
                .trim(from: 0.58, to: 0.86)
                .stroke(DesignTokens.clay.opacity(0.48), style: StrokeStyle(lineWidth: 2, lineCap: .round))
                .frame(width: 196, height: 196)
                .rotationEffect(.degrees(rotates ? -360 : 0))

            ForEach(0..<9, id: \.self) { index in
                let angle = Double(index) / 9 * Double.pi * 2
                let radius: CGFloat = index.isMultiple(of: 2) ? 122 : 98
                Circle()
                    .fill((index.isMultiple(of: 3) ? DesignTokens.clay : stageTint).opacity(index == stageIndex + 3 ? 0.92 : 0.52))
                    .frame(width: index == stageIndex + 3 ? 9 : 5, height: index == stageIndex + 3 ? 9 : 5)
                    .offset(
                        x: CGFloat(cos(angle)) * radius,
                        y: CGFloat(sin(angle)) * radius
                    )
            }

            centerPortrait

            Image(systemName: icon)
                .font(.system(size: 19, weight: .semibold))
                .foregroundStyle(stageTint)
                .frame(width: 42, height: 42)
                .background(DesignTokens.surface.opacity(0.92))
                .clipShape(Circle())
                .shadow(color: DesignTokens.deepInk.opacity(0.1), radius: 14, x: 0, y: 7)
                .offset(x: 72, y: 72)

            if isConnected {
                Image(systemName: "checkmark.seal.fill")
                    .font(.system(size: 34, weight: .semibold))
                    .foregroundStyle(DesignTokens.sage)
                    .frame(width: 56, height: 56)
                    .background(DesignTokens.surface.opacity(0.94))
                    .clipShape(Circle())
                    .shadow(color: DesignTokens.sage.opacity(0.25), radius: 18, x: 0, y: 8)
                    .offset(x: 74, y: -70)
                    .transition(.scale.combined(with: .opacity))
            }
        }
        .frame(width: 292, height: 292)
    }

    @ViewBuilder
    private var centerPortrait: some View {
        ZStack {
            Circle()
                .fill(DesignTokens.surface.opacity(0.88))
                .frame(width: 146, height: 146)
                .shadow(color: DesignTokens.deepInk.opacity(0.12), radius: 30, x: 0, y: 16)

            Circle()
                .fill(stageTint.opacity(0.13))
                .frame(width: 118, height: 118)

            if let data = draft.photoData, let image = UIImage(data: data) {
                Image(uiImage: image)
                    .resizable()
                    .scaledToFill()
                    .frame(width: 108, height: 108)
                    .clipShape(Circle())
                    .overlay {
                        Circle().stroke(DesignTokens.surfaceStroke.opacity(0.92), lineWidth: 3)
                    }
            } else {
                Image(systemName: draft.petType.symbolName)
                    .font(.system(size: 44, weight: .semibold))
                    .foregroundStyle(DesignTokens.clay)
                    .frame(width: 108, height: 108)
                    .background(DesignTokens.petal.opacity(0.92))
                    .clipShape(Circle())
            }
        }
    }
}

private struct StageDots: View {
    var count: Int
    var activeIndex: Int

    var body: some View {
        HStack(spacing: 7) {
            ForEach(0..<count, id: \.self) { index in
                Capsule()
                    .fill(index <= activeIndex ? DesignTokens.sage : DesignTokens.softLine)
                    .frame(width: index == activeIndex ? 22 : 7, height: 7)
                    .animation(.easeInOut(duration: 0.22), value: activeIndex)
            }
        }
    }
}
