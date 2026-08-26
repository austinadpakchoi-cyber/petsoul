# UI / UX 评审报告（2026-08-26）

> 评审方：Claude Code（只出结论，不改代码）
> 整改方：DeepSeek
> 基线提交：`30de3ca`（main）；账号流程截图取自 `feature/account-login-receive-pet`
> 配套文档：`audits/2026-08-26-full-project-audit/report.md`（工程侧审计，本报告只谈 UI/UX）

---

## 0. 评审材料与局限

**看过的东西**

| 材料 | 内容 |
|---|---|
| `docs/mac-verification-shots/` 8 张 | 2026-08-26 22:39–23:03 拍摄：登录页、onboarding 照片步、TA 选择空态、已连接态、地图主页、账号页、TA 选择（有宠物）、返回主页 |
| `audits/2026-07-05-.../screenshots/` | 通讯器夜间对话、明信片、朋友圈、行程卡等 11 张 |
| 源码 | `Views/`、`Design/DesignTokens.swift`、后端 `communicator/`、`weather_provider.py`、`schemas/world.py` |

**本次没能评的（需要跑起来才有结论）**

模拟器集成启动失败：`Xcode is installed but not selected`。需在本机执行（需要密码，AI 无法代劳）：

```bash
sudo xcode-select -s /Applications/Xcode.app/Contents/Developer
```

因此以下维度**尚未评审**，不要当作"没问题"：

- 转场与动效节奏（页面切换、卡片展开、`AmbientSignalField` 实际观感）
- 暗色模式下的地图（截图只有浅色态；夜间 wash 的真实效果未验证）
- 手势与触达（sheet 拖拽、地图缩放与卡片的手势冲突）
- 动态字体 / 无障碍放大后的布局
- 加载态与骨架屏的实际时长体感

**本报告的两类结论要分开看**

- 🔍 **已验证事实** —— 有代码位置或截图为证，DeepSeek 可直接执行。
- 💭 **设计判断** —— 我的主观意见，**需要你拍板后 DeepSeek 才动**，不要当成缺陷照改。

---

## 1. 整体判断（💭）

**这个产品最强的是文案，最弱的是地图。而地图是主屏，是 70% 的画布。**

文案的分寸感很难得——「先登录，再接 TA 回家」「还没有 TA 等在这里」「已送达」而不是「已读」——是真的在做关系产品而不是陪聊工具。夜间通讯器那一屏证明暖夜色板完全成立，是全 App 最好看的界面。

但打开 App 第一眼的地图，看起来就是 Apple Maps 的默认样子：冷灰路网、标准蓝水体、大写英文 `HUBIN MIDDLE ROAD`、左下角挂着 `Apple Maps · Legal`。**平行世界的世界观，在最大的那块画布上是缺席的。**

好消息是：地图的三个问题里有两个属于「已经建好了但没生效」，不是重做，是调参和接线。

---

## 2. P0 —— 决定第一眼观感的三件事（地图）

### P0-1　昼夜大气层被调到看不见（🔍 已验证）

**位置**
- `PetJourneyIOS/PetJourneyIOS/Views/JourneyMapViewport.swift:449-476`（`washColors`，四档昼夜色）
- `PetJourneyIOS/PetJourneyIOS/Views/JourneyMapViewport.swift:513`（整层不透明度）

**现状**：昼夜系统建得很完整——dawn / day / dusk / night 四档 wash，夜间还叠 `AmbientSignalField` 星尘（`:497-505`），相位切换有 1.4s 缓动（`:520`）。设计思路是对的。

问题出在最后一步：

```swift
.opacity(phase == .night ? 0.26 : 0.38)   // :513
```

整层再乘 0.26。夜间那组 `nightDeep 0.46 / nightMid 0.30 / nightSoft 0.34` 落到屏幕上实际只剩约 **0.12 / 0.08 / 0.09**，约等于没有。

**证据**：`14-home-doudou.png` 摄于 22:44，按 `:441` 的相位逻辑（`default: .night`）应为夜间，但画面上看不出任何夜的性格，水体仍是 Apple 标准蓝。

**补充**：`:360` 用的是 `.mapStyle(.standard(elevation: .realistic, pointsOfInterest: .excludingAll, showsTraffic: false))`。POI 已排除是对的；但 MapKit 的瓦片颜色无法直接改，**overlay wash 是唯一手段**——所以这层的强度就是地图气质的全部。

**验收标准**
1. 提高 wash 整层不透明度，使夜间地图在截图上可辨认出暖夜性格（建议起步值 0.6–0.75，以真机/模拟器观感为准反复调）。
2. 调整后必须验证：路名、路网、水体仍清晰可读，不能为了氛围牺牲可用性。
3. 四个相位都要过一遍（可临时改系统时间或注入 `date` 验证），dawn/dusk 不能过曝。
4. 保留 `:520` 的相位缓动动画，不要让天色跳变。

---

### P0-2　昼夜跟的是主人的时区，不是 TA 的（🔍 已验证）

**位置**
- `PetJourneyIOS/PetJourneyIOS/Views/JourneyMapViewport.swift:441`

```swift
var phase: DayPhase {
    switch Calendar.current.component(.hour, from: date) {   // ← 设备本地时间
```

**现象**：地图天色跟随**用户设备时区**。TA 在洛杉矶而主人在国内时，地图显示的是主人这边的天色。

**为什么这条重要**：这个产品的整个前提是「TA 在别处生活」。天色跟着主人走，等于每天都在提醒用户「这只是我手机里的一层皮」，直接消解世界观。它比 P0-1 更伤——P0-1 是不好看，这条是不成立。

**关键：不需要改契约，数据已经在流了**

| 层 | 现状 |
|---|---|
| 后端 | `PetJourneyBackend/app/schemas/world.py:71` —— `WorldObservation.local_time: datetime` 已下发 |
| iOS 模型 | `PetJourneyIOS/PetJourneyIOS/Models/WorldSimulationModels.swift:190,200` —— `localTime` 已建模且 `CodingKeys` 已映射 |
| iOS 消费 | ❌ 未接到相位计算上 |

**验收标准**
1. `DayPhase` 改用世界快照的 `localTime`（TA 所在地当地时间）而非 `Calendar.current`。
2. `localTime` 尚未加载/为空时，回退到设备时间，不得崩溃或黑屏。
3. TA 跨时区移动后，天色应随之改变——补一条单测：给定同一 UTC 时刻、不同 `localTime`，`phase` 输出不同。
4. 检查是否还有别处用 `Calendar.current` 表达「TA 那边的时间」（本次只核了地图相位一处，`Date.petSoulMinuteOfDay` 等共享工具需一并排查）。

---

### P0-3　TA 是全屏最不显眼的元素（💭 设计判断）

**位置**：`14-home-doudou.png`；标记实现见 `Views/JourneyMapMarkers.swift`

**现象**：宠物标记是一个小灰圆 + 月亮 zzz 图标，视觉重量比路网还轻。而右上角一列四个地图控件（`···` / 定位 / 3D / 隐藏）反倒是全屏最抢眼的 chrome。

情感产品里「TA」应该是构图的锚点。现在的层级是反的：系统控件 > 路网 > TA。

**另外三处拥挤（同屏）**
- 底部三层浮层叠罗汉：世界杯卡片 +（半收起的）状态 sheet + tab bar。
- sheet 内文字被截断：`Doudou 找到一处安静地方…`。
- 左下角 `Apple Maps` / `Legal` 归属文字与 tab bar 挤在一起（这是 Apple 强制要求，不能删，但可以调整周边留白避让）。

**建议方向（需你拍板）**
1. 放大宠物标记，给一层呼吸感光晕——`AmbientSignalField` 已有现成实现，可复用，注意仍需遵守 `reduceMotion`。
2. 右上控件列砍到 1–2 个，其余收进 `···`。
3. 底部同时最多出现两层浮层；状态 sheet 的标题不允许截断（用 `lineLimit(2)` 或缩短后端文案）。

---

## 3. P1 —— 通讯器的人称与冗余

### P1-1　一句话说三遍（🔍 已验证）

**证据**：`audits/2026-07-05-.../screenshots/04-chat-duplicate-look-now.jpg`

主人问一句「看看你现在」，得到三块堆叠回应：

1. 气泡：「现在信号一会儿有一会儿没有，落地后会看到。」
2. 卡片「晚点拍给你」：**同一句话，一字不差**
3. 卡片「TA 此刻的位置」

**成因**

| 位置 | 说明 |
|---|---|
| `PetJourneyBackend/app/communicator/attachment_planner.py:109` | `text=policy.visible_status` —— 卡片正文与气泡正文**同源** |
| `PetJourneyBackend/app/communicator/attachment_planner.py:67-68` | 另一支「刚刚才拍过」也是近义重复 |
| `PetJourneyIOS/PetJourneyIOS/Views/CommunicatorChat.swift:299` | `attachments.filter { $0.type != .text }` —— 只挡了 `.text` 类型 |
| `PetJourneyIOS/PetJourneyIOS/Models/CommunicatorModels.swift:24-34` | `photo_status_card` 是独立类型，不在过滤范围内，照常渲染 |

**为什么重要**：TA 说话变成了走工单流程——先口头答复、再发状态卡、再附位置卡。这**恰恰是 AGENTS.md 明确要避免的「客服感」**，与「TA 有自己的生活、用户温柔地参与」相悖。

**验收标准**
1. 气泡与 `photo_status_card` 二选一：同一轮回应中，若卡片承载了该信息，气泡不再重复；反之亦然。
2. 判重不能靠字符串相等（`:67-68` 那支是近义改写而非全等），应在 `attachment_planner` 决策时就决定"这轮用气泡还是用卡"。
3. 补后端测试：同一 intent + cooldown 状态下，断言回应中不出现语义重复的两块。
4. 单轮回应的块数设上限（建议 ≤2），避免堆叠。

### P1-2　天气播报破坏人称（🔍 已验证）

**现象**（同截图）：

> 洛杉矶 · 洛杉矶国际机场。多云，27°C，西南风 4 级，湿度 88%

两个问题：
1. 城市名重复了一次（「洛杉矶 · 洛杉矶国际机场」）。
2. **宠物不会说「湿度 88%」。** 这是气象 API 串直接贴进了对话框。

**成因**：`PetJourneyBackend/app/weather_provider.py:97-105`（`f"{temperature}°C"` / `f"风力{wind_power}级"` / `f"湿度{humidity}%"` 拼接），另见 `:205`、`:225`。

**这条比「客服感」更伤**：客服至少是拟人的，气象串连拟人都不是。

**验收标准**
1. 结构化气象数据保留给地图/状态区展示，**不进对话气泡**。
2. 对话里只留 TA 能感知的部分，用第一人称转译（例：「这边风有点大，毛都吹乱了」）。转译不得暴露机制（硬规则 2），也不要报数值。
3. 修掉「城市 · 城市机场」的重名拼接。
4. 检查 `weather_provider` 的其他消费方是否也有同类直贴。

---

## 4. P2 —— 信息架构与构图

### P2-1　六大模块塞进三个 tab（💭 设计判断）

**现状**：`Views/CommunicatorViews.swift:11-25` 只有三个 tab —— 地图 / 通讯器 / 回忆。

AGENTS.md 定义的六大模块中，**朋友圈（旅途圈）、明信片、证件卡包**都埋在二级页面。而明信片被定义为「正式、私密、收藏级纪念」，卡包是整个世界的身份系统——这两个是情感重头戏。

**我的意见**：**不建议加到五个 tab**，那会稀释「TA 有自己的生活」的专注感。更像样的做法是把「回忆」tab 提升为「TA 确实生活过的证据」聚合页，让明信片与卡包在其中有正经的入口和陈列，而不是当作抽屉。

**这条改动面大、涉及导航重构，需你先拍板方向，DeepSeek 再动。**

### P2-2　留白读起来像"没做完"（💭 设计判断）

**证据**：`10-login-page.png`、`12-pet-picker-empty.png`、`15-account-sheet.png`

三张都是同一个毛病：内容压在屏幕上 40%，下面大片空白。尤其 `12-pet-picker-empty`——标题贴顶、图标居中偏上、CTA 贴底，中间断开一大块。

情感产品的留白应该读作「呼吸」，现在读作「还没加载完」。

**建议方向**：内容整体向视觉中心收拢；或让空白**有内容**——一点世界的动静、一句 TA 那边的天气/时间（正好复用 P0-2 接上的 `localTime`）。

### P2-3　onboarding 照片步的三个小问题（🔍 截图可证）

**证据**：`11-onboarding-photo.png`

1. **两个 CTA 打架**：整张卡片写着「点这里选择一张照片」，卡片内又放了「上传 TA 的照片」按钮，同一个动作两个入口。
2. **状态指示长得像可勾选**：底部三个圆圈（轮廓 / 表情 / 记忆锚点）视觉上是 checkbox，实际是完成度指示，用户会去点。
3. **禁用态是全屏最重的元素**：主 CTA「开始记住这张脸」未激活时仍是大块深色，视觉重量压过了真正该点的上传区。

**验收标准**：三处各自收敛——卡片与按钮二选一；状态指示改用非可点击的视觉语言（如进度点/对勾）；禁用态降低视觉重量。

---

## 5. 做得好的（不要动）

| 项 | 说明 |
|---|---|
| 文案分寸 | 「先登录，再接 TA 回家」「还没有 TA 等在这里」「已送达」而非「已读」——关系产品的语感立住了 |
| 信号母题 | `((•))` 图标、「信号不稳定」、「已送达 TA 的世界」贯彻一致 |
| 夜间通讯器 | 全 App 最好看的一屏，暖夜色板完全成立，是地图应该对齐的标杆 |
| 「TA」的用法 | 克制且全局一致，没有滑向拟人过度 |
| 昼夜系统的架子 | 四档相位 + 缓动 + 星尘，设计思路正确（只是强度和时间源要修，见 P0-1/P0-2） |
| 快捷回复 chips | 「看看你现在／给我拍一张／你在哪呀／今天开心吗」——降低了开口成本，符合「温柔地参与」 |
| 登录页调试入口 | `Views/SignInView.swift:135-162` 有 `#if DEBUG` 包裹，「mock 登录 / PETJOURNEY_BASE_URL」不会漏进 Release。**已核实，不是问题** |

---

## 6. 建议整改顺序

**如果只动三件事**：P0-1（wash 调到能看见）→ P0-2（昼夜改用 TA 的时间）→ P1-1（通讯器去重）。

前两件都是几行代码，但直接决定这个 App 打开第一眼是「平行世界」还是「地图 SDK demo」。

| 批次 | 内容 | 性质 |
|---|---|---|
| 第一批 | P0-1、P0-2 | 🔍 已验证，可直接做，改动小收益大 |
| 第二批 | P1-1、P1-2 | 🔍 已验证，涉及前后端配合 |
| 第三批 | P2-3 | 🔍 已验证，纯 UI 打磨 |
| 待拍板 | P0-3、P2-1、P2-2 | 💭 设计判断，**等用户确认方向再动** |

每批改完按 AGENTS.md 跑：

```bash
cd PetJourneyIOS && xcodebuild -project PetJourneyIOS.xcodeproj -scheme PetJourneyIOS -destination 'platform=iOS Simulator,name=iPhone 17 Pro' test
```

```bash
cd PetJourneyBackend && .venv/bin/python -m unittest discover -s tests
```

**另**：P0-1 是观感调参，必须以真机/模拟器实际观感为准反复试，不能只看代码通过。建议改完补一组四相位截图存进本目录。

---

## 7. 遗留：需要模拟器才能补的评审

跑完 `sudo xcode-select -s /Applications/Xcode.app/Contents/Developer` 后可补齐第 0 节列出的五项（动效节奏、暗色地图、手势冲突、动态字体、加载体感）。本报告的结论不覆盖这些维度。
