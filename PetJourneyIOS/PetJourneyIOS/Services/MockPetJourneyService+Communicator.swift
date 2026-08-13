import Foundation

@MainActor
extension MockPetJourneyService {
    func fetchThoughtTranslation(petID: String, thoughtID: String) async throws -> ThoughtTranslation {
        try ensureJourneyExists(for: petID)
        guard let journey = journeys[petID],
              let thought = journey.thoughts.first(where: { $0.id == thoughtID }),
              let translation = thought.translation
        else {
            throw PetJourneyError.requestFailed("这句话还没有翻译出来")
        }
        return ThoughtTranslation(
            thoughtID: thought.id,
            petID: petID,
            animalText: thought.animalText ?? thought.text,
            translation: translation,
            tone: thought.tone,
            languageStyle: thought.languageStyle,
            model: thought.model
        )
    }

    func sendFeedback(_ request: FeedbackRequest) async throws -> FeedbackResponse {
        try ensureJourneyExists(for: request.petID)
        guard var journey = journeys[request.petID] else { throw PetJourneyError.noPetSession }

        let text: String
        let tone: String
        if request.liked {
            tone = "guide_saved"
            text = "已为你收藏这段攻略。\(journey.profile.name) 的旅程不会被打断，TA 还在按自己的节奏探索。"
        } else {
            tone = "guide_skipped"
            text = "知道了，这类攻略会少推荐给你。\(journey.profile.name) 仍然可以自己喜欢、停留或离开。"
        }

        let thought = agentThought(translation: text, tone: tone, petType: journey.profile.petType)
        journey.thoughts.append(thought)
        journey.lastThoughtText = thought.text
        journey.events.append(
            JourneyEvent(
                id: UUID().uuidString,
                title: request.liked ? "你收藏了一段攻略" : "你略过了这类攻略",
                detail: request.liked ? "这是你的旅行偏好，不会决定 TA 对这个地方的感受。" : "手机会少给你推荐类似地点，但 TA 的旅程仍然自由。",
                timestamp: Date()
            )
        )
        journeys[request.petID] = journey
        appendMemory(
            petID: request.petID,
            kind: "owner_preference",
            title: "\(request.city) 的主人反馈",
            content: text,
            salience: 0.72,
            source: "feedback",
            metadata: ["city": .string(request.city), "liked": .bool(request.liked)]
        )

        let updated = try await fetchAgentStatus(petID: request.petID)
        return FeedbackResponse(success: true, message: text, updatedStatus: updated)
    }

    func sendOwnerMessage(petID: String, request: OwnerMessageRequest) async throws -> OwnerMessageResponse {
        try ensureJourneyExists(for: petID)
        guard var journey = journeys[petID] else { throw PetJourneyError.noPetSession }
        let clean = request.message.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !clean.isEmpty else { throw PetJourneyError.requestFailed("讯息不能为空") }

        let decision: String
        let reply: String
        if clean.contains("想你") || clean.contains("晚安") || clean.contains("早安") {
            decision = "comfort"
            reply = "我听见了。它像一点暖光，被我收进手机里。"
        } else if clean.contains("去") || clean.contains("看看") || clean.contains("咖啡") || clean.contains("海") {
            let accepts = abs(clean.hashValue) % 4 != 0
            decision = accepts ? "accepted" : "declined"
            reply = accepts
                ? "我听见你的建议了。等风和路线合适的时候，我会自己决定要不要靠近看看。"
                : "我听见你的建议了。今天我先把眼前这段路慢慢走完，再自己决定下一步。"
        } else {
            decision = "remembered"
            reply = "我先把这句话记住，不急着决定，等下一段旅程再慢慢判断。"
        }

        let thought = agentThought(translation: reply, tone: "owner_message_\(decision)", petType: journey.profile.petType)
        journey.thoughts.append(thought)
        journey.lastThoughtText = thought.text
        journey.events.append(
            JourneyEvent(
                id: UUID().uuidString,
                title: "TA 收到你的讯息",
                detail: "这是一条建议或陪伴讯息，TA 会自己判断怎么回应。",
                timestamp: Date()
            )
        )
        journeys[petID] = journey
        appendMemory(
            petID: petID,
            kind: "owner_message",
            title: "你的讯息",
            content: "你说：「\(clean)」。TA 回应：\(reply)",
            salience: 0.74,
            source: "owner_message",
            metadata: ["decision": .string(decision)]
        )

        let updated = try await fetchAgentStatus(petID: petID)
        return OwnerMessageResponse(
            success: true,
            decision: decision,
            message: reply,
            thought: thought,
            updatedStatus: updated
        )
    }

    func fetchCommunicatorMessages(petID: String, limit: Int) async throws -> [CommunicatorMessage] {
        try ensureJourneyExists(for: petID)
        return Array((communicatorMessages[petID] ?? []).suffix(max(1, limit)))
    }

    func sendCommunicatorMessage(petID: String, request: CommunicatorSendRequest) async throws -> CommunicatorSendResponse {
        try ensureJourneyExists(for: petID)
        guard let journey = journeys[petID] else { throw PetJourneyError.noPetSession }
        let clean = request.text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !clean.isEmpty else { throw PetJourneyError.requestFailed("讯息不能为空") }
        let city = cityFor(journey: journey)
        let now = Date()
        let intent = mockIntent(for: clean)
        let policy = mockReplyPolicy(intent: intent, message: clean, journey: journey)
        let owner = CommunicatorMessage(
            id: "msg_\(UUID().uuidString)",
            petID: petID,
            sender: .owner,
            text: clean,
            intent: intent,
            messageState: "delivered",
            replyPolicy: policy,
            attachments: [],
            relatedMessageID: nil,
            createdAt: now,
            updatedAt: nil
        )
        communicatorMessages[petID, default: []].append(owner)

        let attachments = mockAttachments(intent: intent, policy: policy, city: city)
        let replyText = mockCommunicatorReply(intent: intent, message: clean, city: city)
        let sender: CommunicatorSender = policy.mode.hasPrefix("queued") ? .system : .pet
        let reply = CommunicatorMessage(
            id: "msg_\(UUID().uuidString)",
            petID: petID,
            sender: sender,
            text: sender == .system ? policy.visibleStatus : replyText,
            intent: intent,
            messageState: "sent",
            replyPolicy: policy,
            attachments: attachments,
            relatedMessageID: owner.id,
            createdAt: now.addingTimeInterval(1),
            updatedAt: nil
        )
        communicatorMessages[petID, default: []].append(reply)

        if sender == .pet {
            var updatedJourney = journey
            let thought = agentThought(translation: replyText, tone: "communicator_\(intent.rawValue.lowercased())", petType: journey.profile.petType)
            updatedJourney.thoughts.append(thought)
            updatedJourney.lastThoughtText = thought.text
            journeys[petID] = updatedJourney
        }

        if intent == .currentStatusVisualRequest || intent == .photoRequest || intent == .confirmPendingPhoto {
            insertMockMomentIfNeeded(petID: petID, petName: journey.profile.name, city: city, attachments: attachments)
        }

        return CommunicatorSendResponse(
            success: true,
            intent: intent,
            replyPolicy: policy,
            ownerMessage: owner,
            messages: [reply],
            pendingRequest: nil
        )
    }

    func sendCommunicatorPhoto(petID: String, imageData: Data, caption: String?) async throws -> CommunicatorSendResponse {
        try ensureJourneyExists(for: petID)
        guard let journey = journeys[petID] else { throw PetJourneyError.noPetSession }
        let city = cityFor(journey: journey)
        let now = Date()
        let clean = caption?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        let imageURL = try persistMockCommunicatorPhoto(imageData)
        let intent = CommunicatorIntent.ownerPhotoShare
        let policy = CommunicatorReplyPolicy(
            mode: "immediate",
            estimatedReplySeconds: 6,
            visibleStatus: "TA 看到了这张照片。",
            reasonCode: "owner_photo_shared",
            shouldBatch: false,
            shouldMarkSeen: true,
            cooldownApplied: false
        )
        let ownerAttachment = CommunicatorAttachment(
            type: .ownerPhoto,
            title: "你发来的照片",
            text: clean.isEmpty ? "给 TA 看的一张照片。" : clean,
            state: "ready",
            photoURL: imageURL,
            location: nil,
            photoMissionID: nil,
            availableAfter: nil
        )
        let owner = CommunicatorMessage(
            id: "msg_\(UUID().uuidString)",
            petID: petID,
            sender: .owner,
            text: clean,
            intent: intent,
            messageState: "delivered",
            replyPolicy: policy,
            attachments: [ownerAttachment],
            relatedMessageID: nil,
            createdAt: now,
            updatedAt: nil
        )
        communicatorMessages[petID, default: []].append(owner)

        let replyText = mockOwnerPhotoReply(caption: clean, city: city)
        let reply = CommunicatorMessage(
            id: "msg_\(UUID().uuidString)",
            petID: petID,
            sender: .pet,
            text: replyText,
            intent: intent,
            messageState: "sent",
            replyPolicy: policy,
            attachments: [],
            relatedMessageID: owner.id,
            createdAt: now.addingTimeInterval(1),
            updatedAt: nil
        )
        communicatorMessages[petID, default: []].append(reply)

        var updatedJourney = journey
        let thought = agentThought(translation: replyText, tone: "communicator_owner_photo_share", petType: journey.profile.petType)
        updatedJourney.thoughts.append(thought)
        updatedJourney.lastThoughtText = thought.text
        journeys[petID] = updatedJourney

        return CommunicatorSendResponse(
            success: true,
            intent: intent,
            replyPolicy: policy,
            ownerMessage: owner,
            messages: [reply],
            pendingRequest: nil
        )
    }

    func fetchMoments(petID: String, limit: Int) async throws -> [CommunicatorMoment] {
        try ensureJourneyExists(for: petID)
        guard let journey = journeys[petID] else { throw PetJourneyError.noPetSession }
        if communicatorMoments[petID]?.isEmpty != false {
            communicatorMoments[petID] = seedMoments(petID: petID, petName: journey.profile.name, city: cityFor(journey: journey))
        }
        return Array((communicatorMoments[petID] ?? []).prefix(max(1, limit)))
    }

    func reactToMoment(petID: String, momentID: String, request: MomentReactionRequest) async throws -> MomentReactionResponse {
        try ensureJourneyExists(for: petID)
        guard let index = communicatorMoments[petID]?.firstIndex(where: { $0.id == momentID }) else {
            throw PetJourneyError.requestFailed("这条朋友圈动态暂时找不到")
        }
        var moment = communicatorMoments[petID]![index]
        if let previous = moment.ownerReaction {
            moment.reactions[previous.rawValue] = max(0, (moment.reactions[previous.rawValue] ?? 0) - 1)
        }
        moment.ownerReaction = request.reaction
        moment.reactions[request.reaction.rawValue] = (moment.reactions[request.reaction.rawValue] ?? 0) + 1
        moment.updatedAt = Date()
        communicatorMoments[petID]![index] = moment
        appendMemory(
            petID: petID,
            kind: "moment_reaction",
            title: "你回应了一条朋友圈",
            content: "你对「\(moment.text)」回应了 \(request.reaction.displayName)。",
            salience: 0.56,
            source: "communicator_moment_reaction",
            metadata: ["reaction": .string(request.reaction.rawValue)]
        )
        return MomentReactionResponse(
            success: true,
            momentID: momentID,
            reaction: request.reaction,
            message: request.reaction == .paw ? "TA 好像感受到你摸了摸它。" : (request.reaction == .hug ? "TA 把这个抱抱轻轻收好了。" : "TA 好像知道你喜欢这一刻。")
        )
    }

    func mockIntent(for text: String) -> CommunicatorIntent {
        if ["撑不住", "好难受", "不想活", "崩溃", "受不了了", "好痛苦"].contains(where: { text.contains($0) }) {
            return .emotionalDistress
        }
        let compact = text.replacingOccurrences(of: " ", with: "")
        if compact.count <= 12,
           ["好", "好滴", "好的", "嗯", "嗯嗯", "行", "可以", "ok", "OK"].contains(where: { compact.contains($0) }),
           ["看", "看看", "照片", "拍"].contains(where: { compact.contains($0) }),
           !["不看", "不用", "别拍", "不要"].contains(where: { compact.contains($0) }) {
            return .confirmPendingPhoto
        }
        if ["你现在干嘛", "现在干嘛", "在干嘛", "看看你", "给我看看", "让我看看你", "发张现在的照片"].contains(where: { text.contains($0) }) {
            return .currentStatusVisualRequest
        }
        if ["拍张照片", "发张照片", "自拍", "看看风景"].contains(where: { text.contains($0) }) {
            return .photoRequest
        }
        if ["寄张明信片", "明信片"].contains(where: { text.contains($0) }) {
            return .postcardRequest
        }
        if ["你在哪", "现在在哪", "到哪里了", "你在什么地方"].contains(where: { text.contains($0) }) {
            return .locationCheck
        }
        if ["想你", "抱抱", "摸摸", "乖乖", "宝宝"].contains(where: { text.contains($0) }) {
            return .affectionIMissYou
        }
        if ["累不累", "饿不饿", "冷不冷", "开心吗", "有没有休息"].contains(where: { text.contains($0) }) {
            return .careCheck
        }
        return .generalChat
    }

    func mockReplyPolicy(intent: CommunicatorIntent, message: String, journey: MockJourney) -> CommunicatorReplyPolicy {
        let status = statusFor(now: Date())
        let isPhotoIntent = intent == .currentStatusVisualRequest || intent == .photoRequest || intent == .confirmPendingPhoto
        if status == .flying {
            return CommunicatorReplyPolicy(
                mode: "queued_until_landed",
                estimatedReplySeconds: 2700,
                visibleStatus: "TA 正在路上，信号一会儿有一会儿没有，落地后会看到。",
                reasonCode: "pet_flying",
                shouldBatch: false,
                shouldMarkSeen: true,
                cooldownApplied: false
            )
        }
        if intent == .generalChat && status == .walking {
            return CommunicatorReplyPolicy(
                mode: "delayed",
                estimatedReplySeconds: 180,
                visibleStatus: "TA 正在路上，可能会慢一点回你。",
                reasonCode: "general_chat_pet_in_transit",
                shouldBatch: false,
                shouldMarkSeen: true,
                cooldownApplied: false
            )
        }
        return CommunicatorReplyPolicy(
            mode: "immediate",
            estimatedReplySeconds: 6,
            visibleStatus: isPhotoIntent ? "这一刻可以拍给你。" : "TA 收到了。",
            reasonCode: isPhotoIntent ? "pet_at_photoable_scene" : "default_available",
            shouldBatch: false,
            shouldMarkSeen: true,
            cooldownApplied: false
        )
    }

    func mockAttachments(intent: CommunicatorIntent, policy: CommunicatorReplyPolicy, city: MockCity) -> [CommunicatorAttachment] {
        let location = CommunicatorLocation(
            city: city.name,
            placeName: city.name == "厦门" ? "海边栈道" : "安静街角",
            latitude: city.position.latitude,
            longitude: city.position.longitude
        )
        if intent == .locationCheck {
            return [
                CommunicatorAttachment(type: .locationCard, title: "TA 此刻的位置", text: "\(city.name) · \(location.placeName ?? "旅途中")。\(city.weather)", state: "ready", photoURL: nil, location: location, photoMissionID: nil, availableAfter: nil)
            ]
        }
        if intent == .currentStatusVisualRequest || intent == .photoRequest || intent == .confirmPendingPhoto {
            return [
                CommunicatorAttachment(type: .photoPlaceholder, title: "正在拍给你", text: "TA 现在在\(city.name) · \(location.placeName ?? "旅途中")，画面准备好后会发来。", state: "placeholder", photoURL: nil, location: location, photoMissionID: "mock-photo-\(UUID().uuidString)", availableAfter: Date().addingTimeInterval(25)),
                CommunicatorAttachment(type: .locationCard, title: "TA 现在在这里", text: "\(city.name) · \(location.placeName ?? "旅途中")。\(city.weather)", state: "ready", photoURL: nil, location: location, photoMissionID: nil, availableAfter: nil)
            ]
        }
        if intent == .postcardRequest {
            return [
                CommunicatorAttachment(type: .postcardCandidate, title: "明信片在路上", text: "TA 会等一个更适合写给你的画面。", state: "planned", photoURL: nil, location: location, photoMissionID: nil, availableAfter: Date().addingTimeInterval(7200))
            ]
        }
        if intent == .affectionIMissYou || intent == .careCheck {
            return [
                CommunicatorAttachment(type: .sticker, title: "🐾 蹭蹭", text: "轻轻蹭了蹭。", state: "ready", photoURL: nil, location: nil, photoMissionID: nil, availableAfter: nil)
            ]
        }
        return []
    }

    func mockCommunicatorReply(intent: CommunicatorIntent, message: String, city: MockCity) -> String {
        switch intent {
        case .emotionalDistress:
            return "我看到你这句话了。先不要一个人硬撑，去找身边可信的人或当地紧急帮助；我会把一点光轻轻放在这里陪你。"
        case .currentStatusVisualRequest:
            return "我在\(city.name)这边。\(mockSceneFeeling(for: city))，我拍给你看。"
        case .photoRequest:
            return "好呀。我找个不晃的角度，拍给你。"
        case .confirmPendingPhoto:
            return "嗯嗯，我拍给你看。"
        case .locationCheck:
            return "我现在在\(city.name)。位置给你发过来了。"
        case .affectionIMissYou:
            return "我也有一点想你。刚才有阵风过来，像你摸了摸我。"
        case .careCheck:
            return "我会慢一点，找个舒服的地方停一下。你也记得照顾自己。"
        case .postcardRequest:
            return "我会等一个更适合写给你的画面，不急着把它寄出去。"
        default:
            return mockGeneralCommunicatorReply(message: message, city: city)
        }
    }

    func mockGeneralCommunicatorReply(message: String, city: MockCity) -> String {
        let compact = message.replacingOccurrences(of: " ", with: "")
        let isShortAck = compact.count <= 8 && ["好", "好滴", "好的", "嗯", "嗯嗯", "行", "可以", "收到", "ok", "OK", "看看"].contains { compact.contains($0) }
        if isShortAck {
            if ["看", "照片", "拍"].contains(where: { compact.contains($0) }) {
                return "嗯嗯，等照片好了我发你。"
            }
            return "嗯嗯。"
        }
        if ["去", "看看", "路过", "下次", "有空"].contains(where: { message.contains($0) }) {
            return "我先记着。等路走到合适的地方，我再看一眼。"
        }
        if message.contains("谢谢") || message.contains("辛苦") {
            return "不辛苦，我慢慢走就好。"
        }
        if message.contains("晚安") {
            return "晚安。我把声音放轻一点。"
        }
        return "我看到啦。现在还在\(city.name)这边，等停稳一点再跟你说。"
    }

    func mockOwnerPhotoReply(caption: String, city: MockCity) -> String {
        if ["家", "以前", "小时候", "想你"].contains(where: { caption.contains($0) }) {
            return "我看到啦。这里面有一点熟悉的味道，像从家里递过来的一小块光。"
        }
        if ["吃", "饭", "咖啡", "甜", "香"].contains(where: { caption.contains($0) }) {
            return "我看到啦。看起来很香，我在\(city.name)这边也慢慢闻了闻风。"
        }
        if ["看看", "看一下", "给你看"].contains(where: { caption.contains($0) }) {
            return "我看到啦。这个画面离我很近，像你把那边的一点点生活递过来了。"
        }
        if !caption.isEmpty {
            return "我看到啦。这张照片我收好了，晚点路上也会想起它。"
        }
        return "我看到啦。像你从那边轻轻递来了一小块画面。"
    }

    func persistMockCommunicatorPhoto(_ imageData: Data) throws -> URL {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("petsoul-communicator", isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let fileURL = directory.appendingPathComponent("owner-photo-\(UUID().uuidString).jpg")
        try imageData.write(to: fileURL)
        return fileURL
    }

    func mockSceneFeeling(for city: MockCity) -> String {
        if city.name == "厦门" {
            return "街边声音有点近"
        }
        return "\(city.weather)，这一刻还算安静"
    }

    func seedMoments(petID: String, petName: String, city: MockCity) -> [CommunicatorMoment] {
        let location = CommunicatorLocation(city: city.name, placeName: city.name == "厦门" ? "海边栈道" : "安静街角", latitude: city.position.latitude, longitude: city.position.longitude)
        let restingDate = Date().addingTimeInterval(-18 * 60)
        let arrivalDate = Date().addingTimeInterval(-42 * 60)
        let restingReactors = mockSocialReactors(seed: "\(petID)-resting", createdAt: restingDate)
        let arrivalReactors = mockSocialReactors(seed: "\(petID)-arrival", createdAt: arrivalDate)
        return [
            CommunicatorMoment(
                id: "moment_mock_\(UUID().uuidString)",
                petID: petID,
                sourceType: "resting",
                sourceEventID: nil,
                text: "\(petName)在一个安静地方停了一小会儿，像是在把今天的路收进爪心。",
                location: location,
                mood: "calm",
                attachments: [
                    CommunicatorAttachment(
                        type: .locationCard,
                        title: "停留地点",
                        text: "\(city.name) · \(location.placeName ?? "安静角落")。TA 在这里慢慢待了一会儿。",
                        state: "ready",
                        photoURL: nil,
                        location: location,
                        photoMissionID: nil,
                        availableAfter: nil
                    )
                ],
                reactions: mockReactionCounts(for: restingReactors),
                ownerReaction: nil,
                isRead: false,
                createdAt: restingDate,
                updatedAt: nil,
                socialReactors: restingReactors
            ),
            CommunicatorMoment(
                id: "moment_mock_\(UUID().uuidString)",
                petID: petID,
                sourceType: "arrival",
                sourceEventID: nil,
                text: "到\(city.name)啦。这里的风和声音都还在慢慢认出来。",
                location: location,
                mood: "curious",
                attachments: MockDemoMedia.frenchiePostcardURL.map { photoURL in [
                    CommunicatorAttachment(
                        type: .photo,
                        title: "刚刚拍到的一眼",
                        text: "到\(city.name)后的第一眼，发给朋友圈一起看看。",
                        state: "ready",
                        photoURL: photoURL,
                        location: location,
                        photoMissionID: "mock-arrival-photo",
                        availableAfter: nil
                    )
                ] } ?? [
                    CommunicatorAttachment(
                        type: .locationCard,
                        title: "到达地点",
                        text: "\(city.name) · \(location.placeName ?? "安静角落")。TA 刚到这里，先向朋友圈报个平安。",
                        state: "ready",
                        photoURL: nil,
                        location: location,
                        photoMissionID: nil,
                        availableAfter: nil
                    )
                ],
                reactions: mockReactionCounts(for: arrivalReactors),
                ownerReaction: nil,
                isRead: false,
                createdAt: arrivalDate,
                updatedAt: nil,
                socialReactors: arrivalReactors
            )
        ]
    }

    func insertMockMomentIfNeeded(petID: String, petName: String, city: MockCity, attachments: [CommunicatorAttachment]) {
        guard communicatorMoments[petID]?.first(where: { $0.sourceType == "current_status_photo" }) == nil else { return }
        let photoAttachments = attachments.filter { $0.type == .photo && $0.photoURL != nil }
        guard !photoAttachments.isEmpty else { return }
        let createdAt = Date()
        let reactors = mockSocialReactors(seed: "\(petID)-current-photo", createdAt: createdAt)
        let moment = CommunicatorMoment(
            id: "moment_mock_\(UUID().uuidString)",
            petID: petID,
            sourceType: "current_status_photo",
            sourceEventID: nil,
            text: "刚好遇到这一刻，就发到朋友圈里。大家路过的话，可以一起看看。",
            location: photoAttachments.first?.location,
            mood: "soft_happy",
            attachments: photoAttachments,
            reactions: mockReactionCounts(for: reactors),
            ownerReaction: nil,
            isRead: false,
            createdAt: createdAt,
            updatedAt: nil,
            socialReactors: reactors
        )
        communicatorMoments[petID, default: seedMoments(petID: petID, petName: petName, city: city)].insert(moment, at: 0)
    }

    func mockSocialReactors(seed: String, createdAt: Date) -> [MomentSocialReactor] {
        // 与后端 communicator/npc_society.py 的常驻 NPC 保持同一批身份
        let pool: [(String, String, String, String, MomentReaction, String)] = [
            ("npc-nana-cat", "Nana", "cat", "🐱", .like, "在附近的窗台看见了这一刻"),
            ("npc-tuanzi-dog", "团子", "dog", "🐶", .like, "也觉得这里适合慢慢待着"),
            ("npc-jiujiu-parrot", "啾啾", "parrot", "🦜", .hug, "从公共频道轻轻回应了一下"),
            ("npc-momo-rabbit", "Momo", "rabbit", "🐰", .like, "把这一刻收藏进小地图"),
            ("npc-mili-hamster", "米粒", "hamster", "🐹", .hug, "偷偷把这一刻塞进了腮帮子"),
            ("npc-lucky-dog", "Lucky", "dog", "🐶", .like, "在街角朝这边汪了一声")
        ]
        let value = seed.unicodeScalars.reduce(0) { $0 + Int($1.value) }
        let count = 1 + value % 3
        let start = value % pool.count
        return (0..<count).map { index in
            let item = pool[(start + index) % pool.count]
            return MomentSocialReactor(
                id: item.0,
                name: item.1,
                species: item.2,
                avatarEmoji: item.3,
                reaction: item.4,
                note: item.5,
                createdAt: createdAt.addingTimeInterval(TimeInterval(18 + index * 31))
            )
        }
    }

    func mockReactionCounts(for reactors: [MomentSocialReactor]) -> [String: Int] {
        var counts = ["like": 0, "paw": 0, "hug": 0]
        for reactor in reactors {
            counts[reactor.reaction.rawValue, default: 0] += 1
        }
        return counts
    }
}
