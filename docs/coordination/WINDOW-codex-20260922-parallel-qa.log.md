# Window codex-20260922-parallel-qa

## START — independent acceptance work package
时间：2026-09-22 23:35 +08:00
任务：只读核对既有验收与测试，提出独立 QA 可立即推进的合同回归工作包。
基线：主窗口已核对 codex/petsoul-web-integration / 980feabc7710462a89c5df488c255d04e9e7de08；保留共享未提交变更。
已读：AGENTS.md、所有窗口日志最新领取。Claude 后端 app/**、tests/** 与真实验收未释放；不更改或启停。
领取：仅本日志与 docs/coordination/PARALLEL-QA-REVIEW-2026-09-22.md。
限制：只读业务代码；不读业务数据库、不联网、不调用供应商、不操作 Git、不修改测试发现目录。
运行资源：无。
是否释放：否。

## HANDOFF / RELEASE — independent acceptance work package
时间：2026-09-22 23:36 +08:00。更正：START 的“23:35”采用了预估时间，实际工具记录约23:34。
产物：docs/coordination/PARALLEL-QA-REVIEW-2026-09-22.md。
已核对：AGENTS、所有窗口最新领取、总方案第2/17/18节、test_web_platform_infra.py、test_web_households.py、web_base.py、仓库根 scripts/real_acceptance.py。
结论：已有关键机制用例；真实验收脚本仍有只采集未强制判定、template/model 混合与文案计数等证据缺口。给出离线证据判定器、8项隔离故障合同、新目录候选和串行整合边界。
验证：文档UTF-8与8项用例结构已检查；仅静态阅读，未运行测试/供应商/服务/数据库/Git操作。
下一步：由用户/整合窗口正式分配QA新目录；当前后端/tests领取维持Claude，18763自然时间验收不受影响。
是否释放：是，释放本次报告；日志仍仅本窗口追加。
