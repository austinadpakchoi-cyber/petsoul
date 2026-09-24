/**
 * 成绩单里的回放：用服务端保存的操作记录在本地重新复算（同一套确定性代码），逐 tick 还原车的位置；
 * 时间轴上标出每一次扣分、红线与到位，点标记跳到发生前 1.5 秒。
 * 看得懂错在哪一刻：播到扣分那一刻，画面里在车（或锥桶）上方贴“−5 压线”这类牌子，下面一行写明“第几秒 · 什么事”；
 * 拖动时间轴会先暂停播放。
 */
import { useEffect, useMemo, useRef, useState } from "react";
import type { DriveItemProgress } from "@/shared/contracts";
import { Button } from "@/shared/ui";
import { Replay } from "../sim/replay";
import type { Course, InputEventT, RouteState, SimEventT } from "../sim/types";
import { formatTicks, reducedMotion } from "../text";
import { type Camera, createStaticLayerCache, drawCached, DRIVE_SPRITE_URLS, type DriveSprites, fitCamera, followCamera, type FrameMark, loadDriveSprites, type Palette, readPalette } from "./render";

/** 扣分标记在回放里停留的 tick 数（与考局里一致：1.5 秒） */
const MARK_TICKS = 45;

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

/**
 * 回放定位（给成绩单“错在哪 → 看回放”用）：item 是项目键（如 "reverse_park"），tick 是事发那一刻（扣分明细里的 t），
 * nonce 每次点都换一个值（同一处可以重复点）。收到后切到那一项、跳到事发前约 1.5 秒，停在那里等玩家点播放。
 * 找不到这一项时不动。
 */
export interface ReplaySeek {
  item: string;
  tick: number;
  nonce: number;
}

/** 事发前留出的 tick 数（1.5 秒） */
export const SEEK_LEAD_TICKS = 45;

export function ReplayViewer({ items, reasons, seek }: { items: DriveItemProgress[]; reasons: Record<string, string>; seek?: ReplaySeek | null }) {
  const [itemIndex, setItemIndex] = useState(0);
  // 切项目时 tick 默认回到 0；定位要跳到别的项目时，先把目标 tick 放在这里，切完项目再用
  const pendingTick = useRef<number | null>(null);
  const item = items[itemIndex];
  const course = item.course as unknown as Course;
  const data = useMemo(() => record(course, item.events as InputEventT[], item.committed_tick), [course, item]);
  const [tick, setTick] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(2);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const paletteRef = useRef<Palette | null>(null);
  // 素材只加载一次（useRef 的初值每次渲染都会求值，写成 useRef(loadDriveSprites(...)) 会在回放的每个 tick 新建一批图片）；
  // 每到一张就重画一次
  const [spritesLoaded, setSpritesLoaded] = useState(0);
  const spritesRef = useRef<DriveSprites | null>(null);
  const staticRef = useRef(createStaticLayerCache());
  spritesRef.current ??= loadDriveSprites(DRIVE_SPRITE_URLS, undefined, undefined, () => setSpritesLoaded((n) => n + 1));
  const last = data.frames.length - 1;
  // 每个扣分 / 红线事件的标记位置：碰锥标在锥桶上，其余标在那一刻的车身中心
  const eventMarks = useMemo(() => {
    const car = course.car;
    const mid = (car.wheelbase + car.front - car.rear) / 2;
    return data.sim
      .filter((e) => e.p > 0 || e.f)
      .map((e) => {
        const cone = e.k === "cone" ? course.cones.find((c) => c.id === e.ref) : undefined;
        const f = data.frames[Math.min(e.t, data.frames.length - 1)];
        const label = reasons[e.k] ?? e.k;
        const at = cone ? { x: cone.x, y: cone.y } : { x: f.x + f.hx * mid, y: f.y + f.hy * mid };
        return { ...at, tick: e.t, text: e.p > 0 ? `−${e.p} ${label}` : label, tone: "bad" as const };
      });
  }, [data, course, reasons]);
  const showing = eventMarks.filter((m) => tick >= m.tick && tick - m.tick < MARK_TICKS);

  useEffect(() => {
    setTick(pendingTick.current ?? 0);
    pendingTick.current = null;
    setPlaying(false);
  }, [itemIndex]);

  // 定位：切到那一项、跳到事发前 1.5 秒、停住
  useEffect(() => {
    if (!seek) return;
    const index = items.findIndex((it) => it.item === seek.item);
    if (index < 0) return;
    const target = Math.max(0, Math.min(items[index].committed_tick, seek.tick - SEEK_LEAD_TICKS));
    setPlaying(false);
    if (index === itemIndex) setTick(target);
    else {
      pendingTick.current = target;
      setItemIndex(index);
    }
    // 只在收到新的定位（nonce 变了）时跳；切项目本身不该再触发一次，所以依赖里不放 itemIndex、items
  }, [seek?.nonce, seek?.item, seek?.tick]);

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
    drawCached(ctx, w, h, cam, {
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
      marks: eventMarks.filter((m) => tick >= m.tick && tick - m.tick < MARK_TICKS).map(({ x, y, text, tone }): FrameMark => ({ x, y, text, tone })),
    }, paletteRef.current, spritesRef.current, staticRef.current, dpr);
  }, [tick, data, course, last, eventMarks, spritesLoaded]);

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
      {/* 播到扣分那一刻，下面写明“第几秒 · 什么事”（读屏会念出来） */}
      <p className="ds-replay__now" aria-live="polite">
        {showing.length ? showing.map((m) => `第 ${formatTicks(m.tick)} · ${m.text}`).join("；") : " "}
      </p>
      <div className="ds-timeline">
        <input
          type="range"
          min={0}
          max={last}
          value={tick}
          aria-label="回放时间"
          aria-valuetext={`第 ${formatTicks(tick)}，共 ${formatTicks(last)}`}
          onChange={(e) => {
            // 拖动时先停下，免得播放和手指抢位置
            setPlaying(false);
            setTick(Number(e.target.value));
          }}
        />
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
          <Button size="sm" aria-label={`播放速度 ${speed} 倍，点一下换`} onClick={() => setSpeed(speed === 1 ? 2 : speed === 2 ? 4 : 1)}>
            {speed} 倍速
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
