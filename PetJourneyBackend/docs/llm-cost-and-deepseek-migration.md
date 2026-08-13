# PetSoul LLM 成本审计与 DeepSeek / 国产生图迁移方案

> 审计范围：`PetJourneyBackend/app`（Python FastAPI）。只读审计，未改动任何代码/配置。
> 结论先行：**当前文本调用全部走第三方 OpenAI 兼容中转（`api.austinsapi.com`），模型名为 gpt-5.5 / gpt-5.4-mini / gpt-image-2（中转别名），且存在 4 类系统性重复调用**。生图走 gpt-image-2（`/images/generations` + `/images/edits`），是另一大成本源。

---

## 0. 结论速览（TL;DR）

| 维度 | 发现 |
|---|---|
| 有效 LLM 文本调用点 | **6 个**（agent 大脑、照片任务脑、攻略主模型、攻略豆包语音、豆包社媒研究、交通班次检索） |
| 有效生图调用点 | **1 个 provider、3 个调用方**（自拍/明信片、纪念品、图文攻略） |
| 最大重复成本 | ① `photo_mission` 无缓存、每次 App 刷新/发消息都重拉；② 调度器每宠物每 15 分钟 1 次 agent 大脑调用；③ `/pet_guide` 每次刷新都重生成（主模型 + 豆包语音 = 2 次）；④ `/responses` 失败即回退 `/chat/completions` 造成双倍调用 |
| Token 用量记录 | **无**（`engine_trace` 只记 step/state/error，不记 token/价格） |
| 死配置 | `translation_model`、`travel_guide_search_model` 已配置但无任何调用点 |
| 迁移要点 | 全部 `/responses` → `/chat/completions`；`json_schema` strict → `json_object` + prompt 内嵌 schema + 重试解析；去掉 `reasoning.effort`；去掉 `web_search_preview` 工具；生图换火山即梦 Seedream（保参考图一致性） |

---

## 1. 调用点清单表

### 1.1 文本 LLM 调用点（按 cost 影响排序）

| # | 模块/函数 | 端点 + 模型 | 触发时机 | payload 规模 | 推理/verbosity | 失败回退（二次调用） |
|---|---|---|---|---|---|---|
| 1 | `agent_brain.py` `OpenAIPetAgentBrain.speak` (:110-142) | `POST /responses`（:118）→ 失败回退 `/chat/completions`（:122-123）；模型 `agent_model=gpt-5.5` | 每次 `_append_agent_thought`：主人消息、调度器 daily 念头、通讯器回复 | system prompt :301-314 + context :316-339（pet DNA + journey），约 1.2–1.8k token | `reasoning.effort=medium`（:167）、`verbosity=low`（:169）、`json_schema` strict（:170-186） | **是**（任何异常双倍） |
| 2 | `photo_mission_brain.py` `OpenAICompatiblePhotoMissionBrain.draft` (:86-116) | `POST /responses`（:95）→ 回退 `/chat/completions`（:99-100）；模型 `photo_mission_model=gpt-5.5` | 每次 `build_photo_mission`：GET `/photo_mission`、`generate_selfie`、首张明信片 | system prompt :217-237 + context :239-303（place 元数据 + product_rules），约 2–3k token | `reasoning.effort=medium`（:134）、`json_schema` strict（:138-166，14 个必填字段） | **是** |
| 3 | `pet_guide_engine/authoring.py` `_remote_pet_guide` (:33-44) | `POST /responses`（:36）→ 回退 `/chat/completions`（:39-40）；模型 `agent_deep_model=gpt-5.5` | GET `/pet_guide` → `build_pet_guide`（每次刷新都重生成，无缓存） | system prompt :132-143 + context :81-131（**整个 journey_plan 全量 dump** + provided_places[:10]），约 3–5k token | `reasoning.effort=medium`、`json_schema` strict（:23-27，含 guide_stops min 3 / max 5） | **是** |
| 4 | `pet_guide_engine/authoring.py` `_maybe_rewrite_with_doubao_voice` (:200-223) | `POST /responses`（豆包，:211）；模型 `doubao_guide_model=doubao-seed-2-1-pro-260628` | **每份攻略生成后必跑一次**（攻略主模型的第二次调用） | `_doubao_voice_prompt` :162-226（guide + stops + DNA），`max_output_tokens=900`（:160） | `reasoning.effort=minimal`（:148） | 失败则静默保留原文（:221-223，不额外加钱） |
| 5 | `travel_research/doubao_client.py` `guide_research` (:26-56) | `POST /responses`（豆包，:45）；模型 `doubao_guide_model` | `create_quest` 创建旅行心愿（仅中国城市，`engine_base.py:234-237`）；海外目的地是 placeholder，**实际不发 web search** | `_guide_prompt` :114-172，`max_output_tokens=700`（:87） | `reasoning.effort=minimal`（:85） | 无（失败回退本地规则，`engine_base.py:56-57`） |
| 6 | `transport_schedule/openai_provider.py` `best_itinerary` (:33-48) | `POST /responses`（:40）；模型 `transport_search_model=gpt-5.4-mini`；**使用 `web_search_preview` 工具**（:53） | 航班/火车班次规划（`transport_reality.py:215-218`）；默认 `transport_schedule_provider=mock`、`transport_web_search_enabled=false`，**默认不触发** | system :371-382 + context :335-362 + 巨型 `json_schema` :61-119 | `verbosity=low`、`json_schema` strict | 无（失败返回空列表） |

> 已确认**无 LLM 调用**的模块（避免误判）：`owner_intent_brain.py`（纯关键词规则）、`communicator/*`（回复文案全脚本化，仅 `legacy_owner_message` 委托 `journey_engine.owner_message` 触发 agent 大脑）、`photo_pipeline.py` / `photo_prompt_builder.py`（纯 prompt 组装+启发式 QA）、`interview_engine.py` / `story_ticker.py` / `credential_prompt_builder.py` / `illustrated_guide_styles.py`（模板/规则）、`memory_store/*`（hash embedding，无 LLM embedding 成本）。

### 1.2 生图调用点

| 调用方 | 端点 + 模型 | 触发时机 | 频次 |
|---|---|---|---|
| `image_provider.py` `generate_image` (:113-134) | `POST /images/generations`（:128）；`image_model=gpt-image-2` | 图文攻略封面/路线图/时间线（3 页）、无参考图的自拍 | 每次 1 张 |
| `image_provider.py` `generate_image_with_references` (:158-192) | `POST /images/edits`（multipart，:182）；`gpt-image-2` | 带宠物参考图（+地点参考图）的自拍/明信片、纪念品 | 每次 1 张 |
| 调用方 1：`event_generator.py` `_postcard_image_url` (:222-245) | 上述两接口 | `generate_selfie`、首张明信片（elapsed≥35s） | 1 张 + **失败重试 1 次**（:228-239） |
| 调用方 2：`event_generator.py` `souvenir_image_url` (:247-256) | 上述接口 | 纪念品收集 | 每纪念品 1 张 |
| 调用方 3：`illustrated_guide.py` `build` (:119-141) | `generate_image` 1024x1536 | POST `/illustrated_guide/generate` | **每次 3 页 = 3 张**（有文件级缓存，见 §3.5） |

---

## 2. 端到端重复调用追踪（典型用户动作）

### 2.1 主人发一条消息（iOS `/messages` 路径）

`POST /api/v1/pets/{id}/messages` → `legacy_owner_message` → `journey_engine.owner_message`（`owner_interaction.py:14`）：

1. `owner_intent_brain.classify` —— **0 次 LLM**（规则）。
2. `_append_agent_thought`（:45）→ `agent_brain.speak` —— **1 次 LLM**（gpt-5.5，失败则 2 次）。
3. `self.status(pet_id)`（:78，构造 updated_status）—— 0 次 LLM（`_life_snapshot` 规则化）。
4. iOS 端回包后 `await refreshPhotoMission()`（`JourneyViewModel+Communication.swift:41`）→ GET `/photo_mission` → `photo_mission_brain.draft` —— **再 1 次 LLM**（gpt-5.5）。

> **每发一条消息 ≈ 2 次 gpt-5.5 调用**（agent 大脑 + 照片任务脑），且两者各自有 `/responses`→`/chat/completions` 的失败翻倍风险。

> 注意：App 的「通讯器」Tab（`CommunicatorViews.swift:151` 走 `/communicator/messages`）是纯规则、**0 LLM**；但 `JourneyViewModel` 的消息入口（`sendOwnerMessage` → `/messages`）与离线补发（`JourneyViewModel+Lifecycle.swift:114`）会触发 LLM。两条路径并存。

### 2.2 旅行攻略请求

`POST /travel_quests` → `create_quest`（`quest_flow.py:35`）：

1. `research_engine.research()`（`engine_base.py:25`）：
   - 中国城市 → `doubao_client.guide_research` **1 次豆包调用**（`engine_base.py:47-55`）。
   - 海外城市 → provider 是 `openai_web_search`，但**实际不发 web search**（`engine_base.py:199-202` 返回 placeholder，`missing_capabilities` 标记 mock）。
2. `_guide_for`（`quest_flow.py:198-231`）→ **规则化 mock 攻略，0 LLM**。

> 所以「旅行攻略」真实成本 = **仅中国城市 1 次豆包研究调用**；不是"研究 + 主模型 + 语音"三层。主模型攻略是另一条独立链路（见 2.3）。

### 2.3 宠物城市攻略（GET `/pet_guide`）

`lifecycle.pet_guide`（`lifecycle.py:239-245`）→ `pet_guide_engine.build_pet_guide`（`authoring.py:18`）：

1. `_remote_pet_guide` —— **1 次主模型**（gpt-5.5，失败 2 次）。
2. `_maybe_rewrite_with_doubao_voice` —— **再 1 次豆包**（doubao-seed）。

> iOS `refreshDetails()`（`JourneyViewModel+Lifecycle.swift:213-241`）每次进入详情都会 `fetchPetGuide`（:218）→ **每次刷新 2 次 LLM，且无任何缓存**。这是被低估的大头。

### 2.4 照片/明信片/回忆生成

`POST /generate_selfie` → `photo.py generate_selfie`（:58）：

1. `photo_mission(pet_id)`（:66）→ `build_photo_mission` → `photo_mission_brain.draft` —— **1 次 LLM**。
2. **之后**才做去重：`find_postcard_by_mission`（:74）+ 20 分钟冷却（:87）。
3. 未命中才生图：`event_generator.generate_selfie_postcard` → `_postcard_image_url` —— **1 张图**（失败再 1 次 = 2 张）。
4. iOS 生图后再 `refreshPhotoMission()`（`JourneyViewModel+Details.swift:122`）—— **再 1 次 LLM**。

> 关键问题：**第 1 步的 LLM 在去重判断之前发生**——即使明信片已存在/冷却中，`photo_mission` 的 LLM 也照跑不误。

### 2.5 调度器 tick（`scheduler.py`）

`scheduler.py:67 tick()`，`scheduler_interval_seconds=60`（config:52，**每 60 秒扫一遍所有宠物**），每宠物执行 `engine.advance_status`（:79）→ `event_generator.advance`：

- 「connected」念头：仅首次。
- 「daily」念头：`daily_due` 由 `agent_turn_interval_seconds=900`（15 分钟）门控（`event_generator.py:76-93`）→ **每宠物每 15 分钟 1 次 agent 大脑 LLM** = **96 次/宠物/天**。
- 首张明信片（elapsed≥35s 且 0 张）：`build_photo_mission`（1 LLM）+ 生图（1 张）。

> 每宠物每天仅「daily 念头」就产生 **~96 次 gpt-5.5 调用**，这是最稳定、最可预测的成本乘数（N 只宠物线性放大）。

---

## 3. 重复调用与成本黑洞排名（附证据）

### 🥇 P0-1 photo_mission LLM 无缓存，按次重拉（估计乘数 ×3–10）

- 证据：`place_interactions/mission.py:52-63` 每次 `build_photo_mission` 都调 `photo_mission_brain.draft`；mission id 是稳定的（`_stable_photo_id` :123/:189），**但 draft 结果从不缓存**。
- 放大点：iOS `refreshDetails`（:234）、`refresh`（:89）、`hydrateInitialDetails`（:146）、发消息后（:41）、自拍后（:122）**全都会重新拉取**。
- 修复：按 `(pet_id, place.id, local_hour_bucket)` 缓存 draft，TTL 30–60 分钟。

### 🥈 P0-2 /pet_guide 每次刷新重生成（固定 ×2）

- 证据：`authoring.py:18-32` 无缓存；`lifecycle.py:239-245` 每次 GET 都重建；iOS `refreshDetails:218` 每次进详情都调。
- 修复：按 `(pet_id, city, local_day)` 持久化缓存 `PetAuthoredGuide`；或复用 `_journey_plan_cache` 的同款 key 思路。

### 🥉 P0-3 调度器 daily 念头 96 次/宠物/天

- 证据：`scheduler.py:52` 60s 间隔 + `event_generator.py:76-93` 15 分钟门控 + `_append_agent_thought`（`helpers.py:30-64`）每次必调 `agent_brain.speak`。
- 建议：把「daily 念头」改为规则模板（城市 thoughts 列表本就有现成文案 `city.thoughts`），**只有 content_intent 判定需要时**才调 LLM；或把间隔提到 30–60 分钟。

### 4. P1-1 /responses → /chat/completions 双倍回退

- 证据：`agent_brain.py:118-124`、`photo_mission_brain.py:95-104`、`authoring.py:34-44`。中转 `api.austinsapi.com` 若不支持 `/responses` 或 `json_schema` strict，**每次调用都会先失败再重试，文本成本直接 ×2**。
- 修复：迁 DeepSeek 时直接删掉 `/responses` 分支，只保留 `/chat/completions`。

### 5. P1-2 生图失败重试 ×2

- 证据：`event_generator.py:228-239`（首次失败 + repair pass 再生成一次）。

### 6. P1-3 自拍去重晚于 photo_mission LLM

- 证据：`photo.py:66`（先 LLM）→ :74/:87（后去重）。

### 7. P2-1 图文攻略 3 张/次（已有缓存，仅首次花钱）

- 证据：`illustrated_guide.py:120-141` 循环 3 页各生 1 张；`_attach_cached_images`（:605-638）+ `_cached_page_media_path`（:630-638）按 `guide_id+page_index` 文件缓存——**已有缓存，可保留**。

### 8. P2-2 死配置（不花钱但误导）

- `translation_model`、`travel_guide_search_model` 仅出现在 config.py，无调用点。

### 9. 无 token/成本记录

- 证据：`repositories/engine_trace.py` 只写 `steps/state_before/state_after/errors/fallbacks`（:12-37），**没有任何 token 用量或价格字段**。建议加 `usage_json`（DeepSeek 返回 `usage.prompt_tokens/completion_tokens`）以便对账。

---

## 4. 低成本速赢清单（不动架构，先砍重复）

1. **给 photo_mission draft 加进程内/DB 缓存**（按 stable mission id），TTL 30 分钟 —— 预计砍掉 60–80% 照片任务脑调用。
2. **给 `/pet_guide` 结果加每日缓存**（`pet_id:city:local_day`）—— 立即省掉每次刷新的主模型 + 豆包语音（2 次/刷新）。
3. **daily 念头改规则模板**，或把 `agent_turn_interval_seconds` 从 900 提到 1800–3600 —— 每宠物每天从 96 次降到 24–48 次。
4. **删掉 `/responses`→`/chat/completions` 回退**，直接单路径调用（配合 DeepSeek 迁移顺带完成）。
5. **显式设置 `max_tokens`**（现在代码不设，全部依赖服务端默认）：聊天 512、照片任务 800、攻略 1600、语音 900。
6. **自拍去重前置**：在调 `photo_mission` 前先查 `find_postcard_by_mission` / 20 分钟冷却。
7. **生图失败重试保留 1 次但加退避**，或对同 prompt 加短 TTL 防抖。
8. **停用/降频 transport web search**（若生产已开）：默认 `transport_schedule_provider=mock`，除非真的需要真实班次号。
9. **给 `engine_trace` 加 usage 字段**，先能对账再谈优化。

---

## 5. 迁移到 DeepSeek 方案

### 5.1 配置变更（`.env`）

```env
PETJOURNEY_LLM_PROVIDER=openai            # 保持，走 OpenAI 兼容协议即可
PETJOURNEY_OPENAI_BASE_URL=https://api.deepseek.com
PETJOURNEY_AGENT_MODEL=deepseek-chat
PETJOURNEY_AGENT_DEEP_MODEL=deepseek-chat   # 攻略主模型；如需深度推理可换 deepseek-reasoner
PETJOURNEY_AGENT_FAST_MODEL=deepseek-chat
PETJOURNEY_PHOTO_MISSION_MODEL=deepseek-chat
PETJOURNEY_TRANSPORT_SEARCH_MODEL=deepseek-chat
# 豆包语音/社媒研究保持不动（本就是国产，见 §5.4）
```

> DeepSeek 兼容 `/chat/completions`，`base_url` 用 `https://api.deepseek.com`（也接受 `/v1`）。**不支持 `/responses` 端点**。

### 5.2 DeepSeek 不支持的能力 → 逐处替换

| OpenAI 特性 | 使用位置 | 替换方案 |
|---|---|---|
| `/responses` 端点 | `agent_brain.py:118`、`photo_mission_brain.py:95`、`authoring.py:36`、`openai_provider.py:40` | 全部改走 `/chat/completions`（各模块已有 `build_chat_completions_payload` 雏形，删掉 `/responses` 分支即可） |
| `response_format.json_schema` strict | `agent_brain.py:170-186/202-209`、`photo_mission_brain.py:138-166`、`prompts.py:23-27/42-49`、`openai_provider.py:57-119` | 改 `response_format={"type":"json_object"}` + 把 JSON schema 内嵌进 system prompt + 复用现有 `_parse_json_candidate` 容错解析（已支持 ```json``` 包裹与首尾 `{}` 截取，`doubao_client.py:228-244` 是最佳范例） |
| `reasoning.effort` | `agent_brain.py:167`、`photo_mission_brain.py:134`、`prompts.py:20` | 删除；`deepseek-reasoner` 自带思维链，`deepseek-chat` 不支持该字段（传了会 400） |
| `web_search_preview` 工具 | `openai_provider.py:53` | DeepSeek 无 web 检索工具。替换为：国内用现有高德 + 豆包社媒路径（`guide_orchestrator.py:56-61` 已定义优先级 amap→doubao_social）；海外用 Google Places（`google_maps_services.py`）。交通班次若必须真实化，接 12306/航旅纵横类国内数据源，或保持 mock |
| `gpt-image` 生图 | `image_provider.py` | 换国产生图 provider（§6） |
| `max_output_tokens` | 豆包 payload 已用（`prompts.py:160`、`doubao_client.py:87`） | DeepSeek 用 `max_tokens`（字段名不同），需在 chat payload 里新增 `max_tokens` |

### 5.3 代码改动清单（按文件）

1. **`agent_brain.py`**：`speak()` 只走 `build_chat_completions_payload`；`response_format` 改 `json_object`；system prompt 追加 JSON 输出 schema 说明；删 `reasoning`；加 `max_tokens=512`。
2. **`photo_mission_brain.py`**：同上；`max_tokens=900`；schema 文本（14 字段）并入 system prompt。
3. **`pet_guide_engine/prompts.py`**：`_chat_payload` 改 `json_object` + schema 内嵌 + `max_tokens=1800`；`_responses_payload` 删除或保留为豆包专用。
4. **`pet_guide_engine/authoring.py`**：`_remote_pet_guide` 删 `/responses` 分支，只留 `/chat/completions`。
5. **`transport_schedule/openai_provider.py`**：删除 `tools=[web_search_preview]` 与 `/responses`；改造为不依赖 web 检索的规则化班次（或直接停用该 provider）。
6. **`image_provider.py`**：新增国产 provider（§6）。

### 5.4 豆包语音层：**建议保留豆包，不迁移**

理由：
- 豆包已经是国产（火山方舟 Ark），**不涉及 OpenAI 中转费**，且 `doubao-seed` 中文宠物口吻质量是本产品卖点。
- 语音层是「不增删地点、只改写口吻」的低风险二次润色，`max_output_tokens=900`，成本极低。
- 保留后，迁移面最小化：只有 `/pet_guide` 的主模型从 gpt-5.5 → deepseek-chat，豆包语音继续。

> 若想进一步减少供应商数量，可把语音层也换成 `deepseek-chat`（复用同一 base_url/key），但需要重写 `_doubao_voice_payload` 为 chat 格式，收益有限，**不推荐**。

---

## 6. 生图迁移方案（国产 provider）

### 6.1 现状：`image_provider.py` 做了什么

- 接口：`ImageProvider` Protocol（`generate_image` / `generate_image_with_reference(s)`，:32-55）。
- 实现：`OpenAICompatibleImageProvider`（:105-324）。
  - `generate_image` → `POST /images/generations`（JSON，b64/url，:120-134）。
  - `generate_image_with_references` → `POST /images/edits`（multipart，:175-187，把宠物参考图 + 地点参考图作为 `image[]` 上传）。
  - 结果解析支持 `b64_json` 与 `url` 两种（:278-313）。
- **核心诉求**：以「宠物参考图」保持宠物身份一致（`pet_identity` role）+ 以「地点参考图」保持场景真实（`place_environment` role），暖调自拍/明信片风格。

### 6.2 三家国产 provider 对比

| 维度 | 火山方舟 / 即梦 Seedream | 阿里通义万相 wanx | 智谱 CogView |
|---|---|---|---|
| 端点 | `https://ark.cn-beijing.volces.com/api/v3/images/generations` | `https://dashscope.aliyuncs.com/api/v1/services/aigc/text2image/image-synthesis`（**异步，需轮询 task_id**） | `https://open.bigmodel.cn/api/paas/v4/images/generations` |
| 模型 | `doubao-seedream-3-0-t2i` / `doubao-seedream-4-0` | `wanx2.1-t2i-turbo` / `wan2.2-t2i-plus` | `cogview-3-flash` / `cogview-3-plus` |
| 参考图/一致性 | **Seedream 3.0/4.0 支持多参考图 + 角色一致性**（最贴合宠物身份保持） | `wanx2.2` 支持参考图（ref_img）做图生图/风格迁移 | cogview-3-flash 支持 image-to-image 编辑，一致性一般 |
| 响应形态 | 同步返回图片 URL | 提交后轮询结果（异步） | 同步返回 URL |
| 价格量级 | ~¥0.15–0.5/张（分辨率相关） | ~¥0.1–0.4/张 | ~¥0.1–0.3/张 |
| 风格契合度 | ⭐⭐⭐ 暖调写实/自拍/角色一致最好 | ⭐⭐ 插画/海报强，写实自拍一般 | ⭐⭐ 通用，写实弱 |

> **推荐：火山即梦 Seedream 3.0/4.0**。理由：① 端点与现有豆包 Ark 相同（`doubao_base_url` 已配置），可复用同一条 API Key 体系，迁移成本最低；② 多参考图 + 角色一致性直接对应代码里的 `pet_identity` / `place_environment` 双参考图设计；③ 同步返回，改动面小。

### 6.3 `image_provider.py` 改造草图（不写代码，仅示意）

1. `config.py` 新增：
   - `image_provider_type`（`PETJOURNEY_IMAGE_PROVIDER=openai|volcengine|dashscope|zhipu`，默认 `openai`）
   - `volcengine_image_model`（默认 `doubao-seedream-3-0-t2i`）
   - 复用现有 `doubao_base_url` / `doubao_api_key`（或新增 `image_api_key` 指向火山 Key）。
2. 新增 `DoubaoSeedreamImageProvider`：
   - `generate_image` → `POST {doubao_base_url}/images/generations`，payload `{model, prompt, size, n:1, response_format:"url"}`。
   - `generate_image_with_references` → 同样端点，把 `pet_identity` / `place_environment` 参考图按 Seedream 的 image 参数传入（Seedream 支持 1–N 张参考图，需按 role 映射为 `image` 数组）。
   - 复用 `_extract_image` 的 url 分支下载图片。
3. 新增 `WanxImageProvider`（异步轮询）与 `CogViewImageProvider`（同步）作为备选，接口签名一致。
4. `build_image_provider`（:327-330）按 `image_provider_type` 分派。
5. 调用方 `event_generator.py` / `illustrated_guide.py` **无需改动**（都依赖 `ImageProvider` Protocol）。

---

## 7. 分阶段落地清单与预期收益

### P0（1–3 天，纯省钱，低风险）
- [ ] photo_mission draft 加缓存（stable id，TTL 30min）。
- [ ] `/pet_guide` 结果每日缓存。
- [ ] daily 念头改规则模板 或 提高 `agent_turn_interval_seconds`。
- [ ] 删除 `/responses`→`/chat/completions` 回退，单路径调用。
- [ ] 显式 `max_tokens`。
- [ ] 自拍去重前置。

### P1（3–5 天，DeepSeek 迁移）
- [ ] 切 `base_url` 到 DeepSeek + 改模型名（§5.1）。
- [ ] `json_schema`→`json_object` + schema 内嵌 + 重试解析（agent_brain / photo_mission_brain / pet_guide prompts）。
- [ ] 删 `reasoning.effort`；新增 `max_tokens`。
- [ ] transport web_search 停用或改高德/Google 路径。
- [ ] `engine_trace` 加 usage 记录，开始对账。

### P2（5–10 天，生图国产化）
- [ ] 新增 `image_provider_type` 配置 + `DoubaoSeedreamImageProvider`。
- [ ] 灰度切自拍/明信片到 Seedream，验证宠物身份一致性。
- [ ] 图文攻略 3 页切 Seedream（1024x1536 竖图）。
- [ ] 评估 wanx / CogView 作为降级 provider。

### 预期收益（量级估算，供决策）

> 以「假设生产为 20 只宠物、App 日活主人若干、每次进详情都刷新」为基线，实际需用 usage 日志校准。

| 项 | 当前量级 | 优化后 | 说明 |
|---|---|---|---|
| daily 念头 | 20×96 = 1920 次/天 gpt-5.5 | 规则化→0，或 1800s→48 次/天 | 最大单一乘数 |
| photo_mission | 每次刷新/消息/自拍都拉 | 缓存后命中即 0 | 预计砍 60–80% |
| /pet_guide | 每次刷新 2 次 | 每日缓存 → 0（首次后） | 主模型 + 豆包语音 |
| 文本单价 | gpt-5.5（中转价未知） | deepseek-chat（公开价，显著低于 GPT-5 系） | 迁移本身再降单价 |
| 生图 | gpt-image-2（$0.03–0.19/张） | Seedream（¥0.15–0.5/张） | 单张成本显著下降 |
| 失败翻倍 | /responses 回退 ×2 | 单路径 | 消除 |

**结论**：P0 速赢预计能砍掉 50–70% 的文本调用量（去重复），P1 迁移把文本单价再降一个量级，P2 把生图单价与参考图一致性同时解决。三者叠加，`$100/天` 主要来自「无缓存 photo_mission + 高频 daily 念头 + 每次刷新重生成 pet_guide + 失败回退翻倍 + gpt-image 生图」的组合，按本方案落地后预计可降到 **$10–30/天 量级**（以最终 usage 对账为准）。

---

## 附：关键文件行号索引

- 配置：`config.py:21-60`（模型/base_url/reasoning/timeout）、`config.py:96-145`（env 映射）
- agent 大脑：`agent_brain.py:110-210`（payload + 回退）、`agent_brain.py:301-339`（prompt/context）
- 照片任务脑：`photo_mission_brain.py:86-166`、`photo_mission_brain.py:217-303`
- 攻略主模型 + 豆包语音：`pet_guide_engine/authoring.py:18-32,33-44,200-223`、`pet_guide_engine/prompts.py:17-50,81-131,144-226`
- 豆包社媒研究：`travel_research/doubao_client.py:26-88`、`travel_research/engine_base.py:25-132,234-237`
- 交通班次：`transport_schedule/openai_provider.py:33-125`、`transport_schedule/factory.py:11-16`
- 生图：`image_provider.py:113-324`、`event_generator.py:222-256`、`illustrated_guide.py:119-141`
- 调度器：`scheduler.py:67-141`、`event_generator.py:44-114`
- 追踪（无 token）：`repositories/engine_trace.py:12-37`
- iOS 触发频率：`JourneyViewModel+Lifecycle.swift:88-90,140-211,213-241`、`JourneyViewModel+Communication.swift:41`、`JourneyViewModel+Details.swift:113-122`
