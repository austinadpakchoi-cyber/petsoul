# PetSoul 核心修复分工调整

准备时间：2026-09-23，依据约 04:59 +08:00 的黑板与源码核对。

**状态：待用户采纳并发送。本文不是 RELEASE，不改变当前文件所有权。** 用户发送本指令后，以 I 的精确 RELEASE 与接手窗口 CLAIM 生效；生效范围取代上一份 NEXT-BATCH-EXECUTION 中“I 继续独占核心装配、B/C 只复验”的安排，其余约束保留。

## 为什么调整

早期把核心接线集中在 I，避免多人同时改文件。现在运行与提交代码已有形态，继续让 B/C 只提问题、I 实施全部修复，会形成排队。改为领域负责人完成自己的实现和定向测试，Q 保持独立验收，I 做跨包协调和整体交付。

I 最新日志已提供可复验指纹，但明确未释放核心范围。B/C 在接手前仍不能直接改。04:57 的文件快照：brain_life `1309bc3b7698ef01`、brain_wiring `81ac4fbaf8f42ca0`、runtime_view `1e7ea44c8af72ee9`、journey/service `e53d74f8ae1316d4`、runtime_epochs `89b3488db6bb4511`；交接时必须重新读取，不把此表当永久基线。

## B：运行与调度的实施负责人

接手窗口：`claude-20260922-234415-fed3`。原有 web_runtime 与证据目录归属不变。请求 I 移交以下整份文件，路径均相对 PetJourneyBackend：

- `app/web_agent/brain_life.py`
- `app/web_agent/brain_wiring.py`
- `app/web_agent/runtime_view.py`
- `app/web_agent/life.py`
- `app/web_agent/ticker.py`
- `app/web_agent_wiring.py`
- `tests/test_web_brain_life.py`
- `tests/test_web_brain_commit_fence.py`
- `tests/test_web_brain_round_fairness.py`
- `tests/test_web_brain_backoff_semantics.py`

B 先保存当前三分支复验结果，再直接修复自己范围内剩余问题：shadow 留痕、硬恢复时间与只读复查、双层额度事实、异常名额和退避、规则/模型决定权、模型建议的复查间隔。最终发起调用仍经过 A 的原子预占；已结算或 unknown 的旧凭证不是新调用许可。

**runtime_view 中的留家提交也归 B 写。** 使用 C 维护的事务/版本工具，在同一写事务保留租约与语义检查；租约失效不按普通模型失败继续执行。C 可以审阅与提反例，不直接改 B 的文件。

## C：旅程提交与事务保护的实施负责人

接手窗口：`claude-20260922-234408-91f2`。原有 decision/**、测试和证据目录归属不变。请求 I 移交：

- `app/web_journey/service.py`
- `app/web_journey/repository.py`
- `app/web_platform/uow.py`
- `app/web_platform/runtime_epochs.py`
- `tests/test_web_commit_boundary.py`
- `tests/test_web_lease_commit_fence.py`

C 负责解析完成后到最终提交的保护、同连接版本/授权检查、有效期与当前时间、租约丢失、正常路径对照。维护两包共用的 UoW 和版本读取接口，直接修自己范围内的缺陷，不再全部回交 I。

C 对留家路径的跨文件要求交给 B 落实；B 对旅程提交的跨文件要求交给 C。固定现有 `unit_of_work(storage)`、`versions_in(conn, pet_id)` 和 `depart(..., expected_versions=..., valid_until=...)` 的兼容接口。需要改签名时先写出调用方变化和兼容方式，双方一次对齐，不能各造一套。

`lane_fence` 的新校验不能覆盖已有租约校验；网络解析仍在短写事务之外。工具反例必须确认注入发生、拒绝原因和业务副作用，不能把任意异常判作保护成功。

## A、Q、前端和 I

| 窗口 | 调整后的职责 |
|---|---|
| A / 4bef | 继续已接手的生图未知结果、恢复、重画，以及任务/额度/计量实现；不改 C 的 UoW 或 B 的接线文件 |
| Q / 4d18 | 在自己的合同文件独立验证 A/B/C；不改业务实现，也不把作者自测当独立验收 |
| 前端 / r7k | 继续访客到入住及 UI/UX；已释放的共享层按原流程 CLAIM，不等后端所有缺陷关闭 |
| I / 307b | 精确交接、共享契约与组合根协调、迁移顺序、整体回归及前端交接；交出后停止编辑对应文件 |

不要再把“全部迁移/全部测试”笼统变成 I 的实现责任。需要新迁移时，I 一次性分配唯一文件名/顺序并 RELEASE 该新路径，由功能作者写 DDL 和隔离迁移测试；I 维护统一注册与整合。现有其他文件不自动转移，仍按当前 CLAIM。

## 交接与执行

1. I 完成正在编辑文件的一个完整修改，留下可读取状态；逐包记录 RELEASE、当前指纹、未完成项与接口。无需等 E2 或全仓回归结束才交接。正在运行的测试按其实际版本留证，发生漂移不得算新版本通过。
2. B/C 复读最新日志与当前文件，分别 CLAIM 自己那一组。一次登记覆盖本批精确列表即可，不要求逐句确认。
3. 同一个文件不按函数切给两个窗口。B 与 C 的实现问题直接交到文件负责人；仅跨包接口冲突交 I 裁决。不得擅改他人文件。
4. 先跑已有定向反例，再修、再跑受影响测试。I 新交付已经修好的内容不重做；新失败留完整输出。由作者提交实现与证据，Q 独立复核，I 在稳定批次收一次整体回归。
5. Q 复验时只固定受测文件的版本；其他范围继续工作。复验中如文件变化，只作废受影响项，不让整个项目停等。
6. 不创建新窗口/工作副本、不整仓 Git 操作、不新增付费、不部署；不重启或写入 18763/E2。本文不唤醒窗口，也不证明窗口已接单。

## 可发送给 I、B、C 的共用消息

```text
调整 PetSoul 核心修复分工，按 docs/coordination/CORE-DELEGATION-2026-09-23.md 执行。
I 不再承包全部修复：先完成当前文件的完整修改，按文档把运行调度范围精确 RELEASE 给 B、旅程提交和事务工具范围 RELEASE 给 C，保留指纹、接口和未完成项；随后负责跨包协调与总集成。
B/C 读最新黑板，看到自己范围 RELEASE 后 CLAIM，先验证当前版本，再直接修自己范围内的问题并给定向证据。没有释放的文件继续只读。同一文件只有一位写入者；跨文件配合直接交对应负责人，不再全部排回 I。
Q 继续独立合同，A 和前端继续现有任务。沿用原窗口 ID，不重启18763/E2、不新增付费、不部署，不重复已完成报告。
```
