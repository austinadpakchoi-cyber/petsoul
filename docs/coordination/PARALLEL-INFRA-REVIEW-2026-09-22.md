# PetSoul 队列与预算并行工作包定向核验

时间：2026-09-22 23:35 +08:00；窗口：codex-20260922-parallel-infra。
Git HEAD：`980feabc7710462a89c5df488c255d04e9e7de08`；检查的是共享工作树当前文件，不把 HEAD 当作未提交源码身份。
范围：只读四个基础设施模块，运行真实类加临时最小 SQLite；只写本报告及自身日志。
结论：两个任务可靠性风险已在隔离环境复现，可拆“任务领取/提交围栏”和“调用前预算预占”两个独立包。
前置条件：Claude 仍持有后端 `app/**`、`tests/**`；以下是分工建议，须由原持有窗口明确释放精确文件后领取，不是本报告自动授权接管。
18763 的自然时间验收保持原样，本轮没有访问该接口、业务数据库或任何供应商。

## 1. 已运行的反例

使用 `D:\python\python.exe -`，设置 `TZ=UTC`、`PYTHONDONTWRITEBYTECODE=1`。
脚本通过 stdin 执行，无探针脚本落入后端源码或测试目录。
真实导入 `app.web_platform.tasks.WebTaskQueue`、`app.web_providers.meter.ProviderMeter`，未替换其实现。
用标准库 `TemporaryDirectory(dir='E:\\petsoul-audit')` 建立临时 SQLite；Storage 适配器仅提供每次独立连接、`sqlite3.Row` 与提交/回滚。
最小表仅有 `web_tasks` 与 `web_provider_usage`；不实例化正式 JourneyStorage，不应用项目迁移。
审计钩子禁止 `socket.connect`、`socket.getaddrinfo`；网络尝试计数为 0。

| 反例 | 执行步骤 | 实测结果 | 证据等级 |
| --- | --- | --- | --- |
| running 到期无法重新领取 | mock `tasks.utcnow=t0`，enqueue；worker-a claim，租期1秒；推进注入时钟至 t0+2秒，worker-b claim | 第二次返回 None；原记录仍 running，attempts=1 | VERIFIED_RUNTIME：真实类、最小表与受控时钟 |
| superseded 被旧完成覆盖 | 对上述真实 task 执行 supersede，再调用旧接口 complete(task_id) | superseded → succeeded | VERIFIED_RUNTIME：顺序陈旧回执反例 |
| 上限检查与记账可交错 | 同一临时库两个 ProviderMeter 实例，cap=1；先分别 allow，再分别 record | 两次 allow 都 True，最终 calls=2 | VERIFIED_RUNTIME：确定性交错；非并发进程压力测试 |

关键输出（原值）：

```json
{
  "expired_running": {"first_status":"running","reclaim_after_expiry":null,"persisted_status":"running","attempts":1},
  "superseded_overwrite": {"before_old_complete":"superseded","after_old_complete":"succeeded"},
  "budget": {"cap":1,"pre_record_permissions":[true,true],"calls_after_two_records":2},
  "network_attempts": [], "source_unchanged": true, "temporary_directory_removed": true
}
```

复现核心调用序列（`queue` 使用真实 WebTaskQueue 和上述临时 Storage）：

```python
with patch.object(tasks, 'utcnow', return_value=t0):
    task, _ = queue.enqueue('probe', 'expired-running', {})
    queue.claim('worker-a', ['probe'], lease_seconds=1)
with patch.object(tasks, 'utcnow', return_value=t0 + timedelta(seconds=2)):
    assert queue.claim('worker-b', ['probe']) is None
    assert queue.get(task.task_id).status == 'running'
queue.supersede(task.task_id, 'source revoked')
queue.complete(task.task_id)
assert queue.get(task.task_id).status == 'succeeded'
```

最小 `web_tasks` 字段：task_id PRIMARY KEY、kind、dedupe_key UNIQUE、status、attempts、max_attempts、payload_json、source_version、run_after、created_at、updated_at、locked_by、locked_until、last_error。
这些测试没有验证生产迁移、HTTP 路由、真实 worker 崩溃、业务副作用或公开环境；不能把上述结果写成现网已丢任务或已超支。

## 2. 静态依据与未验证部分

- `PetJourneyBackend/app/web_platform/tasks.py:83`：claim 仅查询 queued；`:103`、`:143` 的 complete/_set_status 只按 task_id 更新，没有领取者或代数约束。
- `PetJourneyBackend/app/web_platform/tasks.py:167`：run_once 在 handler.run 后 complete；只围栏 complete 无法撤销已经发生的业务写入。
- `PetJourneyBackend/app/web_platform/lease.py:27`：进程租约支持到期换持有者；`:50`、`:57` 报告/释放按 holder 约束，但没有可供领域事务校验的单调 epoch。此项是 VERIFIED_CODE，未做真实长任务接管演练。
- `PetJourneyBackend/app/web_platform/idempotency.py:66`、`:89`、`:97`：占位、handler、完成回执在不同事务；源码自己明确这一限制。异常可删除占位，不代表进程被杀也会清理；本轮未模拟崩溃窗口。
- `PetJourneyBackend/app/web_providers/meter.py:58`、`:62`：allow 与 record 分开，实例内 threading.Lock 只包 record；不是跨进程调用前预算预占。

## 3. 最小文件所有权与集成边界

| 工作包 | 建议独占文件（须先释放） | 包内成果 |
| --- | --- | --- |
| Q：队列与领取围栏 | `app/web_platform/tasks.py`、`app/web_platform/lease.py`；新增 `tests/test_web_task_fencing.py` | 过期 running 回收、领取代数、条件续租/完成/失败、进程 epoch、失效结果拒绝；复用原队列 |
| B：原子预算 | `app/web_providers/meter.py`；必要时新增 `app/web_providers/reservations.py`；新增 `tests/test_web_provider_reservations.py` | 调用前跨进程额度/并发预占，operation_id 去重，完成/释放/unknown 语义 |
| I：原窗口集成 | `app/web_platform/idempotency.py`、全部迁移编号/注册、`web_agent_wiring.py`、`web_worker.py`、组合根、provider 调用点、领域服务与公开契约 | 同连接 UoW 与领域提交 fence；将 Q/B 接入真实调用链，处理兼容、配置与回归 |

以上路径均相对 `PetJourneyBackend/`。Q/B 不修改对方文件，也不直接修改迁移目录、shared schemas、config、main.py、依赖注入或既有综合测试。
Q/B 可在独立单元测试里声明目标最小 schema；生产 migration DDL 作为交接提案交 I，编号与升级验证由 I 单写。
不能在 fixture 上通过就声称已接线；Q/B 交付应带旧调用兼容清单，由 I 统一替换实际调用方。

## 4. 先冻结的接口建议

- Q 返回不可变 Claim：task_id、worker_id、claim_generation、locked_until、runtime_epoch、expected_versions；旧 `complete(task_id)` 不保留可绕过围栏的成功路径。
- Q 提供 `renew(claim)`、`fail(claim, error_code)`；完成采用 `commit_result(claim, conn, expected_versions)` 或等价同连接校验，使领域写与任务状态在一个事务。
- worker 租约返回 holder＋epoch；领取代数、进程 epoch、领域版本职责分开，不能只提高 TTL 替代最终校验。
- B 提供 `reserve(operation_id, provider, purpose, scope, maximum_usage)`、`settle(reservation, outcome, actual_usage)`；同 operation 不重复预占。
- B outcome 至少区分 succeeded/failed/unknown/not_sent；无法确认是否受理的请求不能自动释放并重发，费用未知明确保留 unknown。
- 所有预占/续租/落账使用短写事务，不持 SQLite 写锁等待网络；预算只收紧已有授权，星币不折算供应商费用。

## 5. 最多五项验收

1. 两个真实进程竞争同一到期任务，只有一个有效 claim；running 到期可恢复，达到 max_attempts 进入明确终态。
2. 旧 claim 在接管、supersede、源版本变化后提交业务写与 complete/fail/renew 全部被拒绝；业务与任务回执都不变。
3. 任务执行后、回执前崩溃可恢复，领域唯一键防重复结算；用真实进程中断证明，不能只有顺序 mock。
4. 两进程并发预算预占不能超过全局/用途/主体/并发上限；同 operation 重放、重启、跨账务日规则固定可验证。
5. unknown 供应商结果不盲重试或冒充已退款；模型关闭/超时仍能完成确定性到站/结算，实际接线由 I 验收。

## 6. 本轮源码指纹

四文件执行前后 SHA-256 相同；后续若变化，先重新复现再用本结论。

| 文件 | SHA-256 |
| --- | --- |
| web_platform/tasks.py | `2fbca18dbda8dec7d877d970c0f30fbe5fa64b50be1d9943e13277b5250326b8` |
| web_platform/lease.py | `7a0b2145c5f7fa28ab84e19bb632c06419c1334e8d666f92c00073c3c9fab4c3` |
| web_platform/idempotency.py | `819db7408ed652ef84f4b0ce6015292f2fb8dccda1151a616368631321fedba6` |
| web_providers/meter.py | `049b4065fbfc93cc6d38baddbe03bb613a9568f450e6653bcb8a2f106673fe27` |
