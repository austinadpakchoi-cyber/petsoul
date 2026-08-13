# PetSoul iOS 前端内容审查报告

- 范围：`PetJourneyIOS/PetJourneyIOS/` 全部 96 个 Swift 文件（Views/ViewModels/Models/Services/Core/Design）。
- 性质：只读审查，未修改任何代码，未提交。
- 依据：`AGENTS.md` 四条硬规则 + 产品语音约定 + 「后端即将切换 DeepSeek + 国内生图」这一变更假设。

---

## 执行摘要

iOS 前端整体已把设计系统收敛得相当干净：`小福` 全库 0 命中，`模拟`/`占位`/`第一版`/`正在输入`/`输入中` 均 0 命中，所有 `provider`/`model` 字符串（如 `mock-ios-travel-quest`、`mock-agent`）都集中在 Mock 服务与 Model 层，没有直接渲染进 UI。设计令牌（`DesignTokens.surface/surfaceStroke/deepInk/paper/welcome.*/notebook.*/mapWash.*/credential.*/annotation.*`）已建立，未发现 `Color(red:)/UIColor(red:)` 之类的散落 RGB 构造。

但存在两类显著问题：

1. **产品语音漂移（最严重）**：全库有 38 处 `手机`，其中约 30 处把「通讯器」这一产品形态直接叫成「手机」（Tab 标题、头部标题、按钮、引导文案等），正面违反硬规则第 4 条「Tab 命名『通讯器』，不叫『手机』」。这是本次审查的第一大发现。
2. **模型/供应商名残留（切换风险）**：`providerName`、`model`、`TravelGuideResearchProvider` 枚举里硬编码了 `GPT`、`gpt-5.5`、`豆包`、`doubao_social`、`openai_web_search`；另有 1 处生成提示词写死 `PetSoul/GPT generated content`。这些在切换到 DeepSeek + 国内生图后会变成错误/暴露机制。

统计：**P0 × 4，P1 × 5，P2 × 5**。

---

## P0（违反硬规则 / 模型切换后必然出错）

### P0-1 「手机」作为产品/通讯器名称 —— 违反硬规则第 4 条

产品语音要求「信号/通讯器」语言，`AGENTS.md` 明文「Tab 命名『通讯器』，不叫『手机』」。但通讯器模块及其周边引导大量使用「手机」：

| 位置 | 现状 |
| --- | --- |
| `Views/CommunicatorViews.swift:335` | `.navigationTitle("手机")` —— Tab 标题直接叫「手机」 |
| `Views/CommunicatorViews.swift:367` | `Text("\(viewModel.petName) 的手机")` |
| `Views/CommunicatorViews.swift:57` | `"手机正在接收信号"`（同文件 :67 却用「通讯器在线」，前后不一致） |
| `Views/CommunicatorViews.swift:127` | `toastMessage = "手机信号有点弱，稍后再试。"` |
| `Views/ConnectingView.swift:26` | `"手机已经收到第一段回声"` |
| `Views/ConnectingView.swift:68` | `Label("打开手机", ...)` |
| `Views/PetOnboardingView.swift:88-89` | `"先让手机看见 TA" / "手机会把这张脸作为寻找 TA 的第一个锚点"` |
| `Views/PetOnboardingView.swift:201,265` | `"你最想让手机记住的一句话" / "手机已经知道 TA 会怎么叫你"` |
| `Views/WelcomeView.swift:573` | `"手机正在寻找。"` |
| `Views/DNASettings.swift:120` | `"手机还没有读到 TA 的完整偏好。"` |
| `Views/SecondaryViews.swift:75`、`Views/JourneyMapView.swift:486`、`Views/JourneyLiveSignal.swift:453,524`、`Views/JourneyGuideDigest.swift:432`、`Views/MemoryEditor.swift:525,549` 等 | 同类「手机」隐喻 |

- **为什么是 P0**：这是用户可见文案对硬规则第 4 条的直接违反；「手机」把产品拉回即时通讯/设备范式，破坏「通讯器 + 信号」的仪式感母题。
- **建议修复**：把作为产品形态的「手机」统一替换为「通讯器」（或按语境用「信号」/「TA 的世界」）。注意区分少数合法的物理设备语境（如 `JourneyDayRecap.swift:639-640` 的「换手机/重装 App」）应保留；其余约 30 处需改。

### P0-2 用户可见的供应商名硬编码 —— 违反硬规则第 2 条 + 切换后出错

- **`Services/MockPetJourneyService+Guide.swift:240`**
  `providerName: isWorldCup ? "GPT Web Search + 地图资料" : "豆包社媒线索 + 地图资料"`
  这是 `TravelGuideResearch.providerName`（`Models/TravelQuestModels.swift:240`，编码键 `provider_name`），字段语义即「给用户看的来源名」。目前 Views 里没有直接引用 `providerName`（grep 0 命中），但该字符串一旦被渲染或经后端回传，就会把 `GPT` / `豆包` 暴露给用户，且切换 DeepSeek 后立即错误。
- **建议修复**：删掉具体供应商名，改为仪式感/无机制的描述（如「沿途线索 + 地图资料」「本地与赛事资料」），并在 Model 层把 `providerName` 定位为「内部来源标签」，禁止进入 UI。

### P0-3 模型名硬编码

- **`Services/MockPetJourneyService+Guide.swift:34`** `model: "gpt-5.5"`
  硬编码模型名。切换 DeepSeek 后该字段变成错误假设。虽然当前不渲染，但它是「模型名散落」的代表，需要随切换清理。

### P0-4 供应商枚举硬编码在 Model 契约里

- **`Models/TravelQuestModels.swift:69-74`**
  `enum TravelGuideResearchProvider { case doubaoSocial = "doubao_social"; case openAIWebSearch = "openai_web_search"; case hybrid }`
  这些 raw value 是走 wire 的协议值，后端切 DeepSeek + 国内生图后，`doubao_social`/`openai_web_search` 会失效或含义变化。
- **建议修复**：与后端对齐新枚举值（如 `deepseek`、国内生图 provider），并确认 `hybrid` 的语义仍成立。

---

## P1（用户可见的打磨/仪式感问题）

### P1-1 原生 `.white` 当作表面/背景 —— 违反设计系统第 3 条（深色模式发白）

- **`Views/JourneyChapter.swift:157`**
  `.background(activeMode == mode ? .white.opacity(0.84) : .white.opacity(0.42))` —— 分段选择器底色用 `.white`，深色模式下会变刺眼白底。同文件 :126 的 `ChapterActionButton` 用的是 `DesignTokens.surface.opacity(0.72)`，二者不一致。
- **`Views/PetOnboardingView.swift:408`**
  `.background(photoData == nil ? .white.opacity(0.86) : DesignTokens.ink.opacity(0.68))` —— 「上传照片」胶囊底用 `.white.opacity(0.86)`。
- **建议修复**：改用 `DesignTokens.surface` / `surfaceStroke`（或 `mist` 等语义令牌）。

### P1-2 通讯器仍保留「消息/在线」等即时通讯措辞

- **`Views/CommunicatorViews.swift:301`** `title: "消息"`；**:385** `CommunicatorSignalChip(title: "消息", ...)`；**`Views/CommunicatorChat.swift:265`** `"还没有消息"`；**:67** `"通讯器在线"`。
- 硬规则第 4 条要求「信号语言」，不用即时通讯范式。「消息」「在线」偏 IM 味，与「通讯记录/生活信号」的既有措辞（:303 「条通讯记录」、:326 「最近的生活信号」）混杂。
- **建议修复**：统一为「通讯记录/来信/信号」等措辞，弱化「消息/在线」。

### P1-3 View 文件内硬编码具体宠物名（疑似违反硬规则第 1 条精神）

- **`Views/WorldLifeEvent.swift:31-54`** `static let samples` 内含 `petName: "Luna"/"年年"/"豆豆"/"Coco"` 等；**:253-254** `static let petNames = ["Momo","Luna","年年","小宝","团团","Sugar","豆豆","Nori","米粒","Coco","橘子","Lucky"]`；**:409** 用种子随机取名为世界事件里的「其他灵魂」命名。
- **`ViewModels/WorldStoryViewModel.swift:10`** `remoteEvents.isEmpty ? WorldLifeEvent.samples : remoteEvents` —— 这些样板宠物名在**生产环境作为空数据兜底**进入地图。
- **为什么是 P1**：这些不是「当前宠物」，属于世界氛围内容，故未判 P0；但具体宠物名硬编码在 Views/ 里、且作为生产兜底，踩在硬规则第 1 条边线上。
- **建议修复**：把样板事件/名字迁入 Mock 服务或 `SampleContent`，UI 层只消费「已生成事件」，避免把写死的名字当兜底。

### P1-4 生成提示词内残留「GPT」（切换后过期）

- **`Views/PetCredentialModels.swift:655`**
  `...are fictional PetSoul/GPT generated content for a soul that reappeared...`
  这是证件卡生图提示词（内部、英文、不直接显示给用户），但写死 `GPT`，切换 DeepSeek 后措辞过时。
- **建议修复**：改为中性表述（如 `...fictional PetSoul-generated content...`）。

### P1-5 用户文案脱敏正则未覆盖新供应商（模型切换风险）

- **`Views/JourneyTimeline.swift:518-523`** `petSoulUserFacingText` 用正则把「来源/供应商名」从后端文本中剥掉，白名单为
  `(?:amap|google|mock|hybrid|openai|web|map|provider|service|engine|client|route|planner|mission)`（:522）。
- **问题**：该正则区分大小写、且只覆盖旧供应商。切换 DeepSeek + 国内生图后，`DeepSeek`/`deepseek`/`doubao`/`豆包`/`GPT`（大写）/`抖音`/`小红书`/`文心`/`通义` 等**不会被剥掉**，存在供应商名从后端文本漏给用户的隐患。
- **建议修复**：更新该白名单（大小写不敏感，加入 `deepseek|doubao|gpt|豆包|抖音|小红书|文心|通义|智谱` 等），并在后端文本清洗之外保留这一前端兜底。

---

## P2（代码卫生 / 非用户可见）

### P2-1 散落 hex 字面量（未收敛到 DesignTokens）

- **`Views/WorldLifeEvent.swift`** 约 50 处 `tintHex: 0x...`（:42-210 事件样本、:434-490 故事条目），另有 :541-545 为哈希常量（非颜色，可忽略）。
- **`Views/WelcomeView.swift:576`** `tintHex: 0xD6AA63`；**`ViewModels/WorldStoryViewModel.swift:44`** `tintHex: 0xD6AA63`。
- 其中 `0xE0A25E` 与 `DesignTokens.welcome.signalWarmth` 重复、`0xC8956D` 与 `welcome.fallbackTint` 重复，`0xD6AA63` 在 Welcome/WorldStory 两处重复。设计系统第 3 条要求 hex 不散落。
- **建议修复**：为「世界生活事件」建语义色组（如 `worldEvent.*`）或复用 `welcome.*`，把 `tintHex` 改为令牌引用。

### P2-2 地图标注卡片用 `UIColor.white` 做背景

- **`Views/WorldAnimalViews.swift:100,108,259`** `container.contentView.backgroundColor = UIColor.white.withAlphaComponent(0.40/0.44)`；**:247-249** 选中态 `0.58/0.36`。
- `DesignTokens.annotation` 已有 `titleInk/subtitleInk/shadowBrown`，但缺「卡片底色」令牌，于是退回裸 `UIColor.white`。深色地图氛围下白色半透明卡片会偏冷。
- **建议修复**：在 `annotation` 下补 `cardSurface` 令牌（自适应或暖色），替换裸白。

### P2-3 手账贴纸底色 `Color.white`（边缘情况）

- **`Views/IllustratedGuidePreview.swift:294`** `.background(Color.white.opacity(0.62))` —— 纸面手账上的「贴纸」底色。属于「实物材质」的灰色地带，可判 OK；若严格按规则，宜改用 `DesignTokens.notebook.paper` 或 `paperShade`。:54/:313 的白是渐变高光（镜面反光），合规。

### P2-4 生图尺寸/宽高比假设

- **`Services/MockPetJourneyService+Journey.swift:383,394`** `size: "1536x1024"`（明信片横图 3:2）。
- **`Views/PetCredentialModels.swift:115`** `1536.0 / 1024.0`（证件卡宽高比）；**`Views/PetCredentialCard.swift:279`** `.aspectRatio(3.0/4.0)`（竖卡）。
- 切换国内生图后，输出尺寸/宽高比可能与这些固定值不一致，导致拉伸或裁切异常。
- **建议修复**：宽高比改由后端返回的 `width/height` 驱动，客户端不写死。

### P2-5 用户可见文案里的技术词「POI」

- **`Services/MockPetJourneyService+Guide.swift:246`** findings 含 `"先看榜单、游记和真实 POI"`，经 `TravelViews.swift:500` `finding.petSoulUserFacingText` 渲染给用户（该函数不剥 `POI`）。
- **建议修复**：把「真实 POI」改为「真实地点」等无机制措辞。

---

## 与后端模型切换相关的风险清单

| # | 风险 | 位置 | 影响 | 等级 |
| --- | --- | --- | --- | --- |
| 1 | 供应商名 `GPT`/`豆包` 硬编码在 `providerName` | `Services/MockPetJourneyService+Guide.swift:240` | 一旦渲染/回传即暴露，切换后错误 | P0 |
| 2 | 模型名 `gpt-5.5` 硬编码 | `Services/MockPetJourneyService+Guide.swift:34` | 切换后字段错误 | P0 |
| 3 | 供应商枚举 `doubao_social`/`openai_web_search` | `Models/TravelQuestModels.swift:69-74` | wire 契约与后端脱节 | P0 |
| 4 | 生成提示词写死 `GPT generated content` | `Views/PetCredentialModels.swift:655` | 生图提示措辞过期 | P1 |
| 5 | 前端脱敏正则白名单不含新供应商 | `Views/JourneyTimeline.swift:519-522` | 供应商名可能漏给用户 | P1 |
| 6 | 生图尺寸/宽高比固定值 | `MockPetJourneyService+Journey.swift:383,394`、`PetCredentialModels.swift:115`、`PetCredentialCard.swift:279` | 新生成图尺寸不匹配 | P2 |
| 7 | 大量 `mock-*` provider/source 字符串 | 各 `MockPetJourneyService+*` | 仅 Mock 环境，切换后需保持与后端字段对齐 | 提示 |

---

## 附：正面确认（无问题项）

- `小福`：全库 0 命中（Mock 服务也已不再使用该名）。
- `模拟`、`占位`、`第一版`、`正在输入`、`输入中`：0 命中。
- `openai`/`doubao`/`gpt` 仅出现在：Mock 数据、Model 枚举、脱敏正则、1 处生图提示词——没有直接进入任何 `Text()`。
- 所有 `provider`/`model` 字段都在 Model/Services 层，Views 未渲染。
- `JourneyTimeline.swift:499-537` 的 `petSoulUserFacingText` 是已有的一套「把内部机制文案替换成仪式感文案 + 正则脱敏」防御层，方向正确（需按 P1-5 扩充）。
- 语义令牌体系（`surface/surfaceStroke/deepInk/paper/...`）已建立并广泛使用。

---

*审查方式：对 96 个 Swift 文件做 `小福/mock/provider/openai/doubao/gpt/占位/模拟/第一版/.white/Color.white/正在输入/输入中/hex 字面量/模型名/供应商名/宠物名/即时通讯隐喻` 等 token 的 grep，并对命中处逐条读上下文定级。*
