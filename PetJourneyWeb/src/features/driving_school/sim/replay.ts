/**
 * 操作复算（逐行对应 PetJourneyBackend/app/web_driving/replay.py）：按 tick 应用操作事件、推进车辆、判定扣分、失败与完成。
 * 前端用它实时驾驶；服务端用 Python 版复算上传的操作，两边结果逐位一致（tests/driving-sim.test.ts 用后端生成的样例比对）。
 * 判定事件 {t, k, ref, p, f}：p＝扣分，f＝1 表示红线或失败（本项立即结束）。
 */
import { bbox, type Box, boxesOverlap, circleHitsPoly, insideConvex, segmentHitsPoly, segmentsCross } from "./geometry";
import { type Body, type Car, bodyOf, corners, frontMid, type Physics, physicsOf, step } from "./car";
import type { Course, InputEventT, Poly, RouteConfig, RouteState, SimEventT, Snapshot, Vec } from "./types";

export function lightPhase(route: RouteConfig, tick: number): "green" | "yellow" | "red" {
  const [green, yellow, red] = route.light.cycle;
  const p = (tick + route.light.offset) % (green + yellow + red);
  if (p < green) return "green";
  return p < green + yellow ? "yellow" : "red";
}

export function walkerAt(route: RouteConfig, cwTick: number | null, tick: number): Vec {
  const walker = route.crosswalk.walker;
  const [fx, fy] = walker.from;
  if (cwTick === null) return [fx, fy];
  let k = (tick - cwTick) / walker.ticks;
  if (k > 1) k = 1;
  const [tx, ty] = walker.to;
  return [fx + (tx - fx) * k, fy + (ty - fy) * k];
}

export class Replay {
  readonly course: Course;
  readonly body: Body;
  readonly phys: Physics;
  private readonly lines: [string, Vec, Vec][];
  private readonly lineBoxes: Box[];
  car: Car;
  steer = 0;
  throttle = 0;
  brake = 0;
  blink = 0;
  tick: number;
  pressed: number;
  knocked: string[];
  hold: number;
  status: "running" | "done" | "failed";
  fail: string | null;
  events: SimEventT[];
  front: Vec;
  r: RouteState | null;

  constructor(course: Course, snapshot?: Snapshot | null) {
    this.course = course;
    this.body = bodyOf(course);
    this.phys = physicsOf(course);
    this.lines = course.lines.map((line) => [line.id, [line.a[0], line.a[1]], [line.b[0], line.b[1]]]);
    this.lineBoxes = this.lines.map(([, a, b]) => bbox([a, b]));
    const state = snapshot ?? this.initial();
    const c = state.car;
    this.car = { x: c[0], y: c[1], hx: c[2], hy: c[3], v: c[4], s: c[5], gear: c[6] };
    [this.steer, this.throttle, this.brake, this.blink] = state.ctl;
    this.tick = state.tick;
    this.pressed = state.pressed;
    this.knocked = [...state.knocked];
    this.hold = state.hold;
    this.status = state.status;
    this.fail = state.fail;
    this.events = [...state.events];
    this.front = [state.front[0], state.front[1]];
    this.r = state.route ? { ...state.route, checks: [...state.route.checks] } : null;
  }

  initial(): Snapshot {
    const start = this.course.start;
    const car: Car = { x: start.x, y: start.y, hx: start.hx, hy: start.hy, v: 0, s: 0, gear: start.gear };
    const fm = frontMid(car, this.body);
    const route: RouteState | null = this.course.route
      ? { checks: [], moved: 0, stop_ok: 0, stop_done: 0, cw_tick: null, light_done: 0, turned: 0, invite_tick: null, invite_done: 0, speeding: 0 }
      : null;
    return {
      tick: 0, car: [car.x, car.y, car.hx, car.hy, 0, 0, car.gear], ctl: [0, 0, 0, 0], pressed: 0, knocked: [], hold: 0, status: "running",
      fail: null, events: [], front: [fm[0], fm[1]], route,
    };
  }

  snapshot(): Snapshot {
    const c = this.car;
    return {
      tick: this.tick, car: [c.x, c.y, c.hx, c.hy, c.v, c.s, c.gear], ctl: [this.steer, this.throttle, this.brake, this.blink], pressed: this.pressed,
      knocked: [...this.knocked], hold: this.hold, status: this.status, fail: this.fail, events: [...this.events], front: [this.front[0], this.front[1]],
      route: this.r ? { ...this.r, checks: [...this.r.checks] } : null,
    };
  }

  get deducted(): number {
    return this.events.reduce((sum, e) => sum + e.p, 0);
  }

  /** 从当前 tick 推进到 uptoTick（不含）；events 按 tick 排序。返回新产生的判定事件。 */
  apply(events: InputEventT[], uptoTick: number): SimEventT[] {
    const before = this.events.length;
    let index = 0;
    while (this.tick < uptoTick && this.status === "running") {
      const tick = this.tick;
      while (index < events.length && events[index].t === tick) {
        this.input(events[index].c, events[index].v, tick);
        index++;
      }
      step(this.car, this.steer, this.throttle, this.brake, this.body, this.phys);
      this.detect(tick);
      this.tick = tick + 1;
    }
    return this.events.slice(before);
  }

  private input(code: string, value: number, tick: number): void {
    if (code === "s") this.steer = value;
    else if (code === "t") this.throttle = value;
    else if (code === "b") this.brake = value;
    else if (code === "g") {
      if (this.car.v === 0) this.car.gear = value;
    } else if (code === "k") this.blink = value;
    else if (code === "c") {
      if (this.r !== null && !this.r.checks.includes(value)) this.r.checks = [...this.r.checks, value];
    } else if (code === "v") {
      const r = this.r;
      if (r !== null && r.invite_tick !== null && !r.invite_done && tick >= r.invite_tick) {
        r.invite_done = 1;
        if (value === 1) this.add(tick, "invite_opened", null, this.course.route!.points.invite);
      }
    }
  }

  private add(tick: number, kind: string, ref: string | null, points: number, fatal = 0): void {
    this.events.push({ t: tick, k: kind, ref, p: points, f: fatal });
  }

  private failNow(tick: number, kind: string, ref: string | null = null): void {
    this.add(tick, kind, ref, 0, 1);
    this.status = "failed";
    this.fail = kind;
    this.car.v = 0;
  }

  private detect(tick: number): void {
    const body = this.body;
    const poly = corners(this.car, body);
    const box = bbox(poly);
    const fm = frontMid(this.car, body);
    for (const [cx, cy] of poly) {
      let inside = false;
      for (const area of this.course.bounds) {
        if (insideConvex(cx, cy, area)) {
          inside = true;
          break;
        }
      }
      if (!inside) {
        this.failNow(tick, "out_of_bounds");
        return;
      }
    }
    let hit: string | null = null;
    for (let index = 0; index < this.lines.length; index++) {
      const [lineId, a, b] = this.lines[index];
      if (boxesOverlap(box, this.lineBoxes[index]) && segmentHitsPoly(a, b, poly)) {
        hit = lineId;
        break;
      }
    }
    if (hit !== null && !this.pressed) this.add(tick, "line", hit, this.course.scoring.line);
    this.pressed = hit !== null ? 1 : 0;
    for (const cone of this.course.cones) {
      if (!this.knocked.includes(cone.id) && circleHitsPoly(cone.x, cone.y, cone.r, poly)) {
        this.knocked = [...this.knocked, cone.id];
        this.add(tick, "cone", cone.id, this.course.scoring.cone);
      }
    }
    if (this.r !== null) this.route(tick, poly, fm);
    if (this.status !== "running") return;
    const target = this.course.target;
    if (target !== null) {
      let placed = true;
      for (const [cx, cy] of poly) {
        if (!insideConvex(cx, cy, target.poly)) {
          placed = false;
          break;
        }
      }
      const aligned = this.car.hx * target.dir[0] + this.car.hy * target.dir[1] >= target.cos_tol;
      this.hold = placed && aligned && this.car.v === 0 ? this.hold + 1 : 0;
      if (this.hold >= target.hold_ticks) {
        this.add(tick, "done", null, 0);
        this.status = "done";
        this.front = fm;
        return;
      }
    }
    if (tick + 1 >= this.course.time_limit_ticks) this.failNow(tick, "timeout");
    this.front = fm;
  }

  private route(tick: number, poly: Poly, fm: Vec): void {
    const route = this.course.route!;
    const r = this.r!;
    const car = this.car;
    const prev = this.front;
    const points = route.points;
    if (!r.moved && car.v !== 0) {
      r.moved = 1;
      if (r.checks.length < route.precheck_steps) this.add(tick, "precheck_skipped", null, points.precheck);
      if (this.blink !== route.start_signal) this.add(tick, "start_no_signal", null, points.start_signal);
    }
    const stop = route.stop;
    if (!r.stop_done) {
      if (car.v === 0 && insideConvex(fm[0], fm[1], stop.zone)) r.stop_ok = 1;
      if (car.v > 0 && segmentsCross(prev, fm, stop.line[0], stop.line[1])) {
        r.stop_done = 1;
        if (!r.stop_ok) this.add(tick, "stop_rolled", null, points.stop);
      }
    }
    const crosswalk = route.crosswalk;
    if (r.cw_tick === null && segmentsCross(prev, fm, crosswalk.trigger[0], crosswalk.trigger[1])) r.cw_tick = tick;
    if (r.cw_tick !== null && tick - r.cw_tick < crosswalk.walker.ticks) {
      const area = crosswalk.poly;
      const n = area.length;
      let entered = false;
      for (const [cx, cy] of poly) {
        if (insideConvex(cx, cy, area)) {
          entered = true;
          break;
        }
      }
      if (!entered) {
        for (let i = 0; i < n; i++) {
          if (segmentHitsPoly(area[i], area[(i + 1) % n], poly)) {
            entered = true;
            break;
          }
        }
      }
      if (entered) {
        this.failNow(tick, "crosswalk");
        return;
      }
    }
    const light = route.light;
    if (!r.light_done && car.v > 0 && segmentsCross(prev, fm, light.line[0], light.line[1])) {
      r.light_done = 1;
      if (lightPhase(route, tick) === "red") {
        this.failNow(tick, "red_light");
        return;
      }
    }
    const invite = route.invite;
    if (r.invite_tick === null) {
      if (segmentsCross(prev, fm, invite.trigger[0], invite.trigger[1])) {
        r.invite_tick = tick;
        this.add(tick, "invite_shown", null, 0);
      }
    } else if (!r.invite_done && tick - r.invite_tick >= invite.window_ticks) {
      r.invite_done = 1;
    }
    const turn = route.turn;
    if (!r.turned && insideConvex(fm[0], fm[1], turn.zone) && car.hx * turn.dir[0] + car.hy * turn.dir[1] < turn.cos) {
      r.turned = 1;
      if (this.blink !== turn.side) this.add(tick, "turn_no_signal", null, points.turn);
    }
    const speed = car.v > 0 ? car.v : -car.v;
    if (!r.speeding && speed > route.speed_limit + route.speed_tol) {
      r.speeding = 1;
      this.add(tick, "speeding", null, points.speeding);
    } else if (r.speeding && speed <= route.speed_limit) {
      r.speeding = 0;
    }
  }
}
