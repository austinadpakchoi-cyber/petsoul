# 照片导演（包 P）实施交接

窗口：`claude-20260923-055300-ada5`。更新时间：2026-09-23 11:23 +08:00（本机实测）。
分支 `codex/petsoul-web-integration`，HEAD `980feabc`。**全部未提交**（工作树文件，无 SHA）。
本文覆盖 P0–P3，并已清理早期批次的过时指纹与待办。

**状态口径（先读这一段）**：代码已写、禁网用例 **186 项通过（作者自测，不是独立验收）**、依赖门禁通过；
本包全部文件 ≤30 定义 / ≤800 行。整仓架构门禁以 I 的口径为准，本包自身合规。

**真实供应商图：已有 8 张**（2026-09-23 07:59–08:03，四场景 × 新导演/旧模板对照，规则导演、文本调用 0 次，
估算 2.00 元、未对账）。它们证明的是**提示词编译这一层**：时段与室内外天气分层、事实约束、镜头模式互斥，
这三样都能在真图上看到。它们**不证明网页版已接入**——那八张走的是我自己的离线执行器
（`scripts/run_photo_director_batch.py` 直连 provider，**绕过 `SeedreamIllustrator`，因而不进计量账**），
不是 `web_journey/illustrations.py` 的 worker 路径。**主人的「像不像它」评价仍未给出**，本文不替他下结论。

**接入状态：已接通。** 登记侧 B 的 `web_agent/photo_wiring.py` 与 I 的 `routers/web/pets.py`、
执行侧 A 的 `illustrations.py` + `photo_director_bridge.py` 都已交付；
worker 现在按 `directed` 分支走导演（`illustrations.py:316`），`build_selfie_prompt` **不再无条件**，
没有 `scene_key` 的旧路径行为不变。我没有改过 A/B/C/I 的任何文件。

**独立验收（Q）——据 I 转述，不是我的自测**：Q 的 c24–c29 合并小批 **6/6 PASS**。其中 C25 四场景走到真实 worker：
实收 prompt 与**同次** `bridge.compile_call` 输出逐字相同、`size` 均为 `2048x2048`、
参考图 bytes 的 SHA-256 等于该宠物**真实上传**的那张，四只宠物四个 SHA 互不相同；
缺必需身份参考的那只是 **0 发送、0 预占**，`last_error = image director_hold:identity_reference_missing`。

**它证明了什么、没证明什么**：证明的是**链路忠实传递**（worker 实际发出去的就是导演编译的那份，
没有被旧模板顶替）与 **hold 行为**（缺身份参考在预占前停住，没有先付费画证件照）。
**不证明「像不像它」**——那件事只能靠主人看真图，本文不替他下结论，我也不宣布任何项目级验收。

---

## 一、P0：iOS 正式链路与旧实现的实测结论

完整调用图与行号在窗口日志的 P0 PROGRESS 段。影响迁移决策的四条：

1. **iOS 不写提示词。** `RemotePetJourneyService.swift:91`/`:261` 只 POST/GET 宠物 ID，
   镜头与提示词全在后端（`agent_engine/photo.py:10,58` → `place_interactions/mission.py:68` → `event_generator.py:222`）。
2. **旧"模型照片导演"从来没真正跑起来过。** `app/photo_mission_brain/openai.py` 全部导入只有两行，
   却用到 6 个未绑定名字。禁网隔离执行证明：`draft()` 返回 `None`、`last_remote_error = "name 'json' is not defined"`；
   首个失败点在 `openai.py:142`，**比发网络请求更早**，再被 `openai.py:30-32` 的 `except Exception: return None` 吞掉，
   于是 `mission.py:68-69` 每次都落到规则模板。→ **不存在"搬过来就有模型导演"这回事。**
3. **旧 `quality_report` 是提示词 lint，不是看图。** `photo_pipeline.py:40-69` 全程对提示词字符串做关键词判断，没有任何像素输入。
4. **两处不能原样搬**：`event_generator.py:242-243` 生成失败时返回 `place.photo_url`——把**没有宠物的环境图**当自拍；
   `:317-319` 直接按 URL 下载地点图。另外 GET `photo_mission` 会写 trace 与取地图（`agent_engine/photo.py:19,26,46`），
   与 AGENTS.md 的"读接口纯读"冲突。

---

## 二、四个目标场景：每一项输入从哪里读

P3 已把生产路径**收敛到四个场景**：`cafe` / `train` / `home` / `flight_adventure`
（`recipes.TARGET_SCENES`）。其余 7 个场景的配方已写好，但世界侧还产不出它们要的事实，
所以标成 `fact_source="fixture_only"`：**正式世界事件走到它们会被 `scene_has_no_fact_source` 直接拒绝**，
只在评测输入（`origin="evaluation_fixture"`）里可选。
这样配方库能先写好，**不要求其他窗口为了它去扩建所有世界玩法**。

下表是 2026-09-23 只读核对的现状。"缺口"那列是接入时必须补的，不补就只能用规则导演的保守默认。

| 导演输入 | 现有来源（已核对） | 持有人 | 缺口 |
|---|---|---|---|
| 事件 `event_id` | `journeys.photo_request` → `f"photo:{visit.visit_id}"`；`collection.selfie_request` → `source_key`（`web_agent_wiring.py:247,267`） | B | 无。直接用作 `SceneFacts.event_id` |
| 事件版本 `revision` | **没有** | B/C | 需要一个随事件更正递增的代数，用于 `event_revision_changed` 围栏 |
| 地点 `city` / `place_label` | `place=visit.place["name"]`、`city=journey.city`（`web_agent_wiring.py:248`） | B | 无 |
| 场景 `scene` | 目前是写死的一句中文（`scene="在店里靠窗的位置坐着"`） | B | 需要换成场景键（`cafe`/`train`/`home`/`flight_adventure`） |
| 拍摄时间 `captured_at` | **没有**。任务创建时间≈生成时刻 | B | 需要**带时区、按宠物当时所在城市**的时间（走 `city_timezones`）。传错会让夜里的照片变成白天 |
| 已核验事实 `facts` | **没有**。现在只有一句写死的场景文案 | B | 四场景所需：`at_cafe` / `coffee_cup` / `photographer_present`；`on_train` / `train_seat` / `train_window` / `audio_player`；`at_home` / `home_blanket`；`flight_adventure` / `flight_helmet` / `safety_harness` / `earned_medal`；外加 `weather_*`。**没有的事实就是没有**，导演不会推断 |
| DNA | `character_of(pet_id) -> (species, name, personality)`（`web_composition.py:353`） | I | 只有一段自由文本性格。需要按 `catalog.DNA_FIELDS` 投影成封闭词表（`project_photo_dna`），**不能把主人原话直接塞进来** |
| 参考照 | `reference_photo_of(pet_id) -> (bytes, mime)`（`web_composition.py:359`）；缺照时先由 `portrait_saver` 生成基准照 | I / A | 缺**稳定 `reference_id` 与 `sha256`**。导演用它们做身份锚点与缓存键，没有就防不住"换了参考还命中旧图" |
| 外貌特征 `appearance_tags` | **没有** | I | 可选。给了会进提示词（"橘色毛、虎斑花纹…"），不给则只靠参考图 |
| 照片授权 | `illustrations.opted_in = generated_photos_of(user_id, pet_id)` 读家庭 `generated_photos` 设置（`web_composition.py:365`） | I | 对应 `PhotoAccess.generated_photos`。另外三位（`photo_dna` / `reference_use` / `text_director`）**目前没有对应开关**，见第五节 CR-P-to-I |
| 版本代数 `versions` | privacy_epoch 等在运行层 | B/I | 需要 identity / dna / privacy / activity 四个代数，用于提交前复核 |
| 图片额度 | `illustrations.reserve(...)`（`illustrations.py:250`） | A | 不变。导演**不碰**图片额度 |

---

## 三、把导演输出送到图片请求：现网接不住什么

只读核对（2026-09-23）：

| 位置 | 实际情况 |
|---|---|
| `web_providers/images.py:100` | `Illustrator.render(prompt, reference: tuple[bytes,str] \| None = None, size="2048x2048")`——**只收一张参考图，没有负面提示词参数** |
| `web_providers/images.py:122` | 唯一那张参考被写死成 `role="pet_identity"` |
| `image_provider/seedream.py:21,86` | `REFERENCE_ROLE_ORDER = {"pet_identity": 0, "place_environment": 1}`，按它重排——**不认识 `companion_identity`**，会排到 99 |
| `web_journey/illustrations.py:227` | 实际尺寸 `2048x2048`（手账 `1440x2560`） |

**本包已据此修了一个自己的缺陷**：`DEFAULT_SIZE` 从 `1024x1024` 改成 `2048x2048`——
该模型要求每张约 369 万像素，原值低于门槛会被供应商拒。

**新增 `app/web_photo_director/delivery.py`，让丢字段不再是静默的**：

```python
from app.web_photo_director import plan_delivery, CURRENT_WEB_SINK, describe_gap

plan = plan_delivery(photo, CURRENT_WEB_SINK)               # 默认 strict=True → 语义丢失直接抛错
plan = plan_delivery(photo, CURRENT_WEB_SINK, strict=False) # 允许降级，但 plan.dropped 逐条写明丢了什么
describe_gap()                                              # A 的对齐清单
```

在现网能力下，`strict=True` 会直接抛 `delivery_would_drop_fields:negative_prompt`——
**宁可不出图，也不发一张"负面词没生效、同伴不见了"却看不出来的照片**。
`strict=False` 时 `plan.dropped` / `plan.notes` 逐条说明原因。A 扩完能力后改 `CURRENT_WEB_SINK` 这一个常量即可。

**语义丢失的判定覆盖两种写法**：角色不认识记作 `<role>`，超出张数上限记作 `reference:<role>`。
后者曾经漏判——一个"字段全支持、但只接一张参考"的入口会在 strict 下悄悄把同伴丢掉。
现在任何 `reference:` 前缀或角色名都算语义丢失；同时保留正常对照：单宠照片在单参考入口上仍然 `lossless`。

---

## 四、本包运行边界的修复（P3）

1. **控制流异常不再被吞。** `port.py` 原来是 `except BaseException`，
   会把取消、Ctrl-C、进程退出一并吞掉，然后**继续往下出一张规则图**。
   现在 `KeyboardInterrupt` / `SystemExit` / `GeneratorExit` / `asyncio.CancelledError`
   如实结算成"结果不明"之后**原样抛出**；只有普通 `Exception` 才走降级。
   反例：`test_web_photo_director_resume.ControlFlowTests`（4 项）。

2. **稳定编号 ≠ 只调用一次。** `model_operation_id` 对同一事件稳定，但那只是个**名字**——
   进程崩在发出之后、任务被接管重跑、worker 重启，都会拿着同一个编号再调一次。
   新增可注入的 `DirectorMemo`（`memo.py`，**存储归 A**，本包只定义形状与复用规则）：

   - 记到 `sent_ok` 且拍法仍合法 → 直接复用，**一次都不再调用**；
   - 记到 `sent_unknown` / `invalid_output` / `refused` → 那次可能已计费或已被拒，**不再调用**，走规则；
   - 记下的拍法在当前上下文已不合法（事实变了、撤权了）→ 也**不重新调用**，走规则并标 `recorded_decision_stale`；
   - **没有注入备忘时**，跨进程保证不成立，会如实记成 `memo_absent`，不假装已经防住。

   反例：`test_web_photo_director_resume.RetryDoesNotRecallTests`（5 项，含"重启后全新 chat/budget 实例仍不调用"）。

3. **结算故障不能盖掉更重要的信号。** 中止分支里原先直接 `budget.settle(...)`，
   它一抛错就替换掉了原始异常——调用方看到 `RuntimeError`，真正要紧的「租约已失效」被埋掉。
   现在 `_safe_settle()` 吞掉结算故障并返回它；中止路径把这一笔挂到要抛出的异常上
   （`exc.photo_director_unsettled`），可选的 `on_settlement_failure` 做单独通知；
   非中止路径则在 `text_call.reason` 追加 `settlement_unrecorded:<类型>`。
   **账本写不进去是要对账的事，不是「这次调用失败了」。**

4. **租约失效必须中止，不能降级出图。** `LeaseLost` 是普通 `Exception`，原先落进降级分支，
   结果是"这份活已经不归这个进程了"却还产出了一张规则图。现在
   `PhotoDirector(abort_on=(LeaseLost,))` 可传精确类；不传则按**类名**兜底（含继承链），
   因为 `LeaseLost` 在 `app/web_platform/lease.py`，本包保持零跨包 import。
   两条路都**先如实结算 `sent_unknown` 保留费用事实，再原样上抛**。

5. **先写后发（write-ahead）。** `port.request_draft` 的 `on_attempt` 钩子在
   **预占成功之后、请求离开进程之前**回调，director 用它写 `outcome="in_flight"`。
   恢复的进程读到 `in_flight` 就当"可能已发出、可能已计费"，**不再调用**。
   这堵住了"请求已发出、结论还没写回就崩"的窗口。

**先写后发已证明的范围**（写在 `test_web_photo_director_memo.py` 的 docstring 里）：
内存备忘下的**异常恢复**防重、重新构造对象后不再调用、陈旧 `in_flight` 仍然挡住重发。
`in_flight` **不会因为放久了就被当成没发出**——代码里没有任何过期短路，
那等于自动重发一笔可能已计费的调用。

**启用模型导演前的门槛**（首批规则导演零文本调用，不必等这些）：
  a. **持久提交下的跨进程恢复**——`MemoDict` 是进程内字典，没有序列化、没有真实存储、没有并发，
     **不构成跨进程证明**；真实进程退出也没有验过；
  b. 并发下同一 `operation_id` 的互斥（现在没有任何锁）；
  c. `in_flight` 的**人工清理**策略（崩死后这条会永久挡住该事件的模型路径——有意的保守，但需要运维手段）。

**闭环先用明确标记为 rule 的模式**：`PhotoDirector()` 不注入 `chat`/`budget` 就是纯规则、零调用，
结果上 `directed_by="rule"`、`text_call.outcome="rule_only"`，不会假装是模型写的。

### 四之二、缺必需项就暂不生成（不靠规则默认补齐）

`readiness(context, access)` 把两类分开：

- **可选偏好**——表情、角度、已核验天气、可选物件、地点参考、外貌标签。规则导演可以给默认。
- **必需项**——场景 mandatory 事实、配方 `requires`、镜头现场前提、身份参考、四项授权、事实来源。
  缺任何一样 → `ready=False`，`reason` 为 `hold_missing_required` / `hold_no_shot_is_possible`，
  并列出**具体差什么**。调用方据此干净地跳过这一轮，**不编造**。

**预检复用最终校验**，不再重写一套：先做能给出更细清单的检查（逐个点名缺哪位授权、缺哪条必需事实），
然后直接调 `validate_context`，任何 `PhotoDirectorError` 转成 `hold_validation_failed` + 原因码。
这堵住了曾经的误报——授权版本过期、参考图属于另一只宠物、事件已被更正、同伴没同意，
以前都是预检放行、最终才拒。现在预检与最终给出**同一个原因码**，并保留合法输入（单宠 / 双宠）的正常对照。

`require_ready()` 给异常流调用方，原因码一致。反例 18 项。

---

## 五、给持有人的最小 CHANGE_REQUEST（均未实施）

### CR-P-to-A（`web_journey/illustrations.py`、`web_providers/images.py`）

1. `Illustrator.render` 扩成多参考 + 负面词，建议：
   ```python
   def render(self, prompt: str, references: list[ImageReference] | None = None,
              size: str = "2048x2048", negative_prompt: str | None = None) -> GeneratedImage: ...
   ```
   旧的 `reference: tuple[bytes,str]` 形参保留一轮做兼容，内部转成单元素列表。
2. `SeedreamIllustrator.render` 不要再把 role 写死成 `pet_identity`，按传入的 `ImageReference.role` 走。
3. 底层重排：`image_provider/seedream.py` 的 `REFERENCE_ROLE_ORDER` 需要加
   `"companion_identity": 1`（并把 `place_environment` 推到 2）。**身份图必须排第一**。
   如果不改重排逻辑，请改成"尊重调用方给的顺序"，由本包的 `build_references` 负责排序。
4. `IllustrationService` 加一个可选注入点接本包；为 `None` 时**行为完全不变**（继续走 `build_selfie_prompt`）。
   接上后用 `photo.prompt` / `photo.negative_prompt` / `photo.size` / `photo.references`。
5. 任务/缓存键并入 `photo.context_key`、`photo.prompt_version`、`photo.config_version`——
   换参考、换宠物、撤权都不会误命中旧图。
6. **`DirectorMemo` 的持久化归 A**：按 `operation_id` 存一行
   `{outcome, reserved, recipe, expression, visible_facts, provider_label, requested_model, effective_model, reason}`，
   与任务同一事务写入即可。没有它就没有"重启不重复调用"的保证。
7. 建议一并存下 `photo.story_mode` 与 `photo.review_points`（后者是真实成图后逐条人审用，**不是**程序结论）。
8. **不改动** A 现有的 unknown / 不自动重发 / 重画新尝试规则；导演不触碰图片额度。

### CR-P-to-B（`web_agent_wiring.py` 与运行调度）

1. ~~传写死的中文场景句~~ **已由 C 交付**：`web_agent/photo_wiring.py:20`
   `photo_request_in(conn, visit, journey, *, captured_at, source_key)` 已传
   `scene_key` + `scene_facts` + `captured_at` + `place_timezone` + `hold_reason`。
   **版本代数仍缺**（第二节缺口列），首批按 10.2 的办法全填 0 并在日志标注。
2. 装配 `PhotoDirector(chat=..., budget=..., memo=...)`，**默认 `chat=None`**（纯规则、零调用）。
3. 只在**已提交**的拍照事件上调用，**不在任何读接口里调用**（AGENTS.md：读接口纯读）。
4. 每事件最多一次文本请求已在 `port.py` 内保证；B 侧不要再加重试外层。

### CR-P-to-I（组合根、配置、契约）

1. 两个新开关，建议默认关：`PETJOURNEY_WEB_PHOTO_DIRECTOR_MODE`（`off`/`rule`/`model`，默认 `rule`）、
   `PETJOURNEY_WEB_PHOTO_DIRECTOR_DAILY_PER_PET`（导演文本调用的**独立**日额度，不并入图片或 brain 额度）。
2. `reference_photo_of` 需要一并返回**稳定 `reference_id` 与 `sha256`**。
3. 许可映射：`PhotoAccess` 的 `photo_dna` / `reference_use` / `text_director` / `companion_photos`
   目前没有对应开关。**不要**把现有"模型回信"直接等同于 `text_director`——那是两个不同用途。
4. `character_of` 需要能给出按 `catalog.DNA_FIELDS` 投影后的封闭词表 DNA。
5. 本包**不扩公共 schema、不加路由、不加迁移**；契约 0.4.2 不受影响。

### CR-P-to-C（旅程提交）

`SceneFacts.captured_at` 必须是**宠物当时所在城市**的带时区时间（走 `city_timezones`，不是宿主机时区）。
时段光线直接由它推导。本包只校验"必须带时区"，换算归调用方。
另需要一个随事件更正递增的 `revision`，用于 `event_revision_changed` 围栏。

---

## 六、交付文件与指纹（P3 冻结）

**冻结口径**：本包文件在「正式接入 + 八张对照人审」这一阶段**不再改动**，除非
(a) 用户提出新缺陷、(b) A/B/I 接入时提出必须的接口调整、(c) 真实成图人审要求改提示词。
任何改动都会在窗口日志新增一条记录并给出新指纹。

**权威指纹表在窗口日志 `WINDOW-claude-20260923-055300-ada5.log.md` 的「P3 冻结」段**
（区间 A 实现 / B 测试与 fixture / C 工具与文档）。文档里不再重复一份会过期的副本。

**指纹随每批变化。** 为避免文档与磁盘不一致，权威清单只保留一份，在窗口日志
`WINDOW-claude-20260923-055300-ada5.log.md` 的 **P3 HANDOFF 第三节**。
本包当前构成（13 个实现文件 + 8 个测试文件 + 3 个 fixture + 1 个脚本）：

```
app/web_photo_director/  __init__ catalog recipes contracts validation draft
                         rules compiler port memo delivery director privacy
tests/                   test_web_photo_director_{scenes,cameras,identity,guards,
                         model,budget,wiring,resume}.py
tests/fixtures/photo_director/  scenes.json builders.py harness.py
scripts/                 evaluate_photo_director.py
```

`privacy.py`（SHA256 `A215E34C52A1CD74`）是 pd8f 交下来的原件，一行未改。

---

## 七、验证（实际跑过的）

```bash
cd PetJourneyBackend
TZ=UTC PYTHONPATH=. python -B -m unittest discover -s tests -p "test_web_photo_director_*.py"
# → Ran 186 tests, OK（作者自测；Q 侧的独立合同另算，见第九节）

TZ=UTC python -B scripts/evaluate_photo_director.py \
    --out data/reviews/photo-director-ada5-20260923/offline --compare-template --dry-run
# → 离线用例 12 个；八项对照执行单单独写出；供应商调用 0 次；费用 0

cd .. && TZ=UTC python -B scripts/arch_gate.py         # 当前红：违规在 B 的 test_web_runtime_projection.py，非本包
        TZ=UTC python -B scripts/dependency_gate.py    # 退出码 0
```

条件：`TZ=UTC`、独立新进程、禁网（测试基类把 `socket.connect` / `create_connection` / `getaddrinfo`
换成**断言失败**，任何一次真实连接尝试都会让用例红，而不是静默通过）。

证据目录 `PetJourneyBackend/data/reviews/photo-director-ada5-20260923/`：
- `legacy-static-name-audit-20260923T0605Z.json` — 旧链路 10 份文件的静态未绑定名扫描
- `legacy-brain-offline-probe-20260923T0610Z.json` — 旧大脑禁网实证
- `offline/photo-director-offline.json` — 12 项离线编译结果 + 新旧提示词对照
- `offline/photo-director-pairs-sheet.json` — **八项对照执行单**（尚未获授权）
- `offline/photo-director-contact-sheet.html` — 本地联系表（**图位全空**：没有生成过任何图片）

---

## 八、真实成图执行单：八项，四对（**尚未获授权，一次都没发**）

`scripts/evaluate_photo_director.py --dry-run` 写出 `offline/photo-director-pairs-sheet.json`。
**与 12 项离线评测分开**：离线评测是看配方库编译得对不对，执行单是为了拿到能人审的对照图。

- 设计：四个目标场景（cafe / train / home / flight_adventure），每场景**一旧一新**，共 8 张。
  同一只宠物、同一张固定参考、同一模型与尺寸（`2048x2048`）。
- **本批文本调用 0 次**（固定走规则导演），视觉模型复核 0 次。
- `unknown` **不自动重发、不补图凑张数**——缺的那张就缺着，保留记录与可能的费用。
- **执行单由真实宠物规格驱动**：`--pet <spec.json>`。规格不全 → 状态 `PLACEHOLDER_ONLY`，
  逐条列出阻塞项，**明确标注不可直接用于出图**；齐全 → 用真实身份**重新编译两组提示词**，
  固定参考照摘要、模型、尺寸与参数，不会再带着 fixture 虚构宠物的毛色、眼色与 `fx-` 编号。
- 当前 `data/reviews/photo-director-ada5-20260923/test-pet-spec.json` 仍缺三样，故为 `PLACEHOLDER_ONLY`：
  **`permission=true`**（确认该照片可用于本批次）、**`provider_quote`**（单张实际报价，**未知不得写 0 元**）、
  **`batch_cap`**（本批金额上限）。外貌标签是按照片肉眼填的，**需用户核对**。
  规格文件**不含任何图片字节**，只记路径与摘要；照片不会被复制进仓库。
- 逐张记录：请求 ID、耗时、实际用量/账本、失败样本。

**人审四项**（程序不代填）：
1. 是不是同一只宠物（脸、花纹、体型）
2. 有没有保持真实动物外形（没有人手、人脸、人身）
3. 肢体与接触是否合理（承重、不穿透、器物落在台面上）
4. 场景与镜头是否成立（认得出地方；谁在拍说得通）

**首批走现网单参考路径，负面提示词送不进去**——新导演这一组因此少掉一层保护（禁人手、禁界面控件等），
人审时要把这一点算进去。`adapter_capability_snapshot` 已写进执行单。

**成本**：仓库与 `deploy/web/` 里**没有任何单价配置**，总估价算不出来。
执行单给出算式 `总估价 = provider_quote.unit × 8`，填了单价自动算并与 `batch_cap` 比对；
没填时如实写「无法计算」，**不写 0 元**。次数侧：`web_image_daily_cap=20`（`app/config.py:95`），
八张在内，但那是次数上限不是金额上限。

**停止条件**（写进执行单）：unknown 即停不补发；连续两次 4xx 即停；估价触顶即停；
返回尺寸/模型与执行单不符即停；人审在前两对就判定都不像即停。

**外貌以参考图为主。** 规格里只列看得比较确定的几项，**有意不写死**针毛类别与精确眼色——
一张照片分不清银渐层/shaded/ticked，光线也让眼色在绿与琥珀之间说不准；写死会把身份锁锁到可能不对的特征上。

**提示词长度按成图结果定。** 当前四个目标场景 514–532 字，线上模板 206 字。
公开指南建议更短，但约束更全也更不容易出错——这个取舍本文不下结论，等真图。

---

## 八之二、四对真图的视觉判断（逐场景，非验收）

完整逐图判断写在 `data/reviews/photo-director-ada5-20260923/batch/FOUR-PAIRS-VERDICT.md`，
联系表在同目录 `contact-sheet.html`。只用已有的 8 张，**未重跑、未新生成、零新增付费**。

| | 身份 | 镜头是否成立 | 动作／解剖 | 场景事实 |
|---|---|---|---|---|
| `cafe` | 中（脸比参考宽） | **没成立**（第三人称，不是前置自拍） | 爪子正常；「嘴凑近杯口」只做到凑近，**接触没成立** | 好 |
| `train` | 偏弱（脸明显更圆） | **最好**（鱼眼＋伸出画面的前肢，自拍几何完整） | 肢体正常；动作被镜头挤掉 | **头顶显示屏是伪文字** |
| `home` | **最好**（脸型最接近） | 成立（固定陪拍机位——**本来就不该是自拍**） | 正常；睡姿没落地 | **最好**（夜／窗外雨／室内干） |
| `flight_adventure` | 中偏弱 | 成立（固定座舱机位） | **前爪被画成五指手**，解剖约束没守住 | 好，且虚构标注诚实 |

**查出一条配方自身的缺陷**（不是模型问题）：`train` 把 `front_selfie`（面向镜头）
与「趴着从车窗往外看」（面向窗外）写在同一条配方里，**两者不可能同时成立**。
模型选了镜头、丢了动作——它选对了。这条要改配方，不是改提示词。

**与旧模板比**：`flight` 新图有头盔／安全带／座舱且是写实摄影感，旧图是 CG 感的猫悬空趴在小无人机上、
无任何装具——这一项新图确实更好；**但不是全面更好**，旧图的爪子是正常圆爪，新图反而画成了手。

**口径**：每个场景只有**一对样本，说明不了长期稳定**；
**主人的「像不像它」仍未回答**，本文不代答，也不拿提示词检查冒充视觉验收。

---

## 九、未证明项（请勿当成已完成）

1. **主人的相似度评价未给出——这是最大的一项。** 八张真图我自己看下来：身份脸型仍有漂移、
   咖啡馆那张没拍成自拍。但「像不像它」由主人判定，本文不代判，也不拿我的观感冒充验收。
   Q 的 C25 验的是链路忠实与 hold 行为，**不是视觉相似度**，两者不能互相顶替。
2. **那 8 张真图不能用来证明 worker 路径**——它们走的是我的离线执行器
   （直连 provider、**绕过计量账**）。worker 路径的证据来自 Q 的 C25，不是这八张。
3. 文本导演路径只用**禁网替身**验证；没有真实文本模型调用、没有真实用量数据。
4. **`home` / `train` / `flight_adventure` 的事实来源是「主人主动下命令」**（I 的 `pets.py`），
   **不是世界自己发生的事件**。世界侧能自动产生拍照事件的仍然只有 `cafe` 一条（B 的到店接线）。
   这不是缺陷，但别把它说成「四场景都由世界驱动」。
5. 7 个 `fixture_only` 场景在世界侧没有事实来源，**正式路径不可选**（这是有意的，不是缺陷）。
6. 全仓回归与 CLOSED 口径交 I；Q 的合同验收以 Q 自己的报告为准，本文只转述、不代宣布；
   未浏览器验证、未部署。
7. **`train` 配方矛盾修正后的抑制逻辑，Q 侧覆盖为零。** 经算术复核确认
   Q-C25 的 15/15 **一次都没执行到**它（那四只宠物不带 `look_out_window`，合取条件不成立）。
   目前只有本窗口 `GazeDirectionTests` 6 条自测——**作者自测不等于独立验收**。
   **已定（COORD-P-CLOSEOUT-20260923）**：不新增 Q-C31 抑制逻辑合同，这 6 条作为作者证据保留，
   Q-C25 只按运输／编译链路范围记。**这不是等待项**，而是本批有意留下的覆盖边界。

---

## 十、给 A 的最小接入约定（COORD-0802-P → COORD-P-INTEGRATION 纠偏后定稿）

**首批口径**：规则导演、单宠、固定参考、文本调用 0。本包代码处于冻结状态，下面的签名不会变。

> **2026-09-23 08:2x 撤回声明（COORD-P-INTEGRATION）**：本节初稿有两处写错，**旧写法作废**——
> 1. ~~`versions` 暂时可以全填 0~~ → 版本代数必须来自真实来源，见 10.2a；
> 2. ~~`can_access` / `photo_dna` / `reference_use` 暂时可以填 True~~ → 授权必须从已有权限**推导并标明依据**，推导不出就 hold，见 10.2b。
>
> 另有三处收紧：`context_key` 等只是缓存元数据（10.1）；`at_cafe` 不能对通用 visit 一律断言（10.3）；
> 「300 汉字」是**建议**不是硬限制，脸漂移是**待验证推断**不是八图确证因果（10.6）。

### 10.1 A 侧只需要这四行

```python
from app.web_photo_director import PhotoDirector, readiness

_DIRECTOR = PhotoDirector()          # 零注入 = 规则模式，一次文本模型都不会调

state = readiness(context, access)
if not state.ready:
    return None                      # hold：这次不出图，不编造（原因在 state.reason / state.missing_required）
photo = _DIRECTOR.direct(context, access)
```

用它的四样输出：

| 字段 | 类型 | 怎么用 |
|---|---|---|
| `photo.prompt` | `str` | 直接顶替 `build_selfie_prompt(...)` 的返回值 |
| `photo.size` | `str` | 当前恒为 `2048x2048`，与现网 selfie 路径一致 |
| `photo.references` | `tuple[ReferenceSlot]` | **首批只有一张** `pet_identity`，按 `position` 顺序发 |
| `photo.context_key` / `photo.prompt_version` / `photo.config_version` | `str` | **只作内容来源与缓存元数据**，见下方红线 |

`photo.negative_prompt` **首批不要用**，原因见 10.5。

> **红线（COORD-P-INTEGRATION）**：`context_key` / `prompt_version` / `config_version` 只回答
> 「这张图按哪一版内容生成、能不能复用缓存」。它们**不得**用来构造或改变**已在途的付费 `operation_id`**——
> A 现有的预占编号 `illustration:{task_id}:{attempt}` 与重放保护**保持原样**，导演既不参与也不绕过。
> 一句话：这三个值可以决定「要不要重画」，**不能**决定「这次算不算新的一笔」。

### 10.2 A 要构造的输入（只列首批必须的）

```python
from app.web_photo_director import (
    IdentityReference, MediaReference, PhotoAccess, PhotoContext,
    PhotoVersions, SceneFact, SceneFacts, project_photo_dna,
)
from app.web_photo_director.catalog import DNA_FIELDS
```

| 对象 | 首批怎么填 |
|---|---|
| `PhotoVersions` | **必须来自真实来源**，见 10.2a。推导不出就 hold |
| `PhotoAccess` | **四位授权都要有依据**，见 10.2b。`text_director` 保持默认 `False` |
| `IdentityReference` | `species` 取 `character_of` 的物种；`origin` 用 `owner_original`（有主人原照）或 `original_companion`（生成基准照）；`reference_id`/`sha256` 见 10.4；`appearance_tags` **可以传空元组**，那就只靠参考图 |
| `PhotoDNA` | 用 `project_photo_dna(raw, allowed_fields=..., version=..., projection_id=...)`；值必须落在 `DNA_FIELDS` 的封闭词表里。**不要把主人原话塞进来**，会被 `dna_value_not_allowed` 拒 |
| `MediaReference` | 一张 `role="pet_identity"`，`ready=True, authorized=True`；`source` 按 origin 映射（`owner_original`→`owner_original`，`original_companion`→`generated_canonical`） |
| `SceneFacts` | 见 10.3 |

### 10.2a 版本代数：从 `runtime_epochs` 取，不要填 0

只读核对 `app/web_platform/runtime_epochs.py`（C 持有）：`versions_in(conn, pet_id)` 在**调用方的同一个写事务里**
给出 `runtime_epoch / activity_epoch / privacy_epoch / membership_epoch / dna_version / itinerary_version`。映射：

| `PhotoVersions` 字段 | 取自 | 说明 |
|---|---|---|
| `dna` | `dna_version`（`web_pet_dna.version`） | 直接对应。必须与 `project_photo_dna(version=...)` 传同一个值，否则 `dna_version_mismatch` |
| `privacy` | `privacy_epoch` | **撤权保护就靠它**。用途授权变了会 +1 |
| `activity` | `activity_epoch` | 活动变了会 +1 |
| `identity` | **从参考照 bytes 确定性派生**，与 10.4 的 `sha256` 同源：`int(sha256[:8], 16)` | `runtime_epochs` 里没有身份代数；换了参考照这个值就变，正是它要防的事。**不另建存储** |

`access.versions` 必须用**同一次读取**的值（同一个连接、同一个事务），不要分两次读——
分两次读等于把中途的撤权漏掉，而那正是这道围栏要挡的。
`membership_epoch` 不进 `PhotoVersions`，但它是 `can_access` 变化的信号（见 10.2b）。

### 10.2b 授权：从已有权限推导，并把依据写下来

**不存在独立开关不等于没有许可。** 四位都能从现有的东西推导，但每一条都要在代码注释或任务诊断里写明依据：

| `PhotoAccess` 字段 | 依据（已有的东西） | 推导 |
|---|---|---|
| `can_access` | `illustrations.can_view_pet = pets.is_member`（`web_composition.py:334`） | 家庭成员关系。**这是已有权限**，不是新开关；成员变动由 `membership_epoch` 反映 |
| `generated_photos` | `illustrations.opted_in = generated_photos_of`（`web_composition.py:377`）→ 家庭 `generated_photos` 设置 | 直接用，不改语义 |
| `photo_dna` | 同一份家庭 `generated_photos` 授权 | **依据**：DNA 是注册时主人为**这只**宠物填的，这里只用于**这只**宠物**自己**的照片，不跨宠物、不跨家庭。「同意为它生成照片」已经覆盖「用它自己的资料来编排这张照片」 |
| `reference_use` | `generated_photos` + `reference_photo_of` 的来源约束（`web_composition.py:359` 注释：只用这只宠物自己的照片，不会借用别的宠物或样板照片） | **依据**：参考照本身就是这只宠物的；家庭已同意生成照片 |

**推导不出就 hold。** 典型情形：家庭没设过 `generated_photos`、建立者也没有个人选择 →
`generated_photos_of` 返回 False → `readiness()` 给 `authorisation:generated_photos` 并 hold，
A 直接跳过这一轮，不出图、不编造。

**可选 DNA 偏好为空是允许的**：`project_photo_dna({}, ...)` 合法，导演会走保守构图（场景默认表情与镜头）。
**不要求 I 为首批扩所有回调。**

### 10.3 四场景的事实来源 —— 今天只有一个真的接得上

只读核对（2026-09-23）：世界侧只有 `selfie` / `journal` 两种生图 style，产生自拍事件的只有三处调用点。

| 场景 | 世界侧事件来源 | 结论 |
|---|---|---|
| `cafe` | **有，且已接线**。B 的 `web_agent/photo_wiring.py:20` `photo_request_in(conn, visit, journey, *, captured_at, source_key)`；场景键由 `photo_scene.scene_key_of(journey.destination_key)` 判定 | **已接线**，worker 侧待 A 落位 |
| `train` | **没有**拍照事件。已有的是交通段本身（`app/web_transport/`） | 见 10.3a |
| `home` | **没有**拍照事件。已有的是在家状态与家园地点 | 见 10.3a |
| `flight_adventure` | **没有**，而且**不应该**有世界事件 | 见 10.3a |

**所以「接通四场景」在今天的世界侧只能兑现四分之一。** 我没有替它们编来源，也没有放宽 `readiness()`。
**fixture 里的四场景不等于正式接入完成**——那只是评测输入（`origin="evaluation_fixture"`）。

`cafe` 的事实映射（**B 已在 `photo_scene.verified_facts` 实现**，下表是口径核对，不是待办）：

| 事实 token | 从哪来 | 缺了会怎样 |
|---|---|---|
| `at_cafe` | **确实属于咖啡馆的、已提交的到店事件**。B 拿 `visit.place["category"]` 过封闭词表 `CAFE_CATEGORIES`（`photo_scene.py:41`），认不出就不断言 | **必需**。断言不了 → `readiness()` 给 `hold_missing_required` / `required_fact:at_cafe` → **hold**：0 次图片调用、0 次预占、**绝不回落旧模板**。回落会把「没拍成」伪装成「拍成了」 |
| `coffee_cup` | 点单记录（寻味那边**已确认**的点单）；**没有点单就不要传** | 可选。传了才会画那杯咖啡，不传只会「在店里自在待着」 |
| `weather_sunny` / `_rainy` / `_cloudy` | 已核验天气 | 可选。室内场景会自动渲染成「窗外……，室内保持干燥」 |
| `captured_at` | **主人按下拍照命令的那一刻**，保留**该地点当地时区**（B 用 `photo_scene.place_timezone(visit.place)`，取不到就如实为 None，不回落默认城市） | **必需且最容易传错**：**不是**到店时刻、**不是**排队时刻、**更不是** worker 执行时刻。被执行时刻覆写会让夜里的照片变成白天——真图已验证这条差别 |
| `narrative` | 固定 `"daily_life"` | 必需。填 `fictional_adventure` 会被 `story_mode_not_for_scene` 拒 |
| `revision` | 随事件更正递增的代数 | 与 `access.event_revision` 用同一次读取的同一个值 |

### 10.3a 另外三个场景：现有接口能承载的最小来源

下面是**缺口清单**，不是我要去做的事；由协调窗口定向分派。

| 场景 | 现有接口已有的 | 最小缺口 | 边界 |
|---|---|---|---|
| `train` | 交通段（承运人、班次、在途状态）在 `app/web_transport/`；地点在行程里 | ① 在途交通段产生一个**拍照候选事件**；② 该段承运方式确实是列车；③ 车厢地点标签（不是目的地城市） | `train_seat` / `train_window` 只有在「确实在车上」时才能给；**没有在途段就不能拍火车照** |
| `home` | 在家状态、家园地点（`web_journey/catalog.py:12` 的 `HOME_NODE`）、已拥有物件 | ① 在家时产生拍照候选事件；② 家园地点标签；③ `home_blanket` 取自已拥有物件 | 家是概念片区，**不能落到现实住址**；`at_home` 的语义正是这条 |
| `flight_adventure` | 无，**也不应该从旅行推导** | 一个**主人显式发起**的「拍一张冒险主题照片」请求：`narrative="fictional_adventure"`，`place_label` 写成虚构飞行器 | **明确是主人选择的虚构摄影主题，不是旅行发生了。** 不得由任何交通/旅行事件推导，也不得写进旅程历史或发勋章 |

**还有两个现存的拍照事件不在四场景里**，A 千万不要把导演接到 `request_photo` 的总入口上全量替换：

- `collection.selfie_request`（`web_agent_wiring.py:267`）—— 明信片街边邮筒自拍；
- `web_credentials_wiring.py:96` —— 爪爪驾校证件照。

这两个映射不到任何场景键，硬接会直接抛 `scene_not_supported`。
**正确做法**：`scene_key` **只看目的地，不看有没有拿到事实**。为 None ＝ 本来就不归导演管，
照旧走 `build_selfie_prompt`，这是**正常的旧路**，不是 hold。

这一条 A 与 C 都已交付：`scene_key: str | None = None` 在 `illustrations.py:110,121`，
由 C 的 `photo_scene.scene_key_of(journey.destination_key)` 显式传入。

**三件事不要混**（它们在日志里长得像，处置完全不同）：

| | 触发 | 处置 |
|---|---|---|
| **路由不走导演** | `scene_key is None`（邮筒自拍、驾校证件照、散步进城） | 走旧模板，**正常** |
| **hold** | `scene_key` 有值，但 `readiness().ready is False` | 0 图片调用、0 预占、**绝不回落旧模板** |
| **409** | 命令根本不成立、事件没落库 | 导演**从未被调用** |

### 10.3b 这张照片的由来（`SceneFacts.origin`）——**新增，会影响虚构题材**

原契约只有 `world_event` / `evaluation_fixture`，于是「主人选的虚构飞行题材」只能标成 `world_event`，
等于断言世界上真的发生过一次飞行。**这是本包的缺陷，已修**（COORD-P-BRIDGE-REVIEW）：

| 取值 | 什么时候用 | 谁产出 |
|---|---|---|
| `world_event` | 世界自己发生的事件（到店、上车） | B 的 `photo_wiring` |
| `owner_directed` | 主人按下拍照命令——命令是真的，题材未必是真的 | I 的 `routers/web/pets.py` |
| `evaluation_fixture` | 评测输入。**只有它能解锁 `fixture_only` 场景** | 本包 fixture |

新围栏：`narrative ∈ {fictional_adventure, film_scene}` 时 `origin` **不得**为 `world_event`，
原因码 `world_event_cannot_be_fictional`，经 `readiness()` 表现为 `hold_validation_failed`（结构化 hold，不是异常）。
`owner_directed` **不放宽任何东西**——`fixture_only` 仍然只有 `evaluation_fixture` 能解锁。

登记方需要在 payload 带 `event_origin`，桥接取它而不是写死。

**来源会留痕**：`DirectedPhoto.scene_origin` 原样带出 `SceneFacts.origin`，并进 `evidence()`。
不留痕的话，「虚构题材有没有被记成真事」谁也验不了——包括 Q。

**缺省值的取舍**：`event_origin` 缺失时不要静默回落成 `world_event`——那是**更强的断言**，
「不知道」不能自动变成「世界上真的发生过」。过渡期的正确做法是等两个登记方都显式传上之后，
把缺失改成 hold，原因码用独立的 `event_origin_missing`（别并进 `inputs_missing`：
「忘了声明来源」和「事实不齐」是两回事）。

### 10.3c payload 键名：收敛到 `scene_facts`

只读实测（2026-09-23）：产出方与消费方对不上，**三方单测全绿但真实链路断**。

| | 事实键 | household_id | place_id | revision |
|---|---|---|---|---|
| I `routers/web/pets.py:409` | `scene_facts`（dict 列表） | ✓ | ✓ | ✓ |
| B `web_agent/photo_wiring.py:28` | `verified_facts`（token 元组） | ✗ | ✗ | ✗ |
| A 桥接读的 | **`scene_facts`** | 必需 | 必需 | 必需 |

结论：收敛到 `scene_facts`（消费方与一个产出方都已实现），`fact_basis` **保留**作可追溯依据——
哪条事实凭什么断言，事后要说得出。两个键名并存最危险：两边都「看起来有值」，
谁也不报错，事实静悄悄丢掉，表现成一次合理的 hold。

### 10.3d 两道闸：版本围栏比什么、不比什么

这一节原来没写清楚，害 B 花时间核了一条虚惊（`validation.py:34` 的实际行为）。

**版本围栏只比 `identity` / `dna` / `privacy`，有意不比 `activity`。**
照片内容取决于 `captured_at` 那一刻**已提交的事实**，不取决于宠物此刻在干什么——
已提交的历史照片不因为后来出了门而失效。所以 `visit_ended` 之类的活动事件**不会**让排队中的照片被拒。

| 变了什么 | 结果 | 实测 |
|---|---|---|
| `activity` | **照常出图** | 7→99 仍 `ready=True`，编译成功 |
| `privacy`（撤权） | hold | `versions_changed` |
| `dna`（长相） | hold | `versions_changed` |
| `identity`（换了参考照） | hold | `versions_changed` |

**`event_revision` 是另一道闸，语义容易接错：**

    context.scene.revision  ＝ 这组事实是在**哪一代**事件记录上采下来的（登记那一刻的快照）
    access.event_revision   ＝ **执行这一刻**重新读到的当前代数
    不等 → event_revision_changed → hold

**两边都从 payload 回读就等于没装这道闸**——它们会永远相等。
和 `versions` 是同一个模式：登记快照 vs 执行时实读，缺了后半就空转。

**但「执行时实读」读的不能是 `visit.version`。** 这一条我先前写错过，已更正：

`service.py` 同一事务里，`photo_request_in`（473 行）在 `_commit_activity → update_visit`（495 行，
`version = version + 1`）**之前**，所以照片登记完当场就比当前代数小 1；主人之后正常选座、
点饮品还会继续加。真实 SQL 实测（临时库跑 `repository.py:203` 原句）：

| 时点 | `visit.version` | 按事实算的代数 |
|---|---|---|
| ① 登记那一刻 | 1 | 1778496639 |
| ② `_commit_activity` 之后 | 2 | 1778496639 |
| ③ 主人点了杯饮品（正常生活） | 3 | 1778496639 |
| ④ 地点类目被更正（`at_cafe` 没了） | 4 | **129636654** |

`visit.version` 把「照片所据事实被更正」和「后来正常生活」混在同一个计数器里，
②③④ 全都不等 → **每一张咖啡馆照片都会立刻 hold**。

**最小可实现语义**（纯函数，无新表、无新调度，归 B 的 `photo_scene.py`）：

```python
def fact_revision(place: Mapping | None) -> int | None:
    """只由到访地点的身份与类目决定：place_id | name | category | timezone。"""
    if not place:
        return None
    material = "|".join(str(place.get(k) or "") for k in ("place_id", "name", "category", "timezone"))
    return int(hashlib.sha256(material.encode("utf-8")).hexdigest()[:8], 16)
```

登记侧传 `revision=fact_revision(visit.place)`；执行时读口
`event_revision_of(source_key)` 从**当前**到访记录用同一个函数重算
（`source_key` 是 `f"photo:{visit.visit_id}"`，`service.py:455`，visit_id 可反推）。
两边同一个函数，不需要第二套口径。取值 `0 ~ 2^32-1`，落在本包 `revision: int (>=0)` 契约内。

### 10.4 参考照的稳定 ID 与摘要

`reference_photo_of(pet_id)` 现在只回 `(bytes, mime)`。导演需要 `reference_id` 与 `sha256`：

- **从已有 bytes 确定性计算，不另建存储**：`sha256 = hashlib.sha256(bytes).hexdigest()`，
  `reference_id = f"{pet_id}:{sha256[:16]}"`，`versions.identity = int(sha256[:8], 16)`。
  换了参考照，这三个值一起变，旧图不会被误命中。
- 长期做法由 I 在 `reference_photo_of` 里一并返回稳定 ID（见第五节 CR-P-to-I 第 2 条），**不是首批前置**。

### 10.5 负面提示词：我之前的请求写错了，这里更正

第五节 CR-P-to-A 第 1 条原本写的是「给 `render` 加一个 `negative_prompt` 参数」。
按 COORD-0802-P 核实供应商真实能力后，**那个请求是错的**：

- 方舟 `/images/generations` 的**官方参数表里没有 `negative_prompt`**。
  已核对到的参数：`model` / `prompt` / `image` / `size` / `output_format` / `response_format` /
  `watermark` / `stream` / `sequential_image_generation`(+`_options`) / `tools` / `optimize_prompt_options`。
- 网上「Seedream 支持 negative_prompt」的说法多来自**第三方转售平台**（自己套了 SD 风格参数），
  不能当作方舟直连的能力。
- **边界：这是文档核对，没有实测。** 要确认得发一次带该字段的请求看会不会被 400 拒，本轮不做。

**所以不要加未支持的参数。** 首批可交付策略（COORD-P-INTEGRATION 定稿）：

1. `photo.negative_prompt` **不发**，也**不要**逐字拼进 `prompt`——核心约束（写实动物、不画成人手人形、
   与参考图同一只、接触与承重）**已经在主 prompt 里**，不需要重复。
2. A 调 `plan_delivery(photo, CURRENT_WEB_SINK, strict=False)` 之后**必须**断言：

   ```python
   assert set(plan.dropped) <= {"negative_prompt"}   # 只容许这一项缺失
   ```

   出现任何其他项（身份参考、授权相关、事实相关、`reference:*`、`reference_order`）就 **hold，不出图**。
   **身份参考 / 授权 / 事实一律不准随 `strict=False` 静默丢。**
3. 把 `plan.notes` 里那条「没有负面提示词参数」写进任务诊断，让这张图的局限可追溯。

**如实标注**：把约束留在主 prompt 与独立的 negative 通道**不等价**——正向里的「不要 X」会被模型当作内容提示，
有时反而把 X 画出来；独立负面通道是在采样阶段起作用的，两者机制不同。

### 10.6 观察到的现象与一个待验证的推断

方舟开发者社区文章给的是**建议**：prompt **建议**不超过 300 汉字，超了会「注意力分散、模型忽略细节」。
**这是建议不是硬限制**——官方 API 参数表里没有长度上限，八张图也没有观察到截断或报错。

八张对照的实测：

| 臂 | 汉字数 | 身份锁出现在第几个字符 |
|---|---|---|
| 旧模板 | 164–174 | —（旧模板没有独立身份锁句） |
| **新导演** | **440–462** | **327–341（提示词的后 40%）** |

真图上看到的两个症状（脸型漂移、咖啡馆自拍几何没落地）与这个方向一致。

> **但这是待验证的推断，不是八张图确证的因果。** 新旧两组之间同时变了很多东西——长度、顺序、内容、
> 镜头模式、事实约束——**分离不出单一原因**。要证明「长度/位置导致脸漂移」，必须一次只动一个变量再比。

**冻结结束后的最小变量方案**（一次只动一个变量，顺序执行）：

1. 只把**身份锁提到第 2 句**（紧跟主体+动作），其余一字不改 → 看脸型是否收敛；
2. 只把**总长压到 300 汉字以内**（砍 DNA 子句、合并解剖与接触约束），顺序不变 → 看整体遵循度；
3. 前两条生效后，再把「一只前爪伸向镜头外」提成独立短句，**只测咖啡馆**。

每轮四张（四场景各一张新导演），**不再重跑旧模板**（已有基线）。四张 × 0.25 ≈ **1.00 元/轮，估算未对账**。
**本条不授权新增付费**；是否开跑、跑几轮由用户决定。

### 10.7 首批明确不做的

- 多参考（`companion_identity` / `place_environment`）——首批只发一张身份图；
- `DirectorMemo` 持久化——首批规则导演零文本调用，没有可被重复调用的东西，**不构成阻塞**；
- 模型导演、扩场景、扩配方、双宠——本轮不碰。
