# iOS 深度审计 — Part B：架构 / 状态 / 网络 / 契约

> 范围：PetJourneyIOS（SwiftUI）与 PetJourneyBackend（FastAPI）的架构、状态管理、网络层与线上契约。
> 性质：只读审计，未修改任何源码，未提交。
> 证据口径：所有结论均附 文件:行号。

---

## 0. 执行摘要

总体健康度：中上。上一轮"上帝文件拆分 / VM 逻辑下沉（#40 P2-1）/ DesignTokens / arch_gate 800行·30类型"基本落地——JourneyViewModel 已拆成 6 个文件（主文件 135 行、+Lifecycle 250、+Travel 164、+Details 132、+Communication 102、+Souvenirs 82），每片均 <300 行，VM 内不再做 UI 格式化。网络层 APIClient 把重试/错误归一收口，业务服务只组请求，写请求（POST/PATCH/DELETE）一律 .none 不重试、读请求 .idempotent 才重试——"非幂等 POST 重试"这一危险点已正确规避。

但存在三类真正需要动手的问题：

1. 健壮性缺口（P0）：离线发件队列队头阻塞（一条永久失败消息堵死整条队列）、无 401/令牌刷新、缓存无 TTL（离线冷启动可无限期读陈旧世界快照）。
2. 架构回潮（P1）：WorldStoryViewModel 绕过网络层直接 URLSession；CommunicatorViewModel / MemoryHubViewModel 仍定义在 View 文件里；PetCredentialModels.swift（Views/ 目录、约 780 行）塞满纯业务逻辑；"分钟数"时间计算在 4 处 View 重复实现。
3. 契约漂移（隐性、无崩溃但信息丢失）（P1）：iOS 模型比后端 schema 整体偏宽松/字段偏少，典型是 LifeTickResult 直接丢弃了后端的 observation（世界观测）与 retrieved_memories（检索记忆），PhotoMission 丢弃了 quality_report / prompt_blocks。由于 Codable 对多余字段静默忽略，这些漂移不会崩、但也不会被任何测试发现（无 fixture 契约解码测试）。

模型切换（DeepSeek/Seedream）风险：总体可控。文本侧 iOS 不显示任何模型名/provider（faf38e5 修复已验证通过，全文无 .model/.provider 出现在 View 渲染路径）；图片侧 iOS 凭据卡是本地合成卡面而非服务端生图，服务端 fetchCredentialPrompts 端点在 iOS 从未被调用（死代码）。主要残留风险是尺寸/宽高比硬编码（凭据卡固定 3:2，即 1536/1024，与 Seedream 实际输出尺寸不一致）与后端 IllustratedGuide.model 在 volcengine 下仍可能报 gpt-image-2 的小漂移。

测试最大缺口：ViewModel 层零覆盖 + 无契约解码 fixture 测试——这正是上面契约漂移"看不见"的根因。

### 关键数字

| 指标 | 数值 |
|---|---|
| Swift 文件总数（含测试） | 101（生产 96 + 测试 5） |
| ViewModel 类 | 11 个（其中 2 个定义在 View 文件里） |
| 超 600 行的 View 文件 | JourneyMapView 688、JourneyDayRecap 663、PetOnboardingView 646、CommunicatorChat 603 |
| 最大单文件 | Views/PetCredentialModels.swift ≈787 行（Views/ 目录，非 Models/） |
| 契约漂移结构体 | 8 个（约 20+ 字段 iOS 缺失） |
| 测试文件 | 5 个，覆盖 5 层，VM / 契约解码零覆盖 |

---

## 1. 发现（P0 / P1 / P2）

### P0-1 离线发件队列队头阻塞 + 无重试上限（消息可能永久丢失）

- 证据：Core/Persistence/OutboundMessageQueue.swift:33-46 — drain 逐条补发，catch 里 break 停整个队列；attempts 累加（:35）但无上限、无死信。
  Core/Persistence/CachedModels.swift:39-44 — OutboundMessageState.sent / .failed 两个状态从未被使用（死状态）。
- 影响：一条被服务端永久拒绝（400/内容违规/长度超限）的消息会永远排在队首，重连后每次 drainOutboxIfNeeded（JourneyViewModel+Lifecycle.swift:111-122，每 5 秒随 refreshStatus 触发一次）都会先撞它、失败、break——后续所有离线消息被堵死，且无告警、无丢弃、无人工干预路径。
- 建议：drain 改为"逐条独立失败计数"，超过阈值（如 5 次）标记 failed 并跳过（或移入死信区）；把 OutboundMessageState.sent/.failed 用起来。

### P0-2 认证 401 无刷新、无恢复路径

- 证据：Core/Networking/APIClient.swift:90-93 — 只有 200..<300 判成功，其余（含 401）一律 APIError.server(status,message)；Services/RemotePetJourneyService.swift:319-329 — decode 只注入 Bearer token，无 401 分支、无刷新、无 401→重新登录的信号。
  App/AppSessionStore.swift:106-110,140-156 — 只有 authToken 存取与 signOut()，无刷新令牌逻辑。
- 影响：Apple 登录 JWT 过期后，所有请求稳定 401，iOS 把它们归一成 PetJourneyError.requestFailed(原始 body)（APIError.swift:19-20），UI 看到的是后端返回的原始文案而非"需要重新登录"的信号语言，且无自动恢复。
- 建议：在 decode 识别 401，触发一次令牌刷新并重放；失败则走 signOut 回登录态。至少把 401 单列一个 APIError.unauthorized，映射成明确的"连接已失效"文案。

### P0-3 缓存无 TTL，陈旧世界状态无限期展示

- 证据：Core/Persistence/JourneyCacheRepository.swift:32-47 — store/load 无过期时间；DataFreshness.stale(Date?)（:5-8）只携带 updatedAt，无任何按年龄驱逐/失效逻辑。
  ViewModels/JourneyViewModel+Lifecycle.swift:48-61 — 离线冷启动 catch 里 cache.load(AgentStatus...) 直接点亮整个 UI，dataFreshness = .stale(...) 仅用于"信号弱"提示。
- 影响：本产品核心是"TA 在平行世界持续生活"；若离线数天再冷启动，会展示数天前的 agentStatus/worldSnapshot，主人误以为宠物状态未变，伤害核心体验。MediaCache.swift:14-28 情感资产永久缓存可接受，但快照类缓存应有 TTL。
- 建议：CachedPayload 增加 TTL（按 PayloadKind 差异化，如 worldSnapshot 30 分钟、agentStatus 1 小时），load 超龄返回 nil；stale 文案区分"短时离线"与"数据已很旧"。

### P1-1 WorldStoryViewModel 绕过网络层直接 URLSession

- 证据：ViewModels/WorldStoryViewModel.swift:26-31 — 直接 URLSession.shared.data(from:) + 手写 TickerResponse decode，未走 APIClient（无 auth、无重试、无错误归一、无自定义 ISO8601 解码器）；:38 还硬编码 petName: "平行世界"、petType: .cat 兜底。
- 影响：与"网络层收口到 APIClient、业务只组请求"的架构相悖；该请求无 Authorization 头、无离线/超时分类。
- 建议：在 PetJourneyService 增加 fetchStoryTicker，走 RemotePetJourneyService.get(...)；兜底样本保留在 VM 属正常。

### P1-2 ViewModel 定义在 View 文件里（拆分回潮）

- 证据：Views/CommunicatorViews.swift:32 final class CommunicatorViewModel；Views/MemoryHub.swift:14 final class MemoryHubViewModel。二者未迁入 ViewModels/ 目录，与 JourneyViewModel/OnboardingViewModel/... 的目录约定不一致。
- 建议：抽出为 ViewModels/CommunicatorViewModel.swift、ViewModels/MemoryHubViewModel.swift 并登记 pbxproj。

### P1-3 契约漂移：8 个结构体字段缺失（见第 2 节契约漂移表）

核心证据行：
- Models/PhotoModels.swift:38-76（PhotoMission 缺 prompt_blocks / quality_report / retry_count / failure_category，后端 schemas/place.py:103-106）
- Models/WorldSimulationModels.swift:186-216（LifeTickResult 缺 observation / retrieved_memories，后端 schemas/world.py:124-125）
- Models/WorldSimulationModels.swift:91-117（PetNeedState 全 Int? 可选，后端必填）
- Models/GuideModels.swift:48-98（PetAuthoredGuide 缺 guide_theme / selected_places / pet_first_person_guide 等，后端 schemas/guide.py:85-91）
- Models/TravelQuestModels.swift:206-236（PlaceEvidencePacket 缺 provider_evidence，后端 schemas/travel.py:95）
- Models/JourneyModels.swift:166-180（OwnerMessageResponse 缺 owner_intent，后端 schemas/pet.py:253）
- Models/SouvenirModels.swift:38-117（SouvenirItem 缺 memory_type / source_photo_mission_id / bag_influence_tags，后端 schemas/economy.py:133-135）
- Models/RouteModels.swift:81-121（PlaceSignal 缺 raw，后端 schemas/place.py:29）

影响：Codable 对后端多余字段静默忽略，故不崩；但 iOS 无法展示世界观测、检索记忆、照片质量报告等已生产的数据，属"能跑但信息丢失"的隐性漂移。风险在于无 fixture 解码测试兜底（见第 4 节）。

### P1-4 无契约解码 fixture 测试（漂移无法被测试捕获）

- 证据：PetJourneyIOSTests/ 仅 5 个文件，无任何"用后端真实 JSON 形状反序列化 iOS Models"的测试；现有 MockPetJourneyServiceTests.swift 只测 mock 业务行为，不测线上字段。
- 影响：P1-3 的字段漂移、String vs date 类型漂移（见契约表）都不会在 CI 里红。
- 建议：新增 ContractDecodingTests，用后端 schema 序列化出的 JSON 样本断言 iOS 模型可解且关键字段不丢。

### P1-5 凭据系统客户端/服务端"双轨" + 死代码 + 重复枚举

- 证据：
  - Services/RemotePetJourneyService.swift:273-275 fetchCredentialPrompts 已定义但全工程无调用点（grep 仅命中 3 处 service 定义，无 VM/View 调用）。
  - Views/PetCredentialModels.swift:307-308 documentImagePrompt 与 Views/PetCredentialModels.swift:633-787 整个 PetCredentialPromptTemplate（约 155 行英文提示词模板）无任何调用点——死代码。
  - 枚举重复：Views/PetCredentialModels.swift:54-181 的 PetCredentialKind（UI 版）与 Models/CredentialModels.swift:6-13 的 PetCredentialPromptKind（Codable 版）同一概念的 6 个 case 重复定义。
  - Views/PetCredentialCard.swift:119,164 卡面由本地渐变合成（documentImage 视图），不使用后端返回的 PetCredentialPrompt（含 image_prompt / size / reference_roles）。
- 影响：后端 credential_prompt_builder.py + /api/v1/pets/{pet_id}/credentials/prompts 端点（routers/pets.py:161-170）在 iOS 侧完全未接线；Seedream 多参考图（pet_identity/place_environment）对凭据卡无实际作用。硬编码 documentAspectRatio 的 3:2（见 P1-6）成为唯一的尺寸真相来源。
- 建议：决定"本地合成"还是"服务端生图"。若保留本地合成，删除 PetCredentialPromptTemplate / documentImagePrompt / fetchCredentialPrompts 死代码并合并两枚举；若接服务端，补调用并处理动态尺寸。

### P1-6 图片尺寸/宽高比硬编码，与 Seedream 实际尺寸不一致

- 证据：Views/PetCredentialModels.swift:110-117 — documentAspectRatio 硬编码 1536.0/1024.0（3:2）与 1448.0/1086.0（护照）；Views/PetCredentialCard.swift:143 用其 .aspectRatio(...)。
  后端：credential_prompt_builder.py:79 与 schemas/place.py:53 size="1536x1024"；但 Seedream provider 默认尺寸是 1024x1024（image_provider/seedream.py:27），且 illustrated_guide.py:124 用 1024x1536（竖 9:16）、event_generator.py:277 用 1024x1024。
- 影响：Seedream 支持的尺寸白名单与 1536x1024 / 1448x1086 可能不符；一旦把服务端生图接入凭据卡，固定 3:2 会拉伸/裁切。
- 建议：统一尺寸常量（或由后端 size 字段回传实际尺寸），iOS 依 size 动态计算宽高比，而非硬编码。

### P1-7 时间计算逻辑在 4 处 View 重复 + 业务逻辑残留

- 证据："当天分钟数" Calendar.current.component(.hour...)*60 + component(.minute...) 在 4 处重复：
  Views/JourneyMapModels.swift:136、Views/JourneyGuideDigest.swift:234,246、Views/SecondaryViews.swift:182、Views/CommunicatorChat.swift:436-437（另有独立 DateFormatter）。
  更严重的是 SecondaryViews.swift:178-190 的 dayPlanPhase(for:index:now:) 与 JourneyMapModels.swift:132-144 的 phase(for:items:index:now:) 逻辑几乎逐行相同（同为"哪个 day-plan 项是当前项"判定），跨两个 View 文件重复。
- 影响：同一业务规则多处维护，改一处漏一处。
- 建议：抽共享 DayPlanPhase 计算工具（或下沉到 VM/Model 层）；时间格式化统一走一个 TimeOfDay 帮助类型。

### P2-1 文本清洗正则脆弱、业务逻辑落在 View 扩展

- 证据：Views/JourneyTimeline.swift:499-529 — petSoulUserFacingText 用 12 条硬编码字符串替换 + 5 条正则（:518-524，含 来自(?:高德|Google|...|DeepSeek|...|GPT|...) 与英文标识符正则 :522）来清洗 LLM 可能泄漏的 provider/model 名。JourneyTimeline.swift:531-537 petSoulCleanSpacing、:545-555 cleanedTags 同类。
- 影响：这是"模型切换防御"的证据（团队已知 LLM 会漏 provider 名），但把文案规整逻辑放在 View 扩展、用脆弱的正则兜底；新增 provider 名（如以后换模型）需同步维护正则。
- 建议：这类"服务端文案归一"优先在后端 prompt/后处理做；iOS 侧清洗收敛到一个独立 TextSanitizer，从 View 扩展中移除。

### P2-2 APIClient 在 @MainActor 上做解码 + 重试退避

- 证据：Core/Networking/APIClient.swift:4 @MainActor；send / sendData（:40-67）在主 actor 上 decoder.decode（大 payload：worldSnapshot / illustratedGuide pages）并 await sleeper(...) 退避。
- 影响：Task.sleep 挂起不阻塞，但大 JSON 解码在主线程，理论上可卡 UI 若干毫秒~数十毫秒。
- 建议：解码可移到非隔离上下文（或对超大 payload 用 Task.detached）；当前影响有限，记为待优化。

### P2-3 MediaCache 同步文件写 + 无 TTL

- 证据：Core/Persistence/MediaCache.swift:22-24 data.write(to: options: .atomic) 同步阻塞写；MediaCache 非 @MainActor，但调用点可能在主 actor 语境。
- 建议：写盘移后台；情感资产永久缓存可接受，但可加"容量上限/最近最少使用"清理。

### P2-4 疑似死代码（拆分后遗留）

- 证据：
  - Services/RemotePetJourneyService.swift:150-154 collectTravelQuestSouvenirs（非 economy 变体）疑似未被调用（实际消费走 collectTravelQuestSouvenirsWithEconomy，JourneyViewModel+Souvenirs.swift:24）。
  - Services/RemotePetJourneyService.swift:342-344 SuccessResponse 仅在 unregisterPushDevice 使用，属正常。
  - Core/Networking/APIClient.swift:98-119 RemoteDateDecoding 为顶层 enum（internal），仅 APIClient 使用，可降为 private/嵌套。
- 建议：复核后删除或收紧访问级别。

### P2-5 后端小漂移：IllustratedGuide.model 在 volcengine 下仍可能报 gpt-image-2

- 证据：illustrated_guide.py:108,114-115 model=self.settings.image_model（默认 gpt-image-2，config.py:32）；仅当生成成功且 image.model 非空时才被覆盖（illustrated_guide.py:143,159）。
- 影响：iOS IllustratedGuide.model（可选，GuideModels.swift:218）在"未生成/生成前"阶段拿到 gpt-image-2，与 volcengine 实际模型 doubao-seedream-4-0-250828 不符。iOS 不显示该字段，故无用户可见影响。
- 建议：后端 model 字段应取实际 image provider 的 model（seedream.py:151 已回传），而非配置里的 image_model。

### P2-6 mock 数据陈旧 + 类型漂移

- 证据：Services/MockPetJourneyService+Guide.swift:34 model: "mock-guide-model"（后端现已 deepseek-chat）；Services/MockPetJourneyService+Journey.swift:383,394 size: "1536x1024"。
  Models/EconomyModels.swift:81 coinInflowDate: String vs 后端 date（schemas/economy.py:40）；Models/SouvenirModels.swift:131 preferredStartDate: String? vs 后端 date|None（schemas/travel.py:327）。均能解（ISO date 字符串可入 String），但类型语义弱。
- 建议：mock 对齐线上值；日期字段改 Date 或显式 String 并注释。

### 已验证正确（非问题，列作基线）

- 非幂等 POST 不重试：RemotePetJourneyService.swift:296-310 postJSON/patchJSON/delete 均 decode(...) 默认 .none；仅 get（:293）传 .idempotent。符合"写不重试"。
- 通知/计时器清理：全 iOS 代码 grep 无 NotificationCenter.default.addObserver / Timer.scheduled/publish 残留（0 命中），无观察者泄漏。
- @MainActor：VM、APIClient、NetworkMonitor、AppSessionStore、ServiceContainer 均标注；NetworkMonitor.swift:19-21、ServiceContainer（AppSessionStore.swift:217）用 [weak self]/[weak session] 正确。
- 5 秒轮询任务可取消：JourneyViewModel+Lifecycle.swift:7-16 refreshTask 弱捕获 self；JourneyMapView.swift:194-199 .onAppear{ start() } / .onDisappear{ stop() } 成对，无 StructuredConcurrency 泄漏。
- 模型名不上屏：全文 grep .model/.provider 命中仅在 Mock 数据与 Models 定义，无 View 渲染路径。

---

## 2. 契约漂移表（iOS 字段 vs 后端字段 vs 状态）

状态：✅ 一致 · ⚠️ iOS 缺失/可选（安全忽略但不展示） · 🔴 语义漂移

| # | iOS 结构体（文件:行） | iOS 字段 | 后端字段（schemas/*.py:行） | 状态 | 说明 |
|---|---|---|---|---|---|
| 1 | LifeTickResult Models/WorldSimulationModels.swift:186-216 | 无 | observation: WorldObservation world.py:124 | ⚠️ | iOS 丢弃世界观测对象 |
| 2 | LifeTickResult 同上 | 无 | retrieved_memories: list[MemoryRecord] world.py:125 | ⚠️ | iOS 丢弃检索到的记忆 |
| 3 | LifeTickResult 同上 | needState/intent/action/decision 全 ? | 后端均必填 world.py:126-129 | ⚠️ | iOS 全可选，后端缺字段也不报错，漂移被掩盖 |
| 4 | PetNeedState WorldSimulationModels.swift:91-117 | 全 Int? | energy/hunger/social/curiosity/comfort/playfulness 必填 world.py:53-64 | ⚠️ | 同上 |
| 5 | PhotoMission Models/PhotoModels.swift:38-76 | 无 | prompt_blocks/quality_report/retry_count/failure_category place.py:103-106 | ⚠️ | 照片质量报告/重试信息 iOS 不取 |
| 6 | PetAuthoredGuide Models/GuideModels.swift:48-98 | 无 | guide_theme/selected_places/why_pet_likes_it/why_owner_may_care/photo_potential/crowd_risk/pet_first_person_guide guide.py:85-91 | ⚠️ | 攻略选点与解释 iOS 不取 |
| 7 | PetAuthoredGuide 同上 | voiceProvider/criticProvider/factProviderPriority GuideModels.swift:69-71 | voice_provider/critic_provider/fact_provider_priority guide.py:94-96 | ✅ | 一致 |
| 8 | PlaceEvidencePacket Models/TravelQuestModels.swift:206-236 | 无 | provider_evidence: dict travel.py:95 | ⚠️ | 证据明细 iOS 不取 |
| 9 | OwnerMessageResponse Models/JourneyModels.swift:166-180 | 无 | owner_intent: OwnerIntentResult pet.py:253 | ⚠️ | 意图识别结果 iOS 不取 |
| 10 | SouvenirItem Models/SouvenirModels.swift:38-117 | 无 | memory_type/source_photo_mission_id/bag_influence_tags economy.py:133-135 | ⚠️ | 纪念品来源/包影响标签 iOS 不取 |
| 11 | PlaceSignal Models/RouteModels.swift:81-121 | 无 | raw: dict place.py:29 | ⚠️ | 原始数据 iOS 不取（低风险） |
| 12 | EconomyTransaction Models/EconomyModels.swift:150 | operatorName | operator economy.py:67 | ✅ | CodingKey 正确映射 |
| 13 | PetDNA Models/PetCoreModels.swift:159 | hobbies | hobby pet.py:15 | ✅ | CodingKey hobbies="hobby" 正确 |
| 14 | TravelGuideResearchProvider Models/TravelQuestModels.swift:69-74 | mock/doubao_social/openai_web_search/hybrid | 同名 travel.py:53-57 | ✅ | 原始值完全一致（含 openai_web_search） |
| 15 | OwnerFund Models/EconomyModels.swift:81 | coinInflowDate: String | coin_inflow_date: date economy.py:40 | 🔴 | iOS 用 String 解 date（能跑，类型弱） |
| 16 | TravelQuest Models/SouvenirModels.swift:131 | preferredStartDate: String? | preferred_start_date: date/None travel.py:327 | 🔴 | 同上 |
| 17 | PetCredentialPrompt Models/CredentialModels.swift:6-13 | PetCredentialPromptKind 6 case | PetCredentialKind place.py:38-44 | ✅ | 原始值一致；但 UI 另有重复枚举 PetCredentialKind（Views/PetCredentialModels.swift:54） |

结论：后端新增字段（尤其世界模拟/照片质量/攻略选点）全部是 iOS 单向缺失，方向是"iOS 落后于后端"。无反向的"iOS 独有/后端缺失"字段。多数属"安全忽略"，但 LifeTickResult.observation/retrieved_memories 与 PhotoMission.quality_report 是有产品价值却未消费的数据。

---

## 3. 模型切换风险表（DeepSeek / Seedream）

| # | 风险点 | iOS 位置 | 后端位置 | 状态 | 建议 |
|---|---|---|---|---|---|
| 1 | 文本 LLM 换 deepseek-chat，走 /chat/completions + json_object（无 json_schema strict、无 /responses） | iOS 无模型名硬编码、无 JSON strict 假设 | config.py:23-28；agent_brain.py:171、photo_mission_brain.py:138 | ✅ 安全 | iOS 只 Codable 解码，strict 由后端负责；无需改动 |
| 2 | UI 是否显示模型/provider 名（faf38e5 验证） | 全文无 .model/.provider 渲染 | — | ✅ 已修复 | 确认通过；无用户可见 OpenAI/GPT/DeepSeek 字样 |
| 3 | TravelGuideResearchProvider.openai_web_search 残留 | Models/TravelQuestModels.swift:72 | travel.py:56；guide_orchestrator.py:60 | ✅ 一致 | 这是"研究 provider"非文本 LLM，保留无害 |
| 4 | 图片尺寸硬编码 1536x1024（3:2） | Views/PetCredentialModels.swift:115 | credential_prompt_builder.py:79、place.py:53 | 🔴 风险 | Seedream 默认 1024x1024（seedream.py:27），尺寸可能不匹配；iOS 应依服务端 size 动态算宽高比 |
| 5 | 凭据卡宽高比 3:2 / 护照 1448:1086 | Views/PetCredentialModels.swift:110-117、PetCredentialCard.swift:143 | — | 🔴 风险 | 同上；且凭据卡目前是本地合成，未接服务端生图 |
| 6 | Seedream 多参考图角色 pet_identity/place_environment | iOS 未消费（fetchCredentialPrompts 死代码） | photo_pipeline.py:21-23、seedream.py:75-81 | ⚠️ 未接线 | 见 P1-5；若接服务端需支持多参考图 |
| 7 | revised_prompt | iOS 无引用 | image_provider/models.py:15；illustrated_guide.py:138 | ✅ 安全 | Seedream 不填 revised_prompt，后端 fallback 到 page.image_prompt，iOS 无感 |
| 8 | IllustratedGuide.model 在 volcengine 下报 gpt-image-2 | GuideModels.swift:218（可选，不显示） | illustrated_guide.py:108,114-115 | ⚠️ 漂移 | 后端 model 字段应取实际 provider model（seedream.py:151 已回传），iOS 不显示故低风险 |
| 9 | mock 模型名 mock-guide-model 陈旧 | MockPetJourneyService+Guide.swift:34 | 后端 deepseek-chat | ⚠️ 低风险 | 不显示；建议对齐更新 |
| 10 | 新配置字段 token-usage（last_remote_prompt_tokens/completion_tokens） | iOS 无消费（不调用 /api/v1/*/config） | health.py:82-134；agent_brain.py:160-161、photo_mission_brain.py:127-128 | ✅ 安全忽略 | iOS 忽略新字段，无兼容问题；如需监控可新增只读调用 |
| 11 | 图片 URL 为 Volcengine 签名 URL，可能过期 | MediaCache.swift:14-28 永久落盘 | seedream.py:158-162 下载 | ⚠️ 低风险 | MediaCache 首次下载后永久缓存，恰好规避签名过期；但 AsyncImage 直连场景可能过期 |

总体：文本切换对 iOS 零破坏（无模型名/JSON strict 假设）；图片切换主要风险集中在尺寸/宽高比硬编码（#4、#5）与服务端 model 字段不准确（#8）。无 revised_prompt、无 /responses、无 json_schema 的 iOS 侧依赖。

---

## 4. 测试覆盖缺口

### 已覆盖

| 层 | 测试文件 | 覆盖点 |
|---|---|---|
| 网络重试/错误归一 | APIClientTests.swift | 幂等重试、非幂等不重试、4xx 不重试、offline→信号语言、decoding→invalidResponse、退避抖动、NetworkMonitor 发布 |
| 持久化 | PersistenceTests.swift | Cache store/load/upsert/per-pet 隔离/remoteFirst 回退/purge；Outbox 顺序 drain、失败停止；MediaCache 存取清理 |
| Mock 服务 | MockPetJourneyServiceTests.swift | createPet/feedback/postcard/communicator/翻译/路线 |
| 会话存储 | AppSessionStoreTests.swift | onboarding 完成/恢复/重置 |
| Push 路由 | PushDeepLinkRouterTests.swift | category 解析/consume/未知忽略 |

### 未覆盖（按重要性排序）

1. ViewModel 层完全无测试 — JourneyViewModel（及 5 个扩展：start/stop/loadInitial/refreshStatus/hydrate/outbox/translate/souvenir 状态机）、CommunicatorViewModel、MemoryHubViewModel、OnboardingViewModel、ConnectingViewModel、StreetRankViewModel、WorldStoryViewModel 零覆盖。这是最大的缺口：核心业务（离线回退、轮询、发件队列联动、图片生成状态机）无回归保护。
2. 无契约解码 fixture 测试 — 无"后端 JSON → iOS Models"的反序列化测试，故第 2 节所有字段漂移永不红。这是契约漂移长期潜伏的根因。
3. RemotePetJourneyService 无测试 — multipart 编码（makeMultipartBody）、Bearer 头注入、错误归一、各 endpoint 路径/query 编码均未测。
4. 远程日期解码无测试 — APIClient.swift:98-119 RemoteDateDecoding（小数秒/无小数秒 ISO8601 双路径）无单测。
5. Outbox 边界无测试 — 无 poison message/队头阻塞/attempts 上限测试（对应 P0-1）。
6. 认证无测试 — 无 token 注入/401/刷新/登出测试（对应 P0-2）。
7. 缓存 TTL 无测试 — 无"超龄缓存应失效"测试（对应 P0-3）。
8. 模型名/provider 无断言 — 无测试锁定"UI 不显示 model/provider 名"，faf38e5 的修复无回归护栏。

注：MockPetJourneyServiceTests.swift:69,96 使用样板宠物名"小福"，符合 AGENTS.md（仅限 Mock/测试），非问题。

---

## 5. 建议行动顺序

1. P0 三连（健壮性）：Outbox 队头阻塞 + attempts 上限 → 401/刷新 → 缓存 TTL。
2. P1 契约补齐：优先补 LifeTickResult.observation/retrieved_memories 与 PhotoMission.quality_report（有产品价值），并配 fixture 契约解码测试作为长期护栏。
3. P1 架构回潮：WorldStoryViewModel 走 APIClient；CommunicatorViewModel/MemoryHubViewModel 迁入 ViewModels/；清理凭据死代码与重复枚举。
4. P1 尺寸对齐：凭据/图片尺寸由服务端 size 字段驱动，去掉硬编码 1536/1024。
5. P2 清理：死代码、重复时间计算、RemoteDateDecoding 访问级别、后端 IllustratedGuide.model 取值。

---

审计范围文件：iOS 96 个生产 Swift 文件 + 5 个测试文件；后端 schemas/（base/pet/economy/place/travel/world/guide/auth）、config.py、image_provider/、illustrated_guide.py、photo_pipeline.py、routers/health.py、routers/pets.py、credential_prompt_builder.py。
