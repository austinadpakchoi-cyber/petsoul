# 全项目审计报告（2026-08-26）

> 审计方：Claude Code（只出结论，不改代码）
> 整改方：DeepSeek
> 基线提交：`30de3ca`（本地与 `origin/main` 0/0 同步，工作区干净）

本报告全部结论**来自实际执行**，不是静态阅读推断。每条问题都给出「位置 / 现象 / 触发场景 / 验收标准」，可直接照做。

---

## 0. 实测基线（本次跑过的命令与结果）

| 命令 | 结果 |
|---|---|
| `python3 scripts/arch_gate.py` | ✅ 通过。iOS 最大 `JourneyMapView.swift` 729 行；后端最大 `illustrated_guide.py` 685 行 |
| `.venv/bin/python -m unittest discover -s tests` | ✅ 82 项全绿（6.6s） |
| `xcodebuild ... -destination 'iPhone 17 Pro' test` | ✅ exit 0，**35 用例全绿，0 编译警告** |

环境：Xcode 26.2 (17C52)、backend venv Python 3.12.9。

---

## 1. 已验证通过的项（**不要动**）

这些是上一轮整改的成果，本次逐条实测确认有效，DeepSeek 不需要碰：

| 项 | 实测结论 |
|---|---|
| 硬规则 1（不写死宠物） | 「小福」全仓库仅剩 `MockPetJourneyServiceTests.swift` 一处 ✅ |
| 硬规则 3（pbxproj 登记） | 磁盘 105 个 Swift 文件**全部**已登记，无幽灵引用 ✅ |
| 硬规则 4（通讯器命名） | 「手机」仅剩 5 处，4 处为用户物理设备语境（合理豁免） |
| reduceMotion | 11 处 `TimelineView` 均为 `.animation(minimumInterval: 1/30, paused: reduceMotion)` ✅ |
| 契约红线枚举 | `doubao_social` / `openai_web_search` 前后端逐字一致 ✅ |
| NPC 身份收敛 | iOS `NPCSociety.cast` 与 `app/communicator/npc_society.py` 的 6 个身份 id/name/species **逐字段一致** ✅ |
| 缓存 TTL 分级 | `JourneyCacheRepository.ttl(for:)` 是**穷举 switch 无 default**，新增 `PayloadKind` 会编译报错。13 kind / 4 档，设计正确 ✅ |
| 经济系统幂等 | `clientRequestID` 在 ViewModel 层生成（`JourneyViewModel+Souvenirs.swift:28,49`），APIClient 重试复用同一个 `URLRequest`，幂等未被重试破坏；叠加 `expected_item_version` 乐观锁双保险 ✅ |
| 密钥卫生 | `secrets/`、`.env`、`deploy/backend.env` 均已 gitignore，git 跟踪文件中零泄漏 ✅ |

### 1.1 契约映射层专项扫描结论（**重要：不要大改**）

我写脚本对 **后端 98 个 Pydantic 模型 × iOS 101 个 Codable 结构**（同名配对 80 对）做了字段级比对：

- **风险：iOS 属性未进 `CodingKeys`** → 命中 9 处，逐个核对后**全部是计算属性**（如 `var effectiveStatus: ItemStatus { status ?? .owned }`）。**真实缺失 0 处。**
- **风险：无 `CodingKeys` 但属性是 camelCase** → **0 处**。
- **风险：后端 `Optional`/可下发 null，iOS 声明为必选（会抛解码错）** → **0 处**。
  - 脚本初筛出 91 处「后端有默认值 / iOS 必选」，但已确认后端**完全没有使用** `exclude_none` / `exclude_unset` / `response_model_exclude`（grep 全仓库无命中），所以有默认值的字段一定会序列化下发，**这 91 处均为误报，不要改成 Optional**。

**结论：手写的 87 个 `CodingKeys` 映射层是干净的。** 上一轮契约整改质量可靠。唯一真实缺口见 §3.3。

---

## 2. P0 —— 必须先修

### P0-1　Release 构建会跑 Mock + localhost（TestFlight 硬阻断）

**位置**
- `PetJourneyIOS/PetJourneyIOS/App/AppSessionStore.swift:73`
- `PetJourneyIOS/PetJourneyIOS/App/AppSessionStore.swift:189-196`（`defaultServiceMode`）
- `PetJourneyIOS/PetJourneyIOS/App/AppSessionStore.swift:198-205`（`defaultBaseURLString`）

**现象**

```swift
private static let debugBackendBaseURLString = "https://api.petsoul.games"   // :73

private static func defaultServiceMode(for userDefaults: UserDefaults) -> ServiceMode {
    #if DEBUG
    if userDefaults === UserDefaults.standard { return .remote }
    #endif
    return .mock                        // ← Release 默认走 Mock
}

private static func defaultBaseURLString(for userDefaults: UserDefaults) -> String {
    #if DEBUG
    if userDefaults === UserDefaults.standard { return debugBackendBaseURLString }
    #endif
    return "http://127.0.0.1:8000"      // ← Release 默认指向手机自己
}
```

生产地址 `https://api.petsoul.games` 在全仓库**只出现这一次**，且被 `#if DEBUG` 编译掉。已确认无任何 xcconfig / Info.plist / 其他代码路径兜底。

**触发场景**

打 Release 包（TestFlight / App Store）→ 首次启动 `serviceMode` 落到 `.mock` → **每个测试员看到的都是样板宠物「小福」的假数据**，不是自己的宠物；即便手动切到 remote，端点是 `http://127.0.0.1:8000`（指向手机本机，且明文 http 会被 ATS 拦截）。

TestFlight 计划 Phase 0-5 已合入 main，但这个包发出去是不可用的。

**验收标准**
1. Release 构建下 `defaultServiceMode` 返回 `.remote`。
2. Release 构建下 `defaultBaseURLString` 返回 `https://api.petsoul.games`。
3. Mock 模式保留为**开发者手动可切**（DEBUG 下的调试入口不变），但不再是 Release 的默认值。
4. 保留 `legacyBaseURLStrings` 存量迁移逻辑（`:74-78`）——它是对的，别删。

---

### P0-2　离线发件队列：静默丢消息 + 向主人谎报「已送达」

**位置**
- `PetJourneyIOS/PetJourneyIOS/Core/Persistence/OutboundMessageQueue.swift`
- `PetJourneyIOS/PetJourneyIOS/ViewModels/JourneyViewModel+Lifecycle.swift:111-122`
- `PetJourneyIOS/PetJourneyIOS/Core/Persistence/CachedModels.swift:39-44`

这是上一轮修「队头阻塞」时引入的三个连带缺陷。**这是本报告最严重的一项**：产品的情感契约是"主人的话会送达 TA 的世界"，而当前实现会在丢话的同时告诉主人已送达。

#### (a) `.sending` 是终态黑洞，中断即永久丢失

`drain()` 在 `:38` 把消息置为 `.sending` 并存盘，然后 `await send(...)`。

`queuedMessages()`（`:74-81`）的谓词是 `stateRaw == queued`，**只捞 `.queued`**。

全仓库 grep 确认：`OutboundMessageState.sending` **只在 `:38` 被写入，没有任何地方读取或重置它**，也没有启动时的恢复逻辑。

> **触发场景**：主人在弱网下发了一句话 → 进入 `drain` → 置 `.sending` → `await send` 期间用户切后台/系统回收进程/崩溃 → 这条消息永远停在 `.sending`：不会被重试、不计入 `pendingCount`、`drainOutboxIfNeeded` 的 `guard pendingCount > 0` 连进都不会进。**这句话彻底消失，主人毫不知情。**
>
> 注意这正是发件队列存在的场景——网络差 → 请求久 → 用户更容易切后台。

#### (b) `.failed` 死信是只写不读的黑洞

`:47` 把超过 5 次的消息置为 `.failed`。grep 确认全仓库**没有任何一处读取 `OutboundMessageState.failed`**（其他 `.failed` 命中均属 `generatedGuide.status` / `loadState` 等无关枚举）。

死信既不重试、不展示、不清理（除非 `purgeAll`），且因为不在 `.queued` 里，`pendingCount` 也不计。

#### (c) 成功提示会说谎（由项目自己的测试佐证）

`JourneyViewModel+Lifecycle.swift:111-122`：

```swift
guard outbox.pendingCount > 0 else { return }
await outbox.drain { ... }
if outbox.pendingCount == 0 {
    toastMessage = "刚才没送出去的话，已经送达 TA 的世界。"
}
```

`pendingCount` 只数 `.queued`。消息进死信或卡在 `.sending` 后，`pendingCount` 同样归零 → **一条都没送出去，App 却弹出「已经送达 TA 的世界」。**

项目现有测试 `PersistenceTests.swift:110-123` `testPoisonMessageIsMarkedFailedAndSkipsOthers` 恰好断言了 `XCTAssertEqual(queue.pendingCount, 0)`——即**测试绿灯的同时固化了这个谎报行为**。

**验收标准**
1. 启动（或 `OutboundMessageQueue.init`）时，把残留的 `.sending` 一律复位为 `.queued`，使其重回补发队列。
2. 死信必须有出口：至少让 `.failed` 对上层可见（例如新增 `failedCount`），UI 用信号语言告知主人「这句话没能送出去」，并提供重试或留存路径。**不允许静默消失。**
3. `drainOutboxIfNeeded` 的成功文案，判据从「`pendingCount == 0`」改为「**本轮确有消息成功送达且无失败**」。全部失败时不得出现「已送达」字样。
4. 修改 `testPoisonMessageIsMarkedFailedAndSkipsOthers` 的断言，使其反映死信可见性；**新增**一条覆盖「`.sending` 中断后能恢复重试」的测试。
5. 文案遵守 AGENTS.md 的信号母题，不要用即时通讯范式。

---

### P0-3　CI 完全不跑后端测试

**位置**：`.github/workflows/`（只有 `arch-gate.yml`、`ios-build.yml` 两个）

**现象**：grep 确认**没有任何 workflow 执行 `unittest` 或 `pytest`**。那 82 个后端测试只靠人肉在本地跑。`arch-gate.yml` 只跑 `scripts/arch_gate.py`。

**触发场景**：后端改坏 → push → CI 全绿 → 问题直到部署或手工跑测试才暴露。AGENTS.md 与交接文档都写了「后端改动后必须全绿」，但这只是约定，没有任何机器强制。

**验收标准**
1. 新增（或在 `arch-gate.yml` 里加 job）：`ubuntu-latest` + Python 3.12 + `pip install -r PetJourneyBackend/requirements.txt` + `python -m unittest discover -s tests`（工作目录 `PetJourneyBackend`）。
2. 触发条件与现有 workflow 对齐：`pull_request` + `push: branches: [main]`。
3. 测试失败必须让 CI 红。

---

## 3. P1 —— 应该修

### P1-1　契约护栏只覆盖 5 / 124 个模型

**位置**：`PetJourneyIOS/PetJourneyIOSTests/ContractDecodingTests.swift`（178 行）

**现象**：fixture 实际断言的只有 `LifeTickResult`、`PhotoMission`、`OwnerMessageResponse`、`SouvenirItem`、`PetAuthoredGuide` 这 5 个——正好是上一轮审计中**已经漂移过**的那几个。`Models/` 下另外 119 个 Codable 类型（`CommunicatorMessage`、`DayPlan`、`AgentStatus`、`EconomySnapshot`…）无任何解码护栏。

**判断**：上一轮补的是**已发生**的漂移，**下一次**漂移仍会静默。参考 §1.1，映射层现状是干净的，所以这里不是补窟窿，而是**防复发**。

**验收标准**（二选一，推荐前者）
1. **优先**：把 §1.1 的比对做成脚本纳入 CI（后端 schema × iOS CodingKeys 自动 diff），漂移即让 CI 红。这比手写 119 个 fixture 更省力且不会腐化。
2. 或：为主链路模型（通讯器 / 地图 / 经济 / 回忆四大面）补 fixture，覆盖率从 4% 提到主链路 100%。

### P1-2　NPC 展示字典与 cast 无同步保障（地图会静默少人）

**位置**
- `PetJourneyIOS/PetJourneyIOS/Views/JourneyMapModels.swift:271-292`
- 对照正确写法：`PetJourneyIOS/PetJourneyIOS/Services/MockPetJourneyService+Communicator.swift:590`

**现象**：`DemoCompanionPet.samples` 每天从 6 人 cast 轮换取 5 位出场，但取展示元数据时是

```swift
guard let meta = presentation[name] else { continue }   // :292
```

**触发场景**：任何人往 `NPCSociety.cast`（或后端 `npc_society.py`）加第 7 个 NPC 而忘了同步这个 `presentation` 字典 → 轮到 TA 出场那天，**地图上静默少显示一位同伴**，不报错不崩不留痕。

**不对称点**：朋友圈侧同一模式用的是兜底 `?? ("🐾", .like, "轻轻回应了一下")`（`MockPetJourneyService+Communicator.swift:590`），所以不会漏人。**同一风险两处处理方式不一致，地图侧是错的那个。**

另：两侧测试中**均无**断言保证 iOS cast 与后端 cast 一致（当前是一致的，靠人工维持）。

**验收标准**
1. 地图侧改为兜底（与朋友圈侧一致），不允许 `continue` 丢人。
2. 新增测试：断言 `NPCSociety.cast` 中每个身份在两个 `presentation` 字典里都有条目。
3. 建议再加一条后端测试或 CI 检查，断言两侧 cast 的 id/name/species 一致。

### P1-3　交通班次的三个证据字段 iOS 完全未建模

**位置**
- 后端：`PetJourneyBackend/app/schemas/pet.py:203-205`
- iOS：`PetJourneyIOS/PetJourneyIOS/Models/TravelModels.swift:131-156`

**现象**：后端 `ScheduledTransportLeg` 下发

```python
source_urls: list[str] = Field(default_factory=list)
confidence: str | None = None
search_query: str | None = None
```

iOS 侧这三个字段**一个都没建模**（这是 80 对同名模型比对中**唯一**的未建模缺口）。

已确认后端是**真的在填**它们，不是空壳：`app/transport_schedule/openai_provider.py:235-251` 从 LLM 结果里解析 `source_urls` 并写入 `search_query`。

**为什么重要**：iOS 已经建模了 `reality_level` / `is_simulated`，UI 已在区分「真实班次 vs 模拟班次」，但支撑这个区分的**证据被丢弃了**。这与上一轮补 `PlaceEvidencePacket.provider_evidence`、`PlaceSignal.raw` 是同一类缺口，只是交通这条线漏了。

**验收标准**
1. `ScheduledTransportLeg` 补上三个字段（`sourceURLs` / `confidence` / `searchQuery`）及对应 `CodingKeys`，均为可选或带默认。
2. 文案层若要展示，**不得暴露内部机制**（硬规则 2）——不要出现「搜索词」「LLM」「置信度」这类词，用仪式化表达。

---

## 4. P2 —— 打磨项

### P2-1　地图每秒全量重算（主界面主线程）

**位置**：`PetJourneyIOS/PetJourneyIOS/Views/JourneyMapView.swift:265`

`TimelineView(.periodic(from: .now, by: 1.0))` 的闭包里塞了约 15 个派生计算，包括：
- `JourneyMapEvent.events(...)`（`JourneyMapModels.swift:88`，无记忆化）
- 路线规划 `JourneyRoutePlan.fallback` / `backendPlan`
- `DemoCompanionPet.samples(...)`，其内部 `coordinateAvoidingCrowd` 对递增的 `occupied` 数组做 O(n²) 去重

这些值秒级之间**几乎不变**（事件列表、路线 key、当天 NPC 阵容都是天/请求级别的）。真正需要每秒 tick 的只有 `movingCoordinate`、`activity`、`phase` 三项。

另注：`DemoCompanionPet.samples` 内部用的是 `Date()` 而非闭包给的 `timeline.date`（`JourneyMapModels.swift:283`），与 TimelineView 的时间源不一致。

**验收标准**：把与时间无关的派生值提到 tick 之外（缓存/记忆化，按 routeKey 或请求版本失效），tick 内只保留真正随秒变化的三项。改完地图行为不变。

### P2-2　一处裸 `Color.white` 作背景

**位置**：`PetJourneyIOS/PetJourneyIOS/Views/IllustratedGuidePreview.swift:294`

```swift
.background(Color.white.opacity(0.62))
```

按 AGENTS.md，纸质纪念物应走 `paper` 系固定令牌，白色不得用作背景/卡片表面。

（另两处白色——`JourneyMapMarkers.swift:299`、`JourneyDayRecap.swift:553`——都是头像「贴纸式白圈」，是规则明确允许的，**不要改**。）

### P2-3　Mock 明信片文案里宠物「举手机」

**位置**：`PetJourneyIOS/PetJourneyIOS/Services/MockPetJourneyService+Journey.swift:366`

> 「我把手机举得低低的，在 XX 把这一刻留下来了。」

世界观里宠物用的是**通讯器**。硬规则 4 保留的 5 处物理设备语境中，另外 4 处指的都是**主人的**手机（换手机、贴纸贴在手机角落），只有这一处是**宠物**在用手机，不在豁免精神内。同文件 `:360` 的 `"低角度手机视角"` 同理。

### P2-4　死枚举 `OutboundMessageState.sent`

**位置**：`PetJourneyIOS/PetJourneyIOS/Core/Persistence/CachedModels.swift:42`

`sent` 从未被写入也从未被读取（送达即 `context.delete`）。随 P0-2 一并清理或明确启用。

---

## 5. 非代码项（供决策，不算缺陷）

- **ViewModels 层零测试**：现有 6 个测试文件覆盖 APIClient / AppSessionStore / ContractDecoding / MockService / Persistence / PushDeepLinkRouter，`JourneyViewModel`、`CommunicatorViewModel` 等无任何测试。P0-2 的三个缺陷正是逃逸在这个空白区。
- **`PetJourneyBackend/data-icloud-conflict-20260704/` 残留 45M**：已 gitignore，可安全删除。
- **架构门禁余量充足**：iOS 最大 729 / 800，后端最大 685 / 800，暂无拆分压力。

---

## 6. 建议整改顺序

1. **P0-3**（CI 加后端测试）—— 最省事、立刻生效，且为后续所有改动提供保护网。先做这个。
2. **P0-1**（Release 端点）—— 单文件、改动小、解除 TestFlight 阻断。
3. **P0-2**（发件队列）—— 改动面最大，需配套测试，但涉及产品情感契约，不能拖。
4. **P1-2 / P1-3** —— 各自独立，可并行。
5. **P1-1** —— 建议走 CI 脚本方案而非手写 fixture。
6. **P2 批次** —— 可合并成一个打磨提交。

每批改完按 AGENTS.md 跑：

```bash
python3 scripts/arch_gate.py
```

```bash
cd PetJourneyBackend && .venv/bin/python -m unittest discover -s tests
```

```bash
cd PetJourneyIOS && xcodebuild -project PetJourneyIOS.xcodeproj -scheme PetJourneyIOS -destination 'platform=iOS Simulator,name=iPhone 17 Pro' test
```

---

## 7. 分支现状与合并策略（2026-08-26 实测）

基线 `main` = `30de3ca`（CI 全绿）。当前有 3 个活跃分支，**均非本次审计创建**——`claude/practical-bell-939731` 来自更早的某次 Claude 会话。

| 分支 | 领先 / 落后 main | 内容 | 上游 | 合并难度 |
|---|---|---|---|---|
| `feature/account-login-receive-pet` | +2 / −0 | 账号体系 | ❌ **无（未推送）** | ✅ 可快进 |
| `fix/mac-verification-findings` | +3 / −0 | 后端文案 + Seedream 修复 | ✅ 已推送 | ✅ 可快进 |
| `claude/practical-bell-939731` | +2 / **−54** | 通讯器消息去重 | ✅ 已推送 | ⚠️ 需重写 |

实测确认：前两个分支 `git merge-base --is-ancestor main <branch>` 为真，已包含 main 全部提交；第三个为假。

### 7.1　`feature/account-login-receive-pet`（当前所在分支）

**内容**：登录界面 `SignInView`、TA 选择 `PetPickerView`、账号页 `AccountSheetView`、`fetchMe` 服务层，宠物数据跟随账号。14 文件 +705 行，含 2 个新增测试文件。

**风险 1 —— 无上游，从未推送。** 这 705 行的唯一副本在本机。本仓库位于 iCloud 路径下，历史上出现过 iCloud 驱逐 `.git` 对象导致 git 挂死的事故。**建议立即 `git push -u origin feature/account-login-receive-pet`。**

**风险 2 —— 它动了 `AppSessionStore.swift`，但没有解决 P0-1。** 该分支只在 `#if DEBUG` 块**内部**新增了 `PETJOURNEY_BASE_URL` 环境变量覆盖：

```swift
#if DEBUG
if userDefaults === UserDefaults.standard {
    if let override = ProcessInfo.processInfo.environment["PETJOURNEY_BASE_URL"], !override.isEmpty {
        return override                    // ← 新增，仅 DEBUG 生效
    }
    return debugBackendBaseURLString
}
#endif
return "http://127.0.0.1:8000"             // ← Release 路径原封不动
```

Release 分支的 `.mock` / `127.0.0.1` 未被触及。**这个分支合入后 TestFlight 阻断依然存在**，P0-1 仍需单独修。

### 7.2　`fix/mac-verification-findings`（最干净）

三件事：后端侧「手机→通讯器」文案清理（补上 main 只做了 iOS 侧的另一半）、Seedream 参考图对齐火山方舟 data-URI 协议且生图 key 优先 `DOUBAO`、通讯器状态缺失时显示「等待信号」替代「正在连接」。

主体是后端改动 + 1 个 iOS 文件（`CommunicatorViewModel.swift`），已含 main 全部提交，随时可合。

### 7.3　`claude/practical-bell-939731`（有价值，但已基于废弃架构）

**分叉点**：`f3e0748`（2026-07-05），距今近两个月，落后 54 个提交。中途 merge 过一次 main，但此后 main 又前进了。

**它改的 13 个文件里，2 个在当前 main 上已不存在：**

| 文件 | 去向 |
|---|---|
| `PetJourneyBackend/tests/test_api.py` | 被 `d72114c` 拆成 `base.py` + 10 个领域测试文件 |
| `PetJourneyIOS/PetJourneyIOS/Models/PetModels.swift` | 被 `0c02afd` 拆成 17 个领域模型文件 |

即该分支是**基于 God File 拆分之前的架构**写的，直接 merge 会冲突。

**但不要丢弃它。** 其核心功能是通讯器 `client_message_id` 重发去重，实测确认 **main 上完全没有 `client_message_id` / `clientMessageID`**，功能尚未合入。

**关键关联：这与 P0-2 是同一问题域的两半。** iOS 侧 outbox 补发（P0-2）与后端侧重发去重必须配套——否则弱网抖动会产生重复消息。**修 P0-2 时应把本分支的后端去重逻辑一并重写落地到当前拆分后的结构上**，而不是当作独立分支去 merge。

### 7.4　文件重叠与建议合并顺序

分支间存在重叠，顺序错了会制造无谓冲突：

- `feature` × `claude` 撞 4 个文件：`CommunicatorViews.swift`、`PetJourneyService.swift`、`RemotePetJourneyService.swift`、`MockPetJourneyServiceTests.swift`
- `fix` × `claude` 撞 1 个文件：`communicator/engine.py`

**建议顺序**：

1. `fix/mac-verification-findings` → main（最干净，纯快进）
2. `feature/account-login-receive-pet` → main（快进；**先 push 备份**）
3. `claude/practical-bell-939731` **不 merge**，改为在最新 main 上重写其去重逻辑，与 P0-2 合并成一个改动

---

## 8. 分支清理约定（用户 2026-08-26 指定，新增硬规则）

> **每一个完成合入 main 的分支都必须及时清理干净——本地与远端同时删除，不留残枝。**

**当前状态**：`git branch --merged main` 与 `git branch -r --merged main` 均为空，`git remote prune --dry-run` 无输出。**目前没有需要清理的已合并分支**，本约定对后续每次合并生效。

**每次合并后立即执行**：

```bash
git branch -d <branch>
```

```bash
git push origin --delete <branch>
```

```bash
git remote prune origin
```

**要求**：

1. 用 `git branch -d`（小写 d）而非 `-D`——`-d` 在分支未完全合入时会拒绝删除，是一道安全网。若 `-d` 报错，说明该分支还有内容没进 main，**先查清楚再说，不要直接改用 `-D`**。
2. 本地删了必须同时删远端，反之亦然。只删一边会让下次 `git branch -a` 继续显示幽灵分支。
3. §7.3 那种「不 merge、改为重写」的分支，在重写内容合入 main 并验证通过后，同样要删除，不要留着"以后可能有用"。
4. 定期用下面两条自查，输出应为空：

```bash
git branch --merged main | grep -v -e "^\*" -e "main$"
```

```bash
git branch -r --merged main | grep -v -e "origin/main" -e "origin/HEAD"
```

**建议**：把本条约定补进 `AGENTS.md` 的「协作方式」小节，使其对 Codex / Claude Code / DeepSeek 同等生效（此项由 DeepSeek 执行）。
