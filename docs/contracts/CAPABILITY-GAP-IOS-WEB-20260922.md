# 能力差异表：旧 iOS → 旧后端 → 当前网页（2026-09-22）

维护：`claude-20260922-014933-307b`。依据 `docs/product/BACKEND-PRODUCT-ALIGNMENT-2026-09-22.md` §11 的要求编写。旧 iOS 与旧后端的证据来自本窗口对源码的逐项盘点（静态阅读，路径见各行）；网页一列是本窗口当前的后端实现。

**证据等级**（每一项只写已经达到的最高一级）：

- **代码**：代码已存在，并有假实现的自动化测试覆盖（不访问网络）；
- **本地验证**：在本地 live 后端（127.0.0.1:18761，接真实供应商）用接口实际跑通过；
- **联调**：前端页面与后端接口一起跑通过；
- **上线**：部署在公网环境。

截至本文，本表中本窗口新增的能力都**没有联调、没有上线**：前端页面由 Codex 前端窗口实现，所需改动见本窗口日志的“接口差异记录”第 1–15 条及本表的“前端接口”列。香港环境部署的是早先的 MVP 快照，不含本表新增的能力。

**分类**：✅ 已完成 · 🟡 只有展示或推导 · 🔁 需要迁移 · ➕ 需要新增 · ⏸ 暂缓（写明原因）

路径缩写：`I/` = `PetJourneyIOS/PetJourneyIOS/`，`B/` = `PetJourneyBackend/app/`（旧引擎），`W/` = `PetJourneyBackend/app/`（网页 `web_*` 等模块）。

## 1. 账号、身份与 DNA

| 能力 | 旧 iOS | 旧后端 | 当前网页 | 分类 / 证据 | 缺口与下一步 | 前端接口 | 验收方式 |
|---|---|---|---|---|---|---|---|
| 注册登录 | Apple 登录 `I/Views/SignInView.swift:53` | `B/routers/auth.py:56` | 用户名+密码、可吊销会话 `W/web_identity` | ✅ 本地验证 | 邮箱找回未做 | `/auth/*`、`/session` | 注册→登录→退出 |
| 宠物 DNA | 7 个字段编辑 `I/Views/DNASettings.swift:4` | `B/routers/pets.py:145` | DNA 就是注册、照片与接待资料；没保存过时自动整理成草稿，主人可改 `W/web_pets/dna.py` | ✅ 本地验证（DeepSeek 按 DNA 回话） | 前端 DNA 页未做 | `GET/PUT /pets/{id}/dna` | 注册资料出现在草稿里，改完即生效 |
| DNA 影响生活 | 无（性格只进聊天） | `B/pet_guide_engine/scoring.py:75` 只用于攻略打分 | 行为画像：作息、出门频率、路线兴趣、工作倾向、分享多少 `W/web_agent/profile.py`；0.2.5 起按小句读否定、纠正、混合与含糊说法 `W/web_agent/dna_reading.py`，结论带原话出处，说不准的不归类；只用 DNA 与允许用于家中互动/出行偏好的叮嘱 | ✅ 代码 + 本地演示库实跑 | 仍是确定性规则（不是模型判断）；主人不能直接改结构化作息选项 | `PetDNAView.behavior` | 核查反例“不爱熬夜，不爱热闹，喜欢安静”→ 平常作息、恋家、每天出门 1 次（`tests/test_web_agent_dna_reading.py`） |
| 稳定宠物身份 | 编号取 petID 尾部 `I/Models/PetCredentialModels.swift:408` | 无持久身份证 | 宠物 ID 与证件号分开；改名字、照片不换身份 | ✅ 代码 | — | `/credentials` | 改资料后编号不变 |
| 写实形象 | 本机头像，换设备丢图 | 上传存盘 | 主人上传照片为准；没有照片的伙伴先生成一张写实证件照作为参考 `W/web_journey/illustrations.py` | ✅ 本地验证（Seedream 4.5） | 前端头像需标注“AI 生成” | `PetPrivateSummary.photo_generated` | 同一只宠物多张照片外貌一致 |

## 2. 家、工作与星球银行卡

| 能力 | 旧 iOS | 旧后端 | 当前网页 | 分类 / 证据 | 缺口与下一步 | 前端接口 | 验收方式 |
|---|---|---|---|---|---|---|---|
| 家（环境→城市） | 无（固定三城轮换） | `B/providers/map_providers/mock.py:13` 48 小时轮换 | 8 类 27 个国内片区，坐标模糊；重复提交同类型不换城市，迁居才换 `W/web_home/place.py` | ✅ 本地验证（大连、青岛、北京） | 交通枢纽数据未加；海外片区等 Google | `GET/PUT /home/place`、`move-in.habitat` | 重登、重启后城市不变 |
| 打工 | 无 | 无 | 岗位按家的类型与 DNA 选；走到工作地点、干满时长、工资按旅程只入账一次 `W/web_journey/local.py` | ✅ 代码 | — | `GET /jobs`、出发站 `work:*` | 刷新、重复读取只发一次工资 |
| 星球银行卡 | 钱包（旅贝/星尘/功勋）`I/Views/TravelViews.swift:221` | `B/routers/economy.py:23` | 银行卡就是现有钱包账户：余额和流水直接读统一账本 | ✅ 代码 | — | `/credentials/{银行卡}` 的 balance、ledger | 余额与家园钱包一致 |
| 没钱的日常 | 无 | 无 | 没钱就散步、打工或在家；不依赖主人给钱 `W/web_agent/life.py` | ✅ 本地验证（钱不够时拒绝进城） | — | — | 余额不足时只会散步或打工 |

## 3. 证件卡包（对齐说明 §5）

旧版六张证件全部在客户端现算，不落库；签发日取设备当天日期，每天都在变（`I/Models/PetCredentialModels.swift:400-595`）。旧后端只有证件生图提示词（`B/credential_prompt_builder`、`B/schemas/place.py:38`），没有签发。网页已改为服务端签发：编号稳定唯一、签发时间持久、同一事件只签发一次（`W/web_credentials/service.py`，迁移 `m1400_credentials`）。

| 证件 | 旧 iOS | 当前网页 | 分类 / 证据 | 前端接口 | 验收方式 |
|---|---|---|---|---|---|
| 宠物 ID / 身份卡 | 始终拥有，编号 PJ-ID-末 6 位 | 入住时签发，签发时间＝入住时间 | ✅ 代码 | `GET /credentials`、`/credentials/{id}` | 隔几天刷新编号与日期不变 |
| 星球银行卡 | 无 | 入住时开户，展示现有账户 | ✅ 代码（新增） | 同上 | 同上 |
| 照护档案 | 健康状态、疫苗“星尘印记”（虚构） | 主人确认的习惯、爱吃、怕什么、叮嘱；只给主人看；不捏造医疗记录 | ✅ 代码 | 同上（private） | 其他账号 404 |
| 护照 | 始终拥有，跨境时“启用” | 第一次出远门（跨境）签发，以后的远行关联同一本；到达后盖纪念章 | ✅ 代码 | `stamps` | 两次远行只有一本护照 |
| 爪爪驾驶证 | 始终拥有（装饰） | 只能在爪爪驾校四科全过的那次结算里签发（一只宠物一本 C 照），同时发驾校借车券；领证仪式生成合影收藏 | ✅ 代码 + 前端页面 | `/driving`、`/driving/ceremony` 与 `/credentials` | 见第 4 节 |
| 登机牌 | 联网模式拿不到（任务状态从未推进） | 按实际航段签发；待出发→在途→已使用 | ✅ 代码 | 同上 | 随航班时间变化 |
| 船票 / 车票 | 高铁票为占位 | 按实际轮渡、火车段签发 | ✅ 代码（新增） | 同上 | 同上 |
| 酒店房卡 | 休息时解锁、一移动又锁 | 列出条目与获得条件，暂不签发 | ⏸ 当前旅程都是当天往返，没有过夜入住；出现过夜行程后按入住/退房签发 | 同上（not_obtained） | — |
| 世界杯 Fan Pass、景点票根 | 占位 | 未做 | ⏸ 世界杯彩蛋未迁移（见第 5 节） | — | — |

## 4. 爪爪驾校：主人陪考，宠物拿证（0.3.0，替换 0.2.4–0.2.5 的陪练与场景考试；规格见 DRIVING-SCHOOL-v1.md）

| 能力 | 旧版 | 当前网页 | 分类 / 证据 | 前端接口 / 页面 | 验收方式 |
|---|---|---|---|---|---|
| 学车愿望与报名 | 无 | TA 坐车多了、性格好奇时自己产生愿望；主人陪 TA 报名；报名满一天 TA 邀请主人陪练 | ✅ 代码 + 页面 | `GET /driving`、`POST /driving/enroll`；`/school` | 前端页面流程测试 |
| 四科与上课练习 | 无 | 科一路边小课堂（选择、拖放标志、排先后）、科二倒车入库 / 侧方停车 / 弯道、科三小城路线送菜、科四五段情境；分步教学、扣分项与红线开考前展示；练习不限次数，有提示 | ✅ 代码 + 页面 | `GET /driving/curriculum`、`/driving/sessions/**`；`/school/subject/:subject` | fixture 模式浏览器实测 |
| 机会与冷却 | 无 | 每科首次＋一次补考；两次不过从第二次结算起冷却 7×24 小时（服务器时间）；已通过保留；不卖补考和冷却 | ✅ 代码 | 同上 | `tests/test_web_driving_school.py`、`tests/driving-school.test.tsx` |
| 公平与续考 | 无 | 资源加载完点“开始”才计次；暂停、断线、离开后按服务端记录接着考，不重新抽题、不抹掉扣分；平台故障作废不计次；放弃二次确认并计为不通过 | ✅ 代码 + 页面 | `begin` / `pause` / `abandon`；全屏考局 `/school/session/:id` | 浏览器实测：离开再回来 tick 一致 |
| 服务端复算 | 无 | 科二科三前端 30 Hz 实时驾驶，服务端用同一套确定性模拟按操作记录复算；样例逐位一致 | ✅ 代码 | `POST …/inputs` | `tests/test_web_driving_sim.py`、`tests/test_web_driving_golden.py`、`tests/driving-sim.test.ts` |
| 拿证与自驾 | 无 | 同一事务签发驾照、借车券与拿证消息；领证仪式盖章合影（“以后，换我载你去看世界”）；无证自驾服务端拒绝（403），其他交通方式不受影响；借车券抵一次租车费 | ✅ 代码 + 页面 | `/driving/ceremony`、出发站 `local:drive_trip`；`/school/ceremony` | `tests/test_web_driving_license.py` |
| 驾驶中不看视频 | 无 | 科三考“视频邀请”，不真的打开视频；同行影音沿用“驾驶者不看视频” | ✅ 代码 | — | 路线样例 `route.b.no_signals` |
| 比赛现场体验版 | 无 | 倒车入库体验版，只在本机运行，不计成绩、不发证 | ✅ 页面 | `/school/try` | 前端测试确认不调用驾校服务 |
| 阶段 3 | — | 其他训练场与车型外观、居民委托与拿证后的短途故事、车辆购买与车库、成绩分享、家里展示柜 | ⏸ 未做 | — | — |

## 5. 旅行、地图与寻味

| 能力 | 旧 iOS | 旧后端 | 当前网页 | 分类 / 证据 | 缺口与下一步 |
|---|---|---|---|---|---|
| 自主出行 | 按时钟推进的固定模板 | `B/agent_engine/helpers.py:132` | TA 按 DNA、钱包、建议自己决定出门 `W/web_agent/life.py` | ✅ 本地验证 | 远途目的地仍只有香港演示线路 |
| 真实地点与路线 | MKDirections 步行 | 高德/Google 可选 | 高德地点与路线估时；Google 未开通计费 | ✅ 本地验证 | Google 需开通计费 |
| 动物世界班次 | 喵航等（iOS 本地） | `B/transport_reality/mock.py` | 喵航、爪爪铁路、海獭轮渡，稳定班次号 `W/transport_world` | ✅ 代码 | 核验时刻表来源未接 |
| 地图车辆、音符/电视 | 地图+导航视角 | — | 车辆沿路线移动、音符/电视打开播放器，没有同行舱 | ✅ 代码（MVP） | 前端视觉由 Codex |
| 真实底图 | MapKit | — | 港澳用高德静态底图，海外为示意图 | ✅ 本地验证 | 海外等 Google |
| 寻味 | 无（旧版没有） | 无 | 分店+菜品证据、宠物与主人偏好分开 `W/food_discovery` | ✅ 代码（MVP） | 真实商家菜单与口碑未接入 |
| 第一人称导航视角、开场俯冲、昼夜氛围 | `I/Views/JourneyMapView.swift:690` | 无 | 未做 | 🔁 需要迁移（前端） | 交给前端窗口评估 |
| TA 的一天回放 | `I/Models/JourneyDayRecapModels.swift:28` | 无 | 生活时间线已提供数据 `GET /timeline` | 🟡 数据有，回放页未做 | 前端按时间线做回放 |
| 街区榜 | `I/Views/Map/StreetRankSheet.swift:4` | `B/street_rank.py:16` | 未做 | ⏸ 高德扫街榜接口未确认；不编造名次 | 确认数据来源后再迁移 |
| 世界杯彩蛋 | 球场图层、Paw Pass、球迷包 | `B/travel_quest_engine/quest_flow.py:233` | 未做 | ⏸ 首发不在范围；保留条目 | 需要时从旧任务数据迁移 |
| 旅行心愿与任务攻略 | `I/Views/TravelViews.swift:297` | `B/routers/travel.py:22` | 主人建议（`POST /journey/suggest`）替代心愿；攻略由出行自动生成 | ✅ 代码 | 旧任务的“赛后下一步”不迁移 |

## 6. 攻略、手账、明信片与照片

| 能力 | 旧 iOS | 旧后端 | 当前网页 | 分类 / 证据 | 缺口 |
|---|---|---|---|---|---|
| 攻略手账（图片为主） | 3 页手账、14 种风格 `I/Views/SecondaryViews.swift:207` | `B/illustrated_guide/engine.py:38` | TA 出发时写攻略；站点用高德核对；开启生成照片时出写实手账图；核实过的站点带导航链接和可复制地址；星币预算与现实花费分开；计划与到过的地方分开 `W/web_journey/guides.py` | ✅ 本地验证（《布丁的南锣一日游》4 站核实，中文手账图正确） | 多页与多风格未做 |
| “看 TA 的一天 / 我也想照着走” | `I/Views/SecondaryViews.swift:4` | `B/pet_guide_engine/authoring.py:32` | 攻略的 stops、nav_url、copy_text 支持“照着走” | 🟡 数据有，双模式页面未做 | 前端 |
| 电子明信片 | 仿实物明信片册；自动只发第一张 | `B/event_generator.py:97` | 进城或出远门时回程路过邮局寄一张：TA 写的话＋写实自拍，存进收藏 `W/web_collection` | ✅ 本地验证 | 前端明信片册 |
| 此刻自拍 / 请 TA 拍一张 | 占位永远“洗印中” | `B/routers/pets.py:281` 有接口 iOS 无入口 | 店里合影：开启生成照片时出写实照片，否则是纸质卡片，不冒充照片 | ✅ 代码 | 通讯器“请 TA 拍一张”未做 |

## 7. 星球通讯器、守菜与社交

| 能力 | 旧 iOS | 旧后端 | 当前网页 | 分类 / 证据 | 缺口 |
|---|---|---|---|---|---|
| 按状态回复 | 睡着/飞行排队 `B/communicator/reply_policy.py:44` | 同左 | 睡着等醒来、飞行等落地，推迟的消息到点一定回，多条合并；危机时立即回应并给求助热线 `W/web_agent/reply_policy.py` | ✅ 本地验证 | — |
| 原声＋点击翻译 | `I/Views/JourneyPetCards.swift:6` | `B/agent_brain.py:101` | 未做 | ➕ 需要新增 | 可在模型回信里加“动物原声”一层 |
| TA 的小想法、需求与心情 | `I/Views/JourneyLiveSignal.swift:78` | `B/pet_life_engine/tick.py:36` | 行为画像与此刻状态已有；“小想法”卡片未做 | 🔁 需要迁移 | 可由 `moment`＋`profile` 生成 |
| 主动分享 | 念头只在地图卡片 | `B/event_generator.py:77` | 像微信：随机时刻、按性格多少；发生了事随时发；每天最多 6 条；不推送 | ✅ 本地验证 | — |
| 附件：位置卡、贴纸 | `B/communicator/attachment_planner.py:40` | 同左 | 未做 | 🔁 需要迁移 | 位置卡可用此刻状态生成 |
| 守菜 | 无 | 无 | 在家也可能被偷（醒着 75% 发现、打盹 35%）；赶跑小偷或睡着时被偷都会告诉主人 | ✅ 代码 | — |
| 朋友圈 / 星球圈 | NPC 点赞 `B/communicator/npc_society.py:120` | 同左 | 真实跨账号动态、点赞、评论、关注、屏蔽 `W/web_social` | ✅ 本地验证（MVP） | — |
| 好朋友 | 6 个固定 NPC，无关系 | 同左 | 同一时间同一地点才算遇到；星球居民明确标注；关系累积 `W/web_social/friends.py` | ✅ 代码 | 前端朋友页 |
| 推送 | APNs `B/notifications.py:57` | 同左 | 不做（网页阶段） | ⏸ 用户决定网页阶段不推送；做 App 时再接 | — |

## 8. 回忆、收藏与经济

| 能力 | 旧 iOS | 旧后端 | 当前网页 | 分类 / 证据 | 缺口 |
|---|---|---|---|---|---|
| 生活时间线 / 回忆档案 | MemoryHub 聚合 `I/Views/MemoryHub.swift:6` | — | 旅行、打工工资、证件、纪念章、驾考、朋友、明信片、收藏串成时间线 `W/web_agent/timeline.py` | ✅ 代码 | 前端回忆页 |
| 可校准的记忆档案 | 增删改、6 类筛选 `I/Views/MemoryEditor.swift:5` | `B/routers/memories.py:24` | 接待记忆可纠正、撤回（MemoryPolicy） | 🟡 有纠正撤回，没有完整的记忆档案页 | 🔁 迁移筛选与重要度 |
| 小收藏、纪念品、种子、勋章 | `I/Views/TravelBagSouvenir.swift:277` | `B/agent_engine/souvenirs.py:17` | 种子、勋章、明信片、共同听看回忆 `W/web_collection` | ✅ 代码（MVP） | 纪念品估值与出售未迁移 |
| 旅行小包 | 4 个预设＋留言 `I/Views/TravelBagSouvenir.swift:112` | `B/agent_engine/travel_bag.py:21` | 未做 | ⏸ 首发不在范围；保留条目 | 需要时迁移（影响纪念品） |
| 集市 / 交易 | 纪念品出售 | `B/economy_engine/engine.py:208` | 居民商店与订单 `W/web_market` | ✅ 代码（MVP） | 玩家交易暂不开放（对齐说明 §8） |

## 9. 仍需外部资源或用户决定

- Google 地图（海外片区、地点与路线）：需要在其 Cloud 项目开通计费。
- 核验时刻表、真实商家菜单与口碑、授权影音作品：未提供数据来源。
- 生图 API 选型：本次不讨论（用户指示）。
- 前端联调：本表新增的全部接口都需要前端页面配合，由 Codex 前端窗口实现。前端接入说明见 `docs/coordination/FRONTEND-HANDOFF.md`（0.2.5）。
