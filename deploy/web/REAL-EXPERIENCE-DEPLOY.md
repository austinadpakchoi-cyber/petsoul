# 0.4.0 真实体验：香港部署补充（未部署）

本文是契约 0.4.0（家庭与多宠物、访客与待领养居民、真实交通、独立任务进程）在香港单实例上的部署补充。
**本窗口没有登录服务器、没有部署。** 生产变更按既有的发布授权与协调流程执行；现有团队体验站仍是 `HK-FIRST-DEPLOYMENT.md` 记录的版本。

## 1. 进程与配置

| 进程 | 命令 | 说明 |
|---|---|---|
| API | `uvicorn app.main:app`（现有镜像） | 启动时应用迁移；`PETJOURNEY_WEB_WORLD_RUNNER=worker` 时不在进程里推进世界 |
| 世界任务进程 | `python -m app.web_worker`（同一镜像、同一份环境与数据卷） | 0.4.1 起进程里有两条线、两份租约：**世界线**（到期结算与账本、家庭来信等确定性下游、出门前复核、规则生活、驾校）与**认知线**（攻略与相遇的表达、到点回复、主动消息）。模型卡住只影响认知线；生图任务仍在同一进程（供应商可用时） |

编排：`hk-v1/compose.yml` + `hk-v1/compose.real-experience.override.yml`（新增 `worker` 服务，API 与任务进程都打开 WAL）。

新增/变化的环境变量（其余见 `backend.web.env.example`）：

| 变量 | 生产取值 | 说明 |
|---|---|---|
| `PETJOURNEY_WEB_WORLD_RUNNER` | `worker` | `embedded`（默认，本地开发）/ `worker` / `off` |
| `PETJOURNEY_WEB_HEARTBEAT_MODE` | `shadow` | 心跳策略只评估并记录每宠运行状态（不执行、不调模型）；`off` 关闭 |
| `PETJOURNEY_WEB_BRAIN_MODE` | `off` | 模型自主决策：`off` 一次都不调用（默认）/ `shadow` 只记录 / `live` 复核后执行。改成非 off 会产生真实模型调用，先确认预算与授权 |
| `PETJOURNEY_WEB_BRAIN_DAILY_PER_PET` | `12` | 每只宠物每个 UTC 记账日最多几次自主决策；只收紧已有供应商上限 |
| `PETJOURNEY_SQLITE_WAL` | `1` | API 与任务进程并发读写 |
| `PETJOURNEY_WEB_ENVIRONMENT` | `production` | 只用于状态报告；`/ops/status` 在 staging/production 必须带 `X-Admin-Token`（值为 `PETJOURNEY_ADMIN_TOKEN`） |
| `PETJOURNEY_WEB_DEMO_CATALOG` | 不设置 | 设了才会出现演示线路与“示例”地点，只给明确的演示站 |
| `PETJOURNEY_WEB_PROVIDERS` 与各供应商密钥 | 按既有授权 | 没有地图时：港澳一日行与进城/自驾不成立（明确原因），散步/喝一杯/打工去星球内的地方 |

## 2. 迁移（只增不删）

0.4.0 新增迁移：`0030_worker_status`、`0180_user_entry`、`0230_dna_versions`、`0240_residents`、`0250_dna_personal`、`0420_households`、
`0430_relationship_titles`、`0470_farm_households`、`0510_home_pantry`、`0610_leg_reference`、`0710_reference_trips`、`1130_family_messages`。

- 全部只新增表、列与索引；旧表语义不变（`web_homes.user_id / pet_id` 保留为“建立者 / 第一只宠物”，归属一律看家庭关系表）。
- 旧数据：每个旧家迁成“一个家庭 + 一位管理员 + 原来的宠物”（保留 pet_id、home_id、资产、证件与历史，不复制余额、不补发奖励）；
  旧的宠物仓库并入家庭仓库；旧 DNA 里的称呼与小暗号归给当初保存它的那位主人；还可领养的原创伙伴成为有稳定 pet_id 的待领养居民。
0.4.1 再新增迁移：`0040_outbox`（世界事件投递回执）、`0050_budget`（付费调用的操作级额度预占）、`0060_entity_runtime`（每宠运行记录）、
`1140_pending_reply_claims`（待回复领取期限与结果）。同样只新增表与列，不回填，不改旧表语义。

- 迁移在 API 启动时自动执行，每个迁移与登记在同一事务；重复执行无副作用。**发布前先备份**（`scripts/backup.sh` 或 `petsoul-backup.service`）。
- 0.4.1 升级注意：换新代码重启前先只读查一次遗留任务——
  `SELECT kind, COUNT(*) FROM web_tasks WHERE status='running' AND (locked_until IS NULL OR locked_until <= '<现在 UTC ISO>') GROUP BY kind;`
  新的队列会回收这些过期任务并重排，其中 `illustration` 可能再调用一次付费生图；不希望重画就用 `expired_policy={"illustration": "fail"}`。

## 2.1 打开“模型自主决策”之前要知道的（默认关闭）

`PETJOURNEY_WEB_BRAIN_MODE` 默认 `off`：世界按现有规则生活，**一次自主的模型调用都不会发生**。要打开：

1. 先确认预算与授权：每次决策 1 次模型调用，上限是“每只宠物每个 UTC 记账日 `PETJOURNEY_WEB_BRAIN_DAILY_PER_PET` 次”（默认 12），
   并且不超过供应商本身的每日上限。按当前在养的宠物数估一下每天最多多少次，确认在已授权的额度内。
2. `shadow`：调用模型但只记录“它会选什么”，不出门、不发消息——适合先看看模型的选择是否合理（仍然产生真实调用与费用）。
3. `live`：提案经复核后真的执行。复核在执行前再看一遍：语义版本没变、机会没过期、TA 还在家、规则本身再判一次（钱不够、睡着、
   现实资料不可用都算明确拒绝）。家庭必须先开“模型回信”，否则一次都不会调用。
4. 打开后观察：`/ops/runtime/{pet_id}` 的 `last_decision_by`（model / rule_fallback）与 `heartbeat_action`；
   任务进程日志里的 `brain round pet=… status=… by=… choice=…`；`/ops/status` 的供应商 `calls_today`。
5. 要关掉就把配置改回 `off` 再重启任务进程：已经出发的行程照常走完，不会回滚。

**先在一次性环境里验一次再动正式环境**：

```
python scripts/verify_brain_live.py --yes --mode shadow
```

它在一个全新临时库里建新家庭、新宠物，只配对话模型（地图、生图都不配，不会产生它们的调用），走完整决策链后打印并写下
`composed_by`（`model` 才算真的是模型在选）、这次的选择与理由、调用次数、运行记录，临时库用完即删。
会产生真实付费调用，所以必须显式 `--yes`；`--mode live` 才会让这次选择真的成行。

这一步在 2026-09-23 03:10 / 03:13 +0800 跑过两次（shadow 与 live 各一次，各 1 次 DeepSeek 调用）：
两次 `composed_by` 都是 `model`；live 那次 `status=departed`，模型选的 `local:stroll` 真的变成了行程 `jn-28f8642b2231`，
运行记录写下 `last_decision_by=model`。也就是说真实供应商支持决策用的 JSON 模式、额度按 `operation_id` 预占、
复核后提交这一整条都成立。证据 `PetJourneyBackend/data/web-real-acceptance/evidence/{24-brain-real-model,27-brain-real-model-live}.json`。

## 3. 发布顺序

1. 备份并校验（integrity_check）；记录当前 `release.env`。
2. 新发布号打包、Linux 上复跑测试与门禁（后端全量、`arch_gate`、`dependency_gate`、`contract_diff`、`gen_web_contract --check`、前端 typecheck/test/build）。
3. 先只起 API（迁移），看 `/api/v1/web/meta` 的 `contract_version=0.4.1`、`applied_migrations` 含上面 16 个编号。
4. 再起 `worker`；`/api/v1/web/ops/status`（带管理令牌）确认：`world.lease_alive=true`、`cognition.lease_alive=true`、两者 `holder_role=worker`、`last_ok_at` 都在走；
   `outbox` 里每个下游 `pending` 不持续增长、`dead_letter=0`；`tasks.running_expired=0`；`world.due_lag_seconds` 不持续变大（世界线没卡住）；
   供应商状态为 `verified` 或如实的 `not_configured`。
   排查“某只宠物为什么这么安静”：`GET /api/v1/web/ops/runtime/{pet_id}`（同样只给本机或管理令牌）——在做什么、下次什么时候看、
   有哪些到期事项、安静原因、上次是谁做的决定。返回里没有正文、没有 DNA 原文、没有提示词。
5. 冒烟：`scripts/smoke.sh`；再用两个新账号走一遍 `docs/coordination/BACKEND-REAL-EXPERIENCE-ACCEPTANCE.md` 的 A/B（不要用预置演示账号）。

## 4. 回滚

- **网页**：`scripts/rollback.sh` 切回上一版静态文件。
- **后端**：`release.env` 切回上一镜像标签后 `up -d`；0.3.0 代码可以在 0.4.0 迁移过的库上运行（只增不删），但它不认识家庭表——
  回滚期间新加入的家庭成员、第二只及以后的宠物在旧代码里看不到，旧账号的第一只宠物照常。**回滚前先停 `worker`**，再切 API：
  `docker compose ... stop worker && docker compose ... up -d backend`。
- **数据**：不做反向迁移；确需回到旧数据时按 `scripts/restore.sh` 从发布前的备份恢复（会丢失发布后的新数据，需要用户决定）。
- 任务进程单独回滚/停止不影响数据一致：世界暂停推进，读取接口仍会补齐到期事件；重新启动后按幂等规则接着推进。

## 5. 运行与排查

- `GET /api/v1/web/ops/status`（管理令牌）：环境、数据库文件、WAL、迁移数、供应商“已配置/已验证/失败”、世界任务租约与最近一轮、能力、前端连接方式。
- 任务进程日志：`docker compose ... logs --tail=100 worker`；看到“收到停止信号，释放租约后退出”说明正常停止。
- 船期资料：`app/web_transport/timetables/turbojet_hk_macau_outer.json` 的 `recheck_by`（当前 2026-10-22）之前要重新核对官网；
  过期后港澳一日行自动显示“船期待复核”而不再当作已核验班次使用。更新方法见 `docs/coordination/BACKEND-REAL-EXPERIENCE-ACCEPTANCE.md` §5。
