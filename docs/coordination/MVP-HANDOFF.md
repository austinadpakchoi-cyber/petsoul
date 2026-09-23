# 网页 MVP 交接（MVP-HANDOFF）

- 窗口：`claude-20260922-014933-307b`（R0 框架窗口；用户目标“完成方案所有的要求的内容才能停止工作”）
- 时间：2026-09-22 04:10 → 05:40（+0800）
- 目录 / 分支 / HEAD：`E:\petsoul-audit\petsoul` / `codex/petsoul-web-integration` / `980feabc7710462a89c5df488c255d04e9e7de08`
- **全部未提交**（未 add / commit；未 pull / checkout / stash / reset / clean；未触碰 `_recover_backup`；未建 worktree）。开工前已有的 `M AGENTS.md`、`docs/product/**`、其他窗口日志未改动。
- 96 小时总时钟 T0：仍由用户给定；本窗口没有设定或重置。

结论：**MVP_READY_LOCAL**——总方案 §3 表中“96h 核心交付”列在本地 live 模式下两个真实账号完整走通；**没有**公网部署，也没有接入任何付费真实供应商（见 §5）。R0 交接见 [FOUNDATION-HANDOFF.md](FOUNDATION-HANDOFF.md)（历史）。

## 1. 启动与检查

| 项 | 命令 |
|---|---|
| 演示模式 | `cd PetJourneyWeb && npm run dev:fixture` → http://127.0.0.1:5287（顶部“演示模式”标识） |
| live 本地 | 终端 A：`PETSOUL_DEV_DATA_DIR=../PetJourneyBackend/data/<你的目录> node scripts/dev-backend.mjs`（127.0.0.1:18761，mock 供应商、独立数据/私有媒体目录、密钥置空；可用 `PETJOURNEY_AUTH_SECRET` 固定开发会话密钥，不入仓库）；终端 B：`npm run dev:live`（或 `npx vite --mode live --port 5288 --strictPort`） |
| 前端检查 | `npm run typecheck && npm test && npm run build && npm run contract:check` |
| 后端检查 | `cd PetJourneyBackend && TZ=UTC python -m unittest discover -s tests` |
| 门禁 | `PYTHONIOENCODING=utf-8 python scripts/arch_gate.py`、`dependency_gate.py`、`contract_diff.py`、`gen_web_contract.py --check` |
| 部署包 | `deploy/web/README.md`、`DEMO-SCRIPT.md`、`scripts/{release,rollback,backup,restore,smoke}.sh` |

## 2. 验证证据（2026-09-22 05:35 +0800）

- 后端全量：**159 tests OK（1 项既有 skip）**；其中网页 63 项：`test_web_platform`（元信息/会话/CSRF/信封/伪造 cookie）、`test_web_platform_infra`、`test_web_domains`、`test_web_mvp_flow`（两户完整主循环：注册→领养冲突→上传照片剥离元数据→接待原话候选→确认/幂等重放→HomeWelcome→入住→守护→出发扣费一次→巡院外偷菜进仓库→出售→共享上限→一起听心跳计量/暂停/版本冲突/租约→寻味两模式→到店前改选（端点改、时间不变）→到店活动/私有明信片→离店公开动态（主人未打开页面也可见）→NPC/主人评论→关注→回家收藏/共同回忆→举报/屏蔽）、`test_web_mvp_rules`（稀有种子与轮渡勋章、并发领养/出发各只一个成功、退出吊销与 cookie 重放、登录限流、通讯延迟与隔离、更正/撤回停止使用、愿望匹配、公开开关、居民订单一次性溢价、巡院与冷却、咖啡馆冒险用确认物件、收获换键重发不重复入库；流程测试另验点赞换键重发不重复）、`test_web_intent`（六个离线用例 + assist 只改措辞）、`test_web_reception_rules`。
- 门禁：arch_gate 通过（7 条“待拆分”均为既有 iOS/旧引擎类型）、dependency_gate 通过、contract_diff 90 对齐、web contract 78 枚举 / 122 模型 / 64 路由且 fixture 导出校验通过。
- 前端：typecheck 通过；vitest **26 项**（模块注册与禁止路由、MVP 路由、入住阶段映射、FormData 上传头、偷菜规则、出发重试复用同一幂等键、参与上报 join/心跳/leave 与“播完不算同步”、原有 R0 用例）；build 通过（537 KB / gzip 170 KB，单包未分割）；dist/源码/文档扫描无密钥。
- 浏览器（live，本地后端 + Vite 5288，320 / 390 / 430 宽）：`alice_web` 与 `bob_web` 两个真实账号走完 注册→领养冲突→领养→接待→便笺确认→入住（选择公开）→选种→出发站→地图/音符一起听→寻味改选→到店活动→明信片进通讯→串门偷菜→收获进仓库→居民订单（22→31）→跨账号动态（明信片图片）→宠物身份评论/点赞/关注→回家收藏。fixture 模式同步回归。后端在同一数据目录下重启 6 次，账号、宠物、家园、库存、行程、帖子与会话（固定开发密钥时）均恢复，旅程按真实时间补齐事件、不重开。
- 联调中发现并已修复：领养后分支被重定向丢失、窄屏接待卡溢出（chip 不换行）、首次“跟着 TA”被 `teardown()` 清空状态、播放器从不上报参与、步行段标题误写“自驾”、改选后路线端点未更新、终点段重复“到站”消息与同时刻消息顺序、接待规则把不同话题并成一条/“叫我起床”误判称呼/颜色前缀多截字、更正后沿用旧称呼、公开动态依赖作者本人刷新、外出时误显示“有人守家”、偷菜直接给币（改为物资进仓库）、开发后端私有媒体未隔离。

## 3. 已实现范围（对照总方案 §3）

| 模块 | 本地已实现 | 如实未做 / 需资源 |
|---|---|---|
| 账号与身份 | 用户名+密码（scrypt）、可吊销会话、CSRF、登录限流、入住阶段守卫、设置（公开动态/主页范围/简介） | 邮箱验证与找回 |
| 宠物与领养 | 上传（格式/大小/魔数校验、剥离 EXIF/tEXt、私有存储、鉴权访问）、原子独占领养、公开主页（私密时只给最小名片） | 解码重编码、真实原型档案 |
| 接待与叮嘱 | 引导便笺模式（原话按话题拆、规则只建议）、三种去向与用途、确认/幂等、草稿清除、更正/撤回（先停用再清理）、HomeWelcome、通讯称呼、愿望匹配出发站 | 接待模型与语音（未配置） |
| 意图层 | off/shadow/assist × rule/configured_llm/jev，默认 off；六个离线用例 | Jev/模型接入与中文对照实验 |
| 家园 | 家园快照、宠物唯一位置、守护/巡院、仓库、未读、出发入口 | 自由装修 |
| 农场与邻里 | 作物循环、共享可偷上限、在家守护、主人巡院（10 分钟/冷却 30 分钟）、串门页、稀有种子 | 鱼塘鸡舍 |
| 经济与集市 | 唯一 travel_coin 账本、库存（幂等变动）、杂货铺收购、居民订单；玩家挂牌 disabled | 玩家固定价挂牌（主线稳定后再评估） |
| 旅行与交通 | 出发站、三条演示线路（按真实时间推进）、动物世界班次身份、到达上下文、世界事件幂等 | 高德/Google 底图与地点、核验时刻表、实时动态 |
| 一起听看 | 服务器锚点、共同控制（revision+租约）、心跳计量、驾驶不看视频、共同回忆 | 授权作品（只有自制测试素材）、真机后台/锁屏 |
| 寻味 | 双偏好编辑、双模式、硬过滤+分开评分、行程版本失效、改选、主人反馈 | 真实菜单/口碑资料 |
| 店内互动 | 咖啡馆模板、选座/饮品/合影/居民；商家资料与原创内饰分开 | 更多场景模板 |
| 通讯与影像 | 私密消息、延后回复、原创插画明信片（私有→随动态公开）、冒险故事 | 生图英雄照、声音 |
| 星球圈 | 到访事件动态、NPC 标识、宠物/主人身份评论与回复、点赞、关注、撤下、屏蔽、举报 | 人工审核流程 |
| 冒险与纪念 | 三个事件模板（咖啡馆小侦探/海上小水手/小小飞行员），规则结算绑定勋章 | 个性化英雄图（生图未配置） |
| 公益领养 / 公共活动 / IP | 只用明确原创伙伴；事件记录可复用 | 需核实材料与合作 |
| 部署 | compose/Caddy/env 示例、发布/回滚/备份/恢复（本地演练）/冒烟、演示脚本 | 香港服务器、域名、HTTPS、实际发布 |

## 4. 契约与共享入口

- 契约 0.2.0：[WEB-CONTRACT-v0.2](../contracts/WEB-CONTRACT-v0.2.md)（含破坏性变更：偷菜/收获改为物资）；[MODULE-MAP](../contracts/MODULE-MAP.md) 已更新服务表、失效规则、模块状态与已用迁移号（0460 farm_patrol、0500 inventory 为新增）。
- SCOPE_CHANGE：`PetJourneyBackend/app/schemas/base.py` 的 `EconomyTransactionType` 追加 4 个网页值（只追加）；iOS 严格枚举仅在读取网页宠物账本时受影响。
- 新增后端包：`app/web_market/**`（集市）、`app/web_economy/inventory.py`、`app/web_journey/adventures.py`；开发脚本 `PetJourneyWeb/scripts/dev-backend.mjs` 增加私有媒体目录隔离。

## 5. 阻塞项（需要用户授权或资源，本窗口未擅自执行）

1. 香港生产部署：服务器、域名、HTTPS、发布窗口；部署后执行 `smoke.sh` 与备份恢复演练。
2. 付费/真实供应商：高德、DeepSeek、Seedream 已接通（见 §8）；**Google 需在其 Cloud 项目开通计费并启用 Places/Routes API**；核验时刻表来源、Jev 仍未提供。
3. 授权内容：一起听看的公开作品、真实商家菜单与口碑、真实原型档案与公益合作材料。
4. 真机测试：iOS Safari / Android Chrome 的安全区、键盘、手势播放、后台恢复、弱网。
5. 旧 iOS 接口策略切换（`owner_bearer`/`closed`）需实测 iOS 是否带 Bearer。

## 6. 已知风险与建议

- 世界事件在读取时补齐（任意用户读星球圈会补齐全部进行中旅程）；没有常驻 worker，长时间无人访问时事件在下一次读取补发（时间戳为真实发生时间）。流量上来后建议加一个进程内定时器。
- 单 SQLite 实例；`advance_all` 每次最多 200 段旅程。
- 前端单包 537 KB，建议按路由懒加载拆分。
- `requirements.txt` 固定 fastapi 0.115.12 / pydantic 2.11.4，本机测试运行在 0.119.0 / 2.12.3，部署镜像需按 requirements 复跑全部测试。
- 开发会话密钥只在本会话 scratchpad；重启 dev-backend 不带固定密钥会让所有开发会话失效（预期行为）。

## 7. 运行资源（本窗口启动，仍在运行）

| 资源 | 值 |
|---|---|
| 本地后端 | 127.0.0.1:18761；uvicorn python PID 42860（父 node `dev-backend.mjs` PID 39092，约 14:08 为加载底图代码重启，数据目录不变）；**已开启真实供应商**（PETSOUL_DEV_PROVIDERS=1）；数据 `PetJourneyBackend/data/web-mvp-claude/`（含 alice_web / bob_web / carol_real / dana_real 测试账号，口令为测试值）；日志 `PetJourneyBackend/data/web-mvp-claude-backend.log` |
| Vite live | 127.0.0.1:5288；node PID 3656（npx PID 57084）；日志 `PetJourneyBackend/data/web-mvp-claude-vite-live.log` |
| Vite fixture | 127.0.0.1:5287；node PID 40696（R0 起沿用） |
| 已停止 | R0 后端 PID 49520（数据 `web-r0-claude/` 保留）；MVP 期间多次重启的后端实例均已由本窗口停止 |

## 8. 真实供应商接入（2026-09-22 13:30 → 14:00 +0800，用户在对话中提供配置并授权）

结论：高德（港澳地点与路线估时）、DeepSeek（模型回信、接待模型回应、意图判断器离线对照）、火山方舟 Seedream（冒险插画）已在本地 live 真实调用并通过；**Google 地图被拒**（项目未开通计费，Places/Routes/Geocoding 均返回 REQUEST_DENIED/PERMISSION_DENIED），东京段继续用演示数据，`/meta` 如实显示 `map.google=not_configured` 与原因。

| 项 | 实现 | 真实验证（本地） |
|---|---|---|
| 密钥与开关 | 配置存放在 git 忽略的 `PetJourneyBackend/data/secrets/web-providers.env`（未创建 `.env`，避免旧后端与既有测试自动加载）；`PETSOUL_DEV_PROVIDERS=1 node scripts/dev-backend.mjs` 按白名单读取、不打印值；服务端总开关 `PETJOURNEY_WEB_PROVIDERS` 默认关；每日上限 300/20/500 | 前端产物、源码、文档、日志扫描无密钥；错误摘要脱敏 |
| 真实地点 + 路线估时 | `app/web_providers/geo.py`、`app/web_journey/geo_plan.py`：出发时目的地换成附近真实咖啡店（带“地点资料：高德地图”署名、真实地址），步行/打车段 `routed_estimate` + 真实道路几何；轮渡/航班/火车保持 `demo_fixture`；失败回退演示并标注；结果缓存 24h | 海边咖啡馆 → **Omotesando Koffee(IFC)，香港中环金融街8号ifc商场1层1032号铺**；步行 9 分钟、30 点道路几何；按真实时间到店 |
| 模型回信 | `app/web_communicator/persona.py`：主人在设置开启后才调用；只用宠物名/物种/性格、确认过的称呼与 private_chat 叮嘱、此刻状态；清洗链接/自称模型；失败回模板；`composed_by` 如实标注 | 回复“主人～我也想你！我正趴在窗边练歌呢，还学了一段雨声……”（与领养伙伴“爱唱歌、会模仿雨声”一致） |
| 接待模型回应 | `ReceptionStartRequest.use_model`（默认否）→ `model_conversation`，披露服务商；只生成接待员一句回应+一个问题，便笺仍逐字摘录原话；已禁止“记下了/已保存”类说法（首测发现后修正提示词） | 回应“好，哥哥……它叼球出门时，是跑在前面等你，还是回头看你有没有跟上？”；候选仍为三条原话 |
| 冒险插画 | `app/web_journey/illustrations.py`：主人开启 `generated_photos` 后，冒险事件排异步任务（去重、2 次重试、失败可重画），后台线程只在生图可用时启动；私有文件，仅主人可读 | 咖啡馆小侦探插画 24 秒生成（JPEG 656KB，原创绘本风、含服务商“AI生成”水印）；他人读取 404 |
| 网页底图（0.2.2，14:13 追加） | `app/web_providers/basemap.py` + `GET /map/basemap`、`GET /media/basemaps/{id}`：服务端代理高德静态地图（港澳及珠三角），整数缩放、网格吸附、24h 缓存、每日 200 张与每人 40 张上限；共享地图组件 `shared/map` 在 live 模式自动叠加，投影与底图像素对齐，不可用时退回示意图 | 真实步行路线（31 点）叠加在真实高德底图上沿中环行人天桥走到 IFC，无坐标偏移；未登录 401；演示模式不请求、控制台无错误 |
| 意图判断器 | `app/intent_layer/llm_judge.py`：JSON 信号、依据片段必须能在原文找到；默认 mode=off 不变 | 20 条中文对照：规则基线 16/20，configured_llm 20/20（中位 1.75s），见 `docs/contracts/INTENT-EVAL-20260922.md`（含偏差说明） |

付费调用合计（本阶段）：DeepSeek 23 次（连通 1、应用内 2、意图对照 20）；高德 5 次（连通 2、应用内 3）；Seedream 1 张；Google 6 次均被拒。服务端返回模型名为 deepseek-flash（请求 deepseek-chat），已分开记录。

测试：新增 `tests/test_web_providers.py`、`tests/test_web_provider_units.py`（假实现注入，不触网）；后端全量 **171 OK（1 既有 skip）**；门禁与 `gen_web_contract --check` 通过；契约升至 0.2.1（全部追加字段，TS 生成为可选属性），前端 typecheck 与 26 项 vitest 通过（含 codex-r7k 当前改动）。

前端（BLOCKED，待用户协调）：codex-r7k 13:35 领取了 identity/reception/communicator 等 feature 目录，本窗口未改动这些页面。所需界面改动已写入本窗口日志 13:37 的“接口差异记录”（设置开关与披露、接待“用模型回应”选择、通讯来源标注与插画处理中/失败/重画）。在前端接上之前，这些能力可经 API 使用，默认关闭不影响现有页面。


## 9. 宠物自主世界（2026-09-22 下午，按用户方向实施；契约 0.2.3，全部为追加）

用户方向：这是情感疗愈产品，给离开的宠物一个世界、给主人慰藉，游戏性为留存服务。宠物是自主 agent，主人只给建议；照片写实，不把宠物卡通化。详见 `docs/contracts/WEB-CONTRACT-v0.2.md` §9a，各阶段记录见本窗口日志的 pet-agent-world 条目。

| 方面 | 做了什么 | 在哪里 |
|---|---|---|
| DNA 扮演 | DNA 就是注册和接待时主人给的内容，主人可以补充和修改；DeepSeek 扮演时读取 DNA、此刻状态和最近经历 | `app/web_pets/dna.py`、`app/web_communicator/persona.py` |
| 星球通讯器 | 按状态回复：睡着等醒来、飞行等落地、在路上或在店里晚一点；排队的消息到点一定回复，多条合并成一次；危机时立即回应并给出求助热线；TA 主动发消息像微信一样，随机时刻、按性格多少，发生了事随时发，每天最多 6 条，不推送 | `app/web_agent/{reply_policy,proactive}.py` |
| 家与日常 | 家是一个概念：8 类共 27 个国内片区，坐标模糊处理；家附近散步、喝一杯、进城逛逛；按家的类型打工，工钱存进银行卡 | `app/web_home/place.py`、`app/web_journey/local.py` |
| 自己决定 | 白天每半小时考虑一次，出门节奏看 DNA，没钱就散步或打工；主人的建议和“今天别出门”会被认真考虑 | `app/web_agent/life.py`、`POST /journey/suggest` |
| 菜园 | TA 在家也可能被偷：醒着 75% 会发现小偷，打盹时 35%；赶跑小偷或睡着时被偷，都会主动告诉主人 | `app/web_farm/service.py` |
| 攻略手账 | 进城或出远门时 TA 写一日小攻略，站点用高德核对到真实地址，主人可以照着走；开启生成照片时附写实手账图 | `app/web_journey/guides.py`、`GET /guides` |
| 邮局明信片 | 回程路过邮局寄明信片（TA 写的话，开启生成照片时附写实自拍），存进收藏 | `app/web_collection/service.py` |
| 朋友 | 同一时间同一地点才算遇到；双方都开了公开动态才会结识；星球居民明确标注；关系随见面次数累积 | `app/web_social/friends.py`、`GET /friends` |
| 生图 | 升级到 Seedream 4.5（写实，每张至少约 369 万像素，保留“AI生成”水印）；没有照片的伙伴先生成一张证件照作为参考 | `app/web_providers/images.py`、`app/web_journey/illustrations.py` |
| 世界定时器 | 进程内每 30 秒推进旅程、TA 的决定、排队回复和主动消息 | `app/web_agent/ticker.py`（`PETJOURNEY_WEB_WORLD_TICK_SECONDS`） |

真实验证与费用见本窗口日志（第四阶段 PROGRESS）。前端需要配合的地方写在本窗口日志的“接口差异记录”第 1–15 条，由 Codex 前端窗口实现。

仍待决定或受外部条件限制：
- GPT / Gemini 生图对比：需要对应密钥；它们的官方接口不对香港和内地开放，需要在其他地区另放一台转发服务器；
- Google（海外片区与地点）需要先开通计费；
- 模型扮演与生成照片仍需主人明确开启（数据会发送给服务商），建议在入住流程里询问；
- 出发站由“主人直接出发”改为“给 TA 的建议”需要前端配合，旧接口暂时保留兼容。


## 10. 证件卡包、驾考与生活记录（按 BACKEND-PRODUCT-ALIGNMENT-2026-09-22；契约 0.2.4，全部为追加）

- 能力差异表：`docs/contracts/CAPABILITY-GAP-IOS-WEB-20260922.md`，列出旧 iOS、旧后端与当前网页的对照，并区分代码 / 本地验证 / 联调 / 上线；暂缓的能力保留条目并写明原因。
- 证件卡包 `app/web_credentials/`：
  · 身份卡、星球银行卡、照护档案在入住时签发，签发时间就是入住时间；
  · 护照在第一次出远门时签发，到达后盖纪念章；
  · 登机牌、船票车票按实际行程段签发；
  · 驾驶证只能由驾考签发；
  · 编号稳定唯一，同一事件只签发一次；银行卡直接展示现有钱包和账本。
- 驾考 `app/web_driving/`：
  · 流程是愿望 → 报名 → 陪练或自学 → 理论与场景考试 → 补考 → 签发 → 自驾；
  · 考场上 TA 自己作答，服务端计分并记录错题；
  · 无证自驾返回 403，打车、坐火车、坐飞机不受影响。
- DNA 行为画像 `app/web_agent/profile.py`：作息、出门频率、路线兴趣、工作倾向与分享多少。
- 打工记录与生活时间线：`GET /jobs`、`GET /timeline`。
- 攻略可复用：核实过的站点带导航链接和可复制地址；星币预算与现实花费分开；计划与到过的地方分开。
- 验证：
  · 后端全量 234 项通过（1 项为原有跳过），arch、dependency、contract_diff 门禁通过，契约为 92 个枚举 / 152 个模型 / 86 条路由；
  · 本地 live 实跑通过（证件、银行卡流水、驾考从不及格到拿证、时间线）；
  · 未联调、未上线。

## 11. 独立核查修复与前端交接（契约 0.2.5；依据 BACKEND-REVIEW-2026-09-22）

- P1 驾考签发一致性：
  · `app/web_driving/service.py` 让考试通过与驾驶证签发在同一次提交里完成（`CredentialService.insert` 在调用方的事务里签发），一只宠物一本 C 照（`source_key=driver_license:C`）；
  · `reconcile` 补签旧数据里“已通过未签发”的记录，签发时间取通过考试的时间，在读取 `/driving`、`/credentials`、世界定时器运行、进程重启后都会触发；补签前阶段为 `license_pending`；
  · `app/web_driving/notes.py` 发件箱：消息与状态同事务写入、提交后投递，失败补投。
- P2 陪练：
  · 按组结算（迁移 `m1420_driving_consistency`）；
  · `POST /driving/practice` 与 `POST /driving/exam` 接入现有幂等执行（必须带 Idempotency-Key）；
  · 服务端校验题目、选项与这组题的关系。
- P2 DNA：`app/web_agent/dna_reading.py` 按小句处理否定、纠正、混合与含糊说法，结论带原话出处，经 `PetDNAView.behavior` 展示。画像统一为一份，作息、自主生活、主动消息都读它；只用 DNA 与允许用于家中互动、出行偏好的叮嘱。
- 顺带修正：
  · 银行卡流水不再记 0 元旅费；
  · 时间线回家标题与同一时刻的顺序；
  · `backend_version` 改为 web-mvp-0.2.5。
- 前端交接：`docs/coordination/FRONTEND-HANDOFF.md`（10 个待接页面的接口、真实示例、状态、刷新方式、演示数据与验收路线）；本地演示库脚本 `scripts/seed_web_demo.py`。
- 验证：
  · 后端全量 255 项通过（1 项为原有跳过）；新增 DNA 回归 9 项、驾考一致性 11 项；
  · 门禁通过：arch、dependency、contract_diff 与 `gen_web_contract --check`（96 个枚举 / 157 个模型 / 86 条路由）；
  · 前端 typecheck 通过，vitest 41 项通过；
  · 核查方的反例脚本复跑后三个问题均不再复现。
- 状态：未联调、未上线。

## 12. 爪爪驾校：主人陪考，宠物拿证（契约 0.3.0；2026-09-22 晚，按用户方案实施第一、二阶段）

- 规格与方案：`docs/contracts/DRIVING-SCHOOL-v1.md`。替换 0.2.4–0.2.5 的“宠物按掌握程度自动答题”驾考（前端从未接入旧接口）。
- 后端 `app/web_driving/`：
  · `sim.py`、`replay.py`：确定性车辆模型与判定（30 Hz，只用加减乘除与 sqrt，常数来自场地配置），压线按连续段、锥桶每个一次、出界与超时、科三路线检查点与红线（自动制动）；
  · `courses.py` 场地（两套变体，补考换变体）、`questions.py` 固定题库（补考换题）、`curriculum.py` 课程与按性格的台词、`rules.py` 机会与冷却、`grading.py` 计分、`sessions.py` 考局存取、`service.py` 驾校服务（只结算一次、同事务签发驾照与借车券、领证仪式、旧版补签、定时任务）；
  · 迁移 `m1430_driving_school`；路由 13 条（`app/routers/web/driving.py`）。
- 前端 `PetJourneyWeb/src/features/driving_school/`：总览、科目（上课 / 练习 / 约考确认）、全屏考局（答题；驾驶画面、方向盘与按钮两种转向、踏板、停稳后换挡、转向灯、出发前检查、视频邀请）、成绩单（扣分明细、回放与标记、错题回顾）、领证仪式、倒车入库体验版；入口插槽 `circle.places`（新增）、`home.panels`、`journey.cards`；页面与演示数据按需加载（主包 559 KB）。
- 跨语言样例：`scripts/gen_driving_fixtures.py` 生成 `PetJourneyWeb/tests/fixtures/driving-golden.json`（11 个用例）与 `src/fixtures/driving-school.json`；`--check` 由后端测试调用。
- 验证：
  · 后端全量 269 项通过（1 项原有跳过）；驾校专属 29 项＋18 个子测试；门禁 arch / dependency / contract_diff / `gen_web_contract --check`（101 个枚举 / 178 个模型 / 94 条路由）/ `gen_driving_fixtures --check` 通过；
  · 前端 typecheck、vitest 73 项（驾校 32 项）、build 通过；
  · fixture 模式无头浏览器 390×844 实测：报名、练习讲解、约考确认、正式答题（选择 / 排序 / 拖放）、交卷成绩单、科二三项连考与项间过渡、中途离开再回来（tick 一致）、科三红线与回放、领证仪式、深色与减少动效；考试页顶部 / 训练场 / 操作区实测 84 / 506 / 253 像素。
- 状态：live 界面未联调（不在浏览器里代为输入口令）；未上线；阶段 3 未做。

