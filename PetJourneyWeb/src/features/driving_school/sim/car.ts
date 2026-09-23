/**
 * 车辆模型（逐行对应 PetJourneyBackend/app/web_driving/sim.py 的 step / corners / front_mid）。
 * 每个 tick：转向档位向目标移动 1 档 → 刹车 / 油门 / 滑行 → 以后轴为参考点转向（泰勒展开的小角度旋转，再归一化）→ 前进。
 * 不用 Math.sin/cos/tan、Math.min/max：保证与服务端复算逐位一致。
 */
import type { Course, Poly, Vec } from "./types";

export interface Car {
  x: number;
  y: number;
  hx: number;
  hy: number;
  v: number;
  s: number;
  gear: number;
}

export interface Body {
  width: number;
  wheelbase: number;
  rear: number;
  front: number;
  steps: number;
  tan: number[];
}

export interface Physics {
  vmax_f: number;
  vmax_r: number;
  accel: number;
  brake: number;
  coast: number;
}

export function bodyOf(course: Course): Body {
  const car = course.car;
  return { width: car.width, wheelbase: car.wheelbase, rear: car.rear, front: car.front, steps: car.steer_steps, tan: car.tan };
}

export function physicsOf(course: Course): Physics {
  const p = course.physics;
  return { vmax_f: p.vmax_f, vmax_r: p.vmax_r, accel: p.accel, brake: p.brake, coast: p.coast };
}

export function step(car: Car, steer: number, throttle: number, brake: number, body: Body, phys: Physics): void {
  if (car.s < steer) car.s = car.s + 1;
  else if (car.s > steer) car.s = car.s - 1;
  let v = car.v;
  if (brake) {
    if (v > 0) {
      v = v - phys.brake;
      if (v < 0) v = 0;
    } else if (v < 0) {
      v = v + phys.brake;
      if (v > 0) v = 0;
    }
  } else if (throttle) {
    if (car.gear === 1) {
      v = v + phys.accel;
      if (v > phys.vmax_f) v = phys.vmax_f;
    } else {
      v = v - phys.accel;
      if (v < -phys.vmax_r) v = -phys.vmax_r;
    }
  } else if (v > 0) {
    v = v - phys.coast;
    if (v < 0) v = 0;
  } else if (v < 0) {
    v = v + phys.coast;
    if (v > 0) v = 0;
  }
  car.v = v;
  if (v !== 0 && car.s !== 0) {
    const t = car.s > 0 ? body.tan[car.s] : -body.tan[-car.s];
    const w = (v * t) / body.wheelbase;
    const w2 = w * w;
    const c = 1 - w2 / 2 + (w2 * w2) / 24;
    const sn = w - (w2 * w) / 6 + (w2 * w2 * w) / 120;
    const nx = car.hx * c - car.hy * sn;
    const ny = car.hx * sn + car.hy * c;
    const n = Math.sqrt(nx * nx + ny * ny);
    car.hx = nx / n;
    car.hy = ny / n;
  }
  car.x = car.x + v * car.hx;
  car.y = car.y + v * car.hy;
}

/** 车身四角（逆时针）：左后、右后、右前、左前。 */
export function corners(car: Car, body: Body): Poly {
  const fx = car.hx;
  const fy = car.hy;
  const lx = -fy;
  const ly = fx;
  const hw = body.width / 2;
  const fr = body.wheelbase + body.front;
  const rx = car.x - fx * body.rear;
  const ry = car.y - fy * body.rear;
  const qx = car.x + fx * fr;
  const qy = car.y + fy * fr;
  return [
    [rx + lx * hw, ry + ly * hw],
    [rx - lx * hw, ry - ly * hw],
    [qx - lx * hw, qy - ly * hw],
    [qx + lx * hw, qy + ly * hw],
  ];
}

export function frontMid(car: Car, body: Body): Vec {
  const fr = body.wheelbase + body.front;
  return [car.x + car.hx * fr, car.y + car.hy * fr];
}
