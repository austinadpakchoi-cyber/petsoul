"""科目一（路边小课堂）与科目四（路上的小事）的固定题库：经过审核的内容，不由模型临时编题。

- 科一：10 个知识点 × 3 道题，题型有看场景选择（choice）、拖放标志（match）、判断先后（order），每题 10 分；
  正式卷每个知识点抽 1 题共 10 题，补考换题，覆盖范围与难度相同；练习每次 5 题、三种题型每张都有，答完立刻讲解。
- 科四：5 类情境 × 2 个版本，每段两个判断（choice），共 10 个判断；补考换另一个版本。
这些都是 PetSoul 世界的游戏题目，参考大家熟悉的安全常识，不代表现实驾考题库。
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

BANK_VERSION = "paw-quiz-2026.2"


@dataclass(frozen=True)
class Quiz:
    question_id: str
    subject: str
    topic: str
    kind: str  # choice / match / order
    scene: str
    prompt: str
    options: tuple[tuple[str, str], ...]
    answer: object  # choice：选项 id；order：选项 id 的正确顺序；match：{目标 id: 选项 id}
    explanation: str
    pet_line: str
    targets: tuple[tuple[str, str], ...] = ()
    group: str | None = None
    group_title: str | None = None
    story: tuple[str, ...] = field(default_factory=tuple)


def _choice(qid, topic, scene, prompt, options, answer, explanation, pet_line):
    opts = tuple((f"{qid}.{chr(97 + i)}", text) for i, text in enumerate(options))
    return Quiz(qid, "s1", topic, "choice", scene, prompt, opts, opts[answer][0], explanation, pet_line)


def _order(qid, topic, scene, prompt, steps, explanation, pet_line):
    opts = tuple((f"{qid}.{i}", text) for i, text in enumerate(steps))
    shown = opts[2:] + opts[:2]  # 显示顺序与正确顺序不同
    return Quiz(qid, "s1", topic, "order", scene, prompt, shown, tuple(o[0] for o in opts), explanation, pet_line)


def _match(qid, topic, scene, prompt, pairs, explanation, pet_line):
    opts = tuple((f"{qid}.o{i}", item) for i, (item, _) in enumerate(pairs))
    targets = tuple((f"{qid}.t{i}", place) for i, (_, place) in enumerate(pairs))
    shown = opts[1:] + opts[:1]
    return Quiz(qid, "s1", topic, "match", scene, prompt, shown, {targets[i][0]: opts[i][0] for i in range(len(pairs))}, explanation, pet_line, targets)


S1_TOPICS = ("stop_sign", "direction_sign", "warning_sign", "crosswalk", "signals", "emergency", "pre_drive", "parking_zone", "slow_zone", "reverse_safety")
S1_TOPIC_TITLES = {"stop_sign": "停车让行", "direction_sign": "指示标志", "warning_sign": "警告标志", "crosswalk": "礼让过街的居民", "signals": "信号灯",
                   "emergency": "给救援车让路", "pre_drive": "出发前检查", "parking_zone": "停车的地方", "slow_zone": "慢行的地方", "reverse_safety": "倒车安全"}

S1_BANK: dict[str, tuple[Quiz, ...]] = {
    "stop_sign": (
        _choice("s1.stop.1", "stop_sign", "stop_junction", "路口立着红色八角形的“停”字牌，小车开到停止线前，应该？",
                ["减速看一眼就开过去", "在停止线前完全停下，看清楚再走", "按喇叭提醒别人让开"], 1,
                "“停”字牌的意思是先完全停下来，确认左右安全再走。", "“停”字牌就是要停稳，我记住啦。"),
        _match("s1.stop.2", "stop_sign", "sign_board", "把三块标志放到它们该出现的地方",
               [("“停”字牌", "没有红绿灯的路口前"), ("人行横道牌", "斑马线旁边"), ("停车场牌", "停车区入口")],
               "“停”字牌放在需要停车让行的路口，人行横道牌在斑马线旁，停车场牌告诉大家从哪里进停车区。", "每块牌子都有自己的位置。"),
        _choice("s1.stop.3", "stop_sign", "stop_junction_night", "晚上路口一辆车也没有，但立着“停”字牌，应该？",
                ["反正没车，直接开过去", "照样先停稳，看清楚再走", "打开远光灯直接冲过去"], 1,
                "没车也要按标志停稳，因为暗处可能有看不到的居民。", "没车也要停，晚上更要仔细看。"),
    ),
    "direction_sign": (
        _choice("s1.dir.1", "direction_sign", "blue_arrow", "蓝色圆牌上画着向右的白色箭头，表示？", ["只准向右行驶", "禁止向右转", "前方有向右的急弯"], 0,
                "蓝色圆牌是指示标志：白色箭头指向哪里，就只能往哪里走。", "蓝色圆牌跟着箭头走。"),
        _choice("s1.dir.2", "direction_sign", "lane_arrows", "地上画着直行箭头的车道，想右转的小车应该？", ["在这条车道直接右转", "提前换到画着右转箭头的车道", "停在路中间等机会"], 1,
                "地上的箭头告诉你这条车道能去哪；要右转，提前换到右转车道。", "想右转，要提前换到右转车道。"),
        _match("s1.dir.3", "direction_sign", "sign_board", "把方向标志放到对应的路段", [("向左的箭头牌", "只能左转的路口"), ("向上的箭头牌", "只能直行的路段")],
               "指示标志告诉你这里只能怎么走，放在对应的路口或路段前面。", "左转牌放左转路口，直行牌放直行路段。"),
    ),
    "warning_sign": (
        _choice("s1.warn.1", "warning_sign", "deer_sign", "黄色三角牌里画着一只小鹿，提醒什么？", ["前方可能有动物横穿，减速注意", "前面是动物园入口", "这里可以喂小鹿"], 0,
                "黄色三角是警告标志：前方可能有动物横穿，放慢速度。", "看到小鹿牌，就慢一点。"),
        _choice("s1.warn.2", "warning_sign", "curve_sign", "黄色三角牌上画着一条向右弯的路，提醒？", ["前方向右弯，提前减速", "必须向右转", "前面可以掉头"], 0,
                "这是弯道警告：弯前先减速，转弯时才稳。", "弯道之前先减速。"),
        _choice("s1.warn.3", "warning_sign", "children_sign", "黄色三角牌上画着两个背书包的小朋友，提醒？", ["附近有学校，注意小朋友，慢慢开", "前面是游乐场，可以按喇叭", "小朋友要让车先走"], 0,
                "学校附近随时可能有小朋友跑出来，要慢慢开，随时准备停下。", "学校附近慢慢开。"),
    ),
    "crosswalk": (
        _choice("s1.walk.1", "crosswalk", "zebra_penguin", "企鹅居民正走在斑马线上，小车来到路口，应该？", ["停在线前，等它走完", "从它身后绕过去", "按喇叭催它快点"], 0,
                "斑马线上有居民，就停在线前等它走完，不绕、不催。", "这个我记住了，先让小企鹅过去。"),
        _choice("s1.walk.2", "crosswalk", "zebra_waiting", "斑马线边上站着一只准备过马路的兔子，应该？", ["减速停下，让它先过", "它还没走上来，赶紧开过去", "闪大灯让它别过"], 0,
                "居民准备过马路，也要减速停下让它先过。", "看到有人要过马路，就停下来等。"),
        _order("s1.walk.3", "crosswalk", "zebra_steps", "看到有居民要过斑马线，把下面几步排好顺序",
               ["松开油门减速", "在停止线前停稳", "等居民走到对面", "确认安全再起步"], "先减速，再停稳，等居民走完，确认安全后再走。", "减速、停稳、等、再走。"),
    ),
    "signals": (
        _choice("s1.sig.1", "signals", "signal_flash", "黄灯一直在闪，表示？", ["赶紧加速通过", "注意观察，确认安全后通过", "必须掉头"], 1,
                "黄灯闪烁是提醒：注意观察，确认安全再通过。", "黄灯闪，多看看。"),
        _choice("s1.sig.2", "signals", "signal_green_walker", "绿灯亮了，但斑马线上还有居民没走完，应该？", ["等居民走完再走", "按喇叭催一下", "从居民旁边绕过去"], 0,
                "绿灯也要先让正在过马路的居民走完。", "绿灯也要先让行人。"),
        _match("s1.sig.3", "signals", "signal_board", "把信号灯的颜色和它的意思对上", [("红灯", "停下来等待"), ("黄灯", "准备停下"), ("绿灯", "确认安全后通过")],
               "红灯停、黄灯准备停、绿灯也要确认安全再走。", "红停、黄等、绿看清再走。"),
    ),
    "emergency": (
        _choice("s1.emg.1", "emergency", "ambulance_behind", "星球救护车鸣着笛从后面开来，应该？", ["安全地靠边，让它先过", "加速离开", "原地不动"], 0,
                "救护车在执行任务，要安全地靠边让它先过。", "救护车来了要让路。"),
        _choice("s1.emg.2", "emergency", "firetruck_junction", "路口是绿灯，但消防车鸣着笛从侧面开来，应该？", ["绿灯我先走", "停下来，让消防车先过", "跟在消防车后面开"], 1,
                "消防车执行任务时优先通行，绿灯也要先让它。", "消防车优先。"),
        _order("s1.emg.3", "emergency", "ambulance_steps", "救护车从后面开来，把让路的步骤排好顺序",
               ["看后视镜确认右侧安全", "打右转灯示意", "慢慢靠边停下", "等救护车过去再出发"], "先看后方，再打灯，然后靠边停，等它过去再走。", "看镜子、打灯、靠边、等它过去。"),
    ),
    "pre_drive": (
        _order("s1.pre.1", "pre_drive", "car_check", "准备出发前，把下面几步排好顺序", ["绕车看一圈", "坐好系上安全带", "调好后视镜", "观察周围再起步"],
               "先看看车周围，再系安全带、调镜子，最后观察周围再起步。", "绕车、系带、调镜、观察，再出发。"),
        _choice("s1.pre.2", "pre_drive", "seatbelt", "什么时候系安全带？", ["车子动之前就系好", "上了快速路再系", "被提醒了再系"], 0,
                "车子动之前就要系好安全带。", "先系好安全带再出发。"),
        _choice("s1.pre.3", "pre_drive", "mirror_check", "出发前发现后视镜歪了，应该？", ["先调好镜子再出发", "开着车顺手调", "不用管，回头看就行"], 0,
                "镜子要在出发前调好，开车时不分心。", "镜子出发前调好。"),
    ),
    "parking_zone": (
        _choice("s1.park.1", "parking_zone", "no_parking", "路边画着黄色网格，还立着“禁止停车”的牌子，应该？", ["去画好的车位停", "停一会儿就走没关系", "打开双闪就能停"], 0,
                "禁止停车的地方不能停，去画好的车位停。", "禁停的地方一会儿也不停。"),
        _match("s1.park.2", "parking_zone", "parking_board", "把车停到合适的地方", [("送菜的小车", "食堂门口的装卸区"), ("来吃饭的小车", "停车场的空车位")],
               "装卸区留给送货的车，来吃饭的车停到停车场。", "送货停装卸区，吃饭停停车场。"),
        _choice("s1.park.3", "parking_zone", "accessible_bay", "停车位上画着小轮椅，表示？", ["留给行动不方便的居民，其他车不要停", "谁先到谁停", "只能停自行车"], 0,
                "画着小轮椅的车位是专门留给行动不方便的居民的。", "小轮椅车位要留出来。"),
    ),
    "slow_zone": (
        _choice("s1.slow.1", "slow_zone", "school_gate", "放学时经过小学门口，应该？", ["慢慢开，随时准备停下", "按喇叭让小朋友让开", "赶紧加速开过去"], 0,
                "放学时学校门口人多，慢慢开，随时准备停。", "学校门口，慢慢开。"),
        _choice("s1.slow.2", "slow_zone", "speed_sign", "路边的圆牌上写着“30”，表示？", ["最高速度不超过 30", "最低要开到 30", "前方 30 米有路口"], 0,
                "白底红圈里的数字是限速：不能超过这个速度。", "写着 30，就不超过 30。"),
        _choice("s1.slow.3", "slow_zone", "narrow_street", "小区里的路很窄，两边都有居民在散步，应该？", ["低速慢行，给居民留出空间", "开快点早点出去", "开远光灯提醒他们"], 0,
                "居民散步的地方要低速慢行，留出空间。", "有人散步就慢慢开。"),
    ),
    "reverse_safety": (
        _order("s1.rev.1", "reverse_safety", "reverse_check", "准备倒车离开车位，把几步排好顺序", ["看后视镜和四周", "确认后面没有居民", "挂上倒挡", "慢慢倒车"],
               "倒车前先看镜子和四周，确认没人再挂倒挡，慢慢倒。", "先看、再确认、再挂挡、慢慢倒。"),
        _choice("s1.rev.2", "reverse_safety", "reverse_puppy", "倒车时后面突然有只小狗跑过，应该？", ["马上停下，等它走开", "按喇叭赶它", "加快一点倒完"], 0,
                "倒车时有居民经过，马上停下，等它走开。", "后面有人就停。"),
        _choice("s1.rev.3", "reverse_safety", "reverse_park", "倒车入库时，应该怎样观察？", ["左右后视镜轮流看，留意车尾和边线", "只看一边就够了", "闭上眼睛凭感觉"], 0,
                "左右镜子轮流看，才能同时照顾车尾和两边的线。", "两边的镜子都要看。"),
    ),
}


def _step(qid, slot, scenario, title, story, scene, prompt, options, answer, explanation, pet_line):
    opts = tuple((f"{qid}.{chr(97 + i)}", text) for i, text in enumerate(options))
    return Quiz(qid, "s4", slot, "choice", scene, prompt, opts, opts[answer][0], explanation, pet_line, group=scenario, group_title=title, story=story)


def _scenario(sid, slot, title, story, scene, first, second):
    return (_step(f"{sid}.1", slot, sid, title, story, scene, *first), _step(f"{sid}.2", slot, sid, title, story, scene, *second))


S4_SLOTS = ("drowsy", "weather", "video_invite", "reversing", "dropped_item")
S4_BANK: dict[str, tuple[tuple[Quiz, Quiz], ...]] = {
    "drowsy": (
        _scenario("s4.drowsy.1", "drowsy", "路上困了", ("开了两个小时，TA 打了个大大的哈欠，眼皮直打架。",), "drowsy_road",
                  ("现在要不要继续赶路？", ["再坚持一下就到了", "找安全的地方停下来休息", "开窗吹吹风继续开"], 1, "困了硬撑很危险，要找安全的地方停下来休息。", "困了就停下来歇一歇。"),
                  ("前面两公里有服务区，也有一块路边空地，怎么安排休息？", ["开到服务区停好车，休息二十分钟再走", "在路边空地随便停下眯一会儿", "边开边闭眼休息一下"], 0,
                   "服务区有车位和休息的地方，比路边安全。", "去服务区好好休息。")),
        _scenario("s4.drowsy.2", "drowsy", "夜里还想赶路", ("天黑了，TA 还想连夜开到海边。",), "night_road",
                  ("今晚要不要硬撑着开到？", ["喝杯咖啡硬撑", "今晚先住下，休息好了明早再走", "开远光灯提提神"], 1, "夜里又困又黑，先休息，明早再走更安全。", "晚上先睡一觉，明天再出发。"),
                  ("决定休息以后，下一步？", ["在路边随便停车过夜", "找有停车位的旅店，停好车再休息", "把车停在隧道口"], 1, "要把车停在正规的车位里再休息。", "车停好了才能安心睡。")),
    ),
    "weather": (
        _scenario("s4.weather.1", "weather", "前方下起大雨", ("开着开着，前面下起大雨，雨刷都快忙不过来了。",), "rain_road",
                  ("要怎样调整？", ["保持原来的速度", "降低车速，和前车拉开距离", "加速冲出雨区"], 1, "雨天路滑、看不清，要减速并拉开距离。", "下雨就慢一点，离前车远一点。"),
                  ("雨越下越大，前面几乎看不清了，怎么办？", ["开着双闪继续快开", "找安全的地方停下，等雨小一点再走", "紧跟前车的尾灯"], 1,
                   "看不清路时，找安全的地方停下等一等。", "看不清就先停下等等。")),
        _scenario("s4.weather.2", "weather", "山路起了大雾", ("山路上起了大雾，只能看清前面二十米。",), "fog_road",
                  ("还要按原来的速度走吗？", ["按原计划快点开", "放慢速度，必要时推迟行程", "关掉车灯省电"], 1, "雾天要慢，必要时推迟出发。", "起雾就放慢，不着急。"),
                  ("雾里开车，灯怎么开？", ["打开雾灯和近光灯，慢慢开", "开远光灯看得远", "不开灯"], 0, "雾里开远光反而更看不清，用雾灯和近光灯。", "雾天开雾灯和近光灯。")),
    ),
    "video_invite": (
        _scenario("s4.video.1", "video_invite", "手机收到视频邀请", ("正在开车，手机弹出：朋友邀请你一起看新上的动画片。",), "phone_invite",
                  ("要不要马上看？", ["马上点开", "先不看，专心开车", "看一眼再说"], 1, "开车时不看视频，专心看路。", "开车的时候不看视频。"),
                  ("那这条邀请怎么处理？", ["等停好车再回复", "一边开一边打字回复", "把视频放在方向盘上看"], 0, "停好车再回复，开车时不操作手机。", "停好车再回消息。")),
        _scenario("s4.video.2", "video_invite", "主人发来小视频", ("TA 正在开车，主人发来一段小视频想给 TA 看。",), "phone_video",
                  ("现在要不要看？", ["专心开车，先不看", "视频很短，看一下没关系", "把手机架起来边开边看"], 0, "再短的视频也会让眼睛离开路面。", "先专心开车，一会儿再看。"),
                  ("什么时候看合适？", ["到了目的地、停好车再看", "等红灯的时候看", "在快速路上看"], 0, "车停稳熄火后再看，才不会分心。", "到了地方停好车再看。")),
    ),
    "reversing": (
        _scenario("s4.reverse.1", "reversing", "从菜市场倒车出来", ("TA 要从菜市场的停车位倒车出来。",), "market_reverse",
                  ("挂倒挡之前，先做什么？", ["直接倒", "看后视镜和四周，确认后面没人", "按一下喇叭就行"], 1, "倒车前先观察，确认身后没有居民。", "倒车前先看后面。"),
                  ("倒到一半，发现一只小鸭子在车后面慢慢走，怎么办？", ["马上停下，等它走开", "按喇叭催它", "加快速度倒完"], 0, "有居民在后面就停下，等它走开再倒。", "小鸭子在后面，我就停下等。")),
        _scenario("s4.reverse.2", "reversing", "食堂门口倒车", ("在食堂门口倒车，旁边有居民推着小推车经过。",), "canteen_reverse",
                  ("倒车时车速怎么控制？", ["慢慢倒，随时能停下", "快点倒完，少挡路", "挂空挡溜着倒"], 0, "倒车要慢，才能随时停住。", "倒车就慢慢来。"),
                  ("推车的居民停在车后不动了，怎么办？", ["停车等待，必要时下车看看", "继续慢慢倒，它会让开", "按喇叭让它走开"], 0, "看不清后面时停车等待，必要时下车确认。", "它不动，我就等一等。")),
    ),
    "dropped_item": (
        _scenario("s4.drop.1", "dropped_item", "零食掉到脚边", ("开车时，TA 的零食袋掉到了脚边。",), "snack_drop",
                  ("要不要马上弯腰去捡？", ["马上弯腰去捡", "先不捡，专心开车", "用脚把它勾过来"], 1, "开车时弯腰捡东西会看不到路。", "零食先不捡，专心开车。"),
                  ("什么时候捡合适？", ["找安全的地方停好车再捡", "等红灯的时候弯腰去捡", "让车慢慢溜着捡"], 0, "停好车再捡，最安全。", "停好车再捡。")),
        _scenario("s4.drop.2", "dropped_item", "相框滑到座位下", ("副驾驶座上的小相框滑到了座位下面。",), "frame_drop",
                  ("现在怎么办？", ["伸手去够", "先不管，继续专心开车", "急刹车让它滑出来"], 1, "开车时不伸手去够东西，也不无故急刹。", "先专心开车。"),
                  ("之后怎么处理？", ["到下一个停车点停好车，把它放到安全的地方", "路上随时伸手去拿", "不管它，一直放在那"], 0,
                   "停好车后把东西放稳，避免它再滑动影响开车。", "停好车，把相框放稳。")),
    ),
}

ALL: dict[str, Quiz] = {q.question_id: q for bank in S1_BANK.values() for q in bank}
ALL.update({q.question_id: q for pair in S4_BANK.values() for scenario in pair for q in scenario})


QUIZ_KINDS = ("choice", "match", "order")


def _practice_paper(number: int) -> list[Quiz]:
    """科一练习卷：5 个不同知识点，**选择、拖放、排序三种题型每张至少一道**。

    为什么（6c2b 驾校巡检 2026-09-24）：旧规则前 4 次练习 20 题里拖放 0 道、排序 1 道，第一次正式卷却有拖放 1、排序 3——
    玩家第一次见到拖放界面就是在正式考试里。
    怎么抽：窗口每次挪 2 个知识点、每两次再多挪 1 个；缺哪种题型，就在卷里挑一个知识点换成它那一型的题
    （候选按练习次数轮换；不会把某一型仅有的一道换走）。这组参数是穷举选的：每张三型齐、知识点不重复，
    而且**任意连续 12 次练习必把 30 道题全练到**（从第 1 次起 11 次练全）——不会有题永远练不到。正式卷的抽法不变。
    """
    start = (2 * number + number // 2) % len(S1_TOPICS)
    topics = [S1_TOPICS[(start + i) % len(S1_TOPICS)] for i in range(5)]
    picks = [(2 * number + 2 * i) % len(S1_BANK[topic]) for i, topic in enumerate(topics)]
    for kind in QUIZ_KINDS:
        have = Counter(S1_BANK[topic][pick].kind for topic, pick in zip(topics, picks))
        if have[kind]:
            continue
        swaps = [(i, j) for i, topic in enumerate(topics) for j, quiz in enumerate(S1_BANK[topic])
                 if quiz.kind == kind and have[S1_BANK[topic][picks[i]].kind] > 1]
        if swaps:
            i, j = swaps[number % len(swaps)]
            picks[i] = j
    return [S1_BANK[topic][pick] for topic, pick in zip(topics, picks)]


def paper(subject: str, number: int, practice: bool = False) -> list[Quiz]:
    """一套卷：number 决定抽哪一组（正式卷＝(轮次-1)*2+第几次；练习＝第几次练习），补考与首次必然不同。"""
    if subject == "s1":
        if practice:
            return _practice_paper(number)
        return [S1_BANK[topic][(number + index) % 3] for index, topic in enumerate(S1_TOPICS)]
    return [q for index, slot in enumerate(S4_SLOTS) for q in S4_BANK[slot][(number + index) % 2]]


def correct(question: Quiz, answer: dict) -> bool:
    if question.kind == "choice":
        return answer.get("choice") == question.answer
    if question.kind == "order":
        return tuple(answer.get("order") or ()) == question.answer
    return dict(answer.get("matches") or {}) == question.answer


def correct_answer(question: Quiz) -> dict:
    if question.kind == "choice":
        return {"choice": question.answer}
    if question.kind == "order":
        return {"order": list(question.answer)}
    return {"matches": dict(question.answer)}


def valid(question: Quiz, answer: dict) -> bool:
    """作答的格式必须和题型、选项对得上（服务端校验，不只靠前端）。"""
    ids = {o[0] for o in question.options}
    if question.kind == "choice":
        return answer.get("choice") in ids and not answer.get("order") and not answer.get("matches")
    if question.kind == "order":
        order = answer.get("order") or []
        return sorted(order) == sorted(ids) and not answer.get("choice") and not answer.get("matches")
    matches = answer.get("matches") or {}
    return set(matches) <= {t[0] for t in question.targets} and set(matches.values()) <= ids and not answer.get("choice") and not answer.get("order")
