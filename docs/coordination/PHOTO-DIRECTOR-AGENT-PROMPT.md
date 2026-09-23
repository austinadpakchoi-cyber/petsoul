# PetSoul 照片导演专责 Agent 工单

用户已明确指定照片导演唯一负责人为 **claude-20260923-055300-ada5**。依据 docs/product/PHOTO-DIRECTOR-WEB-PLAN.md。本工单供该既有窗口继续执行，不再新建 Codex 窗口，不释放 A/B/C/I/Q 或前端的范围。

2026-09-23 用户更正：此前未成功创建独立 Codex 工作窗口，不能算作已成功派发。原本对话内 helper 的 P0/P1 实施已取消；05:59 监管已实际读取 pd8f 日志中的 CORRECTION + RELEASE（记录时间05:58:37+08:00），全部 P 范围已释放，协作工具确认 helper 收尾结束。ada5 复读该释放记录后用现有窗口 ID 追加 CLAIM 即可，无需等 I 再释放这个新模块，也不要继续记成“未分配任务”。用户指定负责人不等于窗口已实际领取或开工，实际状态以 ada5 自己的日志为准。

以下可直接交给新窗口：

~~~text
你是 claude-20260923-055300-ada5，用户指定你独家负责 PetSoul 照片导演专项，包 P。沿用这个窗口 ID。仓库 E:/petsoul-audit/petsoul，直接使用共享工作树。不创建工作副本/worktree，不做 pull/checkout/commit/reset/stash/clean 或批量暂存。

用户目标：咖啡馆、火车、家中、冒险照片应像自己的那只宠物。参考照锁外貌；经授权的 DNA 和真实活动决定动作与镜头。写实动物外形，允许平行世界生活，不变成人或卡通，不让模型改写世界事实。

先完整读 AGENTS.md、WINDOW-START-PROMPT.md、全部 WINDOW 最新记录、PHOTO-DIRECTOR-WEB-PLAN.md 和 FRONTEND-HANDOFF 最新修订。登记自己的固定窗口 ID、START、实际时间、Git 基线、已有改动、范围、资源和冲突；不覆盖已有改动，不沿用别人占位时间。

先追 iOS 正式 generateSelfie/photo_mission 到旧 PhotoMissionBrain/PhotoPromptBuilder/PhotoPipeline/EventGenerator，写调用证据。旧 quality_report 是提示词检查，不是看图。旧大脑疑似缺失导入要禁网确认，不能因为有类名就认为可运行，更不能用旧 engine 导入触发模型/地图。

随后实施 P1，不停在报告。先读 WINDOW-codex-20260923-054900-pd8f.log.md 的 RELEASE，再查黑板并 CLAIM 下列范围：
PetJourneyBackend/app/web_photo_director/**
PetJourneyBackend/tests/test_web_photo_director_*.py
PetJourneyBackend/tests/fixtures/photo_director/**（虚构输入）
PetJourneyBackend/scripts/evaluate_photo_director.py
docs/coordination/PHOTO-DIRECTOR-IMPLEMENTATION-HANDOFF.md
自己的 WINDOW 日志及先登记的证据目录。

接手目录已留下 catalog.py、contracts.py、privacy.py、validation.py 四个未完成草稿。它们没有测试通过或接入证明，不是必须沿用的设计；先比对释放指纹并审阅，领取后可在自己的范围内修改或替换，保留可追溯的说明。不要把历史 pd8f 的证据目录当成你自己的证据目录。

实现内部类型、上下文白名单、四场景/镜头策略、可注入的结构化模型端口、草稿校验、稳定身份和事实约束编译、规则后备、参考角色/版本记录、离线评测。真实实现但首批只用禁网替身运行；不直接写业务库、不另建调度器、不扩公共 schema、不改 legacy 文件。

A 持有 illustrations/images/消费者，B 持有 web_agent_wiring 和运行调度，I 持有组合根/配置/契约，C 持有旅程提交。给实际持有人一次列清最小 CHANGE_REQUEST：字段、签名、默认行为、授权/预算、测试。没有 RELEASE 不改；冲突只阻塞重叠部分。

每事件最多一次导演文本请求，预算独立，不藏进图片额度。许可/预算未接好就规则或离线；不绕过 unknown、不自动重发生图、不在读页面时调用。原照读取失败不换成随机动物；原创伙伴的基准保存竞争需要读回真正保存者。测试不读真实用户照片，不用UI样板宠物作当前角色。

测试覆盖多宠隔离、DNA改动作不换身份/地点、隐私白名单、事实不能被模型改写、坏参考/无权限/坏输出、四场景与镜头。人工 fixtures、临时资源、TZ=UTC、新进程、禁网替身、运行前后指纹与完整输出。遵守行数/定义数门禁，不只断言含几个关键词。

准备真实成图 dry-run 与本地联系表工具：同一许可参考、同模型，旧4张+新4张；若仅4张不作优劣对比。留任务、参考摘要、提示版本、事实输入、模型配置、实际发送与用量、失败样本。真实调用/用户媒体/金额上限未明确前不发请求，这不阻止本地开发。需要付费时先提交具体批次与上限供用户一次授权，不零散试探。

交 HANDOFF：新增文件、接口、测试、指纹、A/B/I 最小接入请求、未证明项、成图执行单模板。未接入写未接入，没看实际成图写视觉质量未验证；你不是 Q，不自行宣布全项目验收。

不碰18763/E2/生产、他人测试库/服务、密钥、前端共享文件；新增路径先 SCOPE_CHANGE。按小批继续，不反复停等 I。
~~~

派发更正：桌面独立任务创建没有成功。内部 helper 的先前工作不算用户认可的独立 Codex 任务，也不再继续负责包 P。当前只由 claude-20260923-055300-ada5 接手实施；其是否开工、交付和测试通过均按本人日志及实际证据记录，不由监管窗口代签。
