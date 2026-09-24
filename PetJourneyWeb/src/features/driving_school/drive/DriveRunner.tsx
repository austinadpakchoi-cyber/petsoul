/**
 * 科二 / 科三的考局界面（也用于练习与比赛现场体验版）：
 * - 顶部约 10%：科目、项目、剩余时间、得分、暂停；中部约 60%：训练场画面；底部约 30%：操作区；
 * - 固定步长 30Hz 本地驾驶，约每秒上传一段操作，出现判定事件时立即上传，暂停 / 切后台时也上传；
 * - 服务端复算结果是准绳：对不上就按服务端记录重新同步；断线自动暂停，恢复后原样续传，不重新抽题、不抹掉扣分。
 */
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import type { DriveItemProgress, InputChunk, InputResult, SchoolSession, SessionResult } from "@/shared/contracts";
import type { ApiError } from "@/shared/api/errors";
import { Button, Icon } from "@/shared/ui";
import type { Course, SimEventT, Snapshot } from "../sim/types";
import { formatTicks, reducedMotion } from "../text";
import { Controls, controlsKey, loadSteerMode, saveSteerMode, type SteerMode, SteerModeToggle } from "./Controls";
import { DriveEngine, lerpPose, pose } from "./engine";
import { type Camera, createStaticLayerCache, drawCached, DRIVE_SPRITE_URLS, type DriveSprites, fitCamera, followCamera, type FrameMark, loadDriveSprites, type Palette, readPalette } from "./render";
import { Uploader } from "./uploader";

/** 画布最多按 2 倍像素画：3 倍屏（多数新手机）像素量是 2 倍的 2.25 倍，画面看不出差别，每帧填充却重得多。 */
export const MAX_CANVAS_DPR = 2;

/** 暂停的原因：决定暂停卡的标题和那一句说明（说人话，不露“服务器 / 同步”这类词；考场＝服务端）。 */
export type PauseWhy = "manual" | "hidden" | "offline" | "back" | "resume" | "resynced" | "lost";

export function pauseCopy(why: PauseWhy, practice: boolean): { title: string; line: string } {
  const kept = practice ? "扣分和车的位置都会保留。" : "扣分和车的位置都会保留，不会重新抽题。";
  switch (why) {
    case "hidden":
      return { title: "切到后台，已自动暂停", line: kept };
    case "offline":
      return { title: "信号断了，已自动暂停", line: "信号回来后会补传刚才的操作，扣分和位置都会保留。" };
    case "back":
      return { title: "信号恢复了", line: "刚才的操作已经补传好，点“继续”接着开。" };
    case "resume":
      return { title: "欢迎回来", line: "按考场保存的位置接着开，之前的扣分都还在。" };
    case "resynced":
      return { title: "已按考场的记录对齐", line: "位置和扣分以考场保存的为准，点“继续”接着开。" };
    case "lost":
      return { title: "暂时连不上考场", line: "连上后按考场保存的位置和扣分接着开。" };
    default:
      return { title: "已暂停", line: kept };
  }
}

const TICK_MS = 1000 / 30;
const UPLOAD_EVERY = 30;
/** 压线、碰锥、到位的提示在画面上停留的时长：场地描边与分数高亮 1.2 秒，画面里的“−5 压线”标记 45 个 tick（1.5 秒）。 */
const FLASH_MS = 1200;
const MARK_TICKS = 45;
/** 剩余 30 秒起，剩余时间变成警示色，并提示一次。 */
const LOW_TIME_TICKS = 30 * 30;

export interface DriveBackend {
  upload(chunk: InputChunk): Promise<InputResult>;
  pause(): Promise<unknown>;
  reload(): Promise<SchoolSession>;
}

export interface LocalItemSummary {
  item: string;
  title: string;
  status: string;
  events: SimEventT[];
  ticks: number;
}

type Phase = "ready" | "driving" | "paused" | "syncing" | "between" | "finished";

interface Toast {
  id: number;
  text: string;
  tone: "bad" | "good" | "info";
}

const CHECKS: [number, string][] = [
  [1, "系好安全带"],
  [2, "调好后视镜"],
  [3, "看看四周"],
];

function courseOf(item: DriveItemProgress): Course {
  return item.course as unknown as Course;
}

function snapshotOf(item: DriveItemProgress): Snapshot | null {
  return (item.snapshot as unknown as Snapshot | null) ?? null;
}

/**
 * 续考（刷新、离开再回来、按考场记录对齐）时，快照里视频邀请已经弹出、还没处理（还在窗口里）：卡片要接着显示。
 * 原来显示状态开局总是“没有”，窗口会安静地过期，这一项就测不到了（第三批报的）。
 */
export function invitePending(engine: DriveEngine): boolean {
  const r = engine.replay.r;
  return !!r && r.invite_tick !== null && !r.invite_done;
}

export function DriveRunner({
  title,
  items: initialItems,
  startIndex,
  practice,
  reasons,
  petLines,
  hints,
  backend,
  exitLabel,
  onExit,
  onFinished,
  onVoid,
}: {
  title: string;
  items: DriveItemProgress[];
  startIndex: number;
  practice: boolean;
  reasons: Record<string, string>;
  petLines: Record<string, string>;
  /** 练习提示（按项目） */
  hints: Record<string, string>;
  backend: DriveBackend | null;
  exitLabel: string;
  onExit: () => void;
  onFinished: (result: SessionResult | null, local: LocalItemSummary[]) => void;
  onVoid: (message: string) => void;
}) {
  const [items, setItems] = useState(initialItems);
  const [index, setIndex] = useState(startIndex);
  const [engine, setEngine] = useState(() => new DriveEngine(courseOf(initialItems[startIndex]), snapshotOf(initialItems[startIndex])));
  const [phase, setPhaseState] = useState<Phase>(() => (engine.tick > 0 ? "paused" : "ready"));
  const [version, setVersion] = useState(0);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [offline, setOffline] = useState(false);
  const [lost, setLost] = useState(false);
  const [invite, setInvite] = useState(() => invitePending(engine));
  const [why, setWhy] = useState<PauseWhy>(engine.tick > 0 ? "resume" : "manual");
  const [mode, setMode] = useState<SteerMode>(loadSteerMode);
  // 静音也看得懂：扣分 / 红线时场地描红、分数变红，到位时场地描绿；FLASH_MS 后恢复（减少动态效果时只换颜色、不做动画）。
  const [flash, setFlash] = useState<{ tone: "bad" | "good"; id: number } | null>(null);
  const [hit, setHit] = useState(0);
  const [ended, setEnded] = useState<{ kind: string; label: string; result: SessionResult | null } | null>(null);
  const [baseDeducted, setBaseDeducted] = useState(() =>
    initialItems.slice(0, startIndex).reduce((sum, it) => sum + it.sim_events.reduce((a, e) => a + e.p, 0), 0),
  );
  const phaseRef = useRef(phase);
  const engineRef = useRef(engine);
  const indexRef = useRef(index);
  const uploaderRef = useRef<Uploader | null>(null);
  const snapsRef = useRef(new Map<number, Snapshot>());
  const pressedRef = useRef<string | null>(null);
  const localRef = useRef<LocalItemSummary[]>([]);
  const toastSeq = useRef(0);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const paletteRef = useRef<Palette | null>(null);
  const finishedRef = useRef(false);
  const inviteRef = useRef(invite);
  /** 画面里的扣分标记（世界坐标 + 发生的 tick）：压线标在车上，碰锥标在锥桶上。 */
  const marksRef = useRef<(FrameMark & { tick: number })[]>([]);
  const lowToldRef = useRef(false);
  // 素材（小车、场地装饰）：到了就用图片画，没到或加载失败就是代码画法；每个考局页只加载一次
  const spritesRef = useRef<DriveSprites | null>(null);
  // 静态层（地面加装饰）离屏缓存：每帧只贴一次，再画会变的东西（接素材后 4 倍降速 p95 从 16.8 涨到 33.4ms 才加的）
  const staticRef = useRef(createStaticLayerCache());
  spritesRef.current ??= loadDriveSprites(DRIVE_SPRITE_URLS);
  // 左上角状态徽标占住的框（画布坐标）：画面里的建筑名、场地名落进来就挪到它下面（巡检第 6 批：320 宽压住“农场路口”）
  const hudRef = useRef<HTMLDivElement>(null);
  const hudBoxRef = useRef<{ w: number; h: number } | null>(null);
  useLayoutEffect(() => {
    const hud = hudRef.current;
    const canvas = canvasRef.current;
    if (!hud || !canvas) return;
    const a = hud.getBoundingClientRect();
    const c = canvas.getBoundingClientRect();
    hudBoxRef.current = a.width > 0 ? { w: Math.round(a.right - c.left + 4), h: Math.round(a.bottom - c.top + 4) } : null;
  });
  // 父组件传入的回调与文字放进 ref：循环和上传器只建一次，不因父组件重渲染而重建（否则会丢掉半个 tick 的累计时间与排队片段）。
  const live = useRef({ reasons, petLines, onFinished, onVoid, backend });
  live.current = { reasons, petLines, onFinished, onVoid, backend };
  const hasBackend = backend !== null;
  engineRef.current = engine;
  indexRef.current = index;

  const setPhase = useCallback((next: Phase) => {
    phaseRef.current = next;
    setPhaseState(next);
  }, []);

  const toast = useCallback((text: string, tone: Toast["tone"] = "info") => {
    const id = ++toastSeq.current;
    setToasts((list) => [...list.slice(-2), { id, text, tone }]);
    window.setTimeout(() => setToasts((list) => list.filter((t) => t.id !== id)), 2600);
  }, []);

  const finish = useCallback(
    (result: SessionResult | null) => {
      if (finishedRef.current) return;
      finishedRef.current = true;
      setPhase("finished");
      uploaderRef.current?.close();
      // 红线、超时、出界：先在考场停一张结果卡，看清楚为什么结束了再去成绩单（巡检第 6 批：原来 0.1 秒就跳走）。
      // 这时成绩已经由考场结算好（或体验版在本地算好），停这一下不会丢数据。中途放弃不停。
      const localFatal = localRef.current.flatMap((s) => s.events).find((e) => e.f);
      const kind = result?.fatal?.kind ?? localFatal?.k ?? null;
      if (kind && kind !== "abandoned") {
        const label = result?.fatal?.label ?? live.current.reasons[kind] ?? kind;
        setEnded({ kind, label, result });
        return;
      }
      live.current.onFinished(result, localRef.current);
    },
    [setPhase],
  );

  const voided = useCallback(
    (message: string) => {
      if (finishedRef.current) return;
      finishedRef.current = true;
      setPhase("finished");
      uploaderRef.current?.close();
      live.current.onVoid(message);
    },
    [setPhase],
  );

  /** 按服务端记录重建（409 或快照对不上时）。 */
  const resyncFromServer = useCallback(async () => {
    const remote = live.current.backend;
    if (!remote) return;
    uploaderRef.current?.reset();
    snapsRef.current.clear();
    setPhase("syncing");
    try {
      const session = await remote.reload();
      if (session.state === "settled") return finish(session.result);
      if (session.state === "void") return voided("这场考局已经作废，不计次。");
      const drive = session.drive!;
      const current = drive.items[drive.current_item];
      setItems(drive.items);
      setIndex(drive.current_item);
      setBaseDeducted(drive.items.slice(0, drive.current_item).reduce((sum, it) => sum + it.sim_events.reduce((a, e) => a + e.p, 0), 0));
      const next = new DriveEngine(courseOf(current), snapshotOf(current));
      engineRef.current = next;
      marksRef.current = [];
      lowToldRef.current = false;
      inviteRef.current = invitePending(next);
      setInvite(inviteRef.current);
      setEngine(next);
      setWhy("resynced");
      setPhase(next.tick > 0 ? "paused" : "ready");
    } catch {
      // 连服务器记录都取不到：不让继续开（本地状态可能和服务器不一致），只提供“重新连接”。
      setLost(true);
      setWhy("lost");
      setPhase("paused");
      return;
    }
    setLost(false);
  }, [finish, voided, setPhase]);

  // 上传器：严格按顺序发送；每个考局实例一个。
  useEffect(() => {
    if (!hasBackend) return;
    const uploader = new Uploader((chunk) => live.current.backend!.upload(chunk), {
      result(result: InputResult, chunk: InputChunk) {
        const local = snapsRef.current.get(chunk.upto_tick);
        for (const key of [...snapsRef.current.keys()]) if (key <= chunk.upto_tick) snapsRef.current.delete(key);
        if (result.session_state === "settled") return finish(result.result);
        if (result.session_state === "void") return voided("这场考局已经作废，不计次。");
        const server = result.snapshot as unknown as Snapshot | null;
        if (chunk.item_index === indexRef.current && local && server && !DriveEngine.agrees(local, server)) {
          void resyncFromServer();
          return;
        }
        if (chunk.item_index === indexRef.current && result.item_status === "done" && result.current_item > chunk.item_index) {
          setBaseDeducted(result.deducted);
          setPhase("between");
        }
      },
      rejected(error: ApiError) {
        const reason = typeof error.details?.reason === "string" ? error.details.reason : "";
        // 作废说法照用原话：能走到这里的只有后端的 platform_fault（409，details 带 reason），原话是写给玩家的“考局出现异常，已作废，不计次。”；
        // 这种错误 playerMessage 与 message 一字不差（带 details 就不算路由级 404，错误码也不是“没开放”）。路由级 404 没有 reason，走下面的重新同步。
        if (reason === "platform_fault") return voided(error.message);
        void resyncFromServer();
      },
      offline(isOffline: boolean) {
        setOffline(isOffline);
        if (isOffline && phaseRef.current === "driving") {
          setPhase("paused");
          setWhy("offline");
        } else if (!isOffline && phaseRef.current === "paused") {
          // 补传成功：暂停卡改说“信号恢复了”，不再停在“信号断了”（巡检第 5 批）
          setWhy((w) => (w === "offline" ? "back" : w));
        }
      },
    });
    uploaderRef.current = uploader;
    return () => {
      // 离开页面（包括开着车直接返回）：先把还没交出去的操作收成最后一段，再在后台按顺序发完，不丢刚发生的扣分；
      // 考局已结束时 finish / voided 已经 close，这里什么也不会发。
      const last = engineRef.current.takeChunk(indexRef.current);
      if (last) uploader.push(last);
      uploader.detach();
      uploaderRef.current = null;
    };
  }, [hasBackend, finish, voided, resyncFromServer, setPhase]);

  const flush = useCallback(() => {
    const eng = engineRef.current;
    const chunk = eng.takeChunk(indexRef.current);
    if (!chunk || !uploaderRef.current) return;
    snapsRef.current.set(chunk.upto_tick, eng.replay.snapshot());
    uploaderRef.current.push(chunk);
  }, []);

  const pause = useCallback(
    (reason: PauseWhy = "manual") => {
      if (phaseRef.current !== "driving") return;
      setPhase("paused");
      setWhy(reason);
      flush();
      void live.current.backend?.pause().catch(() => undefined);
    },
    [flush, setPhase],
  );

  /** 场地描边与分数高亮：FLASH_MS 后自动恢复；后来的提示覆盖先前的。 */
  const flashField = useCallback((tone: "bad" | "good", deducted: boolean) => {
    const id = ++toastSeq.current;
    setFlash({ tone, id });
    if (deducted) setHit(id);
    window.setTimeout(() => {
      setFlash((f) => (f && f.id === id ? null : f));
      setHit((h) => (h === id ? 0 : h));
    }, FLASH_MS);
  }, []);

  const handleEvents = useCallback(
    (events: SimEventT[]) => {
      const { reasons: labels, petLines: lines } = live.current;
      const eng = engineRef.current;
      const car = eng.replay.car;
      const body = eng.course.car;
      // 车身中心（后轴往前半个车身）：压线、红线的标记标在车上
      const mid = (body.wheelbase + body.front - body.rear) / 2;
      const atCar = { x: car.x + car.hx * mid, y: car.y + car.hy * mid };
      for (const e of events) {
        if (e.k === "invite_shown") {
          inviteRef.current = true;
          setInvite(true);
          continue;
        }
        if (e.k === "line") pressedRef.current = e.ref;
        if (e.k === "done") {
          toast(`到位！${lines.park ?? "停稳了。"}`, "good");
          flashField("good", false);
          continue;
        }
        const text = labels[e.k] ?? e.k;
        if (e.f) toast(e.k === "timeout" || e.k === "out_of_bounds" ? `${text}，这一项结束了` : `红线：${text}，已自动制动`, "bad");
        else if (e.p > 0) toast(`${text} −${e.p}`, "bad");
        if (e.f || e.p > 0) {
          const cone = e.k === "cone" ? eng.course.cones.find((c) => c.id === e.ref) : undefined;
          marksRef.current = [
            ...marksRef.current.slice(-3),
            { ...(cone ? { x: cone.x, y: cone.y } : atCar), text: e.p > 0 ? `−${e.p} ${text}` : text, tone: "bad", tick: eng.tick },
          ];
          flashField("bad", e.p > 0);
        }
      }
    },
    [toast, flashField],
  );

  // 固定步长循环 + 绘制
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    paletteRef.current = readPalette(canvas);
    let paletteVersion = 0;
    const scheme = window.matchMedia?.("(prefers-color-scheme: dark)");
    const onScheme = () => {
      paletteRef.current = readPalette(canvas);
      paletteVersion += 1;
    };
    scheme?.addEventListener?.("change", onScheme);
    const still = reducedMotion();
    const sprites = spritesRef.current!;
    let raf = 0;
    let last = performance.now();
    let acc = 0;
    let sinceUpload = 0;
    let sinceRender = 0;
    // 画布尺寸：有 ResizeObserver 时只在尺寸变了才量（每帧 getBoundingClientRect 会在 React 刚改过 DOM 的那一帧强制同步排版）；
    // 没有（jsdom）就每帧量。
    let size: { w: number; h: number } | null = null;
    const observer = typeof ResizeObserver === "function" ? new ResizeObserver(() => (size = null)) : null;
    observer?.observe(canvas);
    // 同一画面不重画：暂停、准备、两项之间，车没动、灯没闪时停在同一帧（省电，也不和 React 抢主线程）
    let drawnKey = "";
    // 挡位、停没停稳一变就刷新操作区（换挡键能不能按、按下态），不等每 6 个 tick 的例行刷新
    let lastGear = engineRef.current.replay.car.gear;
    let lastStopped = engineRef.current.replay.car.v === 0;
    const loop = (now: number) => {
      const eng = engineRef.current;
      const dt = Math.min(250, now - last);
      last = now;
      if (phaseRef.current === "driving") {
        acc += dt;
        while (acc >= TICK_MS && eng.running) {
          acc -= TICK_MS;
          const events = eng.advance();
          sinceUpload += 1;
          sinceRender += 1;
          if (eng.replay.pressed === 0) pressedRef.current = null;
          if (events.length) {
            handleEvents(events);
            flush();
            sinceUpload = 0;
            setVersion((v) => v + 1);
          } else if (sinceUpload >= UPLOAD_EVERY) {
            flush();
            sinceUpload = 0;
          }
          if (inviteRef.current && eng.replay.r?.invite_done) {
            inviteRef.current = false;
            setInvite(false);
          }
          if (!lowToldRef.current && eng.running && eng.limit - eng.tick <= LOW_TIME_TICKS) {
            lowToldRef.current = true;
            toast("还剩 30 秒", "bad");
            setVersion((v) => v + 1);
          }
        }
        const stoppedNow = eng.replay.car.v === 0;
        if (sinceRender >= 6 || eng.replay.car.gear !== lastGear || stoppedNow !== lastStopped) {
          sinceRender = 0;
          lastGear = eng.replay.car.gear;
          lastStopped = stoppedNow;
          setVersion((v) => v + 1);
        }
        if (!eng.running) {
          acc = 0;
          flush();
          const it = eng.course;
          localRef.current = [
            ...localRef.current.filter((s) => s.item !== it.item),
            { item: it.item, title: it.title, status: eng.replay.status, events: eng.replay.events, ticks: eng.tick },
          ];
          if (uploaderRef.current) setPhase("syncing");
          else finish(null);
        }
      } else {
        acc = 0;
      }
      if (!observer || !size) {
        const rect = canvas.getBoundingClientRect();
        size = { w: Math.max(1, Math.round(rect.width)), h: Math.max(1, Math.round(rect.height)) };
      }
      const { w, h } = size;
      const dpr = Math.min(MAX_CANVAS_DPR, window.devicePixelRatio || 1);
      const alpha = phaseRef.current === "driving" ? acc / TICK_MS : 1;
      const current = pose(eng.replay.car);
      const shown = alpha < 1 ? lerpPose(eng.prev, current, alpha) : current;
      const blinkOn = still || Math.floor(now / 400) % 2 === 0;
      const marks = marksRef.current.filter((m) => eng.tick - m.tick < MARK_TICKS);
      const car = eng.replay.car;
      const key = [
        w, h, dpr, shown.x, shown.y, shown.hx, shown.hy, car.s, car.gear, car.v, eng.steerTarget, eng.brake, eng.blink, eng.blink !== 0 && blinkOn,
        eng.tick, eng.replay.knocked.length, pressedRef.current, marks.map((m) => m.tick).join(","), paletteVersion, sprites.version,
        hudBoxRef.current?.w, hudBoxRef.current?.h,
      ].join("|");
      if (key !== drawnKey) {
        drawnKey = key;
        if (canvas.width !== w * dpr || canvas.height !== h * dpr) {
          canvas.width = w * dpr;
          canvas.height = h * dpr;
        }
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        const cam: Camera = eng.course.kind === "route" ? followCamera(shown, w, h) : fitCamera(eng.course.view, w, h);
        drawCached(ctx, w, h, cam, {
          course: eng.course,
          pose: shown,
          steer: car.s,
          gear: car.gear,
          brake: eng.brake,
          blink: eng.blink,
          tick: eng.tick,
          knocked: eng.replay.knocked,
          route: eng.replay.r,
          pressedLine: pressedRef.current,
          practice,
          predicted: practice && eng.running ? eng.predict(eng.course.kind === "route" ? 14 : 6) : null,
          blinkOn,
          marks,
          avoid: hudBoxRef.current,
        }, paletteRef.current!, sprites, staticRef.current, dpr);
      }
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => {
      cancelAnimationFrame(raf);
      observer?.disconnect();
      scheme?.removeEventListener?.("change", onScheme);
    };
  }, [engine, finish, flush, handleEvents, practice, setPhase, toast]);

  // 切后台、页面隐藏：自动暂停并上传
  useEffect(() => {
    const onHide = () => {
      if (document.visibilityState === "hidden") pause("hidden");
    };
    const onOffline = () => pause("offline");
    const onOnline = () => {
      uploaderRef.current?.retryNow();
      // 浏览器说联网了：没有待补传的操作时上传器不会回调，这里直接改说法；还在补传时 offline 仍为真，卡片照旧说“信号断了”
      if (phaseRef.current === "paused") setWhy((w) => (w === "offline" ? "back" : w));
    };
    document.addEventListener("visibilitychange", onHide);
    window.addEventListener("offline", onOffline);
    window.addEventListener("online", onOnline);
    return () => {
      document.removeEventListener("visibilitychange", onHide);
      window.removeEventListener("offline", onOffline);
      window.removeEventListener("online", onOnline);
    };
  }, [pause]);

  // 键盘：← → 转向，↑ 油门，空格或 ↓ 刹车，D / R 换挡，Q / E 转向灯，Esc 暂停
  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (phaseRef.current !== "driving" || e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      const eng = engineRef.current;
      const key = e.key.toLowerCase();
      if (key === "arrowleft") eng.nudgeSteer(1);
      else if (key === "arrowright") eng.nudgeSteer(-1);
      else if (key === "arrowup") eng.setThrottle(true);
      else if (key === " " || key === "arrowdown") eng.setBrake(true);
      else if (key === "d" || key === "r") {
        if (!eng.shift(key === "d" ? 1 : -1) && eng.replay.car.v !== 0) toast("车还在动：先踩刹车停稳，再换挡。");
      } else if (key === "q") eng.setBlink(eng.blink === -1 ? 0 : -1);
      else if (key === "e") eng.setBlink(eng.blink === 1 ? 0 : 1);
      else if (key === "escape") pause();
      else return;
      e.preventDefault();
      setVersion((v) => v + 1);
    };
    const up = (e: KeyboardEvent) => {
      const eng = engineRef.current;
      if (e.key === "ArrowUp") eng.setThrottle(false);
      else if (e.key === " " || e.key === "ArrowDown") eng.setBrake(false);
      else return;
      e.preventDefault();
      setVersion((v) => v + 1);
    };
    window.addEventListener("keydown", down);
    window.addEventListener("keyup", up);
    return () => {
      window.removeEventListener("keydown", down);
      window.removeEventListener("keyup", up);
    };
  }, [pause, toast]);

  const startDriving = () => {
    setWhy("manual");
    setPhase("driving");
  };

  const nextItem = () => {
    const next = indexRef.current + 1;
    const item = items[next];
    if (!item) return;
    const eng = new DriveEngine(courseOf(item), null);
    engineRef.current = eng;
    snapsRef.current.clear();
    pressedRef.current = null;
    marksRef.current = [];
    lowToldRef.current = false;
    inviteRef.current = false;
    setInvite(false);
    setIndex(next);
    setEngine(eng);
    setPhase("ready");
  };

  const item = items[index];
  const course = engine.course;
  const route = course.route;
  const r = engine.replay.r;
  // baseDeducted 平时是“之前各项”的扣分；一项做完进入 between 时，它换成服务端回的整场累计（已含这一项），
  // 这时引擎还是这一项的，不能再加一遍它的扣分（巡检 P1：连考时分数重复扣，点“开始下一项”才恢复）。
  const score = Math.max(0, 100 - baseDeducted - (phase === "between" ? 0 : engine.replay.deducted));
  const kmh = Math.round(Math.abs(engine.replay.car.v) * 30 * 3.6);
  const instruction = useMemo(() => {
    if (!route) return null;
    const [fx, fy] = engine.replay.front;
    const found = route.instructions.find((z) => {
      const xs = z.zone.map((p) => p[0]);
      const ys = z.zone.map((p) => p[1]);
      return fx >= Math.min(...xs) && fx <= Math.max(...xs) && fy >= Math.min(...ys) && fy <= Math.max(...ys);
    });
    return found?.text ?? null;
  }, [route, engine, version]); // version 驱动刷新：车的位置每 tick 都在变
  // “到位了，保持停稳”是结果反馈，不是答案提示：正式考试也显示（巡检第 3 批）；预测轨迹、目标车位高亮、分步提示仍只在练习时有。
  const holding = course.target && engine.replay.hold > 0 ? engine.replay.hold / course.target.hold_ticks : 0;
  const hint = practice ? hints[course.item] ?? null : null;
  const remaining = engine.limit - engine.tick;
  const lowTime = engine.running && remaining <= LOW_TIME_TICKS;
  const onModeChange = (m: SteerMode) => {
    setMode(m);
    saveSteerMode(m);
  };
  // 连不上考场、信号断了，比“为什么暂停”更要紧：标题和说明按这两种情况说
  const pausedCopy = pauseCopy(lost ? "lost" : offline ? "offline" : why, practice);
  void version;

  return (
    <div className="ds-exam" data-tick={engine.tick} data-item={index}>
      {/* 顶栏在 320 宽也不截断：第几项跟在项目名后面，副标题只留“科目 · 练习 / 首次考试 / 补考”。 */}
      <header className="ds-exam__top">
        <div className="ds-exam__title">
          <strong>
            {item.title}
            {items.length > 1 ? (
              <small className="ds-exam__step">
                {index + 1}/{items.length}
              </small>
            ) : null}
          </strong>
          <span>{title}</span>
        </div>
        <div className="ds-exam__stat" aria-label="剩余时间" data-low={lowTime ? "" : undefined}>
          <span>剩余</span>
          <strong>{formatTicks(remaining)}</strong>
        </div>
        <div className="ds-exam__stat" aria-label={practice ? "练习得分（不计成绩）" : "当前得分"} data-hit={hit ? "" : undefined}>
          <span>{practice ? "练习分" : "得分"}</span>
          <strong>{score}</strong>
        </div>
        <Button variant="ghost" size="sm" icon="pause" aria-label="暂停" onClick={() => pause()} disabled={phase !== "driving"} />
      </header>

      <div className="ds-exam__field" data-flash={flash?.tone} data-invite={invite && phase === "driving" ? "" : undefined}>
        <canvas ref={canvasRef} className="ds-canvas" role="img" aria-label={`${course.title}训练场：车速 ${kmh} 公里每小时，${engine.replay.car.gear === -1 ? "倒挡" : "前进挡"}`} />
        <div className="ds-field__hud" ref={hudRef}>
          <span className="ds-badge">{engine.replay.car.gear === -1 ? "R 倒车" : "D 前进"}</span>
          <span className="ds-badge">{kmh} 公里/时</span>
          {route ? <span className="ds-badge">限速 {Math.round(route.speed_limit * 30 * 3.6)}</span> : null}
          {offline ? (
            <span className="ds-badge ds-badge--bad" role="status">
              <Icon name="alert" size={13} /> 信号中断，正在重试
            </span>
          ) : null}
        </div>
        {instruction ? <div className="ds-coach-line">龟教练：{instruction}</div> : null}
        {hint && !instruction ? <div className="ds-coach-line ds-coach-line--hint">提示：{hint}</div> : null}
        <div className="ds-field__feed">
          {holding > 0 ? (
            <div className="ds-hold" role="status">
              到位了，保持停稳 <progress max={1} value={holding} aria-label="停稳进度" />
            </div>
          ) : null}
          <div className="ds-toasts" aria-live="polite">
            {toasts.map((t) => (
              <div key={t.id} className={`ds-toast ds-toast--${t.tone}`}>
                {t.text}
              </div>
            ))}
          </div>
        </div>
        {route && r && !r.moved && phase === "driving" ? (
          <div className="ds-checks" role="group" aria-label="出发前检查">
            {CHECKS.map(([n, text]) => (
              <button
                key={n}
                type="button"
                className="ds-check"
                aria-pressed={r.checks.includes(n)}
                onClick={() => {
                  engine.check(n);
                  setVersion((v) => v + 1);
                }}
              >
                {r.checks.includes(n) ? "✓ " : ""}
                {text}
              </button>
            ))}
          </div>
        ) : null}
        {invite && phase === "driving" ? (
          <div className="ds-invite" role="alertdialog" aria-label="手机收到视频邀请">
            <div>
              <strong>视频邀请</strong>
              <p>朋友邀你看新动画片</p>
            </div>
            <div className="ps-row">
              <Button
                size="sm"
                variant="leaf"
                onClick={() => {
                  engine.invite(false);
                  inviteRef.current = false;
                  setInvite(false);
                }}
              >
                稍后再看
              </Button>
              <Button
                size="sm"
                onClick={() => {
                  engine.invite(true);
                  inviteRef.current = false;
                  setInvite(false);
                  toast("开车时不看视频（考场不会真的打开视频）", "bad");
                }}
              >
                打开
              </Button>
            </div>
          </div>
        ) : null}

        {phase === "ready" ? (
          <div className="ds-overlay">
            <div className="ds-overlay__card">
              <strong className="ps-h2">{course.title}</strong>
              <p className="ps-muted">
                限时 {formatTicks(course.time_limit_ticks)}；{course.kind === "route" ? "按教练的指令开到星球食堂的装卸区，停稳 2 秒。" : course.kind === "curve" ? "沿车道开进终点区，停稳 1 秒。" : "整车停进车位、车身摆正，停稳 2 秒。"}
              </p>
              {hint ? <p className="ds-overlay__hint">{hint}</p> : null}
              <SteerModeToggle mode={mode} onModeChange={onModeChange} />
              <Button variant="primary" block autoFocus onClick={startDriving}>
                {index === 0 ? "开始" : "开始这一项"}
              </Button>
            </div>
          </div>
        ) : null}
        {phase === "paused" ? (
          // 暂停卡：一个标题说清为什么停了，一句话说清什么都不会丢，一个主按钮（继续 / 现在重试 / 重新连接），一个离开；320×568 不用滚动
          <div className="ds-overlay">
            <div className="ds-overlay__card" role="dialog" aria-label={pausedCopy.title}>
              <strong className="ps-h2">{pausedCopy.title}</strong>
              <p className="ps-muted">{pausedCopy.line}</p>
              <SteerModeToggle mode={mode} onModeChange={onModeChange} />
              {lost ? (
                <Button variant="primary" block icon="refresh" autoFocus onClick={() => void resyncFromServer()}>
                  重新连接
                </Button>
              ) : offline ? (
                <Button variant="primary" block icon="refresh" autoFocus onClick={() => uploaderRef.current?.retryNow()}>
                  现在重试
                </Button>
              ) : (
                <Button variant="primary" block autoFocus onClick={startDriving}>
                  继续
                </Button>
              )}
              <Button variant="ghost" block onClick={onExit}>
                {exitLabel}
              </Button>
            </div>
          </div>
        ) : null}
        {phase === "syncing" ? (
          <div className="ds-overlay">
            <div className="ds-overlay__card" role="status">
              <strong className="ps-h2">{engine.replay.status === "done" ? "这一项完成了" : engine.replay.status === "failed" ? "这一项结束了" : "正在核对记录"}</strong>
              <p className="ps-muted">{offline ? "信号断了，回来后会自动补传。" : "考场正在核对这一段操作…"}</p>
            </div>
          </div>
        ) : null}
        {phase === "finished" && ended ? (
          <div className="ds-overlay">
            <div className="ds-overlay__card" role="alertdialog" aria-label="这一局结束了">
              <strong className="ps-h2">
                {ended.kind === "timeout" || ended.kind === "out_of_bounds" ? `${ended.label}，这一局结束了` : `红线：${ended.label}`}
              </strong>
              <p className="ps-muted">
                {ended.kind === "timeout" || ended.kind === "out_of_bounds" ? "" : "已经自动制动。"}
                {hasBackend ? "成绩已经交给考场，扣在哪里、第几秒，成绩单上都写着。" : "这一局到这里结束。"}
              </p>
              <Button variant="primary" block autoFocus onClick={() => live.current.onFinished(ended.result, localRef.current)}>
                {hasBackend ? "看成绩单" : "看结果"}
              </Button>
            </div>
          </div>
        ) : null}
        {phase === "between" ? (
          <div className="ds-overlay">
            <div className="ds-overlay__card">
              <strong className="ps-h2">{item.title}完成！</strong>
              <p className="ps-muted">
                这一项扣 {engine.replay.deducted} 分。下一项：{items[index + 1]?.title}
              </p>
              <Button variant="primary" block autoFocus onClick={nextItem}>
                开始下一项
              </Button>
            </div>
          </div>
        ) : null}
      </div>

      <div className="ds-exam__controls">
        {/* 操作区是 memo 的：只有 controlsKey 变了（挡位、停没停、方向、灯、踏板）才随父组件重渲染 */}
        <Controls engine={engine} mode={mode} showBlinkers={!!route} stateKey={controlsKey(engine)} onNotice={toast} />
      </div>
    </div>
  );
}
