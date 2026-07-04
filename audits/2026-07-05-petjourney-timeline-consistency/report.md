# PetJourney 时间线一致性审计报告

审计日期：2026-07-05  
审计范围：本次真机截图 11 张、用户复盘描述、iOS SwiftUI 代码、FastAPI 后端世界模拟/通讯器/调度器/图片链路。  
证据目录：`audits/2026-07-05-petjourney-timeline-consistency/screenshots/`

## 总体结论

这次问题不是单个 UI bug，而是“世界状态源分裂”造成的系统性错乱。

当前产品同时存在多套状态计算方式：

- 后端 `city_position` 按宠物 `created_at` 推导当前城市。
- 后端 `journey_plan/world_snapshot` 在世界杯开关下生成洛杉矶计划和飞行交通段。
- 后端 `event_generator` 按城市和 elapsed 自动生成明信片。
- 后端 `communicator` 独立生成聊天回复、朋友圈种子动态、附件位置卡。
- iOS `MockPetJourneyService` 也按 `createdAt` 推导城市，并固定从厦门开始。
- iOS 地图在部分场景下使用后端 world snapshot，在另一些 fallback 场景下使用本地日程和路线回放。

所以用户看到的是：标题在洛杉矶，位置在厦门；首页说正在飞行，明信片却在厦门咖啡馆；朋友圈说已经到洛杉矶机场，飞行卡又显示还剩 10 小时；几分钟后又跳成 16 分钟。各个模块的答案单独看都像有逻辑，合在一起就是同一只宠物同时存在于多个世界。

## 证据映射

| 截图 | 现象 | 判断 |
| --- | --- | --- |
| `01-map-flight-state.jpg` | 标题“第 1 天 · 洛杉矶”，飞行卡“参考真实航班”，宠物 marker 不在真实航线表达里 | 城市标题、交通态、地图坐标来自不同状态源 |
| `02-postcard-xiamen-cafe.jpg` | 飞行中收到厦门咖啡馆明信片，时间 2026-07-05 00:04 | 明信片生成没有被飞行态阻断 |
| `03-friends-los-angeles-airport.jpg` | 飞行未结束，但朋友圈出现洛杉矶机场到达/停留动态 | 朋友圈 seed 动态绕过飞行态频控 |
| `04-chat-duplicate-look-now.jpg` | “看看你现在”重试后生成两轮回复，位置卡仍指向洛杉矶机场 | 聊天发送缺少 idempotency，位置卡使用当前 world snapshot 但和飞行叙事冲突 |
| `05-flight-card-expanded-copy.jpg` | “参考真实航班前往赛场城市”“查到公开时间线”等内部表达 | 后端内部字段直接进入用户可见文案 |
| `06-flight-card-expanded-details.jpg` | 剩余 10h48m、航班卡、天气文本存在，但表达仍偏内部 | 飞行态已有雏形，但产品文案和状态约束不足 |
| `07-itinerary-list.jpg` | 路线从厦门咖啡馆跳到洛杉矶机场，再到赛场 | 同一天本地生活计划和跨洋比赛计划混排 |
| `08-guide-page-loading.jpg` | 手账页面长时间 loading | 图片 URL/生成状态/前端 fallback 不稳定 |
| `09-route-realism-warning.jpg` | “目的地跨洋，步行、驾车和火车都不符合真实世界原则”暴露给用户 | 内部规则说明进入产品界面 |
| `10-time-jump-flight.jpg` | 几分钟内飞行剩余从 10 小时级跳到 16 分钟 | 行程时钟不稳定，或前端 fallback/后端计划重算不一致 |
| `11-memory-internal-tags.jpg` | `episodic`、`postcard`、`agent_turn`、`scheduler`、重要分数外露 | 回忆列表直接展示数据层字段 |

## P0 问题

### P0-1：缺少唯一世界状态快照，导致城市/交通/活动互相打架

现象：

- 新宠物或重新寻找时默认在厦门。
- 首页标题可能显示洛杉矶，但位置/明信片/动态仍出现厦门。
- `city_position`、`journey_plan`、`world_snapshot`、通讯器位置卡互相不完全一致。

代码证据：

- 后端城市序列固定从厦门开始，`MockMapProvider.city_for_elapsed()` 新宠物 `elapsed=0` 返回 `CITIES[0]`：[providers.py](/Users/austin/Desktop/petsoul/PetJourneyBackend/app/providers.py:28)、[providers.py](/Users/austin/Desktop/petsoul/PetJourneyBackend/app/providers.py:109)
- `create_initial_journey()` 直接用 `_city_for_elapsed(0)`：[agent_engine.py](/Users/austin/Desktop/petsoul/PetJourneyBackend/app/agent_engine.py:198)
- `city_position()` 单独按 `created_at` 算位置，没有引用 world snapshot 或 active transport：[agent_engine.py](/Users/austin/Desktop/petsoul/PetJourneyBackend/app/agent_engine.py:381)
- `route_plan/journey_plan/world_snapshot` 又分别在请求时重新按 `utcnow()` 算城市和计划：[agent_engine.py](/Users/austin/Desktop/petsoul/PetJourneyBackend/app/agent_engine.py:386)、[agent_engine.py](/Users/austin/Desktop/petsoul/PetJourneyBackend/app/agent_engine.py:664)
- iOS Mock 也固定 `cities[0] = 厦门`，创建宠物返回厦门：[MockPetJourneyService.swift](/Users/austin/Desktop/petsoul/PetJourneyIOS/PetJourneyIOS/Services/MockPetJourneyService.swift:51)、[MockPetJourneyService.swift](/Users/austin/Desktop/petsoul/PetJourneyIOS/PetJourneyIOS/Services/MockPetJourneyService.swift:87)
- iOS `loadInitial/refreshStatus` 并行拉 `status/cityPosition/worldSnapshot`，没有统一版本号：[JourneyViewModel.swift](/Users/austin/Desktop/petsoul/PetJourneyIOS/PetJourneyIOS/ViewModels/JourneyViewModel.swift:132)、[JourneyViewModel.swift](/Users/austin/Desktop/petsoul/PetJourneyIOS/PetJourneyIOS/ViewModels/JourneyViewModel.swift:170)

判断：

当前系统没有一个“此刻唯一状态”。每个接口都在现场推导，且推导依据不完全一样。用户快速刷新、网络慢、缓存回填、世界杯路线开启时，就会出现不同模块拿到不同“此刻”。

必须修：

- 新增唯一 `WorldStateSnapshot/JourneyClockState`，成为所有 UI 和内容生成的读源。
- 字段至少包括：`phase`、`origin_city`、`destination_city`、`current_city`、`display_city`、`current_coords`、`active_transport_leg`、`leg_progress`、`local_time`、`weather`、`can_message_now`、`can_generate_photo_now`、`can_post_moment_now`。
- `GET /city_position` 不再自己算城市，应返回 `world_state.current_coords/current_city`。
- `status/journey_plan/world_snapshot/communicator` 必须带同一个 `world_state_id/generated_at`，前端只展示同一版本的数据。

### P0-2：飞行态没有成为阻断模式，导致飞行中产生本地明信片/朋友圈/照片

现象：

- 飞行中收到厦门咖啡馆明信片。
- 飞行未结束时朋友圈已经出现洛杉矶机场动态。
- 聊天要求“看看你现在”时，一边说信号不稳，一边发位置卡到洛杉矶机场。

代码证据：

- `WorldSimulationEngine` 虽然会识别 active transport，并把 flight 映射为 `JourneyStatus.flying`：[world_simulation.py](/Users/austin/Desktop/petsoul/PetJourneyBackend/app/world_simulation.py:100)、[world_simulation.py](/Users/austin/Desktop/petsoul/PetJourneyBackend/app/world_simulation.py:367)
- 但自动明信片在 `JourneyEventGenerator.advance()` 只看 `elapsed >= 35` 和 `count_postcards == 0`，不检查 active transport/flying：[event_generator.py](/Users/austin/Desktop/petsoul/PetJourneyBackend/app/event_generator.py:95)
- 明信片地点来自当前 city 的 places，而不是 world snapshot 的可拍照活动：[event_generator.py](/Users/austin/Desktop/petsoul/PetJourneyBackend/app/event_generator.py:147)
- 朋友圈首次打开时 `ensure_seed_moments()` 强制生成 arrival/resting 两条动态，不经过 `_can_create()` 的飞行态限制：[communicator/engine.py](/Users/austin/Desktop/petsoul/PetJourneyBackend/app/communicator/engine.py:300)、[communicator/moment_generator.py](/Users/austin/Desktop/petsoul/PetJourneyBackend/app/communicator/moment_generator.py:31)
- `_can_create()` 本身有 `world.is_flying` 禁止发动态，但 seed 流程绕过了它：[communicator/moment_generator.py](/Users/austin/Desktop/petsoul/PetJourneyBackend/app/communicator/moment_generator.py:100)

判断：

飞行态只影响了部分 UI 和聊天策略，没有成为全系统状态机的“锁”。内容生成器仍然可以在飞行中创建本地活动证据。

必须修：

- 引入 `phase=in_transit` 的硬规则：禁止普通明信片、普通朋友圈、普通自拍、普通地点打卡。
- 飞行中允许的内容只能是：飞行状态卡、延迟投递说明、机上小想法、落地后补发。
- `event_generator.advance()`、`generate_selfie()`、`moment_generator.ensure_seed_moments()`、scheduler 通知都必须先判断 `world_state.can_generate_*`。
- 飞行期间如果要发内容，必须带 `captured_at` 和 `delivered_at`，避免“00:04 正在咖啡馆”的歧义。

### P0-3：飞行时间和路线没有被稳定锁定，出现剩余时间跳变和路线不真实

现象：

- 飞行剩余从 10 小时级别跳到 16 分钟。
- 地图路线像两点连线，不像真实飞行路径。
- 宠物没有明确“坐在飞机 icon 上沿航线移动”的视觉表达。

代码证据：

- 世界杯计划中飞行段是 `home-city-to-la-flight`，距离和时长写死为 11100km/12h：[route_planner.py](/Users/austin/Desktop/petsoul/PetJourneyBackend/app/route_planner.py:434)
- `worldcup_legs()` 用 `pet.created_at + 2h` 作为出发，`+12h` 作为飞行时长：[transport_reality.py](/Users/austin/Desktop/petsoul/PetJourneyBackend/app/transport_reality.py:100)
- 交通 leg 的 polyline 是 `origin;destination` 两点直线：[transport_reality.py](/Users/austin/Desktop/petsoul/PetJourneyBackend/app/transport_reality.py:321)
- iOS `JourneyRoutePlan.backendPlan()` 对 flight/train/ferry fallback 也是 `[start, end]` 两点：[JourneyRouteSupport.swift](/Users/austin/Desktop/petsoul/PetJourneyIOS/PetJourneyIOS/Views/JourneyRouteSupport.swift:62)
- iOS 还保留了 42 秒循环路线回放 `JourneyMotion.liveCoordinate()`，如果 world snapshot 缺失或 fallback 被用到，就会脱离真实时钟：[JourneyRouteSupport.swift](/Users/austin/Desktop/petsoul/PetJourneyIOS/PetJourneyIOS/Views/JourneyRouteSupport.swift:181)

判断：

现在的飞行不是一个稳定落库的 `TransportLegInstance`，而是每次从宠物创建时间和计划现场推导出来。真实航班候选、后端计划缓存、前端 fallback、截图时刻之间可能不同步。

必须修：

- 创建旅行任务时落库 `transport_leg_instance`：航班号、起飞机场、落地机场、起飞时间、预计落地时间、timezone、route_polyline/great_circle_points、status。
- UI 只使用这个实例，不从 `created_at` 重新推导飞行时间。
- 飞行航线至少用 great-circle 分段点，不用两点直线。
- 飞行中 marker 应使用飞机载具态：宠物头像附着在飞机 bubble 上，label 写“坐 MF829 飞往洛杉矶”。

## P1 问题

### P1-1：新宠物默认从厦门出发，缺少产品解释或随机/个性化规则

现象：

- 重新注册寻找宠物时起点仍是厦门。
- 用户感知为“所有宠物都从厦门出发”，不符合平行世界旅行感。

代码证据：

- 后端 `CITIES` 第一个就是厦门，elapsed 0 返回第一个城市：[providers.py](/Users/austin/Desktop/petsoul/PetJourneyBackend/app/providers.py:28)
- iOS Mock 创建宠物时 `location: cities[0].name`，并用 `cities[0]` seed 朋友圈：[MockPetJourneyService.swift](/Users/austin/Desktop/petsoul/PetJourneyIOS/PetJourneyIOS/Services/MockPetJourneyService.swift:115)
- iOS mock guide 也硬编码从厦门到目的地：[MockPetJourneyService.swift](/Users/austin/Desktop/petsoul/PetJourneyIOS/PetJourneyIOS/Services/MockPetJourneyService.swift:2155)

建议：

- 不要用 city list 第一个元素当默认起点。
- 宠物创建时落库 `origin_anchor`，由以下来源决定：主人当前城市、照片 EXIF/上传上下文、宠物 DNA/性格 seed、随机城市池。
- 如果产品要保留厦门作为测试城市，必须只在 Mock/Debug 数据里出现，真机 remote 不应固定厦门。

### P1-2：路线日历把“本地一天”和“洛杉矶比赛日”混成同一天

现象：

- 核心路线从“默迹咖啡馆 08:10”直接到“洛杉矶机场到达层 16:30”，中间缺少出发、候机、飞行、时区切换。
- 标题“洛杉矶慢慢生活的一天”却包含厦门准备站。

代码证据：

- `_worldcup_plan()` 的 stops 第一站使用 `places[0]`，但后续站都是洛杉矶：[route_planner.py](/Users/austin/Desktop/petsoul/PetJourneyBackend/app/route_planner.py:427)
- 所有 stop 只用本地字符串 `08:10/16:30/18:00/20:00`，没有各自 timezone：[route_planner.py](/Users/austin/Desktop/petsoul/PetJourneyBackend/app/route_planner.py:428)
- `WorldSimulationEngine._stop_windows()` 把所有 stop 的 `planned_time` 统一套到当前设备/服务器本地日期：[world_simulation.py](/Users/austin/Desktop/petsoul/PetJourneyBackend/app/world_simulation.py:311)

建议：

- 旅行日历拆成三段：出发城市准备、长途交通、目的地抵达后。
- 每个 stop 增加 `timezone`、`absolute_start_at`、`absolute_end_at`。
- 跨时区路线标题不要写“洛杉矶第一天”，应显示“去洛杉矶的路上”或“抵达洛杉矶前后”。

### P1-3：内部机制文案大量外露

现象：

- “参考真实航班前往赛场城市”
- “目的地跨洋，步行、驾车和火车都不符合真实世界原则”
- “沿真实道路走”
- `episodic/postcard/agent_turn/scheduler/重要 68`

代码证据：

- 交通候选 title 是“参考真实航班前往赛场城市”：[transport_reality.py](/Users/austin/Desktop/petsoul/PetJourneyBackend/app/transport_reality.py:249)
- `transport_decision.reason` 暴露真实世界原则：[route_planner.py](/Users/austin/Desktop/petsoul/PetJourneyBackend/app/route_planner.py:477)
- iOS 路线 source label 直接显示“沿真实道路走”等技术/验证口吻：[JourneyRouteSupport.swift](/Users/austin/Desktop/petsoul/PetJourneyIOS/PetJourneyIOS/Views/JourneyRouteSupport.swift:30)
- 导航条直接展示 `routePlan.sourceLabel`：[JourneyMapView.swift](/Users/austin/Desktop/petsoul/PetJourneyIOS/PetJourneyIOS/Views/JourneyMapView.swift:3144)
- 回忆卡直接展示 raw `memoryType/kind/source/importance`：[CommunicatorViews.swift](/Users/austin/Desktop/petsoul/PetJourneyIOS/PetJourneyIOS/Views/CommunicatorViews.swift:2121)

建议：

- 建立 `UserFacingCopyAdapter`，所有后端 reason/source/provider/debug 字段默认不可见。
- 交通文案替换为：
  - “小包正在坐 MF829 飞往洛杉矶”
  - “下一站：洛杉矶”
  - “预计 10 小时 48 分钟后落地”
- 回忆标签替换为：`来信`、`明信片`、`小想法`、`收藏片段`，不要展示 source、kind、importance 分数。

### P1-4：聊天重试没有幂等，失败后可能生成重复回复

现象：

- 用户第一遍发送失败，点重试后出现两次主人消息和两轮宠物回复。

代码证据：

- iOS `sendOwnerMessage()` 每次创建新的本地 UUID receipt，但请求体没有 `client_message_id/idempotency_key`：[JourneyViewModel.swift](/Users/austin/Desktop/petsoul/PetJourneyIOS/PetJourneyIOS/ViewModels/JourneyViewModel.swift:470)
- `OwnerMessageRequest` 只有 `message/intentHint`：[PetModels.swift](/Users/austin/Desktop/petsoul/PetJourneyIOS/PetJourneyIOS/Models/PetModels.swift:426)
- `CommunicatorSendRequest` 只有 `text/client_time`：[communicator/schemas.py](/Users/austin/Desktop/petsoul/PetJourneyBackend/app/communicator/schemas.py:186)
- 后端 `/messages` legacy 流程每次都会追加主人消息、宠物消息、thought/event：[communicator/engine.py](/Users/austin/Desktop/petsoul/PetJourneyBackend/app/communicator/engine.py:269)

建议：

- 请求体增加 `client_message_id`。
- 服务端 `communicator_messages` 对 `(pet_id, client_message_id)` 做唯一约束。
- retry 应更新同一条 message 的状态，不应追加新气泡。
- 对“失败但服务端已处理”的超时情况，重试应返回之前的回复。

### P1-5：图片加载失败和手账 loading 与媒体 URL 配置有关

现象：

- 明信片/手账图大量加载不出。

代码证据：

- 后端默认 `PETJOURNEY_PUBLIC_BASE_URL` 是 `http://127.0.0.1:8000`：[config.py](/Users/austin/Desktop/petsoul/PetJourneyBackend/app/config.py:90)
- 图片 URL 拼接这个 base：[main.py](/Users/austin/Desktop/petsoul/PetJourneyBackend/app/main.py:908)、[event_generator.py](/Users/austin/Desktop/petsoul/PetJourneyBackend/app/event_generator.py:256)
- 真机上访问 `127.0.0.1` 会指向手机自己，不是 Mac 后端。
- iOS 图片失败时有 fallback，但手账页 `AsyncImage.empty` 只显示 spinner，用户容易以为一直卡住：[SecondaryViews.swift](/Users/austin/Desktop/petsoul/PetJourneyIOS/PetJourneyIOS/Views/SecondaryViews.swift:4098)

建议：

- Dev 真机环境必须设置：`PETJOURNEY_PUBLIC_BASE_URL=http://192.168.31.237:8000`。
- 更稳的做法：后端返回相对 `media_path`，iOS 用当前 API baseURL 解析媒体地址。
- 图片生成中的状态要明确：`generating/failed/ready`，不要无限 spinner。

## P2 问题

### P2-1：天气和昼夜目前更像文字，不像世界状态

现象：

- 用户没有明显感知黄昏、夜晚、雨天等环境变化。

代码证据：

- `WorldSimulationSnapshot.weather` 只是字符串字段，来自 city weather：[world_simulation.py](/Users/austin/Desktop/petsoul/PetJourneyBackend/app/world_simulation.py:64)
- 目前截图中天气主要出现在卡片文本“多云，27°C...”，没有强绑定地图滤镜、粒子、夜间光线、活动选择。

建议：

- `weather` 结构化：`condition`、`temperature`、`wind`、`humidity`、`is_raining`、`local_sun_phase`。
- 地图层根据 `local_sun_phase/weather.condition` 切换：夜间暗蓝、黄昏暖光、雨天雾化/雨点。
- 活动生成必须受天气约束：雨天减少户外，夜间减少咖啡馆/打卡，飞行中只显示机舱/云层。

### P2-2：主人聊天气泡布局有空白

现象：

- “看看你现在”气泡左侧出现很大的空白。

代码证据：

- owner bubble 使用 `.frame(maxWidth: min(UIScreen.main.bounds.width * 0.72, 310), alignment: .trailing)` 后再加背景，短文本可能被扩展成宽气泡：[CommunicatorViews.swift](/Users/austin/Desktop/petsoul/PetJourneyIOS/PetJourneyIOS/Views/CommunicatorViews.swift:853)

建议：

- 短文本气泡按内容宽度，长文本才限制最大宽度。
- owner row 用 `fixedSize(horizontal: false, vertical: true)` 或外层 maxWidth 控制，不要让 Text frame 本身撑满。

### P2-3：宠物原声没有翻译入口或默认解释

现象：

- “呜汪......汪。汪汪。”用户不知道含义。

代码证据：

- 后端 `JourneyThought` 存了 `animal_text` 和 `translation`，但回忆/通知/部分卡片只展示原声或 raw memory 内容：[agent_engine.py](/Users/austin/Desktop/petsoul/PetJourneyBackend/app/agent_engine.py:1087)、[scheduler.py](/Users/austin/Desktop/petsoul/PetJourneyBackend/app/scheduler.py:192)

建议：

- 原声旁放“翻译”按钮。
- 主动来信默认展示一行翻译摘要，原声作为可展开层。
- 通知正文不要只推原声。

## 推荐修复顺序

### 第一阶段：先止血，解决错乱感

1. `city_position` 改为读 `world_snapshot.current_activity`，不要按 elapsed 单独返回城市。
2. `event_generator.advance()` 在 `world_state.phase == in_transit` 时禁止创建普通明信片。
3. `ensure_seed_moments()` 如果 `world.is_flying`，不要 seed arrival/resting，改 seed 一条“飞行中/信号不稳”的系统动态，且不进入朋友圈。
4. `JourneyViewModel` 增加 `world_state_id/generated_at` 校验，拒绝把不同版本的 status/city/worldSnapshot 混着渲染。
5. Dev 真机配置 `PETJOURNEY_PUBLIC_BASE_URL` 为局域网 IP。
6. 隐藏回忆卡 raw `kind/source/importance`。

### 第二阶段：建立正确模型

1. 新增落库 `journey_clock_states` 或 `world_state_snapshots`。
2. 新增落库 `transport_leg_instances`，旅行创建时一次性决定航班/起降时间/起降机场/航线。
3. 所有内容生成入口都接收 `world_state`，不得自己按 `created_at` 再算城市。
4. 明信片/动态/照片增加 `captured_at`、`delivered_at`、`origin_world_state_id`。
5. 聊天接口增加 `client_message_id` 幂等键。

### 第三阶段：体验增强

1. 飞行视觉：飞机 icon + 宠物头像 + great-circle 航线 + 高空夜色/云层。
2. 天气视觉：雨、夜、黄昏、风，不只显示文字。
3. 跨时区旅程日历：出发地时间和目的地时间分开显示。
4. 原声翻译：默认可读，原声可展开收藏。

## 新的不变量建议

1. 同一屏幕只能展示同一个 `world_state_id` 的数据。
2. `phase=in_transit` 时，不允许生成普通地点照片、普通明信片、普通朋友圈。
3. 所有“此刻位置”必须来自 `WorldStateSnapshot.current_activity/current_transport`。
4. 新宠物起点必须落库，不能由城市数组 index 0 隐式决定。
5. 航班/长途交通一旦开始，时间线实例不能重算到另一个剩余时间。
6. 用户可见文案不得展示 provider/source/reality_level/debug score/internal rule。
7. 客户端重试必须幂等。
8. 媒体 URL 必须能被当前客户端访问，不能在真机返回 `127.0.0.1`。

## 验收用例

1. 新建 20 只宠物，起点不全部是厦门；如果命中厦门，也有可解释来源。
2. 宠物处于飞行中，连续刷新 `status/city_position/world_snapshot/journey_plan/communicator/moments/postcards`，城市、坐标、阶段一致。
3. 飞行中连续 30 分钟不会生成普通咖啡馆明信片、普通朋友圈、普通地点照片。
4. 飞行剩余时间单调递减，不允许从 10 小时跳到 16 分钟，除非航班状态明确变更且有延误/提前说明。
5. 聊天同一 `client_message_id` 重试 10 次，只出现一条主人消息和一轮回复。
6. 真机加载明信片/手账图片，URL 不含 `127.0.0.1`。
7. 回忆列表不出现 `episodic/postcard/agent_turn/scheduler/重要 68` 等内部字段。
8. 搜索全部 iOS 可见文案，不出现“参考真实航班”“真实世界原则”“provider”“source”“scheduler”“agent_turn”等内部词。

## 结语

PetJourney 的方向是对的：飞行、世界状态、通讯延迟、朋友圈、明信片都已经有雏形。但现在缺的是一个强约束的“宠物此刻到底在哪里、能不能说话、能不能拍照、能不能发动态”的状态中心。

先把这个中心立住，后面的天气、航班、手账、通讯器都会自然变稳。否则继续往上叠功能，只会让更多模块各自讲一个看似动人的故事，最后在同一块手机屏幕上互相拆台。
