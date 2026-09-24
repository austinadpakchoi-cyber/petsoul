"""测试用“驾驶员”：按车辆当前状态决定操作，产出一份真实的操作记录（和人一样只能通过操作影响结果）。

只用于测试与生成跨语言样例（scripts/gen_driving_fixtures.py），不进入产品代码。
"""

from __future__ import annotations

import math

from app.web_driving.replay import Replay, light_phase
from app.web_driving.sim import front_mid


class Driver:
    def __init__(self, course: dict) -> None:
        self.course = course
        self.replay = Replay(course)
        self.events: list[dict] = []
        self.ctl = {"s": 0, "t": 0, "b": 0, "k": 0}
        self.tick = 0

    def set(self, code: str, value: int) -> None:
        if code in self.ctl:
            if self.ctl[code] == value:
                return
            self.ctl[code] = value
        self.events.append({"t": self.tick, "c": code, "v": value})

    def run(self, controller, max_ticks: int | None = None) -> "Driver":
        limit = max_ticks or self.course["time_limit_ticks"]
        state: dict = {"phase": 0}
        while self.replay.status == "running" and self.tick < limit:
            before = len(self.events)
            controller(self, state)
            self.replay.apply(self.events[before:], self.tick + 1)
            self.tick += 1
        return self


def reverse_park_bot(x_stop: float = 2.8, y_stop: float = 2.0, sign: int = 1):
    """开过车位 → 停稳 → 挂倒挡满舵倒车 → 车身摆正后回正 → 倒到位停稳。sign=-1 用于镜像场地。"""

    def control(d: Driver, st: dict) -> None:
        car = d.replay.car
        if st["phase"] == 0:
            d.set("t", 1)
            if car.x * sign >= x_stop:
                d.set("t", 0)
                d.set("b", 1)
                st["phase"] = 1
        elif st["phase"] == 1 and car.v == 0:
            d.set("b", 0)
            d.set("g", -1)
            d.set("s", -12 * sign)
            d.set("t", 1)
            st["phase"] = 2
        elif st["phase"] == 2 and car.hy >= 0.9995:
            d.set("s", 0)
            st["phase"] = 3
        elif st["phase"] == 3 and car.y <= y_stop:
            d.set("t", 0)
            d.set("b", 1)
            st["phase"] = 4

    return control


def side_park_bot(x_stop: float, turn_hy: float, sign: int = 1):
    """侧方停车：开过车位 → 停稳 → 挂倒挡满舵倒车 → 车身斜到一定角度后反打满舵 → 摆正后停稳。"""

    def control(d: Driver, st: dict) -> None:
        car = d.replay.car
        if st["phase"] == 0:
            d.set("t", 1)
            if car.x * sign >= x_stop:
                d.set("t", 0)
                d.set("b", 1)
                st["phase"] = 1
        elif st["phase"] == 1 and car.v == 0:
            d.set("b", 0)
            d.set("g", -1)
            d.set("s", -12 * sign)
            d.set("t", 1)
            st["phase"] = 2
        elif st["phase"] == 2 and car.hy >= turn_hy:
            d.set("s", 12 * sign)
            st["phase"] = 3
        elif st["phase"] == 3 and car.hy <= 0.004:
            d.set("s", 0)
            d.set("t", 0)
            d.set("b", 1)
            st["phase"] = 4

    return control


def _pursuit(d: Driver, path: list[tuple[float, float]], look: float) -> None:
    """纯追踪：朝前方 look 米处的路径点打方向（取最接近的档位）。"""
    car, body = d.replay.car, d.replay.body
    best, best_i = None, 0
    for i, (px, py) in enumerate(path):
        dist = (px - car.x) ** 2 + (py - car.y) ** 2
        if best is None or dist < best:
            best, best_i = dist, i
    target = path[-1]
    for px, py in path[best_i:]:
        if (px - car.x) ** 2 + (py - car.y) ** 2 >= look * look:
            target = (px, py)
            break
    dx, dy = target[0] - car.x, target[1] - car.y
    local_y = -car.hy * dx + car.hx * dy
    dist2 = dx * dx + dy * dy
    curvature = 2 * local_y / dist2 if dist2 > 0 else 0.0
    want = curvature * body.wheelbase
    index = min(range(-body.steps, body.steps + 1), key=lambda i: abs((body.tan[i] if i >= 0 else -body.tan[-i]) - want))
    d.set("s", index)


def _dense(points: list[tuple[float, float]], step: float = 0.5) -> list[tuple[float, float]]:
    out = [points[0]]
    for (ax, ay), (bx, by) in zip(points, points[1:]):
        length = math.hypot(bx - ax, by - ay)
        n = max(1, int(length / step))
        out += [(ax + (bx - ax) * i / n, ay + (by - ay) * i / n) for i in range(1, n + 1)]
    return out


def curve_bot(sign: int = 1):
    """弯道：沿车道中心线纯追踪，保持低速，进入终点区后刹停。"""
    center = [(0.0, -3.0), (0.0, 6.0)]
    center += [(8.0 + 8.0 * math.cos(math.radians(180 - 90 * i / 24)), 6.0 + 8.0 * math.sin(math.radians(180 - 90 * i / 24))) for i in range(1, 25)]
    center += [(8.0 + 8.0 * math.cos(math.radians(270 + 90 * i / 24)), 22.0 + 8.0 * math.sin(math.radians(270 + 90 * i / 24))) for i in range(1, 25)]
    center += [(16.0, 31.0)]
    path = _dense([(x * sign, y) for x, y in center])

    def control(d: Driver, st: dict) -> None:
        car = d.replay.car
        if st["phase"] == 0:
            _pursuit(d, path, 3.0)
            d.set("t", 1 if car.v < 1.1 / 30 else 0)
            if car.y >= 26.2:
                d.set("t", 0)
                d.set("b", 1)
                st["phase"] = 1

    return control


_TURN = [(200.0 + 6.0 * math.cos(math.radians(90 - 90 * i / 12)), -4.0 + 6.0 * math.sin(math.radians(90 - 90 * i / 12))) for i in range(13)]
ROUTE_PATH = _dense([(4.0, 1.4), (14.0, 2.0)] + _TURN + [(206.0, -44.0), (205.3, -48.0), (205.3, -60.0)], 0.5)


def route_bot(obey: bool = True, signals: bool = True, invite_open: bool = False, checks: bool = True):
    """科三：检查三项、打左转灯起步；停车让行；等过街的居民；看红绿灯；打右转灯右转；到装卸区靠边停。obey=False 会闯红灯。"""

    def control(d: Driver, st: dict) -> None:
        rp = d.replay
        car, route, r = rp.car, rp.route, rp.r
        fm = front_mid(car, rp.body)
        tick = d.tick
        if st["phase"] == 0:
            if checks and tick < 3:
                d.set("c", tick + 1)
                return
            if signals:
                d.set("k", -1)
            st["phase"] = 1
            return
        target = 7.0 / 30
        stop_at = None
        if not r["stop_done"] and fm[0] < 58.5 and not st.get("stopped"):
            stop_at = 57.8
        if r["cw_tick"] is not None and tick - r["cw_tick"] < route["crosswalk"]["walker"]["ticks"] and fm[0] < 108.0:
            stop_at = 106.5
        if obey and not r["light_done"] and 120.0 < fm[0] < 158.5 and (light_phase(route, tick) != "green" or light_phase(route, tick + 45) != "green"):
            stop_at = 157.8
        if stop_at is not None and fm[0] > stop_at - 14.0:
            target = min(target, max(0.0, (stop_at - fm[0]) * 0.5) / 30)
            if fm[0] >= stop_at - 0.4:
                target = 0.0
        if car.v == 0 and 53.5 < fm[0] < 58.5:
            st["stopped"] = True
        if fm[0] > 186.0 and car.hy > -0.9:
            target = min(target, 3.0 / 30)
        if car.y < -40.0:
            target = min(target, 2.0 / 30)
        if car.y < -50.5:
            target = 0.0
        if r["moved"] and 20.0 < fm[0] < 180.0 and car.hx > 0.99 and d.ctl["k"] == -1:
            d.set("k", 0)
        if signals and fm[0] > 186.0 and car.hy > -0.5 and d.ctl["k"] != 1:
            d.set("k", 1)
        if car.hy < -0.97 and d.ctl["k"] == 1:
            d.set("k", 0)
        if r["invite_tick"] is not None and not r["invite_done"] and tick > r["invite_tick"] + 20:
            d.set("v", 1 if invite_open else 0)
        _pursuit(d, ROUTE_PATH, 4.0 if car.v > 3.0 / 30 else 3.0)
        if target == 0.0:
            d.set("t", 0)
            d.set("b", 1)
        elif car.v < target - 0.2 / 30:
            d.set("b", 0)
            d.set("t", 1)
        elif car.v > target + 0.3 / 30:
            d.set("t", 0)
            d.set("b", 1)
        else:
            d.set("t", 0)
            d.set("b", 0)

    return control
