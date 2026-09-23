"""爪爪驾校的操作复算：按 tick 应用操作事件、推进车辆、判定扣分、失败与完成（规格见 DRIVING-SCHOOL-v1 §4）。

服务端用它逐段复算前端上传的操作记录，前端 `sim/replay.ts` 用同一套逻辑实时驾驶，两边逐行对应。
状态可以序列化成快照（JSON），下一段操作从快照接着算，不必从头复算。

事件 {t, k, ref, p, f}：t＝发生的 tick，k＝种类，ref＝相关的线或锥桶，p＝扣分，f＝1 表示红线或失败（本项立即结束）。
"""

from __future__ import annotations

from .sim import Car, bbox, body_of, boxes_overlap, circle_hits_poly, corners, front_mid, inside_convex, physics_of, segment_hits_poly, segments_cross, step

CODES = ("s", "t", "b", "g", "k", "c", "v")
MAX_CHUNK_TICKS = 900
MAX_CHUNK_EVENTS = 2000


class InputError(ValueError):
    """上传的操作记录不合规（越界的 tick、未知操作、超范围的值）。"""


def validate(events: list[dict], from_tick: int, upto_tick: int, steps: int) -> list[dict]:
    if upto_tick < from_tick or upto_tick - from_tick > MAX_CHUNK_TICKS:
        raise InputError("一段操作最多 30 秒")
    if len(events) > MAX_CHUNK_EVENTS:
        raise InputError("操作记录过多")
    last = from_tick
    clean = []
    for event in events:
        t, c, v = event.get("t"), event.get("c"), event.get("v")
        if not isinstance(t, int) or not isinstance(v, int) or isinstance(t, bool) or isinstance(v, bool) or c not in CODES:
            raise InputError("操作记录格式不对")
        if t < last or t >= upto_tick:
            raise InputError("操作记录的时间不连续")
        ok = {"s": -steps <= v <= steps, "t": v in (0, 1), "b": v in (0, 1), "g": v in (-1, 1), "k": -1 <= v <= 1, "c": 1 <= v <= 3, "v": v in (0, 1)}[c]
        if not ok:
            raise InputError("操作的数值超出范围")
        last = t
        clean.append({"t": t, "c": c, "v": v})
    return clean


def light_phase(route: dict, tick: int) -> str:
    light = route["light"]
    green, yellow, red = light["cycle"]
    p = (tick + light["offset"]) % (green + yellow + red)
    if p < green:
        return "green"
    return "yellow" if p < green + yellow else "red"


def walker_at(route: dict, cw_tick: int | None, tick: int) -> tuple[float, float]:
    walker = route["crosswalk"]["walker"]
    fx, fy = walker["from"]
    if cw_tick is None:
        return fx, fy
    k = (tick - cw_tick) / walker["ticks"]
    if k > 1:
        k = 1.0
    tx, ty = walker["to"]
    return fx + (tx - fx) * k, fy + (ty - fy) * k


class Replay:
    def __init__(self, course: dict, snapshot: dict | None = None) -> None:
        self.course = course
        self.body = body_of(course)
        self.phys = physics_of(course)
        self.lines = [(line["id"], (line["a"][0], line["a"][1]), (line["b"][0], line["b"][1])) for line in course.get("lines", [])]
        self.line_boxes = [bbox([a, b]) for _, a, b in self.lines]
        self.cones = course.get("cones", [])
        self.bounds = [[(p[0], p[1]) for p in poly] for poly in course["bounds"]]
        self.target = course.get("target")
        self.route = course.get("route")
        self.points = course["scoring"]
        self.limit = course["time_limit_ticks"]
        state = snapshot or self.initial()
        car = state["car"]
        self.car = Car(car[0], car[1], car[2], car[3], car[4], car[5], car[6])
        self.steer, self.throttle, self.brake, self.blink = state["ctl"]
        self.tick = state["tick"]
        self.pressed = state["pressed"]
        self.knocked = list(state["knocked"])
        self.hold = state["hold"]
        self.status = state["status"]
        self.fail = state["fail"]
        self.events = list(state["events"])
        self.front = (state["front"][0], state["front"][1])
        self.r = dict(state["route"]) if state["route"] is not None else None

    def initial(self) -> dict:
        start = self.course["start"]
        car = Car(start["x"], start["y"], start["hx"], start["hy"], 0.0, 0, start["gear"])
        fm = front_mid(car, self.body)
        route = None
        if self.course.get("route"):
            route = {"checks": [], "moved": 0, "stop_ok": 0, "stop_done": 0, "cw_tick": None, "light_done": 0, "turned": 0, "invite_tick": None,
                     "invite_done": 0, "speeding": 0}
        return {"tick": 0, "car": [car.x, car.y, car.hx, car.hy, 0.0, 0, car.gear], "ctl": [0, 0, 0, 0], "pressed": 0, "knocked": [], "hold": 0,
                "status": "running", "fail": None, "events": [], "front": [fm[0], fm[1]], "route": route}

    def snapshot(self) -> dict:
        c = self.car
        return {"tick": self.tick, "car": [c.x, c.y, c.hx, c.hy, c.v, c.s, c.gear], "ctl": [self.steer, self.throttle, self.brake, self.blink],
                "pressed": self.pressed, "knocked": list(self.knocked), "hold": self.hold, "status": self.status, "fail": self.fail,
                "events": list(self.events), "front": [self.front[0], self.front[1]], "route": dict(self.r) if self.r is not None else None}

    @property
    def deducted(self) -> int:
        return sum(e["p"] for e in self.events)

    # ---- 推进 ----
    def apply(self, events: list[dict], upto_tick: int) -> list[dict]:
        """从当前 tick 推进到 upto_tick（不含）；events 已校验、按 tick 排序。返回新产生的判定事件。"""
        before = len(self.events)
        index = 0
        while self.tick < upto_tick and self.status == "running":
            tick = self.tick
            while index < len(events) and events[index]["t"] == tick:
                self._input(events[index]["c"], events[index]["v"], tick)
                index += 1
            step(self.car, self.steer, self.throttle, self.brake, self.body, self.phys)
            self._detect(tick)
            self.tick = tick + 1
        return self.events[before:]

    def _input(self, code: str, value: int, tick: int) -> None:
        if code == "s":
            self.steer = value
        elif code == "t":
            self.throttle = value
        elif code == "b":
            self.brake = value
        elif code == "g":
            if self.car.v == 0:
                self.car.gear = value
        elif code == "k":
            self.blink = value
        elif code == "c":
            if self.r is not None and value not in self.r["checks"]:
                self.r["checks"] = self.r["checks"] + [value]
        elif code == "v":
            r = self.r
            if r is not None and r["invite_tick"] is not None and not r["invite_done"] and tick >= r["invite_tick"]:
                r["invite_done"] = 1
                if value == 1:
                    self._add(tick, "invite_opened", None, self.route["points"]["invite"])

    def _add(self, tick: int, kind: str, ref: str | None, points: int, fatal: int = 0) -> None:
        self.events.append({"t": tick, "k": kind, "ref": ref, "p": points, "f": fatal})

    def _fail(self, tick: int, kind: str, ref: str | None = None) -> None:
        self._add(tick, kind, ref, 0, 1)
        self.status = "failed"
        self.fail = kind
        self.car.v = 0.0

    def _detect(self, tick: int) -> None:
        body = self.body
        poly = corners(self.car, body)
        box = bbox(poly)
        fm = front_mid(self.car, body)
        for cx, cy in poly:
            inside = False
            for area in self.bounds:
                if inside_convex(cx, cy, area):
                    inside = True
                    break
            if not inside:
                self._fail(tick, "out_of_bounds")
                return
        hit = None
        for index, (line_id, a, b) in enumerate(self.lines):
            if boxes_overlap(box, self.line_boxes[index]) and segment_hits_poly(a, b, poly):
                hit = line_id
                break
        if hit is not None and not self.pressed:
            self._add(tick, "line", hit, self.points["line"])
        self.pressed = 1 if hit is not None else 0
        for cone in self.cones:
            if cone["id"] not in self.knocked and circle_hits_poly(cone["x"], cone["y"], cone["r"], poly):
                self.knocked = self.knocked + [cone["id"]]
                self._add(tick, "cone", cone["id"], self.points["cone"])
        if self.r is not None:
            self._route(tick, poly, fm)
        if self.status != "running":
            return
        target = self.target
        if target is not None:
            placed = True
            for cx, cy in poly:
                if not inside_convex(cx, cy, target["poly"]):
                    placed = False
                    break
            aligned = self.car.hx * target["dir"][0] + self.car.hy * target["dir"][1] >= target["cos_tol"]
            self.hold = self.hold + 1 if placed and aligned and self.car.v == 0 else 0
            if self.hold >= target["hold_ticks"]:
                self._add(tick, "done", None, 0)
                self.status = "done"
                self.front = fm
                return
        if tick + 1 >= self.limit:
            self._fail(tick, "timeout")
        self.front = fm

    def _route(self, tick: int, poly: list, fm: tuple[float, float]) -> None:
        route, r, car, prev = self.route, self.r, self.car, self.front
        points = route["points"]
        if not r["moved"] and car.v != 0:
            r["moved"] = 1
            if len(r["checks"]) < route["precheck_steps"]:
                self._add(tick, "precheck_skipped", None, points["precheck"])
            if self.blink != route["start_signal"]:
                self._add(tick, "start_no_signal", None, points["start_signal"])
        stop = route["stop"]
        if not r["stop_done"]:
            if car.v == 0 and inside_convex(fm[0], fm[1], stop["zone"]):
                r["stop_ok"] = 1
            if car.v > 0 and segments_cross(prev, fm, stop["line"][0], stop["line"][1]):
                r["stop_done"] = 1
                if not r["stop_ok"]:
                    self._add(tick, "stop_rolled", None, points["stop"])
        crosswalk = route["crosswalk"]
        if r["cw_tick"] is None and segments_cross(prev, fm, crosswalk["trigger"][0], crosswalk["trigger"][1]):
            r["cw_tick"] = tick
        if r["cw_tick"] is not None and tick - r["cw_tick"] < crosswalk["walker"]["ticks"]:
            area = crosswalk["poly"]
            n = len(area)
            entered = False
            for cx, cy in poly:
                if inside_convex(cx, cy, area):
                    entered = True
                    break
            if not entered:
                for i in range(n):
                    if segment_hits_poly(area[i], area[(i + 1) % n], poly):
                        entered = True
                        break
            if entered:
                self._fail(tick, "crosswalk")
                return
        light = route["light"]
        if not r["light_done"] and car.v > 0 and segments_cross(prev, fm, light["line"][0], light["line"][1]):
            r["light_done"] = 1
            if light_phase(route, tick) == "red":
                self._fail(tick, "red_light")
                return
        invite = route["invite"]
        if r["invite_tick"] is None:
            if segments_cross(prev, fm, invite["trigger"][0], invite["trigger"][1]):
                r["invite_tick"] = tick
                self._add(tick, "invite_shown", None, 0)
        elif not r["invite_done"] and tick - r["invite_tick"] >= invite["window_ticks"]:
            r["invite_done"] = 1
        turn = route["turn"]
        if not r["turned"] and inside_convex(fm[0], fm[1], turn["zone"]) and car.hx * turn["dir"][0] + car.hy * turn["dir"][1] < turn["cos"]:
            r["turned"] = 1
            if self.blink != turn["side"]:
                self._add(tick, "turn_no_signal", None, points["turn"])
        speed = car.v if car.v > 0 else -car.v
        if not r["speeding"] and speed > route["speed_limit"] + route["speed_tol"]:
            r["speeding"] = 1
            self._add(tick, "speeding", None, points["speeding"])
        elif r["speeding"] and speed <= route["speed_limit"]:
            r["speeding"] = 0
