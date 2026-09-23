/**
 * 爪爪驾校场地配置与复算快照的形状（服务端 app/web_driving/courses.py、replay.py 的 JSON）。
 * 场地配置是服务端下发的唯一来源：车身、正切表、速度、线、锥桶、目标区、时限、路线检查点与装饰都从这里读，前端不另存常数。
 */

export type Vec = [number, number];
export type Poly = Vec[];

export interface CourseLine {
  id: string;
  a: Vec;
  b: Vec;
  kind: string;
}

export interface CourseCone {
  id: string;
  x: number;
  y: number;
  r: number;
}

export interface CourseTarget {
  poly: Poly;
  dir: Vec;
  cos_tol: number;
  hold_ticks: number;
}

export interface RouteConfig {
  precheck_steps: number;
  start_signal: number;
  speed_limit: number;
  speed_tol: number;
  points: { precheck: number; start_signal: number; stop: number; turn: number; speeding: number; invite: number };
  stop: { line: [Vec, Vec]; zone: Poly; sign: Vec };
  crosswalk: { poly: Poly; trigger: [Vec, Vec]; walker: { from: Vec; to: Vec; ticks: number; kind: string } };
  light: { line: [Vec, Vec]; cycle: [number, number, number]; offset: number; pos: Vec };
  invite: { trigger: [Vec, Vec]; window_ticks: number };
  turn: { zone: Poly; dir: Vec; cos: number; side: number };
  instructions: { zone: Poly; text: string }[];
}

export interface Decor {
  type: string;
  poly?: Poly;
  a?: Vec;
  b?: Vec;
  x?: number;
  y?: number;
  r?: number;
  label?: string | null;
  kind?: string;
  style?: string;
  dash?: number;
  dir?: string;
  practice_only?: number;
  left?: Poly;
  right?: Poly;
}

export interface Course {
  course_id: string;
  item: string;
  variant: string;
  kind: "park" | "curve" | "route";
  title: string;
  tick_hz: number;
  time_limit_ticks: number;
  car: { length: number; width: number; wheelbase: number; rear: number; front: number; steer_steps: number; steer_max_deg: number; tan: number[] };
  physics: { vmax_f: number; vmax_r: number; accel: number; brake: number; coast: number };
  scoring: { line: number; cone: number; pass: number };
  start: { x: number; y: number; hx: number; hy: number; gear: number };
  lines: CourseLine[];
  cones: CourseCone[];
  bounds: Poly[];
  target: CourseTarget | null;
  route: RouteConfig | null;
  view: Poly;
  decor: Decor[];
}

/** 操作事件：s 转向目标 / t 油门 / b 刹车 / g 换挡（1＝D，-1＝R）/ k 转向灯 / c 出发前检查 / v 视频邀请（0 稍后，1 打开） */
export interface InputEventT {
  t: number;
  c: "s" | "t" | "b" | "g" | "k" | "c" | "v";
  v: number;
}

/** 判定事件：p＝扣分，f＝1 表示红线或失败 */
export interface SimEventT {
  t: number;
  k: string;
  ref: string | null;
  p: number;
  f: number;
}

export interface RouteState {
  checks: number[];
  moved: number;
  stop_ok: number;
  stop_done: number;
  cw_tick: number | null;
  light_done: number;
  turned: number;
  invite_tick: number | null;
  invite_done: number;
  speeding: number;
}

export interface Snapshot {
  tick: number;
  car: [number, number, number, number, number, number, number];
  ctl: [number, number, number, number];
  pressed: number;
  knocked: string[];
  hold: number;
  status: "running" | "done" | "failed";
  fail: string | null;
  events: SimEventT[];
  front: Vec;
  route: RouteState | null;
}
