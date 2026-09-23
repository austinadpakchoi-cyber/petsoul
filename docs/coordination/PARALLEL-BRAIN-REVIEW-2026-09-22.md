# Runtime / Brain 并行边界核查

日期：2026-09-22；窗口：codex-20260922-parallel-brain。
基线：共享工作树 `codex/petsoul-web-integration` / `980feabc7710462a89c5df488c255d04e9e7de08`，含大量未提交 Web 实现。
证据层：VERIFIED_CODE；本轮只读源码，没有运行后端、模型、数据库或新测试。
依据：AGENTS、全部窗口最新记录、世界运行层实施方案 v0.2；不沿用早期单主人/单宠/复制领养假设。
当前 Claude 的 app/**、tests/** 未释放；下列路径是建议，不能据本文直接领取。

## 1. 当前代码真正做了什么

| 定位（后端 app/ 下） | 当前机制 | 可下结论 |
| --- | --- | --- |
| `web_agent/profile.py:175` | `derive_profile` 经 dna_reading 解析证据，得到作息、频率、路线/工作权重 | DNA 驱动的确定性画像；不是模型推理 |
| `web_agent/life.py:68,195` | 每当地半小时槽，用 `_roll` 稳定 hash、画像、余额、建议和历史选择目的地；之后调用 `journeys.depart` | 已有会改变实际旅程的规则自主生活；不能称为已接通模型行动规划 |
| `web_agent/moment.py:68` | 读取 presence、active journey、visit、legs，派生睡眠及在途状态 | 已有共用状态投影，应复用，不重造位置事实表 |
| `web_agent_wiring.py:81,102` | 共用 DNA＋各家人授权用于家中互动/旅行偏好的接待记录；画像缓存 60 秒 | 已有用途过滤入口；保存 DNA/修改接待会清缓存，但新异步任务仍需版本戳 |
| `web_agent_wiring.py:141` | 私聊 persona 带该家人的个人层 DNA；家庭/居民 persona 只取共用资料 | 不可把私人 persona 直接复用于全家生活决策 |
| `web_communicator/service.py:109` | 开关与供应商可用时 `chat.complete` 生成回复，不可用回模板并标来源 | 模型已经接入措辞；本次没有验证真实供应商成功 |
| `web_agent/proactive.py:154`、`web_agent_wiring.py:222` | 模型写主动消息/明信片 | 表达调用不证明模型选择了下一份工作或旅程 |
| `web_agent_wiring.py:342` | ticker 串行跑旅程、交通刷新、life、待回复和主动消息 | 将函数换名 heartbeat 不会解除慢模型阻塞 |

额外边界：`life.consider` 先记录 go 再 depart，二者不是同一原子提交；本轮只作静态观察。
`moment._zone` 未知时区回退香港；公共 `city_timezones.py` 未知城市回退上海，必须由集成者统一，不能两包各修一套。
`_deliver_group` 使用 claim 字符串后在事务外调模型，再写消息；领取恢复归可靠性包，不交给 Brain adapter 顺手修改。

## 2. 先串行冻结八项契约，再并行写新文件

契约建议由集成者一次写入 `app/schemas/web/runtime.py`、`decision.py`；尚不存在就新增，存在等价模型则扩展。
只有集成者修改共享 schema、导出和生成器；两个实施包只读它们，不各自定义同名 DTO。
这些是内部边界；不必把全部内部字段生成给网页，尤其不公开 DNA、版本权限细节和观察原文。

| 核心项 | 最小字段或签名 | 唯一职责 |
| --- | --- | --- |
| 1 `Clock` | `now_utc()`、`monotonic()`；测试可注入 | UTC 持久时刻与进程内超时分开，正式时钟不加速 |
| 2 `SemanticStamp` | runtime owner/epoch、activity epoch、DNA/privacy/membership/itinerary version | 请求携带；集成者在最终事务重新核对 |
| 3 `RuntimeState` | pet_id、可空 household_id、scene/activity 引用、starts/ends、next_check、认知状态、silence_reason | 每只宠物一份，不按家人成倍建立，不复制钱包 |
| 4 `WakeSignals` | event IDs、已到期事实、回复承诺、依赖重试、预算恢复、clock health | 只传事实与截止时间，不传私人聊天全文 |
| 5 `HeartbeatOutcome` | CONTINUE/APPLY_RULE/REQUEST_BRAIN/DEFER/RECOVER、reason、next_check、wake_on、rule_refs | `evaluate(state, signals, now) -> outcome`，纯函数无外部调用 |
| 6 `ActionOffer` | offer_id、action kind、既有 destination/job ref、有效期、成本/时间、前置版本、允许参数范围 | 领域提供可行动作；模型不能发明钱、班次、坐标 |
| 7 `DecisionContext` | operation/pet/purpose/audience、as_of/deadline、stamp、获准 DNA/观察/记忆引用、offers | `build_context(authorised_input) -> context`，先授权再检索/拼接 |
| 8 `BrainProposal` | operation、选中 offer 或 continue、有限参数、意图摘要、review_after、来源与失败码 | `propose(context, chat_port) -> proposal`；只返回提案，不执行 |

模型不复述完整分析链；只留可审计的短意图与事实引用。元数据缺失不能默认为“有权限”。
复核分两层：Brain 校验结构/offer 枚举；最终提交者重新核对最新权限、活动、交通、余额和预算。

## 3. 包 A：无模型 Runtime policy / clock / state

建议新增范围：`app/web_runtime/{clock.py,state.py,policy.py,__init__.py}`。
建议独立测试文件：`tests/test_web_runtime_policy.py`；必须先由当前持有人释放这一精确新增路径。
依赖仅标准库、共享 schema 和公共时间工具；不 import Brain、provider、communicator 或组合根。
已有 `PetMoment` 由集成适配器转成 RuntimeState；本包不修改 moment/profile/life，不扫描家庭或居民表。
只产出状态转换和下次检查决策，不创建线程、队列、迁移、第二套 worker 或直接写经济账本。
未知时区要形成明确不可用结果；公共时区工具扩展由集成者完成，本包不复制城市映射表。

完成条件：
1. 注入时钟覆盖睡眠、在途、工作、活动结束、待回复与依赖故障；结果确定且无网络/数据库调用。
2. 到期确定性事项优先 APPLY_RULE；即使模型关闭、额度耗尽也不被 DEFER 掩盖。
3. 非终态均有 next_check 或明确外部唤醒；已消费的过去时间不反复造成立即空转。
4. 两宠共用家庭仍独立运行；无家庭居民也可评估；一次宠物活动不随家庭人数复制。
5. 支持真实 UTC、当地作息、回拨异常；媒体暂停与浏览器时钟不能修改交通锚点。

## 4. 包 B：DNA / 感知 / 有限提案 adapter

建议新增范围：`app/web_agent/decision/{context.py,adapter.py,validation.py,__init__.py}`。
建议独立测试文件：`tests/test_web_brain_decision.py`；同样需先释放精确路径，不接管整个 tests/**。
只读复用 `web_agent/profile.py`、`dna_reading.py` 与已有 DNA 模型，不趁机重写当前画像规则。
感知输入由注入的授权读取端口提供；复用 `reception.projection` 的用途语义，但不能在 adapter 内自行枚举全部私聊。
接收已核验/缓存 ActionOffer，不直接调用 `journeys.destinations/depart`，避免隐藏的地图访问和状态变化。
用注入 chat_port 接现有 `web_providers/llm.py`；包内无密钥、新供应商、预算扩容、后台循环或数据库写入。
只有调度层已取得预算预占才允许执行模型；无凭证/开关关闭返回 disabled，不偷偷调用。
首版一次模型尝试即可；有限格式修复需明确上限与剩余截止时间，不与 worker 重试叠成无限重试。

完成条件：
1. 给定相同事实/不同获准 DNA 能形成不同可检视上下文；私人 chat-only 记录不能混入共享生活规划。
2. 仅选给定 offer 或 continue；伪造价格、未知动作、越界参数、坏 JSON、过期上下文都返回拒绝码。
3. 假模型可分别选择留家/工作/出行并产出类型正确提案；adapter 调用不会改变钱包、旅程或消息。
4. 超时/额度不足/模型关闭产生有来源的失败或 rule_fallback，不能标为 model；真正执行仍在提交者。
5. 自主规划按 pet_id 去重，私聊按 user_id＋pet_id 隔离；包含来源引用与版本，供撤权/到站后的最终拒绝。

## 5. 必须留给集成者串行修改的实际入口

- `web_agent_wiring.py`：唯一装配 profile/context/moment/heartbeat/brain，注入同一次 now，避免 persona 内 utcnow 与任务快照漂移。
- `web_composition.py`、`web_worker.py`、`web_agent/ticker.py`：worker 注册、运行模式、慢任务移出关键线程、单次入口切换。
- `web_agent/life.py`、`moment.py`：保留规则后备，逐步改成 offer/投影适配；禁止新旧两套同时决定同一宠物出门。
- `web_platform/tasks.py`、`lease.py`、`idempotency.py`、`web_providers/meter.py`：领取围栏、恢复、预算预占归可靠性包，与 A/B 分离。
- `web_journey/service.py`、`web_economy/adapter.py`：提案到领域命令的最终校验和原子结算；Brain 不能绕过这里。
- `web_communicator/service.py`、`web_agent/proactive.py`、`web_journey/guides.py`：表达排队及提交时权限复核，不由 A/B 同改。
- `city_timezones.py`、`schemas/web/**`、迁移注册、`scripts/gen_web_contract.py`、前端 generated.ts：共享改动集中处理。

## 6. 集成顺序与证据门

先确认持有人释放精确新增文件 → 集成者冻结八项契约 → A/B 各自纯逻辑实现和离线样例 → 串行接持久化与提交。
先 shadow：只记录建议，不调供应商、不出门、不发消息、不记钱；比较规则旧实现与新 policy 差异。
随后选一只隔离测试宠物切换 runtime owner/epoch，失效旧任务，再连接真实领域命令；不触碰18763自然时间验收。
关键验收：假模型选工作后实际生成既有工作记录，到期工资一次；模型挂起期间另一宠物照常到站。
再验证 DNA更正/家庭撤权/到站/余额变化使旧提案被最终事务拒绝，证明不是仅验证 JSON。
“包 A/B 完成”仅表示模块与离线机制完成；真实模型选择、领域执行、重启恢复、香港部署分别留证。
分工由用户选择窗口；本报告没有给任何模型自动分配实施职责，没有释放 Claude 既有范围。
