"""爪爪驾校的场地配置（服务端唯一来源；前端只按配置渲染与模拟）。

坐标单位是米，y 轴向上。所有多边形按逆时针排列；镜像变体把 x 取反并反转顶点顺序。
科二：倒车入库、侧方停车、弯道行驶（正式考试三项连考），外加两个入门练习场（直线倒车、转向与回正）。
科三：小城路线，从农场路口把一篮菜送到星球食堂。
数值是游戏调参的起点，不代表现实驾考标准。补考换一局同难度的变体（镜像，或者换红绿灯与路口的时机）。
"""

from __future__ import annotations

import math

TICK_HZ = 30
CAR = {"length": 3.8, "width": 1.7, "wheelbase": 2.4, "rear": 0.6, "front": 0.8, "steer_steps": 12, "steer_max_deg": 34.0}
TAN = [math.tan(math.radians(i * CAR["steer_max_deg"] / CAR["steer_steps"])) for i in range(CAR["steer_steps"] + 1)]
COS_12 = math.cos(math.radians(12))
COS_45 = math.cos(math.radians(45))


def _per_tick(mps: float) -> float:
    return mps / TICK_HZ


def _per_tick2(mps2: float) -> float:
    return mps2 / (TICK_HZ * TICK_HZ)


TRAINING = {"vmax_f": _per_tick(1.6), "vmax_r": _per_tick(1.2), "accel": _per_tick2(0.8), "brake": _per_tick2(3.0), "coast": _per_tick2(0.6)}
TOWN = {"vmax_f": _per_tick(11.0), "vmax_r": _per_tick(1.5), "accel": _per_tick2(2.0), "brake": _per_tick2(6.0), "coast": _per_tick2(0.4)}
SCORING = {"line": 5, "cone": 10, "pass": 80}

FORMAL_ITEMS = {"s2": ("reverse_park", "side_park", "curve"), "s3": ("route",)}
PRACTICE_ITEMS = {"s2": ("reverse_straight", "reverse_turn", "reverse_park", "side_park", "curve"), "s3": ("route",)}
TITLES = {"reverse_straight": "直线倒车", "reverse_turn": "转向与回正", "reverse_park": "倒车入库", "side_park": "侧方停车", "curve": "弯道行驶",
          "route": "送菜到星球食堂"}
VARIANTS = ("a", "b")


def rect(x0: float, y0: float, x1: float, y1: float) -> list[list[float]]:
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


def line(line_id: str, a: tuple[float, float], b: tuple[float, float], kind: str = "line") -> dict:
    return {"id": line_id, "a": [a[0], a[1]], "b": [b[0], b[1]], "kind": kind}


def _base(item: str, variant: str, kind: str, seconds: int, physics: dict, start: tuple[float, float, float, float]) -> dict:
    return {"course_id": f"{item}.{variant}", "item": item, "variant": variant, "kind": kind, "title": TITLES[item], "tick_hz": TICK_HZ,
            "time_limit_ticks": seconds * TICK_HZ, "car": dict(CAR, tan=list(TAN)), "physics": dict(physics), "scoring": dict(SCORING),
            "start": {"x": start[0], "y": start[1], "hx": start[2], "hy": start[3], "gear": 1}, "lines": [], "cones": [], "bounds": [],
            "target": None, "route": None, "view": None, "decor": []}


def reverse_park(variant: str = "a", *, bay_width: float = 2.7, item: str = "reverse_park", seconds: int = 150) -> dict:
    """倒车入库：从左边开过车位，停在起始区，挂倒挡转向倒进车位，车头朝外停稳。"""
    half = bay_width / 2
    course = _base(item, "a", "park", seconds, TRAINING, (-11.0, 9.0, 1.0, 0.0))
    course["lines"] = [line("bay_left", (-half, 6.0), (-half, 0.8), "bay"), line("bay_right", (half, 6.0), (half, 0.8), "bay"),
                       line("bay_back", (-half, 0.8), (half, 0.8), "bay"), line("road_far", (-15.0, 12.0), (15.0, 12.0), "edge")]
    course["cones"] = [{"id": "cone_far_left", "x": -2.2, "y": 12.5, "r": 0.25}, {"id": "cone_far_right", "x": 2.2, "y": 12.5, "r": 0.25},
                       {"id": "cone_back", "x": 0.0, "y": 0.2, "r": 0.25}]
    course["bounds"] = [rect(-16.0, -1.5, 16.0, 15.0)]
    course["target"] = {"poly": rect(-half, 0.8, half, 6.0), "dir": [0.0, 1.0], "cos_tol": COS_12, "hold_ticks": 60}
    course["view"] = rect(-16.0, -1.5, 16.0, 15.0)
    course["decor"] = [{"type": "asphalt", "poly": rect(-15.0, 6.0, 15.0, 12.0)}, {"type": "asphalt", "poly": rect(-half, 0.8, half, 6.0)},
                       {"type": "paint", "a": [-15.0, 6.0], "b": [-half, 6.0], "dash": 1}, {"type": "paint", "a": [half, 6.0], "b": [15.0, 6.0], "dash": 1},
                       {"type": "zone", "poly": rect(2.8, 7.6, 5.2, 10.4), "label": "起始区", "practice_only": 1},
                       {"type": "tree", "x": -13.0, "y": 2.0, "r": 1.4}, {"type": "tree", "x": 12.5, "y": 2.5, "r": 1.6}, {"type": "tree", "x": 8.0, "y": 14.0, "r": 1.1},
                       {"type": "coach", "x": -13.5, "y": 13.3}, {"type": "sign", "x": -4.0, "y": 3.2, "label": "倒车入库"}]
    return mirror(course) if variant == "b" else course


def side_park(variant: str = "a", *, seconds: int = 150) -> dict:
    """侧方停车：沿路开过车位，倒车把车身摆进路边车位，调正后停稳。"""
    course = _base("side_park", "a", "park", seconds, TRAINING, (-11.0, 5.2, 1.0, 0.0))
    course["lines"] = [line("bay_front", (3.5, 0.0), (3.5, 2.5), "bay"), line("bay_rear", (-3.5, 0.0), (-3.5, 2.5), "bay"),
                       line("curb", (-15.0, 0.0), (15.0, 0.0), "curb"), line("road_far", (-15.0, 8.5), (15.0, 8.5), "edge")]
    course["cones"] = [{"id": "cone_front", "x": 3.9, "y": 2.9, "r": 0.25}, {"id": "cone_rear", "x": -3.9, "y": 2.9, "r": 0.25}]
    course["bounds"] = [rect(-16.0, -2.5, 16.0, 11.0)]
    course["target"] = {"poly": rect(-3.5, 0.0, 3.5, 2.5), "dir": [1.0, 0.0], "cos_tol": COS_12, "hold_ticks": 60}
    course["view"] = rect(-16.0, -2.5, 16.0, 11.0)
    course["decor"] = [{"type": "sidewalk", "poly": rect(-15.0, -2.5, 15.0, 0.0)}, {"type": "asphalt", "poly": rect(-15.0, 0.0, 15.0, 8.5)},
                       {"type": "paint", "a": [-3.5, 2.5], "b": [3.5, 2.5], "dash": 1},
                       {"type": "zone", "poly": rect(5.2, 3.4, 8.8, 7.0), "label": "起始区", "practice_only": 1},
                       {"type": "tree", "x": -12.0, "y": -1.3, "r": 1.0}, {"type": "tree", "x": 11.0, "y": -1.3, "r": 1.0},
                       {"type": "coach", "x": -14.2, "y": 9.6}, {"type": "sign", "x": 0.0, "y": -1.4, "label": "侧方停车"}]
    return mirror(course) if variant == "b" else course


def _arc(cx: float, cy: float, r: float, a0: float, a1: float, n: int) -> list[tuple[float, float]]:
    return [(cx + r * math.cos(math.radians(a0 + (a1 - a0) * i / n)), cy + r * math.sin(math.radians(a0 + (a1 - a0) * i / n))) for i in range(n + 1)]


def _edge(points: list[tuple[float, float]], name: str, kind: str = "edge") -> list[dict]:
    return [line(f"{name}_{i}", points[i], points[i + 1], kind) for i in range(len(points) - 1)]


def curve(variant: str = "a", *, seconds: int = 120) -> dict:
    """弯道行驶：一段先右后左的 S 弯，车道宽 3.4 米，开到终点区停稳。"""
    half, radius = 1.7, 8.0
    course = _base("curve", "a", "curve", seconds, TRAINING, (0.0, -0.8, 0.0, 1.0))
    left = [(-half, -3.0), (-half, 6.0)] + _arc(radius, 6.0, radius + half, 180, 90, 12)[1:] + _arc(radius, 22.0, radius - half, 270, 360, 12)[1:] + [(2 * radius - half, 31.0)]
    right = [(half, -3.0), (half, 6.0)] + _arc(radius, 6.0, radius - half, 180, 90, 12)[1:] + _arc(radius, 22.0, radius + half, 270, 360, 12)[1:] + [(2 * radius + half, 31.0)]
    course["lines"] = _edge(left, "left") + _edge(right, "right")
    course["bounds"] = [rect(-7.0, -5.0, 23.0, 34.0)]
    course["target"] = {"poly": rect(2 * radius - half, 24.0, 2 * radius + half, 30.5), "dir": [0.0, 1.0], "cos_tol": COS_12, "hold_ticks": 30}
    course["view"] = rect(-7.0, -5.0, 23.0, 34.0)
    course["decor"] = [{"type": "lane", "left": [list(p) for p in left], "right": [list(p) for p in right]},
                       {"type": "zone", "poly": rect(2 * radius - half, 24.0, 2 * radius + half, 30.5), "label": "终点区"},
                       {"type": "tree", "x": 7.0, "y": 11.0, "r": 1.6}, {"type": "tree", "x": 10.0, "y": 17.5, "r": 1.3}, {"type": "tree", "x": -4.5, "y": 20.0, "r": 1.8},
                       {"type": "tree", "x": 20.0, "y": 6.0, "r": 1.5}, {"type": "coach", "x": -4.8, "y": -3.2}, {"type": "sign", "x": -4.0, "y": 3.0, "label": "弯道行驶"}]
    return mirror(course) if variant == "b" else course


def reverse_straight(variant: str = "a") -> dict:
    """入门练习：挂倒挡，沿直线慢慢倒进身后的长车位。"""
    course = _base("reverse_straight", "a", "park", 120, TRAINING, (0.0, 10.0, 0.0, 1.0))
    course["lines"] = [line("left", (-1.6, 1.0), (-1.6, 14.0), "bay"), line("right", (1.6, 1.0), (1.6, 14.0), "bay"), line("back", (-1.6, 1.0), (1.6, 1.0), "bay")]
    course["bounds"] = [rect(-8.0, -1.5, 8.0, 17.0)]
    course["target"] = {"poly": rect(-1.6, 1.0, 1.6, 6.5), "dir": [0.0, 1.0], "cos_tol": COS_12, "hold_ticks": 60}
    course["view"] = rect(-8.0, -1.5, 8.0, 17.0)
    course["decor"] = [{"type": "asphalt", "poly": rect(-1.6, 1.0, 1.6, 14.0)}, {"type": "zone", "poly": rect(-1.6, 1.0, 1.6, 6.5), "label": "停在这里"},
                       {"type": "tree", "x": -5.5, "y": 4.0, "r": 1.3}, {"type": "coach", "x": 5.2, "y": 12.5}]
    return course


def reverse_turn(variant: str = "a") -> dict:
    """入门练习：宽车位的倒车入库，先熟悉转向与回正。"""
    return reverse_park(variant, bay_width=4.0, item="reverse_turn", seconds=180)


def route(variant: str = "a", *, seconds: int = 360) -> dict:
    """科三：小城路线。从农场路口出发，向东经过停车让行路口、人行横道、红绿灯，在 T 字路口右转，把菜送到星球食堂装卸区。"""
    course = _base("route", variant, "route", seconds, TOWN, (2.0, 1.4, 1.0, 0.0))
    offset, trigger_x, invite_x = (150, 85.0, 130.0) if variant == "a" else (480, 88.0, 136.0)
    south = [(-5.0, 60.0), (68.0, 160.0), (168.0, 200.0)]
    north = [(-5.0, 60.0), (68.0, 160.0), (168.0, 212.0)]
    corner = _arc(200.0, -4.0, 4.0, 90, 0, 6)  # 路口转角是圆角路沿（半径 4 米）
    course["lines"] = ([line(f"curb_s_{i}", (a, 0.0), (b, 0.0), "curb") for i, (a, b) in enumerate(south)]
                       + [line(f"curb_n_{i}", (a, 8.0), (b, 8.0), "curb") for i, (a, b) in enumerate(north)]
                       + [line(f"center_{i}", (a, 4.0), (b if b < 204.0 else 204.0, 4.0), "center") for i, (a, b) in enumerate([(-5.0, 60.0), (68.0, 160.0), (168.0, 204.0)])]
                       + _edge(corner, "curb_corner", "curb")
                       + [line("curb_w", (204.0, -4.0), (204.0, -70.0), "curb"), line("curb_e", (212.0, 8.0), (212.0, -70.0), "curb"),
                          line("center_s", (208.0, 0.0), (208.0, -70.0), "center")]
                       + [line(f"barrier_{x0}_{side}", (x0, y), (x0 + 8.0, y), "barrier") for x0 in (60.0, 160.0) for side, y in (("n", 13.0), ("s", -5.0))])
    course["bounds"] = [rect(-6.0, -3.0, 212.0, 11.0), rect(201.0, -74.0, 215.0, 11.0), rect(60.0, -6.0, 68.0, 14.0), rect(160.0, -6.0, 168.0, 14.0)]
    course["target"] = {"poly": rect(204.0, -56.0, 206.6, -49.0), "dir": [0.0, -1.0], "cos_tol": COS_12, "hold_ticks": 60}
    course["route"] = {
        "precheck_steps": 3, "start_signal": -1, "speed_limit": _per_tick(30 / 3.6), "speed_tol": _per_tick(0.5 / 3.6),
        "points": {"precheck": 10, "start_signal": 5, "stop": 10, "turn": 10, "speeding": 5, "invite": 10},
        "stop": {"line": [[58.5, 0.0], [58.5, 4.0]], "zone": rect(53.5, 0.0, 58.5, 4.0), "sign": [57.5, -1.2]},
        "crosswalk": {"poly": rect(108.0, 0.0, 112.0, 8.0), "trigger": [[trigger_x, 0.0], [trigger_x, 8.0]],
                      "walker": {"from": [110.0, 9.6], "to": [110.0, -1.6], "ticks": round(11.2 / _per_tick(1.1)), "kind": "rabbit"}},
        "light": {"line": [[158.5, 0.0], [158.5, 4.0]], "cycle": [300, 90, 330], "offset": offset, "pos": [158.0, -1.6]},
        "invite": {"trigger": [[invite_x, 0.0], [invite_x, 8.0]], "window_ticks": 240},
        "turn": {"zone": rect(192.0, -10.0, 212.0, 8.0), "dir": [1.0, 0.0], "cos": COS_45, "side": 1},
        "instructions": [{"zone": rect(-6.0, -3.0, 40.0, 11.0), "text": "系好安全带、调好后视镜、看看四周，打左转灯起步"},
                         {"zone": rect(40.0, -3.0, 62.0, 11.0), "text": "前方停车让行路口，在停止线前停稳"},
                         {"zone": rect(62.0, -3.0, 114.0, 11.0), "text": "前方人行横道，注意过街的居民"},
                         {"zone": rect(114.0, -3.0, 172.0, 11.0), "text": "前方红绿灯路口"},
                         {"zone": rect(172.0, -3.0, 215.0, 11.0), "text": "前方路口右转"},
                         {"zone": rect(201.0, -74.0, 215.0, -3.0), "text": "到星球食堂门口靠边停车"}],
    }
    course["view"] = rect(-6.0, -74.0, 215.0, 14.0)
    course["decor"] = _town_decor()
    return course


def _town_decor() -> list[dict]:
    fillet = [[200.0, 0.0]] + [[x, y] for x, y in _arc(200.0, -4.0, 4.0, 90, 0, 6)[1:]] + [[204.0, 0.0]]
    decor: list[dict] = [{"type": "sidewalk", "poly": rect(-6.0, -3.0, 204.0, 0.0)}, {"type": "sidewalk", "poly": rect(-6.0, 8.0, 212.0, 11.0)},
                         {"type": "sidewalk", "poly": rect(201.0, -74.0, 204.0, 0.0)}, {"type": "sidewalk", "poly": rect(212.0, -74.0, 215.0, 8.0)},
                         {"type": "asphalt", "poly": rect(-5.0, 0.0, 212.0, 8.0)}, {"type": "asphalt", "poly": rect(204.0, -72.0, 212.0, 8.0)},
                         {"type": "asphalt", "poly": fillet},
                         {"type": "asphalt", "poly": rect(60.0, -6.0, 68.0, 14.0)}, {"type": "asphalt", "poly": rect(160.0, -6.0, 168.0, 14.0)},
                         {"type": "crosswalk", "poly": rect(108.0, 0.0, 112.0, 8.0)}, {"type": "zone", "poly": rect(204.0, -56.0, 206.6, -49.0), "label": "装卸区"},
                         {"type": "stopline", "a": [58.5, 0.0], "b": [58.5, 4.0]}, {"type": "stopline", "a": [158.5, 0.0], "b": [158.5, 4.0]},
                         {"type": "arrow", "x": 186.0, "y": 2.0, "dir": "right"},
                         {"type": "sign", "x": 57.5, "y": -1.2, "kind": "stop", "label": "停"}, {"type": "sign", "x": 30.0, "y": -1.4, "kind": "speed", "label": "30"},
                         {"type": "sign", "x": 104.0, "y": -1.4, "kind": "crossing", "label": "人行横道"}, {"type": "sign", "x": 206.0, "y": -20.0, "kind": "speed", "label": "30"}]
    for x0 in (60.0, 160.0):
        decor += [{"type": "barrier", "a": [x0, 13.0], "b": [x0 + 8.0, 13.0]}, {"type": "barrier", "a": [x0, -5.0], "b": [x0 + 8.0, -5.0]}]
    buildings = [(-4.0, 12.0, 14.0, 22.0, "农场路口", "farm"), (20.0, 12.5, 40.0, 24.0, None, "house"), (72.0, 12.5, 96.0, 26.0, "邮局", "post"),
                 (120.0, 12.5, 140.0, 22.0, None, "house"), (172.0, 12.5, 200.0, 24.0, None, "house"), (-4.0, -16.0, 20.0, -4.0, None, "barn"),
                 (26.0, -15.0, 52.0, -4.0, None, "house"), (72.0, -14.0, 100.0, -4.0, None, "house"), (118.0, -15.0, 150.0, -4.0, "小学", "school"),
                 (172.0, -16.0, 198.0, -4.0, None, "house"), (216.0, -40.0, 232.0, 6.0, None, "house"), (184.0, -62.0, 200.0, -44.0, "星球食堂", "canteen"),
                 (184.0, -38.0, 200.0, -20.0, None, "house")]
    decor += [{"type": "building", "poly": rect(x0, y0, x1, y1), "label": label, "style": style} for x0, y0, x1, y1, label, style in buildings]
    decor += [{"type": "tree", "x": x, "y": y, "r": r} for x, y, r in ((16.0, 9.8, 1.2), (48.0, 9.9, 1.2), (86.0, -1.8, 1.0), (140.0, 9.8, 1.1),
                                                                         (190.0, -1.9, 1.0), (213.5, -30.0, 1.0), (202.5, -30.0, 0.9))]
    decor += [{"type": "resident", "x": 45.0, "y": 9.6, "kind": "penguin"}, {"type": "resident", "x": 199.0, "y": -52.0, "kind": "bear"},
              {"type": "bus_stop", "x": 132.0, "y": 9.4}]
    return decor


def mirror(course: dict) -> dict:
    """左右镜像（x 取反、多边形顶点反序以保持逆时针）；难度不变。"""

    def neg(v):
        return -v if v != 0 else 0.0

    def pt(p):
        return [neg(p[0]), p[1]]

    def poly(ps):
        return [pt(p) for p in reversed(ps)]

    out = dict(course, variant="b", course_id=f"{course['item']}.b")
    out["start"] = dict(course["start"], x=neg(course["start"]["x"]), hx=neg(course["start"]["hx"]))
    out["lines"] = [dict(ln, a=pt(ln["a"]), b=pt(ln["b"])) for ln in course["lines"]]
    out["cones"] = [dict(c, x=neg(c["x"])) for c in course["cones"]]
    out["bounds"] = [poly(b) for b in course["bounds"]]
    out["view"] = poly(course["view"])
    if course["target"]:
        out["target"] = dict(course["target"], poly=poly(course["target"]["poly"]), dir=[neg(course["target"]["dir"][0]), course["target"]["dir"][1]])
    decor = []
    for d in course["decor"]:
        m = dict(d)
        if "poly" in d:
            m["poly"] = poly(d["poly"])
        if "x" in d:
            m["x"] = neg(d["x"])
        for key in ("a", "b"):
            if key in d:
                m[key] = pt(d[key])
        for key in ("left", "right"):
            if key in d:
                m["right" if key == "left" else "left"] = [pt(p) for p in d[key]]
        decor.append(m)
    out["decor"] = decor
    return out


BUILDERS = {"reverse_park": reverse_park, "side_park": side_park, "curve": curve, "reverse_straight": reverse_straight, "reverse_turn": reverse_turn,
            "route": route}


def course_for(item: str, variant: str) -> dict:
    return BUILDERS[item](variant)
