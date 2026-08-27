# 架构清晰度审计报告（2026-08-26）

> 审计方：Claude Code（只出结论，不改代码）
> 整改方：DeepSeek
> 基线提交：`bfa08ce`（本地 main，领先 origin/main 15 个提交）
> 同批文档：`audits/2026-08-26-full-project-audit/`（工程）、`audits/2026-08-26-ui-ux-review/`（观感）

**结论先行：局部很干净，整体没有约束——项目有「尺寸纪律」，没有「依赖纪律」。**

---

## 0. 审计方法与实测基线

| 维度 | 手段 |
|---|---|
| 目录与体量分布 | 按目录统计文件数/行数，前后端各一遍 |
| 依赖方向 | 脚本解析全部 `import` / `from` 构建模块图，检查层次倒挂与循环 |
| God Object | 按**类型**（而非文件）归并 `extension`，统计跨文件体量 |
| 层次泄漏 | grep View 层是否直连 Service/APIClient；统计 `Views/` 下非 View 类型 |
| 门禁能力边界 | 读 `scripts/arch_gate.py` 实际度量口径 |

**规模基线**

| | 文件 | 行数 |
|---|---|---|
| 后端 `app/` | 161 py | 24,462 |
| iOS `PetJourneyIOS/` | 105 swift | 28,352 |

**结论分两类看**
- 🔍 **已验证事实** —— 有数据或代码位置为证，可直接执行。
- 💭 **架构判断** —— 我的意见，**需你拍板**，不是缺陷。

---

## 1. 核心判断（💭）

仓库唯一的架构强制是 `scripts/arch_gate.py`：**单文件** ≤ 800 行、≤ 30 个类型（`DEFAULT_MAX_LINES = 800` / `DEFAULT_MAX_TYPES = 30`，`scan()` 逐文件度量）。

而 `AGENTS.md` 中**没有任何一句**规定层次、依赖方向、或某类型该归属哪一层——grep「分层 / 层次 / 依赖方向 / layer / 不得依赖」全部零命中。硬规则 3 只说「单文件宜控制在 ~800 行以内、单文件内类型不宜超过 ~30 个」。

**后果是「横向溢出」**：为了过门禁而拆文件，问题被推到门禁看不见的地方——

| 现象 | 门禁读数 |
|---|---|
| `JourneyViewModel` 881 行拆成 6 个文件 | ✅ 每个都 < 800 |
| 后端 God File 拆成包，但 36 个模块仍平铺根目录 | ✅ 每个都 < 800 |
| iOS 领域模型被推进 `Views/` | ✅ 目录不在门禁范围 |

**拆分本身没错，错在拆完就当问题解决了。** 下面每一条都是这个模式的具体表现。

---

## 2. 已验证干净的部分（**不要动**）

| 项 | 实测结论 |
|---|---|
| 后端循环依赖 | **0 对**（模块级全图扫描） |
| `app/storage.py` 门面 | 设计良好：1672 行 / 90 方法 / 22 表的 God File 拆成 11 个 repository mixin，多重继承聚合，注释交代了拆分原因，并保留历史导入面（`from app.storage import JourneyStorage` 仍可用）。**这是全仓库最好的一次拆分，是范例** |
| 后端 16 个子包 | `agent_engine`(16 文件) / `communicator`(15) / `repositories`(12) / `schemas`(10) 等拆得合理，门面 re-export 到位 |
| iOS MVVM 边界 | **无一个 View 直接调用 Service 或 APIClient**。6 处 `let service: any PetJourneyService` 均只用于 `init` 中构造 `StateObject(wrappedValue: XxxViewModel(...))`，是标准 SwiftUI 依赖传递 |
| iOS 分层目录 | `App / Core / Design / Models / Services / ViewModels / Views` 划分本身是对的，问题在填充比例而非划分 |

---

## 3. P0 —— 根因两条

### P0-1　arch_gate 有盲区：跨文件的 God Object 拿不到（🔍 已验证）

**位置**：`scripts/arch_gate.py:24-25`（`DEFAULT_MAX_LINES` / `DEFAULT_MAX_TYPES`）、`:73 scan()`

**现象**：门禁逐**文件**度量。同一个类型用 `extension` 摊进多个文件即可绕过，且绕过后门禁全绿、无任何提示。

**实例 —— `JourneyViewModel`**

| 文件 | 行数 | 方法数 |
|---|---|---|
| `ViewModels/JourneyViewModel.swift` | 135 | 1 |
| `ViewModels/JourneyViewModel+Lifecycle.swift` | 258 | 11 |
| `ViewModels/JourneyViewModel+Travel.swift` | 164 | 7 |
| `ViewModels/JourneyViewModel+Details.swift` | 132 | 10 |
| `ViewModels/JourneyViewModel+Communication.swift` | 110 | 4 |
| `ViewModels/JourneyViewModel+Souvenirs.swift` | 82 | 6 |
| **合计** | **881** | **39** |

外加 **31 个 `@Published` 属性**（`JourneyViewModel.swift`）。

一个类型同时负责生命周期、旅行、详情、通讯、纪念品五件事——是 God Object 换了个马甲。**门禁全绿。**

**附带性能影响**：31 个 `@Published` 在同一个 `ObservableObject` 上，任一属性变更都会触发全部观察者重算。与 `audits/2026-08-26-full-project-audit` 中 P2-1（地图 1Hz 全量重算）叠加，地图页每秒既重算派生值又可能触发大范围视图刷新。

**验收标准**
1. `arch_gate.py` 增加「跨文件类型体量」检查：Swift 侧按类型名归并 `class X` / `struct X` / `extension X`，统计合并后的行数与方法数；Python 侧按类名归并同名 `class` 的 mixin 定义。
2. 阈值可与单文件不同（建议单类型 ≤ 600 行 / ≤ 25 方法，具体由你定），超标即 CI 红。
3. `JourneyViewModel` 按职责真正拆成独立类型（如旅行/通讯/纪念品各自成 ViewModel），而不是继续加 extension。**拆分方案需你先拍板，改动面较大。**
4. 顺带评估把 31 个 `@Published` 按使用面收敛（拆分后自然缓解）。

> ⚠️ 第 3 条是 💭 架构判断，改动面大；第 1、2 条是 🔍 可直接做的门禁增强。**建议先做 1、2 让问题可见，再决定 3。**

### P0-2　分层约定完全没有成文（🔍 已验证）

**位置**：`AGENTS.md`

**现象**：全文对「哪层可以依赖哪层」「新引擎该建包还是建平铺文件」「模型该放哪个目录」**零字说明**。唯一的架构条款是硬规则 3 的单文件尺寸。

**这是本报告其余所有问题的共同根因**：没有成文规则 → 新人和 AI 代理只能模仿最近看到的写法 → 同一类东西出现多种形态（见 P1-2）。

**验收标准**
1. 在 `AGENTS.md` 新增「架构分层」小节，至少写明三件事：
   - 后端依赖方向（建议：`routers → engines → repositories → storage/infra`，`schemas` 与 `utils/config` 为公共底层，**底层不得反向 import 上层**）；
   - 后端新增引擎的形态规则（例：单文件超过 N 行或职责超过一个即建包，否则平铺）；
   - iOS 类型归属规则（`Views/` 只放 `: View`；领域与表现模型一律进 `Models/`；跨视图复用的构建器进 `Models/` 或新建 `Presentation/`）。
2. 规则要能被机器检查（配合 P1-1、P1-3 的门禁），否则仍会腐化。

---

## 4. P1 —— 三处结构性问题

### P1-1　`Views/` 是事实上的倾倒场（🔍 已验证）

**体量分布**

| 层 | 行数 | 占比 |
|---|---|---|
| **`Views/`**（含 `Components/`、`Map/`） | **18,252** | **64%** |
| `Models/` | 3,464 | 12% |
| `Services/` | 3,386 | 12% |
| **`ViewModels/`** | **1,636** | **6%** |

`Views : ViewModels = 11 : 1`。MVVM 项目里这个比例是倒的。

**更直接的证据**：`Views/` 下共 **223 个顶层类型，其中仅 176 个是 SwiftUI View**，**47 个不是**——领域模型、枚举、构建器：

```
DayRecapBuilder          JourneyDaySchedule       PetGuideDigest
JourneyMapEvent          MerchantStop             JourneyActivitySnapshot
JourneyMapEventPhase     DayRecapChapter          GuideDigestMetric
RoutePerspective         IntroFlightState         JourneyDateChipModel  …
```

对比：`Models/` 只有 **129 个类型**。**模型在视图层比在模型层还多。**

**两个文件名字本身就招了**
- `Views/JourneyMapModels.swift` —— 655 行 / 5 个类型
- `Views/PetCredentialModels.swift` —— 632 行 / 5 个类型

叫 `*Models` 却住在 `Views/`，合计 1,287 行。

**验收标准**
1. 先搬这两个自证的文件到 `Models/`（或新建 `Presentation/`），登记 pbxproj。这两个零争议。
2. 其余 45 个非 View 类型按批次迁移，**每批跑 iOS 全量测试**。
3. 加门禁：`Views/` 下不允许出现非 `: View` 的顶层类型（`Views/*Models.swift` 这类命名可先做一条硬检查）。
4. 迁移只是移动 + pbxproj 登记，**不要顺手改逻辑**，否则 review 无法分辨。

### P1-2　后端包化做了一半，且没有规则解释（🔍 已验证）

**现象**：`app/` 根目录仍平铺 **36 个模块 / 8,493 行 = 后端总量的 35%**，其中不乏与已包化引擎同量级的大文件：

```
illustrated_guide.py    685      economy_engine.py       625
route_planner.py        676      souvenir_catalog.py     535
photo_mission_brain.py  453      transport_reality.py    415
credential_prompt_builder.py 411 google_maps_services.py 410
```

**问题不在于它们大，而在于形态不一致且无规则可循**：

| 同量级、同性质 | 形态 |
|---|---|
| `route_planner.py` 676 行 | 平铺单文件 |
| `pet_life_engine/` 649 行 | 包（5 文件） |

新人（和 AI 代理）无从判断新引擎该建包还是建文件。

**验收标准**
1. 在 `AGENTS.md` 写明形态规则（见 P0-2 第 1 条第二项）。
2. 按规则把根目录中超标的引擎逐个包化，**参照 `storage.py` 的门面模式**——保留历史导入面、注释交代拆分原因。
3. `config.py` / `main.py` / `dependencies.py` / `utils.py` 等组合根与基础设施**留在根目录是对的，不要动**。
4. 一次一个引擎、单独提交，每次跑后端全量测试 + 契约门禁。

### P1-3　`http_utils.py` 是杂物抽屉，且造成全后端唯一的层次倒挂（🔍 已验证）

**位置**：`PetJourneyBackend/app/http_utils.py`（110 行）

**现象**：名字像底层 HTTP 工具，实际装了六件互不相干的事：

| 函数 | 职责 |
|---|---|
| `parse_dna` | 领域解析 |
| `ensure_demo_media` | 演示数据播种 |
| `sanitize_filename` | 文件名清洗 |
| `public_photo_url` / `public_media_url` | URL 构建 |
| `with_not_found` | FastAPI 异常辅助 |
| `lightweight_illustrated_guide_plan(engine, route_planner, pet) -> JourneyPlan` | **领域编排** |

为此它 import 了 `.agent_engine`（`JourneyEngine`）与 `.route_planner`（`TravelRoutePlanner`）——**工具模块反向依赖引擎层**。

经逐条核对，这是**全后端唯一真实的层次倒挂**（其余自动扫描命中均为误报，见 §5）。

**验收标准**
1. 按职责拆散：URL/文件名工具留在真正的工具模块；`parse_dna` 归领域；`with_not_found` 归 `routers` 或 `dependencies`；`ensure_demo_media` 归启动/播种；`lightweight_illustrated_guide_plan` 归引擎层。
2. 拆完后 `http_utils`（或其继任者）**不得 import 任何引擎模块**。
3. 加依赖方向门禁（见 P0-2 第 2 条）锁住，防复发。

---

## 5. 误报澄清（**重要：DeepSeek 不要改这些**）

我先跑了一个自动分层脚本，报出 **69 处「层次倒挂」**。逐条核对后，**真实的只有 1 处**（P1-3 的 `http_utils.py`）。其余全部是我脚本的缺陷或对设计的误判：

| 自动报出的「问题」 | 实际情况 |
|---|---|
| `schemas → base/pet/place/travel/...` 等 20+ 条 | 脚本把**包内相对导入**（`from .base import`）当成跨层依赖。`schemas/__init__.py` re-export 自己的子模块，正常 |
| `repositories.economy → records`、`repositories.pets → records` | 同上，`repositories/records.py` 是包内模块 |
| `storage → repositories.*` 共 11 条 | **刻意的门面组合**，见 §2。设计正确 |
| `dependencies → 25 个引擎` | `dependencies.py` 是 FastAPI 的**依赖注入组合根**，import 引擎正是它的职责 |
| `main → routers` | `main.py` 是应用组合根，正常 |
| `routers.auth → storage` | 只 import 了 `PetRecord` / `PetOwnershipConflict` **两个类型**，storage 实例走 `Depends(get_storage)` 注入。正常 |

**另外两条也别改**：
- iOS 那 6 个持有 `let service` 的 View —— 只用于构造 ViewModel，是标准 SwiftUI 写法（§2 已验证）。
- 后端循环依赖 —— 实测 0 对，不需要处理。

---

## 6. 建议：把隐形约定变成显性门禁

项目已经证明门禁有效——`scripts/contract_diff.py` 我做过破坏性验证（注入 `travel_coin` → `travel_coin_DRIFT`，门禁准确报出并 exit 1，还原后工作区干净）。同样的思路适用于架构：

| # | 门禁 | 拦住什么 | 成本 |
|---|---|---|---|
| 1 | **跨文件类型体量**（P0-1） | 拆 extension 绕过门禁 | 低，改 `arch_gate.py` |
| 2 | **依赖方向**（P0-2/P1-3） | 底层反向 import 上层 | 中，需先定义层次 |
| 3 | **`Views/` 只放 View**（P1-1） | 模型继续往视图层堆 | 低，一条 grep 即可起步 |

**第 1 条杠杆最高**——它堵死「拆文件绕过门禁」这条路，否则后面所有整改都会以同样方式复发。

---

## 7. 建议整改顺序

| 批次 | 内容 | 性质 |
|---|---|---|
| 第一批 | P0-2 写分层约定 + 门禁 1、3 | 🔍 低风险高杠杆，先让问题可见 |
| 第二批 | P1-3 `http_utils` 拆散 + 门禁 2 | 🔍 范围小、边界清楚 |
| 第三批 | P1-1 迁 `Views/*Models.swift` 两个自证文件 | 🔍 零争议，纯移动 |
| 第四批 | P1-2 后端根目录逐个包化 | 🔍 一次一个引擎，单独提交 |
| 待拍板 | P0-1 第 3 条 `JourneyViewModel` 真拆分；P1-1 其余 45 个类型迁移 | 💭 改动面大，**等你确认方案再动** |

每批完成后按 AGENTS.md 跑：

```bash
python3 scripts/arch_gate.py
```

```bash
cd PetJourneyBackend && .venv/bin/python -m unittest discover -s tests
```

```bash
PetJourneyBackend/.venv/bin/python scripts/contract_diff.py
```

```bash
cd PetJourneyIOS && xcodebuild -project PetJourneyIOS.xcodeproj -scheme PetJourneyIOS -destination 'platform=iOS Simulator,name=iPhone 17 Pro' test
```

**注意**：§4 的迁移类改动（P1-1、P1-2）只做移动与登记，不要顺手改逻辑——否则 code review 无法区分「搬家」和「改行为」，出问题时也无法二分定位。

## 8. 回访记录（2026-08-27）：CI 抓到宿主机时区依赖并已修复

本报告 P0-3 主张的「CI 必须真跑后端测试」在首次实跑（`f1518f0`）即兑现价值：

- **现象**：`Backend Tests` 在 CI（UTC）挂 1 个用例 `test_world_simulation_anchors_stops_without_location_drift`（`'默迹咖啡馆' != '狐尾山公园'`），本机（+8）95 全绿。
- **根因**：`world_simulation/timeline.py` 的 `_stop_windows` 用裸 `now.astimezone()`（宿主机时区）划分行程窗口。生产跑 UTC，而 TA 在厦门——「当前活动」与本城墙上时间差 8 小时，该在公园时显示在咖啡馆。这是 UI/UX 审计 P0-2（地图天色）同一 bug 的后端版本：`local_time` 字段修好了，决定「TA 此刻在哪一站」的窗口划分却仍跟着服务器时区。
- **修复**（`f620059` + `971d3d7`）：
  1. `_stop_windows` / `_next_stop` 改用 `city_timezones`（`ZoneInfo(城市)`），`_timeline`/`snapshot` 传入 `plan.city`。
  2. 全后端清扫同类漏网：`city_timezones` 消费方 1 → 10（communicator `local_hour`、pet_energy 钟点、meal_rules 餐段、place_interactions 时段、route_planner/event_generator 早间判定、agent_engine `_status_for` 与计划缓存日、quest_flow 出发日、guide 缓存日、transport_reality 当日班次起点）；`story_ticker`/memories 分桶/证件签发日等宿主日期改为确定性 UTC。
  3. `meal_rules` 新约定：无时区 datetime = 墙上时间本身（直读小时），带时区 instant 需传城市名换算。
  4. 新增跨时区一致性测试：同一 plan 在 UTC / America/New_York / Asia/Tokyo 宿主机时区下 `snapshot()` 结果一致（`time.tzset` 轮换）。
  5. `AGENTS.md`：后端测试命令强制 `TZ=UTC` 对齐 CI；架构分层写入「世界模拟墙上时间一律走 `city_timezones`，禁裸 `now.astimezone()` / `date.today()`」。
- **结果**：96 测试在 TZ=UTC / +8 / America/New_York 下全绿，三门禁通过，`origin/main = 971d3d7` 时 Backend Tests / Architecture Gate / iOS Build & Test 三项 CI 全部 success。
