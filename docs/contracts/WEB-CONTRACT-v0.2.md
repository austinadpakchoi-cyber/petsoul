# PetSoul 网页契约 v0.2（MVP · 0.2.1 真实供应商 · 0.2.2 网页底图 · 0.2.3 宠物自主世界 · 0.2.4 证件与驾考 · 0.3.0 爪爪驾校）

状态：**MVP 实现版**，2026-09-22，框架窗口 `claude-20260922-014933-307b`。v0.1（R0 冻结）保留在 [WEB-CONTRACT-v0.1.md](WEB-CONTRACT-v0.1.md) 作历史；本文件描述当前已实现的语义，依据 [总方案 v1.5](../product/PETSOUL-2.0-MASTER-PLAN.md) 与寻味/交通/接待/意图四个专题。

**字段与枚举的唯一代码来源仍是后端 `PetJourneyBackend/app/schemas/web/`（Pydantic）**，`WEB_CONTRACT_VERSION = "0.4.1"`：

| 生成物 | 路径 | 内容 |
|---|---|---|
| 前端类型 | `PetJourneyWeb/src/shared/contracts/generated.ts` | 178 个 DTO、101 个枚举（含 `*Values` 常量）、`WEB_ENDPOINTS`；枚举与模型共用命名空间，重名时生成脚本直接拒绝 |
| JSON Schema | `docs/contracts/generated/web-contract.schema.json` | 其他语言/工具消费 |
| 路由表 | `docs/contracts/generated/WEB-ROUTES.md` | 从 FastAPI 实际注册的 94 条路由生成：方法、路径、请求/响应、登录、CSRF、幂等 |
| fixture 样例 | `docs/contracts/examples/r0-fixtures.json`；`npm test` 导出到 `PetJourneyWeb/.runtime/contract-examples/`（含 `driving-school.json`） | 前端 fixture 导出，Pydantic 逐条校验 |

门禁：`python scripts/gen_web_contract.py --check`（`npm run contract:check`）。

---

## 1. 通用约定（与 v0.1 相同）

前缀 `/api/v1/web`；UTC ISO 8601 + IANA 时区；唯一游戏币 `travel_coin`（整数），现实价格 `MoneyAmount`；游标分页；`data_origin: fixture | live`；未实现 501 `CAPABILITY_UNAVAILABLE` / 缺配置 503 `NOT_CONFIGURED` / 产品关闭 `disabled`；权威快照带 `server_time` 与 `version`；`Cache-Control: no-store` 与 `X-Request-ID`。

`GET /meta` 的能力清单（48 项）随配置变化：供应商总开关关闭时，高德、网页底图、Google、路线估时、接待模型、英雄图为 `not_configured`；开启且密钥可用时它们变为 `available`（Google 若被拒则如实保持 `not_configured` 并写明原因，见 §9）。始终 `not_implemented`：邮箱找回、真实原型档案、核验时刻表、授权作品清单、真实寻味资料；始终 `disabled`：扫街榜、实时动态、接待语音、玩家挂牌；意图层默认 `disabled`（mode=off）。页面以它为准显示“未接入/未配置”，不伪造。

## 2. 会话、身份、入住

- 用户名+密码（3–32 位 `[A-Za-z0-9_.-]`，口令 ≥8），服务端 **scrypt**（标准库 `hashlib.scrypt`，无新增依赖）；登录失败按“用户名+来源”限流（5 分钟 8 次 → 429 `RATE_LIMITED`）。
- 会话：HttpOnly cookie `petsoul_session`（JWT `typ=web_session`，含 `sid`），**服务端 `web_sessions` 表可吊销**：退出即吊销，签名正确但记录不存在/已吊销/过期 → 401 `SESSION_EXPIRED`（前端当作未登录并回欢迎页）。CSRF 双提交 `petsoul_csrf` / `X-CSRF-Token`。iOS Bearer 仍兼容。
- 入住阶段 `OnboardingState{step, pet_id, home_id, reception_session_id, reception_skipped, home_activated_at, pet_origin}`：`needs_companion → reception_optional → ready_to_move_in → active`。`pet_origin` 决定接待分支（自己的宠物 / 领养）。
- `POST /onboarding/move-in {public_posts}`：激活家（与接待分开；**不自动出发**），种下欢迎作物、发一次 20 旅费见面礼（幂等键 `web:welcome_gift:<home_id>`）。`public_posts` 由主人选择，默认不公开；之后可在 `PATCH /settings` 改。
- 每账号一只当前宠物、一个家（重复建立 409 `ALREADY_HAS_COMPANION`）。iOS 旧宠物不会被静默当作网页之家。

## 3. 错误信封

形态同 v0.1。新增稳定 code：`ALREADY_HAS_COMPANION`、`MEDIA_REJECTED`（上传格式/大小）、`INSUFFICIENT_FUNDS`、`ALREADY_TRAVELING`、`FARM_GUARDED`（宠物在家或主人巡院）。领域冲突的 `details.reason` 细分：`not_ripe / occupied / no_seed / already_taken / nothing_left / cooldown / pet_home / not_enough / expired / no_journey / too_late / stale_recommendation …`，前端按 code + reason 分支。

## 4. 幂等与版本

同 v0.1：写操作 `Idempotency-Key`（8–128 字符），`(user, scope, key)` 绑定请求摘要。领域表另有自然键去重：账本 `economy_transactions.idempotency_key`、库存 `web_inventory_moves.source_key`（`harvest:<cycle>` / `steal:<cycle>:<user>` / `sell:<pet>:<key>` / `order:<order_id>`）、世界事件 `(journey_id, event_key)`、收藏 `(pet_id, source_event_id, kind)`、动态 `source_event_id`、偷菜 `(cycle_id, thief_user_id)`、领养候选条件更新、旅程“每宠物一段进行中”唯一部分索引。版本：`draft_revision`、`session_revision`、`expected_version`、`expected_itinerary_version` → 409 `VERSION_CONFLICT`。

## 5. 可见性与记忆

同 v0.1（MemoryPolicy 在检索前过滤；`owner_private`/`inference` 永不投影）。新增兑现点：
- HomeWelcome（`home_interaction`）、通讯称呼（`private_chat` 的 `owner_title`）、出发站愿望匹配（`travel_preference` 的 wish）、旅行安静偏好（`travel_mood` → 活动只放音乐）、冒险故事中的物件（`private_chat` 的 `favorite_object`）。
- 更正：先撤销旧版本授权，再写新版本（`supersedes_note_id`）；槽位值按新文字重新建议，无法确定时清空（不沿用旧称呼）。撤回后投影立即不含该条。
- 公开主页：主页私密但主人同意公开动态时，只给动态作者最小名片（名字/物种/计数，无头像与简介）；`viewer_follows`、`is_own` 由服务端计算。

## 6. 领域语义（MVP 新增/变化）

### 6.1 家园、守护、仓库、集市
- `HomeSnapshot` 新增 `pantry: InventoryItem[]`；`GuardState{guarding, basis: pet_at_home|owner_patrol|none, until, next_patrol_at}`。**宠物外出且主人未巡院时 `guarding=false`**（v0.1 的“外出即 owner_patrol”已废止）。
- `POST /farm/patrol`：宠物外出时主人巡院 10 分钟、冷却 30 分钟；巡院中偷菜 409 `FARM_GUARDED`。
- 收获与偷菜得到**物资**进仓库（`FarmActionResult.gained_items`、`StealResult{gained_item_key, gained_units}`），不直接给币；`GET /market` → `MarketView{pantry, wallet, orders, player_listing_enabled=false, player_listing_note}`；`POST /market/sell {item_key, qty}` 按作物固定价（杂货铺，NPC）入账；`POST /market/orders/{id}/fulfill` 居民订单（每天两张、出价约为杂货铺 1.5 倍、每单一次）。旅费仍只写 `pet_wallets.travel_coin`。
- 稀有作物需要旅行带回的种子（`CollectionItem.kind=seed`，`item_key` 为作物键），种下即消耗，并发种植失败退回种子。

### 6.2 旅程、到访、世界事件
- `GET /journey/destinations` → `DestinationOption{fee, total_minutes, modes, time_basis=demo_fixture, wish_match, affordable}`；`POST /journey/depart` 扣旅费（`web:travel_fee:<journey_id>`）并返回地图快照。
- `JourneyMapSnapshot` 新增 `lifecycle`、`destination_title`、`current_visit_id`（仅在店里时）、`planned_visit_id`（出发即确定）。从未出发 `GET /journey/map` → 404 `details.reason=no_journey`；已回家返回最近一次（`lifecycle=completed`）。
- 世界事件（`departed / leg_arrived / visit_started / visit_ended / photo_taken / adventure / returned_home`）按时间补齐、每个只生效一次、失败保持顺序等待下次读取；终点段（到店/到家）的到站不再单独发消息。
- `POST /visits/{id}/choice`：到店前改去寻味推荐的分店；同一事务更新到访地点与相接两段交通端点（**时间不变**）并把行程版本 +1；旧推荐 `freshness=needs_recheck`；到店后 409 `too_late`。
- 店内活动先落库再广播事件：合影生成原创插画明信片（私有，随公开动态一起公开）；和居民打招呼触发「咖啡馆小侦探」。
- 冒险事件模板（`app/web_journey/adventures.py`）：咖啡馆小侦探、海上小水手（轮渡到站）、小小飞行员（航班到站）；规则结算绑定宠物、不可交易的勋章；故事只做表达；插画见 §9（主人开启后异步生成，失败不影响勋章）。

### 6.3 同行影音
同 v0.1。前端播放器现在真实上报参与：加入 `join`、每 10 秒 `heartbeat{player_state, position_ms, media_edition}`、状态变化立即上报、离开/离开旅途页 `leave`；只有服务器判定 `synced` 的时长计入，满 30 秒在回家时生成“共同听看的回忆”。

### 6.4 寻味
同 v0.1。`PUT /food/preferences/{subject}` 保存偏好（版本 +1；饮食限制只在主人偏好、恒为私密）；宠物模式服务端以当前行程重算到达上下文（客户端传入的上下文被覆盖）；主人反馈只修正主人偏好，`verification=self_reported`，宠物模式推荐拒收现实反馈。

### 6.5 星球圈、通讯、收藏
- 动态只来自 `visit_ended` 事件且主人同意公开；每条附一条 NPC 居民留言（NPC 标识明确）。评论/回复需声明以宠物或主人身份；撤下/删除只能作者本人；屏蔽双向不可见；举报记录在案（人工审核流程未建立）。
- 通讯：宠物回复按其状态延后可见（在家 20s、店里 60s、路上 180s）；消息按可见时间与写入顺序稳定排序。
- 收藏：`CollectionItem.item_key`（种子为作物键）；种类 `postcard / seed / badge / shared_memory`。

### 6.6 意图判断层
`IntentLayer(mode: off|shadow|assist, provider: rule|configured_llm|jev)`，默认 `off`。`assist` 只调整通讯回应措辞或给出需确认的控件提议，**永不直接改行程/删记忆/公开内容**；判断器不可用 → `degraded_reason=judge_unavailable` + 澄清提议，不改用其他付费供应商。六个离线用例见 `tests/test_web_intent.py`；configured_llm 与规则基线的 20 条中文对照见 `INTENT-EVAL-20260922.md`。

## 7. fixture / live 模式（前端）

同 v0.1。live 模式新增入口守卫：带底部导航的页面只对“已登录且已入住”的账号开放；任何请求返回 `AUTH_REQUIRED/SESSION_EXPIRED` 会重新读取会话并回到欢迎页。fixture 模式不设守卫、不创建账号、不上传照片。

## 8. 旧接口与已知缺口

旧接口策略与 v0.1 相同（`open` 仅限本地；公开部署用 `owner_bearer` 或 `closed`，Caddy 示例对公网屏蔽旧接口、`/docs`、`/openapi.json`、`/media/*`）。网页照片与明信片走鉴权路由（`/api/v1/web/media/...`，私有目录，不在 `/media` 静态挂载下）。

仍未完成、需要资源或授权：海外范围的网页真实底图（港澳已接高德静态底图，见 §9；东京等仍为示意图）、Google 地图（项目未开通计费）、核验时刻表与实时动态、接待语音、Jev 判断器、真实商家菜单与口碑、授权影音作品、真实原型档案、邮箱验证/找回、上传图片解码重编码、人工审核流程、公网部署与真机测试。

## 9. 真实供应商（0.2.1 追加，均为非破坏性字段）

用户在 2026-09-22 提供并授权使用供应商配置。所有调用只在服务端进行；密钥不进前端产物、日志与响应。

| 能力 | 供应商 | 何时调用 | 失败/关闭时 |
|---|---|---|---|
| 真实地点 | 高德 Web 服务（港澳）；Google Places（其他地区） | 出发时为目的地找附近真实咖啡店；结果缓存 24 小时 | 保留演示店并如实标“演示资料” |
| 路线估时 | 高德步行/驾车；Google Routes | 出发时估算步行/打车段；time_basis=routed_estimate、freshness=verified、route 为真实道路几何（WGS-84，高德 GCJ-02 已换算） | 保留目录时长，time_basis=demo_fixture |
| 模型回信 | DeepSeek（OpenAI 兼容） | 主人在设置开启 model_replies 后，宠物私信回复由模型按 MemoryPolicy(private_chat) 投影写；MessageSummary.composed_by=model | 模板回应，composed_by=template |
| 接待模型回应 | 同上 | 主人开始接待时选择 use_model；只生成接待员的回应，便笺仍由规则摘录原话；ReceptionTurn.composed_by | 固定引导，composed_by=guided |
| 冒险插画 | 火山方舟 Seedream | 主人开启 generated_photos 后，冒险事件排一个异步生图任务；消息 photo_status=processing→ready/failed，可 retry-photo | 失败如实显示，可重画；勋章与故事不受影响 |
| 网页底图（0.2.2） | 高德静态地图（港澳及珠三角） | 旅途地图组件按范围与容器尺寸请求 `GET /map/basemap`；服务端选整数缩放级别、中心吸附 32 像素网格、尺寸取 32 的倍数，同片区复用同一张图（缓存 24 小时，`web_basemap_cache`）；图片经 `GET /media/basemaps/{basemap_id}`（需登录）原样返回，含高德标志与审图号；`center` 为 WGS-84，叠加层按 Web Mercator 投影对齐 | `available=false` + `reason`（not_configured / outside_region / daily_cap / user_limit / upstream_error），地图组件退回示意图并标“非真实底图”；海外范围不混用高德底图 |
| 意图判断器 configured_llm | DeepSeek | 仅在 intent_layer_provider=configured_llm 时构建；默认 mode=off；离线对照见 INTENT-EVAL-20260922.md | JudgeUnavailable → 澄清提议 |

- 总开关 `PETJOURNEY_WEB_PROVIDERS`（默认关闭）；每日上限 `PETJOURNEY_WEB_{LLM,IMAGE,MAP,MAP_STATIC}_DAILY_CAP`（默认 300/20/500/200；底图另有每人每日新增 40 张），计量在 `web_provider_usage`，到上限即视为不可用。
- `/meta` 能力按配置与最近一次（脱敏）错误如实声明：例如 Google 项目未开通计费时 `map.google=not_configured` 并写明原因，重启后仍保持。
- 模型名：请求的模型与服务端返回的模型分开记录（例如请求 deepseek-chat，返回 deepseek-flash）。
- 新增字段（TS 中为可选属性，旧客户端不受影响）：`SettingsView.{model_replies, model_replies_available, model_provider, generated_photos, generated_photos_available, image_provider}`、`SettingsUpdate.{model_replies, generated_photos}`、`ReceptionStartRequest.use_model`、`ReceptionTurn.composed_by`、`MessageSummary.{composed_by, photo_status}`；新增路由 `POST /communicator/{pet_id}/messages/{message_id}/retry-photo`、`GET /media/illustrations/{illustration_id}`（仅主人）。
- 生成器约定：字段 `json_schema_extra={"x-additive": True}` 在前端类型中生成为可选属性。
- 0.2.2 新增（全部追加）：`BasemapView`、`BasemapProvider`、`BasemapUnavailableReason`；路由 `GET /map/basemap`、`GET /media/basemaps/{basemap_id}`；能力 `map.basemap`。前端 `PlatformService.basemap()`，由共享地图组件内部调用，页面无需改代码（可用 `realBasemap={false}` 关闭）。

## 9a. 宠物自主世界（0.2.3，全部为追加；用户 2026-09-22 的方向）

这是情感疗愈产品：给离开的宠物一个世界，给主人慰藉；游戏性是为了留存。宠物是自主 agent，主人只给建议。

| 能力 | 接口 / 字段 | 规则 |
|---|---|---|
| 宠物 DNA | `GET/PUT /pets/{pet_id}/dna` → `PetDNAView{dna: PetDNA, confirmed, draft_sources}` | 没保存过时，草稿就是注册、领养资料和接待确认过的叮嘱；主人保存即确认。`shared_memories` 只用于私信 |
| 星球通讯器的回复时机 | `MessageSummary.{status_note, expected_reply_at, topic}` | TA 睡着时等醒来，飞行时等落地，在路上或在店里晚几分钟，在家醒着时很快；推迟的消息会排队，到点一定回复，多条合并成一次；主人情绪危机时立即以固定关怀回应，并附上求助热线；不做“正在输入” |
| TA 主动发消息 | `topic`：morning / share / goodnight / thinking_of_you / news；设置项 `pet_messages`（默认开）、`timezone` | 像微信：不按固定时段，在 TA 醒着时随机几个时刻发；话多的宠物发得多；发生了事随时可以发，不看主人在不在睡觉（目前不推送）；每天最多 6 条；主人 7 天没来就停 |
| TA 的家（概念） | `GET/PUT /home/place`；`MoveInRequest.habitat`；`HomeSnapshot.place` | 8 类共 27 个国内真实片区，坐标在片区中心 1 公里内随机偏移，只显示“城市·片区”；香港演示线路只给住在中环（默认）的宠物 |
| 日常出门与打工 | `DestinationOption.destination_key` 新增 `local:stroll`、`local:cafe`、`local:city_trip`、`work:<job>` | 有地图服务时用高德找真实地点并估算路线，否则标注为演示；打工结束时工钱存进银行卡（流水类型 `web_job_income`，按旅程号去重）；散步和打工不寄明信片 |
| 自己决定出门 | `POST /journey/suggest`、`GET /journey/suggestions`（`JourneySuggestion`） | 只在 TA 所在地白天考虑，每半小时最多决定一次；出门次数看 DNA（3/2/1）；钱不够时只散步或打工；主人的建议更可能被采纳，说“今天别出门”时多半在家，但由 TA 自己决定；`POST /journey/depart` 暂时保留兼容 |
| 菜园守护 | `NeighborHomeSummary/NeighborHomeView.watch`（`FarmWatch`） | 醒着在家时 75% 会发现小偷，打盹时 35%，主人巡院时一定偷不到；赶跑小偷、睡着时被偷，都会主动告诉主人 |
| 写实照片与邮局明信片 | `CollectionItem.{note, image_url, image_status, place, city}` | 不把宠物卡通化：冒险照片和店里合影都是写实照片（Seedream 4.5，`PETJOURNEY_WEB_IMAGE_MODEL`，至少 2048×2048，保留供应商“AI生成”水印）；进城或出远门时，TA 在回程路过邮局，写一张明信片寄给主人（开启“生成照片”时附写实自拍）；没开启时是纸质卡片，不冒充照片 |
| 攻略手账 | `GET /guides`、`GET /guides/{guide_id}`（`TravelGuide`、`TravelGuideStop`） | 进城或出远门出发时 TA 写一日小攻略（开启模型回信时由模型写，第一站就是这次真实要去的地方）；每站用高德按城市核对：查得到的给真实名称、地址和来源，查不到的标“TA 听说的，未核实”，不给地址；开启生成照片时再生成一页写实手账图（1440×2560，标题和站点名写在画面上） |
| 遇到朋友 | `GET /friends`（`FriendSummary`、`FriendKind`） | 两只真实宠物同一时间在同一地点（或同城 300 米内）才算遇到；双方主人都开了公开动态才会结识，拉黑过的不相遇；星球居民明确标注；见面次数累积为初识、熟人、好朋友；双方宠物都会告诉自己的主人 |
| 伙伴的写实证件照 | `PetPrivateSummary.photo_generated` | 没有主人上传照片的伙伴（领养的原创伙伴），第一次需要画它时先生成一张写实证件照，存为它的照片；之后的照片、明信片和手账都以它为参考，保证是同一只；页面应标注“AI 生成”。不会覆盖主人上传的真实照片 |
| 世界定时器 | `PETJOURNEY_WEB_WORLD_TICK_SECONDS`（默认 30，0 关闭） | 依次推进旅程事件、TA 自己的决定、到点的排队回复和主动消息；读取接口也会补齐，定时器停了只影响及时性 |

## 9b. 证件卡包、驾考与生活记录（0.2.4，全部为追加；依据 BACKEND-PRODUCT-ALIGNMENT-2026-09-22）

能力差异表见 `docs/contracts/CAPABILITY-GAP-IOS-WEB-20260922.md`。

| 能力 | 接口 | 规则 |
|---|---|---|
| 证件卡包 | `GET /credentials`、`GET /credentials/{credential_id}`（`CredentialSummary`、`CredentialDetail`） | 身份卡、星球银行卡、照护档案在入住时签发（签发时间＝入住时间）；护照在第一次出远门时签发，到达后盖纪念章；登机牌、船票车票按实际行程段签发，状态随时间变化；驾驶证只能由驾考签发；酒店房卡暂未开放（没有过夜入住）。编号稳定唯一，签发时间持久，同一事件只签发一次；尚未获得的证件也列出，并写明获得条件。银行卡的余额与流水就是现有钱包账户。照护档案只给主人看 |
| 驾考（**0.3.0 已替换为爪爪驾校，见 §9d**） | `GET /driving`、`POST /driving/enroll`、`GET/POST /driving/practice`、`POST /driving/exam` | 规则版本 `paw-drive-2026.1`（比赛建议值）：理论 10 题对 8 题通过；场景 5 个各 20 分，80 分以上且无关键错误通过。考场上 TA 自己作答，答对与否只看掌握程度，服务端计分并记录错题；客户端提交“passed”无效；没通过先练一次才能补考；通过后签发一次驾驶证并解锁 `local:drive_trip`（无证返回 403 `FORBIDDEN`，reason=`no_license`） |
| 打工记录 | `GET /jobs`（`JobRecord`） | 岗位、地点、开始与结束时间、状态（going / working / done）、工资与是否入账 |
| 生活时间线 | `GET /timeline`（`TimelineItem`） | 只读汇总已发生的记录：旅行、打工工资、证件、纪念章、驾考、朋友、明信片、收藏、攻略 |
| 攻略可复用 | `TravelGuideStop.{nav_url, copy_text}`、`TravelGuide.{status, visited, coin_budget, real_budget_note}` | 核实过的站点带高德导航链接（WGS-84）和可复制的名称地址；星币预算与现实花费分开；计划与到过的地方分开 |
| DNA 行为画像 | 无新接口 | 作息（睡觉与起床时间）、出门频率、路线兴趣、工作倾向和分享多少都由 DNA 推导，影响回复时机、主动消息、自主出门和学车速度 |
| 家的稳定 | `PUT /home/place` | 同一类型重复提交保持原来的城市，换成另一类地方才迁居 |

## 9c. 独立核查修复（0.2.5；依据 docs/coordination/BACKEND-REVIEW-2026-09-22.md；其中陪练与考试两行已被 0.3.0 替换）

前端接入说明见 `docs/coordination/FRONTEND-HANDOFF.md`。

| 能力 | 接口 | 规则 |
|---|---|---|
| 驾考一致性（P1） | `POST /driving/exam`（**必须带 Idempotency-Key**）；`DrivingStage` 新增 `license_pending` | 考试通过、驾驶证签发与驾驶资格同一次提交；签发失败整次考试不落库，可重试，一只宠物一本 C 照。旧数据“已通过未签发”在读取 `/driving`、`/credentials`、世界定时器或重启后补签（签发时间＝通过考试的时间），补签前阶段为 `license_pending`。考试与拿证消息走发件箱，投递失败不影响资格、之后按去重键补投 |
| 陪练按组结算（P2） | `GET /driving/practice` → `PracticeSet {practice_id, part, questions, created_at}`；`POST /driving/practice {practice_id, answers}`（**必须带 Idempotency-Key**）→ `PracticeResult` 追加 `practice_id`、`submitted_at` | 没交卷时反复打开是同一组；题目必须属于这一组、每题一次、选项在范围内（422 `duplicate_question` / `question_not_in_practice` / `invalid_choice`）；一组只结算一次，同键重试与原样重复提交返回第一次结果，换答案再交 409 `practice_already_submitted`；他人的组 404 |
| DNA 行为倾向（P2） | `PetDNAView.behavior`（`PetBehavior`、`BehaviorTrait`、`BehaviorEvidence`、`BehaviorPreference`；枚举 `PetRhythm`、`PetSociability`、`BehaviorTraitStatus`、`BehaviorPolarity`） | 规则版本 `dna-behavior-2026.2`：按小句读，处理否定、纠正（以前/现在、不是…而是…）、混合与含糊说法；每条结论带原话出处；说不准或矛盾的列入 `unclassified`，不强行归类；只用 DNA 与允许用于“家中互动 / 出行偏好”的叮嘱；作息、自主出门、主动消息与学车快慢都读这一份；确定性规则，不调用模型 |
| 元数据 | `GET /meta` | `backend_version` 改为 `web-mvp-0.2.5`，此后与契约版本同步递增 |

## 9d. 爪爪驾校：主人陪考，宠物拿证（0.3.0，**替换**旧驾考接口）

完整规格（科目、机会与冷却、确定性模拟、判定与扣分、操作上传、拿证）见 [DRIVING-SCHOOL-v1.md](DRIVING-SCHOOL-v1.md)；前端接入说明见 `docs/coordination/FRONTEND-HANDOFF.md` §4.5。

| 能力 | 接口 | 规则 |
|---|---|---|
| 总览与课程 | `GET /driving` → `DrivingSchoolStatus`；`GET /driving/curriculum` → `SchoolCurriculum`；`POST /driving/enroll` | 四科状态 `locked / available / in_exam / cooldown / passed`、本轮机会、冷却截止（服务器时间）、未结束考局、驾照、借车券、仪式；课程含分步教学、扣分项与红线（开考前展示）、操作说明、补考规则、按性格的台词与判定说明 `reasons` |
| 考局 | `POST /driving/sessions`（**必须带 Idempotency-Key**）、`GET /driving/sessions/{id}`、`POST …/begin`、`POST …/pause`、`POST …/abandon {confirm}` | 建局不计次，`begin` 才计次；一小时没开始作废；同一只宠物同一时间只有一场未结束的正式考局（部分唯一索引）；放弃需二次确认并计为不通过；复算出错作废不计次；他人考局 404 |
| 科一、科四 | `PUT …/answers`、`POST …/submit` | 固定题库 `paw-quiz-2026.2`，补考换一组；练习即时讲解，正式交卷前不给提示；只结算一次；科一 10 题 ≥90、科四 5 段 × 2 判断 ≥90 |
| 科二、科三 | `POST …/inputs {item_index, from_tick, upto_tick, events}` | 前端实时驾驶，服务端用同一套确定性模拟复算操作（30 Hz，只用加减乘除与 sqrt，常数来自场地配置）；片段必须连续，相同重发原样返回，不连续 409 `gap` / 不一致 409 `resync`；压线按连续段 −5、碰锥每个 −10、超时与出界不通过；科三红线自动制动并当场结算 |
| 拿证与领证 | `POST /driving/ceremony` → `CeremonyResult` | 第四科通过且四科齐全时同一事务签发 C 照、发驾校借车券、登记拿证消息；领证仪式只生成一次“领证合影”，再打开只是回看；驾照与借车券绑定宠物、不可交易；借车券抵一次自驾租车费 |
| 历史 | `GET /driving/history` | 只给主人看 |

## 10. 变更流程

同 v0.1。

变更记录：
- 0.1.0（2026-09-22）：R0 初版冻结。
- 0.2.0（2026-09-22）：MVP 实现。新增 identity 注册/登录/入住/设置、pets 上传、农场巡院与仓库、集市（market 模块 DTO：`ResidentOrder`、`MarketView`、`SellRequest`、`MarketResult`）、出发站、到访改选、冒险事件、`OnboardingState.pet_origin`、`JourneyMapSnapshot.{lifecycle,destination_title,current_visit_id,planned_visit_id}`、`PetPublicProfile.{viewer_follows,is_own}`、`CollectionItem.item_key`、`MemoryCorrectionRequest.new_slot_value`、`GuardState.{until,next_patrol_at}`、`HomeSnapshot.pantry`。**破坏性**：`StealResult.gained_coins` → `gained_item_key` + `gained_units`（偷到的是物资）；收获不再直接入账（进仓库）。
- 0.2.1（2026-09-22）：真实供应商接入（见 §9），全部为追加字段与路由；无破坏性变更。
- 0.2.2（2026-09-22）：网页底图（高德静态地图代理，见 §9），全部为追加模型与路由；无破坏性变更。
- 0.2.3（2026-09-22）：宠物自主世界（见 §9a），全部为追加字段、模型与路由；无破坏性变更。行为上的变化：宠物在家时菜园不再一定偷不到；店里合影不再生成卡通明信片。
- 0.2.4（2026-09-22）：证件卡包、驾考与补考、打工记录、生活时间线（见 §9b），全部为追加；无破坏性变更。行为上的变化：同一类型重复提交家不再重新随机。
- 0.2.5（2026-09-22）：独立核查三个问题的修复（见 §9c）。**陪练接口结构变化**（前端尚未接入）：`GET /driving/practice` 返回 `PracticeSet`，`POST /driving/practice` 需 `practice_id`；`POST /driving/practice` 与 `POST /driving/exam` 改为必须带幂等键；`DrivingStage` 追加 `license_pending`；`PetDNAView.behavior` 追加。数据修正：银行卡流水不再记 0 元旅费；时间线回家标题与同一时刻的顺序。
- 0.3.0（2026-09-22）：爪爪驾校（见 §9d 与 DRIVING-SCHOOL-v1.md）。**破坏性**：删除 `GET/POST /driving/practice`、`POST /driving/exam` 及旧驾考进度、陪练组与考试模型；`GET /driving`、`POST /driving/enroll` 改为返回 `DrivingSchoolStatus`（前端从未接入旧接口）。追加：`/driving/curriculum`、`/driving/sessions/**`、`/driving/history`、`/driving/ceremony` 与 20 多个驾校模型（考局状态枚举为 `SchoolSessionState`）；迁移 `m1430_driving_school`；前端插槽 `circle.places`。`backend_version` 为 web-mvp-0.3.0。
- 0.4.1（2026-09-23）：后端并行开发的总集成第 1–2 批（前端对接见 `docs/coordination/FRONTEND-HANDOFF.md` 的 0.4.1 节）。追加路由：`GET /ops/runtime/{pet_id}`（每宠运行详情，只给本机或管理令牌，新模型 `PetRuntimeStatus` / `RuntimeDueItem`）。
追加字段（全部 x-additive）：`MessageSummary.{source_event_id, reply_to}`（只下发世界事件来源 `<journey_id>:<事件键>`）、`LedgerEntry.{ref_kind, ref_id}`（journey / order / home）、`OpsStatus.{tasks, outbox, cognition}`（新模型 `OutboxHealth`）、`WorldRunnerStatus.due_lag_seconds`、`HomeSnapshot.catching_up`、`JourneyMapSnapshot.catching_up`。没有新枚举值。**行为变化**：到期结算（工资、世界事件、行程完成）与每个下游的 outbox 同一事务；家庭来信、动态、收藏、证件在提交后立即投递，攻略与朋友相遇由后台任务投递（出发请求不再等模型）；待回复与生图按领取令牌提交，过期可接管、旧结果作废；已移出家庭的家人不再收到排队中的回复。迁移：`0040_outbox`、`0050_budget`、`1140_pending_reply_claims`。`backend_version` 为 web-mvp-0.4.1。
- 0.4.0（2026-09-22）：真实新用户、家庭共同照顾与多宠物、访客与待领养居民、真实交通、运行环境（前端对接见 `docs/coordination/FRONTEND-HANDOFF.md` 的 0.4.0 节，验收见 `docs/coordination/BACKEND-REAL-EXPERIENCE-ACCEPTANCE.md`）。追加模块：`household`（`HouseholdBrief/Detail/Member/Settings/Invite/InvitePreview/PetRelationship/EntryIntent*/PendingAdoption`、枚举 `HouseholdRole/InviteStatus/PetJoinStep/EntryKind`）、`public`（`PublicWorld/PublicResident/PublicPetView/PublicEntry`、枚举 `EntryRoute`）、`ops`（`OpsStatus/ProviderHealth/WorldRunnerStatus/FrontendHint`、枚举 `ProviderState`）；追加路由：`/households/**`、`/invites/preview`、`/invites/accept`、`/pets/{id}/relationship`、`/public/**`、`/journey/plan`、`/ops/status`；追加字段（全部 x-additive）：`RegisterRequest.entry`、`OnboardingState.{households,entry}`、`MoveInRequest.pet_id`、`HomeSnapshot.{household,pets}`、`GuardState.guarding_pets`、`AdoptRequest.household_id`、`AdoptionCandidate.{pet_id,residence,living_since}`、`PetDNAView.{version,personal_fields,updated_by_you}`、`MessageSummary.channel`（新枚举 `MessageChannel`）、`DestinationOption.{available,unavailable_reason,reference_note}`、`JourneyLeg.time_source`（新枚举 `LegTimeSource`）、`HabitatOption.open`，新模型 `TripPlanPreview/PlannedLegPreview/ReferenceFare`；枚举追加值：`PlaceProvider.world`（`TimeBasis` 不变）。**行为变化**：宠物相关接口可带 `?pet_id=`，照顾不止一只时不带 → 409 `pet_required`；指明别人家的宠物一律 404；角色不够 403；`POST /pets` 已建过家庭时 409 `household_exists`；DNA 带 `?expected_version=` 时冲突 409 `dna_version_conflict`；个人称呼与小暗号按家人各自保存；通讯器分私聊与家庭频道；正式环境没有演示线路（`PETJOURNEY_WEB_DEMO_CATALOG` 只在演示环境打开），远行按已核验船期与地图接驳、从开船时间反推出门，现实资料拿不到时 409 `transport_unavailable`（不退回演示、不扣钱）；新家只开放香港中环/西贡。迁移：`0030/0180/0230/0240/0250/0420/0430/0470/0510/0610/0710/1130`。`backend_version` 为 web-mvp-0.4.0。
