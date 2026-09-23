/**
 * 驾驶考局的本地引擎（与 React 无关，便于测试）：
 * - 主人的操作先写进“期望控制”，每个 tick 开始时和上一次记录的值比较，有变化才记一条操作事件 {t, c, v}；
 * - 用 Replay 按 tick 推进（与服务端复算同一套代码），产生压线、碰锥、到位、红线等判定事件；
 * - 未上传的操作攒成片段 {from_tick, upto_tick, events}，由上传器按顺序发给服务端；
 * - 服务端的快照是准绳：对不上时用服务端快照重建本地状态（不能抹掉已经发生的扣分）。
 */
import type { InputChunk } from "@/shared/contracts";
import type { Car } from "../sim/car";
import { Replay } from "../sim/replay";
import type { Course, InputEventT, SimEventT, Snapshot } from "../sim/types";

type Code = InputEventT["c"];

export interface Pose {
  x: number;
  y: number;
  hx: number;
  hy: number;
}

export class DriveEngine {
  readonly course: Course;
  replay: Replay;
  /** 上一个 tick 的车位姿（渲染插值用） */
  prev: Pose;
  /** 期望控制：转向目标档位、油门、刹车、转向灯 */
  private desired: { s: number; t: number; b: number; k: number };
  private recorded: { s: number; t: number; b: number; k: number };
  private oneShots: InputEventT[] = [];
  /** 还没交给上传器的操作 */
  private pending: InputEventT[] = [];
  /** 下一段的起点（已交给上传器的最后一个 tick） */
  sentTick: number;

  constructor(course: Course, snapshot?: Snapshot | null) {
    this.course = course;
    this.replay = new Replay(course, snapshot ?? null);
    const [s, t, b, k] = [this.replay.steer, this.replay.throttle, this.replay.brake, this.replay.blink];
    this.recorded = { s, t, b, k };
    // 续考时踏板视为已经松开：界面上没有按着的踏板，第一 tick 会记下松开（转向与灯保持原样）。
    this.desired = { s, t: 0, b: 0, k };
    this.sentTick = this.replay.tick;
    this.prev = pose(this.replay.car);
  }

  get tick(): number {
    return this.replay.tick;
  }

  get running(): boolean {
    return this.replay.status === "running";
  }

  get limit(): number {
    return this.course.time_limit_ticks;
  }

  get steerTarget(): number {
    return this.desired.s;
  }

  get blink(): number {
    return this.desired.k;
  }

  get throttle(): boolean {
    return this.desired.t === 1;
  }

  get brake(): boolean {
    return this.desired.b === 1;
  }

  setSteer(value: number): void {
    const max = this.course.car.steer_steps;
    this.desired.s = value > max ? max : value < -max ? -max : Math.round(value);
  }

  nudgeSteer(delta: number): void {
    this.setSteer(this.desired.s + delta);
  }

  setThrottle(on: boolean): void {
    this.desired.t = on ? 1 : 0;
  }

  setBrake(on: boolean): void {
    this.desired.b = on ? 1 : 0;
  }

  setBlink(value: -1 | 0 | 1): void {
    this.desired.k = value;
  }

  /** 换挡请求：只有车完全停下才会生效（复算里同样只在 v==0 时生效）。 */
  shift(gear: 1 | -1): boolean {
    if (this.replay.car.v !== 0 || this.replay.car.gear === gear) return false;
    this.oneShots.push({ t: -1, c: "g", v: gear });
    return true;
  }

  check(step: number): void {
    const done = this.replay.r?.checks ?? [];
    if (!done.includes(step) && !this.oneShots.some((e) => e.c === "c" && e.v === step)) this.oneShots.push({ t: -1, c: "c", v: step });
  }

  invite(open: boolean): void {
    this.oneShots.push({ t: -1, c: "v", v: open ? 1 : 0 });
  }

  /** 推进一个 tick，返回这一 tick 新产生的判定事件。 */
  advance(): SimEventT[] {
    if (!this.running) return [];
    const t = this.replay.tick;
    const events: InputEventT[] = [];
    const push = (c: Code, v: number) => events.push({ t, c, v });
    for (const code of ["s", "t", "b", "k"] as const) {
      if (this.desired[code] !== this.recorded[code]) {
        push(code, this.desired[code]);
        this.recorded[code] = this.desired[code];
      }
    }
    for (const shot of this.oneShots) push(shot.c, shot.v);
    this.oneShots = [];
    this.pending.push(...events);
    this.prev = pose(this.replay.car);
    return this.replay.apply(events, t + 1);
  }

  /** 取出一段待上传的操作；没有新 tick 时返回 null。 */
  takeChunk(itemIndex: number): InputChunk | null {
    const upto = this.replay.tick;
    if (upto <= this.sentTick) return null;
    const chunk: InputChunk = { item_index: itemIndex, from_tick: this.sentTick, upto_tick: upto, events: this.pending };
    this.pending = [];
    this.sentTick = upto;
    return chunk;
  }

  /** 与服务端在同一 tick 的快照比对（只比对判定结果与车辆状态）。 */
  static agrees(local: Snapshot, server: Snapshot): boolean {
    if (local.tick !== server.tick || local.status !== server.status || local.events.length !== server.events.length) return false;
    for (let i = 0; i < 7; i++) if (local.car[i] !== server.car[i]) return false;
    return true;
  }

  /**
   * 预测轨迹（练习提示用，只画不判）：按当前挡位方向、当前方向盘目标，以慢速往前推 meters 米，
   * 告诉主人“照这样打方向，车会走到哪里”。与踏板无关，也不影响复算。
   */
  predict(meters: number, every = 0.5): Pose[] {
    const car: Car = { ...this.replay.car };
    const body = this.replay.body;
    const dir = car.gear === -1 ? -1 : 1;
    const speed = car.v > 0 ? car.v : -car.v;
    // 每步走“一个 tick 的路程”，方向盘每步向目标转 1 档，和真实车辆的转向节奏一致。
    const ds = speed > 0.01 ? speed : dir === 1 ? this.replay.phys.vmax_f * 0.4 : this.replay.phys.vmax_r;
    const out: Pose[] = [];
    let travelled = 0;
    let next = every;
    while (travelled < meters) {
      if (car.s < this.desired.s) car.s += 1;
      else if (car.s > this.desired.s) car.s -= 1;
      const tan = car.s > 0 ? body.tan[car.s] : -body.tan[-car.s];
      const w = (dir * ds * tan) / body.wheelbase;
      const c = Math.cos(w);
      const sn = Math.sin(w);
      const hx = car.hx * c - car.hy * sn;
      const hy = car.hx * sn + car.hy * c;
      car.hx = hx;
      car.hy = hy;
      car.x += dir * ds * hx;
      car.y += dir * ds * hy;
      travelled += ds;
      if (travelled >= next) {
        out.push(pose(car));
        next += every;
      }
    }
    return out;
  }
}

export function pose(car: Car): Pose {
  return { x: car.x, y: car.y, hx: car.hx, hy: car.hy };
}

export function lerpPose(a: Pose, b: Pose, k: number): Pose {
  const hx = a.hx + (b.hx - a.hx) * k;
  const hy = a.hy + (b.hy - a.hy) * k;
  const n = Math.hypot(hx, hy) || 1;
  return { x: a.x + (b.x - a.x) * k, y: a.y + (b.y - a.y) * k, hx: hx / n, hy: hy / n };
}
