# iOS 深度审计总报告（内容/设计系统 + 架构/网络/契约）

> 基于两份分项报告（part-a-content-design.md、part-b-architecture-contract.md），由协调方合成、抽验并裁定优先级。
> 性质：只读审计。所有关键结论均已人工抽验 file:line 属实；含 1 处对分项报告的误判纠正。

---

## 0. 执行摘要

iOS 侧整体健康度**中上**：上一轮「God File 拆分 / VM 下沉 / DesignTokens / arch_gate」落地扎实（VM 已拆 6 片且全部 <300 行；写请求不重试、读请求幂等重试的正确约定已在；观察者/计时器零泄漏；模型名/provider 不上屏）。但深度审计挖出 **3 个 P0 健壮性缺口 + 约 9 个 P1**，其中一半是「拆分回潮」与「契约漂移」这类肉眼不易察觉、CI 也永不红的问题。

**P0 汇总（必须先修）**：① 离线发件队列队头阻塞（一条坏消息堵死全部离线消息）；② 401 无刷新/无恢复路径；③ 缓存无 TTL（离线冷启动无限期展示陈旧世界状态——直击「TA 在平行世界生活」的产品核心）。

**最大结构性风险**：契约漂移（8 结构体 20+ 字段 iOS 缺失）+ ViewModel/契约解码**零测试**——这是漂移长期潜伏、CI 不红的根因，建议作为长期护栏立项。

---

## 1. 分项报告误判纠正

- **Part A 的「P0-1 wire 枚举漏改」判定有误，降级为「双方对齐事项」**：Models/TravelQuestModels.swift:71-72 的 doubao_social / openai_web_search 与后端 schemas/travel.py:55-56 **完全一致**——后端本次 DeepSeek 迁移并未改这个「研究 provider」枚举，iOS 保留原值才是正确对齐（改任何一方都会破坏解码）。要改必须前后端同一提交一起改，且后端 orchestration 逻辑（guide_orchestrator.py 引用同值）也要同步。**这不是 faf38e5 的遗漏。**
- Part A 的「2 处手机漏改」裁定：Info.plist:29（相册权限文案「生成手机身份卡」）✅ 属实应改；MockPetJourneyService+Journey.swift:366（明信片 petVoice「我把手机举得低低的」）**裁定保留**——这是宠物「举着通讯器自拍」的物理动作描写，与后端同款文案一致，不是产品形态称呼。可选替代：「把镜头放得低低的」。

## 2. faf38e5 修复验证（复核后）

| 修复项 | 结论 |
|---|---|
| 手机→通讯器主战场（Tab/头部/引导/地图/时间线等） | ✅ 通过（33 处；另 5 处物理设备语境保留正确） |
| 供应商名（GPT/豆包）/ 模型名 gpt-5.5 / 生图提示词 GPT / POI | ✅ 通过 |
| 脱敏正则扩充（DeepSeek/doubao/豆包/抖音/小红书…） | ✅ 通过 |
| .white→surface ×2、消息→通讯、通讯器在线→信号已连接 | ✅ 通过 |
| wire 枚举（Part A 判漏改） | ✅ 本应保留（见 §1 纠正） |
| Info.plist 相册权限文案「手机身份卡」 | ⚠️ 待改（本轮新增） |

## 3. 主发现清单（合并 + 裁定）

### P0（健壮性，建议前端窗口优先）

| # | 问题 | 证据 | 修复方向 |
|---|---|---|---|
| 1 | 离线发件队列**队头阻塞**：一条永久失败（400/超长/违规）的消息卡在队首，每次 drain 先撞它→break，后面所有离线消息被堵死；attempts 累加但无上限、无死信 | Core/Persistence/OutboundMessageQueue.swift:33-46；CachedModels.swift:39-44（sent/failed 死状态） | drain 逐条独立计数，≥5 次标记 failed 并跳过（或死信区），用起 sent/failed 状态 |
| 2 | **401 无刷新/无恢复**：JWT 过期后所有请求稳定 401，被归一成普通 requestFailed，UI 显示后端原始文案，无重新登录信号 | APIClient.swift:90-93；RemotePetJourneyService.swift:319-329；AppSessionStore.swift:106-156 | 401 单列 APIError.unauthorized → 触发一次刷新重放，失败走 signOut；至少映射「连接已失效」信号文案 |
| 3 | **缓存无 TTL**：离线数天冷启动会展示数天前的 worldSnapshot/agentStatus，「TA 还在老地方」伤害核心体验 | JourneyCacheRepository.swift:32-47（store/load 无过期）；JourneyViewModel+Lifecycle.swift:48-61（stale 仅提示信号弱） | CachedPayload 加 TTL（按 kind 差异化：snapshot 30min、status 1h），超龄 load 返回 nil；stale 文案区分「短时离线」与「数据已很旧」 |

### P1（架构回潮 / 契约 / 用户可见）

| # | 问题 | 证据 |
|---|---|---|
| 4 | **9 处常驻动画不响应 reduceMotion、无 1/30 帧率上限**（跑满 60-120fps） | JourneyTelemetry.swift:12,373,401；JourneyLiveSignal.swift:391,420；JourneyMapMarkers.swift:200,245；JourneyMapViewport.swift:528；JourneyMapLoading.swift:22（Part A 列 8 处，抽验实为 9 处） |
| 5 | **MemoryEditor 用户可达表单暴露内部机制**（来源事件 ID/显著度/重要度/情绪值/信心值 + 英文枚举 episodic/owner_note）违反硬规则 2 | Views/MemoryEditor.swift:388-389,426-441；入口 MemoryHub.swift:299 非 DEBUG 门控 |
| 6 | **契约漂移**：8 结构体 20+ 字段 iOS 缺失（LifeTickResult.observation/retrieved_memories、PhotoMission.quality_report/prompt_blocks、PetAuthoredGuide.selected_places/pet_first_person_guide、SouvenirItem.memory_type 等）；coinInflowDate/preferredStartDate 用 String 解后端 date | 详表见 part-b §2（17 行逐字段） |
| 7 | **凭据系统双轨死代码**：fetchCredentialPrompts 无调用、PetCredentialPromptTemplate（约 155 行英文提示词）死代码、PetCredentialKind 与 PetCredentialPromptKind 重复枚举；卡面本地合成，未接服务端 Seedream 生图 | RemotePetJourneyService.swift:273-275；Views/PetCredentialModels.swift:54-181,307-308,633-787；PetCredentialCard.swift:119,164 |
| 8 | **图片尺寸/宽高比硬编码** 1536/1024(3:2)、护照 1448/1086，与 Seedream 默认 1024x1024 不一致 | Views/PetCredentialModels.swift:110-117；PetCredentialCard.swift:143 |
| 9 | **WorldStoryViewModel 绕过网络层**直接 URLSession（无 auth/重试/错误归一） | ViewModels/WorldStoryViewModel.swift:26-31 |
| 10 | **ViewModel 定义在 View 文件**（CommunicatorViewModel/MemoryHubViewModel）+ PetCredentialModels.swift 约 787 行塞满业务逻辑 | Views/CommunicatorViews.swift:32；Views/MemoryHub.swift:14 |
| 11 | **NPC 宠物名三处硬编码**（View + Mock + 后端 npc_society.py，注释自证需两边同步） | Views/JourneyMapModels.swift:263-272 |
| 12 | **分钟数时间计算 4 处 View 重复**（含 dayPlanPhase 判定两处逐行相似） | JourneyMapModels.swift:136；JourneyGuideDigest.swift:234,246；SecondaryViews.swift:178-190；CommunicatorChat.swift:436-437 |

### P2（清理 / 打磨，择机做）

- Info.plist:29「手机身份卡」→「宠物身份卡/通讯器身份卡」（用户可见系统弹窗）。
- 「识别/生成/真实」机制词散布用户文案（PetOnboardingView:246,248、CommunicatorChat:517,607、SecondaryViews 生成类、TravelGuide:365「真实移动」、JourneyDaySchedule:63「沿真实道路」等，全库「真实」36 处）→ 统一仪式化措辞（识别→记住/收好、生成→洗出来/写好、真实→删或换）。
- 地图标注卡裸 UIColor.white（WorldAnimalViews.swift:100,108,248,249,259 等）→ 补 DesignTokens.annotation.cardSurface 令牌。
- 阴影 8 处用 .black 而非 deepInk（JourneyDayRecap:242,390,555,606、CommunicatorChat:260、PetCredentialWallet:455,587、JourneyTimeline:243）。
- 「账号」4th wall 措辞（MapControlDock:84,86、JourneyDayRecap:640）→ 软化。
- WelcomeView:118「灵魂世界」vs 规范「平行世界」术语不一致；:611 免责声明是否保留需产品确认。
- minimumScaleFactor 0.55-0.62 过低（JourneyTimeline:239、PetCredentialCard:314,362）→ ≥0.8 或改多行。
- 厦门行程/城市品牌名多处硬编码重复（JourneyDaySchedule/JourneyMapModels/JourneyGuideDigest 与 Mock 四处）。
- 死代码：collectTravelQuestSouvenirs（非 economy 变体）、SuccessResponse 仅单处用、RemoteDateDecoding 访问级别（APIClient.swift:98-119）。
- 后端小漂移：illustrated_guide.py 的 model 字段在 volcengine 下仍报 gpt-image-2（应取实际 provider model）；Mock 的 model「mock-guide-model」可对齐 deepseek-chat。

## 4. 模型切换（DeepSeek/Seedream）对 iOS 的最终结论

- **文本切换：零破坏**。iOS 无模型名/JSON strict//responses 假设；faf38e5 已验证无任何 .model/.provider 上屏。
- **图片切换：两处真实风险**——① 尺寸/宽高比硬编码（P1-8，凭据卡若接服务端生图会拉伸）；② 后端 IllustratedGuide.model 漂移（iOS 不显示，低危）。其余（revised_prompt、多参考图、签名 URL、token-usage 新字段）安全。
- 附带利好：MediaCache 首次下载后永久缓存，恰好规避了火山签名 URL 过期问题。

## 5. 整改方案（建议顺序与分工）

**Phase 1 — 前端窗口 P0 健壮性（1-2 天，全在 iOS 侧）**
1. Outbox 队头阻塞 + attempts 上限 + 死信；补 poison message 测试。
2. 401 → APIError.unauthorized → 刷新/登出路径 + 「连接已失效」文案；补认证测试。
3. 缓存 TTL（按 kind）+ stale 分级文案；补超龄缓存测试。

**Phase 2 — 前端窗口 P1 架构回潮（2-3 天）**
4. 9 处 TimelineView 统一 reduceMotion + 1/30 上限（硬规则，改动小收益大，可先行）。
5. MemoryEditor 表单 DEBUG 门控或砍内部字段（硬规则 2）。
6. CommunicatorViewModel/MemoryHubViewModel 迁入 ViewModels/（登记 pbxproj）；WorldStoryViewModel 走 APIClient。
7. NPC 名单收敛单一数据源（与后端 npc_society.py 对齐）；分钟数计算抽共享工具。

**Phase 3 — 契约对齐（前后端联合，3-5 天）**
8. 补 iOS 缺失的高价值字段（LifeTickResult.observation/retrieved_memories、PhotoMission.quality_report 优先）；**新建 ContractDecodingTests**（后端 schema 序列化样本 → iOS 解码断言）作为长期护栏；date 字段类型统一。
9. 凭据双轨决策：本地合成则删死代码/合并枚举；接服务端则补调用 + 动态尺寸。
10. 尺寸统一：iOS 依后端 size 字段算宽高比，删硬编码；后端 illustrated_guide.model 取实际 provider。

**Phase 4 — P2 打磨（按产品节奏穿插）**
11. Info.plist 文案、机制词仪式化、annotation.cardSurface、阴影 deepInk、术语统一、minimumScaleFactor、死代码清理。

**测试护栏（贯穿）**：ViewModel 层（尤其 JourneyViewModel 状态机/离线回退/轮询/outbox 联动）与 RemotePetJourneyService（multipart/Bearer/错误归一）、RemoteDateDecoding、契约解码——这些是当前最大缺口，也是 P0/P1 反复出现的根因。

---

## 附：整改落实情况（2026-08-14 更新）

| 项 | 状态 | 提交 |
|---|---|---|
| 后端 illustrated_guide.model 漂移 | ✅ 已修（取实际 provider 模型） | dd5d919 |
| P0-1 Outbox 队头阻塞 | ✅ 已修（attempts 上限 5 + 死信 + 不再 break）+ poison 测试 | 5cd545a |
| P0-2 401 路径 | ✅ 已修（APIError.unauthorized → sessionExpired + 信号文案）+ 测试 | 5cd545a、dcc0807 |
| P0-3 缓存 TTL | ✅ 已修（13 种 kind 分级 TTL）+ 超龄拒绝测试 | 5cd545a |
| P1-2 9 处 reduceMotion | ✅ 已修（1/30 上限 + paused） | 5ffbe02 |
| P1-3 MemoryEditor 内部字段 | ✅ 已修（#if DEBUG 门控） | 0a7adb7 |
| P1-4 契约补齐 | ✅ 已修（7 结构体字段 + 2 处 JSONValue 承载）+ ContractDecodingTests | bfdcb16 |
| P1-5 凭据双轨 | ✅ 已修（删 155 行模板 + 死方法 + 重复枚举） | c56243b |
| P1-6 尺寸硬编码 | ✅ 已修（标准卡/护照尺寸常量集中 + 注释说明服务端接入路径） | bea6ad5 |
| P1-7 WorldStoryViewModel | ✅ 已修（走统一 APIClient） | 2e5e964 |
| P1-8 VM 迁出 View | ✅ 已修（CommunicatorViewModel/MemoryHubViewModel → ViewModels/，pbxproj 登记） | 20877c1 |
| P1-9 NPC 单一数据源 | ✅ 已修（NPCSociety.cast，View/Mock 元数据分离） | b021132 |
| P1-10 分钟数共享 | ✅ 已修（Date.petSoulMinuteOfDay，3 处收敛） | 7181e74 |
| P2 全部（Info.plist/机制词/cardSurface/阴影/账号/术语/minimumScaleFactor/死代码） | ✅ 已修 | 52d5a37、db37c10、bea6ad5 |
| CI 编译修复（RetryPolicy 穷尽 switch） | ✅ 已修 | dcc0807 |

验证状态：后端 82 测试全绿；arch_gate 绿；Architecture Gate CI ✅；iOS Build & Test CI（macOS 真机编译+测试）最终确认见 Actions。

---

## 附：正面确认（审计双方一致）

- 小福/模拟/占位/第一版/正在输入/输入中/在线/已读/好友/联系人/通知栏/接口/数据源/后台/引擎/算法/提示词/系统/版本/升级/数据同步：全库 0 命中。
- 命名 4 个常驻动画（AmbientSignalField/SignalPulseRings/SignalBars/EnergyRing）reduceMotion + 1/30 已正确。
- 写请求不重试、读请求幂等重试；观察者/计时器零泄漏；@MainActor 与 weak 捕获正确；5s 轮询可取消。
- 无医疗/宗教硬性越界；反控制语境文案正确。
- macOS CI（GitHub Actions）当前 main 全绿：Architecture Gate ✅、iOS Build & Test ✅（faf38e5 已验证，f9664db 后端提交不影响 iOS）。
