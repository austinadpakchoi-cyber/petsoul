# PetSoul 网页模块图（MVP · 契约 v0.3.0）

版本：MVP（契约 0.3.0：爪爪驾校替换旧驾考接口，见 [DRIVING-SCHOOL-v1](DRIVING-SCHOOL-v1.md)）· 2026-09-22 · 框架窗口 `claude-20260922-014933-307b`（R0 之后按用户目标继续实现了全部模块的 96h 主线）。契约语义见 [WEB-CONTRACT-v0.2](WEB-CONTRACT-v0.2.md)（v0.1 保留作历史），实际路由见 [generated/WEB-ROUTES.md](generated/WEB-ROUTES.md)。

**模块划分不等于任务分派。**“负责人”一栏全部留空，由用户分配；框架窗口不替任何窗口领取任务。

## 1. 接入方式（所有模块相同）

前端：每个模块一个目录 `PetJourneyWeb/src/features/<module>/`，默认导出 `defineModule({...})` 于 `module.ts(x)`：

```ts
export default defineModule({
  id: "food_discovery",
  routes: [{ path: "journey/food", element: <FoodDiscoveryPage /> }],   // 带底部导航的页面
  bareRoutes: [],                                                      // 全屏流程（欢迎/注册/接待）
  services: { food: { fixture: createFixtureFoodService, live: createLiveFoodService } },
  slots: [slot("journey.cards", "food_discovery.arrival", FoodArrivalCard, 10)],
});
```

- `app/modules.ts` 用 `import.meta.glob("../features/*/module.{ts,tsx}")` 自动发现——**新增/修改模块不需要改 app/、router 或 shared/**（`tests/modules.test.tsx` 证明：transport 与 companion_media 两个独立模块经固定导出同时接入 `journey.map.overlay` / `journey.sheet` 插槽；测试内新建的 probe 模块无需改核心即可渲染）。
- 启动时自动检查：模块 id 重复、路由冲突、禁止路由（`cabin` / `舱` / `transport/...` 独立交通场景页）、服务重复提供、插槽贡献 id 重复——任一违规直接抛错。
- 模块不能新增底部 Tab（家 / 旅途 / 星球圈 / 通讯固定在 `app/RootLayout.tsx`）。
- 页面只通过 `useServices()` 取服务、只通过 `shared/api/client.ts` 访问后端、只用 `@/shared/contracts` 的生成类型、只用 `@/shared/ui` 与 tokens。
- 模块样式写在自己目录的 `*.css`，只用 `shared/theme/tokens.css` 变量。

后端：每个模块一个路由文件 `PetJourneyBackend/app/routers/web/<module>.py`（`router` + `capabilities(settings)`），领域代码在 `app/<domain>/`，迁移在 `app/web_platform/migrations/m<NNNN>_<slug>.py`（自动发现，编号区间见下表）。把占位 `raise not_implemented(...)` 换成实现，并把该文件 `capabilities()` 中对应条目改为 `available`；不需要改 `main.py`。

## 2. 插槽（宿主页面已放置）

| 插槽 | 宿主 | props | 当前贡献 |
|---|---|---|---|
| `home.welcome` | `/home` | `{snapshot: HomeSnapshot}` | home.welcome-banner（HomeWelcome） |
| `home.panels` | `/home` | `{snapshot}` | journey.status(5)、farm.panel(10)、driving_school.progress(40，学车进行中 / 待领证时才出现) |
| `journey.map.overlay` | `/journey` 地图（随投影移动） | `{snapshot: JourneyMapSnapshot, nowMs, openSheet}` | transport.vehicle(10)、companion_media.badge(20) |
| `journey.sheet` | `/journey`（URL `?sheet=kind:id`） | `{snapshot, nowMs, kind: leg\|media, targetId, close}` | transport.leg(10)、companion_media.sheet(20) |
| `journey.dock` | `/journey` 常驻层 | 同 overlay | companion_media.dock |
| `journey.cards` | `/journey` 地图下方 | 同 overlay | food_discovery.arrival(10)、venue.entry(20)、driving_school.hint(40，报名后提示自驾要驾照 / 拿证后提示借车券) |
| `venue.panels` | `/visits/:visitId` | `{visit: Visit}` | （空，留给寻味“为什么选这里”等） |
| `circle.places` | `/circle` 动态流之前（0.3.0 新增） | `{}` | driving_school.entry(10，“星球上的地方 · 爪爪驾校”) |

新增插槽 = 修改 `shared/slots/names.ts` + 宿主页面放置 `<Slot>`，属于共享入口变更。

## 3. 服务边界（`shared/services/types.ts`）

| 服务键 | 接口 | 当前提供者 | live 实现 |
|---|---|---|---|
| platform | `meta()` | app/platform.module | ✅ `GET /meta` |
| session | `current/register/login/logout/onboarding/moveIn/settings/updateSettings` | identity | ✅ 用户名+密码（scrypt）、可吊销会话 cookie + CSRF、入住阶段、设置 |
| world | `home()` | home | ✅ `GET /home`（网页之家：位置、守护/巡院、钱包、仓库、地块、旅程简报、欢迎细节、未读） |
| visits | `visit/act/choose` | journey | ✅ 到访、店内活动（合影明信片、冒险事件）、到店前改选推荐分店 |
| economy | `collection/market/sell/fulfill` | collection | ✅ 收藏；集市（杂货铺收购、居民订单）；玩家挂牌关闭 |
| farm | `act/crops/neighbors/neighborHome/steal/patrol` | farm | ✅ 种植/收获进仓库、稀有种子、串门互偷、主人巡院 |
| pets | `adoptionCandidates/adopt/createOwn/publicProfile` | pets | ✅ 原子独占领养、照片上传（私有存储、剥离元数据）、公开主页 |
| reception | `start/get/addTurn/skip/confirm/notes/correct/homeWelcome` | reception | ✅ 引导便笺模式（接待模型未配置时不伪装自由对话）、确认、更正/撤回 |
| transport | `journeyMap/leg/destinations/depart/fixtureScenarios` | transport | ✅ 出发站、出发扣旅费、时间线（演示线路，按真实时间推进） |
| companionMedia | `session/join/command/heartbeat/leave` | companion_media | ✅ 服务器锚点、共同控制（revision + 租约）、心跳计量 |
| food | `preference/savePreference/recommend/recommendation/feedback/fixtureVariants` | food_discovery | ✅ 两套偏好、两种模式、行程版本失效、主人反馈（演示资料集） |
| social | `feed/petPosts/post/comments/react/comment/removePost/removeComment/follow/block/report` | social | ✅ 跨账号动态、评论（明确以宠物或主人身份）、关注、撤下、屏蔽、举报 |
| communicator | `thread/send` | communicator | ✅ 私密消息、按宠物状态延后回复、明信片与冒险故事 |
| driving | `status/curriculum/enroll/createSession/session/begin/answer/inputs/pause/submit/abandon/history/ceremony` | driving_school | ✅ `/driving/*`（0.3.0）：四科、首次＋补考、7×24 小时冷却、服务端复算、只结算一次、领证仪式；fixture 版在内存按同一规则运行（`features/driving_school/fixture.ts`，按需加载） |

### 3.0 宠物自主世界（服务端，0.2.3）

`app/web_agent/`：`moment.py`（TA 此刻的状态）、`reply_policy.py`（按状态决定何时回复、危机识别）、`proactive.py`（主动消息）、`life.py`（自己决定出门、主人建议）、`ticker.py`（世界定时器）；装配在 `app/web_agent_wiring.py`。相关模块：`app/web_pets/dna.py`（DNA）、`app/web_home/place.py`（家的片区）、`app/web_journey/local.py`（日常出门与打工）、`app/web_farm`（按几率守护）、`app/web_collection`（邮局明信片）、`app/web_journey/guides.py`（攻略手账）、`app/web_social/friends.py`（遇到朋友）、`app/web_agent/profile.py` 与 `dna_reading.py`（DNA 行为画像：按小句读否定、纠正与含糊说法，结论带原话出处）、`app/web_agent/timeline.py`（打工记录与生活时间线）；证件与驾校在 `app/web_credentials/`、`app/web_driving/`（0.3.0 爪爪驾校：`sim.py` 车辆模型与几何、`replay.py` 操作复算与判定、`courses.py` 场地配置、`questions.py` 固定题库、`curriculum.py` 课程与台词、`rules.py` 机会与冷却、`grading.py` 计分、`sessions.py` 考局存取、`service.py` 驾校服务与同事务签发、`notes.py` 消息发件箱；规格见 `docs/contracts/DRIVING-SCHOOL-v1.md`），装配在 `app/web_credentials_wiring.py`；前端 `src/features/driving_school/`（`sim/` 与后端逐行对应的复算、`drive/` 驾驶界面、`quiz/` 答题、`pages/` 页面）。跨语言样例：`scripts/gen_driving_fixtures.py` 生成 `PetJourneyWeb/tests/fixtures/driving-golden.json` 与 `src/fixtures/driving-school.json`。本地演示库：`scripts/seed_web_demo.py`（只写 `PetJourneyBackend/data/web-demo/`，不调用任何供应商）。

### 3.1 真实供应商（服务端，0.2.1）

`app/web_providers/`：`ProviderMeter`（每日上限与脱敏状态）、`OpenAICompatibleChat`（DeepSeek）、`GeoService`（高德/Google 地点与路线，缓存 24h，GCJ-02↔WGS-84）、`BasemapService`（0.2.2：高德静态底图代理，港澳范围，缓存 24h，迁移 0020）、`SeedreamIllustrator`、`readiness`（能力声明）。总开关 `PETJOURNEY_WEB_PROVIDERS` 默认关闭；本地开发由 `PETSOUL_DEV_PROVIDERS=1 node scripts/dev-backend.mjs` 读取 git 忽略的 `PetJourneyBackend/data/secrets/web-providers.env`。
消费方：journey（`geo_plan.py` 出发时真实地点/估时；`illustrations.py` 冒险插画任务与后台 worker）、communicator（`persona.py` 模型回信）、reception（接待模型回应）、intent_layer（`llm_judge.py`）。测试一律注入假实现（`tests/web_provider_fakes.py`），不触网。

适配边界（非数据服务）：地图 `shared/map`（`MapProjection` 上下文 + `MapAnchor`；`SchematicMapSurface` 在 live 模式下向 `platform.basemap()` 要真实底图，港澳范围叠加高德静态底图、投影与底图像素对齐，其他情况为示意地图；投影函数在 `shared/map/projection.ts`；Google 底图待开通计费后实现同一上下文）；媒体 `features/companion_media/playerStore.ts`（HTMLMediaElement 真实播放、同步判定、失败/拦截状态）。

## 4. 跨模块失效规则（`shared/query/queryClient.ts::queryKeys`）

| 写操作成功后 | 必须失效/更新 |
|---|---|
| 农场收获/种植/互偷/巡院 | `queryKeys.home`（钱包、仓库、地块、守护、版本）；种稀有作物还要 `queryKeys.collection`（种子被消耗）；互偷后 `neighbors`/`neighborHome(id)` |
| 集市出售/交单 | `["economy","market"]`、`queryKeys.home` |
| 接待确认/更正/撤回 | `queryKeys.home`（HomeWelcome）、`queryKeys.homeWelcome(petId)`、`queryKeys.session`（入住阶段） |
| 出发/到站/改行程 | `queryKeys.home`、`["transport"]`、`["food","recommendations"]`（行程版本变化使推荐待复核）、`["communicator"]`、**`["world","state"]`**（2026-09-24 补：W1 统一世界状态直接受出发/到站影响；加 W1 时**漏登记了这一条**，地图会有最多 `staleTime`＝15 秒显示旧状态。6c2b 报，I 补） |
| 媒体控制命令 | `queryKeys.mediaSession(id)`（用返回值 setQueryData） |
| 到访活动 | `queryKeys.visit(id)`；产生动态/勋章时 `queryKeys.circleFeed`、`queryKeys.collection` |
| 点赞/评论/撤下/屏蔽/关注 | `queryKeys.post(id)`、`queryKeys.circleFeed`、`queryKeys.petProfile(petId)` |
| 发送消息 | `queryKeys.messages(petId)` |
| 驾校报名/建局/开考/交卷/放弃/上传结算/领证 | `["driving"]`（状态、课程、考局、历史）、`queryKeys.credentials`（驾照）、`queryKeys.collection`（借车券、领证合影）、`queryKeys.home`；考局写操作用返回值 `setQueryData(queryKeys.drivingSession(id))` |
| 领养/建立宠物/入住 | `queryKeys.session`、`queryKeys.home`、`queryKeys.adoption` |
| 任何请求返回 AUTH_REQUIRED/SESSION_EXPIRED | 全局重新读取 `queryKeys.session`，入口守卫带回欢迎页 |

## 5. 模块表

迁移编号区间：每个模块只在自己的区间建文件；`0001–0099` 平台共享（框架窗口）。已用：0001、0010、0020、0100、0150、0160、0200、0210、0220、0300、0400、0410、0450、0460、0500、0600、0650、0660、0670、0700、0800、0900、1000、1020、1100、1110、1120、1200、1210、1300、1400、1410、1420、1430。`1300–1399` 为宠物自主世界（`app/web_agent/`），`1400–1499` 为证件与驾考（`app/web_credentials/`、`app/web_driving/`），`1500–1599` 为员工运营后台（`app/web_admin/`），**`1600–1699` 为世界角色资产（`app/web_character/`，CR-PLAYER-CHARACTER-01）**。

| 模块 ID | 前端可写范围 | 后端可写范围 | 迁移区间 | 提供 | 消费 | 验收命令 | MVP 状态 | 负责人 |
|---|---|---|---|---|---|---|---|---|
| identity | `src/features/identity/**` | `app/routers/web/identity.py`；新建 `app/web_identity/**` | 0100–0199 | SessionService、注册/登录/退出/入住阶段、会话吊销钩子 | web_platform.session、storage users | `npm test`、`python -m unittest tests.test_web_platform` + 新增测试 | 已实现：注册/登录/退出、会话吊销、登录限流、入住阶段与激活、设置；邮箱验证/找回未接入 | |
| pets | `src/features/pets/**`、`src/fixtures/adoption.ts` | `app/routers/web/pets.py`；新建 `app/web_pets/**` | 0200–0299 | PetsService、上传建宠、专属领养、公开主页数据 | identity、媒体私有存储（待定） | 同上 + 并发领养测试 | 已实现：原子独占领养、上传（校验/剥离元数据/私有存储，未做解码重编码）、公开主页；真实原型档案未提供 | |
| character（CR-PLAYER-CHARACTER-01） | `src/features/home/**` 的角色渲染入口（6c2b） | **A 持有**：`app/routers/web/character.py`（I 已建占位＋登记，A 直接填实现）、新建 `app/web_character/**`、迁移 `m16xx_*` | **1600–1699** | 世界角色资产：active／candidate 分离、六态、受权限保护的图片、参考／风格版本、尺寸／锚点 | pets（身份参考、可见性）、web_platform（tasks／budget／租约）、web_providers（GPT 生图）、P 的角色导演用途 | `python -m unittest discover -s tests -p 'test_web_character*.py'` | **契约与路由面已就位（I），实现未开始**：三条路由均 `not_implemented`，无迁移、无领域包 | A（`claude-20260922-234337-4bef`） |
| reception | `src/features/reception/**`、`src/fixtures/reception.ts` | `app/routers/web/reception.py`、`app/reception/**`（`policy.py` 规则变更需记录） | 0300–0399 | ReceptionService、MemoryPolicy 投影、HomeWelcome | identity、pets、web_platform.tasks | `npm test`、`python -m unittest tests.test_web_domains` + 新增 | 已实现：引导便笺、原话候选与规则建议、确认/更正/撤回、MemoryPolicy 投影、HomeWelcome；接待模型/语音未配置 | |
| home | `src/features/home/**`、`src/fixtures/home.ts`（与 farm 协调） | `app/routers/web/home.py`、`app/web_adapters/home_snapshot.py` | 0400–0449 | WorldService（HomeSnapshot）、家园场景 | reception（HomeWelcome）、economy、journey | 同上 | 已实现：网页之家快照、在家/外出/到店、守护与巡院、仓库、未读 | |
| farm | `src/features/farm/**` | `app/routers/web/farm.py`；新建 `app/web_farm/**` | 0450–0499 | FarmService、地块/成熟/可偷总额/互偷 | economy（经 EconomyAdapter 记账）、home | 同上 + 幂等/并发测试 | 已实现：作物循环、稀有种子、收获进仓库、互偷共享上限、宠物在家守护、主人巡院 | |
| economy | （无独立页面；钱包在 HomeSnapshot） | 新建 `app/web_economy/**`（EconomyAdapter → `pet_wallets.travel_coin`） | 0500–0599 | 统一记账口径、库存/绑定标识 | 既有 economy_engine | 同上 | 已实现：统一账本适配、库存（`app/web_economy/inventory.py`）；集市在 `app/web_market/**` | |
| journey | `src/features/journey/**`、`src/fixtures/venue.ts` | `app/routers/web/journey.py`；新建 `app/web_journey/**` | 0600–0699 | `/journey` 宿主页、JourneyMapSnapshot 组合、VisitService、到访状态机 | transport、companion_media、food_discovery | 同上 | 已实现：出发站、唯一位置、世界事件幂等、到访与店内活动、改选、冒险事件模板（`adventures.py`） | |
| venue | `src/features/venue/**` | —（数据来自 journey 的 Visit） | — | 店内场景与活动呈现 | VisitService | `npm test` + 浏览器 | 已实现：咖啡馆模板、活动反馈、商家资料与原创内饰分开 | |
| transport | `src/features/transport/**`、`src/fixtures/transport.ts` | `app/routers/web/transport.py`、`app/transport_world/**`；旧 `transport_schedule/transport_reality/route_planner/world_simulation` 的修改需另行登记 | 0700–0799 | TransportService、VehicleMarker、班次卡、WorldService 映射、到达上下文 | shared/map、shared/journey/vehicle | `npm test`、`python -m unittest tests.test_web_domains` + 新增 | 已实现：演示线路时间线、动物世界班次身份、到达上下文；核验时刻表/实时动态未接入 | |
| companion_media | `src/features/companion_media/**`、`src/fixtures/media.ts`、`public/fixtures/media/**` | `app/routers/web/companion_media.py`、`app/companion_media/**` | 0800–0899 | CompanionMediaService、ActivityBadge、MediaSheet、MediaDock、参与计量 | transport（活动/驾驶角色）、shared/media | 同上 | 已实现：服务器会话、共同控制、心跳计量、驾驶不看视频；授权作品清单未提供（仅自制测试素材） | |
| food_discovery | `src/features/food_discovery/**`、`src/fixtures/food.ts` | `app/routers/web/food.py`、`app/food_discovery/**` | 0900–0999 | FoodDiscoveryService、推荐卡/详情、双模式/双偏好 | transport（PetArrivalContext）、reception（已确认偏好投影） | 同上 | 已实现：双偏好、双模式、硬过滤/分开评分/重排、行程版本失效、主人反馈；真实资料未接入 | |
| social | `src/features/social/**`、`src/fixtures/social.ts`（与 communicator/collection 协调） | `app/routers/web/social.py`；新建 `app/web_social/**` | 1000–1099 | SocialService、星球圈/动态/评论/公开主页 | pets（公开简介）、journey（源事件） | 同上 + A/B 隔离测试 | 已实现：动态来自到访事件、评论/回复/点赞（明确行动者）、关注、撤下、屏蔽、举报；人工审核流程未建立 | |
| communicator | `src/features/communicator/**` | `app/routers/web/communicator.py`；适配既有 `app/communicator/**`（修改旧引擎需登记） | 1100–1199 | CommunicatorService（私密） | 既有 communicator 引擎 | 同上 | 已实现（网页独立实现，未改旧引擎）：消息、延后回复、明信片、冒险故事、意图层措辞（默认关闭） | |
| collection | `src/features/collection/**` | `app/routers/web/collection.py` | 1200–1299 | EconomyService.collection、市场开关 | economy | 同上 | 已实现：收藏（纪念绑定、种子可种）、集市 NPC 杂货铺与居民订单；玩家挂牌关闭 | |
| driving_school | `src/features/driving_school/**`、`src/fixtures/driving.ts`、`src/fixtures/driving-school.json`（生成物） | `app/routers/web/driving.py`、`app/web_driving/**`、`app/schemas/web/school*.py`（共享 DTO，框架窗口维护） | 1400–1499（驾校 1430） | DrivingSchoolService；路由 `/school`、`/school/subject/:subject`、`/school/result/:sessionId`；全屏 `/school/session/:sessionId`、`/school/ceremony`、`/school/try`（体验版不连后端）；插槽 circle.places / home.panels / journey.cards | credentials（驾照）、collection（借车券、合影）、journey（自驾抵扣）、communicator（驾校消息） | `npm test`（`tests/driving-sim.test.ts` 逐位比对、`tests/driving-school.test.tsx`）、`python -m pytest tests/test_web_driving_*.py`、`python scripts/gen_driving_fixtures.py --check` | 已实现并验证（自动化测试＋fixture 模式浏览器实测）；live 界面未联调；阶段 3（其他训练场、车辆购买、居民委托等）未做 | |
| households（0.4.0） | —（页面待前端窗口：家庭页、邀请直达页、宠物切换） | `app/routers/web/households.py`、`app/web_household/**`（`access.py` 查询与授权、`members.py` 建家与成员、`invites.py` 邀请） | 0420–0439（home 区间） | 家庭、成员与角色、邀请、称呼；所有宠物接口的授权裁定（`require_pet` / `require_household`） | identity、pets、home | `python -m pytest tests/test_web_households.py` | 已实现并验证（自动化 + real-local 实跑）；页面未做 | |
| public / residents（0.4.0） | —（访客页面待前端窗口） | `app/routers/web/public.py`、`app/web_residents/**` | 0240（pets 区间） | 访客首页、居民列表与公开主页、公开媒体；待领养居民的驿站生活与领养交接 | pets、journey（只读 peek）、social | 同上 | 已实现并验证；页面未做 | |
| web_transport（0.4.0） | — | `app/web_transport/**`（时刻表快照、枢纽、港澳一日行规划）、`app/web_journey/planning.py` | 0710（transport 区间）、0610（journey） | 已核验船期按服务日期落地、反推出门、参考班次与动物世界编号追溯、行程预览 `/journey/plan` | GeoService（高德） | `python -m pytest tests/test_web_real_transport.py` | 已实现并验证（港澳一日行）；其他城市对未接入 | |
| platform 运行（0.4.0） | — | `app/web_platform/lease.py`、`app/web_worker.py`、`app/routers/web/meta.py`（`/ops/status`）、`scripts/real_integration.py`、`scripts/real_acceptance.py` | 0030 | 世界任务租约与独立任务进程、供应商健康、运行状态、真实联调启动与验收 | 全部 | 同上 | 已实现并验证（本地 real-local）；未部署 | |
| 每宠运行与自主决策接入（0.4.1，I） | — | `app/web_agent/runtime_view.py`（投影 + 心跳 shadow）、`app/web_agent/brain_life.py`（提案 → 复核 → 真实计划） | 0060 | 每宠运行记录（语义版本、下次检查、安静原因、上次决定）；心跳 shadow；自主决策按配置 off / shadow / live | web_runtime（B）、web_agent/decision（C）、web_platform/budget（A） | `python -m unittest discover -s tests -p "test_web_runtime_shadow.py"`（自主决策用例同理） | 已实现并验证（本地自动化，假模型）；默认 brain=off、heartbeat=shadow | |
| platform 事务与投递（0.4.1，I） | — | `app/web_platform/uow.py`（一个业务事务一个连接）、`app/web_platform/outbox.py`、`app/web_journey/settlement.py`、`app/web_journey/events.py` | 0040、1140 | 到期结算（工资、世界事件、行程完成、outbox 同一事务）；outbox 按下游投递（fast / slow 通道）；待回复领取期限与令牌围栏 | journey、economy、communicator、social、collection、credentials、guides、friends | `python -m unittest discover -s tests -p "test_web_settlement_chain.py"`（围栏用例同理） | 已实现并验证（本地自动化 + real-local 18763 已换上这版代码）；未部署 | |
| 任务可靠性与额度（0.4.1，包 A） | — | `app/web_platform/{tasks.py, lease.py, budget.py}`、`app/web_providers/meter.py`（窗口 claude-20260922-234337-4bef 持有） | 0050（DDL 由 A 提出、I 实施） | 领取代数与围栏、过期回收、续租、有界重试、终态保护、进程租约任期、供应商上限原子化、操作级预算预占 | —（被 I 接入：插画 run_claimed、接待更正、运维 task_health） | A 的 `tests/test_web_task_*.py`、`test_web_budget_reservation.py` | 已实现（A 交付）；插画与接待已接入；预算预占尚未接到模型调用 | |
| 世界时钟与心跳（包 B） | — | `app/web_runtime/{clock_policy,state,reasons,wake_events,heartbeat_policy}.py`（窗口 claude-20260922-234415-fed3 持有；`__init__.py` 归 I） | — | 纯策略：继续 / 执行规则 / 请求大脑 / 延期 / 恢复与下次检查 | runtime-internal 共享类型 | `tests/test_web_heartbeat_policy.py` | 已实现（B 交付）；未接入运行路径（第 4 批 shadow） | |
| DNA 与有限决策（包 C） | — | `app/web_agent/decision/**`（窗口 claude-20260922-234408-91f2 持有） | — | 授权上下文、有限提案、失效检测、模型适配 | runtime-internal、web_providers.llm | `tests/test_web_decision_*.py` | 已实现（C 交付）；未接入运行路径（第 4 批 shadow） | |
| map（CR-6C2B-MAP W0，I） | `src/features/world_map/**`（6c2b） | **I 持有**：`app/routers/web/map.py`、`app/schemas/web/map.py`、站点根代理 `app/routers/amap_service.py`、`app/main.py` 挂载 | —（纯读，无迁移） | 底图公开配置 `GET /map/config`（JS Key 公开下发，靠控制台域名白名单防护）；`/_AMapService/*` 只放行三条渲染路径并补安全密钥，服务类一律 403 | `config.amap_js_key` / `amap_js_security_code`（git 忽略的 `web-providers.env`） | `python -m pytest tests/test_web_map_w0.py` | **已实现**：配置接口与代理、10 项＋12 subtests；生产反向代理与域名白名单属部署，未做 | I（`claude-20260922-014933-307b`） |
| world（CR-6C2B-MAP W1，I） | `src/features/world_map/**`（6c2b） | **I 持有**：`app/routers/web/world.py`、`app/schemas/web/world.py` | —（纯读，无迁移） | 统一世界状态 `GET /world/state`：家里每只宠物此刻在哪／在做什么／还要多久；`phase` 由时间线推、`position.basis` 必须说明坐标来路、`pose` 只由事实推出 | journey（`peek`，纯读）、households、home_places、pets | `python -m pytest tests/test_web_world_state.py` | **已实现**：14 项＋5 subtests，含纯读验证（世界表行数快照）；`avatar_url` 未做头部裁切、`doing` 未接 moment、非成员可见性属 W2 | I（`claude-20260922-014933-307b`） |
| runtime-internal 共享类型（I） | — | `app/schemas/runtime_internal/**`（不进网页契约） | — | Clock、Versions、RuntimeState、WakeEvent、HeartbeatDecision、TaskClaim、BudgetReservation、DecisionContext、ActionOffer、BrainProposal、CommitOutcome、DomainEvent | — | `tests/test_runtime_internal_types.py` | 0.1.1 | |
| deploy / 验证 | — | `deploy/web/**`（新增）；现有 `deploy/docker-compose.yml`、`deploy/Caddyfile` 修改需用户授权 | — | 部署包、反代、SPA 回退、备份回滚 | 全部 | 见 deploy/web/README.md | 已提供：compose/Caddy/env 示例、发布/回滚/备份/恢复/冒烟脚本（本地演练过备份恢复）、演示脚本；未部署 | |

`src/fixtures/world.ts` 是共享 fixture 时间基准与样板宠物，改动需在日志提出。

## 6. 共享入口（仍由框架窗口 claude-20260922-014933-307b 保留写权限，其他窗口通过日志提出变更）

- 前端：`PetJourneyWeb/package.json`、`package-lock.json`、`.npmrc`、`vite.config.ts`、`tsconfig*.json`、`index.html`、`.env.*`、`src/main.tsx`、`src/app/**`、`src/shared/**`（含 `contracts/generated.ts` 生成物、`theme/tokens.css`、`slots/names.ts`、`services/types.ts`、`query/queryClient.ts`）、`src/fixtures/world.ts`、`scripts/dev-backend.mjs`、`tests/modules.test.tsx`、`tests/api-client.test.ts`、`tests/setup.ts`。
- 后端：`app/main.py`（装配）、`app/config.py`（web 设置段）、`app/schemas/web/**`（共享 DTO，模块提出字段变更由维护者合入并重新生成）、`app/web_platform/**`（错误、会话、幂等、迁移框架与 0001–0099、任务、旧接口策略）、`app/routers/web/__init__.py` 与 `_shared.py`、`app/routers/web/meta.py`、`tests/web_base.py`、`tests/test_web_platform*.py`。
- 契约与门禁：`docs/contracts/**`、`scripts/gen_web_contract.py`。
- 依赖：`PetJourneyWeb` 的 npm 依赖安装、`PetJourneyBackend/requirements.txt` 变更——串行，由共享入口维护者执行。

## 7. 通用验收命令

```bash
cd PetJourneyWeb && npm ci && npm run typecheck && npm test && npm run build && npm run contract:check
cd PetJourneyBackend && TZ=UTC python -m unittest discover -s tests
python scripts/arch_gate.py && python scripts/contract_diff.py && python scripts/dependency_gate.py
python scripts/gen_web_contract.py --check
```

Windows 控制台运行 `arch_gate.py` 需 `PYTHONIOENCODING=utf-8`（否则打印 “⚠” 时因 GBK 编码报错退出 1，与门禁结果无关）。


## 前端路由与后端实现的对应（2026-09-23 03:33:40Z 登记，只登记**当前已存在**的实现）

r7k 在其日志 11:22 领取了三个前端路由。这里只记它们**各自对应的后端实现**，
**不改 r7k 的任何代码，也不替它登记前端文件归属**——前端那侧的归属以 r7k 自己的 CLAIM 为准。

| 前端路由（r7k 领取） | 当前已存在的后端实现 |
|---|---|
| `/households/manage` | `app/routers/web/households.py`：`GET /households`、`GET /households/{household_id}`、`PATCH /households/{household_id}/settings`、`PUT …/members/{user_id}/role`、`DELETE …/members/{user_id}`、`POST …/invites`；服务在 `app/web_household/`（`access.py` 访问裁定与同连接授权复核、`members.py` 成员与家庭设置） |
| `/life` | `app/routers/web/life.py`：`GET /jobs`、`GET /timeline`；数据来自 `app/web_agent/timeline.py`（打工记录与生活时间线） |
| `/photos`（r7k 11:52 CLAIM） | `app/routers/web/pets.py`：`POST /pets/{pet_id}/photo-request`（下命令）、`GET /pets/{pet_id}/photo-requests`（结果列表，纯读）、`POST /pets/{pet_id}/photo-requests/{request_id}/retry-image`（重画）；判定在 `app/web_journey/photo_command.py`，生图执行在 `app/web_journey/illustrations.py`，导演在 `app/web_photo_director/` |
| `/credentials/:credentialId` | `app/routers/web/credentials.py`：`GET /credentials`、`GET /credentials/{credential_id}`；服务在 `app/web_credentials/`，装配在 `app/web_credentials_wiring.py`（含驾照与银行卡流水） |

**没有为这三条新增或改动任何后端实现**——它们本来就在，这里只是把对应关系写下来，
免得前端去猜哪个后端口对应哪个页面。契约以 `PetJourneyWeb/src/shared/contracts/generated.ts` 为准。
