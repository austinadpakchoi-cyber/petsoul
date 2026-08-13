import Foundation

@MainActor
extension JourneyViewModel {
    func updateDNA(_ nextDNA: PetDNA) async {
        isUpdatingDNA = true
        defer { isUpdatingDNA = false }
        do {
            dna = try await service.updateDNA(petID: petID, dna: nextDNA)
            toastMessage = "通讯 DNA 已更新。"
        } catch {
            toastMessage = "通讯 DNA 暂时保存失败。"
        }
    }

    func generateIllustratedGuideIfNeeded(_ guide: IllustratedGuide) async {
        guard illustratedGuideNeedsImage(guide), !isGeneratingIllustratedGuide else { return }
        guard !illustratedGuideGenerationIDs.contains(guide.id) else { return }
        illustratedGuideGenerationIDs.insert(guide.id)
        isGeneratingIllustratedGuide = true
        defer { isGeneratingIllustratedGuide = false }

        do {
            let generatedGuide = try await service.generateIllustratedGuide(petID: petID)
            illustratedGuide = generatedGuide
            if illustratedGuideHasImage(generatedGuide) {
                toastMessage = "TA 的手绘旅程图画好了。"
            } else if generatedGuide.status == .failed {
                toastMessage = "这套手账图暂时没画出来，稍后再试。"
            }
        } catch {
            toastMessage = "手绘旅程图还在路上，信号好一点会再试。"
        }
    }

    func illustratedGuideNeedsImage(_ guide: IllustratedGuide) -> Bool {
        if illustratedGuideHasImage(guide), guide.status == .ready {
            return false
        }
        guard let pages = guide.pages, !pages.isEmpty else {
            return guide.imageURL == nil && guide.thumbnailURL == nil
        }
        return pages.contains { $0.imageURL == nil && $0.thumbnailURL == nil }
    }

    func illustratedGuideHasImage(_ guide: IllustratedGuide) -> Bool {
        if guide.imageURL != nil || guide.thumbnailURL != nil {
            return true
        }
        return guide.pages?.contains { $0.imageURL != nil || $0.thumbnailURL != nil } ?? false
    }

    func refreshRoutePlan() async {
        do {
            let nextJourneyPlan = try await service.fetchJourneyPlan(petID: petID)
            journeyPlan = nextJourneyPlan
            remoteRoutePlan = nextJourneyPlan.compatibilityRoutePlan
        } catch {
            do {
                journeyPlan = nil
                remoteRoutePlan = try await service.fetchRoutePlan(petID: petID)
            } catch {
                toastMessage = "路线还没有同步完整。"
            }
        }
    }

    func refreshPhotoMission() async {
        do {
            photoMission = try await service.fetchPhotoMission(petID: petID)
        } catch {
            photoMission = nil
        }
    }

    func hasReceivedPhotoMission(_ mission: PhotoMission?) -> Bool {
        guard let mission else { return false }
        return receivedPhotoMissionIDs.contains(mission.id)
    }

    func translateLatestThought() async {
        guard let thought = status?.agentState.latestThought else { return }
        if visibleThoughtTranslation?.thoughtID == thought.id {
            visibleThoughtTranslation = nil
            return
        }
        if let cached = translationCache[thought.id] {
            visibleThoughtTranslation = cached
            return
        }
        guard thought.translationAvailable else {
            toastMessage = "这句话还没有翻译出来。"
            return
        }

        isTranslatingThought = true
        defer { isTranslatingThought = false }
        do {
            let translation = try await service.fetchThoughtTranslation(petID: petID, thoughtID: thought.id)
            translationCache[thought.id] = translation
            visibleThoughtTranslation = translation
        } catch {
            toastMessage = "翻译信号有点弱，稍后再试。"
        }
    }

    func receiveCurrentPhoto() async {
        guard !isGeneratingPhoto else { return }
        isGeneratingPhoto = true
        defer { isGeneratingPhoto = false }

        do {
            let missionID = photoMission?.id
            _ = try await service.generateSelfie(petID: petID)
            if let missionID {
                markPhotoMissionReceived(missionID)
            }
            hasUnreadPostcard = true
            toastMessage = "手机里多了一张此刻照片。"
            PetPushRegistrationCoordinator.shared.requestAuthorizationForUserMoment()
            await refreshStatus()
            await refreshPhotoMission()
        } catch {
            toastMessage = "这张照片还没准备好。"
        }
    }

    func markPhotoMissionReceived(_ missionID: String) {
        receivedPhotoMissionIDs.insert(missionID)
        UserDefaults.standard.set(Array(receivedPhotoMissionIDs), forKey: receivedPhotoMissionStorageKey)
    }
}
