# 自主决策的提交边界：隔离反例证据（工作包 C）

- 窗口：`claude-20260922-234408-91f2`（C）。时间：2026-09-23 04:17 +08:00。
- 证据层级：**隔离反例**。真实网页服务 + 一次性临时库 + 假模型 + 故障注入。不是生产故障复现，也不是自然时间验收；
  没有联网、没有调用真实供应商、没有碰 18763 与 E2。
- 用途：给 I 定位与复核用；I 修完之后由 C 按同一脚本复验，再交 Q 独立检查。
- **状态（2026-09-23 05:06 更新）：第 2～5 节记的是 04:17 的修复前现场，保留不改；修复后的复验结果与结论在第 6～7 节——
  I 的 CR-C1 交付版本 8/8 合格。**

## 1. 怎么跑

```bash
cd E:/petsoul-audit/petsoul
set PYTHONDONTWRITEBYTECODE=1 && set TZ=UTC && python -B PetJourneyBackend/data/reviews/c-91f2-20260923/repro_commit_boundary.py
```

输出写在 `PetJourneyBackend/data/reviews/c-91f2-20260923/evidence.json`（该目录被 `.gitignore` 的 `PetJourneyBackend/data/` 覆盖）。
每个用例自建临时库、跑完即删；脚本内拦截外网，只放行进程内回环（asyncio 需要），本轮 `socket_attempts = 0`。

## 2. 被测文件指纹（本轮运行时，SHA256 前 16 位）

| 文件 | 指纹 |
|---|---|
| `app/web_agent/brain_life.py` | `35ba884384d36371` |
| `app/web_agent/brain_wiring.py` | `3cab668971cd0ca0` |
| `app/web_agent/runtime_view.py` | `6d0d13abd01d9f1e` |
| `app/web_journey/service.py` | `aa57cb2c6b9bdbcf` |
| `app/web_agent/decision/brain.py`（C） | `2b4700ba790693df` |
| `app/web_agent/decision/service_reader.py`（C） | `32c6e0601dc58e76` |

`WebJourneyService.depart` 当前签名：`(user_id, pet_id, home_id, destination_key, now=None, operation_key=None)`——没有版本参数，
所以“提案依据的版本”目前进不了写事务。

## 3. 故障注入点

都落在“提案已经交出、业务还没写库”之间：

- **resolve**：`journeys.resolve` 正在解析地点时注入。这是真实窗口里最长的一段——live 模式下这里会打地图供应商。
- **insert**：`journeys.repo.insert` 写行程前的最后一刻注入。
  *方法学限制*：此处若注入的是**写操作**，会与已经 `BEGIN IMMEDIATE` 的事务争锁，SQLite 直接抛 `OperationalError`，
  出发因此被拒。这是注入方式造成的，**不能当作“这里有保护”**。判断保护是否存在请看 resolve 组。
- **decide**：留在家里时，`projector.runtime.record_decision` 写决策记录前的最后一刻注入。

## 4. 结果（2026-09-23 04:17，第 11 批代码）

| 用例 | 注入点 | 注入内容 | 期望 | 实际 |
|---|---|---|---|---|
| revoke_during_resolve | resolve | 撤回用途授权（`privacy_epoch+1`） | 拒绝旧提案 | **departed**：行程 `work:fishing_port` 照建 |
| dna_during_resolve | resolve | 家人保存新 DNA（`dna_version` 变） | 拒绝旧提案 | **departed** |
| offer_expired_during_resolve | resolve | 时钟越过机会有效期（+11 分钟） | 拒绝旧提案 | **departed**，且 `departed_at` 比提交时刻早 660 秒 |
| activity_changed_during_resolve | resolve | 活动版本变化（`activity_epoch+1`） | 拒绝旧提案 | **departed**（真实的并发出发另有唯一约束兜底，这里只说明版本没被复核） |
| revoke_just_before_insert | insert | 撤回用途授权 | — | rejected，但原因是 `OperationalError`（锁），见上文方法学限制 |
| stay_home_version_change | decide | 撤回用途授权 | 不覆盖决策者与复查时间 | **stayed**，`last_decision_by=model` 照写 |

已经修好的两项（第 11 批，复验通过）：

| 项 | 之前 | 现在 |
|---|---|---|
| 出发时刻漂移 | 模型想 60 秒 → `departed_at` 回填成 60 秒前 | `drift = 0.0s`：出发时刻就是提交时刻 |
| 失败后反复思考 | 5 轮 30 秒 → 5 次模型调用 | 1 次调用后记退避（`next_review_at=+15min`、`silence_reason=brain:bad_output`），其余轮心跳 `continue` |

## 5. 结论与建议（交 I）

1. `brain_life._commit` 的版本复核仍在写事务之外：复核通过之后要走 `resolve`（可能打地图）再写库，窗口不是毫秒级。
   建议把“提案依据的版本”带进 `depart` 的那个 `BEGIN IMMEDIATE` 事务里，与 `bump_in(conn, pet_id, "activity_epoch", now)` 并排核对，
   不一致就整笔回滚并返回明确原因。**核对要用事务里的那个连接**；在事务里调用另开连接的检查函数（例如现在的 `projector.versions`）
   读到的是另一份快照，还可能与自己的写事务争锁（第 3 节 insert 组就是这么被锁住的）。
   *实现路径（2026-09-23 04:46 补）*：第 11 批为 CR-A4 建的 `app/web_platform/uow.py::lane_fence + unit_of_work` 正是这个形态——
   写事务拿到锁之后、写业务之前，用同一个连接执行检查，抛异常就整体回滚。提案复核可以复用同一个机制
   （提交前 `with lane_fence(检查授权/版本/有效期/领域条件)`），只是 `journeys.depart` 目前自己 `storage.connect() + BEGIN IMMEDIATE`，
   没走 `unit_of_work`，需要一并接上。
2. “留在家里”也是一次决策提交：`record_decision` 之前同样要按版本判断，否则旧提案会覆盖决策者与下次复查时间。
3. 机会有效期的判断建议和第 1 条一起放进事务：现在 `_commit` 判完之后到写库之间还能过期。
4. 与其他包的归属：租约失效后的提交归 **CR-A4**；失败退避归 **CR-B2**（第 11 批已按此实现，本轮复验通过）；
   模型建议的复查间隔（`BrainProposal.suggested_review_after_seconds` 目前被丢弃）建议与规则/模型决定权（**CR-B3**）一起处理，不单独改。

## 6. 定向复验脚本与结果

```bash
cd E:/petsoul-audit/petsoul
set PYTHONDONTWRITEBYTECODE=1 && set TZ=UTC && python -B PetJourneyBackend/data/reviews/c-91f2-20260923/verify_commit_boundary.py verify
```

判定口径写死在脚本里（`44c415e8add03269`，440 行），输出 `verify-<UTC时间戳>-<brain_life指纹8位>.json`，**只增不覆盖**，同名自动加序号。
跑前跑后各取一次指纹：中途有人改了被测文件就整份 `verdict=invalid-drift`，每项标 `affected_by_drift`，结论降级为待复验。
全部合格、无 drift、无外网尝试才退出码 0。

### 6.1 每一项"被挡下"要同时满足的 9 条

`injection_fired`（注入确实发生）、`mutation_effective`（注入真的改变了世界：比对前后语义版本／时钟）、`no_crash`、
`rejected`（是明确的拒绝结果）、`reason_expected`（原因正确）、
**`reason_not_ordinary`**（原因不是 OperationalError / IntegrityError / TypeError 这类普通异常——那是注入方式或代码崩了，不是保护）、
`no_journey`（行程条数不变）、`no_charge`（钱包余额与 `economy_transactions` 笔数都不变）、
`no_decision_record`（`last_decision_by` / `last_decision_at` 仍为空）。

### 6.2 结果：2026-09-23 05:06，I 的 CR-C1 交付版本，**8/8 合格**

被测指纹：`journey/service = e53d74f8ae1316d4`（与 I 04:57 日志的交付登记一致）、`brain_life = e53fafbb17c090ba`、
`uow = 2c98bdcb4545b8f8`、`runtime_epochs = 89b3488db6bb4511`。`drift = {}`，`socket_attempts = 0`。
结果文件：`verify-20260922T210652Z-e53fafbb.json`。

| 编号 | 合格标准 | 实际观察值 |
|---|---|---|
| `control_normal_path` | 照常出发、记下决策者、出发时刻＝提交时刻（脚本让模型耗时 45 秒） | PASS：departed、`last_decision_by=model`、`drift_seconds=0.0` |
| `revoke_during_resolve` | 拒绝旧提案，不建行程 | PASS：`versions_changed`，行程 0、余额与账本不变、无决策记录 |
| `dna_during_resolve` | 同上 | PASS：`versions_changed` |
| `activity_during_resolve` | 同上 | PASS：`versions_changed` |
| `offer_expired_during_resolve` | 同上 | PASS：`offer_expired`（解析期间时钟推进 660 秒） |
| `stayed_version_change` | 留家路径同样按版本判断，不写决策记录 | PASS：`versions_changed:privacy_epoch`；入口 `record_decision_checked`、`expected_passed=true` |
| `local_timezone_injected` | TA 在东京时用所在地时区 | PASS：投影与读取层同为 `Asia/Tokyo`，`timezone_of` 已注入 |
| `lease_and_versions_both_apply` | 提案版本复核与进程租约围栏**同时**成立 | PASS：a) 租约失效 → rejected（`missing`）、不建行程；b) 围栏放行＋改版本 → rejected `versions_changed` |

第 8 项是本轮新增，对应"`lane_fence` 的新校验不能覆盖已有租约校验"：a) 用 `lane_fence(assert_lease_held(...))` 包住 `consider`（与 `ticker` 同形），
只对 `depart` 那一段写事务失效——若谁在 `depart` 里嵌套一层自己的 `lane_fence` 做版本复核，外层租约检查会被 ContextVar 顶掉，这项就会 FAIL；
b) 装一个放行的围栏再改版本，确认版本复核没有因为装了围栏而被跳过。两个方向都测。

### 6.3 反向对照：这份工具的"合格"不是空转

```bash
set TZ=UTC && python -B PetJourneyBackend/data/reviews/c-91f2-20260923/verify_commit_boundary.py --mutate-guards
```

只在脚本进程里打补丁（**不改任何业务文件**）把事务内两道复核打掉：`WebJourneyService._assert_still_valid` → no-op、
`RuntimeStore.record_decision_checked` → `expected=None`。结果 **2/8**（`mutation-20260922T210624Z-e53fafbb.json`）：
四项 resolve 全部变回 departed、stayed 变回 stayed 并写下 `last_decision_by=model`；
`control_normal_path` 与 `local_timezone_injected` 仍 PASS；第 8 项里 a) 仍 PASS、b) FAIL。
——说明租约围栏与版本复核是两道**互相独立**的检查。

**证据边界（要点，别读过头）**：`--mutate-guards` 打掉的只有**版本复核**两处，**没有打掉租约保护**。
所以它证明的是"四项 resolve、stayed、第 8 项 b) 这些**版本判据**是活的"，
**不证明**第 8 项 a) 的**租约判据**是活的——a) 在这一跑里之所以仍 PASS，正是因为租约那道根本没被动过。
要验证租约判据本身，需要另做一次针对租约的突变（例如让 `unit_of_work` 忽略围栏、或去掉 `LeaseLost` 的重抛），
那落在 B 的实现与 Q 的验收范围，本包不扩展。

### 6.4 修复前基线与 drift 的如实说明

- **04:17 第 11 批**：`evidence-20260923T0417-35ba8843-before-fix.json`（第 4 节那张表），冻结保留。
- **04:48 旧版脚本 1/7**：`verify-20260922T204724Z-35ba8843.json`，冻结保留。
  **这是一次跑动期间有 drift 的运行**——`journey/service.py` 在取完快照约 3 秒后被重写，`brain_life` / `brain_wiring` 在跑完后也变了。
  它只能当作修复前的**定性**基线，不要把它记录的指纹当成"被测版本"。新版脚本已跑前跑后各取一次指纹，这种情况会直接标 `invalid-drift`。

## 7. 结论、移交与仍待处理

- **CR-C1 已修复并复验通过**：出发路径在 `depart` 的 `unit_of_work` 里用事务自己的连接核版本／有效期／在途（`_assert_still_valid`），
  留家路径在 `record_decision_checked` 的 `BEGIN IMMEDIATE` 里核版本；网络解析仍在写事务之外。CR-C6（`timezone_of`）已接入。
- **交 Q 独立复核**：Q 可直接复跑第 6 节两条命令（判定写死在脚本里，不依赖 C 的解读），或按第 3 节的注入点自行实现；
  `--mutate-guards` 可用来先验证这份工具本身没有空转。证据文件全部只增不覆盖，修复前后可直接对比。
- **CR-C8（新，交 B）**：`brain_life._commit` 的 `except Exception` 把 `LeaseLost` 也吃掉，原因取成 `missing` / `taken_over` / `expired`，
  于是按普通模型失败走 `_back_off` → `record_backoff(silence_reason="brain:missing")`，只给这一只宠物排了下次复查。
  租约丢失意味着这个进程这一任期不该再写任何东西，应当中止整轮交回 ticker；`brain:missing` 对排查也没有信息量。
  第 8 项 a) 可直接当 B 的回归用例。（按 2026-09-23 的分工调整，`brain_life.py` 归 B 写。）
- **仍未做**：CR-C4（建议状态真实语义）、CR-C3（并入 CR-B3，模型建议的复查间隔）。CR-C7 已撤回。
- 若要把其中某条固化成默认测试套件里的用例：`tests/test_web_commit_boundary.py` 与 `tests/test_web_lease_commit_fence.py`
  已在新分工里划给 C，待 I RELEASE、C CLAIM 之后再写。
