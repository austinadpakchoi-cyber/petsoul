# PetSoul 网页前端交接（后端契约 0.4.5；下方 0.4.4、0.4.3、0.4.2、0.4.1、0.4.0、0.3.0 及以前的内容保留作历史）

- 编写：后端窗口 `claude-20260922-014933-307b`，2026-09-22。
- 依据：修复后的实际代码、FastAPI 实际注册的路由，以及生成契约 `PetJourneyWeb/src/shared/contracts/generated.ts`（0.3.0：101 个枚举、178 个模型、94 条路由）。
- **0.3.0 更新（同日晚些时候）**：驾考改为“爪爪驾校：主人陪考，宠物拿证”，替换了 0.2.5 的陪练与场景考试接口，前端页面已由本窗口实现（`PetJourneyWeb/src/features/driving_school/`），见 §4.5 与文末附录。
- 文中示例都是真实响应：用 `scripts/seed_web_demo.py` 在本地演示库里跑出来，没有手写。为了篇幅做了截断，截断处写 `…`。演示库全程关闭真实供应商，所以地点名都带“示例·…（演示）”。
- **本文所有能力都没有部署公网，也没有和前端联调。** 公网 `https://petsoul.games` 仍是契约 0.2.1。

## ★ 0.4.5（2026-09-23 上午）：主人可以主动让 TA 拍一张，**并且在网页上看得到结果**

`contract_version` / `backend_version` → **0.4.5**；路由 118 → **120**，枚举 111，模型 **213**。
新增三条路由，都在 `/pets/{pet_id}` 下。

### 这是什么

之前只有"TA 到了咖啡馆自己拍一张"（行程里的到访活动触发）。现在主人可以**主动说「给我拍一张」**，
覆盖三个到访触发够不着的场景：

| `scene` | 什么时候能用 |
|---|---|
| `home` | TA **此刻真的在家**，而且不是"正准备出门"那种状态 |
| `train` | TA **此刻真的在列车段上**（当前行程段的承运方式是火车） |
| `flight_adventure` | 主人明确选的**虚构飞行主题**——不写世界事件、不进旅程历史、不扣旅费、不发勋章 |

**`cafe` 不在这里**：到咖啡馆拍照仍走原来的到访活动，那条路没变，两条并存。

### 三条路由

| 路由 | 说明 |
|---|---|
| `POST /pets/{pet_id}/photo-request` | 下命令。要 `X-CSRF-Token` 与 `Idempotency-Key`，需要"照顾"权限 |
| `GET /pets/{pet_id}/photo-requests` | 看结果列表（新的在前，最多 50 条）。**纯读**，不会驱动任务也不会发起调用 |
| `POST /pets/{pet_id}/photo-requests/{request_id}/retry-image` | 没画成 / 结果没确认时重画。要 `X-CSRF-Token` |

**请求体**：`{ "scene": "home" | "train" | "flight_adventure", "narrative": "daily_life" | "fictional_adventure" }`
`flight_adventure` **必须**显式传 `fictional_adventure`，默认的 `daily_life` 会 **422**；反过来日常场景传虚构也是 422。

**受理响应**（`PhotoRequestResult`）：`request_id`（稳定标识，拿它去查结果或重画）、`task_id`、
`scene`、`narrative`、`fictional`、`captured_at`、`place`、`city`。

### 前端最容易踩的四个点

1. **状态不成立是 409，和「画不出来」是两回事。**
   409 ＝ TA 现在不在家 / 不在列车上，**命令根本不成立，连记录都不写**，`details` 里有 `activity` 与 `leg_mode`。
   而"命令成立了、但画不出来"会变成列表里的 `failed` / `unknown`，**两者不要合并成一个提示**。
2. **不要拿重发 POST 当状态轮询。** 同一个 `Idempotency-Key` 重发会原样拿回**第一次**的受理结果
   （同一个 `request_id`、同一个 `task_id`、同一个 `captured_at`）。要看画得怎么样，去读列表。
3. **`photo_status` 有四态，`unknown` 必须单独显示。**
   `processing`＝还在画；`ready`＝画好了（这时 `image_url` 才非空）；`failed`＝确定没画成；
   **`unknown`＝结果还没确认**（请求可能已经发出、甚至已经计费）——页面要写"还没确认"并给重画入口，
   **不能写成"没画成"**，那会让主人以为什么都没发生。`can_retry` 在 `failed` / `unknown` 时为真。
4. **重画的第二次点击是 200 不是 404。** 已经在画或已经画好时再点，回 200 ＋ 当前状态，不会再发起付费尝试；
   只有"这条内容找不到"或"明确不能重试"才是 404。跨宠物、跨家庭拿别人的 `request_id` 也是 **404**（不泄露存在与否）。

### ⚠ `task_id` 为 `null` 时前端要怎么做（真实浏览器跑出来的情形）

受理返回 **200 但 `task_id` 是 `null`**，意思很明确：**这次没有排出任何生成任务**。

已在关闭供应商的隔离环境里用真实 Chrome 验过：这时 `GET /pets/{pet_id}/photo-requests` **返回空列表**，
额度预占与供应商用量**都是 0**，游戏内旅费**一分没动**。

所以前端**不要**做这三件事：

1. **不要显示「正在画」** —— 没有任务在画，那是个不存在的状态；
2. **不要轮询列表等它出现** —— 列表是空的，等多久都不会有；
3. **不要编一个更具体的原因** —— 后端此刻只知道"没排出来"，可能是**供应商不可用**，也可能是**这个环境没授权生图**。
   照实说（例如「现在拍不了照片」）比猜一个原因好；**别写成"失败了"或"额度用完了"**，那都是没有依据的。

判断很简单：`task_id` 有值才有后续可查；为 `null` 就到此为止，这一次请求没有产生任何可跟踪的东西。

### 现在还画不出来的情况（**不是前端的问题**）

照片导演要求参考照**标注来源**，来源说不清就 hold（宁可不画，也不给来源不明的图冒名）。
当前会 hold 的有两类：**领养的原创伙伴**（预置素材，既不是主人原照也不是我们生成的基准照），
以及**登记成"其他"物种**的宠物。这两类要不要出图是产品判断，还没定。
这时列表里看到的是 `failed` / `unknown`，前端照常显示并给重画入口即可。

## ★ 0.4.4（2026-09-23 上午）：运维接口多一个字段，**玩家页面不受影响**

`backend_version` → **`web-mvp-0.4.4`**。**路由、模型、枚举的数量都没变（117 / 210 / 109）**，
唯一的变化是 `GET /ops/runtime/{pet_id}` 的响应里多了一个**可选**字段：

| 字段 | 含义 |
|---|---|
| `next_review_at` | 上一次决定时写下的「到这个时刻再重新考虑」。可能为 `null`。 |

**和 `next_check_at` 不是一回事**，别混用：
- `next_check_at` —— **此刻**按当前事实算出来的下次查看时间，每次请求现算，不落库；
- `next_review_at` —— **当时那次决定**留下的有效期（比如「先留在家，两小时后再看」），决定时落库，之后不随请求变。

这条接口**只给本机或带管理令牌的请求**（运维排查用，回答「TA 为什么这么安静」），
不在玩家页面上，**前端不需要任何改动**。没做过决定时该字段是 `null`，不是缺键。

### ⚠ 同一批里补上的一笔历史欠账：`contract_version` 终于跟上了

**这一项前端需要注意**：`/meta` 返回的 `contract_version` 之前一直是 **`0.4.1`**，但契约其实已经改过三次——

| 版本 | 契约上实际改了什么 |
|---|---|
| 0.4.2 | `PhotoStatus` **新增枚举值** `unknown` |
| 0.4.3 | **新增两条路由**（收藏、攻略的 retry-image），115 → 117 |
| 0.4.4 | `PetRuntimeStatus` **新增可选字段** `next_review_at` |

也就是说，`contract_version` 这个常量一直停在 0.4.1 没人动，而生成产物（`generated.ts`）其实是跟着改的。
现在把它对齐到 **`0.4.4`**，并重新生成了一次契约产物。

`PetJourneyWeb/src/shared/contracts/generated.ts` 的实际变化**只有 6 行、3 处**：
`WEB_CONTRACT_VERSION` 改成 `"0.4.4"`；`PetRuntimeStatus` 多一个 `next_review_at`；
`PetRuntimeStatusInput` 的可选列表里多一个 `next_review_at`。**没有删改任何既有字段或路由。**

数量仍是 **109 枚举 / 210 模型 / 117 路由**（`npm run contract:check` 与后端自查两边一致）。

**前端要做的**：如果哪里硬编码了 `contract_version === "0.4.1"`，改成 `0.4.4`；
其余不用动——页面用到的字段一个都没变。

## ★ 0.4.1 更新（2026-09-23 凌晨）：到期结算同一事务、事件 outbox、读接口纯读、领取围栏、两条后台线

> 编写：后端窗口 `claude-20260922-014933-307b`（package I，总集成，并行开发第 1–8 批）。依据：实际代码与生成契约（0.4.1：109 个枚举、210 个模型、115 条路由）。
> **只在本地；没有部署、没有和前端页面联调。** 本地真实联调环境 18763 已换上这版代码（自然时间验收的打工部分已判定完毕）。
> 只重新生成了 `src/shared/contracts/generated.ts`，前端 typecheck 与 73 项测试通过；没有改任何页面。

### A. 兼容性
- 全部是 `x-additive` 字段（TS 里可选），没有删字段、没有新增枚举值、没有改路由。0.4.0 的页面不改也能用。

### B. 新字段
| 位置 | 字段 | 用途 |
|---|---|---|
| `MessageSummary` | `source_event_id` | 由世界事件产生的来信（出发、到站、到店、收工、回家、合影……）指向那个事件：`<journey_id>:<事件键>`。同一事件全家只有一条；可以据此把地图、时间线与来信连起来。其他消息为空（私聊回复、主动消息不下发内部去重键）。 |
| `MessageSummary` | `reply_to` | TA 的这条回复针对的家人消息编号：可以把“排队后补上的回复”挂在原消息下面。 |
| `LedgerEntry`（银行卡流水） | `ref_kind` / `ref_id` | 这笔钱属于哪项业务：`journey`（旅费、工资、退款 → `journey_id`）/ `order`（集市订单）/ `home`（家园商店、欢迎礼）。认不出的为空，不猜。可以从流水跳到对应行程或工作记录。 |
| 新路由 `GET /ops/runtime/{pet_id}`（运维，只给本机或管理令牌） | `PetRuntimeStatus` | 一只宠物此刻在做什么、能不能打断、下次什么时候看、有哪些到期事项、为什么安静、上次是谁做的决定。玩家界面不用，返回里没有正文与 DNA 原文。 |
| `OpsStatus`（运维，只给本机或管理令牌） | `tasks`、`outbox[]`、`cognition`、`world.due_lag_seconds` | 后台任务健康、世界事件各下游的投递情况（pending / delivered / dead_letter / 最老等待秒数）、认知线状态，以及“最老一件已到期还没登记的事实等了多少秒”。玩家界面不用。 |

### C. 行为变化（前端需要知道）
| 变化 | 以前 | 现在 |
|---|---|---|
| 攻略手账（远行出发时 TA 写的攻略） | 出发请求里同步调用模型写好，`POST /journey/depart` 返回前就有 | **由后台任务写**（一般 30 秒内）；出发请求不再等模型。页面在出发后短时间内 `GET /guides` 可能还是空的，轮询或稍后刷新即可；模型不可用时仍会写模板攻略 |
| 旅途中遇到朋友、相遇的新鲜事 | 读取页面时同步处理 | 由后台任务处理（可能调模型）；朋友列表与“遇到了……”的新鲜事会晚一轮出现（一般 30 秒内） |
| 家庭来信（出发、到站、收工、回家……） | 与事件一起即时写入 | 仍然即时：事件、工资与行程完成在同一个事务里成立后，立刻投递家庭来信、动态、收藏与证件；某个下游暂时失败只让它自己稍后重试（30 秒、2 分钟、10 分钟……），**工资与到站不会因此撤销，也不会重复** |
| 排队中的回复（TA 睡着、在路上时收到的消息） | 后台处理中进程崩溃可能永远卡在“等待回复” | 领取有期限，过期后由别的进程接手，**恰好回复一次**；如果这位家人已经被移出家庭，就不再回复 |
| 生图（合影、明信片、手账页、冒险插画） | 被接管的旧任务晚到的结果也会写进来 | 结果只由当前有效的领取提交（与任务完成同一个事务）；“重画”按任务队列规则重排，不清零次数 |
| 读接口（`/home`、`/journey/map`、`/visits/{id}`、`/timeline`、`/jobs`、`/communicator/{pet}/messages`、`/credentials`、`/collection`、`/circle/feed`） | 顺手补齐到期事件：读一次页面可能就发工资、发来信、写动态 | **纯读**：只按服务器时间投影画面，不推进世界、不调模型与地图（只记已读位置）。结算由任务进程或命令（出发、店内动作等）完成 |
| 还没结算到的时候 | 看不出来 | `HomeSnapshot.catching_up` / `JourneyMapSnapshot.catching_up = true`：位置照常按时间显示（例如已经过了回家时间就显示在家），工资与来信稍后出现。**不要显示成出错**，也不要据此自己推进什么 |
| 后台 | 一条线依次做完所有事 | 两条线各自跑、各有租约：世界线（到期结算、确定性下游、出门前复核、规则生活、驾校）与认知线（攻略与相遇的表达、到点回复、主动消息）。模型卡住只影响认知线 |
| 同一个 `Idempotency-Key` 重试 | 上一次请求在写回结果前中断，这个键就永远 409 “处理中” | 占位超过 5 分钟没写回结果，下一次同键同请求会接手重跑；领域侧的唯一键保证不会变成两份（重复出发仍然返回 409 `already_traveling`，只扣一次钱） |
| 家人被移出家庭后，后台还在生成的内容 | 可能仍然发给他 | 发布前在同一个事务里复核成员关系：排队中的回复记为 suppressed，主动消息与回应便笺直接不发布 |

### D. 前端要做的小改动（0.4.1）
1. 读接口不再“读一次推一次”：需要马上看到结果的操作（出发、店内动作）仍是命令，返回即生效；其余状态按轮询刷新（建议 15–30 秒一次，与后台一轮同量级）。
2. `catching_up = true` 时显示“世界正在更新”一类的轻提示，不要报错、不要重复请求。
3. 家庭来信可以用 `source_event_id` 与地图、时间线互相跳转；银行卡流水可以用 `ref_kind` / `ref_id` 跳到对应行程。


### E. 还没做的（后续批次，届时再更新本节）
- 模型自主决策默认关闭（`PETJOURNEY_WEB_BRAIN_MODE=off`）：打开前不会有任何自主的付费调用，玩家可见行为也不变。打开后 TA 的出门选择会由模型在规则给出的可行项里做，家庭必须先开“模型回信”。
  （第 8 批已把这一步接进认知线：只对心跳说“需要想一想”的宠物走一次决策，一轮最多 5 只；`off` 时整步跳过。打开前先看 `deploy/web/REAL-EXPERIENCE-DEPLOY.md` §2.1。）
- 心跳策略目前只做 shadow（只评估、只记录运行状态），世界仍由现有规则推进。
- 真实模型的自主决策**整条链已经验通**：2026-09-23 03:10 / 03:13 用 `scripts/verify_brain_live.py --yes` 分别跑了 shadow 与 live
  （各在一次性临时库里，各 1 次 DeepSeek 调用）。shadow：`composed_by=model`、只记录不执行；live：`composed_by=model`、
  `status=departed`，模型选的 `local:stroll` 真的变成了行程 `jn-28f8642b2231`，运行记录写下 `last_decision_by=model`。
  证据 `evidence/24-brain-real-model.json` 与 `evidence/27-brain-real-model-live.json`。正式环境仍默认 `off`，打开前先确认预算与家庭授权。

### I. 0.4.3：收藏与攻略也有了"重画"入口（新增两条路由）

`backend_version` → **`web-mvp-0.4.3`**；路由数 115 → **117**，枚举与模型数量不变（109 / 210）。

| 新路由 | 说明 |
|---|---|
| `POST /collection/{pet_id}/items/{item_id}/retry-image` | 明信片没画成（或结果没确认）时重画，返回该宠物的收藏列表 |
| `POST /guides/{pet_id}/{guide_id}/retry-image` | 手账图没画成（或结果没确认）时重画，返回该宠物的攻略列表 |

两条都要 `X-CSRF-Token`（不带是 403），都需要家庭成员且有"照顾"权限；不是这家的人一律 **404**（不泄露存在与否）。
**什么时候 404、什么时候 200，规则是一条**：404 只留给"根本找不到这件东西"（不存在、不属于这只宠物、这位家人看不到），
以及后端明确判定"这个任务不能重试"（已作废、任务号对不上）。
**对象在、只是这一刻不能重画（正在画 / 已经画好）→ 200 并回当前状态**，不是 404。

所以：**连点两次的第二次是 200**（状态仍是"正在画"），重画一张已经画好的图也是 200（状态仍是 ready）——
两种都**不会**再发起一次付费尝试。前端据此写：200 就按返回的 `image_status` / `photo_status` 刷新显示，
不要把 200 一律当成"新的一次重画已开始"；404 才提示"这条内容找不到了"。

**前端现在可以展示收藏与攻略的"重画"按钮了。** 在这之前只有通讯器的 `retry-photo` 一个入口，
收藏与攻略上的按钮点不到任何接口——所以之前的交接里写的是"先别展示"，这条到此解除。

配合 §H 的四态一起用：`failed`（确定没画成）与 `unknown`（结果还没确认）都给"重画"入口，
但文案要分开——`unknown` 说"还没确认"，不要说"没画成"。

### H. 0.4.2（唯一的对外变化）：照片多了一个"还没确认"的状态

`backend_version` 从 `web-mvp-0.4.1` 变成 **`web-mvp-0.4.2`**。这一版对外只改了一处，但**它是枚举新增值，不是可选字段，前端必须处理**：

`PhotoStatus` 增加成员 `unknown`（`processing` / `ready` / `failed` / **`unknown`**）。
出现在：`MessageSummary.photo_status`、收藏项与攻略的 `image_status`。

| 状态 | 含义 | 页面怎么说 |
|---|---|---|
| `processing` | 还在画 | "正在画…" |
| `ready` | 画好了 | 显示图片 |
| `failed` | **确定没画成**（没配置、到了每日上限、被供应商当场拒绝） | "没画成"，给"重画" |
| `unknown` | **结果还没确认**：请求发出去了、可能已经受理并计费，但响应没拿回来（超时、传输中断，或响应回来后解析失败） | **"还没确认"**，给"重画"；**不要写成"没画成"** |

为什么要分开：`unknown` 那次很可能已经产生了费用。把它说成"没画成"，主人会以为什么都没发生，
点一次"重画"就又付一次钱。后端对这两种的处理也不同——`failed` 可以自动重试，`unknown` **不自动重发**，只等主人显式重画。

前端要做的：凡是 `switch (photo_status)` / 三态判断的地方都补上 `unknown` 分支；
兜底分支不要落进"没画成"。TypeScript 侧 `PhotoStatusValues` 已经包含它（`npx tsc --noEmit` 当前通过，因为没有穷尽性检查的地方）。

### G. 0.4.1 收口（第 9–11 批）：现在到底开了什么、还差什么

> 补充于 2026-09-23 05:0x +0800。**契约仍是 0.4.1，没有新增或改动任何路由、模型、枚举**，这一节只讲"实际生效的行为"。

#### G.1 两个开关的组合，实际效果是什么

| `PETJOURNEY_WEB_HEARTBEAT_MODE` | `PETJOURNEY_WEB_BRAIN_MODE` | 世界怎么动 | 有没有模型调用 | 运维能看到什么 |
|---|---|---|---|---|
| `shadow`（默认） | `off`（默认） | 完全按现有规则生活（世界线的 `life`） | **一次都没有** | `/ops/runtime/{pet}` 有 `heartbeat_action`、`silence_reason`、`next_check_at`；`last_decision_by` 为 `rule` 或空 |
| `shadow` | `shadow` | 仍按规则生活，不受模型影响 | **有**（每次决策 1 次，真实付费）；只记录"模型会选什么"，不出门、不发消息 | 多出 `brain shadow pet=… by=model choice=…` 日志；`/ops/status` 的 `llm.calls_today` 会涨 |
| `shadow` | `live` | 心跳说"该想一想"的宠物由**模型**在规则给出的可行项里选，复核通过后真的出发 | **有** | `last_decision_by=model`；被挡下时 `silence_reason=brain:<原因>` |
| 其他值（＝关闭心跳投影） | 任意 | 与上面同列一致（认知线自己会评估一次，不依赖 shadow） | 同上 | `next_check_at` / `silence_reason` / `last_evaluated_at` 不再更新，运维可见性下降 |

- 默认组合（`shadow` + `off`）下，**玩家可见行为与 0.4.0 完全一致**，前端不需要任何改动。
- 打开 `live` 还有两道前提：家庭在设置里开了"模型回信"，并且对话模型供应商可用。任一不满足就退回规则生活并标 `rule_fallback`。
- 额度：每只宠物每个 UTC 记账日 `PETJOURNEY_WEB_BRAIN_DAILY_PER_PET`（默认 12）次，且不超过供应商本身的每日上限（llm 默认 300）。

#### G.2 已经接入并有反例守着的能力

| 能力 | 默认 | 守着它的反例 |
|---|---|---|
| 到期结算、世界事件、行程完成、outbox 同一事务；下游各自重试 | 开 | `test_web_settlement_chain`（9） |
| 读接口纯读（不推进世界、不调模型与地图） | 开 | `test_web_integration_fences`、Q-C6 |
| 旧任务的迟到结果作废（生图、待回复） | 开 | `test_web_integration_fences`、Q-C2 |
| 同一个 `Idempotency-Key` 始终对应同一次出发（**原行程结束后重试也不会变成第二趟**） | 开 | `test_web_idempotency_recovery`（3）、Q-C3a / C3c |
| 被接手的旧执行者不能用过期结果覆盖回执 | 开 | `test_web_idempotency_recovery`、Q-C3d（已 PASS） |
| 出门前按作息复核改签／取消退款 | 开 | `test_web_predeparture_review`（3）；真实环境那趟见验收 E2 |
| 生图按**实际发出的调用次数**结算；超时记"结果不明"且不自动重试 | 开 | `test_web_illustration_settlement`（5） |
| 一轮决策的逻辑编号持久化（重试／重启／跨分钟复用） | 随 brain 开关 | `test_web_decision_operation_id`（4） |
| 提交前按此刻复核（截止、授权撤回、语义版本、机会有效期） | 随 brain 开关 | `test_web_brain_commit_fence`（6） |
| 认知线按游标轮转、想不成会退避、不与规则生活抢同一只宠物 | 随 brain 开关 | `test_web_brain_round_fairness`（6） |
| 进程租约管到最终写事务（被接手后旧进程写不进去） | 开 | `test_web_lease_commit_fence`（4） |

#### G.3 前端可见的一处行为变化（第 11 批）

`POST /journey/depart` 用**同一个 `Idempotency-Key` 重试**时：以前在 TA 还在路上的情况下会返回 409 `already_traveling`，
现在返回 **200 并重放原来那一趟**（`journey_id` 不变）。换一个新的键、而 TA 确实在路上，仍然是 409 `already_traveling`。
对正常使用没有影响；网络重试的体验更好——重试不会再看到一个"冲突"错误。

#### G.4 仍然需要配置或证据的

- 模型自主决策默认关着。真实模型已经验过一次 shadow、一次 live（见 §E），但那是一次性临时库里的单次验证，
  **不等于长期自主性已经证明**；正式打开前请按部署文档 §2.1 先估预算。
- 心跳目前只做 `shadow`（只评估、只记录）。"由心跳驱动世界"没有做，也不在 0.4.1 的范围里。
- 真实环境的自然时间验收项 E2（出门前复核）到点由任务进程判定；**那份证据对应的是当时运行的代码版本**，
  第 9–11 批之后的代码没有在真实环境重跑过，不能直接拿旧证据当新版本的证明。
- 独立验收（Q）对第 11 批的复验还没做。I 这边跑 Q 的合同是 15 条全 PASS（整体 PASS、退出码 0），但那不是 Q 的独立结论。

### F. 第 7–8 批（前端无需改动）
都在后端内部，契约没有任何变化：语义版本代数在出发/结算/接待更正/成员变动的同一事务里递增（用于后台复核，不下发前端）；
认知线新增 `brain_life` 一步；`GET /ops/runtime/{pet_id}` 对不存在的宠物返回 404（以前会假装“在家”）。

## ★ 0.4.0 更新（2026-09-22 晚）：真实新用户、家庭共同照顾与多宠物、访客与待领养居民、真实交通

> 编写：后端窗口 `claude-20260922-014933-307b`。依据：实际代码、生成契约（0.4.0：109 个枚举、207 个模型、114 条路由）与本地真实联调环境实跑（证据见 `docs/coordination/BACKEND-REAL-EXPERIENCE-ACCEPTANCE.md`）。
> **只在本地；没有部署，没有和前端页面联调。** 前端页面本窗口没有改（`src/features/**` 不属于本窗口）；只重新生成了 `src/shared/contracts/generated.ts`，前端 typecheck / 73 项测试 / build 都通过。

### A. 旧页面照样能用的部分（兼容）

- 只照顾一只宠物的账号：所有接口不带 `pet_id` 也照旧工作（默认那一只）。
- 新增字段都是 `x-additive`（TS 里是可选）；原有枚举 **没有** 增加新值，只有 `PlaceProvider` 新增了 `world`（星球内的地方）。
- `time_basis` 仍只有四个值。星球内的路程记为 `routed_estimate`（“估算”），精确来源看新增的 `time_source`（`verified_timetable / operator_rule / routed_estimate / world_rule / demo_fixture`）与 `reference.source_label`。现有 `LegSheet` 的“预计车程”标签不会误导；前端方便时可以按 `time_source` 细分文案（例如 `world_rule` 显示“星球内的路程”）。

### B. 行为变化（前端必须知道）

| 变化 | 以前 | 现在 |
|---|---|---|
| 照顾不止一只宠物时不带 `pet_id` | — | `409 CONFLICT`，`details.reason = "pet_required"`，`details.pets = [{pet_id, household_id}]`；页面应让用户选一只，之后每个请求都带 `?pet_id=` |
| 指明别人家的宠物 | 有时返回 409 PET_NOT_ACTIVATED | 一律 `404 NOT_FOUND`（不是这个家庭的成员；不暴露是否存在） |
| 角色不够 | — | `403 FORBIDDEN`：`admin_required`（家庭设置、成员、邀请、给家庭添宠物、搬家）或 `spend_not_allowed`（家庭关闭了“共同照顾者可用宠物账户”时替 TA 出发） |
| 注册 | 注册后必须马上建宠物 | 可以只注册；`POST /auth/register` 可带 `entry`（见 C.1），`GET /onboarding` 在 `needs_companion` 时带回 `entry` 等用户确认 |
| `POST /pets` 不带 `household_id` 而这个账号已经建过家庭 | 409 already_has_companion | `409 CONFLICT`，`reason = "household_exists"`，`details.household_id`；页面应改成“加进你的家”（带上 `household_id` 再提交） |
| 正式环境（real-local / 部署）的出发站 | 有演示线路 `harbour_cafe / tokyo_flight` | **没有演示线路**；`macau_ferry` 变成真实港澳一日行；选项多了 `available / unavailable_reason / reference_note` |
| TA 在睡觉时家人点“出发”去附近 | 照样出门 | `409 CONFLICT`，`reason = "pet_asleep"`：按 DNA 作息 TA 在睡觉，不叫醒；可以先 `POST /journey/suggest` 留建议，TA 醒了自己决定 |
| 远行的出门时间 | 点了就出门 | 从开船时间反推：可能要过一会儿（甚至第二天早上）才出门；这段时间 `presence = at_home`，通讯器里 TA 会说“在家收拾东西，HH:MM 出门去……”，地图快照的交通段 `phase = scheduled` |
| 现实资料拿不到 | 静默退回演示线路 | `409 CONFLICT`，`reason = "transport_unavailable"`，`details.unavailable_reason` ∈ `map_unavailable / route_unavailable / place_unavailable / no_sailing / timetable_needs_recheck / not_supported_here`；不扣钱、不生成行程 |
| 地图不可用时的附近活动 | “示例·…（演示）” | 散步、喝一杯、打工去**星球内的地方**（`place.provider = world`，署名“星球内的地方：世界规则设定……”）；进城、自驾不成立（`available=false`） |
| 寻味推荐（`POST /food/recommendations`） | 返回演示小样本 | 正式环境 `503 NOT_CONFIGURED`（`details.capability = "food.recommendations"`）：没有获准分析的真实菜单/评论资料，演示小样本只在演示环境给；页面按能力不可用处理 |
| 入住时选居住环境 | 八类都能选 | 新家只开放已接通真实交通与地点的片区（海边→香港西贡、城市→香港中环）；`GET /home/place` 的 `options[].open` 标出来；选未开放的 → `422 VALIDATION_FAILED`，`reason = "habitat_not_supported"`。已有的家不动 |
| 通讯器 | 只有主人与 TA | 每条消息多了 `channel`：`private`（你和 TA 的私聊，别的家人看不到）/ `family`（家庭频道：出发、到站、到店、合影、回家、打工、明信片、攻略、证件、驾校、看家守菜、遇到朋友——全家看到同一条） |
| DNA | 一份，谁保存谁覆盖 | 共用部分带 `version`；`PUT /pets/{id}/dna?expected_version=N`，家人在这之后改过 → `409`，`reason = "dna_version_conflict"`，`details.current_version`；`owner_title` 和 `shared_memories` 是**每位家人自己的一份**（`personal_fields`），不会被别的家人覆盖 |
| 设置 | 全部个人 | 个人：`model_replies`、`pet_messages`（TA 主动找我私聊）、`timezone`；家庭（管理员）：`public_posts`、`generated_photos`、宠物 `profile_visibility`；简介 `bio` 家人都能改 |

### C. 新接口

**C.1 入口与访客（不登录）**

| 接口 | 说明 |
|---|---|
| `GET /public/world` | 访客首页：`entries`（先逛逛 / 带我的宠物来 / 认识新伙伴 / 家人邀请）、`residents`（还在驿站生活、可领养的居民此刻在哪、在做什么、最近公开动态）、`recent_posts`（全星球最近公开动态）；缓存 30 秒，同一来源每分钟 120 次 |
| `GET /public/residents`、`GET /public/pets/{pet_id}`、`GET /public/pets/{pet_id}/posts` | 居民列表、公开主页（居民或主页公开的宠物；其余 404）、公开动态 |
| `GET /public/media/postcards/{photo_id}`、`GET /public/media/pets/{pet_id}/photo` | 访客可看的图片（已公开的明信片、主页公开的头像） |
| `POST /auth/register` 的 `entry` | `{kind: "browse" \| "own_pet" \| "adopt" \| "invite", pet_id?, invite_token?}`；只记下来，不会自动领养或加入 |
| `GET /onboarding` 的 `entry` | `pending_adoption {pet_id, name, species, available}`（已被别人领走时 `available=false`）/ `pending_invite`（邀请预览）；用户确认后调领养或接受邀请，入口自动清掉 |

**C.2 家庭**

| 接口 | 权限 | 说明 |
|---|---|---|
| `GET /households` | 登录 | 我在的家庭与每家宠物（入住进度、此刻位置） |
| `GET /households/{id}` | 成员 | 成员（角色、是不是你）、设置、你的权限 `your_permissions` |
| `PATCH /households/{id}/settings` | 管理员 | `name`、`caregivers_can_spend`、`generated_photos`、`pet_messages`（家庭频道新鲜事）、`public_posts` |
| `PUT /households/{id}/members/{user_id}/role` | 管理员 | `admin / caregiver`；最后一位管理员不能降级（409 `last_admin`） |
| `DELETE /households/{id}/members/{user_id}` | 管理员；或自己退出 | 立即生效；最后一位管理员不能退出（409 `last_admin`） |
| `POST /households/{id}/invites` | 管理员 | 返回 `token` 与 `join_path=/join?invite=<token>`（**令牌只返回这一次**，服务端只存摘要）；`ttl_hours` 1–336 |
| `GET /households/{id}/invites`、`DELETE /households/{id}/invites/{invite_id}` | 管理员 | 列表、撤销 |
| `POST /invites/preview` `{token}` | 不需要登录 | 谁邀请、家里有哪几只、角色、是否过期、你是否已是成员 |
| `POST /invites/accept` `{token}` | 登录 | 同一人重复点返回同一结果；被用过 409 `invite_used`；过期 409 `invite_expired`；撤销 404 |
| `GET/PUT /pets/{pet_id}/relationship` | 成员 | TA 怎么称呼你、你们的关系称呼（只属于你和 TA；不带权限） |
| `POST /pets` 表单字段 `household_id`、`POST /adoption/adopt` 的 `household_id` | 管理员 | 把新宠物加进已有的家 |

**C.3 交通与运行**

| 接口 | 说明 |
|---|---|
| `GET /journey/plan?destination_key=&pet_id=` | 出发前看一眼真实行程：出门时间、每段起止、来源说明、参考班次编号、动物世界承运人、现实参考票价（港币，与星币无关）、到访地点；**不扣钱、不生成行程、不分配编号** |
| `GET /ops/status` | 运行状态（只给本机或带 `X-Admin-Token`）：环境、数据、供应商“已配置/已验证/失败”、世界任务进程与租约、能力、前端该怎么连。前端页面不需要调用 |

### D. 需要前端做的事（按优先级，页面归属仍由用户分配）

1. **宠物切换**：`HomeSnapshot.pets` 列出家里每一只，做标签切换；之后所有宠物相关请求带 `?pet_id=`。遇到 `pet_required` 时弹出选择。
2. **访客首页与三个入口**：`/public/world`；选中的伙伴在注册时作为 `entry` 带上，登录后在 `onboarding.entry` 里恢复并请用户确认。
3. **邀请直达页**：`/join?invite=<token>` → `POST /invites/preview` → 注册/登录（注册时带 `entry: {kind:"invite", invite_token}`）→ 用户点确认 `POST /invites/accept`。令牌不要写进日志或埋点。
4. **家庭页**：成员、角色、邀请、移除/退出、家庭设置；称呼页（relationship）。
5. **通讯器**：按 `channel` 区分私聊与家庭频道。
6. **出发站**：显示 `available=false` 的原因；远行先调 `/journey/plan` 给家人看计划与来源；出门前的“在家收拾”状态。
7. **DNA 页**：带上 `version` 保存，处理 `dna_version_conflict`；标出 `personal_fields` 是“你自己的一份”。
8. **居住环境**：按 `options[].open` 置灰未开放的类型。

### E. 本地环境

| 实例 | 端口 | 数据 | 用途 |
|---|---|---|---|
| 真实联调（本窗口，real-local） | 127.0.0.1:18763 | `PetJourneyBackend/data/web-real-acceptance/`（git 忽略） | 真实供应商、无演示线路、WAL、独立任务进程。启动/状态/停止：仓库根目录 `python scripts/real_integration.py start / status / stop` |
| 前端连真实联调 | 5290（建议） | — | `cd PetJourneyWeb && PETSOUL_DEV_API_TARGET=http://127.0.0.1:18763 npx vite --mode live --port 5290`（live 模式；fixture 模式不连后端） |
| 本窗口旧验证环境 | 127.0.0.1:18761 | `data/web-mvp-claude/` | 仍是 0.3.0 代码；下次重启时自动应用 0.4.0 迁移（只增不删） |
| mock / 演示库 | 18761 / 18762 | `data/web-dev/`、`data/web-demo/` | 演示库要看演示线路时，设 `PETJOURNEY_WEB_DEMO_CATALOG=1`（演示环境专用） |

### F. 还没有的（不要在页面上写成可用）

- 除港澳一日行外的真实远行（东京等）：没有已核验时刻表，正式环境不提供；
- 实时船况、延误与改签：没有实时动态来源；只按已核验船期；
- 家人直接点“出发”仍然可以替 TA 出发（MVP 遗留，受“可花费”权限约束）；现在会看作息（睡着不叫醒、远行排在 TA 醒着的时候），但按“主人只建议”的方向最终应改成建议，需要前端配合再收紧；
- 邀请与家庭页面、访客页面、宠物切换：后端已有，页面未做。


## 0. 状态口径

| 口径 | 含义 |
|---|---|
| 后端已实现 | 代码与接口存在 |
| 已验证 | 有自动化测试覆盖；标“本地实跑”的，另外在本地后端或演示库里走通过 |
| 待前端联调 | 前端页面还没接这个接口，没有做过端到端验收 |
| 尚未实现 | 后端没有，不能在页面上写成可用 |
| 已上线 | 没有任何一项 |

## 1. 版本、启动与地址

### 1.1 版本

| 项 | 本地（本窗口代码） | 公网 petsoul.games |
|---|---|---|
| `GET /api/v1/web/meta` → `contract_version` | **0.3.0** | 0.2.1（c84a 核查于 2026-09-22 17:2x 读取） |
| `backend_version` | **web-mvp-0.3.0**（和契约一起递增） | web-mvp-0.2.0 |
| 能力目录条数 | 57 | 47 |
| 证件、爪爪驾校、DNA 行为倾向、打工记录、时间线、朋友、攻略手账资料 | 有 | 没有 |

前端可以用 `GET /meta` 里的 `contract_version` 判断连上的是不是新后端。能力是否可用看 `capabilities[].status`：`available` 可用，`not_implemented`/`not_configured`/`disabled` 表示不可用。

### 1.2 生成契约（唯一来源）

- 前端类型：`PetJourneyWeb/src/shared/contracts/generated.ts`
- 路由一览（方法、路径、登录、CSRF、幂等键）：`docs/contracts/generated/WEB-ROUTES.md`
- JSON Schema：`docs/contracts/generated/web-contract.schema.json`
- 重新生成：在仓库根目录运行 `python scripts/gen_web_contract.py`；门禁运行 `--check`。只有后端窗口改 schema，前端不要手改生成物。
- 标了 `x-additive` 的追加字段，在 TS 里是可选属性（`?:`）。

### 1.3 本地后端启动

| 用途 | 命令（在 `PetJourneyWeb/` 下） | 说明 |
|---|---|---|
| mock 开发后端 | `node scripts/dev-backend.mjs` | 127.0.0.1:18761，数据在 `PetJourneyBackend/data/web-dev/`；所有供应商都是 mock，不读任何密钥 |
| 演示库（推荐联调用） | 先在仓库根目录运行 `python scripts/seed_web_demo.py`，再 `PETSOUL_DEV_DATA_DIR=../PetJourneyBackend/data/web-demo PETSOUL_DEV_BACKEND_PORT=18762 node scripts/dev-backend.mjs` | 127.0.0.1:18762；已经有“两天的生活”，见第 7 节 |
| 真实供应商 | `PETSOUL_DEV_PROVIDERS=1 node scripts/dev-backend.mjs` | 读 git 忽略的 `PetJourneyBackend/data/secrets/web-providers.env`；**会产生 DeepSeek、高德、Seedream 付费调用**，需要用户授权 |

- 前端连后端：设 `VITE_PETSOUL_DATA_MODE=live`、`VITE_PETSOUL_API_BASE=/api/v1/web`，由 Vite 代理到上面的端口。fixture 模式不连后端。
- 本窗口当前运行的实例：127.0.0.1:18761，数据在 `data/web-mvp-claude/`，**开启了真实供应商**，是本窗口的验证环境。前端联调请另开 18762 演示库或 mock 实例，不要用它，也不要停它。
- 世界定时器每 30 秒推进一次：旅程事件、到点回复、主动消息、驾校（作废一小时没开始的考局、冷却结束时 TA 提醒一次、消息补投）。没人打开页面，世界也照样往前走。**TA 不会自己去考试**，考试由主人陪着完成。

## 2. 待接页面清单

| 页面 | 主要接口 | 谁在推动 | 后端状态 |
|---|---|---|---|
| DNA | `GET/PUT /pets/{pet_id}/dna` | 主人填写与修改 | 已实现、已验证；**0.2.5 新增 `behavior`** |
| 居住环境 | `GET/PUT /home/place`；入住时传 `habitat` | 主人选择 | 已实现、已验证 |
| 银行卡和流水 | `GET /credentials` → `GET /credentials/{id}`（`bank_card`） | TA 打工、出门（自动记账） | 已实现、已验证 |
| 证件卡包 | `GET /credentials`、`GET /credentials/{id}` | 入住、出行、驾考时签发 | 已实现、已验证；房卡未实现 |
| 爪爪驾校（0.3.0） | `GET /driving`、`GET /driving/curriculum`、`POST /driving/enroll`、`/driving/sessions/**`、`GET /driving/history`、`POST /driving/ceremony` | 主人操作、陪考；宠物执行，性格只体现在表情和话语里 | 后端与前端都已实现、已验证（自动化＋fixture 模式浏览器实测）；**live 界面未联调** |
| 工作记录 | `GET /jobs`（出发站：`GET /journey/destinations`、`POST /journey/suggest`） | TA 自己选岗 | 已实现、已验证 |
| 朋友 | `GET /friends` | TA 在外面自己遇到 | 已实现、已验证 |
| 生活时间线 | `GET /timeline` | 只读汇总 | 已实现、已验证 |
| 攻略手账 | `GET /guides`、`GET /guides/{guide_id}` | TA 出门前写 | 已实现、已验证（多站攻略需要模型） |
| 明信片 | `GET /collection`（`kind=postcard`）、`GET /media/illustrations/{id}` | TA 在外面寄 | 已实现、已验证（自拍需要生图） |

除爪爪驾校外全部**待前端联调**；爪爪驾校的前端已完成，待 live 联调。

## 3. 通用约定

### 3.1 登录会话

- `POST /auth/register`、`POST /auth/login` 会设置两个 cookie：
  - `petsoul_session`：HttpOnly、SameSite=Lax；
  - `petsoul_csrf`：前端可读，用来回填 CSRF 头。
- 刷新页面时用 `GET /session` 恢复登录状态，返回 `SessionState {authenticated, user, csrf_required, expires_at, onboarding}`。
- 所有请求走同源并带 `credentials: "include"`。现有 `shared/api/client.ts` 已经处理好了。
- 未登录返回 401 `AUTH_REQUIRED`，会话过期返回 401 `SESSION_EXPIRED`，这时跳去登录。
- 需要入住后才能用的页面（第 2 节除 DNA 外全部），在没入住时返回 409 `PET_NOT_ACTIVATED`，`details.onboarding_step` 给出下一步。沿用现有入住守卫。

### 3.2 CSRF

- 所有 POST、PUT、PATCH、DELETE 都要带请求头 `X-CSRF-Token`，值与 cookie `petsoul_csrf` 相同；缺少或不一致返回 403 `CSRF_FAILED`。`client.ts` 会自动回填。

### 3.3 幂等键

`WEB-ROUTES.md` 的“幂等键”一列标了“必填”的接口，必须带 `Idempotency-Key` 请求头：8–128 位，只能用 `A-Za-z0-9_-:.`。本文涉及的有：

- `POST /driving/sessions`（0.3.0：建立练习或正式考局）
- `POST /journey/depart`
- `POST /adoption/adopt`

规则：

- **一次用户动作用一个键。** 网络重试、超时重发都复用同一个键；动作成功后再换新键（`shared/api/idempotency.ts` 的 `newIdempotencyKey`）。
- 同键、同请求体：返回第一次的结果，不会重复执行。例如陪练不会重复加分，考试不会重考。
- 同键、不同请求体：409 `IDEMPOTENCY_KEY_REUSED`。
- 同一个键的请求还在处理中：409 `IDEMPOTENCY_IN_PROGRESS`，`retryable=true`，稍后用同一个键重试。
- 缺少这个头：400 `IDEMPOTENCY_KEY_REQUIRED`。
- 幂等只是第一层保护，领域层另有兜底：一场考局只结算一次，同一只宠物同一时间只有一场未结束的正式考试，一只宠物只有一本 C 照，同一份工资只入账一次。

### 3.4 跨账号访问

- 所有数据都按当前会话的主人过滤。
- 访问别人的 `pet_id`、`credential_id`、`guide_id`、驾校考局 `session_id`、插画或明信片，统一返回 **404 `NOT_FOUND`**，不是 403，不暴露资源是否存在。已有测试覆盖：他人证件详情、他人考局、他人 DNA。
- 照护档案（`private=true`）和 DNA 只给主人看，不能出现在公开主页或星球圈。

### 3.5 错误信封

```json
{"error": {"code": "CONFLICT", "message": "这一科两次都没通过，等冷却结束再约考试；练习随时可以。", "request_id": "req_7dba0ba8552e4bdf", "retryable": false, "details": {"reason": "cooldown", "cooldown_until": "2026-09-29T04:00:00Z"}}}
```

- 前端按 `code` 加 `details.reason` 分支，不要解析 `message`；`message` 可以直接展示给用户。
- 反馈问题时带上 `request_id`。
- 请求体里多了字段（例如伪造 `"passed": true`）会返回 422 `VALIDATION_FAILED`：所有 DTO 都禁止未知字段。

### 3.6 时间

- 接口里的时间都是 UTC ISO 8601（以 `Z` 结尾）。
- 服务器当前时间看 `GET /meta` 的 `server_time`，或旅程快照的 `server_time`。**不要用浏览器时钟推导状态。** 工作进度、证件状态、攻略状态都直接用服务端给的 `status`。
- 和 TA 生活有关的时刻（作息、打工、出门），按 TA 家所在地的时区显示：`GET /home/place` 的 `place.timezone`，例如 `Asia/Hong_Kong`。
- 和主人有关的，按主人设置里的 `timezone` 显示。

## 4. 各页面接口

### 4.1 DNA

| 方法 | 路径 | 参数 | 说明 |
|---|---|---|---|
| GET | `/pets/{pet_id}/dna` | — | 没保存过时返回草稿：`confirmed=false`，`draft_sources` 说明来源 |
| PUT | `/pets/{pet_id}/dna` | 请求体为完整的 `PetDNA`，整体替换 | 需要 CSRF，不需要幂等键；保存即代表主人确认 |

`PetDNA` 字段：`owner_title`(≤12)、`nicknames`(≤5)、`personality`(≤80)、`voice_style`(≤40)、`catchphrase`(≤40)、`favorite_foods`、`favorite_places`、`hobbies`、`habits`（各 ≤8，每条 ≤40）、`fears`(≤6)、`shared_memories`(≤8，每条 ≤80，**只用于私信**)。

**0.2.5 新增 `behavior`**（可选字段）：由这份 DNA 整理出的行为倾向。它就是作息判断、自主出门、主动消息、学车快慢实际使用的那一份。

请求与响应（真实，已截断）：

```json
PUT /api/v1/web/pets/PJ-5BE199D4/dna
{"owner_title": "姐姐", "nicknames": ["岚岚"], "personality": "不爱熬夜，不爱热闹，喜欢安静。", "voice_style": "慢吞吞的，说话前先眨眨眼",
 "habits": ["每天早上用头蹭一蹭姐姐的手", "偶尔半夜跑到窗台上看月亮"], "hobbies": ["看书", "晒太阳"], "favorite_places": ["海边"],
 "favorite_foods": ["冻干小鱼"], "fears": ["打雷"]}

200
{"pet_id": "PJ-5BE199D4", "dna": {…同上…, "catchphrase": null, "shared_memories": []}, "confirmed": true, "draft_sources": [],
 "updated_at": "2026-09-20T01:00:00Z", "private_fields": ["shared_memories"],
 "behavior": {
  "rules_version": "dna-behavior-2026.2", "rhythm": "regular", "sleep_start": "23:30", "wake": "07:30",
  "sociability": "homebody", "curious": false, "outings_per_day": 1, "chattiness": 1, "learn_rate": 1.0,
  "summary": ["不爱熬夜：按平常作息（23:30 睡，07:30 起）", "恋家：少出门、话少"],
  "traits": [
   {"key": "night_owl", "label": "爱熬夜", "status": "negated", "evidence": [
     {"field": "personality", "field_label": "性格", "phrase": "不爱熬夜", "polarity": "negative", "note": "“不”否定了这个说法", "implied": false},
     {"field": "habits", "field_label": "小习惯", "phrase": "偶尔半夜跑到窗台上看月亮", "polarity": "uncertain", "note": "“偶尔”：说法不确定，暂不归类", "implied": false}]},
   {"key": "social", "label": "爱热闹", "status": "negated", "evidence": [{"field": "personality", "phrase": "不爱热闹", "polarity": "negative", …}]},
   {"key": "homebody", "label": "恋家安静", "status": "applied", "evidence": [
     {"field": "personality", "phrase": "喜欢安静", "polarity": "positive", "note": null, "implied": false, …},
     {"field": "personality", "phrase": "不爱热闹", "polarity": "positive", "note": "由“不爱热闹”反推（单独不足以归类）", "implied": true, …}]}],
  "preferences": [
   {"key": "job:bookstore", "label": "在书店理书", "weight": 2.0, "evidence": [{"phrase": "喜欢安静", …}, {"field": "hobbies", "phrase": "看书", …}], "notes": []},
   {"key": "route:local:stroll", "label": "在家附近走走", "weight": 2.25, "evidence": […], "notes": ["恋家：更爱在附近走走"]},
   {"key": "route:local:city_trip", "label": "进城逛逛", "weight": 1.0, "evidence": [{"phrase": "不爱热闹", "polarity": "negative", …}], "notes": []},
   {"key": "route:long", "label": "出远门", "weight": 0.3, "evidence": [], "notes": ["恋家：不太想出远门"]}, …],
  "unclassified": [], "sources": ["personality", "voice_style", "habits", "hobbies", "favorite_places", "favorite_foods", "fears"]}}
```

字段与展示建议：

- 页面分两块：“你写的”是 `dna`，原样显示；“我们这样理解”是 `behavior`。
- **结论**：`summary` 可以直接作为结论展示。作息（`sleep_start`/`wake`）按 TA 家的当地时间显示。`rhythm` 取值：`regular`、`night_owl`、`early_bird`、`sleepy`。`sociability` 取值：`social`、`steady`、`homebody`。
- **`traits[].status`**：
  - `applied`：用上了；
  - `negated`：你说了“不是”，例如“不爱熬夜”；
  - `outweighed`：被更明确的说法盖过，例如“以前爱熬夜，现在早睡早起”；
  - `uncertain`：说不准，没有用。
- **`evidence[]`** 标明每条结论来自哪一栏（`field_label`）的哪一句原话（`phrase`，原样），以及为什么这样理解（`note`）。`implied=true` 表示由别的说法反推，单独不足以归类，可以弱化显示。
- **`unclassified`** 列出提到了但说不准、或前后矛盾的原话。建议提示：“这几句我们没把握，没有用在 TA 的作息里，可以换个更明确的说法。”
- **`preferences[].weight`**：大于 1 表示更愿意，小于 1 表示不太愿意，等于 1 表示照常（只是提到过）。`notes` 是来自性格的调整。
- `behavior` 只使用两类来源：DNA；以及接待时主人允许用于“家中互动”或“出行偏好”的叮嘱（`sources` 里的 `note`）。**只允许私信使用的叮嘱，以及 `shared_memories`，不参与行为。** 草稿状态下的 `dna.habits` 可能包含只限私信的叮嘱，所以草稿的 `behavior` 不一定和 `dna` 一一对应。
- 规则是确定性的（`rules_version=dna-behavior-2026.2`），不调用模型，不产生费用。

空值与错误：

- 新宠物还没有任何资料时，`dna` 各栏为空，`behavior` 为默认值（`regular`/`steady`，`traits` 为空）。
- 404 `NOT_FOUND`：不是你的宠物。
- 422 `VALIDATION_FAILED`：超长或含未知字段。
- 403 `CSRF_FAILED`。

刷新：

- PUT 的响应就是最新的 `PetDNAView`，直接写回缓存，不需要再请求。
- 需要让这些查询失效：`["dna", pet_id]`；家园快照（TA 此刻睡着或醒着可能随作息变化）；星球通讯器（状态提示）。
- 服务端对画像有 60 秒缓存，但保存 DNA、接待确认或更正叮嘱时会立即清掉。

### 4.2 居住环境

| 方法 | 路径 | 参数 | 说明 |
|---|---|---|---|
| POST | `/onboarding/move-in` | `{"public_posts": bool, "habitat"?: HabitatKind}` | 入住时选择；不填沿用默认（香港·中环） |
| GET | `/home/place` | — | 当前的家与可选类型 |
| PUT | `/home/place` | `{"habitat": HabitatKind}` | 搬家；需要 CSRF |

```json
GET /api/v1/web/home/place → 200
{"place": {"habitat": "seaside", "habitat_label": "海边", "city": "香港", "area_label": "西贡的海边", "display": "香港·西贡的海边",
           "timezone": "Asia/Hong_Kong", "chosen": true},
 "options": [{"habitat": "seaside", "label": "海边", "examples": ["香港", "厦门", "青岛", "三亚", "大连"]},
             {"habitat": "grassland", "label": "草原", "examples": ["呼伦贝尔", "锡林郭勒", "阿坝"]}, …],
 "can_change": true}
```

- `HabitatKind` 取值：`seaside`、`grassland`、`desert`、`forest`、`lakeside`、`mountain`、`city`、`countryside`。
- 服务端在对应类型里随机分配一座城市的一个片区，**不给具体门牌**，页面平时用 `display` 或 `habitat_label` 即可。
- 同一类型重复提交，城市保持不变；换类型才算搬家，会换城市。刷新或重新登录都不会换城市。
- `can_change=false` 表示 TA 在外面，这时 PUT 返回 409 `CONFLICT`（`reason=pet_away`，“TA 还在外面，等回家了再搬”）。
- `chosen=false` 表示还没选过（用的是默认的家）。
- 搬家后需要让这些查询失效：`/home/place`、家园快照、`/journey/destinations`（出发站按城市变化）。

### 4.3 银行卡和流水

银行卡就是 TA 现有的钱包账户，不另建余额。家园快照里的 `wallet.balance` 与银行卡的 `balance` 是同一个数。

```json
GET /api/v1/web/credentials/cr-e5f64af94f4e → 200
{"summary": {"credential_id": "cr-e5f64af94f4e", "kind": "bank_card", "label": "星球银行卡", "status": "active", "number": "PSB-2026-KRU9QQ",
             "issued_at": "2026-09-20T01:00:00Z", "title": "星球银行卡", "condition": "入住时开户；就是 TA 的钱包账户，工资和旅费都记在这里",
             "private": false, "links": [{"kind": "home", "ref_id": "home-PJ-5BE199D4", "title": "入住星球", "at": "2026-09-20T01:00:00Z"}]},
 "fields": [{"label": "户名", "value": "小岚 的星球账户"}, {"label": "卡号", "value": "PSB-2026-KRU9QQ"}, {"label": "开户日期", "value": "2026-09-20"},
            {"label": "币种", "value": "星币"}],
 "balance": 48,
 "ledger": [{"tx_id": "TX-2A54B30190A2F8", "type": "web_job_income", "delta": 28, "reason": "去渔港帮忙收网的工钱", "created_at": "2026-09-20T04:10:00Z"},
            {"tx_id": "TX-086B68A92AD195", "type": "web_reward", "delta": 20, "reason": "入住欢迎旅费（每个家一次，不可交易）", "created_at": "2026-09-20T01:00:00Z"}],
 "stamps": [], "care_notes": []}
```

- 流水按时间倒序，`delta` 为正是收入、为负是支出。`type` 常见取值：
  - `web_reward`：欢迎旅费；
  - `web_job_income`：工资；
  - `web_travel_fee`：旅费，`reason` 形如“「进城逛逛」的旅费”；
  - 其余为集市、农场等现有账本类型。
- 本轮修正：不花钱的出门（散步、打工）不再记一笔 0 元旅费。
- 钱不够时出发会返回 409 `INSUFFICIENT_FUNDS`，`details` 里有 `balance` 和 `fee`。TA 自主生活时，钱不够就只会散步或去打工。
- 星币只在星球上用，不能换算成现实花费，页面不要显示任何人民币价格。
- 刷新时机：工资到账、出门扣费都发生在世界事件里。建议进入页面时刷新，另外在收到通讯器新消息（例如“工钱已经存进我的银行卡”）后让 `/credentials/{bank_id}` 和家园快照失效。

### 4.4 证件卡包

`GET /credentials` **总是列出 8 类证件**。已获得的有 `credential_id` 和 `number`；未获得的这两个字段为 `null`，并用 `condition` 说明获得条件。

```json
GET /api/v1/web/credentials → 200（节选）
[{"credential_id": "cr-16faad8ce32e", "kind": "identity_card", "label": "宠物 ID", "status": "active", "number": "PS-ID-2026-QP2LPZ",
  "issued_at": "2026-09-20T01:00:00Z", "title": "宠物 ID", "condition": "入住星球时签发", "private": false, "links": [{"kind": "home", …}]},
 {"credential_id": "cr-66415a165e76", "kind": "care_profile", "label": "照护档案", "status": "active", "number": "PS-CARE-2026-AXSKSM", …, "private": true, …},
 {"credential_id": "cr-7aaa507c558b", "kind": "driver_license", "label": "爪爪驾驶证", "status": "active", "number": "PAW-DL-2026-4ZLRSG",
  "issued_at": "2026-09-20T05:00:00Z", "title": "爪爪驾驶证 · 小型车（C）", "condition": "通过理论考试和场景驾驶考试后签发",
  "links": [{"kind": "exam", "ref_id": "ex-63030c7738e4", "title": "通过场景驾驶考试", "at": "2026-09-20T05:00:00Z"}]},
 {"credential_id": null, "kind": "passport", "label": "护照", "status": "not_obtained", "number": null, "issued_at": null,
  "condition": "第一次出远门（跨城或跨境）时签发；本地散步不需要", "links": []},
 {"credential_id": null, "kind": "hotel_key", "label": "酒店房卡", "status": "not_obtained", …, "condition": "在外过夜入住时发放；目前的旅程都是当天往返，暂未开放"}, …]
```

| kind | 何时签发 | status 的变化 | 详情里的额外内容 |
|---|---|---|---|
| `identity_card` 宠物 ID | 入住时，`issued_at` 就是入住时间 | `active` | `fields`：名字、物种、星球编号、住在、入住日期；头像沿用宠物照片接口 `GET /media/pets/{pet_id}/photo` |
| `bank_card` 星球银行卡 | 入住时 | `active` | `balance`、`ledger` |
| `care_profile` 照护档案 | 入住时 | `active`，**`private=true`** | `care_notes`（主人确认过的习惯、怕的、爱吃的、叮嘱） |
| `passport` 护照 | 第一次出远门时，只有澳门、东京两条正式远行 | `active` | `stamps`：到达后盖的纪念章 |
| `driver_license` 爪爪驾驶证 | 场景考试通过时，与考试结果同一次提交 | 学车期间未签发，列表里显示 `in_progress`；签发后为 `active` | 准驾车型、理论与场景成绩 |
| `boarding_pass` 登机牌 | 坐飞机的正式远行 | 出发前 `active`，在途 `in_progress`，到达后 `used` | 承运人、班次、座位、起止时间 |
| `transport_ticket` 船票、车票 | 坐船或火车的正式远行 | 同登机牌 | 同登机牌 |
| `hotel_key` 酒店房卡 | **尚未实现**（没有过夜行程） | 永远是 `not_obtained` | — |

- 编号全局唯一、稳定；`issued_at` 是持久保存的签发时间，刷新或隔天再看都不会变成“今天签发”。页面不要自己编号，也不要用宠物 ID 截尾。
- `status` 由服务端按行程时间计算，前端直接用，不要自己比对时间。
- 房卡在 `/meta` 里的能力是 `credentials.hotel_key: not_implemented`，请显示为“暂未开放”，不要显示成“去获得”。
- 登机牌、船票：目前只有家在香港·中环时才有澳门、东京两条正式远行，其他城市暂无（见第 8 节）。
- 照护档案属于私密资料，只在主人自己的卡包里显示，不进公开卡片或星球圈。
- 详情接口是 `GET /credentials/{credential_id}` → `CredentialDetail {summary, fields, balance, ledger, stamps, care_notes}`，卡面文字直接用 `fields`（`label`/`value`）排版。
- 错误：他人的证件，或尚未获得的证件（没有 `credential_id`），返回 404。
- 刷新：进入卡包时刷新。入住后、出远门后、拿证后，让 `/credentials` 失效。

### 4.5 爪爪驾校（0.3.0，替换 0.2.5 的陪练与场景考试；前端已实现）

- 规格：[`docs/contracts/DRIVING-SCHOOL-v1.md`](../contracts/DRIVING-SCHOOL-v1.md)。前端模块：`PetJourneyWeb/src/features/driving_school/`（总览、科目、考局、成绩单与回放、领证仪式、倒车入库体验版；fixture 与 live 两套服务）。下面供维护与 live 联调参考。
- 核心：**主人操作，宠物执行**。正式成绩只由操作与规则决定：科一科四按固定题库批改，科二科三由服务端按操作记录复算；模型与随机数都不参与，客户端上报的分数一律无效。

| 方法 | 路径 | 请求 | 幂等键 | 说明 |
|---|---|---|---|---|
| GET | `/driving` | — | — | `DrivingSchoolStatus`：阶段、四科状态（`locked`/`available`/`in_exam`/`cooldown`/`passed`）、本轮机会、冷却截止时间、未结束的考局、驾照、借车券、仪式是否完成、`temperament`（选台词用）、`server_time` |
| GET | `/driving/curriculum` | — | — | `SchoolCurriculum`：教练、四科说明、分步教学、扣分项与红线、操作说明、补考规则、按性格的台词、`reasons`（判定说明文字，实时提示与成绩单共用） |
| POST | `/driving/enroll` | — | — | 陪 TA 报名；已报名时是空操作 |
| POST | `/driving/sessions` | `{subject, mode: "practice"\|"formal", item?}` | **必填** | 建局，状态 `preparing`，**不计次**。正式考局检查解锁、机会、冷却与未结束的考局；同一科已有未结束的正式考局时原样返回它 |
| GET | `/driving/sessions/{id}` | — | — | 考局：题目（不含答案）或场地配置（`course`）、已保存的作答或操作、服务端快照、结果 |
| POST | `/driving/sessions/{id}/begin` | — | — | 资源加载完成、点“开始”：正式考局**从这一刻起计次**；重复调用无副作用 |
| PUT | `/driving/sessions/{id}/answers` | `{question_id, answer: {choice?, order?, matches?}}` | — | 科一科四逐题保存（同题再存会覆盖）。练习立即返回讲解；正式考试交卷前不给任何提示 |
| POST | `/driving/sessions/{id}/inputs` | `{item_index, from_tick, upto_tick, events: [{t, c, v}]}` | — | 科二科三上传一段操作（≤900 tick、≤2000 条），返回服务端复算的判定事件、扣分与快照。完全相同的重发原样返回；不连续 409 `gap`，内容不同 409 `resync`（都带 `committed_tick`） |
| POST | `/driving/sessions/{id}/pause` | — | — | 记录暂停（切后台、断线、主动暂停） |
| POST | `/driving/sessions/{id}/submit` | — | — | 科一科四交卷；只结算一次，重复请求返回同一结果。科二科三开完或失败时自动结算 |
| POST | `/driving/sessions/{id}/abandon` | `{"confirm": true}` | — | 已开始的正式考局计为不通过；练习与还没开始的正式考局直接作废、不计次 |
| GET | `/driving/history` | — | — | 最近的练习与考试（只给主人看） |
| POST | `/driving/ceremony` | — | — | 领证仪式：第一次生成“领证合影”收藏；再次打开只是回看（`first_time=false`） |

规则要点：

- **解锁**：正式考试按科目一 → 二 → 三 → 四；上课与练习报名后随时可以。
- **机会与冷却**：每轮首次考试＋一次补考；两次都没通过，从第二次结算的时间起冷却 7×24 小时（服务器时间），冷却结束开始新一轮；已通过的科目一直保留；不卖补考次数，也不能清除或缩短冷却。
- **计次**：`begin` 之后才算一次；建立后一小时没开始的考局作废（`void_reason=not_started`）；服务端复算出错的考局作废（`platform_fault`）；这两种都不计次。主动放弃要 `confirm: true`，计为不通过。
- **续考**：暂停、断线、换设备回来，都按服务端保存的作答或操作接着考，不会重新抽题，也不会抹掉已经发生的扣分。同一只宠物同一时间只有一场未结束的正式考试（数据库部分唯一索引兜底）。
- **拿证**：第四科通过、四科齐全时，同一事务签发 PetSoul · 爪爪驾驶证（C 照）、发一张驾校借车券（第一次自驾免租车费）、登记拿证消息；消息投递失败不影响驾照。
- **驾驶模拟**：30 Hz 固定步长，只用加减乘除与 `sqrt`，所有常数来自场地配置。前端 `features/driving_school/sim/` 与后端 `app/web_driving/sim.py`、`replay.py` 逐行对应；`tests/driving-sim.test.ts` 用 `scripts/gen_driving_fixtures.py` 生成的样例逐位比对。操作事件 `c`：`s` 转向目标（−12..12）、`t` 油门、`b` 刹车、`g` 换挡（1＝D，−1＝R，只在车速为 0 时生效）、`k` 转向灯（−1 左 / 1 右）、`c` 出发前检查（1..3）、`v` 视频邀请（0 稍后 / 1 打开）。

真实响应（进程内测试基座跑出，已截断）：

```json
POST /api/v1/web/driving/sessions   Idempotency-Key: <这次建局的键>   {"subject": "s2", "mode": "practice", "item": "reverse_park"}
200 {"session_id": "ds-1865d37ec1b74a72", "subject": "s2", "title": "科目二：把小车开稳 · 倒车入库", "mode": "practice", "item": "reverse_park",
     "attempt_kind": null, "state": "preparing", "pass_score": 80, "quiz": null,
     "drive": {"items": [{"item": "reverse_park", "title": "倒车入库", "status": "running", "committed_tick": 0, "course": {…}, "events": [], "sim_events": [], "snapshot": {…}}], "current_item": 0}, "result": null, …}

POST /api/v1/web/driving/sessions/ds-…/inputs   {"item_index": 0, "from_tick": 0, "upto_tick": 30, "events": [{"t": 0, "c": "t", "v": 1}]}
200 {"session_state": "running", "item_index": 0, "current_item": 0, "item_status": "running", "committed_tick": 30, "new_events": [], "deducted": 0, "snapshot": {…}, "result": null, …}

POST /api/v1/web/driving/sessions/ds-…/inputs   {"item_index": 0, "from_tick": 60, "upto_tick": 90, "events": []}
409 {"error": {"code": "CONFLICT", "message": "中间缺了一段操作记录，请按服务器记录重新同步。", "retryable": false, "details": {"reason": "gap", "committed_tick": 30}, …}}

POST /api/v1/web/driving/sessions/ds-…/submit   （科目一补考，错 3 题）
200 {"state": "settled", "attempt_kind": "retake", "result": {"passed": false, "score": 70, "max_score": 100, "pass_score": 90,
     "deductions": [{"kind": "wrong_answer", "label": "答错：停车让行", "points": 10, "question_id": "s1.stop.1", …}, …],
     "review": [{"question_id": "s1.stop.1", "correct": false, "your_answer": {…}, "correct_answer": {…}, "explanation": "“停”字牌的意思是先完全停下来，确认左右安全再走。"}, …],
     "pet_says": "（轻轻蹭了蹭你）这轮先到这里，我们把要练的地方记下来了。",
     "next": {"kind": "cooldown", "message": "这轮先到这里。我们把需要练的地方记下来了；模拟练习随时开放。", "attempts_left": 0, "cooldown_until": "2026-09-29T04:00:00Z"}}, …}
```

错误码（`details.reason`）：

| HTTP / code | reason | 何时出现 | 前端做法（已实现） |
|---|---|---|---|
| 409 CONFLICT | `not_enrolled` | 还没报名就建局 | 引导报名 |
| 409 CONFLICT | `locked` | 前一科还没通过 | 显示 `unlock_hint`，可以练习 |
| 409 CONFLICT | `cooldown`（带 `cooldown_until`） | 本轮两次都没通过 | 显示等待时间，可以练习 |
| 409 CONFLICT | `already_passed` | 这一科已经通过 | 刷新状态 |
| 409 CONFLICT | `exam_in_progress`（带 `session_id`） | 另一科还有未结束的正式考试 | 引导回去接着考 |
| 409 CONFLICT | `not_running`、`not_finished`、`wrong_item` | 考局还没开始、已经结束，或项目不对 | 重新取考局 |
| 409 CONFLICT | `gap`、`resync`（带 `committed_tick`） | 操作片段不连续或不一致 | 按服务端快照重建本地状态，暂停等主人点“继续” |
| 409 CONFLICT | `platform_fault` | 服务端复算出错 | 显示“考局已作废，不计次” |
| 409 CONFLICT | `not_licensed`、`license_pending` | 还没拿证就去领证；驾照正在签发 | 回驾校首页 / 稍后再来 |
| 404 NOT_FOUND | `session_not_found` | 考局不存在或不是你的 | — |
| 422 VALIDATION_FAILED | `invalid_item`、`question_not_in_paper`、`invalid_answer`、`invalid_input`、`confirm_required` | 请求内容与题目或规则不符 | 前端 bug，重新取考局 |
| 400 | IDEMPOTENCY_KEY_REQUIRED | 建局缺少幂等键 | — |

刷新：驾校写操作成功后失效 `["driving"]`（状态、课程、考局、历史）、`/credentials`（驾照）、`/collection`（借车券、领证合影）和家园快照；考局写操作直接用响应更新考局缓存（`features/driving_school/hooks.ts::useInvalidateSchool`）。

### 4.6 工作记录

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/jobs` | TA 的打工记录，最近在前，最多 50 条 |
| GET | `/journey/destinations` | 出发站：本地活动、打工岗位（按家所在的环境）、有驾照后的自驾 |
| POST | `/journey/suggest` | 主人给出门建议（推荐的交互）：TA 会认真考虑，但由 TA 自己决定去不去、什么时候去 |
| GET | `/journey/suggestions` | 建议的处理结果：`pending`、`accepted`、`passed`、`replaced` |
| POST | `/journey/depart` | 立即出发；需要幂等键。现有页面在用，联调时也可以用它来确定性地触发打工 |

```json
GET /api/v1/web/jobs → 200
[{"journey_id": "jn-01ada7b286b0", "job_key": "fishing_port", "title": "去渔港帮忙收网", "place": "示例·渔港帮忙收网（演示）",
  "starts_at": "2026-09-21T01:10:00Z", "ends_at": "2026-09-21T04:10:00Z", "status": "done", "pay": 28, "paid": true},
 {"journey_id": "jn-4e3c7b8bfbb9", …, "status": "going", "pay": 28, "paid": false}]
```

- `status` 由服务端按到岗时间计算：
  - `going`：去上班的路上；
  - `working`：在干活；
  - `done`：干完了。
- `paid` 表示工资是否已经进了银行卡。工资在“干完活”这个世界事件里入账，按旅程只入一次。`done` 但 `paid=false` 只会短暂出现，可以显示“工钱入账中”。
- 岗位按家所在的环境开放：咖啡馆、花店、邮局哪里都有；书店在城市、湖边、田园；渔港在海边；牧场在草原、田园；巡山在森林、山里；骆驼队在沙漠。
- **TA 自主选岗**：白天每半小时考虑一次；钱少时更愿意去打工，一天最多一份工；DNA 喜欢的活更容易被选中。主人只给建议。
- 刷新：出门或建议成功后，让 `/jobs`、`/journey/map`、家园快照失效；打工期间可以按分钟级轮询 `/jobs` 或 `/journey/map`。

### 4.7 朋友

```json
GET /api/v1/web/friends → 200
[{"friend_id": "npc:dog_wang", "kind": "resident", "name": "导游犬旺旺", "species": null, "meet_count": 2, "closeness": "熟人",
  "first_met_at": "2026-09-20T01:10:00Z", "last_met_at": "2026-09-21T01:10:00Z", "last_place": "示例·渔港帮忙收网（演示）"}]
```

- `kind` 取值：
  - `resident`：星球居民（NPC）。**页面必须明确标注“星球居民”**，不能冒充真实玩家；
  - `pet`：真实玩家的宠物，有 `species`。
- 只有同一时间在同一地点（或同城 300 米内）才算遇到，双方主人都开了公开动态、且互相没有拉黑。
- `closeness` 取值：初识、熟人、好朋友。
- 遇到后，双方宠物会在通讯器里告诉主人，受每日主动消息上限约束。
- 空列表时显示“TA 还没在外面遇到朋友”。
- 刷新：进入页面时刷新；收到通讯器新消息后失效。

### 4.8 生活时间线

```json
GET /api/v1/web/timeline → 200（节选，最近在前，最多 100 条）
[{"at": "2026-09-21T07:20:00Z", "kind": "home", "title": "回到家：进城逛逛", "detail": null, "ref_id": "jn-540e87b6959a"},
 {"at": "2026-09-21T06:55:00Z", "kind": "postcard", "title": "寄回一张明信片", "detail": "来自青岛的明信片", "ref_id": "it-0f6e20c81656"},
 {"at": "2026-09-20T07:40:00Z", "kind": "credential", "title": "拿到驾驶证", "detail": "PAW-DL-2026-XSHK4A", "ref_id": "cr-22a237b2afed"},
 {"at": "2026-09-20T07:40:00Z", "kind": "exam", "title": "场景驾驶考试通过", "detail": "100/100", "ref_id": "ex-…"},
 {"at": "2026-09-20T06:40:00Z", "kind": "exam", "title": "场景驾驶考试没通过", "detail": "20/100", "ref_id": "ex-…"},
 {"at": "2026-09-20T04:10:00Z", "kind": "salary", "title": "领到工资 28 星币", "detail": "去渔港帮忙收网的工钱", "ref_id": "TX-…"},
 {"at": "2026-09-20T01:10:00Z", "kind": "friend", "title": "认识了星球居民导游犬旺旺", "detail": "示例·渔港帮忙收网（演示）", "ref_id": "npc:dog_wang"}, …]
```

`kind` 与 `ref_id` 的对应：

| kind | ref_id 是什么 |
|---|---|
| `trip`（出发）、`first_drive`（第一次自驾）、`work`（去打工）、`home`（回到家） | `journey_id` |
| `salary`（工资） | 账本 `tx_id` |
| `credential`（证件签发） | `credential_id` |
| `stamp`（护照纪念章） | `journey_id` |
| `exam`（驾考） | `attempt_id` |
| `friend`（认识朋友） | `friend_id` |
| `postcard`、`badge`、`seed`、`shared_memory`（收藏） | `item_id` |
| `guide`（写攻略） | `guide_id` |

- 这些都是已经发生的记录，不是计划。同一时刻按发生先后排列，后发生的在前（本轮修正）。
- 标题可以直接展示，`kind` 用来选图标。
- 本轮把回家标题从“从去渔港帮忙收网回到家”改成了“收工回到家：去渔港帮忙收网”。

### 4.9 攻略手账

```json
GET /api/v1/web/guides → 200（节选；演示库没有模型，所以是模板攻略）
[{"guide_id": "gd-44e8773b0a75", "journey_id": "jn-069de51b79b7", "city": "青岛", "destination_title": "进城逛逛", "title": "青岛小攻略",
  "summary": "今天去示例·青岛城里（演示）。",
  "stops": [{"name": "示例·青岛城里（演示）", "label": "示例·青岛城里（演示）", "time": "今天", "why": "这次就去这里。", "tip": "以现场为准。",
             "verified": false, "address": null, "lat": null, "lng": null, "attribution": "演示地点：不对应真实商家", "nav_url": null, "copy_text": null}],
  "owner_tips": ["出发前查一下天气和开放时间，以现场为准。"], "composed_by": "template", "image_status": null, "image_url": null,
  "created_at": "2026-09-21T05:00:00Z", "status": "completed", "visited": ["示例·青岛城里（演示）"], "coin_budget": 30,
  "real_budget_note": "现实出行的门票、交通和餐饮花费以现场为准；本攻略不提供价格，星币只用于 TA 在星球上的旅费。"}]
```

- **计划与已发生分开**：`stops` 是 TA 的计划；`visited` 是实际到过的站点。`status` 取值：`planned` 还没出发、`in_progress` 在路上、`completed` 已回家。
- **可复用**：只有核实过的站点（`verified=true`）才有 `address`、`nav_url` 和 `copy_text`：
  - `nav_url` 打开高德地图标记，坐标为 WGS-84；
  - `copy_text` 用于“复制名称和地址”。
  - 未核实的站点要显示“未核实，以现场为准”，不要给导航。
- **预算分开**：`coin_budget` 是星币（游戏内，从银行卡扣）；`real_budget_note` 说明现实花费，不提供价格，**不要把星币换算成人民币**。
- `composed_by` 取值：
  - `model`：由 DeepSeek 按 DNA 写，多站；要求主人开启“模型回信”，且后端配置了模型（付费）；
  - `template`：只有一站，就是这次真的要去的地方。
- 手账图：主人开启“生成照片”且配置了生图（付费）时，`image_status` 依次为 `processing`、`ready`、`failed`，`ready` 时有 `image_url`，指向 `/api/v1/web/media/illustrations/{id}`，只有主人本人可读。
- 攻略写好后，TA 会在通讯器里说一声。
- 刷新：出门后让 `/guides` 失效；`in_progress` 期间 `visited` 会变化，可以按分钟级刷新。

### 4.10 明信片

```json
GET /api/v1/web/collection → 200（kind=postcard 的节选）
[{"item_id": "it-36e5e96b2a46", "kind": "postcard", "item_key": null, "title": "来自青岛的明信片", "obtained_at": "2026-09-21T06:55:00Z",
  "tradable": false, "bound_to_pet": true, "source_event_id": "jn-069de51b79b7:visit_ended", "data_origin": "live",
  "note": "姐姐，今天在青岛的示例·青岛城里（演示）待了一会儿，回来的路上路过邮局，就想给你寄一张。",
  "image_url": null, "image_status": null, "place": "示例·青岛城里（演示）", "city": "青岛"}]
```

- 明信片由 TA 在外面的邮局写好寄回，只写真实发生的地点。打工、附近散步、去附近喝一杯不寄；进城、自驾兜风、正式远行会寄。
- `note` 是 TA 写的话：主人开启“模型回信”时由模型按 DNA 写，否则用模板。
- 写实自拍：主人开启“生成照片”且配置了生图时才有。`image_status` 依次为 `processing`、`ready`、`failed`；没开启时为 `null`，这时显示没有照片的纸质卡片样式。生成失败时保留卡片、显示“自拍没洗出来”，目前没有重试接口。
- 同一接口还返回其他收藏（`seed` 种子、`badge` 勋章、`shared_memory` 一起听歌的回忆），按 `kind` 过滤。
- 寄出后，TA 会在通讯器说“路过…的邮局，给你寄了一张明信片～在收藏里能看到。”
- 刷新：收到通讯器新消息后让 `/collection` 失效；有 `processing` 的卡片时，可以每 30 秒刷新一次，直到 `ready` 或 `failed`。

### 4.11 相关：星球通讯器消息（验收路线要用）

- 接口：`GET /communicator/{pet_id}/messages` → `{pet_id, items[], next_cursor, data_origin}`。
- `items[]` 包含 `sender`（pet 或 owner）、`text`、`created_at`、`composed_by`（template、event、model）、`topic`、`photo_status` 等字段。
- 驾考、打工、明信片、朋友、攻略的消息都会出现在这里。例如：“我拿到驾照啦！编号 PAW-DL-2026-XSHK4A。以后可以自己开车去兜风了（要先租车哦）。”

## 5. 哪些由宠物自主完成、哪些由主人触发

| 事情 | 宠物自主（服务端定时器，主人离线也继续） | 主人触发 |
|---|---|---|
| 出门、去哪 | 白天按 DNA 的节奏与银行卡余额自己决定；钱不够就散步或打工 | `POST /journey/suggest` 给建议；“今天别出门”一类的话会降低出门几率 |
| 打工 | 自己选岗，一天最多一份；工资自动入账 | 可以建议 |
| 学车 | 产生愿望；报名满一天后邀请主人陪练；冷却结束时告诉主人可以再约考试。**不会自己去考试** | 陪 TA 报名、上课、练习、陪考（操作由主人完成）、领证仪式 |
| 证件 | 入住、出行时自动签发；驾照在四科全过的那次结算里签发 | 只能查看 |
| 攻略、明信片、朋友 | 出门时自己写、自己寄、自己遇到 | 只能查看 |
| DNA、居住环境 | — | 主人填写、选择 |
| 消息 | 事件消息与主动消息（每天有上限，不推送） | 主人发消息，TA 按自己的状态回复 |

## 6. 前端更新方式

| 操作成功后 | 需要失效或刷新的查询 |
|---|---|
| PUT DNA | `["dna"]`、家园快照、通讯器状态 |
| PUT /home/place | `/home/place`、家园快照、`/journey/destinations` |
| POST /journey/suggest | `/journey/suggestions` |
| POST /journey/depart | `/journey/map`、家园快照、`/jobs`、`/credentials`（银行卡余额）、`/guides` |
| POST /driving/enroll | `/driving`（用响应直接更新） |
| 驾校建局、开考、作答、上传、交卷、放弃 | 考局用响应更新；`/driving`、`/driving/history` |
| 结算四科全过、POST /driving/ceremony | `/driving`、`/credentials`、`/collection`、`/journey/destinations`、`/timeline`、通讯器 |
| 收到通讯器新消息 | `/timeline`、`/collection`、`/friends`、`/credentials`、家园快照 |

- 世界在服务端自己往前走（定时器每 30 秒），页面不会收到推送。建议窗口重新获得焦点时刷新当前页；家园、打工、明信片生成中这几处，停留时每 30–60 秒轮询一次。驾校页面不用轮询：状态只因主人的操作变化（冷却到期按服务器时间计算）。
- 所有“到点了没有”的判断（到岗、到站、签发、入账）都以服务端返回的状态和 `server_time` 为准。

## 7. 本地测试账号与演示数据

- 生成演示库：`python scripts/seed_web_demo.py`（加 `--reset` 重建，加 `--examples out.json` 同时导出真实请求与响应）。
  - 只写 `PetJourneyBackend/data/web-demo/`，该目录被 git 忽略；
  - 全程关闭真实供应商，不产生任何付费调用；
  - 用回放时钟把两天的生活压缩成几秒，所有事件都发生在过去。
- 演示内容：
  - 入住海边的家（城市随机，例如青岛、香港）；
  - DNA 用的是核查反例原句；
  - 三张入住证件；
  - 两次渔港打工并发薪；
  - 爪爪驾校（0.3.0）：科一、科二首次没过、补考通过，科三、科四通过，领证仪式；第一次自驾用借车券；
  - 自驾兜风、进城逛逛各一次，各有模板攻略和明信片；
  - 认识星球居民，数量由确定性掷骰决定，多数情况下有 1–2 位；
  - 一串通讯器消息。
- **账号与口令**：
  - 用户名以 `demo-` 开头，宠物是虚构的领养伙伴“小岚”；
  - 口令随机生成，只写在 `data/web-demo/demo-login.local.txt`（git 忽略），**不打印、不进仓库、不进文档、不发给任何人**。
- **演示数据与真实数据的区分**：
  - 演示库是独立的 SQLite 文件，与本窗口的验证库、公网数据互不相通；
  - 演示地点都带“示例·…（演示）”，`attribution` 写明“演示地点：不对应真实商家”；
  - 交通 `time_basis=demo_fixture`，写明“未接入核验时刻表”。
  - 页面上不要把演示数据说成真实商家或真实班次。
- 自动化测试的 fixture：后端 `PetJourneyBackend/tests/web_base.py`（`WebPlatformTestBase`、`FakeClock`、`WebUser`）可以造任意状态。例如：
  - `tests/test_web_driving_license.py` 构造了签发失败回滚、旧版补签；`tests/school_helpers.py` 的测试驾驶员能按每秒一段上传操作；
  - `tests/test_web_agent_dna_reading.py` 覆盖了各类 DNA 说法。
- 前端自己的 fixture 模式（`VITE_PETSOUL_DATA_MODE=fixture`）不连后端，fixture 数据需要带 `data_origin: "fixture"`，不要混入 live。

## 8. 各模块完成边界

| 模块 | 后端已实现 | 已验证 | 待前端联调 | 尚未实现（不要写成可用） |
|---|---|---|---|---|
| DNA 与行为倾向 | 保存与读取；按小句读否定、纠正、混合与含糊说法；给出原话出处；用途限制 | 自动化（9 项回归，外加画像与生活测试）；本地实跑演示库 | 是 | 主人直接改“作息、性格”结构化选项（目前只能改原话）；模型级人格判断 |
| 居住环境 | 8 类环境、稳定城市、搬家限制 | 自动化；本地实跑 | 是 | 交通枢纽数据；海外片区（等 Google 地图） |
| 银行卡与流水 | 统一钱包、流水 | 自动化；本地实跑 | 是 | 现实银行业务（永远不做） |
| 证件卡包 | 7 类可签发；编号稳定、签发时间持久、跨账号隔离 | 自动化；本地实跑 | 是 | **酒店房卡**（没有过夜行程）；正式远行只从香港·中环出发（澳门、东京），其他城市暂无护照和登机牌 |
| 爪爪驾校（0.3.0） | 四科、首次＋补考、7×24 小时冷却、续考、放弃确认、服务端复算、只结算一次、同事务签发、借车券、领证仪式与合影、旧版补签 | 后端自动化 29 项＋18 个子测试（含复算、红线、样例逐位一致、签发回滚）；前端 32 项（复算逐位比对、规则、页面流程）；fixture 模式浏览器实测（390×844） | 前端已完成，live 界面待联调 | 阶段 3：其他训练场与车型外观、居民委托与拿证后的短途故事、车辆购买与车库、成绩分享、家里展示柜 |
| 工作记录 | 岗位、状态、工资只入一次 | 自动化；本地实跑 | 是 | 可验证的工作小游戏或完成条件（目前按时长完成） |
| 朋友 | 真实宠物同地相遇、星球居民、关系累积 | 自动化；本地实跑 | 是 | 朋友之间互动、互访 |
| 生活时间线 | 汇总 10 类记录 | 自动化；本地实跑 | 是 | 分页（目前取最近 100 条） |
| 攻略手账 | 站点核实、导航与复制、计划与已到访、预算口径、手账图 | 自动化；真实模型、高德、生图在上一轮本地实跑过（付费调用） | 是 | 营业时间、价格、口碑、交通核验；核验时刻表 |
| 明信片 | 邮局明信片、TA 写的话、写实自拍（生图） | 自动化；上一轮本地实跑过生图 | 是 | 自拍失败后的重试接口 |

## 9. 联调验收路线

建议在 18762 演示库上走一遍“看已有状态”，再用一个新注册账号在 mock 后端上从零走一遍下面的路线。第 3–4 步涉及时间：mock 后端按真实时间推进，一份工需要 2–4 小时；等不及时，就用演示库验证“已完成”的状态。

1. **入住**：注册 → `GET /adoption/candidates` → `POST /adoption/adopt`（幂等键）→ `POST /onboarding/move-in {"public_posts": true, "habitat": "seaside"}`。
   - 期望：`step=active`；`GET /home/place` 返回海边片区，`can_change=true`。
2. **身份卡与账户**：`GET /credentials`。
   - 期望：宠物 ID、星球银行卡、照护档案为 `active`，其余 5 类为 `not_obtained` 并带 `condition`，房卡显示“暂未开放”；刷新后编号与签发时间不变。
   - 打开银行卡详情：余额 20，流水里有“入住欢迎旅费”。
3. **工作收入**：出发站选一个 `work:*`。可以用 `POST /journey/suggest` 等 TA 自己决定，也可以用 `POST /journey/depart` 立即触发。
   - 期望：`GET /jobs` 依次为 `going`、`working`、`done`，`paid` 为 true；银行卡流水多一笔 `web_job_income`；通讯器收到“……干完啦，赚了 N，已经存进我的银行卡”；时间线出现工资记录。
   - 刷新多次，工资只有一笔。
4. **驾校报名与练习**（页面 `/circle` → 爪爪驾校 → `/school`）：陪 TA 报名 → 科目一“做一套练习题”。
   - 期望：练习答完一题马上讲解；科目二可单项练习（直线倒车、转向与回正、倒车入库、侧方停车、弯道行驶），有预测轨迹与目标车位提示。
5. **正式考试失败与补考**：约科目一首次考试（确认框写明首次＋补考、两次不过等 7 天、点开始才计次）→ 故意答错几题交卷。
   - 期望：成绩单有错题回顾与 TA 的话，下一步是“补考”；再失败一次后进入冷却，`/driving` 的 `cooldown_until` 为第二次结算时间＋7×24 小时，约考返回 409 `cooldown`，练习照常。
6. **科目二、三**：开考后中途暂停、离开考场、回来接着考。
   - 期望：回来时剩余时间、位置与扣分不变；压线、碰锥、红线（闯红灯、冲进有居民的人行横道）按规则处理，红线自动制动并当场结算；成绩单能回放并在时间轴标出扣分。
7. **拿证**：四科全过那次结算。
   - 期望：`GET /driving` 的 `stage=licensed`、`voucher_available=true`；`GET /credentials` 里驾驶证为 `active`；`/school/ceremony` 盖章、合影，台词“以后，换我载你去看世界”；再次打开只是回看。卡包里只有一本驾驶证。
8. **自驾**：`GET /journey/destinations` 出现 `local:drive_trip`（`modes=["drive"]`）→ 出发。
   - 期望：交通段 `mode=drive`、`role=driver`；时间线出现“第一次自己开车”。
   - 反向检查：没拿证时自驾返回 403 `FORBIDDEN`（`reason=no_license`），打车 `local:city_trip` 照常可以出发。
9. **消息与收藏**：通讯器里依次有：
   - 报名；
   - 每次正式考试的结算（“科目一这次没过。……”“科目二过啦！……”）；
   - 冷却结束时“驾校说科目一又可以约考试啦……”（每轮一次）；
   - “我拿到驾照啦！编号 …”（只出现一次）。
   - 自驾或进城回来后，`GET /collection` 有 `postcard`，`GET /guides` 有这次的攻略（`status=completed`，`visited` 包含实际到过的站点），时间线串起全过程。

每一步都要检查：页面显示和服务端状态一致；重复点击和网络重试不产生重复记录；刷新后编号与时间不变；访问另一个账号的资源返回 404。

## 附：相对 0.2.4 的接口变化（0.2.5，历史记录；其中驾考三行已被 0.3.0 的爪爪驾校替换，见下一节）

| 变化 | 类型 | 影响 |
|---|---|---|
| `GET /driving/practice` 的响应从 `DrivingQuestion[]` 改为 `PracticeSet {practice_id, part, questions, created_at}` | 结构变化 | 前端还没接，现在接入正好 |
| `POST /driving/practice` 请求体新增必填 `practice_id`；必须带幂等键；响应新增 `practice_id`、`submitted_at` | 结构变化 | 同上 |
| `POST /driving/exam` 必须带幂等键 | 规则变化 | 同上 |
| `DrivingStage` 新增 `license_pending` | 追加枚举值 | 需要能显示“签发中” |
| `PetDNAView.behavior`（`PetBehavior` 等 8 个新类型） | 追加可选字段 | 旧代码不受影响 |
| `backend_version` 改为 web-mvp-0.2.5 | 元数据 | 可以用来区分新旧后端 |
| 银行卡流水不再有 0 元旅费；时间线回家标题与同一时刻的顺序修正 | 数据修正 | 无 |

## 附：0.3.0 的接口变化（爪爪驾校）

| 变化 | 类型 | 影响 |
|---|---|---|
| 删除 `GET/POST /driving/practice`、`POST /driving/exam` 及其模型（陪练组、考试请求与结果、旧的驾考进度） | **破坏性** | 前端从未接入旧接口；驾校页面已按新接口实现 |
| `GET /driving`、`POST /driving/enroll` 改为返回 `DrivingSchoolStatus` | **破坏性** | 同上 |
| 新增 `GET /driving/curriculum`、`/driving/sessions/**`（建局、开始、作答、上传操作、暂停、交卷、放弃）、`GET /driving/history`、`POST /driving/ceremony` | 追加 | 见 §4.5 |
| 新增模型：`SchoolSubject`、`SchoolStage`、`SubjectState`、`SessionMode`、`AttemptKind`、`SchoolSessionState`、`SessionBrief`、`SubjectStatus`、`CoachInfo`、`DrivingSchoolStatus`、`SchoolCurriculum`（含 `reasons`）、`QuizQuestionView`、`QuizAnswer`、`QuizFeedback`、`InputEvent`、`SimEvent`、`DriveProgress`、`SessionResult`、`SchoolSession`、`InputChunk`、`InputResult`、`CeremonyResult` 等 | 追加 | 生成契约 0.3.0 |
| 考局状态枚举命名为 `SchoolSessionState`（避免与登录的 `SessionState` 重名）；`gen_web_contract.py` 遇到重名直接拒绝生成 | 约束 | — |
| 新增插槽 `circle.places`（星球圈“星球上的地方”），驾校入口卡片 | 前端共享入口 | 宿主 `features/social/pages.tsx` 已放置 |
| 迁移 `m1430_driving_school`：`web_school_subjects`、`web_school_sessions`（部分唯一索引：每只宠物最多一场未结束的正式考局）、`web_driving.ceremony_at` | 数据 | 启动时自动执行；旧驾考表不再写入，已持证的宠物保留驾照（科目显示“旧版驾考已通过”） |
| `backend_version` 改为 web-mvp-0.3.0 | 元数据 | 可以用来区分新旧后端 |
