/**
 * 训练场绘制（只负责画，不做任何判定）：场地配置里的装饰、计分线、锥桶、目标区、路线上的信号灯与过街居民、小车与车里的 TA。
 * 颜色全部取自主题变量（读 CSS 变量），日间 / 夜间自动跟随；世界坐标单位是米，y 轴向上。
 */
import { lightPhase, walkerAt } from "../sim/replay";
import type { Course, Decor, Poly, RouteState, Vec } from "../sim/types";
import type { Pose } from "./engine";

export interface Palette {
  grass: string;
  road: string;
  sidewalk: string;
  paint: string;
  center: string;
  curb: string;
  zone: string;
  zoneStroke: string;
  tree: string;
  paper: string;
  paperShade: string;
  paperInk: string;
  cone: string;
  coneKnocked: string;
  car: string;
  carInk: string;
  glass: string;
  pet: string;
  leaf: string;
  danger: string;
  sun: string;
  sky: string;
  ink: string;
  font: string;
}

const TOKENS: Record<Exclude<keyof Palette, "font">, [string, string]> = {
  grass: ["--c-leaf-soft", "#d9ecdf"],
  road: ["--c-deep-ink", "#203129"],
  sidewalk: ["--c-bg-soft", "#efe7d8"],
  paint: ["--c-on-deep", "#fbf7ef"],
  center: ["--c-sun", "#e9a53a"],
  curb: ["--c-ink-3", "#a1968a"],
  zone: ["--c-sun-soft", "#fbead0"],
  zoneStroke: ["--c-sun", "#e9a53a"],
  tree: ["--c-leaf", "#2f7d5e"],
  paper: ["--paper", "#f4ead5"],
  paperShade: ["--paper-shade", "#e6d6b6"],
  paperInk: ["--paper-ink", "#3b2f22"],
  cone: ["--c-coral", "#df6f55"],
  coneKnocked: ["--c-ink-3", "#a1968a"],
  car: ["--c-sky", "#6aa9dc"],
  carInk: ["--c-deep-ink", "#203129"],
  glass: ["--c-sky-soft", "#d9ebf8"],
  pet: ["--c-sun", "#e9a53a"],
  leaf: ["--c-leaf", "#2f7d5e"],
  danger: ["--c-danger", "#c24b3a"],
  sun: ["--c-sun", "#e9a53a"],
  sky: ["--c-sky", "#6aa9dc"],
  ink: ["--c-ink", "#2b2620"],
};

export function readPalette(el: Element): Palette {
  const style = getComputedStyle(el);
  const out = {} as Palette;
  for (const [key, [token, fallback]] of Object.entries(TOKENS)) {
    const value = style.getPropertyValue(token).trim();
    (out as unknown as Record<string, string>)[key] = value || fallback;
  }
  out.font = style.getPropertyValue("--font-sans").trim() || "sans-serif";
  return out;
}

export interface Camera {
  cx: number;
  cy: number;
  scale: number;
}

export function fitCamera(view: Poly, width: number, height: number, pad = 8): Camera {
  let loX = Infinity;
  let hiX = -Infinity;
  let loY = Infinity;
  let hiY = -Infinity;
  for (const [x, y] of view) {
    loX = Math.min(loX, x);
    hiX = Math.max(hiX, x);
    loY = Math.min(loY, y);
    hiY = Math.max(hiY, y);
  }
  const scale = Math.min((width - pad * 2) / (hiX - loX), (height - pad * 2) / (hiY - loY));
  return { cx: (loX + hiX) / 2, cy: (loY + hiY) / 2, scale };
}

/** 路线跟车：车在画面中偏后的位置，前方多看一点（约 40 米视野，车头前方留出 10 米）。 */
export function followCamera(p: Pose, width: number, height: number): Camera {
  const scale = Math.min(width, height) / 40;
  return { cx: p.x + p.hx * 10, cy: p.y + p.hy * 10, scale };
}

export interface Frame {
  course: Course;
  pose: Pose;
  /** 当前转向档位（车轮角度） */
  steer: number;
  gear: number;
  brake: boolean;
  blink: number;
  tick: number;
  knocked: string[];
  route: RouteState | null;
  /** 正在压着的线（高亮） */
  pressedLine: string | null;
  practice: boolean;
  predicted: Pose[] | null;
  /** 闪烁相位（转向灯）；减少动效时固定常亮 */
  blinkOn: boolean;
}

export function draw(ctx: CanvasRenderingContext2D, width: number, height: number, cam: Camera, frame: Frame, pal: Palette): void {
  const S = cam.scale;
  const X = (x: number) => (x - cam.cx) * S + width / 2;
  const Y = (y: number) => height / 2 - (y - cam.cy) * S;
  const path = (poly: Poly) => {
    ctx.beginPath();
    poly.forEach(([x, y], i) => (i === 0 ? ctx.moveTo(X(x), Y(y)) : ctx.lineTo(X(x), Y(y))));
    ctx.closePath();
  };
  const segment = (a: Vec, b: Vec) => {
    ctx.beginPath();
    ctx.moveTo(X(a[0]), Y(a[1]));
    ctx.lineTo(X(b[0]), Y(b[1]));
  };
  const label = (text: string, x: number, y: number, size: number, color: string, weight = 600) => {
    ctx.font = `${weight} ${Math.max(10, size)}px ${pal.font}`;
    ctx.fillStyle = color;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(text, x, y);
  };

  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = pal.grass;
  ctx.fillRect(0, 0, width, height);

  const decor = frame.course.decor;
  const layer = (types: string[]) => decor.filter((d) => types.includes(d.type) && (frame.practice || !d.practice_only));
  for (const d of layer(["sidewalk"])) {
    path(d.poly!);
    ctx.fillStyle = pal.sidewalk;
    ctx.fill();
  }
  for (const d of layer(["asphalt"])) {
    path(d.poly!);
    ctx.globalAlpha = 0.82;
    ctx.fillStyle = pal.road;
    ctx.fill();
    ctx.globalAlpha = 1;
  }
  for (const d of layer(["lane"])) drawLane(d);
  for (const d of layer(["crosswalk"])) drawCrosswalk(d.poly!);
  for (const d of layer(["zone"])) {
    path(d.poly!);
    ctx.globalAlpha = 0.35;
    ctx.fillStyle = pal.zone;
    ctx.fill();
    ctx.globalAlpha = 1;
    ctx.setLineDash([6, 5]);
    ctx.lineWidth = 2;
    ctx.strokeStyle = pal.zoneStroke;
    ctx.stroke();
    ctx.setLineDash([]);
    if (d.label) {
      const [cx, cy] = centroid(d.poly!);
      label(d.label, X(cx), Y(cy), S * 0.7, pal.paint);
    }
  }
  for (const d of layer(["paint"])) {
    segment(d.a!, d.b!);
    ctx.setLineDash(d.dash ? [S * 0.8, S * 0.6] : []);
    ctx.lineWidth = Math.max(1.5, S * 0.12);
    ctx.strokeStyle = pal.paint;
    ctx.globalAlpha = 0.7;
    ctx.stroke();
    ctx.globalAlpha = 1;
    ctx.setLineDash([]);
  }
  for (const d of layer(["stopline"])) {
    segment(d.a!, d.b!);
    ctx.lineWidth = Math.max(3, S * 0.35);
    ctx.strokeStyle = pal.paint;
    ctx.stroke();
  }
  for (const d of layer(["arrow"])) drawArrow(d);

  // 计分线（压到就扣分）：车位线白色、路沿灰色、中心线黄色；正在压的线变红。
  for (const line of frame.course.lines) {
    segment(line.a, line.b);
    const pressed = frame.pressedLine === line.id;
    ctx.lineWidth = line.kind === "curb" || line.kind === "barrier" ? Math.max(3, S * 0.3) : Math.max(2, S * 0.15);
    ctx.strokeStyle = pressed ? pal.danger : line.kind === "center" ? pal.center : line.kind === "curb" || line.kind === "barrier" ? pal.curb : pal.paint;
    ctx.stroke();
  }
  for (const d of layer(["barrier"])) {
    segment(d.a!, d.b!);
    ctx.lineWidth = Math.max(4, S * 0.4);
    ctx.setLineDash([S * 0.5, S * 0.5]);
    ctx.strokeStyle = pal.cone;
    ctx.stroke();
    ctx.setLineDash([]);
  }

  // 练习提示：目标车位与朝向。
  const target = frame.course.target;
  if (frame.practice && target) {
    path(target.poly);
    ctx.globalAlpha = 0.18;
    ctx.fillStyle = pal.leaf;
    ctx.fill();
    ctx.globalAlpha = 1;
    ctx.setLineDash([5, 4]);
    ctx.lineWidth = 2;
    ctx.strokeStyle = pal.leaf;
    ctx.stroke();
    ctx.setLineDash([]);
  }

  for (const cone of frame.course.cones) {
    const down = frame.knocked.includes(cone.id);
    ctx.beginPath();
    ctx.arc(X(cone.x) + (down ? S * 0.25 : 0), Y(cone.y), Math.max(4, cone.r * S * 1.2), 0, Math.PI * 2);
    ctx.fillStyle = down ? pal.coneKnocked : pal.cone;
    ctx.fill();
    ctx.lineWidth = 1.5;
    ctx.strokeStyle = pal.paint;
    ctx.stroke();
  }

  for (const d of layer(["building"])) drawBuilding(d);
  for (const d of layer(["tree"])) {
    ctx.beginPath();
    ctx.arc(X(d.x!), Y(d.y!), (d.r ?? 1) * S, 0, Math.PI * 2);
    ctx.fillStyle = pal.tree;
    ctx.globalAlpha = 0.85;
    ctx.fill();
    ctx.globalAlpha = 1;
  }
  for (const d of layer(["bus_stop"])) {
    ctx.fillStyle = pal.sky;
    ctx.fillRect(X(d.x!) - S * 1.2, Y(d.y!) - S * 0.4, S * 2.4, S * 0.8);
    label("站", X(d.x!), Y(d.y!), S * 0.6, pal.paint);
  }
  for (const d of layer(["sign"])) drawSign(d);
  for (const d of layer(["resident"])) drawResident(d.x!, d.y!, d.kind ?? "penguin");
  for (const d of layer(["coach"])) drawCoach(d.x!, d.y!);

  const route = frame.course.route;
  if (route) {
    const phase = lightPhase(route, frame.tick);
    const [lx, ly] = route.light.pos;
    ctx.fillStyle = pal.carInk;
    ctx.fillRect(X(lx) - S * 0.5, Y(ly) - S * 1.3, S * 1.0, S * 2.6);
    const lamps: ["red" | "yellow" | "green", string, number][] = [["red", pal.danger, 0.8], ["yellow", pal.sun, 0], ["green", pal.leaf, -0.8]];
    for (const [name, color, dy] of lamps) {
      ctx.beginPath();
      ctx.arc(X(lx), Y(ly + dy), S * 0.32, 0, Math.PI * 2);
      ctx.fillStyle = color;
      ctx.globalAlpha = phase === name ? 1 : 0.2;
      ctx.fill();
      ctx.globalAlpha = 1;
    }
    const r = frame.route;
    if (r && r.cw_tick !== null && frame.tick - r.cw_tick < route.crosswalk.walker.ticks) {
      const [wx, wy] = walkerAt(route, r.cw_tick, frame.tick);
      drawResident(wx, wy, route.crosswalk.walker.kind);
    } else if (!r || r.cw_tick === null) {
      const [wx, wy] = route.crosswalk.walker.from;
      drawResident(wx, wy, route.crosswalk.walker.kind);
    }
  }

  if (frame.predicted && frame.predicted.length) {
    ctx.fillStyle = pal.leaf;
    for (const p of frame.predicted) {
      ctx.beginPath();
      ctx.arc(X(p.x), Y(p.y), Math.max(1.5, S * 0.1), 0, Math.PI * 2);
      ctx.fill();
    }
  }

  drawCar(frame);

  // ---- 局部绘制函数 ----
  function drawLane(d: Decor) {
    const left = d.left!;
    const right = d.right!;
    ctx.beginPath();
    left.forEach(([x, y], i) => (i === 0 ? ctx.moveTo(X(x), Y(y)) : ctx.lineTo(X(x), Y(y))));
    for (let i = right.length - 1; i >= 0; i--) ctx.lineTo(X(right[i][0]), Y(right[i][1]));
    ctx.closePath();
    ctx.globalAlpha = 0.82;
    ctx.fillStyle = pal.road;
    ctx.fill();
    ctx.globalAlpha = 1;
  }

  function drawCrosswalk(poly: Poly) {
    const xs = poly.map((p) => p[0]);
    const ys = poly.map((p) => p[1]);
    const x0 = Math.min(...xs);
    const x1 = Math.max(...xs);
    const y0 = Math.min(...ys);
    const y1 = Math.max(...ys);
    ctx.fillStyle = pal.paint;
    ctx.globalAlpha = 0.85;
    for (let y = y0 + 0.3; y < y1; y += 1.0) ctx.fillRect(X(x0), Y(y + 0.5), (x1 - x0) * S, 0.5 * S);
    ctx.globalAlpha = 1;
  }

  function drawArrow(d: Decor) {
    const x = X(d.x!);
    const y = Y(d.y!);
    ctx.save();
    ctx.translate(x, y);
    if (d.dir === "right") ctx.rotate(Math.PI / 2);
    ctx.fillStyle = pal.paint;
    ctx.globalAlpha = 0.75;
    ctx.beginPath();
    ctx.moveTo(-S * 0.3, S * 1.2);
    ctx.lineTo(-S * 0.3, -S * 0.2);
    ctx.lineTo(S * 0.6, -S * 0.2);
    ctx.lineTo(S * 0.6, -S * 0.6);
    ctx.lineTo(S * 1.3, 0);
    ctx.lineTo(S * 0.6, S * 0.6);
    ctx.lineTo(S * 0.6, S * 0.2);
    ctx.lineTo(S * 0.3, S * 0.2);
    ctx.lineTo(S * 0.3, S * 1.2);
    ctx.closePath();
    ctx.fill();
    ctx.restore();
  }

  function drawBuilding(d: Decor) {
    const poly = d.poly!;
    path(poly);
    ctx.fillStyle = d.style === "canteen" || d.style === "post" || d.style === "school" ? pal.paper : pal.paperShade;
    ctx.fill();
    ctx.lineWidth = 1.5;
    ctx.strokeStyle = pal.paperInk;
    ctx.globalAlpha = 0.35;
    ctx.stroke();
    ctx.globalAlpha = 1;
    if (d.label) {
      const [cx, cy] = centroid(poly);
      label(d.label, X(cx), Y(cy), S * 1.4, pal.paperInk, 700);
    }
  }

  function drawSign(d: Decor) {
    const x = X(d.x!);
    const y = Y(d.y!);
    const r = Math.max(9, S * 0.7);
    ctx.beginPath();
    if (d.kind === "stop") {
      for (let i = 0; i < 8; i++) {
        const a = Math.PI / 8 + (i * Math.PI) / 4;
        ctx.lineTo(x + r * Math.cos(a), y + r * Math.sin(a));
      }
      ctx.closePath();
      ctx.fillStyle = pal.danger;
      ctx.fill();
      label(d.label ?? "停", x, y, r * 0.95, pal.paint, 800);
      return;
    }
    if (d.kind === "speed") {
      ctx.arc(x, y, r, 0, Math.PI * 2);
      ctx.fillStyle = pal.paint;
      ctx.fill();
      ctx.lineWidth = Math.max(2, r * 0.22);
      ctx.strokeStyle = pal.danger;
      ctx.stroke();
      label(d.label ?? "", x, y, r * 0.9, pal.paperInk, 800);
      return;
    }
    const text = d.label ?? "";
    ctx.font = `700 ${Math.max(10, S * 0.6)}px ${pal.font}`;
    const w = ctx.measureText(text).width + 10;
    ctx.fillStyle = d.kind === "crossing" ? pal.sky : pal.paper;
    ctx.fillRect(x - w / 2, y - r * 0.8, w, r * 1.6);
    label(text, x, y, S * 0.6, d.kind === "crossing" ? pal.paint : pal.paperInk, 700);
  }

  function drawResident(wx: number, wy: number, kind: string) {
    const x = X(wx);
    const y = Y(wy);
    const r = Math.max(6, S * 0.45);
    ctx.beginPath();
    ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.fillStyle = kind === "penguin" ? pal.carInk : kind === "bear" ? pal.paperShade : pal.paint;
    ctx.fill();
    ctx.lineWidth = 1.5;
    ctx.strokeStyle = pal.ink;
    ctx.stroke();
    if (kind === "rabbit") {
      ctx.fillStyle = pal.paint;
      ctx.fillRect(x - r * 0.55, y - r * 2, r * 0.35, r * 1.3);
      ctx.fillRect(x + r * 0.2, y - r * 2, r * 0.35, r * 1.3);
    }
    ctx.fillStyle = kind === "penguin" ? pal.paint : pal.carInk;
    ctx.beginPath();
    ctx.arc(x - r * 0.35, y - r * 0.1, r * 0.13, 0, Math.PI * 2);
    ctx.arc(x + r * 0.35, y - r * 0.1, r * 0.13, 0, Math.PI * 2);
    ctx.fill();
  }

  function drawCoach(wx: number, wy: number) {
    const x = X(wx);
    const y = Y(wy);
    const r = Math.max(8, S * 0.6);
    ctx.beginPath();
    ctx.ellipse(x, y, r * 1.2, r * 0.9, 0, 0, Math.PI * 2);
    ctx.fillStyle = pal.leaf;
    ctx.fill();
    ctx.beginPath();
    ctx.arc(x + r * 1.3, y - r * 0.2, r * 0.45, 0, Math.PI * 2);
    ctx.fillStyle = pal.tree;
    ctx.fill();
    label("龟教练", x, y - r * 1.5, Math.max(10, S * 0.5), pal.ink, 700);
  }

  function drawCar(f: Frame) {
    const car = f.course.car;
    const p = f.pose;
    const x = X(p.x);
    const y = Y(p.y);
    const angle = Math.atan2(-p.hy, p.hx);
    const len = (car.rear + car.wheelbase + car.front) * S;
    const wid = car.width * S;
    const rear = car.rear * S;
    ctx.save();
    ctx.translate(x, y);
    ctx.rotate(angle);
    // 车轮（前轮随方向盘转动）
    const wheel = (wx: number, wy: number, rot: number) => {
      ctx.save();
      ctx.translate(wx, wy);
      ctx.rotate(rot);
      ctx.fillStyle = pal.carInk;
      ctx.fillRect(-S * 0.35, -S * 0.13, S * 0.7, S * 0.26);
      ctx.restore();
    };
    const steerAngle = -(f.steer / car.steer_steps) * ((car.steer_max_deg * Math.PI) / 180);
    const wb = car.wheelbase * S;
    wheel(0, -wid / 2, 0);
    wheel(0, wid / 2, 0);
    wheel(wb, -wid / 2, steerAngle);
    wheel(wb, wid / 2, steerAngle);
    // 车身
    roundRect(-rear, -wid / 2 + S * 0.08, len, wid - S * 0.16, S * 0.45);
    ctx.fillStyle = pal.car;
    ctx.fill();
    ctx.lineWidth = 1.5;
    ctx.strokeStyle = pal.carInk;
    ctx.stroke();
    // 挡风玻璃与车顶
    roundRect(wb - S * 0.9, -wid / 2 + S * 0.3, S * 0.55, wid - S * 0.6, S * 0.15);
    ctx.fillStyle = pal.glass;
    ctx.fill();
    // 车里的 TA（坐在左侧驾驶位；局部坐标里车头朝 +x，左侧是 -y）：圆脑袋加两只朝前的耳朵
    const hx0 = wb - S * 1.5;
    const hy0 = -S * 0.35;
    const hr = S * 0.34;
    ctx.fillStyle = pal.pet;
    ctx.beginPath();
    ctx.arc(hx0, hy0, hr, 0, Math.PI * 2);
    ctx.fill();
    ctx.beginPath();
    for (const side of [-1, 1]) {
      ctx.moveTo(hx0 + hr * 0.2, hy0 + side * hr * 0.95);
      ctx.lineTo(hx0 + hr * 1.25, hy0 + side * hr * 0.75);
      ctx.lineTo(hx0 + hr * 0.75, hy0 + side * hr * 0.1);
    }
    ctx.fill();
    // 尾灯：刹车红、倒挡白
    const tail = f.brake ? pal.danger : f.gear === -1 ? pal.paint : null;
    if (tail) {
      ctx.fillStyle = tail;
      ctx.fillRect(-rear - S * 0.05, -wid / 2 + S * 0.15, S * 0.18, S * 0.35);
      ctx.fillRect(-rear - S * 0.05, wid / 2 - S * 0.5, S * 0.18, S * 0.35);
    }
    // 转向灯（-1 左、1 右；车头朝 +x，左侧是 -y 屏幕方向）
    if (f.blink !== 0 && f.blinkOn) {
      ctx.fillStyle = pal.sun;
      const side = f.blink === -1 ? -1 : 1;
      const yy = side * (wid / 2 - S * 0.12);
      ctx.beginPath();
      ctx.arc(len - rear - S * 0.15, yy, S * 0.2, 0, Math.PI * 2);
      ctx.arc(-rear + S * 0.15, yy, S * 0.2, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.restore();
  }

  function roundRect(x: number, y: number, w: number, h: number, r: number) {
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.lineTo(x + w - r, y);
    ctx.quadraticCurveTo(x + w, y, x + w, y + r);
    ctx.lineTo(x + w, y + h - r);
    ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
    ctx.lineTo(x + r, y + h);
    ctx.quadraticCurveTo(x, y + h, x, y + h - r);
    ctx.lineTo(x, y + r);
    ctx.quadraticCurveTo(x, y, x + r, y);
    ctx.closePath();
  }
}

function centroid(poly: Poly): Vec {
  let x = 0;
  let y = 0;
  for (const p of poly) {
    x += p[0];
    y += p[1];
  }
  return [x / poly.length, y / poly.length];
}
