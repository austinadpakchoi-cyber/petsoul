import Foundation

@MainActor
extension JourneyViewModel {
    func start() {
        guard refreshTask == nil else { return }
        refreshTask = Task { [weak self] in
            guard let self else { return }
            await self.loadInitial()
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(5))
                if !Task.isCancelled {
                    await self.refreshStatus()
                }
            }
        }
    }

    func stop() {
        refreshTask?.cancel()
        refreshTask = nil
        hydrationTask?.cancel()
        hydrationTask = nil
    }

    func loadInitial() async {
        hydrationTask?.cancel()
        loadState = .loading
        do {
            async let status = service.fetchAgentStatus(petID: petID)
            async let cityPosition = service.fetchCityPosition(petID: petID)

            let nextStatus = try await status
            self.status = nextStatus
            cache.store(nextStatus, kind: .agentStatus)
            if let nextPosition = try? await cityPosition {
                self.cityPosition = nextPosition
                cache.store(nextPosition, kind: .cityPosition)
            } else if let cached = cache.load(CityPosition.self, kind: .cityPosition) {
                self.cityPosition = cached.value
            }
            lastPostcardCount = nextStatus.postcards.count
            markRefreshSucceeded()
            loadState = .loaded
            hydrationTask = Task { [weak self] in
                await self?.hydrateInitialDetails()
            }
        } catch {
            if Task.isCancelled { return }
            // 离线冷启动：有缓存就先让 TA 的世界亮起来，标记 stale 待信号恢复。
            if let cachedStatus = cache.load(AgentStatus.self, kind: .agentStatus) {
                status = cachedStatus.value
                cityPosition = cache.load(CityPosition.self, kind: .cityPosition)?.value
                lastPostcardCount = cachedStatus.value.postcards.count
                dataFreshness = .stale(cachedStatus.updatedAt)
                loadState = .loaded
                hydrateDetailsFromCache()
            } else {
                loadState = .failed(error.localizedDescription)
            }
        }
    }

    func refreshStatus() async {
        do {
            async let statusTask = service.fetchAgentStatus(petID: petID)
            async let positionTask = service.fetchCityPosition(petID: petID)
            async let worldSnapshotTask = service.fetchWorldSnapshot(petID: petID)
            let nextStatus = try await statusTask
            let nextCount = nextStatus.postcards.count
            let previousJourneyStatus = status?.agentState.status
            if nextCount > lastPostcardCount {
                hasUnreadPostcard = true
            }
            status = nextStatus

            let nextPosition = try? await positionTask
            if let nextPosition {
                cityPosition = nextPosition
                cache.store(nextPosition, kind: .cityPosition)
            }

            let nextWorldSnapshot = try? await worldSnapshotTask
            if let nextWorldSnapshot {
                worldSnapshot = nextWorldSnapshot
                cache.store(nextWorldSnapshot, kind: .worldSnapshot)
            }
            if photoMission == nil || nextStatus.agentState.status != previousJourneyStatus {
                await refreshPhotoMission()
            }
            if visibleThoughtTranslation?.thoughtID != nextStatus.agentState.latestThought?.id {
                visibleThoughtTranslation = nil
            }
            lastPostcardCount = nextCount
            cache.store(nextStatus, kind: .agentStatus)
            markRefreshSucceeded()
            await drainOutboxIfNeeded()
        } catch {
            dataFreshness = .stale(lastRefreshSucceededAt)
            toastMessage = "通讯信号有点弱，稍后会再试。"
        }
    }

    func markRefreshSucceeded() {
        lastRefreshSucceededAt = Date()
        dataFreshness = .fresh
    }

    /// 信号恢复后补发离线期间存下的讯息。

    func drainOutboxIfNeeded() async {
        guard outbox.pendingCount > 0 else { return }
        await outbox.drain { [service, petID] text in
            _ = try await service.sendOwnerMessage(
                petID: petID,
                request: OwnerMessageRequest(message: text, intentHint: "owner_suggestion_or_companion_message")
            )
        }
        if outbox.pendingCount == 0 {
            toastMessage = "刚才没送出去的话，已经送达 TA 的世界。"
        }
    }

    /// 离线冷启动时用缓存点亮细节面。

    func hydrateDetailsFromCache() {
        if let cached = cache.load(DayPlan.self, kind: .dayPlan) { dayPlan = cached.value }
        if let cached = cache.load(PetDNA.self, kind: .dna) { dna = cached.value }
        if let cached = cache.load(WorldSimulationSnapshot.self, kind: .worldSnapshot) { worldSnapshot = cached.value }
        if let cached = cache.load(JourneyPlan.self, kind: .journeyPlan) {
            journeyPlan = cached.value
            remoteRoutePlan = cached.value.compatibilityRoutePlan
        }
        if let cached = cache.load(IllustratedGuide.self, kind: .illustratedGuide) { illustratedGuide = cached.value }
        if let cached = cache.load([TravelQuest].self, kind: .travelQuests) { travelQuests = cached.value }
        if let cached = cache.load([SouvenirItem].self, kind: .souvenirs) { souvenirs = cached.value }
        if let cached = cache.load(EconomyResponse.self, kind: .economy) { economy = cached.value }
    }

    func hydrateInitialDetails() async {
        async let dayPlanTask = service.fetchDayPlan(petID: petID)
        async let dnaTask = service.fetchDNA(petID: petID)
        async let worldSnapshotTask = service.fetchWorldSnapshot(petID: petID)
        async let journeyPlanTask = service.fetchJourneyPlan(petID: petID)
        async let illustratedGuideTask = service.fetchIllustratedGuide(petID: petID)
        async let photoMissionTask = service.fetchPhotoMission(petID: petID)
        async let travelQuestTask = service.fetchTravelQuests(petID: petID, limit: 8)
        async let souvenirTask = service.fetchSouvenirs(petID: petID, limit: 40)
        async let economyTask = service.fetchEconomy(petID: petID)
        var pendingIllustratedGuide: IllustratedGuide?

        if let nextDayPlan = try? await dayPlanTask {
            dayPlan = nextDayPlan
            cache.store(nextDayPlan, kind: .dayPlan)
        } else if dayPlan == nil, let cached = cache.load(DayPlan.self, kind: .dayPlan) {
            dayPlan = cached.value
        }
        if let nextDNA = try? await dnaTask {
            dna = nextDNA
            cache.store(nextDNA, kind: .dna)
        } else if dna == nil, let cached = cache.load(PetDNA.self, kind: .dna) {
            dna = cached.value
        }
        if let nextWorldSnapshot = try? await worldSnapshotTask {
            worldSnapshot = nextWorldSnapshot
            cache.store(nextWorldSnapshot, kind: .worldSnapshot)
        }
        if let nextJourneyPlan = try? await journeyPlanTask {
            journeyPlan = nextJourneyPlan
            remoteRoutePlan = nextJourneyPlan.compatibilityRoutePlan
            cache.store(nextJourneyPlan, kind: .journeyPlan)
        } else if let fallbackRoutePlan = try? await service.fetchRoutePlan(petID: petID) {
            journeyPlan = nil
            remoteRoutePlan = fallbackRoutePlan
        } else if journeyPlan == nil, let cached = cache.load(JourneyPlan.self, kind: .journeyPlan) {
            journeyPlan = cached.value
            remoteRoutePlan = cached.value.compatibilityRoutePlan
        }
        if let nextIllustratedGuide = try? await illustratedGuideTask {
            illustratedGuide = nextIllustratedGuide
            pendingIllustratedGuide = nextIllustratedGuide
            cache.store(nextIllustratedGuide, kind: .illustratedGuide)
        } else if illustratedGuide == nil, let cached = cache.load(IllustratedGuide.self, kind: .illustratedGuide) {
            illustratedGuide = cached.value
        }
        if let nextPhotoMission = try? await photoMissionTask {
            photoMission = nextPhotoMission
        }
        if let nextTravelQuests = try? await travelQuestTask {
            travelQuests = nextTravelQuests
            cache.store(nextTravelQuests, kind: .travelQuests)
            await refreshTravelBag()
        } else if travelQuests.isEmpty, let cached = cache.load([TravelQuest].self, kind: .travelQuests) {
            travelQuests = cached.value
        }
        if let nextSouvenirs = try? await souvenirTask {
            souvenirs = nextSouvenirs
            cache.store(nextSouvenirs, kind: .souvenirs)
        } else if souvenirs.isEmpty, let cached = cache.load([SouvenirItem].self, kind: .souvenirs) {
            souvenirs = cached.value
        }
        if let nextEconomy = try? await economyTask {
            economy = nextEconomy
            cache.store(nextEconomy, kind: .economy)
        } else if economy == nil, let cached = cache.load(EconomyResponse.self, kind: .economy) {
            economy = cached.value
        }
        if let pendingIllustratedGuide {
            await generateIllustratedGuideIfNeeded(pendingIllustratedGuide)
        }
    }

    func refreshDetails() async {
        do {
            async let dayPlan = service.fetchDayPlan(petID: petID)
            async let dna = service.fetchDNA(petID: petID)
            async let worldSnapshot = service.fetchWorldSnapshot(petID: petID)
            async let petGuide = service.fetchPetGuide(petID: petID)
            async let illustratedGuide = service.fetchIllustratedGuide(petID: petID)
            async let travelQuests = service.fetchTravelQuests(petID: petID, limit: 8)
            async let souvenirs = service.fetchSouvenirs(petID: petID, limit: 40)
            async let economy = service.fetchEconomy(petID: petID)
            self.dayPlan = try await dayPlan
            self.dna = try await dna
            self.worldSnapshot = try? await worldSnapshot
            self.petGuide = try? await petGuide
            let nextIllustratedGuide = try? await illustratedGuide
            self.illustratedGuide = nextIllustratedGuide
            self.travelQuests = (try? await travelQuests) ?? self.travelQuests
            self.souvenirs = (try? await souvenirs) ?? self.souvenirs
            self.economy = (try? await economy) ?? self.economy
            await refreshTravelBag()
            await refreshRoutePlan()
            await refreshPhotoMission()
            if let nextIllustratedGuide {
                await generateIllustratedGuideIfNeeded(nextIllustratedGuide)
            }
        } catch {
            toastMessage = "细节暂时没有同步完整。"
        }
    }

    func markPostcardsRead() {
        hasUnreadPostcard = false
    }

    func clearToast() {
        toastMessage = nil
    }
}
