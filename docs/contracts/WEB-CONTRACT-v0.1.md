# PetSoul 网页契约 v0.1（R0 冻结）

> 历史版本：当前实现以 [WEB-CONTRACT-v0.2](WEB-CONTRACT-v0.2.md)（0.2.0）为准。

状态：**R0 冻结**，2026-09-22，由框架窗口 `claude-20260922-014933-307b` 产出，依据 [总方案 v1.4](../product/PETSOUL-2.0-MASTER-PLAN.md) §7–§10 与寻味/交通/接待三个专题。

本文件说明语义；**字段与枚举的唯一代码来源是后端 `PetJourneyBackend/app/schemas/web/`（Pydantic）**。以下生成物与代码保持一致，由门禁检查：

| 生成物 | 路径 | 用途 |
|---|---|---|
| 前端类型 | `PetJourneyWeb/src/shared/contracts/generated.ts` | 93 个 DTO、68 个枚举（含 `*Values` 常量）、`WEB_ENDPOINTS` 端点表 |
| JSON Schema | `docs/contracts/generated/web-contract.schema.json` | 其他语言/工具消费 |
| 路由表 | `docs/contracts/generated/WEB-ROUTES.md` | 从 FastAPI **实际注册**的 44 条路由生成：方法、路径、请求/响应、登录、CSRF、幂等 |
| fixture 样例 | `docs/contracts/examples/r0-fixtures.json` | 前端 fixture 导出，已用 Pydantic 逐条校验 |

门禁：`python scripts/gen_web_contract.py --check`（或 `npm run contract:check`）——生成物过期或前端 fixture 导出不符合 Pydantic 模型即 exit 1。

---

## 1. 通用约定

| 项 | 约定 |
|---|---|
| 前缀 | 新网页 API 一律 `/api/v1/web`；旧 `/api/v1/*`（iOS）保留不变，不得另起前缀 |
| ID | 稳定字符串；来源实体带命名空间（`amap:` / `google:` / `fixture:` 分店、地点 ID） |
| 时间 | 存储与传输为 UTC ISO 8601（`2026-09-22T07:35:00Z`）；当地展示用随附的 IANA 时区（`Asia/Hong_Kong`）；日期为 `YYYY-MM-DD` |
| 金额 | 整数。游戏币 `travel_coin`（唯一游戏币口径）；现实价格 `MoneyAmount{amount_minor, currency}`，两者不混算 |
| 分页 | 游标：`{items, next_cursor}`；`next_cursor=null` 表示没有更多 |
| 数据来源 | 关键 DTO 带 `data_origin: fixture | live`。live 响应不得静默混入 fixture |
| 能力 | 未实现 → 501 `CAPABILITY_UNAVAILABLE`；缺配置/密钥 → 503 `NOT_CONFIGURED`；产品关闭 → `disabled`（见 `/meta` 的 capabilities）。**禁止用伪造的 200 表示未实现功能** |
| 快照 | 权威状态带 `server_time` 与 `version`；客户端插值只用于呈现，不结算、不决定到达或宠物位置 |
| 缓存头 | `/api/v1/web/*` 响应均带 `Cache-Control: no-store` 与 `X-Request-ID` |

`GET /api/v1/web/meta`（公开）返回契约版本、服务器时间、能力清单（36 项）与已应用迁移，是前端判断“哪些能力已接入”的唯一来源。

## 2. 会话、身份与权限

- **网页会话**：同源 HttpOnly cookie `petsoul_session`（JWT，`typ=web_session`，含 `sid`，SameSite=Lax，`Secure` 由 `PETJOURNEY_WEB_COOKIE_SECURE` 控制，默认开）。签发/清除原语在 `app/web_platform/session.py`：`issue_web_session`、`set_session_cookies`、`clear_session_cookies`；会话吊销检查通过 `app.state.web_session_revocation_check` 钩子由身份模块提供。
- **CSRF**：cookie 会话的 POST/PUT/PATCH/DELETE 必须带请求头 `X-CSRF-Token`，值等于非 HttpOnly cookie `petsoul_csrf`（双提交）。统一客户端自动回填。Bearer 客户端不受 CSRF 约束。
- **旧 iOS Bearer 兼容**：`Authorization: Bearer <既有会话 JWT>` 同样被 `/api/v1/web` 接受（`auth_method=apple_bearer`）。
- **登录级别**（见 WEB-ROUTES）：`public` / `optional` / `required`。有凭据但无效或过期 → 401 `SESSION_EXPIRED`，**不静默降级为匿名**；无凭据访问 required 路由 → 401 `AUTH_REQUIRED`。
- **资源归属**：所有带 `pet_id`、`session_id`、`note_id` 等的路由，实现方必须按 `principal.user_id` 校验归属；不存在与不属于调用者统一返回 404，避免 ID 枚举。
- **R0 状态**：用户名+密码注册/登录**未实现**（`/auth/register`、`/auth/login` 返回 501）；前端 fixture 模式也不提供假登录。口令哈希库由身份模块在实现时选定并登记（`requirements.txt` 为共享文件）。
- **注册 → 归属 → 可选接待 → 入住**：`OnboardingStep = needs_companion → reception_optional → ready_to_move_in → active`。网页建立宠物（`POST /pets`、`POST /adoption/adopt`）**不开启旅程**；入住激活是单独动作（`POST /onboarding/move-in`）。旧 `POST /api/v1/create_pet` 会立即 `create_initial_journey`，网页门面不得复用该副作用。

## 3. 错误信封

所有 `/api/v1/web` 错误：

```json
{"error": {"code": "VERSION_CONFLICT", "message": "内容已在别处更新，请刷新后再试。", "request_id": "req_1b4b7e1983e541cf", "retryable": false, "details": {"expected": 3, "current": 4}}}
```

- `code` 稳定，前端只按 code 分支；`message` 可读，不含堆栈/SQL/密钥；校验错误的 `details.errors` **不回显输入值**（请求体可能含口令或倾诉）。
- `request_id` 同时出现在响应头 `X-Request-ID`；客户端可传入合法的 `X-Request-ID` 贯穿日志。
- 旧 `/api/v1/*` 保持原 `{"detail": ...}` 形态（iOS 兼容）。

| code | HTTP | 含义 |
|---|---|---|
| AUTH_REQUIRED | 401 | 需要登录 |
| SESSION_EXPIRED | 401 | 凭据无效/过期/用户不存在 |
| CSRF_FAILED | 403 | cookie 会话写操作缺少或不匹配 CSRF |
| FORBIDDEN | 403 | 有登录但无权限（优先用 404 隐藏他人资源） |
| NOT_FOUND | 404 | 资源不存在或不属于调用者；未知路由 |
| VALIDATION_FAILED | 400/422 | 请求格式不符 |
| CONFLICT | 409 | 状态冲突（例如作物未成熟） |
| VERSION_CONFLICT | 409 | revision/version 过期（草稿、媒体会话、叮嘱更正） |
| IDEMPOTENCY_KEY_REQUIRED | 400 | 需要幂等键的写操作缺少 `Idempotency-Key` |
| IDEMPOTENCY_KEY_REUSED | 409 | 同键不同请求 |
| IDEMPOTENCY_IN_PROGRESS | 409 | 同键请求仍在处理（retryable） |
| CAPABILITY_UNAVAILABLE | 501 | 能力未实现 |
| NOT_CONFIGURED | 503 | 缺配置/密钥 |
| RATE_LIMITED | 429 | 限流 |
| UPSTREAM_UNAVAILABLE | 502/503 | 上游不可用（客户端也用它表示网关 502） |
| INTERNAL_ERROR | 500 | 未处理异常（retryable） |
| USERNAME_TAKEN / INVALID_CREDENTIALS | 409 / 401 | 身份模块 |
| ADOPTION_TAKEN | 409 | 专属领养竞争失败：同一只最多一人成功 |
| PET_NOT_ACTIVATED | 409 | 还没有建立专属伙伴/未入住（`details.onboarding_step`） |
| DRIVING_BLOCKS_VIDEO | 409 | 宠物驾驶中请求视频活动 |
| CONTROL_LEASE_HELD | 409 | 媒体控制租约被其他设备持有 |
| ITINERARY_CHANGED | 409 | 行程版本已变（寻味/出发前复核） |
| DRAFT_EXPIRED | 410 | 接待草稿已过期 |

客户端另有 `NETWORK_ERROR` / `TIMEOUT` / `ABORTED`（仅前端 `ApiError`，不会由服务端返回）。

## 4. 幂等

- 有副作用的写操作带请求头 `Idempotency-Key`（8–128 字符 `[A-Za-z0-9_\-:.]`）；WEB-ROUTES 中“幂等键=必填”的路由缺键返回 400。
- 服务端按 `(user_id, scope, key)` 绑定请求摘要（`app/web_platform/idempotency.py::IdempotencyStore.run`）：同键同请求 → 返回首个成功结果；同键不同请求 → 409 `IDEMPOTENCY_KEY_REUSED`；处理中 → 409 `IDEMPOTENCY_IN_PROGRESS`；handler 失败 → 删除占位，可用同键重试。
- 客户端：**一次用户动作一个键，失败重试复用同一个键，成功后才换新键**（`newIdempotencyKey(scope)`）。
- 局限：幂等记录与业务写入不在同一事务。收获、互偷、扣费、领养、点赞、发帖、收费任务还必须在领域表上设唯一约束（例如既有 `economy_transactions.idempotency_key UNIQUE`）。
- 通讯发送沿用旧引擎的 `(pet_id, client_message_id)` 去重：`SendMessageRequest.client_message_id` 即幂等键。
- 版本冲突与幂等分开：带 `draft_revision` / `session_revision` / `expected_version` 的请求，旧版本返回 409 `VERSION_CONFLICT`。

## 5. 可见性与记忆用途

- 私有 DTO（`HomeSnapshot`、`PetPrivateSummary`、`ReceptionSession`、`CareNote`、`FoodPreference`、`MessageThread`…）只发给归属主人。
- 公开投影只用明确的公开 DTO：`PetPublicProfile`、`Post`、`Comment`。公开 DTO 不含主人私密资料、接待原文、饮食限制（`DietaryRestriction.private` 恒为 true）。
- 行动者 `ActorRef.actor_kind = pet | npc | owner`，`is_real_household` 区分真实账号家庭与 NPC；NPC 不冒充真实玩家；计数来自已执行动作。
- **MemoryPolicy**（`app/reception/policy.py::project_memory`，前端镜像 `src/shared/memory/policy.ts` 仅供 fixture/测试）：在检索/摘要/生成**之前**按 宠物归属、`target=give_to_pet`、已确认、未撤回、未被 supersede、用途在 `purposes` 内、存在对应版本且未撤回的 `MemoryGrant` 过滤。`owner_private` 与 `inference` 永不进入投影。任何消费者只拿 `MemoryProjection`，不直接读旧 `memories` 表或原始对话。
- `HomeWelcome` 只能由 `purpose=home_interaction` 的投影生成，只兑现当前支持的槽位（`owner_title` / `favorite_object` / `interaction_boundary`）。
- 撤回/更正：先使 grant 失效（停止使用），再经 `WebTaskQueue.supersede_pending("reception:note:<note_id>:")` 使待生成任务失效，最后清理衍生物；结果区分 `usage_stopped / cleanup_pending / cleanup_done`。

## 6. 领域契约摘要

完整字段见 generated.ts；以下只写跨模块必须遵守的语义。

### 6.1 家园、钱包、农场
- `HomeSnapshot{home_id, server_time, version, pet, presence, guard, wallet, plots, journey, welcome, unread, missing_capabilities, data_origin}`。`presence` 是宠物唯一位置（`at_home / in_transit / at_destination / visiting / returning / not_activated / unknown`）；在外就不能在家守菜。
- 钱包：只有 `WalletSummary{currency="travel_coin", balance, updated_at}`，经 EconomyAdapter 映射既有 `pet_wallets.travel_coin`。**不新建可独立写入的家园金币余额**；`owner_funds` 其他预算字段保留原语义。
- `FarmActionRequest{home_id, plot_id, cycle_id, action: plant|harvest|steal, crop_key}` + 幂等键；可偷总额 `steal_total/steal_remaining` 为本批全体访客共享。
- R0 live：`GET /home` 经旧存储只读适配（宠物 + 钱包）；旧模型无在家/守护/菜园概念，因此 `presence=unknown`、`plots=[]`，并在 `missing_capabilities` 列出，不伪造。

### 6.2 宠物与专属领养
- `PetPrivateSummary.owner_title` 只在主人确认后出现；旧 DNA 的 `owner_title` 默认值不视为主人确认（R0 适配器返回 null）。
- `AdoptionCandidate.availability = available | reserved | adopted`；`source_note` 未知即 null，不编造。领养原子占用，竞争失败 409 `ADOPTION_TAKEN`。

### 6.3 旅途、到访
- `VisitState = planned → travelling → arrived → active → completed`，另有 `cancelled`。
- `Visit.recommendation_id` 可引用寻味推荐，但推荐 ID 不等于到访；到访由 Journey 服务在确认下一站时创建。`interior_is_original=true`：店内为原创场景，真实商家资料（`Place`）分开展示，缺失字段为 null。

### 6.4 平行交通（地图即主界面）
- 现实参考 `TransportReference`（服务端核验用）与动物世界身份 `WorldService{carrier_name, service_code, mapping_version}`（界面展示）分离；同一运营实例稳定映射（内部键 `world_service_key(provider, operating_instance_id, service_date, origin, destination, segment_seq)`，持久化唯一约束）。
- `JourneyLeg{kind: main|connection|wait|transfer, mode: flight|train|ferry|drive|transit|taxi|walk, role: driver|passenger|walker, times: LegTimes, time_basis, freshness, position_basis, phase, itinerary_version, route}`。
- `LegTimes` 计划/预计/实际三组时间**分别可缺省**，schema 不把实际默认为计划。
- `TimeBasis = verified_timetable | live_status | routed_estimate | demo_fixture`；`DataFreshness = verified | stale | unavailable`；`PositionBasis = simulated_route | schematic | live_vehicle`。有 source_url 或模型高置信 ≠ verified。插值中转节点 `TransportNode.verified=false` 且按 schematic 呈现。
- 进度只由服务器时间与已确认时间线决定（`transport_world.timeline.leg_progress`）；下一站冲突用 `schedule_after_leg` 顺延，**不压缩交通**。
- 地图入口：`MapActivityEntry{leg_id, activity_id, badge: music|tv, badge_state, media_session_id, actions}`，只由实际 `TravelActivity` 产生；无活动不下发。前端固定组件：VehicleMarker（transport）/ ActivityBadge + MediaSheet（companion_media），深链接 `/journey?sheet=leg:<id>` 或 `?sheet=media:<id>`。**不设舱室路由**。

### 6.5 同行影音（独立时钟）
- `MediaAsset{edition, duration_ms, availability: in_app_sync|external_link|unavailable, license: MediaLicense}`；`external_link` 永不标同步；`LicenseStatus.self_generated_test` 仅测试。
- 锚点：`playing: position = clamp(anchor.position_ms + elapsed_server_ms × rate, 0, duration)`；`paused/interrupted: position = anchor.position_ms`（后端 `companion_media.position_at`，前端 `shared/media/anchor.ts`）。
- `CompanionSession{state, anchor, revision, resume_policy, control: ControlLease, saved_progress_ms, interrupt_reason, video_allowed}`：驾驶中 `video_allowed=false`；抵达中断并保存进度，不等待播放器。
- 控制命令带 `session_revision` + 幂等键；控制租约只有持有设备或租约过期后可控。
- `Participation.mode = not_joined | joining | synced | solo | buffering | blocked | failed | left`；只有 `synced` 且偏差 ≤ 1s（音频）/2s（视频，待实测目标）且心跳 ≤30s 才累计 `counted_ms`。
- 与图片生成 `MediaJob` 是不同实体；私密通讯复用既有 communicator。

### 6.6 寻味（两种模式、两套偏好）
- `FoodMode = pet_virtual_explore | owner_real_dining`。宠物模式只接受 `pet_context: PetArrivalContext{journey_id, itinerary_version, leg_id, feasible_arrival_utc, stay_window_start/end_utc, destination_timezone}`；主人模式只接受 `owner_context: OwnerDiningContext{plan_date, meal_time_local, timezone, city}`（`food_discovery.validate_request_context` 强制互斥）。
- `FoodRecommendation.scores = {quality, match, value, logistics, uncertainty}` 各自可缺省；不输出满意概率。`eligibility`、`group`、`rank`、`reasons`、`not_suitable_when`、`unknowns`、`provenance{fact_version, preference_version, rule_version, data_status, coverage_note}`。
- `SourceRating.source_rating_count`（平台总数）与 `observed_sample_count`（实际取得）分开。
- `REAL_QUALITY_SOURCES = merchant_menu | licensed_review | owner_feedback | partner_note`；`fixture`、虚拟吃饭、AI 图、游戏点赞永不进入现实品质证据。
- 行程版本变化 → `freshness=needs_recheck`（`recommendation_freshness`）。`FoodFeedback.verification = self_reported | verified`，不同于虚拟到访。

### 6.7 接待与入住叮嘱
- `ReceptionSession{branch: own_pet|adopted, mode: guided_notes|model_conversation, status, host, turns, candidates, draft_revision, draft_expires_at}`；接待角色名可配置，`is_ai=true` 且有披露文案，不是管理员。
- `IntakeCandidate{kind: habit|shared_story|wish|letter|owner_private|inference, subject: pet|owner|relationship, source_turn_id, source_excerpt, suggested_slot}` —— **没有任何“已授权”字段**。
- `CareNoteDecision{text, target: give_to_pet|keep_here|do_not_save, purposes[], slot, slot_value}`；`owner_private` / `inference` 只能 `keep_here` 或 `do_not_save`（前端 UI 与后端实现都要拦）。
- `IntakeConfirmationRequest{session_id, draft_revision, decisions}` + 幂等键 → `IntakeConfirmationResult{persist_state: persisted|failed, notes, grants, onboarding}`。**只有 persisted 才可以说“记好了”**。

### 6.8 星球圈、通讯、收藏、市场
- `Post{author: ActorRef, source_event_id, visit_id, visibility, reaction_count, comment_count, viewer_reacted}`；`PostMedia.generated=true` 表示 AI 生成图，不代表真实到店照片。
- `MessageDeliveryState = sending | delivered | awaiting_reply | processing | failed`（信号语言，不用“正在输入”）。
- `CollectionItem{tradable, bound_to_pet}`；市场能力 `market.player_listing=disabled`，NPC 商店不等于玩家市场。

## 7. fixture / live 模式（前端）

- `VITE_PETSOUL_DATA_MODE=fixture|live`，全局显式；fixture 模式页面顶部常驻“演示模式”标识，数据带 `data_origin=fixture` 与“演示”标签。
- live 模式只走统一客户端访问 `/api/v1/web`；某模块没有 live 实现或后端返回 501，页面显示“尚未接入”，**绝不回退到 fixture**（`shared/services/registry.tsx::unavailableService`）。
- fixture 来源统一在 `src/fixtures/`，文件头注明来源；fixture 通过 `tests/fixtures.contract.test.ts` 导出并由 Pydantic 校验。

fixture 样例（节选，完整见 `examples/r0-fixtures.json`）：

```json
{"entry_id": "entry-fx-act-flight-music", "leg_id": "fx-leg-flight", "activity_id": "fx-act-flight-music",
 "badge": "music", "badge_state": "active", "media_session_id": "fx-ms-flight",
 "label": "TA 在听《窗边的小调》", "actions": ["join", "solo", "open_leg_card"]}
```

```json
{"world_service_id": "fx-ws-cat222", "carrier_name": "喵航", "service_code": "Cat222", "mode": "flight",
 "vehicle_style": "橘色机尾", "reference_id": null, "mapping_version": 1}
```

以上承运身份与行程均为 `time_basis=demo_fixture` 的演示数据，不对应任何真实班次。

## 8. 旧接口与已知缺口（必须由对应模块覆盖）

**旧路由权限**（HEAD 980feab 只读核对）：除 `/api/v1/me`、`/api/v1/me/claim_pet` 外，旧宠物级接口（`/api/v1/pets/{pet_id}/*` 的通讯、记忆、经济、旅行、轨迹、生图，以及 `/api/v1/pet_dna|agent_status|day_plan/{pet_id}`）不校验调用者；`/api/v1/scheduler/tick` 可匿名推进世界；`/api/v1/*/config` 暴露供应商配置；`/media/*` 静态目录全量公开上传文件；`/docs` 与 `/openapi.json` 默认开放。

R0 提供统一接入：`PETJOURNEY_LEGACY_API_POLICY`（`app/web_platform/legacy_guard.py`）
- `open`（默认，保持 iOS/测试现状，**不可用于公开网页部署**）；
- `owner_bearer`：旧接口需 Bearer，宠物级路径须是主人（不存在/非本人统一 404），调度/调试/配置/demo/轨迹需 `X-PetJourney-Admin-Token`；
- `closed`：只保留 `/health`、Apple 登录与 `/api/v1/web`，其余旧 `/api/v1/*` 404。
仍未覆盖：`/media` 私有化（媒体/身份模块）、`/api/v1/feedback` 等 body 内 pet_id 的细粒度校验、`/docs` 关闭（部署配置）。公开网页部署前必须选择 `owner_bearer` 或 `closed` 并完成对应验证；iOS 客户端是否发送 Bearer 需实测。

**旧引擎差异**（不改名、不接管，按专题由后续模块处理）：
- `street_rank.PetStreetRankEngine.rank()`：对 `places[:10]` 上游顺序算分后未重排；分数含照片/距离/天气——**不能改名为餐食品质分**。
- `transport_schedule/openai_provider.py`：名称含 WebSearch，实际走 `/chat/completions` 且提示词写明无实时网络——输出不能标 `verified_timetable`。
- `world_simulation/timeline.py`：move_end 取下一站开始与按时长计算的较早者——会压短交通。
- `transport_reality/mock.py::_candidate_endpoint`：中转节点坐标插值——只能 `verified=false` + schematic。
- 现实承运人/班次直接进展示字段——网页只展示 `WorldService`。
- `update_pet_dna` 会写入记忆；`list_memories` 按 pet_id 读取、无用途过滤——未确认候选不得调用，消费者必须经 MemoryPolicy。
- `requirements.txt` 固定 `fastapi==0.115.12`、`pydantic==2.11.4`，本机实际安装 fastapi 0.119.0 / pydantic 2.12.3；R0 测试在本机版本上运行，部署镜像需按 requirements 重验。

## 9. 变更流程

1. 修改契约的窗口在自己日志登记 SCOPE_CHANGE，说明消费者影响；共享 DTO 文件由共享入口维护者（见 MODULE-MAP）合入。
2. 改 Python DTO → `python scripts/gen_web_contract.py` → 同步本文件语义 → `--check` 通过。
3. 破坏性变更升 `WEB_CONTRACT_VERSION`（`app/schemas/web/common.py`）并在交接中列出受影响模块；非破坏性新增（可缺省字段、新枚举值需评估前端穷举）记录在本文件末尾的变更记录。

变更记录：
- 0.1.0（2026-09-22）：R0 初版冻结。
