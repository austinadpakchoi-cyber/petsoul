"""爪爪驾校的确定性驾驶模拟：车辆模型与几何判定（规格见 docs/contracts/DRIVING-SCHOOL-v1.md §4）。

前端 `PetJourneyWeb/src/features/driving_school/sim/` 逐行对应本文件与 replay.py，两边必须保持同样的运算顺序：
- 只用 IEEE 双精度的加减乘除与 sqrt（Python 与 JavaScript 结果逐位相同），不用 sin/cos/tan；
- 所有常数（车身、正切表、速度、加速度、刹车）都来自场地配置，前端不另存常数；
- 不用 min/max 处理速度，避免 ±0 的差异；比较一律用 < / > / <= / >=。
跨语言一致性由 scripts/gen_driving_fixtures.py 生成的样例在两边测试中逐位比对。
"""

from __future__ import annotations

from dataclasses import dataclass
from math import sqrt

Point = tuple[float, float]


@dataclass
class Car:
    x: float
    y: float
    hx: float
    hy: float
    v: float = 0.0  # 米/tick，前进为正、倒车为负
    s: int = 0  # 转向档位，正为向左
    gear: int = 1  # 1＝D，-1＝R


@dataclass(frozen=True)
class Body:
    width: float
    wheelbase: float
    rear: float  # 后轴到车尾
    front: float  # 前轴到车头
    steps: int
    tan: tuple[float, ...]  # tan[i]：第 i 档的转向角正切值（0..steps）


@dataclass(frozen=True)
class Physics:
    vmax_f: float
    vmax_r: float
    accel: float
    brake: float
    coast: float


def body_of(course: dict) -> Body:
    car = course["car"]
    return Body(width=car["width"], wheelbase=car["wheelbase"], rear=car["rear"], front=car["front"], steps=car["steer_steps"], tan=tuple(car["tan"]))


def physics_of(course: dict) -> Physics:
    p = course["physics"]
    return Physics(vmax_f=p["vmax_f"], vmax_r=p["vmax_r"], accel=p["accel"], brake=p["brake"], coast=p["coast"])


def step(car: Car, steer: int, throttle: int, brake: int, body: Body, phys: Physics) -> None:
    """推进一个 tick（换挡由调用方在此之前处理）。"""
    if car.s < steer:
        car.s = car.s + 1
    elif car.s > steer:
        car.s = car.s - 1
    v = car.v
    if brake:
        if v > 0:
            v = v - phys.brake
            if v < 0:
                v = 0.0
        elif v < 0:
            v = v + phys.brake
            if v > 0:
                v = 0.0
    elif throttle:
        if car.gear == 1:
            v = v + phys.accel
            if v > phys.vmax_f:
                v = phys.vmax_f
        else:
            v = v - phys.accel
            if v < -phys.vmax_r:
                v = -phys.vmax_r
    else:
        if v > 0:
            v = v - phys.coast
            if v < 0:
                v = 0.0
        elif v < 0:
            v = v + phys.coast
            if v > 0:
                v = 0.0
    car.v = v
    if v != 0 and car.s != 0:
        t = body.tan[car.s] if car.s > 0 else -body.tan[-car.s]
        w = v * t / body.wheelbase
        w2 = w * w
        c = 1 - w2 / 2 + w2 * w2 / 24
        sn = w - w2 * w / 6 + w2 * w2 * w / 120
        nx = car.hx * c - car.hy * sn
        ny = car.hx * sn + car.hy * c
        n = sqrt(nx * nx + ny * ny)
        car.hx = nx / n
        car.hy = ny / n
    car.x = car.x + v * car.hx
    car.y = car.y + v * car.hy


def corners(car: Car, body: Body) -> list[Point]:
    """车身四角（逆时针）：左后、右后、右前、左前。"""
    fx, fy = car.hx, car.hy
    lx, ly = -fy, fx
    hw = body.width / 2
    fr = body.wheelbase + body.front
    rx = car.x - fx * body.rear
    ry = car.y - fy * body.rear
    qx = car.x + fx * fr
    qy = car.y + fy * fr
    return [(rx + lx * hw, ry + ly * hw), (rx - lx * hw, ry - ly * hw), (qx - lx * hw, qy - ly * hw), (qx + lx * hw, qy + ly * hw)]


def front_mid(car: Car, body: Body) -> Point:
    fr = body.wheelbase + body.front
    return (car.x + car.hx * fr, car.y + car.hy * fr)


def cross(ax: float, ay: float, bx: float, by: float, px: float, py: float) -> float:
    return (bx - ax) * (py - ay) - (by - ay) * (px - ax)


def inside_convex(px: float, py: float, poly: list) -> bool:
    """点在逆时针凸多边形内（含边上）。"""
    n = len(poly)
    for i in range(n):
        a = poly[i]
        b = poly[(i + 1) % n]
        if cross(a[0], a[1], b[0], b[1], px, py) < 0:
            return False
    return True


def _on_segment(ax: float, ay: float, bx: float, by: float, px: float, py: float) -> bool:
    lo_x = ax if ax < bx else bx
    hi_x = bx if ax < bx else ax
    lo_y = ay if ay < by else by
    hi_y = by if ay < by else ay
    return lo_x <= px <= hi_x and lo_y <= py <= hi_y


def segments_cross(a: Point, b: Point, c: Point, d: Point) -> bool:
    d1 = cross(c[0], c[1], d[0], d[1], a[0], a[1])
    d2 = cross(c[0], c[1], d[0], d[1], b[0], b[1])
    d3 = cross(a[0], a[1], b[0], b[1], c[0], c[1])
    d4 = cross(a[0], a[1], b[0], b[1], d[0], d[1])
    if ((d1 > 0 and d2 < 0) or (d1 < 0 and d2 > 0)) and ((d3 > 0 and d4 < 0) or (d3 < 0 and d4 > 0)):
        return True
    if d1 == 0 and _on_segment(c[0], c[1], d[0], d[1], a[0], a[1]):
        return True
    if d2 == 0 and _on_segment(c[0], c[1], d[0], d[1], b[0], b[1]):
        return True
    if d3 == 0 and _on_segment(a[0], a[1], b[0], b[1], c[0], c[1]):
        return True
    return d4 == 0 and _on_segment(a[0], a[1], b[0], b[1], d[0], d[1])


def segment_hits_poly(a: Point, b: Point, poly: list[Point]) -> bool:
    if inside_convex(a[0], a[1], poly) or inside_convex(b[0], b[1], poly):
        return True
    n = len(poly)
    for i in range(n):
        if segments_cross(a, b, poly[i], poly[(i + 1) % n]):
            return True
    return False


def dist2_to_segment(px: float, py: float, a: Point, b: Point) -> float:
    dx = b[0] - a[0]
    dy = b[1] - a[1]
    len2 = dx * dx + dy * dy
    t = 0.0
    if len2 > 0:
        t = ((px - a[0]) * dx + (py - a[1]) * dy) / len2
        if t < 0:
            t = 0.0
        elif t > 1:
            t = 1.0
    cx = a[0] + t * dx
    cy = a[1] + t * dy
    ex = px - cx
    ey = py - cy
    return ex * ex + ey * ey


def circle_hits_poly(cx: float, cy: float, r: float, poly: list[Point]) -> bool:
    if inside_convex(cx, cy, poly):
        return True
    r2 = r * r
    n = len(poly)
    for i in range(n):
        if dist2_to_segment(cx, cy, poly[i], poly[(i + 1) % n]) <= r2:
            return True
    return False


def bbox(points: list) -> tuple[float, float, float, float]:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    lo_x, hi_x, lo_y, hi_y = xs[0], xs[0], ys[0], ys[0]
    for x in xs:
        if x < lo_x:
            lo_x = x
        if x > hi_x:
            hi_x = x
    for y in ys:
        if y < lo_y:
            lo_y = y
        if y > hi_y:
            hi_y = y
    return lo_x, lo_y, hi_x, hi_y


def boxes_overlap(a: tuple[float, float, float, float], b: tuple[float, float, float, float], pad: float = 0.0) -> bool:
    return not (a[2] + pad < b[0] or b[2] + pad < a[0] or a[3] + pad < b[1] or b[3] + pad < a[1])
