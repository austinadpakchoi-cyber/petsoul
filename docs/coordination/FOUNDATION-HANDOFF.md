# R0 框架交接（FOUNDATION-HANDOFF）

> 历史文档：本文件记录 R0 结束时（04:05）的状态。之后同一窗口按用户目标继续实现了 MVP，当前状态、运行资源与验证证据以 [MVP-HANDOFF.md](MVP-HANDOFF.md) 为准。

- 窗口：`claude-20260922-014933-307b`（用户指定的框架窗口）
- 时间：2026-09-22 03:02 → 04:05（+0800），约 1 小时
- 目录 / 分支 / HEAD：`E:\petsoul-audit\petsoul` / `codex/petsoul-web-integration` / `980feabc7710462a89c5df488c255d04e9e7de08`
- **全部未提交**（未 add / commit；未 pull / checkout / stash / reset / clean）。开工时已有的 `M AGENTS.md`、`?? docs/product/`、`?? docs/coordination/`（其他窗口文档）未改动。
- 96 小时总时钟：**T0 与截止时间待用户给定**。任何文档都没有记录 T0；本窗口没有把自己的启动时间当作 T0，也没有重置时钟。

结论：**FRAMEWORK_READY（仅代表框架）**。农场结算、真实注册、真实班次、同步播放、寻味算法、跨账号社交、部署都**没有**完成。

## 1. 启动命令与版本

| 项 | 版本 / 命令 |
|---|---|
| Node / npm / Python | 22.20.0 / 10.9.3 / 3.12.2（本机） |
| 前端依赖（lockfile 锁定） | react 19.3.0、react-router 7.18.4、@tanstack/react-query 5.103.2、vite 8.3.0、@vitejs/plugin-react 6.1.1、typescript 6.0.3、vitest 5.0.1、jsdom 27.4.0 |
| 后端依赖 | 未新增。注意：本机实际 fastapi 0.119.0 / pydantic 2.12.3 / starlette 0.48.0，而 `requirements.txt` 固定 0.115.12 / 2.11.4——R0 测试在本机版本上运行，部署镜像需按 requirements 重验 |
| 安装 | `cd PetJourneyWeb && npm ci` |
| 演示模式 | `npm run dev:fixture` → http://127.0.0.1:5287 |
| live 模式 | 终端 A：`node scripts/dev-backend.mjs`（127.0.0.1:18761，mock 供应商、独立数据目录、密钥置空）；终端 B：`npm run dev:live` |
| 检查 | `npm run typecheck`、`npm test`、`npm run build`、`npm run contract:check`；后端 `TZ=UTC python -m unittest discover -s tests`；`python scripts/arch_gate.py`（Windows 需 `PYTHONIOENCODING=utf-8`）、`contract_diff.py`、`dependency_gate.py` |

## 2. 运行资源（本窗口启动，**仍在运行，未释放**）

| 资源 | 值 |
|---|---|
| 本地后端 | 127.0.0.1:18761；uvicorn python PID **49520**（父进程 node `scripts/dev-backend.mjs` PID 46096）；数据 `PetJourneyBackend/data/web-r0-claude/`（已被 .gitignore 覆盖）；日志 `PetJourneyBackend/data/web-r0-claude-backend.log`；含本窗口冒烟用的 mock Apple 用户与一只测试宠物 |
| Vite dev（fixture） | 127.0.0.1:5287；node PID **40696**；日志 `PetJourneyBackend/data/web-r0-claude-vite-fixture.log` |
| 已停止 | 首个后端 PID 54688（错误路径测试时由本窗口停止并重启）；vite preview 127.0.0.1:4287 PID 46972（测试后停止） |

需要释放时停止上述两个 PID 即可；其他窗口不要复用 `data/web-r0-claude/`，请用 `PETSOUL_DEV_DATA_DIR` 与 `PETSOUL_DEV_BACKEND_PORT` 另起。

## 3. 验证结果（本机，2026-09-22 04:0x）

| 检查 | 结果 | 证据 |
|---|---|---|
| `npm run typecheck` | 通过（83+ 源文件；已用故意写错的探针确认检查生效） | `PetJourneyBackend/data/web-r0-claude-verify.log` |
| `npm test`（vitest） | 4 文件 19 项通过 | 同上 |
| `npm run build` | 通过（JS 486 KB / gzip 155 KB） | 同上 |
| `npm run contract:check` | 通过：68 枚举、93 模型、44 路由；2 个 fixture 导出文件经 Pydantic 校验（另做反例：缺字段/非法枚举会被拒绝） | 同上 |
| 后端全量 unittest（TZ=UTC） | 130 项 OK，skip 1（既有 Windows 时区用例）；其中新增 web 测试 34 项；开工基线 96 项 OK/skip 1 | `PetJourneyBackend/data/web-r0-claude-unittest.log` |
| arch_gate / contract_diff / dependency_gate | 通过（arch 的“待拆分”警告均为既有旧类） | 命令输出 |
| live 构建密钥扫描 | 未发现密钥模式（仅 `mask-type` 误报） | `.runtime/dist-live` 手动 grep |

浏览器冒烟（应用内浏览器，**模拟尺寸，不是真机**）：

- 320×640、390×844、430×932：各检查同一组 21 条路由（含播放面板打开态），均无横向滚动；390×844 下验证了深链接硬刷新、Tab 切换、前进/后退、未知路径 → 404 页、不存在的到访 → NOT_FOUND 状态。
- 旅途地图：拖动+滚轮缩放后车辆从 (196,418) 移到 (382,344)，音符徽标与车辆的偏移恒为 (+30,−38)；点音符只打开播放面板（不开班次卡）；点车辆只开班次卡（本地时刻按两地时区显示）；深链接 `?sheet=media:…`/`?sheet=leg:…` 打开同一地图与面板。
- 一起听：真实加载自制音频，`playing` 事件后且偏差在容忍内才显示“你正和 TA 一起”；收起面板后迷你播放条仍显示“和 TA 一起”，车辆锚点 4 秒内继续前进；共同暂停/继续改变会话 revision 与本地播放；视频在面板内实际播放（480 宽，currentTime 前进）；素材缺失 → “播放失败”，不显示同步；驾驶场景“换成看剧”禁用并说明；到站场景显示“已保存到 0:18”，无“一起看”按钮；轮船场景无徽标；飞机听歌活动约 140 秒后徽标消失。
- 寻味：清淡组首选“示例·清汤面馆”，浓郁组首选“示例·街角咖喱小馆”；只有 2 家时如实说明“不硬凑三个”；勾选行程延误后卡片变“待复核”；主人模式使用自己的日期/时间与私密饮食提示。
- 接待：自己的宠物分支 5 条候选（3 习惯、1 私人心里话默认“只留在这里”且不能“交给 TA”、1 推测默认“不保存”）；未逐项选择时不能确认；模拟保存失败 → 草稿保留、提示可重试；重试成功 → 交给 TA 3 条、只留这里 1 条；进入家显示“姐姐，我到家啦。”及两条细节（第 1 版），页面不含私人倾诉原文；刷新后仍一致（fixture 标签页存储）。
- live 构建（vite preview）：`GET /meta` 200（真实后端）；未登录 `GET /home` → 401，页面显示“需要先登录”与后端 request_id；停后端 → 502，页面显示错误状态、重试按钮与 `UPSTREAM_UNAVAILABLE`；重启后重试恢复；注册提交 → 后端 501，页面如实显示“账号注册/登录尚未接入”。
- curl（真实后端、mock Apple Bearer，仅本地）：认领宠物后 `GET /api/v1/web/home` 返回真实存储的宠物与钱包（`presence=unknown`、`missing_capabilities` 如实列出）；坏令牌 → 401 `SESSION_EXPIRED`；经代理访问未实现的 `/circle/feed` → 501 `CAPABILITY_UNAVAILABLE`。

说明：隐藏的浏览器标签页中，TanStack Query 默认暂停重试（visibility=hidden），错误状态出现会延后；前台标签页不受影响。

## 4. 哪些是真实实现、哪些是 fixture、哪些未验证

| 类别 | 内容 |
|---|---|
| 真实实现（本地已测） | `/api/v1/web` 错误信封与 request_id；会话解析（cookie+CSRF / Bearer 兼容）；`GET /meta`、`GET /session`、`GET /home`（旧存储只读适配）、`POST /auth/logout`；幂等存储；迁移框架（0001）；任务队列原语；旧接口访问策略 `owner_bearer`/`closed`（默认 `open`）；MemoryPolicy、寻味上下文、交通时间线、媒体锚点纯函数；前端统一客户端/服务注册/插槽/路由检查；真实 HTMLMediaElement 播放与失败处理 |
| 契约占位（401/501，如实） | 注册/登录、入住、建宠/领养/公开主页、接待全部写入、农场、到访、地图快照、交通段、媒体会话、寻味、星球圈、通讯、收藏——路由已注册，先鉴权/CSRF/幂等键校验，再返回 501 |
| fixture（前端，明确标注） | 家园快照与菜园、四类交通 7 个场景（`time_basis=demo_fixture`，喵航 Cat222 / 爪爪铁路 Paw318 / 海獭轮渡 Otter08 为原创示例身份）、媒体会话与自制音视频、寻味清淡/浓郁（示例店与示例菜）、接待两条分支脚本、示例咖啡馆到访、星球圈/通讯/收藏、领养池 |
| 未验证 / 未完成 | 真实注册与口令哈希；接待真实保存/模型/删除传播；农场与经济结算；真实班次/时刻表/映射注册表；服务端媒体会话与同步、授权作品；寻味筛选排序、真实资料与反馈；跨账号社交；`/media` 私有化；高德/Google 地图适配；iOS Safari / Android Chrome 真机；部署 |

## 5. 共享文件（框架窗口保留写权限，见 MODULE-MAP §6）

前端：`package.json`、`package-lock.json`、`.npmrc`、`vite.config.ts`、`tsconfig*.json`、`index.html`、`.env.example/.env.fixture/.env.live`、`src/main.tsx`、`src/app/**`、`src/shared/**`、`src/fixtures/world.ts`、`scripts/dev-backend.mjs`、`tests/modules.test.tsx`、`tests/api-client.test.ts`、`tests/setup.ts`。
后端：`app/main.py`、`app/config.py`（web 段）、`app/schemas/web/**`、`app/web_platform/**`、`app/routers/web/__init__.py`、`_shared.py`、`meta.py`、`tests/web_base.py`、`tests/test_web_platform*.py`。
契约：`docs/contracts/**`、`scripts/gen_web_contract.py`。依赖安装与 `requirements.txt` 变更串行执行。

这些共享入口**继续由本窗口保留**，直到用户指定新的维护者；其他窗口需要改动时在自己的日志写提议与影响，不直接修改。

## 6. 现在可分配的模块（负责人留空，由用户决定）

| 模块 | 可写路径（前端 / 后端 / 迁移区间） | 共享依赖 |
|---|---|---|
| identity | `src/features/identity/**` / `app/routers/web/identity.py`、新建 `app/web_identity/**` / 0100–0199 | web_platform.session、requirements.txt（口令哈希库需提议） |
| pets | `src/features/pets/**`、`src/fixtures/adoption.ts` / `app/routers/web/pets.py`、`app/web_pets/**` / 0200–0299 | identity、媒体私有化 |
| reception | `src/features/reception/**`、`src/fixtures/reception.ts` / `app/routers/web/reception.py`、`app/reception/**` / 0300–0399 | MemoryPolicy、web_platform.tasks |
| home | `src/features/home/**`、`src/fixtures/home.ts` / `app/routers/web/home.py`、`app/web_adapters/home_snapshot.py` / 0400–0449 | reception、economy、journey |
| farm | `src/features/farm/**` / `app/routers/web/farm.py`、`app/web_farm/**` / 0450–0499 | economy、home |
| economy | — / `app/web_economy/**` / 0500–0599 | 既有 economy_engine（唯一账本） |
| journey | `src/features/journey/**`、`src/fixtures/venue.ts` / `app/routers/web/journey.py`、`app/web_journey/**` / 0600–0699 | transport、companion_media、food |
| venue | `src/features/venue/**` / — | VisitService |
| transport | `src/features/transport/**`、`src/fixtures/transport.ts` / `app/routers/web/transport.py`、`app/transport_world/**` / 0700–0799 | 旧交通引擎修改需另登记 |
| companion_media | `src/features/companion_media/**`、`src/fixtures/media.ts`、`public/fixtures/media/**` / `app/routers/web/companion_media.py`、`app/companion_media/**` / 0800–0899 | transport |
| food_discovery | `src/features/food_discovery/**`、`src/fixtures/food.ts` / `app/routers/web/food.py`、`app/food_discovery/**` / 0900–0999 | transport、reception |
| social | `src/features/social/**`、`src/fixtures/social.ts` / `app/routers/web/social.py`、`app/web_social/**` / 1000–1099 | pets、journey |
| communicator | `src/features/communicator/**` / `app/routers/web/communicator.py`（适配既有 `app/communicator`） / 1100–1199 | 既有 communicator |
| collection | `src/features/collection/**` / `app/routers/web/collection.py` / 1200–1299 | economy |
| deploy / 验证 | `deploy/web/**` | 修改现有 docker-compose/Caddyfile、真实部署需用户授权 |

`src/fixtures/social.ts` 同时服务 social / communicator / collection，多窗口时需先协调。

## 7. 剩余依赖、风险与已知缺口

1. **旧接口权限**：默认 `PETJOURNEY_LEGACY_API_POLICY=open`（保持 iOS 现状）。公开网页部署前必须切 `owner_bearer` 或 `closed` 并实测 iOS 是否带 Bearer；`/media` 静态目录仍全量公开；`/api/v1/feedback` 等 body 内 pet_id 未细粒度校验；`/docs`、`/openapi.json` 需在部署层关闭。
2. **旧引擎差异**（已写入契约 §8，未修改旧代码）：street_rank 算分后未重排且含照片/距离；transport_schedule 的 WebSearch 名称不代表联网；world_simulation 会压短交通；中转节点插值；现实承运人直接展示；`update_pet_dna` 写记忆、`list_memories` 无用途过滤；旧 `create_pet` 立即开启旅程。
3. 幂等记录与业务写入不同事务：关键结算须在领域表加唯一约束。
4. 任务队列没有常驻 worker；需接入受控单实例调度（不能每个标签页各自推进）。
5. 小屏（320×640）打开播放面板时车辆可能被面板遮挡；后续可按面板高度偏移地图中心。fixture 场景中共同暂停只改变媒体会话，地图徽标状态来自交通快照（真实实现应由服务端同时更新两者）。
6. fixture 代码目前随 live bundle 一起打包（只在 fixture 模式启用）；如需减小体积可改为按模式动态导入。
7. 真实供应商（地图、模型、生图、时刻表、影音平台）均未调用；扫街榜接口未确认；香港部署、域名、容量、备份与回滚均未执行。
8. 接待草稿保留期（建议 24h）、口令哈希库、会话吊销表、`/media` 私有访问方案需要对应模块决策并登记。

## 8. 文件清单（新增/修改）

- 修改（追加式）：`PetJourneyBackend/app/main.py`（+7 行：安装 web 平台、注册 web 路由）、`PetJourneyBackend/app/config.py`（+8 行：`legacy_api_policy`、`web_cookie_secure`、`web_session_ttl_seconds`）。
- 新增后端：`app/schemas/web/`（10 文件）、`app/web_platform/`（errors、session、idempotency、tasks、legacy_guard、migrations/）、`app/routers/web/`（13 文件）、`app/web_adapters/`、`app/reception/`、`app/food_discovery/`、`app/transport_world/`、`app/companion_media/`、`tests/web_base.py`、`tests/test_web_platform.py`、`tests/test_web_platform_infra.py`、`tests/test_web_domains.py`。
- 新增前端：`PetJourneyWeb/`（配置、lockfile、`src/app`、`src/shared`、14 个 `src/features/*`、`src/fixtures`、`public/fixtures/media`、`tests`、`scripts/dev-backend.mjs`、README）。
- 新增文档/脚本：`docs/contracts/WEB-CONTRACT-v0.1.md`、`docs/contracts/MODULE-MAP.md`、`docs/contracts/generated/`（TS 对应的 schema 与路由表）、`docs/contracts/examples/r0-fixtures.json`、`scripts/gen_web_contract.py`、`deploy/web/README.md`、`deploy/web/Caddyfile.web.example`、本文件。
