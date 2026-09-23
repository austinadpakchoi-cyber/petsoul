/**
 * 几何判定（逐行对应 PetJourneyBackend/app/web_driving/sim.py）：只用加减乘除与比较，Python 与 JavaScript 逐位一致。
 * 修改这里必须同步修改后端，并重新生成跨语言样例（python scripts/gen_driving_fixtures.py）。
 */
import type { Poly, Vec } from "./types";

export type Box = [number, number, number, number];

export function cross(ax: number, ay: number, bx: number, by: number, px: number, py: number): number {
  return (bx - ax) * (py - ay) - (by - ay) * (px - ax);
}

/** 点在逆时针凸多边形内（含边上）。 */
export function insideConvex(px: number, py: number, poly: Poly): boolean {
  const n = poly.length;
  for (let i = 0; i < n; i++) {
    const a = poly[i];
    const b = poly[(i + 1) % n];
    if (cross(a[0], a[1], b[0], b[1], px, py) < 0) return false;
  }
  return true;
}

function onSegment(ax: number, ay: number, bx: number, by: number, px: number, py: number): boolean {
  const loX = ax < bx ? ax : bx;
  const hiX = ax < bx ? bx : ax;
  const loY = ay < by ? ay : by;
  const hiY = ay < by ? by : ay;
  return loX <= px && px <= hiX && loY <= py && py <= hiY;
}

export function segmentsCross(a: Vec, b: Vec, c: Vec, d: Vec): boolean {
  const d1 = cross(c[0], c[1], d[0], d[1], a[0], a[1]);
  const d2 = cross(c[0], c[1], d[0], d[1], b[0], b[1]);
  const d3 = cross(a[0], a[1], b[0], b[1], c[0], c[1]);
  const d4 = cross(a[0], a[1], b[0], b[1], d[0], d[1]);
  if (((d1 > 0 && d2 < 0) || (d1 < 0 && d2 > 0)) && ((d3 > 0 && d4 < 0) || (d3 < 0 && d4 > 0))) return true;
  if (d1 === 0 && onSegment(c[0], c[1], d[0], d[1], a[0], a[1])) return true;
  if (d2 === 0 && onSegment(c[0], c[1], d[0], d[1], b[0], b[1])) return true;
  if (d3 === 0 && onSegment(a[0], a[1], b[0], b[1], c[0], c[1])) return true;
  return d4 === 0 && onSegment(a[0], a[1], b[0], b[1], d[0], d[1]);
}

export function segmentHitsPoly(a: Vec, b: Vec, poly: Poly): boolean {
  if (insideConvex(a[0], a[1], poly) || insideConvex(b[0], b[1], poly)) return true;
  const n = poly.length;
  for (let i = 0; i < n; i++) {
    if (segmentsCross(a, b, poly[i], poly[(i + 1) % n])) return true;
  }
  return false;
}

export function dist2ToSegment(px: number, py: number, a: Vec, b: Vec): number {
  const dx = b[0] - a[0];
  const dy = b[1] - a[1];
  const len2 = dx * dx + dy * dy;
  let t = 0;
  if (len2 > 0) {
    t = ((px - a[0]) * dx + (py - a[1]) * dy) / len2;
    if (t < 0) t = 0;
    else if (t > 1) t = 1;
  }
  const cx = a[0] + t * dx;
  const cy = a[1] + t * dy;
  const ex = px - cx;
  const ey = py - cy;
  return ex * ex + ey * ey;
}

export function circleHitsPoly(cx: number, cy: number, r: number, poly: Poly): boolean {
  if (insideConvex(cx, cy, poly)) return true;
  const r2 = r * r;
  const n = poly.length;
  for (let i = 0; i < n; i++) {
    if (dist2ToSegment(cx, cy, poly[i], poly[(i + 1) % n]) <= r2) return true;
  }
  return false;
}

export function bbox(points: Vec[]): Box {
  let loX = points[0][0];
  let hiX = points[0][0];
  let loY = points[0][1];
  let hiY = points[0][1];
  for (const p of points) {
    if (p[0] < loX) loX = p[0];
    if (p[0] > hiX) hiX = p[0];
  }
  for (const p of points) {
    if (p[1] < loY) loY = p[1];
    if (p[1] > hiY) hiY = p[1];
  }
  return [loX, loY, hiX, hiY];
}

export function boxesOverlap(a: Box, b: Box, pad = 0): boolean {
  return !(a[2] + pad < b[0] || b[2] + pad < a[0] || a[3] + pad < b[1] || b[3] + pad < a[1]);
}
