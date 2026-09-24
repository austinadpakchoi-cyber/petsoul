"""爪爪驾校的课程与台词：教练、四科说明、分步教学、扣分项与红线、操作说明、补考规则。

- 教练“龟教练·慢慢”是原创居民；播报保持中立，不替主人答题。
- TA 的话按 DNA 行为画像的性格选择固定模板，不调用模型、不随机影响成绩；没考过时不责怪主人。
- 所有扣分项和红线在教学页和开考说明里提前列出，不在考后才告诉主人。
"""

from __future__ import annotations

import hashlib

from .courses import FORMAL_ITEMS, PRACTICE_ITEMS, TICK_HZ, TITLES, course_for

RULES_VERSION = "paw-school-2026.1"
SUBJECTS = ("s1", "s2", "s3", "s4")
COOLDOWN_HOURS = 7 * 24

COACH = {"name": "龟教练·慢慢", "line": "方向可以慢慢找，停车要稳稳当当。",
         "intro": "我是爪爪驾校的龟教练慢慢。学车不着急，你们一起练，练会了再考。考场上我只报指令，不告诉答案。"}

META = {
    "s1": {"title": "科目一：认识路上的规则", "theme": "看得懂、判断对", "format": "10 道题：看场景选择、拖放标志、判断先后，每题 10 分",
           "pass_rule": "达到 90 分通过", "pass_score": 90, "duration": "约 3 分钟", "kind": "quiz"},
    "s2": {"title": "科目二：把小车开稳", "theme": "方向与空间", "format": "倒车入库、侧方停车、弯道行驶，一场连考",
           "pass_rule": "三项都完成，综合达到 80 分通过；任何一项超时或开出训练场即不通过", "pass_score": 80, "duration": "约 6—8 分钟", "kind": "drive"},
    "s3": {"title": "科目三：第一次上路", "theme": "连续驾驶与观察", "format": "开车把一篮菜从农场路口送到星球食堂",
           "pass_rule": "完成路线、达到 80 分，且没有触发红线", "pass_score": 80, "duration": "约 3—5 分钟", "kind": "drive"},
    "s4": {"title": "科目四：遇到情况怎么办", "theme": "情境判断", "format": "五段路上的小事，每段两个判断，每个 10 分",
           "pass_rule": "达到 90 分通过", "pass_score": 90, "duration": "约 3 分钟", "kind": "quiz"},
}

LESSONS = {
    "s1": [("小课堂怎么上", "教练的桌上有一座会动的小街道。每道题先看场景，再选择、拖放或排顺序。"),
           ("练习和考试的区别", "练习时答完一题马上讲解；正式考试全部答完才出成绩，TA 不会提前提示答案。"),
           ("考查的内容", "停车让行、指示与警告标志、礼让过街的居民、信号灯、给救援车让路、出发前检查、停车的地方、慢行的地方、倒车安全，每项一题。")],
    "s2": [("操作", "左手拖动方向盘（也可以换成“左 / 回正 / 右”按钮），右手按油门和刹车。车完全停下才能切换 D（前进）和 R（倒车）。"),
           ("第一步：直线倒车", "挂 R，轻点油门慢慢往后，车身保持直线，停在指定区域。"),
           ("第二步：转向与回正", "倒车时向右打方向，车尾往右边摆；车身摆正后记得回正方向。"),
           ("第三步：完整入库", "开过车位 → 在起始区停稳 → 挂 R → 边倒边转进车位 → 修正角度 → 回正并停稳 2 秒。"),
           ("侧方停车", "沿路开过车位，停稳后挂 R 向右打满倒车，车身斜进车位后反方向打满，把车摆正，停在车位里。"),
           ("弯道行驶", "低速通过一段 S 弯，跟着车道慢慢转方向，开进终点区停稳。"),
           ("练习与考试", "练习时有预测轨迹、目标车位和分步提示；正式考试只保留边线、车位和挡位。")],
    "s3": [("路线", "从农场路口出发，把一篮刚收的菜送到星球食堂：出发前检查 → 起步 → 停车让行路口 → 人行横道 → 红绿灯 → 路口右转 → 靠边停车。"),
           ("出发前", "依次点“系好安全带”“调好后视镜”“看看四周”，再打左转灯起步。"),
           ("转向灯", "起步前打左转灯；到了右转路口前打右转灯。"),
           ("停车让行", "“停”字牌路口要在停止线前完全停稳，再继续走。"),
           ("礼让居民", "有居民正在过人行横道时，停在线前，等它走到对面。"),
           ("开车不看视频", "开车时手机弹出视频邀请，选“稍后再看”；考场不会真的打开视频。"),
           ("靠边停车", "到星球食堂门口，把车停进装卸区，车身摆正，停稳 2 秒。")],
    "s4": [("路上的小事", "五段生活小动画：困了、天气变差、视频邀请、倒车时附近有居民、车上东西掉了。每段两个判断。"),
           ("怎么答", "先看故事，再判断“现在要怎样做”。科一问“标志是什么意思”，科四问“你现在怎么做”。"),
           ("练习与考试", "练习时答完马上讲解；正式考试全部答完才出成绩。")],
}

DEDUCTIONS = {
    "s1": [("答错一题", 10)],
    "s2": [("一次连续压线", 5), ("碰到一个训练锥（每个只算一次）", 10)],
    "s3": [("起步前没完成三项检查", 10), ("起步时没打左转灯", 5), ("停车让行路口没停稳", 10), ("右转前没打右转灯", 10), ("超速（每次）", 5),
           ("压到路沿或中心线（每次）", 5), ("开车时打开视频邀请", 10)],
    "s4": [("判断错一个", 10)],
}
RED_LINES = {
    "s1": [], "s4": [],
    "s2": ["任何一项超过时间限制", "车身开出训练场"],
    "s3": ["闯已经亮起的红灯", "冲进居民正在通过的人行横道", "开出道路", "超过时间限制"],
}
CONTROLS = ["左手：拖动方向盘转向；松手后方向盘停在原处，点“回正”可以回到中间。也可以换成“左 / 回正 / 右”按钮。",
            "右手：按住油门加速，按住刹车减速。车完全停下后才能切换 D / R。",
            "键盘：← → 转向，↑ 油门，空格 刹车，D / R 换挡，Q / E 左右转向灯。"]
RETAKE_RULE = ["每科有一次首次考试和一次补考。", "两次都没通过，这一科需要等 7 天（从第二次结算的时间算起）才能再约考试；已经通过的科目一直保留。",
               "等待期间可以不限次数地练习，TA 的生活和旅行照常。", "资源加载完成、点“开始考试”后才算一次考试；网络或程序故障中断的考局会保留，回来可以接着考。"]

REASONS = {
    "line": "压线", "cone": "碰到训练锥", "out_of_bounds": "开出了场地", "timeout": "超过时间限制", "precheck_skipped": "起步前没完成三项检查",
    "start_no_signal": "起步时没打左转灯", "stop_rolled": "停车让行路口没停稳", "crosswalk": "冲进了居民正在通过的人行横道", "red_light": "闯了红灯",
    "turn_no_signal": "右转前没打右转灯", "speeding": "超速", "invite_opened": "开车时打开了视频邀请", "wrong_answer": "答错", "abandoned": "中途放弃了这场考试",
}

PET_LINES = {
    "lively": {"pass": "我们过啦！尾巴都摇起来了！", "fail": "这轮先到这里，我们把要练的地方记下来了。下次我们一起再来！",
               "park": "停进去啦！", "right": "对啦，我记住了！", "license": "以后，换我载你去看世界！"},
    "steady": {"pass": "过了。谢谢你陪我练。", "fail": "这轮先到这里，我们把要练的地方记下来了。", "park": "停稳了。", "right": "嗯，这个我记住了。",
               "license": "以后，换我载你去看世界。"},
    "quiet": {"pass": "（抬头看了你一眼）过了。", "fail": "（轻轻蹭了蹭你）这轮先到这里，我们把要练的地方记下来了。", "park": "（松开方向盘，转头看了看你）",
              "right": "（点点头）", "license": "（把驾照捧到你面前）以后，换我载你去看世界。"},
}


def temperament(profile) -> str:
    if profile is None:
        return "steady"
    if profile.sociability == "social" or profile.curious:
        return "lively"
    return "quiet" if profile.sociability == "homebody" else "steady"


def pet_line(kind: str, profile, pet_id: str = "") -> str:
    return PET_LINES[temperament(profile)][kind]


def items(subject: str) -> list[dict]:
    names = FORMAL_ITEMS.get(subject, ())
    return [{"item": name, "title": TITLES[name], "time_limit_s": course_for(name, "a")["time_limit_ticks"] // TICK_HZ} for name in names]


def practice_items(subject: str) -> list[dict]:
    return [{"item": name, "title": TITLES[name], "time_limit_s": course_for(name, "a")["time_limit_ticks"] // TICK_HZ} for name in PRACTICE_ITEMS.get(subject, ())]


def curriculum() -> dict:
    subjects = []
    for key in SUBJECTS:
        meta = META[key]
        subjects.append({"subject": key, **{k: meta[k] for k in ("title", "theme", "format", "pass_rule", "pass_score", "duration", "kind")},
                         "lessons": [{"title": t, "body": b} for t, b in LESSONS[key]], "deductions": [{"label": l, "points": p} for l, p in DEDUCTIONS[key]],
                         "red_lines": list(RED_LINES[key]), "items": items(key), "practice_items": practice_items(key)})
    return {"rules_version": RULES_VERSION, "coach": dict(COACH), "subjects": subjects, "controls": list(CONTROLS), "retake_rule": list(RETAKE_RULE),
            "cooldown_hours": COOLDOWN_HOURS, "reasons": dict(REASONS)}


def seed(*parts: object) -> int:
    return int(hashlib.sha1(":".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:8], 16)
