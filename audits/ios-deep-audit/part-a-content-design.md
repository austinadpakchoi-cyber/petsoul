# PetSoul iOS 深度审计（Part A：内容与设计系统合规）

- 范围：PetJourneyIOS/PetJourneyIOS/ 96 个 Swift 文件 + Info.plist + 资源目录。
- 性质：只读审计，未修改任何代码，未提交。
- 依据：petsoul/AGENTS.md 四条硬规则 + 设计系统 DesignTokens.swift + 产品语音约定。
- 目标：验证 faf38e5 是否把上一轮 P0/P1 修对，并比上一轮更深地挖出新问题。

---

## 一、执行摘要（数字统计）

| 项 | 数量 |
| --- | --- |
| 复核 faf38e5 的修复项 | 6 通过 / 2 遗漏（其中 P0-1 为部分遗漏） |
| P0（本轮） | 1 |
| P1（本轮） | 4 |
| P2（本轮） | 10 |

一句话结论：faf38e5 把「手机->通讯器」的主战场（Tab 标题、头部、按钮、引导文案）和「消息/在线/正在输入」的 IM 措辞修对了，供应商名/模型名/脱敏正则/.white->surface 两处/生图提示词也都落地。但它漏掉了 P0-4 的 wire 层供应商枚举（doubao_social / openai_web_search 原样还在），并且还有 2 处「手机」残留在用户可见文案里（Info.plist 权限文案 + 明信片 petVoice）。上一轮审计完全没看无障碍，而本轮头部新发现正是无障碍：8 处常驻 TimelineView 动画既不响应 accessibilityReduceMotion、也没有 1/30 帧率上限。

---

## 二、faf38e5 修复验证表

| # | 上轮问题 | faf38e5 声明 | 验证结果 | 证据 |
| --- | --- | --- | --- | --- |
| 1 | P0-1「手机」作产品名（约 30 处） | 手机->通讯器 33 处 | ⚠️ 部分遗漏：主战场已改，但剩 2 处用户可见「手机」未改 | 见 §3.4 |
| 2 | P0-2 用户可见供应商名 GPT/豆包 | 供应商名清理 | ✅ 通过 | Services/MockPetJourneyService+Guide.swift:240 改为「沿途线索 + 地图资料」/「本地生活线索 + 地图资料」 |
| 3 | P0-3 模型名 gpt-5.5 | 模型名清理 | ✅ 通过 | Services/MockPetJourneyService+Guide.swift:34 改为 mock-guide-model；gpt-5 全库 0 命中 |
| 4 | P0-4 供应商枚举 doubao_social/openai_web_search | （属「供应商名清理」范畴但未声明） | ❌ 遗漏 | Models/TravelQuestModels.swift:71-72 原样保留（见 §3.1） |
| 5 | P1-1 .white->surface 两处 | .white->surface 2 处 | ✅ 通过 | Views/JourneyChapter.swift:157、Views/PetOnboardingView.swift:408 均改为 DesignTokens.surface |
| 6 | P1-2「消息/在线」IM 措辞 | 消息->通讯 | ✅ 通过 | Views/CommunicatorViews.swift:298,385 消息->通讯；Views/CommunicatorChat.swift:265 还没有消息->还没有来信；Views/CommunicatorViews.swift:67 通讯器在线->信号已连接 |
| 7 | P1-4 生图提示词写死 GPT | 模型名清理 | ✅ 通过 | Views/PetCredentialModels.swift:655 改为 PetSoul-generated content |
| 8 | P1-5 脱敏正则不含新供应商 | 正则扩充 | ✅ 通过 | Views/JourneyTimeline.swift:521-522 加入 deepseek/doubao/gpt/豆包/抖音/小红书/文心/通义/智谱 |

需要返工：1 项——P0-4 的 wire 枚举未清理（Models/TravelQuestModels.swift:71-72），以及 §3.4 的 2 处「手机」残留。

---

## 三、发现（按 P0/P1/P2 分级，含 file:line + 片段 + 建议）

### P0-1 wire 层供应商枚举仍硬编码旧供应商 —— faf38e5 遗漏

- 位置：Models/TravelQuestModels.swift:69-74
- 片段：

    enum TravelGuideResearchProvider: String, Codable, Equatable, Sendable {
        case mock
        case doubaoSocial = "doubao_social"      // 旧供应商
        case openAIWebSearch = "openai_web_search" // 旧供应商
        case hybrid
    }

- 问题：这是走 wire 的协议值。后端已切 DeepSeek + 国内生图，doubao_social / openai_web_search 是过期契约。faf38e5 改了用户可见的 providerName 和 model，却漏了这层枚举。
- 建议：与后端对齐新枚举（如 deepseek、国内生图 provider），确认 hybrid 语义；若枚举仅内部使用，改为不写死具体供应商的抽象名。

### P1-1 View 文件硬编码「其他灵魂」宠物名 + 三处重复（上轮 P1-3 的漏网）

- 位置：Views/JourneyMapModels.swift:263-272（上轮审计未覆盖此处）
- 片段：

    static func samples(around events: [JourneyMapEvent], ...) -> [DemoCompanionPet] {
        // 常驻 NPC 阵容——与后端 communicator/npc_society.py 是同一批身份,改动需两边同步。
        let cast: [(String, PetType, ...)] = [
            ("Nana", .cat, "看橱窗", ...),
            ("团子", .dog, "等面包", ...),
            ("啾啾", .parrot, "学人说话", ...),
            ("Momo", .rabbit, "听风铃", ...),
            ("米粒", .hamster, "找补给", ...),
            ("Lucky", .dog, "追光斑", ...)
        ]
    }

- 问题：Views/ 里写死了 6 个具体宠物名，且同一批 NPC 身份在三处重复：JourneyMapModels.swift:266-272（地图同伴）、Services/MockPetJourneyService+Communicator.swift:577-582（npc-nana-cat/…，Mock 服务）、后端 npc_society.py。注释自证「改动需两边同步」——这是典型 drift 风险。上轮 P1-3 只点名 WorldLifeEvent.swift，这里漏了。
- 建议：把这批 NPC 名单收敛为单一数据源（Mock 服务或 SampleContent），View 只消费；后端同理。

### P1-2 无障碍：8 处常驻动画不响应 reduceMotion、无帧率上限

- 规则：AGENTS.md——常驻动画必须响应 accessibilityReduceMotion，帧率上限 1/30。
- 命名那 4 个（AmbientSignalField/SignalPulseRings/SignalBars/EnergyRing）在 DesignTokens.swift:171,242,269 与 EnergyRing.swift:8,42 已正确 gate（TimelineView(.animation(minimumInterval: 1/30, paused: reduceMotion))）。但以下 8 处同样常驻的动画既没有 reduceMotion 环境变量、也没 minimumInterval（.animation 默认跑满刷新率，可达 60–120fps）：

| file:line | 视图 | 说明 |
| --- | --- | --- |
| Views/JourneyMapMarkers.swift:200 | PetMotionWake | 地图标记运动尾迹 |
| Views/JourneyMapMarkers.swift:245 | PetFootstepOrbit | 足迹环绕 |
| Views/JourneyTelemetry.swift:12 | PixelPetActivityAnimation | 像素宠物活动动画 |
| Views/JourneyTelemetry.swift:373 | NavigationProgressGlint | 导航扫光 |
| Views/JourneyTelemetry.swift:401 | NavigationPulseDot | 导航脉冲点 |
| Views/JourneyLiveSignal.swift:391 | SleepBreathingHalo | 睡眠呼吸光环 |
| Views/JourneyLiveSignal.swift:420 | SleepBreathDot | 睡眠呼吸点 |
| Views/JourneyMapViewport.swift:528 | NavigationScanOverlay | 导航扫描线 |

- 建议：给这 8 处统一加 @Environment(\.accessibilityReduceMotion) var reduceMotion，改用 TimelineView(.animation(minimumInterval: 1/30, paused: reduceMotion))，闭包内 let time = reduceMotion ? 0 : timeline.date...

### P1-3 MemoryEditor 用户可达表单暴露内部机制（违反硬规则 2 + 4th wall）

- 位置：Views/MemoryEditor.swift（用户可通过 Views/MemoryHub.swift:299 的「可编辑记忆档案」进入，非 DEBUG 门控）
- 片段：

    // :388-389  English 枚举直接做选项
    let memoryTypeOptions = ["episodic", "recent_episodic", "relationship", ...]
    let kindOptions = ["owner_note", "identity", "owner_preference", "feedback", ...]
    // :420-441  表单字段
    Section("分类") { Picker("Kind", ...) ; Picker("Memory Type", ...) }
    TextField("来源", text: $source)                    // :431
    TextField("来源事件 ID", text: $sourceEventID)        // :432
    Section("权重") { SliderValueRow("显著度",...) ; SliderValueRow("重要度",...) ; SliderValueRow("情绪值",...) ; SliderValueRow("信心值",...) } // :437-441

- 问题：「来源事件 ID」「权重」「显著度/信心值/情绪值」是内部记忆引擎字段，直接以中文表单 + 英文枚举值（episodic/owner_note/manual）暴露给用户，正面违反硬规则 2「文案不得暴露内部机制」。
- 建议：把该编辑表单降级为 DEBUG-only（#if DEBUG），或将「来源事件 ID/权重/情绪值」等字段从用户表单移除，仅保留「标题/内容/照片/分类」等仪式感字段。

### P1-4「手机」残留 2 处用户可见（faf38e5 漏改）

- 位置与片段：
  1. Info.plist:29 —— <string>选择一张宠物照片，用来生成手机身份卡。</string>（相册权限文案，系统弹窗对用户可见，应作「通讯器身份卡/宠物身份卡」）。
  2. Services/MockPetJourneyService+Journey.swift:366 —— postcardText: "我把手机举得低低的，在 (place.name) 把这一刻留下来了..."（明信片 petVoice 直接对用户可见，应作「我把镜头/画面收得低低的」）。
- 说明：另 4 处「手机」经上下文判断有意保留：Views/JourneyDayRecap.swift:639-640（换手机/重装 App，物理设备）；Services/MockPetJourneyService+Economy.swift:228（贴在手机角落，实物贴纸）；Services/MockPetJourneyService+Journey.swift:360（landmarkHints 拍照美学「低角度手机视角」，内部提示词）。

### P2-1「识别/生成/真实」机制词散布在用户文案

- 识别：
  - Views/PetOnboardingView.swift:246 —— case .photo: "开始照片识别"（应作「开始记住这张脸 / 收好这个锚点」）。
  - Services/PetJourneyService.swift:15 —— "服务返回的数据暂时无法识别"（错误文案应仪式化，如「信号暂时没有接通」）。
- 生成（暴露 AI 生成机制）：
  - Views/CommunicatorChat.swift:517 "生成中"；:607 "这一刻的照片正在生成"。
  - Views/SecondaryViews.swift:220/552/559/589 "已生成/正在生成真正的手绘攻略图/生成信号暂时不稳定/等待生成手绘攻略图"。
  - Views/PetOnboardingView.swift:248 "生成通讯卡并寻找 TA"。
- 真实（暴露「真实路网/真实地点」模拟机制，全库 36 处，代表性）：
  - Views/TravelGuide.swift:365 Text("真实移动")；Views/JourneyDaySchedule.swift:63 "TA 沿真实道路去沙坡尾…"；Views/JourneyRouteSupport.swift:37 "沿真实道路走"。
- 建议：统一替换为无机制措辞——「生成」->「洗出来/写好/画好」，「识别」->「记住/收好」，「真实」-> 直接去掉（如「沿道路走」「这趟移动」）。

### P2-2 地图标注卡片仍用裸 UIColor.white 做背景（上轮 P2-2 未修）

- 位置：Views/WorldAnimalViews.swift:100,108,143,148,248,249,259,285
- 片段：container.contentView.backgroundColor = UIColor.white.withAlphaComponent(0.40)（及 0.44/0.58/0.36；dot.layer.borderColor = UIColor.white.cgColor）。
- 问题：深色地图氛围下白色半透明卡片发冷；DesignTokens.annotation 有 titleInk/subtitleInk/shadowBrown 但缺「卡片底色」令牌。
- 建议：在 annotation 下补 cardSurface 令牌（自适应或暖色），替换裸白。

### P2-3 阴影用 .black 而非 deepInk（设计令牌缺口）

- 规则：阴影必须用 deepInk（ink 深色模式会变浅发白光）。.black 虽不发白，但不是语义令牌。
- 位置：Views/JourneyDayRecap.swift:242,390,555,606；Views/CommunicatorChat.swift:260；Views/PetCredentialWallet.swift:455,587；Views/JourneyTimeline.swift:243（均为 .shadow(color: .black.opacity(0.05...0.38), ...)）。
- 建议：替换为 DesignTokens.deepInk.opacity(...)。

### P2-4「账号系统」措辞进入用户文案（4th wall）

- 位置：Views/Map/MapControlDock.swift:84,86 —— Label("账号 · (accountName ?? 已登录)")、Label("保存旅程到账号")；Views/JourneyDayRecap.swift:640 —— "用 Apple 账号一键保存..."。
- 问题：AGENTS.md 未禁「账号」，但「账号系统」是内部机制，出现在用户文案削弱仪式感。
- 建议：软化为「保存旅程 / 旅程已安全保存 / 用 Apple 登录保存」，弱化「账号」字面。

### P2-5 术语不一致：「灵魂世界」vs 规范「平行世界」+ 显式免责声明

- Views/WelcomeView.swift:118 —— Text("灵魂世界正在旅行")。规范术语是「平行世界」（AGENTS.md 通篇、PetCredentialModels 里「平行航线/平行房卡」都用「平行」），「灵魂世界」偏宗教感且与体系不一致。
- Views/WelcomeView.swift:611 —— "这里是情感陪伴体验，不代表宗教、医疗或真实灵性声明..."。这是故意的合规免责声明，直接破 4th wall；建议产品确认是否保留，或收敛为更轻的脚注。

### P2-6 动态类型：minimumScaleFactor 过低致长中文缩到不可读

- 位置：Views/JourneyTimeline.swift:239 minimumScaleFactor(0.58)；Views/PetCredentialCard.swift:314 0.62；Views/PetCredentialCard.swift:362 0.55（均搭配 .lineLimit(1)）。
- 问题：长中文在辅助功能大字号下会被压到 55–62% 字号，可读性差；应改用多行 lineLimit 或 fixedSize(vertical: true) 换行，minimumScaleFactor 保持 ≥0.8。

### P2-7 重复文案漂移：同一段厦门行程/同一批 NPC 多处硬编码

- 厦门行程（八市/沙坡尾/环岛路/白城/筼筜湖/山海步道）在四处重复：
  - Services/MockPetJourneyService+Journey.swift:135-139,449-453（Mock 数据，canonical）
  - Views/JourneyDaySchedule.swift:46,58,63,74,85,90,101（View 硬编码）
  - Views/JourneyMapModels.swift:227-232（MerchantStop 样本）
  - Views/JourneyGuideDigest.swift:444,447（hasCityAnchor = [八市,沙坡尾,...] 硬编码清单）
- 具体字符串「把这段路记进通讯器」同时出现在 Views/JourneyMapModels.swift:205 与 Services/MockPetJourneyService+Journey.swift:476。
- 城市/品牌名硬编码：厦门/京都/雷克雅未克（Views/JourneyMapModels.swift:227,234,241、Views/JourneyGuideDigest.swift:447），品牌 高德地图/Google Maps/小红书/抖音（Services/MockPetJourneyService+Guide.swift:247 recommendedSources，当前未渲染但可回传泄漏）。
- 建议：View 层只消费 Mock/远程返回的行程与 NPC，删掉 View 里的硬编码样本与锚点清单。

### P2-8 中英混排不一致（残余小项）

- Views/MemoryEditor.swift:388-389 English 枚举选项（已并入 P1-3）。
- Views/PetCredentialModels.swift:524 statusLine: "On the way · 平行航线" 中英混排（证件卡实物语境可保留但风格需统一）。
- Views/MemoryHub.swift:322 "证件照、身份信息和远行凭证"、Views/PetCredentialCard.swift:434 "基本信息/字段信息" 的「信息」为轻度技术词。

---

## 四、深色模式与无障碍清单

### 深色模式

| 项 | 结论 | 位置 |
| --- | --- | --- |
| 语义令牌自适应 surface/… | ✅ 正常，Color(light:dark:) 覆盖主色板 | DesignTokens.swift:10-29 |
| 硬编码 .white 作背景 | ⚠️ 地图标注卡仍用 UIColor.white（P2-2） | WorldAnimalViews.swift:100,108,248,249,259 |
| 手账贴纸 Color.white.opacity(0.62) | 灰色地带（上轮 P2-3，实物材质可判 OK） | IllustratedGuidePreview.swift:294 |
| 阴影用 ink | ✅ 无 .shadow(color: DesignTokens.ink)（合规） | 全库 0 命中 |
| 阴影用 .black | ⚠️ 8 处未走 deepInk 令牌（P2-3） | JourneyDayRecap.swift:242,390,555,606 等 |
| 深色下硬编码浅色 | ✅ 未发现散落 Color(red:)/UIColor(red:)（0 命中）；固定色（paper/notebook/mapWash/credential/welcome/annotation）已按实物/场景语义收敛进令牌 | DesignTokens.swift:31-111 |

### 无障碍

| 项 | 结论 | 位置 |
| --- | --- | --- |
| 命名 4 个常驻动画响应 reduceMotion + 1/30 | ✅ | DesignTokens.swift:171,242,269、EnergyRing.swift:8,42 |
| 其它常驻 TimelineView 响应 reduceMotion | ❌ 8 处未 gate、无帧率上限（P1-2） | 见 §P1-2 表 |
| WelcomeView 世界故事条 | ✅ 过渡/动画已按 reduceMotion 降级 | WelcomeView.swift:500,557-558 |
| 动态类型 / 大字号长中文 | ⚠️ minimumScaleFactor 0.55-0.62 过低（P2-6） | JourneyTimeline.swift:239、PetCredentialCard.swift:314,362 |
| VoiceOver 标签 | ✅ 关键动作有 accessibilityLabel（约 28 处：编辑/删除/关闭/返回地球视角/球场地图等）；装饰动画均 accessibilityHidden(true) | MapControlDock.swift:111,129、WorldAnimalViews.swift:52,240 等 |

---

## 五、附：正面确认（无问题项）

- 小福、模拟、占位、第一版、正在输入、输入中、在线、已读、好友、联系人、通知栏、接口、数据源、后台、引擎、算法、提示词、系统、版本、升级、数据同步：全库 0 命中。
- 离线 8 处全部在代码注释，UI 实际显示「信号弱」（Core/Networking/NetworkMonitor.swift:4），合规。
- Mock 69 处全部在 Services/MockPetJourneyService* 与 App/AppSessionStore，未泄漏进 View。
- provider/model/source/API 在 Views 中仅 Views/JourneyRouteSupport.swift:94-101（内部局部变量）与脱敏正则，无用户可见渲染；sourceLabel（Views/JourneyRouteSupport.swift:30-40）已映射为「沿步行路走/沿真实道路走/沿街慢慢走」等仪式化中文。
- 命令/控制 仅出现在「不用命令 TA 照做」「不控制真实路线」的反控制语境，产品语音正确。
- 治疗/复生/复活/投胎/天堂/轮回 0 命中，无医疗/宗教硬性越界。

---

审查方式：对 96 个 Swift 文件做 手机/消息/GPT/豆包/gpt-5/POI/正在输入/输入中/模拟/mock/Mock/占位/第一版/provider/source/model/API/接口/数据源/后台/服务器/引擎/算法/识别/AI/模型/提示词/系统/生成/token 及 hex/Color.white/UIColor.white/Color(red:)/UIColor(red:)/宠物名/城市品牌名/TimelineView/reduceMotion/shadow(color:)/lineLimit 等 token 的 grep，并逐条读上下文定级。