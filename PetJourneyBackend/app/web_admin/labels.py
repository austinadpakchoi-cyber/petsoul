"""后台界面上的「人话」：把领域里的代码翻成运营同学看得懂的说法（方案 §5「不把原始 JSON 当日常界面」）。

三条规矩：
- **只翻译，不改义。** 每个说法对应领域里一个确定的代码；没收录的代码原样返回 None，由界面如实显示原值并标「未收录」，不编。
- **能枚举的代码族由用例双向核对**（`tests/test_admin_labels.py`）：领域里多一个值、这里少一句说法就红；
  这里多写一个领域里没有的值也红。自由字符串（账本来源、错误串）没法枚举，只收录已知的，其余照原样显示。
- **纯静态词表**：不查库、不写审计、不含任何玩家数据。

代码本身不藏：界面顶部的「显示技术代码」打开后，每个说法旁边都会带上原始代码，方便对日志、对工程师。
"""

from __future__ import annotations

from typing import Any

# ---- 宠物此刻的状态 ----
ACTIVITY = {
    "at_home": "在家",
    "visit": "在外面拜访一个地方",
    "work": "在打工",
    "travel": "在路上",
    "exam": "在考试（不能打断）",
    # web_agent/runtime_view.py：家还没完成入住、又不是驿站居民的宠物，世界不为它推进
    "not_activated": "还没入住（世界不为 TA 推进）",
    "unknown": "不知道（运行投影没有给出）",
}

# 安静原因：（一句话，还能做什么）。与 web_runtime.reasons.SilenceReason 一一对应。
SILENCE = {
    "living": ("TA 正在生活", "有正在进行的活动或刚刚做过决定，不需要处理。"),
    "asleep": ("TA 在睡觉", "按所在城市的当地作息，现在是睡眠时段。醒来后会自己继续。"),
    "outside_active_hours": ("不在活跃时段", "当地时间还没到 TA 的活跃时段。"),
    "enough_today": ("今天已经够了", "今天的决定次数已达上限，明天会恢复。"),
    "no_new_decision": ("暂时没有新决定", "上一次决定之后还没到复查时间。"),
    "thinking": ("正在思考", "已经有一次 AI 思考在进行，等它结束。"),
    "not_activated": ("还没入住", "这只宠物所在的家还没完成入住，世界不会为它推进。"),
    "budget_deferred": ("额度用完，已推迟", "调用额度到上限被推迟；这是额度问题，不是故障。要恢复请调整额度，不要重发。"),
    "maintenance": ("已暂停", "后台暂停了 TA 的自主运行（不做新的生活决定）。在「宠物运行」或宠物页的运行记录里恢复。"),
    "dependency_unavailable": ("依赖不可用", "模型或其他依赖当前不可用。看「系统运行」页的供应商状态。"),
    "task_stuck": ("任务卡住", "有到期事项反复失败或租约过期。看下面的照片与任务，符合条件的可以做一次受控恢复。"),
    "clock_unhealthy": ("时钟异常", "服务器时间出现回拨或跳变，世界暂停推进以免写坏事实。请转给技术同学。"),
    "timezone_unknown": ("时区未知", "拿不到 TA 所在城市的时区，作息无法判断。请转给技术同学。"),
    "state_inconsistent": ("状态不一致", "记录之间对不上，需要对账。不要用改数据库的方式抹平，请转给技术同学。"),
}
SILENCE_KIND = {"normal": "正常", "deferred": "已推迟", "fault": "故障"}

# 心跳这一次的结论（web_runtime.heartbeat_policy.HeartbeatAction）
HEARTBEAT_ACTION = {
    "continue": "先不动，等下次复查",
    "apply_rule": "按日常规则安排生活",
    "request_brain": "请 AI 想一想接下来做什么",
    "defer": "推迟（等条件满足再说）",
    "recover": "先处理卡住的事项",
}

# 心跳给出这个结论的依据（web_runtime.reasons.ReasonCode）。「silence:xxx」形式的依据按 SILENCE 翻译。
REASON = {
    "maintenance": "被后台暂停",
    "clock_regressed": "服务器时间往回跳了",
    "clock_jumped": "服务器时间突然跳了一大段",
    "clock_event": "时钟有异常事件",
    "catching_up": "正在补上落下的事",
    "message_received": "收到了主人的消息",
    "versions_changed": "资料有更新（行程、成员或隐私设置变了）",
    "duplicate_events": "有重复的事件",
    "foreign_events": "有不属于 TA 的事件",
    "future_events": "有时间在未来的事件",
    "due_commitment": "有答应家人的事到期了",
    "due_world_event": "有世界里的事到期了",
    "commitment_overdue": "答应家人的事已经超时",
    "more_due_items": "还有更多到期的事排着",
    "due_item_stuck": "有到期的事卡住了",
    "stale_due_item": "有到期的事很久没处理",
    "task_expired": "有任务过了期限",
    "brain_expired": "上一次 AI 思考过期了",
    "brain_stale": "上一次 AI 思考的结果已经过时",
    "brain_in_flight": "AI 正在思考",
    "activity_overdue": "当前活动超时了",
    "activity_unknown": "不知道 TA 在做什么",
    "in_activity": "TA 正在做一件事",
    "suggestion_noted": "记下了主人的建议",
    "not_activated": "还没入住",
    "timezone_unknown": "时区未知",
    "default_rhythm": "按默认作息",
    "asleep": "在睡觉",
    "outside_active_hours": "不在活跃时段",
    "enough_today": "今天的决定次数够了",
    "review_not_due": "还没到复查时间",
    "decision_interval": "离上次决定太近",
    "idle_review": "闲着，例行看一看",
    "owner_suggestion": "主人给了建议",
    "activity_ended": "上一个活动结束了",
    "brain_disabled": "AI 思考没有开启",
    "brain_exhausted": "今天的 AI 思考额度用完了",
    "brain_unavailable": "AI 思考暂时不可用",
    "resident_rule_life": "待领养的居民按规则生活",
    "rule_fallback": "改按规则安排",
    "watchdog": "例行巡检",
}

# 上一次决定是谁做的（web_entity_runtime.last_decision_by；schemas/web/ops.py：model / rule_fallback / rule）
DECIDED_BY = {"model": "AI 想的", "rule": "按日常规则", "rule_fallback": "AI 不可用，改按规则"}

# 到期事项（web_runtime.state.DueKind）
DUE_KIND = {"journey": "旅程里的事", "reply": "要回复主人", "cooldown": "冷却结束", "other": "其他"}

# 旅程
JOURNEY_LIFECYCLE = {"active": "进行中", "completed": "已结束", "cancelled": "已取消"}
WORLD_EVENT = {
    "departed": "出发",
    "leg_arrived": "到达一站",
    "adventure": "路上的小插曲",
    "visit_started": "到店",
    "visit_ended": "离店",
    "work_done": "打工结束、结算工钱",
    "returned_home": "回到家",
    "photo_taken": "拍了一张照片",
    "refresh": "行程刷新",
}

# ---- 照片与任务 ----
ILLUSTRATION_STATUS = {"processing": "处理中", "ready": "已出图", "failed": "没画成"}
CALL_STATE = {"ready": "已出图", "processing": "处理中", "failed": "没画成", "unknown": "结果未确认"}
TASK_STATUS = {"queued": "排队中", "running": "执行中", "succeeded": "已完成", "failed": "失败", "superseded": "被新的任务取代"}
RESERVATION_STATUS = {
    "reserved": "已占额度，还没结果",
    "settled": "已结清",
    "released": "没发出，额度已退回",
    "unknown": "结果未确认",
    "expired": "占着的额度过期了（结果未确认）",
}
PROVIDER = {  # 额度预占里只有 image / llm；amap / amap_static / google 是地图服务，出现在服务健康表里
    "image": "生图服务",
    "llm": "大模型（对话与思考）",
    "amap": "高德地图",
    "amap_static": "高德静态底图（地图页的底图图片）",  # web_providers/basemap.py，配了高德密钥才出现
    "google": "谷歌地图",
    "research": "搜索研究（旅行心愿出发前查资料）",  # web_travel/research.py 的 PROVIDER；额度车道 provider:research:daily
}
PURPOSE = {  # 预占的用途（web_journey.illustrations / web_character / web_character.id_photo / web_agent.brain_life）
    "illustration": "照片 / 插画",
    "character": "角色形象",
    # 证件照的额度车道是 pet:<宠物>:id_photo：每宠上限和角色同一个数，但单独计数，不占角色那条
    "id_photo": "证件照",
    "life_plan": "生活规划（AI 思考）",
    # 旅行心愿出发前查资料的那一次平台调用（web_travel/research.py）；花的是平台 API 的钱，和宠物的游戏金币无关。
    # 每宠车道 pet:<宠物>:travel_research、全局车道 provider:research:daily
    "travel_research": "旅行心愿查资料（平台调用，不是游戏金币）",
}
# 任务队列（web_tasks.kind）里的任务类型：与源码里每一处入队的种类逐个核对（test_admin_labels）
TASK_KIND = {
    "illustration": "照片 / 插画",
    "pet_character": "生成角色形象",
    "pet_character_pose": "生成角色的其它姿态",
    "pet_id_photo": "生成证件照",
    # 旅行心愿（A 的 web_travel/service.py，TRV-03）：心愿形成时在同一事务里登记，为它查资料、核实去处与行程的事实
    "travel_research": "旅行心愿：查资料、核实事实",
}
# 角色形象与证件照没做成的原因（schemas/web/character.py::CharacterReason，用例双向核对）。
# 玩家那一侧有给主人看的说法（PetJourneyWeb 的 PetFigure.tsx）；这里写给运营看：发没发出、会不会自动重试、钱是不是可能已经花了。
CHARACTER_REASON = {
    # 排队前就挡住了（都没有发出）
    "no_reference_photo": "还没有这只宠物的照片，没法准备形象（没有发出）",
    "species_unsupported": "这个物种的形象暂时画不了（没有发出）",
    "provider_unavailable": "没配生图服务，没有发出",
    "not_configured": "生图服务没配置，没有发出（额度已退回）",
    "pet_has_no_household": "这只宠物不属于任何家庭，不做形象（没有发出）",
    # 执行中途停下
    "generated_reference_only": "只有系统自己画的基准照，要一张主人上传的真实照片才能做",
    "reference_changed": "排队期间主人换了照片：这一版作废、不发布，按新照片来",
    "budget_denied": "额度用完了，没有发出",
    "unknown_result": "上一次可能已经发出、结果没确认：不自动重发",
    "transparency_not_requested": "图片不透明，而这次本来就没请求透明背景（要改请求参数，不是提示词）",
    "attempts_exhausted": "重试次数用完了，不再自动重试",
    # 生图服务当场给的说法
    "daily_cap": "到了每日上限，没有发出（额度已退回）",
    "rejected": "生图服务当场拒绝，没有发出（额度已退回）",
    "timeout": "发出去了、没等到结果：结果未确认，可能已经计费，不会自动重发",
    "unconfirmed": "生成已受理、之后取图失败：结果未确认，可能已经计费，不会自动重发",
    # 「调整形象」时已经有一版在排队或生成：不是失败
    "already_queued": "已经有一版在排队或生成，这次不用再排",
    # 图像校验没过：画出来了但不能用（这一张的钱已按实结算，不会自动重画）
    "not_png": "图片不是 PNG 格式，没有用上",
    "undecodable": "图片解不开，没有用上",
    "interlaced_unsupported": "图片是隔行扫描格式，查不了，没有用上",
    "palette_unsupported": "图片是调色板格式，查不了，没有用上",
    "bit_depth_unsupported": "图片色深不支持，查不了，没有用上",
    "too_large_to_check": "图片太大，查不了，按没通过算",
    "no_alpha_channel": "图片没有透明通道，没有用上",
    "opaque_background": "请求了透明背景，拿回来还是不透明，没有用上",
    "checkerboard_drawn": "透明背景在传输中被压成了灰白格子，没有用上",
    "empty_subject": "画里没有宠物，没有用上",
    "multiple_subjects": "画里不止一只，没有用上",
    "subject_cut_off": "宠物贴边被裁，画得不完整，没有用上",
    "subject_too_large": "宠物在画里太大，没有用上",
    "subject_too_small": "宠物在画里太小，没有用上",
    # 证件照自己的校验（只出现在证件照上）
    "photo_not_to_bottom": "证件照没画成头和上半身（画成了全身或半身），没有用上",
    "photo_headroom_off": "证件照头顶留白不合适（要在画面高度的 3%–20%），没有用上",
    "photo_head_cut_off": "证件照头部太靠边，裁头像时会裁掉耳朵，没有用上",
    "photo_too_small": "证件照尺寸太小（短边不到 512 像素），没有用上",
    "photo_wrong_shape": "证件照比例不对（宽÷高要在 0.55–0.80 之间的竖幅），没有用上",
    "photo_blank": "证件照几乎没有明暗变化（像一整片单色），没有用上",
}
# 任务错误里的原因（web_journey.illustrations 的 NOT_SENT / UNKNOWN / NO_RETRY 三组，加上任务队列的租约过期）。
# 错误串常见形如 `image timeout`、`image director_hold:…`、`image delivery_would_drop:…`；认不出来的照原样显示。
TASK_ERROR = {
    "daily_cap": "到了每日上限，没有发出（额度已退回）",
    "not_configured": "生图服务没配置，没有发出（额度已退回）",
    "rejected": "生图服务当场拒绝，没有发出（额度已退回）",
    "provider_error": "连不上生图服务或被限流，没有发出；会换个时间自动再试",
    "timeout": "发出去了、没等到结果：结果未确认，可能已经计费，不会自动重发",
    "unconfirmed": "生成已受理、之后取图失败：结果未确认，可能已经计费，不会自动重发",
    "unknown_result": "上一次可能已经发出、结果没确认，或付过钱的结果找不回来：不重发",
    "lease_expired": "执行中途失联（租约过期），已按次数规则处理",
    "budget_denied": "额度用完了，没有发出",
    # 可以重试的供应商错误（连不上、被限流），任务队列按异常类名记下（web_platform/tasks.py：fail_claim(type(exc).__name__)）
    "ImageUnavailable": "连不上生图服务或被限流，没有发出（这类错误会按次数自动再试）",
}
# 照片导演没开拍的原因（director_hold:<原因>[:<缺的那一项>]）：缺的是事实或授权，**不会自动重试**，重试也不会让它变有
DIRECTOR_HOLD = {
    "identity_reference_missing": "缺少这只宠物的身份参考照",
    "reference_origin_unknown": "参考照来源不明",
    "runtime_versions_unreadable": "读不到 TA 当前的资料版本",
    "event_revision_unwired": "拍照事件的版本读口没接上（接线问题，转技术）",
    "event_origin_missing": "不知道这次拍照是怎么来的（接线问题，转技术）",
    "captured_at_not_localised": "拍摄时刻换算不成当地时间",
    "inputs_missing": "拍照需要的事实不齐",
    "hold_missing_required": "缺少必要的拍照条件",
    "hold_no_shot_is_possible": "按现有事实拍不出一张合规的照片",
    "hold_validation_failed": "拍照要求没通过校验",
    "payload_missing": "拍照请求里缺了登记方该给的一项事实（接线问题，转技术）",  # photo_director_bridge.py
    "scene_not_supported": "这个拍照场景照片导演还不支持",  # web_photo_director/readiness.py
}
# 照片出现在玩家那一侧的哪里（后台按任务号关联；没关联上就是「没找到」，不猜）
PHOTO_SURFACE = {
    "postcard": "明信片",
    "message": "通讯器消息里的照片",
    "guide": "攻略手账的配图",
    # 明信片以外的藏品（比如领证合影）：具体是哪种藏品另给 item_kind，按藏品种类的说法显示
    "keepsake": "藏品里的照片",
}

# ---- 游戏账本 ----
LEDGER_TYPE = {
    "item_acquired": "得到物品",
    "item_sold": "卖出物品",
    "owner_fund_granted": "主人给的零花钱",
    "fund_to_coin_converted": "零花钱换成星币",
    "item_locked": "物品锁定",
    "item_unlocked": "物品解锁",
    "item_archived": "物品归档",
    "web_farm_harvest": "菜地收成",
    "web_farm_steal": "偷菜",
    "web_travel_fee": "旅费",
    "web_reward": "奖励",
    "web_job_income": "打工收入",
}
LEDGER_SOURCE = {
    "admin.compensation": "后台补偿",
    "admin.compensation.batch": "后台批量补偿",
    "admin.compensation.reversal": "后台冲正",
    # 说法跟玩家看到的账单事由对齐（6c2b 2026-09-24 统一：货币只叫「星币」，「旅费」只当用途讲；集市里分杂货铺收购与居民订单）
    "web.home.move_in": "入住欢迎星币（每个家一次）",
    "web.journey.depart": "出发付旅费",
    "web.journey.replan": "来不及成行，旅费退回",
    "web.journey.work": "打工工钱",
    "web.market.sell": "集市：卖给杂货铺",
    "web.market.order": "集市：居民订单",
    "seed.admin_demo": "演示数据（只在演示库里有）",
}
LEDGER_STATUS = {"committed": "已入账"}  # 代码里只写这一种；别的状态出现就照原样显示

# 物种（schemas/web/pets.PetSpecies，用例双向核对）
SPECIES = {"dog": "狗", "cat": "猫", "parrot": "鹦鹉", "rabbit": "兔子", "hamster": "仓鼠", "bird": "鸟", "other": "其他"}

# ---- 宠物的东西 ----
# 藏品种类：与玩家时间线的 web_agent/timeline.py::COLLECTION_TITLE 双向核对，并核每一处发放藏品的写入口都收录了
COLLECTION_KIND = {"postcard": "明信片", "badge": "徽章", "seed": "种子", "shared_memory": "共同回忆（只显示数量，不看内容）",
                   "license_photo": "领证合影", "car_voucher": "驾校借车券"}
# 证件种类：说法以玩家后端的证件目录为准（web_credentials/service.py 的 CATALOG），后台只在后面补一句提示；
# 用例双向核对种类、并核每一条都以目录里的名字开头——玩家那边改名、这里没跟上就红
CREDENTIAL_KIND = {"identity_card": "星球居民证", "bank_card": "星球银行卡", "care_profile": "照护档案（内容不在后台显示）",
                   "passport": "护照", "driver_license": "爪爪驾驶证", "boarding_pass": "登机牌", "transport_ticket": "船票 / 车票",
                   "hotel_key": "酒店房卡"}
DRIVING_STAGE = {"wish": "说过想学车", "enrolled": "在驾校上课", "theory_passed": "理论考过了", "licensed": "拿到驾照",
                 # 与玩家那一侧同一个判断（web_driving/service.py 的 _stage_in）：记成考过了、却还没有驾驶证
                 "license_pending": "考试都过了，驾照还没签发（旧版留下的记录，系统会按那次考试补签）"}
CHARACTER_STATE = {"queued": "排队中", "running": "生成中", "ready": "已生成", "failed": "没生成出来"}
CHARACTER_POSE = {  # schemas/web/character.py::CharacterPose；精灵里只有姿态，光斑、食盆、窝都由场景画
    "neutral_full": "中性站姿（全身）",
    "sleeping": "睡觉",
    "sunbathing": "晒太阳",
    "eating": "吃东西",
    "walking": "走路",
    "petted": "被摸摸时的回应",
}
REPLY_REASON = {  # web_agent.reply_policy.ReplyPlan.reason：主人发来消息后，TA 为什么晚一点才回
    "distress": "主人像是遇到难处，尽快回",
    "asleep": "TA 在睡觉，醒来再回",
    "in_flight": "TA 在飞机上，落地再回",
    "on_the_way": "TA 在路上，信号慢一点",
    "visiting": "TA 在店里，忙完再回",
    "at_home": "TA 在家，稍等就回",
}
REPLY_OUTCOME = {"delivered": "已回复", "suppressed": "这条不再回复（情况变了）"}
# 菜地一格的状态（belongings.py 按种植、成熟、收获时间推出来的，不是库里的列）
PLOT_STATE = {"empty": "空着", "growing": "在长", "ripe": "熟了，等收", "harvested": "收过了"}

# ---- 系统运行 ----
OUTBOX_STATUS = {"pending": "待投递", "delivered": "已投递",
                 "dead_letter": "投递失败次数太多，已放弃（死信）"}  # web_platform/outbox.py：试满 MAX_ATTEMPTS 次
OUTBOX_CONSUMER = {
    "collection": "收藏（明信片、徽章）",
    "communicator": "通讯器消息",
    "credentials": "证件（银行卡流水等）",
    "friends": "朋友与相遇",
    "guides": "攻略手账",
    "social": "动态与社交",
}
# 世界推进怎么跑（设置 web_world_runner；app/main.py：embedded 在网站进程里跑、worker 交给独立进程、off 都不跑）
WORLD_RUNNER = {"embedded": "跟网站在同一个进程里跑", "worker": "由独立的后台进程跑", "off": "关着：世界不自动推进"}
# 执行者租约的角色（web_agent_wiring：web_world_runner=worker 时是独立进程，否则跟网站同一个进程）；租约名本身见 LANE
WORKER_ROLE = {"worker": "独立的后台进程", "embedded": "跟网站在同一个进程里"}

# 经济对账发现的种类（economy_checks.RULES 的键）
FINDING_KIND = {
    "balance_mismatch": "余额和流水对不上",
    "chain_gap": "前后两条流水接不上",
    "entry_inconsistent": "一条流水自己算不对",
    "ledger_without_wallet": "有流水却没有钱包",
    "negative_balance": "余额是负数",
    "repeated_admin_compensation": "短时间里重复补偿",
}

# 批量补偿里每一只的结果（m1520 admin_grant_batch_items.status）
BATCH_ITEM_STATUS = {"pending": "待发放", "applied": "已发放", "skipped": "跳过了", "failed": "没发成"}
# 内容正文里的字段（content_types.py 的校验与各领域的 *_PUBLISHABLE_FIELDS）
CONTENT_FIELD = {
    "title": "标题", "body": "正文", "severity": "级别", "audience": "可见范围", "link": "站内链接", "image_asset_id": "配图",
    "badge": "徽章", "story": "故事", "city": "城市", "summary": "简介", "fee": "旅费",
    "label": "名称", "unit_value": "收购价", "grow_seconds": "成熟用时（秒）", "hours": "工时", "pay": "工钱",
    "personality": "性格", "dream": "梦想", "source_note": "来源说明",
    # 不可发布的字段（routers/admin/content.py 的 blocked）：列出来并说明，不悄悄不显示
    "key": "内部编号", "yield_units": "每次收获几份", "steal_total": "一块地最多被偷几份", "requires_seed": "要不要种子",
    "keyword": "岗位关键词（决定哪里有这个活）", "habitats": "哪些地方有这个活", "outbound": "去程路线", "inbound": "回程路线",
    "venue": "要去的店", "wish_keywords": "和愿望对上的关键词", "food_area": "吃东西的片区", "name": "名字", "species": "物种",
    "pet_id": "宠物编号",
    # 预览里额外算出来给人看的几行
    "consumer": "玩家侧在哪儿读到", "story_template": "故事模板", "sample_render": "示例效果", "sample_note": "示例说明",
    "grow_readable": "成熟用时", "shop_line": "杂货铺收购", "worked_line": "打工结算示例", "total_minutes": "全程用时（分钟）",
    "modes": "交通方式", "identity": "是谁", "identity_note": "说明",
    # 校验问题里会出现的另外两个字段
    "content_type": "内容类型", "slug": "条目",
}
# 公告的级别与可见范围（web_admin/content_types.py 的 ANNOUNCEMENT_SEVERITIES / ANNOUNCEMENT_AUDIENCES）
ANNOUNCEMENT_SEVERITY = {"info": "一般", "notice": "通知", "maintenance": "维护"}
ANNOUNCEMENT_AUDIENCE = {"all": "所有访客", "signed_in": "仅已登录"}
# 检索命中的是哪一项（web_admin/directory.py 的 matched_on）
SEARCH_MATCH = {"user_id": "用户编号", "username": "用户名", "display_name": "显示名", "pet": "宠物名或编号"}

# ---- 第八批：旅程逐段（schemas/web/transport.JourneyLeg 的字段类型）----
LEG_DIRECTION = {"outbound": "去程", "return": "回程"}  # web_journey_legs.direction 的 CHECK
LEG_KIND = {"main": "主要的一段", "connection": "接驳", "wait": "等候", "transfer": "换乘"}
TRANSPORT_MODE = {"flight": "飞机", "train": "火车", "ferry": "渡轮", "drive": "开车", "transit": "公交或地铁", "taxi": "出租车", "walk": "走路"}
TRAVELLER_ROLE = {"driver": "自己开", "passenger": "坐车", "walker": "走路"}
TIME_BASIS = {"verified_timetable": "核实过的时刻表", "live_status": "实时动态", "routed_estimate": "按路线估算", "demo_fixture": "演示用的固定时间"}
DATA_FRESHNESS = {"verified": "核实过", "stale": "可能过时了", "unavailable": "没有实时数据"}
POSITION_BASIS = {"simulated_route": "按路线模拟的位置", "schematic": "示意位置", "live_vehicle": "真实车辆的位置"}
# 到店（schemas/web/journey）
VENUE_TEMPLATE = {"cafe": "咖啡馆", "restaurant": "餐厅", "park": "公园", "generic": "其他地方"}
VISIT_ACTIVITY = {"choose_seat": "选座位", "order_drink": "点饮品", "take_photo": "拍照", "greet_resident": "和店里的居民打招呼"}
VISIT_ACTIVITY_STATE = {"available": "可以做", "in_progress": "正在做", "done": "做完了", "disabled": "做不了"}

# ---- 第八批：社交（schemas/web/social）----
ACTOR_KIND = {"pet": "宠物", "npc": "游戏里的居民", "owner": "主人"}
FRIEND_KIND = {"pet": "别人家的宠物", "resident": "游戏里的居民"}
POST_VISIBILITY = {"public": "公开", "followers": "仅关注者可见", "removed": "已下架"}

# ---- 第八批：待领养居民（web_residents 的 CHECK 与 schemas/web/pets）----
# kind 是「类型」不是「现在的状态」：已经被领养的居民类型仍是 adoptable，所以不说「可以领养」
RESIDENT_KIND = {"adoptable": "可领养类", "public_npc": "公共居民（不参加领养）"}
RESIDENT_STATUS = {"resident": "住在驿站", "adopted": "已经被领养"}
ADOPTION_AVAILABILITY = {"available": "可以领养", "reserved": "有人正在领养", "adopted": "已经被领养"}
# 来源（m0240：原创伙伴与已核验真实原型分开标注）；对还没被领养的居民也成立，所以不写「领养的」
PET_ORIGIN = {"own_pet": "主人自己的宠物", "adopted_original": "原创伙伴", "adopted_real_archive": "有真实原型的伙伴（已核验）"}

# ---- 第八批：驾校课堂（web_driving 的字面量）、同行影音、口味（schemas/web/companion_media、food）----
SCHOOL_MODE = {"formal": "正式考试", "practice": "练习"}
SCHOOL_STATE = {"preparing": "准备中", "running": "进行中", "settled": "已经结算", "void": "作废了"}
MEDIA_STATE = {"playing": "正在放", "paused": "暂停了", "ended": "放完了", "interrupted": "被打断了"}
PARTICIPATION_MODE = {"not_joined": "没加入", "joining": "正在加入", "synced": "一起在看 / 听", "solo": "自己看 / 听",
                      "buffering": "缓冲中", "blocked": "被挡住了", "failed": "没连上", "left": "离开了"}
FOOD_SUBJECT = {"pet": "宠物的口味", "owner": "主人的口味"}
FOOD_MODE = {"pet_virtual_explore": "宠物在游戏里尝鲜", "owner_real_dining": "主人真的去吃"}

# ---- 授权开关（只看开关，不看正文）----
CONSENT = {
    "household_id": "所属家庭",
    "owner_user_id": "照顾人",
    "household_generated_photos": "家庭：允许生成照片",
    "household_pet_messages": "家庭：允许宠物主动发消息",
    "owner_model_replies": "照顾人：开启 AI 回复",
    "owner_generated_photos": "照顾人：允许生成照片",
    "cognition_enabled": "AI 思考已启用",
}

# ---- 后台自己的：审计动作、权限、角色、举报处理 ----
AUDIT_ACTION = {
    # 查看（合法访问也留痕）
    "user.search": "搜索用户或宠物",
    "user.detail": "查看用户详情",
    "user.ledger_summary": "查看用户的两本账汇总",
    "pet.diagnosis": "查看宠物诊断",
    "pet.belongings": "查看宠物的东西",
    "home.detail": "查看家里的东西",
    "user.social": "查看用户的社交",
    "resident.list": "查看待领养居民",
    "pet.runtime_list": "查看宠物运行总览",
    "photo.detail": "查看照片任务",
    "report.list": "查看举报队列",
    # 处置
    "account.freeze": "冻结账号",
    "account.unfreeze": "解冻账号",
    "account.revoke_session": "让账号在所有设备上退出登录",
    "report.takedown": "下架被举报的内容",
    "report.dismiss": "举报记为不处理",
    "report.restore": "恢复被下架的内容",
    "report.claim": "认领举报",
    "report.release": "放弃认领",
    "provider.paused": "暂停新增 AI 调用",
    "provider.active": "恢复新增 AI 调用",
    "task.recover": "受控恢复一次照片任务",
    "pet.pause": "暂停宠物的自主运行",
    "pet.resume": "恢复宠物的自主运行",
    # 游戏经济
    "economy.grant": "补偿星币",
    "economy.reverse": "冲正一笔补偿",
    "economy.batch_submit": "提交批量补偿",
    "economy.batch_decide": "审批批量补偿",
    "economy.batch_execute": "执行批量补偿",
    # 内容与素材
    "content.create": "新建内容",
    "content.save_draft": "保存内容草稿",
    "content.publish": "发布内容",
    "content.withdraw": "撤下内容",
    "content.rollback": "回退到旧版本",
    "asset.upload": "上传素材",
    "asset.retire": "下架素材",
    # 平台成本
    "cost.price_add": "录入价格",
    "cost.price_retire": "作废价格",
    "cost.relay_import": "导入中转回执",
    # 员工
    "staff.bootstrap": "在服务器上创建第一个员工",
    "staff.create": "新建员工",
    "staff.login": "员工登录",
    "staff.logout": "员工退出",
    "staff.mfa_enroll_started": "开始绑定二次验证",
    "staff.mfa_activated": "启用二次验证",
    "staff.set_roles": "调整员工角色",
    "staff.set_status": "停用或启用员工",
}
# 审计里「对什么」的种类（trace_read / 各命令的 target_kind；post / comment 来自举报）
TARGET_KIND = {
    "user": "用户", "pet": "宠物", "home": "家", "illustration": "照片", "post": "动态", "comment": "评论",
    "switch": "开关", "query": "搜索词", "queue": "举报队列", "staff": "员工", "grant_batch": "批量补偿",
    "asset": "素材", "content": "内容", "price": "价格", "residents": "待领养居民名单", "pets": "宠物运行总览", "relay_import": "中转回执导入",
}
AUDIT_STATUS = {"allowed": "查看", "succeeded": "成功", "replayed": "重放（同一操作号，没有重复生效）",
                "denied": "被拒绝", "failed": "失败"}
ROLE = {
    "platform_owner": "平台负责人",
    "support": "客服",
    "moderator": "审核",
    "content_editor": "内容编辑",
    "content_publisher": "内容发布",
    "economy_ops": "经济运营",
    "economy_lead": "经济负责人",
    "sre": "技术运维",
    "auditor": "只读审计",
}
PERMISSION = {
    "ops.read": "看运营首页与系统运行",
    "user.read": "查用户与家庭（脱敏）",
    "pet.read": "看宠物诊断与宠物的东西",
    "task.read": "看照片与任务",
    "provider.read": "看调用用量与平台成本",
    "economy.read": "看星币流水与家里的库存",
    "report.read": "看举报队列",
    "content.read": "看内容草稿与发布历史",
    "asset.read": "看素材库",
    "audit.read": "看操作记录",
    "private.read": "看私密正文（默认不给任何角色）",
    "account.freeze": "冻结 / 解冻账号",
    "account.revoke_session": "让账号在所有设备上退出登录",
    "report.action": "处理举报（下架 / 恢复 / 不处理）",
    "provider.pause": "暂停 / 恢复新增 AI 调用",
    "task.recover": "受控恢复失败的任务",
    "pet.maintain": "暂停 / 恢复宠物的自主运行",
    "content.edit": "编辑内容草稿",
    "content.publish": "发布 / 撤下 / 回退内容",
    "asset.manage": "上传 / 下架素材",
    "economy.grant": "单笔补偿星币",
    "economy.grant_batch": "提交与执行批量补偿",
    "economy.approve": "审批批量补偿",
    "economy.reverse": "冲正一笔后台补偿",
    "cost.manage": "维护平台价格表",
    "staff.manage": "管理员工与角色",
}
REPORT_DECISION = {"takedown": "下架", "dismiss": "不处理", "restore": "恢复"}
LANE = {"world": "世界推进", "cognition": "AI 思考"}
# 执行者状态按配置判（web_admin/lanes.py；c84a 审查 ADM-HEALTH-02）
LANE_STATE = {"configured_off": "按配置关着（不是故障）", "healthy": "在岗", "lost": "应该在跑，但心跳过期了（可能停了）"}

# ---- 第九批：宠物运行总览（config.py 的模式说明；pet_runtime.py 按已记录的事实推出来的状态）----
# AI 思考写进安静原因那一列的 `brain:<原因>`（web_agent/brain_life.py、brain_wiring.py）：对照模式记下的结论，
# 或这一次没想成、稍后再试的原因——DecisionFailureCode、提交前按此刻复核（截止、撤回同意、资料变了、去处过期）、异常退避。
# 出发被规则拒绝时记的是出发那边的原因（开放集合），认不出来的统一说「这次没想成，稍后再试」：那条路径的共同事实就是这个。
BRAIN_BACKOFF = {
    "shadow": "对照模式：想过了，只记下结论、不执行",
    "no_offers": "这会儿没有可以选的去处",
    "disabled": "模型开关关着或没有凭证，没有调用",
    "budget_denied": "AI 思考的额度用完了，没有调用",
    "timeout": "模型超时没回",
    "provider_error": "模型服务出错（连不上或被限流）",
    "bad_output": "模型给的结果格式不对",
    "unknown_offer": "模型选了一个不在候选里的去处",
    "out_of_bounds": "模型给的参数超出范围",
    "stale_context": "资料版本变了，或候选去处过期了",
    "revoked": "权限撤回了，或成员被移除了",
    "deadline_passed": "过了这次思考的截止时间",
    "deadline_exceeded": "想好时已经过了截止时间，这次不执行",
    "consent_withdrawn": "想的时候家里同意用模型，交出结果前撤回了，这次不执行",
    "versions_changed": "想好时资料已经变了（行程、成员或隐私设置），这次不执行",
    "offer_expired": "想好时选中的去处已经过期，这次不执行",
    "evaluate_failed": "评估这只宠物时出错（还没调模型）",
    "round_failed": "这一轮思考出错（那次调用可能已经发出，不重发）",
    "unknown": "原因不明",
}
HEARTBEAT_MODE = {"off": "不跑", "shadow": "对照：每轮评估并记下结论，不执行、不调模型"}
BRAIN_MODE = {"off": "关：一次模型都不调", "shadow": "对照：会调模型，但只记下结论、不执行", "live": "正式：复核后真的执行"}
HEARTBEAT_STATE = {"never": "还没评估过", "late": "过了该看的时间还没看", "ok": "按时", "paused": "已暂停"}
BRAIN_STATE = {"thinking": "正在思考", "stuck": "思考超过 10 分钟还没结束", "idle": "没在思考"}
# 规则生活每个时段记下的决定（web_agent/life.py 的 _record）；go:<地点> 由后端换成地点名
RULE_DECISION = {"rest": "这个时段歇着", "rest:enough_today": "今天出门够了，歇着", "go": "决定出门"}
# 每天生图的结果分类（额度账的 status / outcome 合起来看；metering 的口径）
IMAGE_BUCKET = {"ok": "出图了", "failed": "发出去了、没画成", "not_sent": "没发出（额度已退回）", "unknown": "结果未确认",
                "inflight": "还在路上"}

FAMILIES: dict[str, dict[str, Any]] = {
    "activity": ACTIVITY,
    "silence": {code: text for code, (text, _) in SILENCE.items()},
    "silence_kind": SILENCE_KIND,
    "heartbeat_action": HEARTBEAT_ACTION,
    "decided_by": DECIDED_BY,
    "reason": REASON,
    "due_kind": DUE_KIND,
    "journey_lifecycle": JOURNEY_LIFECYCLE,
    "world_event": WORLD_EVENT,
    "illustration_status": ILLUSTRATION_STATUS,
    "call_state": CALL_STATE,
    "task_status": TASK_STATUS,
    "reservation_status": RESERVATION_STATUS,
    "provider": PROVIDER,
    "purpose": PURPOSE,
    "task_kind": TASK_KIND,
    "task_error": TASK_ERROR,
    "director_hold": DIRECTOR_HOLD,
    "photo_surface": PHOTO_SURFACE,
    "ledger_type": LEDGER_TYPE,
    "ledger_source": LEDGER_SOURCE,
    "ledger_status": LEDGER_STATUS,
    "consent": CONSENT,
    "leg_direction": LEG_DIRECTION,
    "leg_kind": LEG_KIND,
    "transport_mode": TRANSPORT_MODE,
    "traveller_role": TRAVELLER_ROLE,
    "time_basis": TIME_BASIS,
    "data_freshness": DATA_FRESHNESS,
    "position_basis": POSITION_BASIS,
    "venue_template": VENUE_TEMPLATE,
    "visit_activity": VISIT_ACTIVITY,
    "visit_activity_state": VISIT_ACTIVITY_STATE,
    "actor_kind": ACTOR_KIND,
    "friend_kind": FRIEND_KIND,
    "post_visibility": POST_VISIBILITY,
    "resident_kind": RESIDENT_KIND,
    "resident_status": RESIDENT_STATUS,
    "adoption_availability": ADOPTION_AVAILABILITY,
    "pet_origin": PET_ORIGIN,
    "school_mode": SCHOOL_MODE,
    "school_state": SCHOOL_STATE,
    "media_state": MEDIA_STATE,
    "participation_mode": PARTICIPATION_MODE,
    "food_subject": FOOD_SUBJECT,
    "food_mode": FOOD_MODE,
    "batch_item_status": BATCH_ITEM_STATUS,
    "content_field": CONTENT_FIELD,
    "finding_kind": FINDING_KIND,
    "audit_action": AUDIT_ACTION,
    "audit_status": AUDIT_STATUS,
    "target_kind": TARGET_KIND,
    "report_decision": REPORT_DECISION,
    "lane": LANE,
    "role": ROLE,
    "permission": PERMISSION,
    "species": SPECIES,
    "collection_kind": COLLECTION_KIND,
    "credential_kind": CREDENTIAL_KIND,
    "driving_stage": DRIVING_STAGE,
    "character_state": CHARACTER_STATE,
    "brain_backoff": BRAIN_BACKOFF,
    "character_reason": CHARACTER_REASON,
    "character_pose": CHARACTER_POSE,
    "heartbeat_mode": HEARTBEAT_MODE,
    "brain_mode": BRAIN_MODE,
    "heartbeat_state": HEARTBEAT_STATE,
    "brain_state": BRAIN_STATE,
    "rule_decision": RULE_DECISION,
    "image_bucket": IMAGE_BUCKET,
    "lane_state": LANE_STATE,
    "announcement_severity": ANNOUNCEMENT_SEVERITY,
    "announcement_audience": ANNOUNCEMENT_AUDIENCE,
    "search_match": SEARCH_MATCH,
    "reply_reason": REPLY_REASON,
    "reply_outcome": REPLY_OUTCOME,
    "outbox_status": OUTBOX_STATUS,
    "outbox_consumer": OUTBOX_CONSUMER,
    "worker_role": WORKER_ROLE,
    "world_runner": WORLD_RUNNER,
    "plot_state": PLOT_STATE,
}


def label(family: str, code: str | None) -> str | None:
    """代码 → 说法；没收录（或代码为空）返回 None，由调用方决定如实显示原值。"""
    if code is None:
        return None
    return FAMILIES.get(family, {}).get(code)


def silence_label(code: str | None) -> str | None:
    """安静原因那一列 → 说法。心跳写的是 SilenceReason；AI 思考写的是 `brain:<原因>`（见 BRAIN_BACKOFF）。认不出来的返回 None。"""
    if not code:
        return None
    if code.startswith("brain:"):
        text = BRAIN_BACKOFF.get(code.split(":", 1)[1].split(":")[0])
        return f"AI 思考：{text}" if text else "AI 思考：这次没想成，稍后再试"
    entry = SILENCE.get(code)
    return entry[0] if entry else None


def reason_label(code: str) -> str | None:
    """心跳依据：`silence:<安静原因>` 按安静原因翻译，其余按 REASON。"""
    if code.startswith("silence:"):
        text = label("silence", code.split(":", 1)[1])
        return f"安静原因：{text}" if text else None
    return label("reason", code)


def error_label(text: str | None) -> str | None:
    """任务错误串 → 一句人话。认得的片段翻译，认不得的返回 None（界面照原样显示）。

    错误串是自由文本（常见形如 `image director_hold:identity_reference_missing` 或 `image timeout`），
    这里只做**认得出来才翻**的匹配：前缀是供应商名的先去掉，再按导演暂停 / 已知片段逐个认。
    """
    if not text:
        return None
    body = text.strip()
    head, _, rest = body.partition(" ")
    if rest and head in ("image", "character", "id_photo"):
        body = rest.strip()
    if body.startswith("delivery_would_drop:"):
        return f"交付会丢掉不该丢的内容（{body.split(':', 1)[1]}），宁可不出图。不会自动重试。"
    if body.startswith("director_hold:"):
        parts = body.split(":")
        reason = DIRECTOR_HOLD.get(parts[1]) if len(parts) > 1 else None
        missing = f"（缺：{parts[2]}）" if len(parts) > 2 and parts[2] else ""
        return (f"照片导演没有开拍：{reason or '条件不齐'}{missing}。系统不会自动重试；"
                "要等缺的东西补上（比如主人上传了参考照）之后，恢复一次才有用。")
    # 角色形象与证件照的任务错误写的是它们自己的原因码（`character <码>` / `id_photo <码>`）
    return TASK_ERROR.get(body) or (CHARACTER_REASON.get(body) if head in ("character", "id_photo") else None)


def audit_action_label(action: str) -> str | None:
    """审计动作 → 说法。没有权限被挡下的请求记成 `denied:<方法> <路径>`，按规则翻成「被拒绝的请求」。"""
    if action.startswith("denied:"):
        return f"没有权限、被挡下的请求（{action.split(':', 1)[1].strip()}）"
    return AUDIT_ACTION.get(action)
