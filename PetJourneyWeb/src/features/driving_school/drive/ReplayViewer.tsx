/**
 * 成绩单里的回放：用服务端保存的操作记录在本地重新复算（同一套确定性代码），逐 tick 还原车的位置；
 * 时间轴上标出每一次扣分、红线与到位，点标记跳到发生前 1.5 秒。
 */
import { useEffect, useMemo, useRef, useState } from "react";
import type { DriveItemProgress } from "@/shared/contracts";
import { Button } from "@/shared/ui";
import { Replay } from "../sim/replay";
import type { Course, InputEventT, RouteState, SimEventT } from "../sim/types";
import { formatTicks, reducedMotion } from "../text";
import { type Camera, draw, fitCamera, followCamera, type Palette, readPalette } from "./render";

interface FrameRec {
  x: number;
  y: number;
  hx: number;
  hy: number;
  s: number;
  gear: number;
  brake: boolean;
  blink: number;
  knocked: number;
  cw: number | null;
  moved: number;
  line: string | null;
}

function record(course: Course, events: InputEventT[], upto: number): { frames: FrameRec[]; knocked: string[]; sim: SimEventT[] } {
  const replay = new Replay(course);
  const frames: FrameRec[] = [];
  let index = 0;
  let line: string | null = null;
  const push = () => {
    const c = replay.car;
    const r: RouteState | null = replay.r;
    frames.push({ x: c.x, y: c.y, hx: c.hx, hy: c.hy, s: c.s, gear: c.gear, brake: replay.brake === 1, blink: replay.blink, knocked: replay.knocked.length, cw: r?.cw_tick ?? null, moved: r?.moved ?? 0, line });
  };
  push();
  while (replay.tick < upto && replay.status === "running") {
    const t = replay.tick;
    const chunk: InputEventT[] = [];
    while (index < events.length && events[index].t === t) chunk.push(events[index++]);
    const fresh = replay.apply(chunk, t + 1);
    for (const e of fresh) if (e.k === "line") line = e.ref;
    if (!replay.pressed) line = null;
    push();
  }
  return { frames, knocked: replay.knocked, sim: replay.events };
}

export function ReplayViewer({ items, reasons }: { items: DriveItemProgress[]; reasons: Record<string, string> }) {
  const [itemIndex, setItemIndex] = useState(0);
  const item = items[itemIndex];
  const course = item.course as unknown as Course;
  const data = useMemo(() => record(course, item.events as InputEventT[], item.committed_tick), [course, item]);
  const [tick, setTick] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(2);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const paletteRef = useRef<Palette | null>(null);
  const last = data.frames.length - 1;

  useEffect(() => {
    setTick(0);
    setPlaying(false);
  }, [itemIndex]);

  useEffect(() => {
    if (!playing) return;
    let raf = 0;
    let prev = performance.now();
    let acc = 0;
    const loop = (now: number) => {
      acc += ((now - prev) * 30 * speed) / 1000;
      prev = now;
      const step = Math.floor(acc);
      if (step > 0) {
        acc -= step;
        setTick((t) => {
          const next = Math.min(last, t + step);
          if (next >= last) setPlaying(false);
          return next;
        });
      }
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [playing, speed, last]);

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;
    paletteRef.current ??= readPalette(canvas);
    const rect = canvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    const w = Math.max(1, Math.round(rect.width));
    const h = Math.max(1, Math.round(rect.height));
    canvas.width = w * dpr;
    canvas.height = h * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const f = data.frames[Math.min(tick, last)];
    const p = { x: f.x, y: f.y, hx: f.hx, hy: f.hy };
    const cam: Camera = course.kind === "route" ? followCamera(p, w, h) : fitCamera(course.view, w, h);
    const route: RouteState | null = course.route
      ? { checks: [], moved: f.moved, stop_ok: 0, stop_done: 0, cw_tick: f.cw, light_done: 0, turned: 0, invite_tick: null, invite_done: 0, speeding: 0 }
      : null;
    draw(ctx, w, h, cam, {
      course,
      pose: p,
      steer: f.s,
      gear: f.gear,
      brake: f.brake,
      blink: f.blink,
      tick,
      knocked: data.knocked.slice(0, f.knocked),
      route,
      pressedLine: f.line,
      practice: false,
      predicted: null,
      blinkOn: reducedMotion() || Math.floor(tick / 12) % 2 === 0,
    }, paletteRef.current);
  }, [tick, data, course, last]);

  const marks = data.sim.filter((e) => e.p > 0 || e.f || e.k === "done");
  return (
    <div className="ds-replay">
      {items.length > 1 ? (
        <div className="ds-segmented" role="group" aria-label="选择项目">
          {items.map((it, i) => (
            <button key={it.item} type="button" aria-pressed={i === itemIndex} onClick={() => setItemIndex(i)}>
              {it.title}
            </button>
          ))}
        </div>
      ) : null}
      <canvas ref={canvasRef} className="ds-canvas ds-canvas--replay" role="img" aria-label={`${item.title}回放，第 ${formatTicks(tick)}`} />
      <div className="ds-timeline">
        <input type="range" min={0} max={last} value={tick} aria-label="回放时间" onChange={(e) => setTick(Number(e.target.value))} />
        <div className="ds-timeline__marks" aria-hidden="true">
          {marks.map((e, i) => (
            <span key={i} className={`ds-mark ${e.k === "done" ? "is-good" : "is-bad"}`} style={{ left: `${(e.t / Math.max(1, last)) * 100}%` }} />
          ))}
        </div>
      </div>
      <div className="ps-row" style={{ justifyContent: "space-between" }}>
        <div className="ps-row">
          <Button size="sm" variant="primary" icon={playing ? "pause" : "play"} onClick={() => (tick >= last ? (setTick(0), setPlaying(true)) : setPlaying(!playing))}>
            {playing ? "暂停" : "播放"}
          </Button>
          <Button size="sm" onClick={() => setSpeed(speed === 1 ? 2 : speed === 2 ? 4 : 1)}>
            ×{speed}
          </Button>
        </div>
        <span className="ps-muted">
          {formatTicks(tick)} / {formatTicks(last)}
        </span>
      </div>
      {marks.length ? (
        <ul className="ds-marks-list">
          {marks.map((e, i) => (
            <li key={i}>
              <button type="button" className="ds-link" onClick={() => (setPlaying(false), setTick(Math.max(0, e.t - 45)))}>
                {formatTicks(e.t)} · {e.k === "done" ? "停稳到位" : reasons[e.k] ?? e.k}
                {e.p > 0 ? ` −${e.p}` : e.f ? "（红线）" : ""}
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="ps-muted">这一项没有扣分。</p>
      )}
    </div>
  );
}
