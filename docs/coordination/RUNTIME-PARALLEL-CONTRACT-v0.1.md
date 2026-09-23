# Runtime 并行开发最小接口 v0.1

时间：2026-09-22。状态：**候选接口，供集成窗口一次性核对并登记接受；尚未发布为实际 API。**

目的：任务基础设施、心跳策略、DNA 决策和验收可以独立开发，不各自猜测数据结构。执行包见 [并行工作包](BACKEND-PARALLEL-WORK-PACKAGES-2026-09-22.md)，完整语义见 [世界运行方案](../product/PETSOUL-WORLD-RUNTIME-IMPLEMENTATION-PLAN-v0.2.md)。

## 1. 唯一写入者与依赖方向

- 内部 DTO 建议由总集成窗口一次性落在 `PetJourneyBackend/app/schemas/runtime_internal.py`；仅标准库/基础类型，不 import 引擎，也不进入网页公开字段导出。
- 各执行包只消费该契约，不编辑同一份文件。新增需求在自身日志写 CHANGE_REQUEST；兼容调整由集成窗口实施并登记版本。
- 对外 DTO 继续在 `app/schemas/web/`，由集成窗口生成 TypeScript。不能让两个窗口同时运行会写文件的契约生成命令。
- 各包新增自己的模块和单元测试；数据库迁移、组合根、真实写入适配器均由集成窗口统一接入。
- 下文 `Connection` 是由同一个 UoW 提供的连接；接口不能私自新开连接、提交或回滚调用者事务。

## 2. 八组内部类型

### 2.1 Clock

```python
class Clock(Protocol):
    def now_utc(self) -> datetime: ...  # aware UTC
    def monotonic(self) -> float: ...  # 只用于进程内持续时间
```

生产使用真实时钟，测试注入 FakeClock。心跳策略显式接收 now，不从函数深处取宿主机本地时间。地区钟点委托项目统一时间入口。

### 2.2 Versions / RuntimeState

```text
Versions
  runtime_epoch, activity_epoch, dna_version, privacy_epoch,
  membership_epoch, itinerary_version?           # 均来自可信存储

RuntimeState
  pet_id, realm_id, versions, as_of
  region_id, scene_ref, primary_activity_ref
  activity_ends_at?, next_check_at?, silence_reason?
  pending_commitment_deadline?, cognition_status
```

wallet、inventory 等领域状态只读引用或当次快照，不在 runtime 中维护另一份可写余额。共享资源有 household_id；私人上下文另有 conversation/user scope。

### 2.3 WakeEvent / HeartbeatDecision

```text
WakeEvent
  event_id, pet_id, kind, effective_at, source_ref, sequence

HeartbeatDecision
  action = CONTINUE | APPLY_RULE | REQUEST_BRAIN | DEFER | RECOVER
  reason_codes[], next_check_at?, wait_event_kinds[]
  task_intents[], brain_purpose?, consumed_event_ids[]
```

心跳是纯函数：`evaluate(state, authorized_events, policy, now) -> HeartbeatDecision`。

不写库、不调模型、不消费预算、不调用地图。待处理事项不能无下次时间且无唤醒事件；过去的时间不能反复生成零延迟空转。`consumed_event_ids` 只是建议，集成事务成功后才确认消费。

### 2.4 TaskClaim

```text
TaskClaim
  task_id, kind, aggregate_id, payload_ref
  worker_id, claim_generation, lease_until
  attempts, max_attempts, deadline_at?, source_versions
```

`claim(worker_id, kinds, now, lease_duration) -> TaskClaim | None`。
`renew(claim, now, extension) -> updated_claim | LostClaim`。
`recover_expired(now, limit) -> recovery_counts`。

最终提交使用 `assert_current_claim(conn, claim, now)`，检查 status、持有者、代数和期限；`complete_in_tx(conn, claim, result_ref)` 与业务写入同事务。队列包只检查任务权威，领域权限/活动版本另由集成者校验，二者缺一不可。

失败/失效更新同样带领取令牌，不能只靠 task_id 覆盖。队列包提供旧调用面兼容计划，但不以 optional token 默默绕过新任务的提交检查。

### 2.5 BudgetReservation

```text
BudgetReservation
  reservation_id, operation_id, provider, purpose, subject_scope
  accounting_window, reserved_units, expires_at, status
```

`reserve(operation_id, scopes, limits, estimated_units, conn) -> reservation | BudgetDenied`。
`settle(reservation, actual_usage?, provider_request_id?, outcome, conn)`。

原子检查所有预算层级，operation_id 重放不重复预占；多个进程一致。外部是否受理不明时 outcome=unknown，不能当“完全没花钱”立即释放然后重复调用。真实货币费用未知时单列未知，不把星币算作 API 成本。

### 2.6 DecisionContext / ActionOffer

```text
DecisionContext
  operation_id, purpose, pet_id, audience_scope
  as_of, deadline_at, versions
  conversation_id?, input_high_watermark?
  permitted_dna, memory_refs[], observations[], commitments[]
  current_activity, action_offers[]

ActionOffer
  offer_id, action_kind, bounded_parameters, source_ref
  expected_versions, valid_until, cost_bounds, duration_bounds
```

角色包通过注入的授权 ContextReader 获取最小信息；SQL授权过滤由存储/集成适配器保证，不能先拿到所有家人私信再让模型过滤。可行 offer 由规则适配器构建，模型不能自行捏造已核验车次、商家或工资。

### 2.7 BrainProposal

```text
BrainProposal
  operation_id, source_versions
  selected_offer_id? / continue_current
  parameters, intent_summary
  suggested_review_after_seconds?
  expression_request?, memory_candidate_refs[]
```

`decide(context, model_adapter, call_limits) -> BrainProposal | DecisionFailure`。

角色包负责约束输出与有限调用，集成器负责预算预占及最终可行性校验。模型不可用返回失败/延期原因，不能偷偷换供应商、直接调用另一套旧生活循环或虚构成功结果。

### 2.8 CommitOutcome / DomainEvent

```text
CommitOutcome
  command_id, status = committed | rejected | pending | replayed
  reason_code?, state_version?, event_ids[], receipt

DomainEvent
  event_id, aggregate_id, aggregate_sequence, kind
  effective_at, recorded_at, source_versions, audience_scope, payload_ref
```

`commit_proposal(proposal, claim, current_actor_scope) -> CommitOutcome` 由集成窗口实现：同事务检查任务令牌、最新权限、相关语义版本、动作条件、领域幂等，更新状态、事件、下一任务、outbox、回执。请求受理或模型返回都不等于 committed。

## 3. 必须一致的行为样例

| 场景 | 约定结果 |
| --- | --- |
| 活动还没结束，无新事项 | CONTINUE；next_check 指向有效边界，不调模型 |
| 工资已到期 | APPLY_RULE；同一工作实例只有一次入账，无论几位家人刷新 |
| 活动结束，需要安排下一步 | REQUEST_BRAIN 或预算受限 DEFER；规则先提供可行机会 |
| 模型未返回，宠物已经到站 | 旧地点动作不能提交；新计划可另建 operation |
| 思考时撤回记忆/移除成员 | 最终提交再次校验；不发布依赖旧权限的内容 |
| running过期被接管 | claim_generation递增；旧worker不能写结果或更新任务状态 |
| 任务已superseded，旧complete到达 | 保持superseded，返回LostClaim/冲突 |
| 两次调用争抢最后一个额度 | 只有一次预占成功，未获预算的一次不访问外部 |
| 收到后来消息 | input_high_watermark区分覆盖范围，不吞掉新输入 |
| 暂停一起听 | 播放状态变化；世界时钟和车辆继续 |

## 4. 接入完成的证明

类型定义、隔离测试、集成接入、真实用户链路分别记状态。纯策略测试可以使用合成输入；正式用户必须读取真实授权数据。不得以“全部接口返回了一份样例”宣称 Runtime 完成。

集成窗口接受本接口后，在自身日志写明版本、文件映射和需要的最小修订；执行包据此编码。接受后不追求一次冻结所有未来字段，每批变更通过一条明确 CHANGE_REQUEST 同步。
